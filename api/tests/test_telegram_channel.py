import json
import sqlite3
import httpx
from api.app import security as sec
from api.app.notifications import telegram
from api.tests.test_accounts import signup,world
from api.tests.test_bill_email import bill


def test_link_requires_user_confirmation_and_replays_never_duplicate(world,monkeypatch):
    c,path=world
    agent=signup(c,'channelowner');business=agent['business_id']
    base='/api/channels/telegram'
    assert c.get(base+'/link').json()['configured'] is False
    assert c.post(base+'/link-code',json={}).status_code==503
    secret='w'*40
    monkeypatch.setenv('SAFELEDGER_TELEGRAM_ENABLED','1')
    monkeypatch.setenv('SAFELEDGER_TELEGRAM_BOT_TOKEN','123456:'+'t'*32)
    monkeypatch.setenv('SAFELEDGER_TELEGRAM_WEBHOOK_SECRET',secret)
    monkeypatch.setenv('SAFELEDGER_TELEGRAM_BOT_USERNAME','test_bot')
    monkeypatch.setenv('SAFELEDGER_PUBLIC_URL','https://test.invalid')
    calls=[]
    def fake(request):
        calls.append(request.content.decode())
        return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(telegram,'TRANSPORT',httpx.MockTransport(fake))
    # Each action uses a local test client. No network call goes to Telegram.
    token=c.post(base+'/link-code',json={}).json()['code']
    event={'update_id':10,'message':{'text':'/start '+token,'date':sec.now(),'chat':{'id':12345,'type':'private'},
                                     'from':{'id':12345,'username':'test_member'}}}
    assert c.post(base,json=event).status_code==403
    headers={'X-Telegram-Bot-Api-Secret-Token':secret}
    for _ in range(2):
        assert c.post(base,json=event,headers=headers).status_code==200
    assert c.get(base+'/link').json()['pending']
    noon=int(telegram.datetime.now(telegram.BD).replace(hour=12,minute=0,second=0,microsecond=0).timestamp())
    with sqlite3.connect(path) as db:
        with sec.transaction(db):
            telegram.queue(db,business,noon)
        telegram.deliver(db,business,noon)
        assert len(calls)==1 and 'finish connecting' in calls[0]
        calls.clear()
        assert db.execute('SELECT COUNT(*) FROM telegram_updates').fetchone()[0]==1
    assert c.post(base+'/confirm',json={}).status_code==200
    with sqlite3.connect(path) as db:
        for _ in range(2):
            with sec.transaction(db):telegram.queue(db,business,noon)
            telegram.deliver(db,business,noon)
        count=2 if telegram.datetime.fromtimestamp(noon,telegram.BD).weekday()==6 else 1
        assert len(calls)==count
        assert all('notification inbox' in call and 'balance' not in call for call in calls)
    bill(c).raise_for_status()
    with sqlite3.connect(path) as db:
        for _ in range(2):
            with sec.transaction(db):telegram.queue(db,business,noon,has_due_bills=True)
            telegram.deliver(db,business,noon)
        assert len(calls)==count+1
        assert 'A Capzoryx bill needs your review.' in calls[-1] and 'PRIVATE-BILL' not in calls[-1]
    event['update_id']=11;event['message']['text']='/stop'
    assert c.post(base,json=event,headers=headers).status_code==200
    assert not c.get(base+'/link').json()['linked']
    assert not c.get('/api/workspace').json()['events']


def test_private_book_replies_require_separate_opt_in_and_never_write(world,monkeypatch):
    c,path=world
    signup(c,'telegram_books')
    base='/api/channels/telegram'
    secret='x'*40
    for suffix,value in {'ENABLED':'1','BOT_TOKEN':'123456:'+'t'*32,'WEBHOOK_SECRET':secret,'BOT_USERNAME':'books_test_bot'}.items():
        monkeypatch.setenv('SAFELEDGER_TELEGRAM_'+suffix,value)
    sent=[]
    def fake(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(telegram,'TRANSPORT',httpx.MockTransport(fake))
    headers={'X-Telegram-Bot-Api-Secret-Token':secret}
    def incoming(update,text,chat=65432,kind='private'):
        message={'text':text,'chat':{'id':chat,'type':kind},'from':{'id':chat},'date':sec.now()}
        c.post(base,json={'update_id':update,'message':message},headers=headers).raise_for_status()
    token=c.post(base+'/link-code',json={}).json()['code']
    incoming(101,'/start '+token)
    incoming(102,'/balance')
    assert len(sent)==1 and 'finish connecting' in sent[0]['text']
    assert c.post(base+'/chat',json={'enabled':True}).status_code==409
    c.post(base+'/confirm',json={}).raise_for_status()
    incoming(103,'/balance')
    assert 'enable Telegram book replies' in sent[-1]['text']
    assert not c.get(base+'/link').json()['chat_enabled']
    c.post(base+'/chat',json={'enabled':True}).raise_for_status()
    assert c.get(base+'/link').json()['chat_enabled']
    bill(c).raise_for_status()
    incoming(104,'/bills')
    assert sent[-1]['text'].startswith('Open supplier bills: BDT 3,892.41')
    assert sent[-1]['chat_id']=='65432'
    before=len(sent)
    incoming(104,'/bills')
    incoming(105,'/bills',chat=65433)
    incoming(106,'/bills',kind='group')
    assert len(sent)==before
    incoming(107,'হাতে কত টাকা আছে?')
    assert sent[-1]['text'].startswith('Cash balance: BDT')
    incoming(108,'pay BDT 800 to someone')
    assert sent[-1]['text']==telegram.CHAT_HELP
    assert not c.get('/api/workspace').json()['events']
    c.post(base+'/chat',json={'enabled':False}).raise_for_status()
    incoming(109,'/balance')
    assert 'enable Telegram book replies' in sent[-1]['text']
    before=len(sent)
    incoming(110,'/stop')
    incoming(111,'/balance')
    assert len(sent)==before
    assert not c.get(base+'/link').json()['linked']


def test_webhook_setup_registers_only_the_explicit_service_url(monkeypatch):
    inbound='https://api.synthetic.invalid/api/channels/telegram'
    secret='s'*40
    for suffix,value in {'ENABLED':'1','BOT_TOKEN':'123456:'+'t'*32,'WEBHOOK_SECRET':secret,
                         'BOT_USERNAME':'books_test_bot','WEBHOOK_URL':inbound}.items():
        monkeypatch.setenv('SAFELEDGER_TELEGRAM_'+suffix,value)
    calls=[]
    def fake(request):
        calls.append(json.loads(request.content))
        assert request.url.host=='api.telegram.org' and request.url.path.endswith('/setWebhook')
        return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(telegram,'TRANSPORT',httpx.MockTransport(fake))
    telegram.register_webhook()
    assert calls==[{'url':inbound,'secret_token':secret,'allowed_updates':['message']}]
