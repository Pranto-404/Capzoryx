"""Private WhatsApp chat with the Capzoryx brain over the Meta WhatsApp Cloud API.

Linking mirrors Telegram: the owner gets a short code in Settings, sends it to the business number from their own
WhatsApp, then confirms that number on the website. Replies go out inside WhatsApp's free 24-hour service window,
so no paid template messages are used.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from api.app import security as sec
from api.app.notifications.telegram import ChatPreference, Empty
from api.app.receivables import owner_transaction
from api.app.routes import db_connection, principal
from api.app.services.receivables import customer_key, key_tag, seal, unseal

router = APIRouter(prefix='/api/channels/whatsapp')
TRANSPORT = None
GRAPH = 'https://graph.facebook.com/v21.0/'
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
BUTTON_PAYLOADS = ('__save__', '__cancel__', '__summary__', '__list_receivables__', '__list_payables__')
log = logging.getLogger('uvicorn.error')
UNLINKED = ("Hi! I'm Capzoryx, your money assistant. 👋\nTo connect me to your books, sign in to Capzoryx, open "
            "Settings → WhatsApp and tap “Connect WhatsApp”. Then just chat — “cash koto?”, “who owes me?”, "
            "“Rahim theke 500 taka pelam”.")


def schema(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS whatsapp_links(business_id TEXT NOT NULL,user_id TEXT NOT NULL,
        code_hash TEXT UNIQUE,expires_at INTEGER,chat_hash TEXT UNIQUE,chat_enc TEXT,key_tag TEXT,confirmed_at INTEGER,
        chat_enabled INTEGER NOT NULL DEFAULT 0 CHECK(chat_enabled IN (0,1)),
        records_enabled INTEGER NOT NULL DEFAULT 0 CHECK(records_enabled IN (0,1)),PRIMARY KEY(business_id,user_id));
      CREATE TABLE IF NOT EXISTS whatsapp_updates(message_hash TEXT PRIMARY KEY,received_at INTEGER NOT NULL);
    """)
    from api.app.chat import brain
    brain.schema(db)


def configured():
    return bool(os.getenv('SAFELEDGER_WHATSAPP_ENABLED') == '1'
                and re.fullmatch(r'[A-Za-z0-9_-]{40,600}', os.getenv('SAFELEDGER_WHATSAPP_TOKEN', ''))
                and re.fullmatch(r'[0-9]{6,20}', os.getenv('SAFELEDGER_WHATSAPP_PHONE_ID', ''))
                and re.fullmatch(r'[A-Za-z0-9]{16,128}', os.getenv('SAFELEDGER_WHATSAPP_APP_SECRET', ''))
                and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', os.getenv('SAFELEDGER_WHATSAPP_VERIFY_TOKEN', ''))
                and re.fullmatch(r'[0-9]{8,15}', os.getenv('SAFELEDGER_WHATSAPP_NUMBER', '')))


def forget(db, business, user):
    from api.app.chat import brain
    for (chat,) in db.execute('SELECT chat_hash FROM whatsapp_links WHERE business_id=? AND user_id=? AND chat_hash IS NOT NULL',
                              (business, user)).fetchall():
        brain.forget_chat(db, chat)
    db.execute('DELETE FROM whatsapp_links WHERE business_id=? AND user_id=?', (business, user))


