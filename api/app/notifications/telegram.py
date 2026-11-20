"""Owner-confirmed private Telegram linking and optional count-only summary delivery."""
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import Field

from api.app import security as sec
from api.app.contracts import Contract
from api.app.notifications.service import BD, claim, deliver_after, pref
from api.app.receivables import owner_transaction
from api.app.routes import db_connection, principal
from api.app.services.receivables import customer_key, key_tag, seal, unseal

router=APIRouter(prefix='/api/channels/telegram')
TRANSPORT=None


def schema(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS telegram_links(business_id TEXT NOT NULL,user_id TEXT NOT NULL,
        code_hash TEXT UNIQUE,expires_at INTEGER,chat_hash TEXT UNIQUE,chat_enc TEXT,key_tag TEXT,
        confirmed_at INTEGER,PRIMARY KEY(business_id,user_id));
      CREATE TABLE IF NOT EXISTS telegram_updates(update_id INTEGER PRIMARY KEY,received_at INTEGER NOT NULL);
    """)


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
        row=db.execute('SELECT confirmed_at,chat_hash,expires_at,chat_enc,key_tag FROM telegram_links WHERE business_id=? AND user_id=?',
                       (owner.business_id,owner.user_id)).fetchone()
        display=None
        if row and row[3]:
            key=customer_key(db,owner.business_id)
            if key and key_tag(key)==row[4]:
                address=json.loads(unseal(key,row[3],owner.business_id+'/'+owner.user_id+'/telegram'))
                display=address['label']
        return dict(configured=configured(),linked=bool(row and row[0]),pending=bool(row and row[1] and not row[0] and row[2]>sec.now()),
                    chat_label=display,simulation_only=True)


class Empty(Contract):
    pass


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
    if type(chat_id)!=int or chat_id<=0 or sender.get('id')!=chat_id or sender.get('is_bot') or not isinstance(text,str):
        return {'ok':True}
    match=re.fullmatch(r'/start ([A-Za-z0-9_-]{32})',text)
    if not match and text!='/stop':
        return {'ok':True}
    sent=message.get('date')
    now=sec.now()
    if type(sent)!=int or abs(now-sent)>300:
        return {'ok':True}
    with sec.transaction(db):
        db.execute('DELETE FROM telegram_updates WHERE received_at<?',(now-86400,))
        if not db.execute('INSERT OR IGNORE INTO telegram_updates VALUES (?,?) RETURNING update_id',(update,now)).fetchone():
            return {'ok':True}
        chat_hash=sec.signature('telegram-chat',str(chat_id))
        previous=db.execute('SELECT business_id,user_id FROM telegram_links WHERE chat_hash=?',(chat_hash,)).fetchone()
        if text=='/stop':
            if previous:
                forget(db,*previous)
        elif not previous:
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
    return {'ok':True}


def queue(db,business,at):
    if not configured():
        return
    local=datetime.fromtimestamp(at,BD)
    if local.hour<8:
        return
    kinds=['morning_briefing']
    if local.weekday()==6 and local.hour>=9:
        kinds.append('weekly_summary')
    rows=db.execute('SELECT user_id FROM telegram_links WHERE business_id=? AND confirmed_at IS NOT NULL',(business,)).fetchall()
    for (user,) in rows:
        _,start,end=pref(db,business,user)
        for kind in kinds:
            key=sec.signature('notification-key',[business,kind,user,'telegram',str(local.date())])
            db.execute("""INSERT INTO notification_jobs(id,business_id,dedupe_key,recipient_user_id,channel,payload_json,run_after)
                          VALUES (?,?,?,?,'telegram',?,?) ON CONFLICT(dedupe_key) DO NOTHING""",
                       (uuid.uuid4().hex,business,key,user,sec.canonical({'kind':kind,'page':'Audit'}),deliver_after(at,start,end)))


def next_delivery(db,business,at):
    with sec.transaction(db):
        row=db.execute("""SELECT id,recipient_user_id,attempts FROM notification_jobs WHERE business_id=? AND channel='telegram'
                          AND ((status='queued' AND run_after<=?) OR (status='sending' AND claimed_until<=?))
                          ORDER BY run_after,id LIMIT 1""",(business,at,at)).fetchone()
        if not row or not claim(db,row[0],at):
            return None
        identity,user,prior_attempts=row
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
        address=json.loads(unseal(key,linked[0],business+'/'+user+'/telegram'))['id']
        return identity,address,prior_attempts+1


def deliver(db,business,at):
    if not configured():
        return
    target=urlsplit(os.getenv('SAFELEDGER_PUBLIC_URL',''))
    if target.scheme!='https' or not target.hostname or target.username or target.password or target.query or target.fragment:
        return
    home='https://'+target.netloc+'/'
    # The Bot API requires a secret in the path. Use the transport directly to
    # avoid URL-bearing httpx.Client request logs. No redirects are followed.
    with (TRANSPORT or httpx.HTTPTransport(trust_env=False)) as transport:
        for _ in range(4):
            job=next_delivery(db,business,at)
            if not job:
                break
            identity,chat,attempts=job
            try:
                request=httpx.Request('POST','https://api.telegram.org/bot'+os.environ['SAFELEDGER_TELEGRAM_BOT_TOKEN']+'/sendMessage',
                    json={'chat_id':chat,'text':'Capzoryx has a workspace update. Open your notification inbox: '+home,
                          'link_preview_options':{'is_disabled':True}},extensions={'timeout':dict.fromkeys(('connect','read','write','pool'),8)})
                response=transport.handle_request(request)
                try:
                    response.read()
                    success=response.status_code==200 and response.json().get('ok') is True
                finally:
                    response.close()
            except (httpx.HTTPError,ValueError,AttributeError):
                success=False
            with sec.transaction(db):
                status='sent' if success else ('failed' if attempts>=3 else 'queued')
                db.execute("""UPDATE notification_jobs SET status=?,run_after=?,claimed_until=NULL,sent_at=?,last_error=?
                              WHERE id=? AND status='sending' AND attempts=?""",(status,at+60*2**attempts,
                           at if success else None,None if success else 'TELEGRAM_DELIVERY_FAILED',identity,attempts))
