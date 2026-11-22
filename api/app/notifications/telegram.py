"""Owner-confirmed private Telegram linking, reminders and read-only ledger replies."""
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import Field

from api.app import security as sec
from api.app.contracts import Contract
from api.app.currencies import CURRENCIES, scale
from api.app.notifications.service import BD, claim, deliver_after, pref
from api.app.receivables import owner_transaction
from api.app.routes import db_connection, principal
from api.app.services.receivables import customer_key, key_tag, seal, unseal

router=APIRouter(prefix='/api/channels/telegram')
TRANSPORT=None
log=logging.getLogger('uvicorn.error')


def schema(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS telegram_links(business_id TEXT NOT NULL,user_id TEXT NOT NULL,
        code_hash TEXT UNIQUE,expires_at INTEGER,chat_hash TEXT UNIQUE,chat_enc TEXT,key_tag TEXT,
        confirmed_at INTEGER,PRIMARY KEY(business_id,user_id));
      CREATE TABLE IF NOT EXISTS telegram_updates(update_id INTEGER PRIMARY KEY,received_at INTEGER NOT NULL);
    """)
    if 'chat_enabled' not in {row[1] for row in db.execute('PRAGMA table_info(telegram_links)')}:
        db.execute('ALTER TABLE telegram_links ADD COLUMN chat_enabled INTEGER NOT NULL DEFAULT 0 CHECK(chat_enabled IN (0,1))')


def configured():
    return bool(os.getenv('SAFELEDGER_TELEGRAM_ENABLED')=='1'
                and re.fullmatch(r'[0-9]{4,20}:[A-Za-z0-9_-]{20,100}',os.getenv('SAFELEDGER_TELEGRAM_BOT_TOKEN',''))
                and re.fullmatch(r'[A-Za-z0-9_-]{32,256}',os.getenv('SAFELEDGER_TELEGRAM_WEBHOOK_SECRET',''))
                and re.fullmatch(r'[A-Za-z0-9_]{3,32}',os.getenv('SAFELEDGER_TELEGRAM_BOT_USERNAME','')))


def forget(db,business,user):
    db.execute('DELETE FROM telegram_links WHERE business_id=? AND user_id=?',(business,user))
    db.execute("""UPDATE notification_jobs SET status='cancelled',claimed_until=NULL WHERE business_id=? AND
                  recipient_user_id=? AND channel='telegram' AND status IN ('queued','sending')""",(business,user))


@router.get('/link')
def status(actor=Depends(principal),db=Depends(db_connection)):
    with owner_transaction(db,actor) as owner:
        row=db.execute('SELECT confirmed_at,chat_hash,expires_at,chat_enc,key_tag,chat_enabled FROM telegram_links WHERE business_id=? AND user_id=?',
                       (owner.business_id,owner.user_id)).fetchone()
        display=None
        if row and row[3]:
            key=customer_key(db,owner.business_id)
            if key and key_tag(key)==row[4]:
                address=json.loads(unseal(key,row[3],owner.business_id+'/'+owner.user_id+'/telegram'))
                display=address['label']
        return dict(configured=configured(),linked=bool(row and row[0]),chat_enabled=bool(row and row[0] and row[5]),
                    pending=bool(row and row[1] and not row[0] and row[2]>sec.now()),
                    chat_label=display,simulation_only=True)


class Empty(Contract):
    pass


class ChatPreference(Contract):
    enabled: bool = Field(strict=True)


@router.post('/chat')
def set_chat(body:ChatPreference,actor=Depends(principal),db=Depends(db_connection)):
    with owner_transaction(db,actor) as owner:
        if body.enabled and not configured():
            sec.fail(503,'TELEGRAM_NOT_CONFIGURED')
        result=db.execute('''UPDATE telegram_links SET chat_enabled=? WHERE business_id=? AND user_id=?
                             AND confirmed_at IS NOT NULL RETURNING user_id''',
                          (int(body.enabled),owner.business_id,owner.user_id)).fetchone()
        if not result:
            sec.fail(409,'TELEGRAM_LINK_EXPIRED_OR_INCOMPLETE')
        sec.audit(db,owner,uuid.uuid4().hex,'TELEGRAM_CHAT_PREFERENCE_CHANGED',{'enabled':body.enabled})
    return dict(simulation_only=True)


@router.post('/link-code')
def code(body:Empty,actor=Depends(principal),db=Depends(db_connection)):
    if not configured():
        sec.fail(503,'TELEGRAM_NOT_CONFIGURED')
    with owner_transaction(db,actor) as owner:
        sec.budget(db,'telegram-code:'+owner.user_id,4)
        forget(db,owner.business_id,owner.user_id)
        value=secrets.token_urlsafe(24)
        digest=sec.signature('telegram-code',value)
        expires=sec.now()+300
        db.execute('INSERT INTO telegram_links(business_id,user_id,code_hash,expires_at) VALUES (?,?,?,?)',
                   (owner.business_id,owner.user_id,digest,expires))
        return dict(bot=os.environ['SAFELEDGER_TELEGRAM_BOT_USERNAME'],code=value,expires_at=expires,simulation_only=True)


@router.post('/confirm')
def confirm(body:Empty,actor=Depends(principal),db=Depends(db_connection)):
    with owner_transaction(db,actor) as owner:
        row=db.execute('SELECT confirmed_at,expires_at,chat_hash FROM telegram_links WHERE business_id=? AND user_id=?',
                       (owner.business_id,owner.user_id)).fetchone()
        if not configured() or not row or not row[2] or (not row[0] and row[1]<=sec.now()):
            sec.fail(409,'TELEGRAM_LINK_EXPIRED_OR_INCOMPLETE')
        if not row[0]:
            db.execute('UPDATE telegram_links SET confirmed_at=?,code_hash=NULL WHERE business_id=? AND user_id=?',
                       (sec.now(),owner.business_id,owner.user_id))
            sec.audit(db,owner,uuid.uuid4().hex,'TELEGRAM_LINK_CONFIRMED',{'channel':'telegram'})
    return dict(simulation_only=True)


@router.post('/unlink')
def unlink(body:Empty,actor=Depends(principal),db=Depends(db_connection)):
    with owner_transaction(db,actor) as owner:
        forget(db,owner.business_id,owner.user_id)
    return dict(simulation_only=True)


CHAT_COMMANDS={'/balance':'balance','/bills':'supplier bills','/dues':'customer dues','/forecast':'7 day forecast'}
CHAT_LABELS={'balance':'Cash balance','income':'Income','expenses':'Expenses','payables':'Open supplier bills',
             'overdue_bills':'Overdue supplier bills','receivables':'Open customer dues','overdue_receipts':'Overdue customer dues',
             'week':'Projected cash in 7 days','month':'Projected cash in 30 days'}
CHAT_HELP=('Ask about your books with /balance, /bills, /dues or /forecast. '
           'You can also type “cash koto?” or “হাতে কত টাকা আছে?”. Use /stop to disconnect this chat.')


def chat_reply(db,business,enabled,text):
    from api.app.copilot import books

    if not enabled:
        return 'To ask about your books, enable Telegram book replies in Capzoryx Settings.'
    question=CHAT_COMMANDS.get(text,text)
    normalized,_=books.query_parts(question)
    if normalized not in books.MAPPING:
        return CHAT_HELP
    sec.verified_audit(db,business)
    result=books.answer(db,business,'owner',question)
    if not result['answered']:
        return CHAT_HELP
    code=result['currency']
    amount=Decimal(result['amount_minor'])/scale(code)
    digits=CURRENCIES[code]['digits']
    window={'today':' today','this_month':' this month','last_month':' last month'}.get(result['window'],'')
    return f"{CHAT_LABELS[result['kind']]}{window}: {code} {amount:,.{digits}f}\nWorkspace snapshot: {result['as_of']}"


@router.post('')
def webhook(payload:dict,request:Request,db=Depends(db_connection)):
    expected=os.getenv('SAFELEDGER_TELEGRAM_WEBHOOK_SECRET','')
    got=request.headers.get('x-telegram-bot-api-secret-token','')
    if not configured() or not got.isascii() or not hmac.compare_digest(expected,got):
        sec.fail(403,'TELEGRAM_SIGNATURE_INVALID')
    update=payload.get('update_id')
    if type(update)!=int or not 0<=update<=2**63-1:
        sec.fail(422,'INVALID_TELEGRAM_UPDATE')
    message=payload.get('message')
    if not isinstance(message,dict):
        return {'ok':True}
    chat=message.get('chat')
    sender=message.get('from')
    if not isinstance(chat,dict) or not isinstance(sender,dict) or chat.get('type')!='private':
        return {'ok':True}
    chat_id=chat.get('id')
    text=message.get('text')
    if type(chat_id)!=int or chat_id<=0 or sender.get('id')!=chat_id or sender.get('is_bot') or not isinstance(text,str) or not 1<=len(text)<=240:
        return {'ok':True}
    text=text.strip()
    if not text:
        return {'ok':True}
    match=re.fullmatch(r'/start ([A-Za-z0-9_-]{32})',text)
    sent=message.get('date')
    now=sec.now()
    if type(sent)!=int or abs(now-sent)>300:
        return {'ok':True}
    chat_hash=sec.signature('telegram-chat',str(chat_id))
    try:
        sec.budgets(db,[('telegram-webhook:'+chat_hash,12),('telegram-webhook-all',120)])
    except sec.PolicyError as error:
        if error.status!=429:
            raise
        return {'ok':True}
    reply=None
    with sec.transaction(db):
        db.execute('DELETE FROM telegram_updates WHERE received_at<?',(now-86400,))
        if not db.execute('INSERT OR IGNORE INTO telegram_updates VALUES (?,?) RETURNING update_id',(update,now)).fetchone():
            return {'ok':True}
        previous=db.execute('SELECT business_id,user_id FROM telegram_links WHERE chat_hash=?',(chat_hash,)).fetchone()
        if text=='/stop':
            if previous:
                forget(db,*previous)
        elif match and not previous:
            digest=sec.signature('telegram-code',match[1])
            row=db.execute("""SELECT business_id,user_id FROM telegram_links WHERE code_hash=? AND expires_at>?
                              AND confirmed_at IS NULL AND chat_hash IS NULL""",(digest,now)).fetchone()
            if row:
                business,user=row
                key=customer_key(db,business,create=True)
                username=sender.get('username')
                label='@'+username if isinstance(username,str) and re.fullmatch(r'[A-Za-z0-9_]{3,32}',username) else '…'+str(chat_id)[-4:]
                cipher=seal(key,sec.canonical({'id':str(chat_id),'label':label}).encode(),business+'/'+user+'/telegram')
                db.execute('UPDATE telegram_links SET chat_hash=?,chat_enc=?,key_tag=?,code_hash=NULL WHERE business_id=? AND user_id=?',
                           (chat_hash,cipher,key_tag(key),business,user))
                reply='Return to Capzoryx Settings and confirm this Telegram account to finish connecting.'
        elif not match and previous:
            business,user=previous
            row=db.execute('''SELECT t.chat_enabled,t.key_tag FROM telegram_links t
                  JOIN effective_security_users u ON u.user_id=t.user_id AND u.business_id=t.business_id
                  JOIN workspace_meta w ON w.business_id=t.business_id WHERE t.chat_hash=? AND t.confirmed_at IS NOT NULL
                  AND u.active=1 AND u.role='owner' AND w.kind='personal' AND w.archived_at IS NULL''',(chat_hash,)).fetchone()
            key=customer_key(db,business) if row else None
            if key and key_tag(key)==row[1]:
                reply=chat_reply(db,business,bool(row[0]),text)
    if reply:
        with (TRANSPORT or httpx.HTTPTransport(trust_env=False)) as transport:
            send_message(transport,str(chat_id),reply)
    return {'ok':True}


def queue(db,business,at,*,has_due_bills=False):
    if not configured():
        return
    local=datetime.fromtimestamp(at,BD)
    if local.hour<8:
        return
    kinds=['morning_briefing']
    if has_due_bills:
        kinds.append('bill_due')
    if local.weekday()==6 and local.hour>=9:
        kinds.append('weekly_summary')
    rows=db.execute('SELECT user_id FROM telegram_links WHERE business_id=? AND confirmed_at IS NOT NULL',(business,)).fetchall()
    for (user,) in rows:
        _,start,end=pref(db,business,user)
        for kind in kinds:
            key=sec.signature('notification-key',[business,kind,user,'telegram',str(local.date())])
            db.execute("""INSERT INTO notification_jobs(id,business_id,dedupe_key,recipient_user_id,channel,payload_json,run_after)
                          VALUES (?,?,?,?,'telegram',?,?) ON CONFLICT(dedupe_key) DO NOTHING""",
                       (uuid.uuid4().hex,business,key,user,sec.canonical({'kind':kind,'page':'Audit','day':str(local.date())}),
                        deliver_after(at,start,end)))


def next_delivery(db,business,at):
    with sec.transaction(db):
        row=db.execute("""SELECT id,recipient_user_id,attempts,payload_json FROM notification_jobs WHERE business_id=? AND channel='telegram'
                          AND ((status='queued' AND run_after<=?) OR (status='sending' AND claimed_until<=?))
                          ORDER BY run_after,id LIMIT 1""",(business,at,at)).fetchone()
        if not row or not claim(db,row[0],at):
            return None
        identity,user,prior_attempts,payload=row
        linked=db.execute("""SELECT t.chat_enc,t.key_tag FROM telegram_links t JOIN security_users u ON u.user_id=t.user_id
                             AND u.business_id=t.business_id JOIN workspace_meta w ON w.business_id=t.business_id
                             WHERE t.business_id=? AND t.user_id=? AND t.confirmed_at IS NOT NULL AND u.active=1
                             AND u.role='owner' AND w.archived_at IS NULL AND w.kind='personal'""",(business,user)).fetchone()
        key=customer_key(db,business)
        if not linked or not key or key_tag(key)!=linked[1] or prior_attempts>=3:
            db.execute("UPDATE notification_jobs SET status='cancelled',claimed_until=NULL WHERE id=?",(identity,))
            return None
        _,start,end=pref(db,business,user)
        later=deliver_after(at,start,end)
        if later>at:
            db.execute("UPDATE notification_jobs SET status='queued',claimed_until=NULL,run_after=?,attempts=attempts-1 WHERE id=?",
                       (later,identity))
            return None
        notice=json.loads(payload)
        if notice['kind']=='bill_due':
            from api.app.notifications.email_alerts import due_count
            day=datetime.fromtimestamp(at,BD).date()
            if notice.get('day')!=str(day) or not due_count(sec.runtime_dataset(db,business),day):
                db.execute("UPDATE notification_jobs SET status='cancelled',claimed_until=NULL WHERE id=?",(identity,))
                return None
        address=json.loads(unseal(key,linked[0],business+'/'+user+'/telegram'))['id']
        return identity,address,prior_attempts+1,notice['kind']


def bot_request(transport,method,payload):
    # Keep the Bot API token out of httpx.Client URL logs.
    try:
        request=httpx.Request('POST','https://api.telegram.org/bot'+os.environ['SAFELEDGER_TELEGRAM_BOT_TOKEN']+'/'+method,
            json=payload,
            extensions={'timeout':dict.fromkeys(('connect','read','write','pool'),8)})
        response=transport.handle_request(request)
        try:
            response.read()
            return response.status_code==200 and response.json().get('ok') is True
        finally:
            response.close()
    except (httpx.HTTPError,ValueError,AttributeError):
        return False


def send_message(transport,chat,text):
    return bot_request(transport,'sendMessage',
                       {'chat_id':chat,'text':text,'link_preview_options':{'is_disabled':True}})


def register_webhook():
    url=os.getenv('SAFELEDGER_TELEGRAM_WEBHOOK_URL','')
    if not url or not configured():
        return
    try:
        target=urlsplit(url)
        valid=(target.scheme=='https' and target.hostname and not (target.username or target.password or
               target.query or target.fragment) and target.path=='/api/channels/telegram')
    except ValueError:
        valid=False
    if not valid:
        log.warning('Telegram webhook registration URL is invalid.')
        return
    with (TRANSPORT or httpx.HTTPTransport(trust_env=False)) as transport:
        ok=bot_request(transport,'setWebhook',{'url':url,'secret_token':os.environ['SAFELEDGER_TELEGRAM_WEBHOOK_SECRET'],
                                               'allowed_updates':['message']})
    if ok:
        log.info('Telegram webhook registered.')
    else:
        log.warning('Telegram webhook registration did not succeed.')


def deliver(db,business,at):
    if not configured():
        return
    target=urlsplit(os.getenv('SAFELEDGER_PUBLIC_URL',''))
    if target.scheme!='https' or not target.hostname or target.username or target.password or target.query or target.fragment:
        return
    home='https://'+target.netloc+'/'
    with (TRANSPORT or httpx.HTTPTransport(trust_env=False)) as transport:
        for _ in range(4):
            job=next_delivery(db,business,at)
            if not job:
                break
            identity,chat,attempts,kind=job
            summary='A Capzoryx bill needs your review.' if kind=='bill_due' else 'Capzoryx has a workspace update.'
            success=send_message(transport,chat,summary+' Open your notification inbox: '+home+'?view=activity')
            with sec.transaction(db):
                status='sent' if success else ('failed' if attempts>=3 else 'queued')
                db.execute("""UPDATE notification_jobs SET status=?,run_after=?,claimed_until=NULL,sent_at=?,last_error=?
                              WHERE id=? AND status='sending' AND attempts=?""",(status,at+60*2**attempts,
                           at if success else None,None if success else 'TELEGRAM_DELIVERY_FAILED',identity,attempts))
