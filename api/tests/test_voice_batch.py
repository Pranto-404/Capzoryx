"""Challenge 1: a whole week of spending in one voice note, every entry its own checked draft."""
import base64
import json
from datetime import date

import httpx
import pytest

from api.app import voice_batch as vb
from api.app.chat import llm
from api.tests.test_accounts import signup, world  # noqa: F401

TODAY = date(2026, 11, 24)  # a Tuesday


@pytest.mark.parametrize('text,amount', [
    ('rent 5000 dilam', 5000), ('৫০০০ টাকা ভাড়া', 5000), ('dui hajar pachsho taka', 2500), ('দুই হাজার পাঁচশো টাকা', 2500),
    ('দেড় হাজার', 1500), ('arai hajar', 2500), ('sare tin hajar', 3500), ('2.5k', 2500), ('1,20,000 taka', 120000),
    ('5 hajar 200 taka', 5200), ('two thousand five hundred', 2500), ('pachsho', 500), ('ek lakh', 100000),
])
def test_amounts_said_in_bangla_banglish_and_english(text, amount):
    assert amount in vb.spoken_amounts(text)


@pytest.mark.parametrize('text,expected', [
    ('aj 200 taka', TODAY), ('gotokal 300', date(2026, 11, 23)), ('পরশু', date(2026, 11, 22)), ('3 din age', date(2026, 11, 21)),
    ('tin din age', date(2026, 11, 21)), ('shombar rent', date(2026, 11, 23)), ('শুক্রবার', date(2026, 11, 20)),
    ('on Sunday', date(2026, 11, 22)), ('tuesday', TODAY), ('kono din na', None),
])
def test_days_said_aloud(text, expected):
    assert vb.said_day(text, TODAY) == expected


WEEK = ('Shombar dokan bhara 5000 taka dilam. Tarpor transport e 300. Budhbar Rahim theke 12 hajar taka pelam, '
        'shukrobar biddut bill 1,850 taka. Aj chaa nasta 250.')


def test_rules_split_a_week_without_any_ai():
    drafts, dropped, method = vb.split_note(WEEK, TODAY, 'BDT', 2, use_ai=False)
    assert method == 'rules'
    got = [(d['amount_minor'], d['effective_on'], d.get('direction')) for d in drafts]
    assert got == [(500000, '2026-11-23', 'outflow'), (30000, '2026-11-23', 'outflow'),  # no day said: the day before it
                   (1200000, '2026-11-18', 'inflow'), (185000, '2026-11-20', 'outflow'), (25000, '2026-11-24', 'outflow')]


def _ai(monkeypatch, entries, seen=None):
    def handle(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'entries': entries})}}]})
    monkeypatch.setattr(vb, 'TRANSPORT', httpx.MockTransport(handle))
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_KEY', 'gsk_test')
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_MODEL', 'llama-3.3-70b-versatile')
    for name in ('GEMINI', 'CEREBRAS', 'OPENROUTER', 'MISTRAL', 'GITHUB', 'SAMBANOVA'):
        monkeypatch.delenv(f'CAPZORYX_CHAT_{name}_KEY', raising=False)
    monkeypatch.delenv('SAFELEDGER_LLM_API_KEY', raising=False)
    llm._cooldown.clear()


def test_ai_split_is_checked_against_what_was_said(monkeypatch):
    note = 'Shombar bhara 5000 r transport 300 dilam. Budhbar mal kinlam dui hajar pachsho taka, na na tin hajar.'
    _ai(monkeypatch, [
        {'evidence': 'Shombar bhara 5000', 'amount': 5000, 'type': 'expense', 'when': 'Shombar', 'category': 'rent'},
        {'evidence': 'transport 300 dilam', 'amount': 300, 'type': 'expense', 'category': 'transport'},
        {'evidence': 'Budhbar mal kinlam dui hajar pachsho taka, na na tin hajar', 'amount': 3000, 'type': 'expense', 'when': 'Budhbar'},
        {'evidence': 'Shombar bhara 5000', 'amount': 9000, 'type': 'expense'},          # an amount nobody said
        {'evidence': 'Paid the landlord 7000 on Friday', 'amount': 7000, 'type': 'expense'},  # not in the note
    ])
    drafts, dropped, method = vb.split_note(note, TODAY, 'BDT', 2)
    assert method == 'ai'
    assert [(d['amount_minor'], d['effective_on']) for d in drafts] == [(500000, '2026-11-23'), (30000, '2026-11-23'), (300000, '2026-11-18')]
    assert {d['reason'] for d in dropped} == {'AMOUNT_NOT_SAID', 'NOT_IN_NOTE'}
    assert any('Two numbers' in w for w in drafts[2]['warnings'])  # the correction is flagged for a second look