@router.get('/link')
def status(actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        row = db.execute('SELECT confirmed_at,chat_hash,expires_at,chat_enc,key_tag,chat_enabled,records_enabled '
                         'FROM whatsapp_links WHERE business_id=? AND user_id=?', (owner.business_id, owner.user_id)).fetchone()
        label = None
        if row and row[3]:
            key = customer_key(db, owner.business_id)
            if key and key_tag(key) == row[4]:
                label = json.loads(unseal(key, row[3], owner.business_id + '/' + owner.user_id + '/whatsapp'))['label']
        linked = bool(row and row[0])
        return dict(configured=configured(), linked=linked, chat_enabled=bool(linked and row[5]),
                    records_enabled=bool(linked and row[5] and row[6]),
                    pending=bool(row and row[1] and not row[0]),
                    awaiting_message=bool(row and not row[1] and row[2] and row[2] > sec.now()),
                    chat_label=label, simulation_only=True)


@router.post('/link-code')
def code(body: Empty, actor=Depends(principal), db=Depends(db_connection)):
    if not configured():
        sec.fail(503, 'WHATSAPP_NOT_CONFIGURED')
    with owner_transaction(db, actor) as owner:
        sec.budget(db, 'whatsapp-code:' + owner.user_id, 4)
        forget(db, owner.business_id, owner.user_id)
        value = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        expires = sec.now() + 600
        db.execute('INSERT INTO whatsapp_links(business_id,user_id,code_hash,expires_at) VALUES (?,?,?,?)',
                   (owner.business_id, owner.user_id, sec.signature('whatsapp-code', value), expires))
        return dict(number=os.environ['SAFELEDGER_WHATSAPP_NUMBER'], code=value, expires_at=expires, simulation_only=True)


@router.post('/confirm')
def confirm(body: Empty, actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        row = db.execute('SELECT confirmed_at,chat_hash FROM whatsapp_links WHERE business_id=? AND user_id=?',
                         (owner.business_id, owner.user_id)).fetchone()
        if not configured() or not row or not row[1]:
            sec.fail(409, 'WHATSAPP_LINK_EXPIRED_OR_INCOMPLETE')
        if not row[0]:
            db.execute('UPDATE whatsapp_links SET confirmed_at=?,code_hash=NULL,expires_at=NULL WHERE business_id=? AND user_id=?',
                       (sec.now(), owner.business_id, owner.user_id))
            sec.audit(db, owner, uuid.uuid4().hex, 'WHATSAPP_LINK_CONFIRMED', {'channel': 'whatsapp'})
    return dict(simulation_only=True)


@router.post('/unlink')
def unlink(body: Empty, actor=Depends(principal), db=Depends(db_connection)):
    with owner_transaction(db, actor) as owner:
        forget(db, owner.business_id, owner.user_id)
    return dict(simulation_only=True)


def preference(db, actor, column, enabled, event):
    with owner_transaction(db, actor) as owner:
        if enabled and not configured():
            sec.fail(503, 'WHATSAPP_NOT_CONFIGURED')
        sql = f'UPDATE whatsapp_links SET {column}=? WHERE business_id=? AND user_id=? AND confirmed_at IS NOT NULL'
        params = [int(enabled), owner.business_id, owner.user_id]
        if column == 'records_enabled':
            sql += ' AND (chat_enabled=1 OR ?=0)'
            params.append(int(enabled))
        result = db.execute(sql + ' RETURNING user_id', params).fetchone()
        if not result:
            sec.fail(409, 'WHATSAPP_LINK_EXPIRED_OR_INCOMPLETE')
        if column == 'chat_enabled' and not enabled:
            db.execute('UPDATE whatsapp_links SET records_enabled=0 WHERE business_id=? AND user_id=?',
                       (owner.business_id, owner.user_id))
        sec.audit(db, owner, uuid.uuid4().hex, event, {'enabled': enabled})
    return dict(simulation_only=True)


@router.post('/chat')
def set_chat(body: ChatPreference, actor=Depends(principal), db=Depends(db_connection)):
    return preference(db, actor, 'chat_enabled', body.enabled, 'WHATSAPP_CHAT_PREFERENCE_CHANGED')


@router.post('/records')
def set_records(body: ChatPreference, actor=Depends(principal), db=Depends(db_connection)):
    return preference(db, actor, 'records_enabled', body.enabled, 'WHATSAPP_RECORDS_PREFERENCE_CHANGED')


@router.get('')
def verify(request: Request):
    """Meta's one-time webhook handshake."""
    query = request.query_params
    expected = os.getenv('SAFELEDGER_WHATSAPP_VERIFY_TOKEN', '')
    token = query.get('hub.verify_token', '')
    challenge = query.get('hub.challenge', '')
    if (not configured() or query.get('hub.mode') != 'subscribe' or not token.isascii()
            or not hmac.compare_digest(expected, token) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', challenge)):
        sec.fail(403, 'WHATSAPP_VERIFY_FAILED')
    return PlainTextResponse(challenge)


async def raw_body(request: Request):
    return await request.body()


def messages(payload):
    """Yield (sender, message_id, text, timestamp) for text messages and button replies to our number."""
    phone_id = os.getenv('SAFELEDGER_WHATSAPP_PHONE_ID', '')
    if payload.get('object') != 'whatsapp_business_account' or not isinstance(payload.get('entry'), list):
        return
    for entry in payload['entry'][:5]:
        for change in (entry.get('changes') or [])[:5] if isinstance(entry, dict) else []:
            value = change.get('value') if isinstance(change, dict) else None
            if not isinstance(value, dict) or (value.get('metadata') or {}).get('phone_number_id') != phone_id:
                continue
            for item in (value.get('messages') or [])[:10]:
                if not isinstance(item, dict):
                    continue
                sender, identity, stamp = item.get('from'), item.get('id'), item.get('timestamp')
                if not (isinstance(sender, str) and re.fullmatch(r'[0-9]{8,15}', sender) and isinstance(identity, str)
                        and 1 <= len(identity) <= 200 and isinstance(stamp, str) and stamp.isdigit()):
                    continue
                text = None
                if item.get('type') == 'text' and isinstance(item.get('text'), dict):
                    text = item['text'].get('body')
                elif item.get('type') == 'interactive' and isinstance(item.get('interactive'), dict):
                    reply = item['interactive'].get('button_reply') or {}
                    text = reply.get('id') if reply.get('id') in BUTTON_PAYLOADS else None
                elif item.get('type') == 'button' and isinstance(item.get('button'), dict):
                    text = item['button'].get('payload') if item['button'].get('payload') in BUTTON_PAYLOADS else None
                if isinstance(text, str) and 1 <= len(text.strip()) <= 240:
                    yield sender, identity, text.strip(), int(stamp)


@router.post('')
def webhook(request: Request, body: bytes = Depends(raw_body), db=Depends(db_connection)):
    from api.app.chat import brain
    secret = os.getenv('SAFELEDGER_WHATSAPP_APP_SECRET', '').encode()
    got = request.headers.get('x-hub-signature-256', '')
    expected = 'sha256=' + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not configured() or not got.isascii() or not hmac.compare_digest(expected, got):
        sec.fail(403, 'WHATSAPP_SIGNATURE_INVALID')
    try:
        payload = json.loads(body)
    except ValueError:
        sec.fail(422, 'INVALID_WHATSAPP_UPDATE')
    if not isinstance(payload, dict):
        sec.fail(422, 'INVALID_WHATSAPP_UPDATE')
    now = sec.now()
    for sender, identity, text, stamp in messages(payload):
        if abs(now - stamp) > 600:
            continue
        chat_hash = sec.signature('whatsapp-chat', sender)
        try:
            sec.budgets(db, [('whatsapp-webhook:' + chat_hash, 20), ('whatsapp-webhook-all', 120)])
        except sec.PolicyError as error:
            if error.status != 429:
                raise
            continue
        reply, ctx = None, None
        link = re.fullmatch(r'(?:link|connect|capzoryx)?\s*([A-Za-z0-9]{8})', text, re.I)
        with sec.transaction(db):
            db.execute('DELETE FROM whatsapp_updates WHERE received_at<?', (now - 86400,))
            digest = hashlib.sha256(identity.encode()).hexdigest()
            if not db.execute('INSERT OR IGNORE INTO whatsapp_updates VALUES (?,?) RETURNING message_hash', (digest, now)).fetchone():
                continue
            previous = db.execute('SELECT business_id,user_id,confirmed_at,chat_enabled,records_enabled,key_tag '
                                  'FROM whatsapp_links WHERE chat_hash=?', (chat_hash,)).fetchone()
            if text.casefold() in ('stop', '/stop', 'unlink', 'বন্ধ'):
                if previous:
                    forget(db, previous[0], previous[1])
                    reply = brain.Reply("Disconnected. I won't message you again. You can reconnect from Capzoryx Settings anytime.")
            elif link and not previous:
                row = db.execute('SELECT business_id,user_id FROM whatsapp_links WHERE code_hash=? AND expires_at>? '
                                 'AND confirmed_at IS NULL AND chat_hash IS NULL',
                                 (sec.signature('whatsapp-code', link[1].upper()), now)).fetchone()
                if row:
                    business, user = row
                    key = customer_key(db, business, create=True)
                    cipher = seal(key, sec.canonical({'id': sender, 'label': '…' + sender[-4:]}).encode(),
                                  business + '/' + user + '/whatsapp')
                    db.execute('UPDATE whatsapp_links SET chat_hash=?,chat_enc=?,key_tag=?,code_hash=NULL '
                               'WHERE business_id=? AND user_id=?', (chat_hash, cipher, key_tag(key), business, user))
                    reply = brain.Reply('Almost there! Go back to Capzoryx Settings and confirm this WhatsApp number to finish connecting.')
                else:
                    reply = brain.Reply(UNLINKED)
            elif previous and not previous[2]:
                reply = brain.Reply('Almost there! Go back to Capzoryx Settings and confirm this WhatsApp number to finish connecting.')
            elif previous:
                business, user = previous[0], previous[1]
                active = db.execute("""SELECT 1 FROM effective_security_users u JOIN workspace_meta w ON w.business_id=u.business_id
                                       WHERE u.user_id=? AND u.business_id=? AND u.active=1 AND u.role='owner'
                                       AND w.kind='personal' AND w.archived_at IS NULL""", (user, business)).fetchone()
                key = customer_key(db, business) if active else None
                if key and key_tag(key) == previous[5]:
                    ctx = brain.Context('whatsapp', chat_hash, business, user, chat_enabled=bool(previous[3]),
                                        records_enabled=bool(previous[3] and previous[4]), settings_hint='Settings → WhatsApp')
                    reply = brain.decide(db, ctx, text)
            else:
                reply = brain.Reply(UNLINKED)
        if reply and ctx and (reply.llm is not None or reply.save is not None):
            reply = brain.finish(db, ctx, reply)
        if reply and reply.text:
            send_message(sender, reply.text, reply.buttons)
    return {'ok': True}


def send_message(to, text, buttons=()):
    if buttons:
        payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'interactive',
                   'interactive': {'type': 'button', 'body': {'text': text[:1024]},
                                   'action': {'buttons': [{'type': 'reply', 'reply': {'id': data, 'title': label[:20]}}
                                                          for label, data in buttons[:3]]}}}
    else:
        payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'text',
                   'text': {'body': text[:4096], 'preview_url': False}}
    # Keep the access token out of client URL logs; the phone id is not secret.
    try:
        request = httpx.Request('POST', GRAPH + os.environ['SAFELEDGER_WHATSAPP_PHONE_ID'] + '/messages', json=payload,
                                headers={'Authorization': 'Bearer ' + os.environ['SAFELEDGER_WHATSAPP_TOKEN']},
                                extensions={'timeout': dict.fromkeys(('connect', 'read', 'write', 'pool'), 8)})
        with (TRANSPORT or httpx.HTTPTransport(trust_env=False)) as transport:
            response = transport.handle_request(request)
            try:
                response.read()
                ok = response.status_code == 200
            finally:
                response.close()
        if not ok:
            log.warning('WhatsApp reply was not accepted.')
        return ok
    except (httpx.HTTPError, KeyError):
        log.warning('WhatsApp reply could not be sent.')
        return False
