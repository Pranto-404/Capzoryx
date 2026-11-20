"""In-app reminders computed in Bangladesh local time from existing records."""
from datetime import date, datetime, timedelta
import json

from api.app import security as sec
from api.app.contracts import ScenarioRequest
from api.app.notifications.service import BD, dispatch, enqueue
from api.app.services.finance import project_cashflow
from api.app.services.receivables import open_receipts


def run_workspace(db, business, at):
    if not db.execute("SELECT 1 FROM workspace_meta WHERE business_id=? AND kind='personal' AND archived_at IS NULL",
                      (business,)).fetchone():
        return
    now = datetime.fromtimestamp(at, BD)
    today = now.date()
    ds = sec.runtime_dataset(db, business)
    for bill in ds.invoices:
        if bill.status == 'open' and (bill.due_on-today).days in (0, 1, 3, 7):
            enqueue(db, business, 'bill_due', bill.invoice_id, at=at, period=str(today))
    rows = db.execute("""SELECT customer_id,due_on FROM receivable_balances
                         WHERE business_id=? AND open_minor>0 AND due_on<?""", (business, str(today)))
    due = {customer for customer, day in rows if (today-date.fromisoformat(day)).days % 3 == 1}
    for customer in sorted(due):
        enqueue(db, business, 'customer_overdue', customer, at=at, period=str(today))
    receipts = open_receipts(db, business)
    if ds.events or ds.invoices or receipts or ds.opening_balance_minor:
        if now.hour >= 8:
            enqueue(db, business, 'morning_briefing', str(today), at=at)
        reserve = db.execute('SELECT reserve_minor FROM security_policies WHERE business_id=?', (business,)).fetchone()
        if reserve:
            forecast = project_cashflow(ds, ScenarioRequest(as_of=ds.as_of,horizon_days=30,reserve_minor=reserve[0]), receipts)
            breach = next((d['date'] for d in forecast['days'] if d['shortfall_minor'] and
                           str(today) <= d['date'] <= str(today+timedelta(days=14))), None)
            if breach:
                enqueue(db, business, 'cash_breach', breach, at=at)
    from api.app.notifications import telegram
    telegram.queue(db,business,at)
    # Dispatch once a deferred reminder can be shown. The transaction rechecks open balances and membership.
    pending = db.execute("""SELECT id FROM notification_jobs WHERE business_id=? AND channel='inapp' AND
                            ((status='queued' AND run_after<=?) OR (status='sending' AND claimed_until<=?))
                            ORDER BY run_after,id LIMIT 100""", (business,at,at)).fetchall()
    for (identity,) in pending:
        dispatch(db, identity, at)


def tick_business(db, business, at):
    with sec.transaction(db):
        # Claim each half-hour only once, including when both schedulers run.
        claimed = db.execute("""INSERT INTO notification_rules_state(business_id,last_slot) VALUES (?,?)
                                ON CONFLICT(business_id) DO UPDATE SET last_slot=excluded.last_slot
                                WHERE last_slot<excluded.last_slot RETURNING business_id""", (business, at//1800)).fetchone()
        if claimed:
            run_workspace(db, business, at)
    from api.app.notifications import telegram
    telegram.deliver(db,business,at)
    return bool(claimed)


def tick(db, at):
    batch = db.execute("""SELECT w.business_id FROM workspace_meta w LEFT JOIN notification_rules_state s
                          ON s.business_id=w.business_id WHERE w.kind='personal' AND w.archived_at IS NULL
                          AND COALESCE(s.last_slot,-1)<? ORDER BY COALESCE(s.last_slot,-1),w.business_id LIMIT 6""",
                       (at//1800,)).fetchall()
    count = sum(tick_business(db, row[0], at) for row in batch[:5])
    return dict(processed=count, more=len(batch)>5, simulation_only=True)
