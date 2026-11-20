import sqlite3
import httpx
from api.app import security as sec
from api.app.notifications import telegram
from api.tests.test_accounts import signup,world


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
        assert calls==[]
        assert db.execute('SELECT COUNT(*) FROM telegram_updates').fetchone()[0]==1
    assert c.post(base+'/confirm',json={}).status_code==200
    with sqlite3.connect(path) as db:
        for _ in range(2):
            with sec.transaction(db):telegram.queue(db,business,noon)
            telegram.deliver(db,business,noon)
        count=2 if telegram.datetime.fromtimestamp(noon,telegram.BD).weekday()==6 else 1
        assert len(calls)==count
        assert all('notification inbox' in call and 'balance' not in call for call in calls)
    event['update_id']=11;event['message']['text']='/stop'
    assert c.post(base,json=event,headers=headers).status_code==200
    assert not c.get(base+'/link').json()['linked']
    assert not c.get('/api/workspace').json()['events']
