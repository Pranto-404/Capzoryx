import hashlib
import hmac
import json

import httpx

from api.app import security as sec
from api.app.notifications import whatsapp
from api.app.ratelimit import limiter
from api.tests.test_accounts import signup, world  # noqa: F401
from api.tests.test_bill_email import bill

SECRET = 'a' * 32
ENV = {'ENABLED': '1', 'TOKEN': 'E' * 60, 'PHONE_ID': '1234567890', 'APP_SECRET': SECRET,
       'VERIFY_TOKEN': 'v' * 24, 'NUMBER': '8801700000000'}


def setup(monkeypatch):
    for suffix, value in ENV.items():
        monkeypatch.setenv('SAFELEDGER_WHATSAPP_' + suffix, value)
    sent = []

    def fake(request):
        assert request.url.host == 'graph.facebook.com' and request.headers['authorization'] == 'Bearer ' + 'E' * 60
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'messages': [{'id': 'x'}]})
    monkeypatch.setattr(whatsapp, 'TRANSPORT', httpx.MockTransport(fake))
    return sent


def post(c, message, sender='8801711111111', signature=None, phone_id='1234567890'):
    payload = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {
        'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': phone_id}, 'messages': [message]}}]}]}
    body = json.dumps(payload).encode()
    digest = signature or 'sha256=' + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return c.post('/api/channels/whatsapp', content=body,
                  headers={'Content-Type': 'application/json', 'X-Hub-Signature-256': digest})


counter = iter(range(10**6))


def text(c, value, **kw):
    message = {'from': kw.pop('sender', '8801711111111'), 'id': f'wamid.{next(counter)}', 'timestamp': str(sec.now()),
               'type': 'text', 'text': {'body': value}}
    return post(c, message, **kw)


def button(c, data, sender='8801711111111'):
    message = {'from': sender, 'id': f'wamid.{next(counter)}', 'timestamp': str(sec.now()), 'type': 'interactive',
               'interactive': {'type': 'button_reply', 'button_reply': {'id': data, 'title': 'x'}}}
    return post(c, message)


def test_whatsapp_verify_handshake_and_signature(world, monkeypatch):  # noqa: F811
    c, _ = world
    base = '/api/channels/whatsapp'
    assert c.get(base, params={'hub.mode': 'subscribe', 'hub.verify_token': 'v' * 24, 'hub.challenge': '42'}).status_code == 403
    setup(monkeypatch)
    ok = c.get(base, params={'hub.mode': 'subscribe', 'hub.verify_token': 'v' * 24, 'hub.challenge': '42'})
    assert ok.status_code == 200 and ok.text == '42'
    assert c.get(base, params={'hub.mode': 'subscribe', 'hub.verify_token': 'w' * 24, 'hub.challenge': '42'}).status_code == 403
    assert text(c, 'hi', signature='sha256=' + '0' * 64).status_code == 403


def test_whatsapp_links_chats_and_saves_only_after_confirmation(world, monkeypatch):  # noqa: F811
    c, _ = world
    signup(c, 'whatsapp_owner')
    base = '/api/channels/whatsapp'
    assert c.get(base + '/link').json()['configured'] is False
    sent = setup(monkeypatch)
    assert text(c, 'hello').status_code == 200
    assert 'Connect WhatsApp' in sent[-1]['text']['body']
    link = c.post(base + '/link-code', json={}).json()
    assert link['number'] == ENV['NUMBER'] and len(link['code']) == 8
    assert c.get(base + '/link').json()['awaiting_message']
    text(c, 'LINK ' + link['code'].lower())
    assert 'confirm this WhatsApp number' in sent[-1]['text']['body']
    status = c.get(base + '/link').json()
    assert status['pending'] and status['chat_label'] == '…1111'
    text(c, 'cash koto?')
    assert 'confirm this WhatsApp number' in sent[-1]['text']['body']
    c.post(base + '/confirm', json={}).raise_for_status()
    text(c, 'cash koto?')
    assert 'book reply bondho' in sent[-1]['text']['body']
    c.post(base + '/chat', json={'enabled': True}).raise_for_status()
    bill(c).raise_for_status()
    text(c, 'supplier der koto dite hobe?')
    body = sent[-1]
    assert body['type'] == 'interactive' and '৳3,892.41' in body['interactive']['body']['text']
    button(c, '__list_payables__')
    assert '৳3,892.41' in sent[-1]['text']['body']
    text(c, 'ধন্যবাদ')
    assert sent[-1]['text']['body'] in ('স্বাগতম!', 'কোনো ব্যাপার না। 🙂', 'যখন দরকার, বলবেন!')
    limiter.reset()
    assert c.post(base + '/records', json={'enabled': True}).status_code == 200
    text(c, 'paid 1200 to Karim')
    assert sent[-1]['type'] == 'interactive' and 'Shall I save it?' in sent[-1]['interactive']['body']['text']
    button(c, '__save__')
    assert 'Saved' in sent[-1]['text']['body']
    events = c.get('/api/workspace').json()['events']
    assert len(events) == 1 and events[0]['direction'] == 'outflow' and events[0]['amount_minor'] == 120000
    before = len(sent)
    post(c, {'from': '8801711111111', 'id': 'wamid.dup', 'timestamp': str(sec.now()), 'type': 'text', 'text': {'body': 'hi'}})
    post(c, {'from': '8801711111111', 'id': 'wamid.dup', 'timestamp': str(sec.now()), 'type': 'text', 'text': {'body': 'hi'}})
    text(c, 'hi', phone_id='999999999')
    assert len(sent) == before + 1
    text(c, 'stop')
    assert 'Disconnected' in sent[-1]['text']['body'] and not c.get(base + '/link').json()['linked']