def test_ai_misses_an_entry_and_the_rule_reader_adds_it_for_checking(monkeypatch):
    _ai(monkeypatch, [{'evidence': 'Shombar dokan bhara 5000 taka dilam', 'amount': 5000, 'type': 'expense', 'when': 'Shombar'}])
    drafts, _, _ = vb.split_note(WEEK, TODAY, 'BDT', 2)
    assert len(drafts) == 5 and drafts[0]['confidence'] == 0.9
    assert all('backup reader' in ' '.join(d['warnings']) for d in drafts[1:])


def test_no_ai_answer_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(vb, 'TRANSPORT', httpx.MockTransport(lambda r: httpx.Response(503)))
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_KEY', 'gsk_test')
    llm._cooldown.clear()
    drafts, _, method = vb.split_note(WEEK, TODAY, 'BDT', 2)
    assert method == 'rules' and len(drafts) == 5


def test_speech_uses_whisper_then_gemini(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request.url.host + request.url.path)
        if 'groq' in request.url.host:
            return httpx.Response(429)
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'shombar bhara 5000 taka'}]}}]})
    monkeypatch.setattr(vb, 'TRANSPORT', httpx.MockTransport(handle))
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_KEY', 'gsk_test')
    monkeypatch.setenv('CAPZORYX_CHAT_GEMINI_KEY', 'gm_test')
    text, model = vb.transcribe(b'x' * 2000, 'audio/webm;codecs=opus', 'bn', 'taka')
    assert text == 'shombar bhara 5000 taka' and model.startswith('gemini')
    assert calls[:2] == ['api.groq.com/openai/v1/audio/transcriptions'] * 2  # large-v3, then turbo


def test_voice_note_routes_end_to_end(world, monkeypatch):  # noqa: F811
    c, _ = world
    signup(c, 'voice_owner')
    c.post('/api/account/profile', json={'smart_assist': True}).raise_for_status()

    def handle(request):
        if request.url.path.endswith('/audio/transcriptions'):
            assert b'whisper-large-v3' in request.content
            return httpx.Response(200, json={'text': WEEK})
        return httpx.Response(503)
    monkeypatch.setattr(vb, 'TRANSPORT', httpx.MockTransport(handle))
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_KEY', 'gsk_test')
    llm._cooldown.clear()
    assert c.get('/api/assist/voice-note').json()['speech'] is True
    audio = base64.b64encode(b'\x1aE\xdf\xa3' + b'0' * 3000).decode()
    refused = c.post('/api/assist/voice-note', json={'audio_b64': audio, 'mime': 'audio/webm;codecs=opus', 'language': 'bn', 'consent': False})
    assert refused.status_code == 403
    heard = c.post('/api/assist/voice-note', json={'audio_b64': audio, 'mime': 'audio/webm;codecs=opus', 'language': 'bn', 'consent': True})
    assert heard.status_code == 200 and heard.json()['transcript'] == WEEK
    split = c.post('/api/assist/batch-drafts', json={'transcript': WEEK, 'consent': True}).json()
    assert len(split['drafts']) == 5
    revision = c.get('/api/workspace').json()['dataset_revision']
    import uuid
    records = [dict(request_id=str(uuid.uuid4()), kind='cash', amount_minor=d['amount_minor'], effective_on=d['effective_on'],
                    direction=d['direction'], status='cleared', memo=d['memo']) for d in split['drafts']]
    saved = c.post('/api/workspace/records/batch', json={'expected_revision': revision, 'records': records})
    assert saved.status_code == 201, saved.text
    assert saved.json()["saved"] == 5
    snap = c.get('/api/workspace').json()['snapshot']
    assert snap['income_minor'] == 1200000 and snap['expenses_minor'] == 500000 + 30000 + 185000 + 25000
    # The same batch again is a replay, not five more records; a stale revision is refused as a whole.
    again = c.post('/api/workspace/records/batch', json={'expected_revision': revision, 'records': records})
    assert again.status_code == 201 and c.get('/api/workspace').json()['snapshot']['income_minor'] == 1200000
    fresh = [dict(r, request_id=str(uuid.uuid4())) for r in records]
    stale = c.post('/api/workspace/records/batch', json={'expected_revision': revision, 'records': fresh})
    assert stale.status_code == 409 and c.get('/api/workspace').json()['snapshot']['income_minor'] == 1200000
