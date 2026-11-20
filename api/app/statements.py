"""Review a statement locally on the API, then book selected cash rows one at a time."""
import base64
from collections import Counter
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field

from api.app import security as sec
from api.app.accounts import today_bd
from api.app.contracts import Contract, Currency, ISODate
from api.app.currencies import CURRENCIES
from api.app.inputs import InputRecord, append_record
from api.app.receivables import owner_transaction
from api.app.routes import db_connection, principal
from api.app.services.finance import fingerprint

router=APIRouter(prefix='/api/statements')
SLOT=threading.BoundedSemaphore(1)
NAMESPACE=uuid.UUID('609f2073-0189-47d8-b217-47ed0a41f714')
HASH=r'^[a-f0-9]{64}$'


def schema(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS statement_imports(id TEXT PRIMARY KEY,business_id TEXT NOT NULL,file_hash TEXT NOT NULL,
        layout TEXT NOT NULL,rows_total INTEGER NOT NULL,rows_new INTEGER NOT NULL,rows_duplicate INTEGER NOT NULL,
        rows_review INTEGER NOT NULL,created_at INTEGER NOT NULL,UNIQUE(business_id,file_hash));
      CREATE TABLE IF NOT EXISTS statement_rows(business_id TEXT NOT NULL,row_hash TEXT NOT NULL,economics_hash TEXT NOT NULL,
        import_id TEXT NOT NULL REFERENCES statement_imports(id),cash_record_id TEXT NOT NULL,PRIMARY KEY(business_id,row_hash),
        UNIQUE(business_id,cash_record_id));
    """)


class Upload(Contract):
    data: str = Field(min_length=1,max_length=4194000)
    layout: Literal['csv','xlsx','pdf']
    currency: Currency
    date_order: Literal['DMY','MDY']='DMY'
    account_label: str = Field(min_length=1,max_length=64)


class ReviewFile(Contract):
    file_hash: str = Field(pattern=HASH)
    layout: Literal['csv','xlsx','pdf']
    currency: Currency
    account_hash: str = Field(pattern=HASH)
    rows_total: int = Field(strict=True,gt=0,le=20000)
    rows_duplicate: int = Field(strict=True,ge=0,le=20000)
    rows_review: int = Field(strict=True,ge=0,le=20000)


class ReviewRow(Contract):
    line: int=Field(strict=True,gt=0,le=20030)
    row_hash: str=Field(pattern=HASH)
    day: ISODate
    signed: int=Field(strict=True,ge=-(10**12),le=10**12)
    needs_review: bool = Field(strict=True)


class Confirm(Contract):
    file: ReviewFile
    row: ReviewRow
    signature: str = Field(pattern=HASH)
    verified_distinct: bool = Field(default=False,strict=True)


def decode(upload):
    try:
        raw=base64.b64decode(upload.data,validate=True)
    except (ValueError,TypeError):
        sec.fail(422,'STATEMENT_INVALID_BASE64')
    if not SLOT.acquire(timeout=0.2):
        sec.fail(503,'STATEMENT_READER_BUSY')
    try:
        # Parsing runs without application credentials, with separate CPU/memory limits.
        worker=os.path.join(os.path.dirname(__file__),'services','statements.py')
        result=subprocess.run([sys.executable,'-I',worker,upload.layout,upload.currency,
                               str(CURRENCIES[upload.currency]['digits']),upload.date_order],
                              input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'LANG':'C.UTF-8'},
                              timeout=18)
        if result.returncode or len(result.stdout)>12*1024*1024:
            sec.fail(422,'STATEMENT_READER_LIMIT')
        data=json.loads(result.stdout)
        if 'error' in data:sec.fail(422,data['error'])
        return hashlib.sha256(raw).hexdigest(),data['rows']
    except (subprocess.TimeoutExpired,ValueError):
        sec.fail(422,'STATEMENT_READER_LIMIT')
    finally:
        SLOT.release()


def economics(row):
    return hashlib.sha256(sec.canonical([str(row['day']),row['signed']]).encode()).hexdigest()


def token(actor,manifest,row):
    return sec.signature('statement-review-v1',[actor.business_id,actor.user_id,manifest,row])


def cash_keys(ds):
    return {(str(event.effective_on),event.amount_minor*(1 if event.direction=='inflow' else -1))
            for event in ds.events if event.status=='cleared'}


@router.post('/preview')
def preview(body: Upload,actor=Depends(principal),db=Depends(db_connection)):
    if actor.role!='owner':sec.fail(403,'OWNER_REQUIRED')
    sec.budget(db,'statement-reader:'+actor.user_id,12)
    file_hash,decoded=decode(body)
    with owner_transaction(db,actor) as current:
        business=current.business_id
        ds=sec.runtime_dataset(db,business)
        if ds.currency!=body.currency:sec.fail(422,'IMPORT_CURRENCY_MISMATCH')
        existing=cash_keys(ds)
        account_hash=sec.signature('statement-account',[business,' '.join(body.account_label.casefold().split())])
        linked=dict(db.execute('SELECT row_hash,economics_hash FROM statement_rows WHERE business_id=?',(business,)).fetchall())
        prior_file=db.execute('SELECT id,rows_new FROM statement_imports WHERE business_id=? AND file_hash=?',(business,file_hash)).fetchone()
        # Reusing a file with a different mapping can hide duplicates across manual imports.
        manifest_id='statement-'+str(uuid.uuid5(NAMESPACE,sec.canonical([business,file_hash,body.layout,account_hash,body.date_order,body.currency])))
        if prior_file and prior_file[0]!=manifest_id:sec.fail(409,'STATEMENT_MAPPING_CHANGED')
        ids=[];signatures=[]
        for row in decoded:
            if 'signed' not in row:
                ids.append(None);signatures.append(None);continue
            # For rows without an issuer reference include the running balance when available.
            key=['ref',row['ref']] if row['ref'] else ['cash',row['day'],row['signed'],row['balance']]
            ids.append(sec.signature('statement-row',[business,account_hash,key]))
            signatures.append((row['day'],row['signed']))
        counts=Counter(ids);shapes=Counter(signatures)
        file_rows=[];held=0;duplicates=0
        for row,identity,shape in zip(decoded,ids,signatures):
            status='new';reason=row.get('reason');review=None
            if reason:status='blocked'
            elif row['day']<str(ds.opening_on) or row['day']>str(today_bd()):status,reason='blocked','DATE_OUTSIDE_WORKSPACE'
            elif identity in linked:
                if economics(row)==linked[identity]:status,reason='duplicate','ALREADY_IMPORTED'
                else:status,reason='blocked','REFERENCE_CONFLICT'
            elif counts[identity]>1:
                status,reason='blocked','REPEATED_IDENTITY_IN_FILE'
            elif shape in existing or shapes[shape]>1:
                status,reason='review','SIMILAR_CASH_ENTRY'
            if status in {'new','review'}:
                review=dict(line=row['line'],row_hash=identity,day=row['day'],signed=row['signed'],needs_review=status=='review')
            held+=status in {'review','blocked'};duplicates+=status=='duplicate'
            file_rows.append(dict(line=row['line'],day=row.get('day'),signed=row.get('signed'),status=status,reason=reason,review=review))
        manifest=dict(file_hash=file_hash,layout=body.layout,currency=body.currency,account_hash=account_hash,
                      rows_total=len(file_rows),rows_duplicate=duplicates,rows_review=held)
        # Include the date-order mapping in the signed manifest via the per-import identifier.
        for row in file_rows:
            if row['review']:
                row['signature']=token(current,[manifest,manifest_id],row['review'])
        return dict(file=manifest,import_id=manifest_id,rows=file_rows,imported_count=prior_file[1] if prior_file else 0,simulation_only=True)


class ConfirmRow(Confirm):
    import_id: str = Field(pattern=r'^statement-[0-9a-f-]{36}$')


@router.post('/confirm')
def confirm(body: ConfirmRow,actor=Depends(principal),db=Depends(db_connection)):
    with owner_transaction(db,actor) as current:
        manifest=body.file.model_dump(mode='json');row=body.row.model_dump(mode='json')
        if not hmac.compare_digest(token(current,[manifest,body.import_id],row),body.signature):
            sec.fail(409,'STATEMENT_REVIEW_EXPIRED')
        business=current.business_id
        previous=db.execute('SELECT economics_hash,cash_record_id FROM statement_rows WHERE business_id=? AND row_hash=?',
                            (business,body.row.row_hash)).fetchone()
        if previous:
            if previous[0]!=economics(row):sec.fail(409,'STATEMENT_REFERENCE_CONFLICT')
            return dict(cash_record_id=previous[1],replayed=True,simulation_only=True)
        ds=sec.original_dataset(db,business)
        if ds.currency!=body.file.currency:sec.fail(409,'IMPORT_CURRENCY_MISMATCH')
        if (body.row.needs_review or (str(body.row.day),body.row.signed) in cash_keys(sec.runtime_dataset(db,business))) and not body.verified_distinct:
            sec.fail(409,'STATEMENT_VERIFY_DISTINCT')
        prior=db.execute('SELECT id FROM statement_imports WHERE business_id=? AND file_hash=?',(business,body.file.file_hash)).fetchone()
        if prior and prior[0]!=body.import_id:sec.fail(409,'STATEMENT_MAPPING_CHANGED')
        if not prior:
            db.execute('INSERT INTO statement_imports VALUES(?,?,?,?,?,?,?,?,?)',
                       (body.import_id,business,body.file.file_hash,body.file.layout,body.file.rows_total,0,body.file.rows_duplicate,
                        body.file.rows_review,sec.now()))
        request_id=str(uuid.uuid5(NAMESPACE,business+':'+body.row.row_hash))
        saved=append_record(db,current,InputRecord(request_id=request_id,expected_revision=fingerprint(ds),
                            kind='cash',direction='inflow' if body.row.signed>0 else 'outflow',
                            amount_minor=abs(body.row.signed),effective_on=body.row.day))
        if saved['replayed']:sec.fail(409,'CASH_REQUEST_ALREADY_USED')
        cash=saved['source_id']
        db.execute('INSERT INTO statement_rows VALUES(?,?,?,?,?)',(business,body.row.row_hash,economics(row),body.import_id,cash))
        db.execute('UPDATE statement_imports SET rows_new=rows_new+1 WHERE business_id=? AND id=?',(business,body.import_id))
        sec.audit(db,current,body.import_id,'STATEMENT_ROW_IMPORTED',dict(line=body.row.line,cash_record_id=cash))
        return dict(cash_record_id=cash,replayed=False,simulation_only=True)
