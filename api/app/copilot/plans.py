"""Workspace-scoped plan acceptance and owner-controlled reminder drafts."""
import json
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field

from api.app import security as sec
from api.app.contracts import Contract, RecordId, ScenarioRequest
from api.app.currencies import CURRENCIES, scale
from api.app.copilot.gapfix import best_plan
from api.app.receivables import owner_transaction
from api.app.routes import db_connection, principal
from api.app.services.finance import fingerprint, project_cashflow, snapshot
from api.app.services.gap_fix import collection_plan
from api.app.services.receivables import open_receipts

router = APIRouter(prefix='/api/copilot')


def schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS gap_plans(
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            breach_date TEXT NOT NULL, shortfall_minor INTEGER NOT NULL, plan_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('proposed','accepted','dismissed')),
            decided_by TEXT, decided_at INTEGER);
        CREATE TABLE IF NOT EXISTS copilot_tasks(
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL, plan_id TEXT REFERENCES gap_plans(id),
            kind TEXT NOT NULL, payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','dismissed')),
            due_on TEXT, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS copilot_tasks_due ON copilot_tasks(business_id,status,due_on);
    """)


def proof_id(business, dataset, receipts, scenario, actions):
    evidence = [business, fingerprint(dataset), [(r.source_id, str(r.due_on), r.amount_minor) for r in receipts],
                scenario.model_dump(mode='json'), actions]
    return sec.signature('collection-plan-v1', evidence)


def propose(db, actor, dataset, receipts, scenario):
    baseline = project_cashflow(dataset, scenario, receipts)
    result = collection_plan(dataset, baseline, receipts)
    plan = best_plan(dataset, scenario, receipts, baseline)
    if plan and actor.role == 'owner':
        identity = proof_id(actor.business_id, dataset, receipts, scenario, plan['actions'])
        body = dict(scenario=scenario.model_dump(mode='json'), actions=plan['actions'])
        db.execute("""INSERT OR IGNORE INTO gap_plans(id,business_id,created_at,breach_date,shortfall_minor,plan_json,status)
                      VALUES (?,?,?,?,?,?,'proposed')""",
                   (identity, actor.business_id, sec.now(), plan['first_shortfall_on'],
                    plan['original_gap_minor'], sec.canonical(body)))
        plan['id'] = identity
    return dict(result, plan=plan, simulation_only=True)


class Accept(Contract):
    plan_id: str = Field(pattern=r'^[a-f0-9]{64}$')


def tasks(db, business, plan_id=None):
    sql = 'SELECT id,payload_json,due_on,status FROM copilot_tasks WHERE business_id=?'
    params = [business]
    if plan_id is None:
        sql += " AND status='open'"
    else:
        sql += ' AND plan_id=?'
        params.append(plan_id)
    rows = db.execute(sql + ' ORDER BY due_on,created_at,id', params)
    return [dict(id=identity, action=json.loads(payload), due_on=due, status=status)
            for identity, payload, due, status in rows]


@router.post('/gap-fix/accept')
def accept(body: Accept, actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        business = owner.business_id
        row = db.execute('SELECT status,plan_json FROM gap_plans WHERE business_id=? AND id=?',
                         (business, body.plan_id)).fetchone()
        if not row:
            sec.fail(404, 'PLAN_NOT_FOUND')
        if row[0] == 'accepted':
            return dict(tasks=tasks(db, business, body.plan_id), replayed=True, simulation_only=True)
        saved = json.loads(row[1])
        dataset = sec.runtime_dataset(db, business)
        receipts = open_receipts(db, business)
        scenario = ScenarioRequest.model_validate(saved['scenario'])
        if row[0] != 'proposed' or proof_id(business, dataset, receipts, scenario, saved['actions']) != body.plan_id:
            sec.fail(409, 'FORECAST_CHANGED_REQUEST_NEW_PLAN')
        pending_sources = {task['action']['source_id'] for task in tasks(db, business)}
        if pending_sources.intersection(action['source_id'] for action in saved['actions']):
            sec.fail(409, 'COLLECTION_TASK_ALREADY_OPEN')
        now = sec.now()
        for action in saved['actions']:
            db.execute("""INSERT INTO copilot_tasks(id,business_id,plan_id,kind,payload_json,due_on,created_at)
                          VALUES (?,?,?,?,?,?,?)""",
                       (uuid.uuid4().hex, business, body.plan_id, action['kind'], sec.canonical(action), action['collect_by'], now))
        db.execute("UPDATE gap_plans SET status='accepted',decided_by=?,decided_at=? WHERE business_id=? AND id=?",
                   (owner.user_id, now, business, body.plan_id))
        sec.audit(db, owner, body.plan_id, 'GAP_PLAN_ACCEPTED', dict(task_count=len(saved['actions'])))
        return dict(tasks=tasks(db, business, body.plan_id), replayed=False, simulation_only=True)


@router.get('/tasks')
def list_tasks(actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        return dict(tasks=tasks(db, owner.business_id), simulation_only=True)


class TaskDecision(Contract):
    status: Literal['done', 'dismissed']


@router.post('/tasks/{task_id}')
def decide(task_id: str, body: TaskDecision, actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        params = (owner.business_id, task_id)
        row = db.execute('SELECT status FROM copilot_tasks WHERE business_id=? AND id=?', params).fetchone()
        if not row:
            sec.fail(404, 'TASK_NOT_FOUND')
        if row[0] == 'open':
            db.execute('UPDATE copilot_tasks SET status=? WHERE business_id=? AND id=?', (body.status, *params))
            sec.audit(db, owner, task_id, 'COLLECTION_TASK_UPDATED', dict(status=body.status))
        elif row[0] != body.status:
            sec.fail(409, 'TASK_ALREADY_CLOSED')
        return dict(tasks=tasks(db, owner.business_id), simulation_only=True)


class Reminder(Contract):
    receivable_id: RecordId
    language: Literal['bn', 'en'] = 'bn'


@router.post('/message')
def message(body: Reminder, actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        row = db.execute('SELECT open_minor,due_on FROM receivable_balances WHERE business_id=? AND id=?',
                         (owner.business_id, body.receivable_id)).fetchone()
        if not row:
            sec.fail(404, 'RECEIVABLE_NOT_FOUND')
        if row[0] <= 0:
            sec.fail(409, 'RECEIVABLE_PAID')
        currency = sec.original_dataset(db, owner.business_id).currency
        precision = CURRENCIES[currency]['digits']
        amount = f'{Decimal(row[0]) / scale(currency):,.{precision}f} {currency}'
        if body.language == 'bn':
            digits = str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯')
            content = f"নমস্কার। আমাদের হিসাবে আপনার কাছে {amount.translate(digits)} বাকি আছে। পরিশোধের তারিখ {row[1].translate(digits)}। সুবিধামতো কবে পরিশোধ করতে পারবেন জানাবেন। ধন্যবাদ।"
        else:
            content = f"Hello. Our records show an outstanding balance of {amount}, due on {row[1]}. Please let us know when you can pay. Thank you."
        return dict(message=content, source_id=body.receivable_id, open_minor=row[0], due_on=row[1],
                    currency=currency, simulation_only=True)


@router.get('/briefing')
def briefing(actor=Depends(principal), db=Depends(db_connection)):
    db.execute('BEGIN')
    with db:
        current = sec.recheck(db, actor)
        if current.role not in ('owner', 'viewer', 'approver', 'bookkeeper'):
            sec.fail(403, 'MEMBER_REQUIRED')
        sec.verified_audit(db, current.business_id)
        dataset = sec.runtime_dataset(db, current.business_id)
        receipts = open_receipts(db, current.business_id)
        reserve = db.execute('SELECT reserve_minor FROM security_policies WHERE business_id=?', (current.business_id,)).fetchone()[0]
        request = ScenarioRequest(as_of=dataset.as_of, horizon_days=7, reserve_minor=reserve)
        projected = project_cashflow(dataset, request, receipts)
        return dict(as_of=str(dataset.as_of), currency=dataset.currency, balance_minor=snapshot(dataset)['balance_minor'],
                    closing_7_day_minor=projected['closing_balance_minor'], first_shortfall_on=projected['first_shortfall_on'],
                    amount_owed_minor=sum(r.amount_minor for r in receipts), source_ids=sorted(set(projected['source_ids']) | {r.source_id for r in receipts}),
                    simulation_only=True)
