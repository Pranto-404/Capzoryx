import json

import httpx
import pytest

from api.app.chat import llm
from ml.hisab_chat import self_play


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    llm._cooldown.clear()
    for p in llm.PROVIDERS:
        for field in ('URL', 'KEY', 'MODEL'):
            monkeypatch.delenv(f'CAPZORYX_CHAT_{p.name.upper()}_{field}', raising=False)
    monkeypatch.delenv('SAFELEDGER_LLM_API_KEY', raising=False)
    monkeypatch.setenv('CAPZORYX_CHAT_GROQ_KEY', 'g')


def test_teacher_grades_the_student_and_keeps_only_grounded_rewrites(monkeypatch):
    def fake(request):
        body = json.loads(request.content)
        prompt = body['messages'][-1]['content']
        if request.url.host == 'student.local':
            return httpx.Response(200, json={'choices': [{'message': {'content': 'ami jani na'}}]})
        if 'Write 8 different messages' in prompt:
            content = json.dumps({'messages': ['cash kto ase vai', 'বিক্রি কত হলো?']})
        elif 'cash kto' in prompt:
            balance = prompt.split('Cash balance: ')[1].split('.00')[0]
            content = json.dumps({'score': 2, 'better': f'Ekhon hate {balance} taka ache, vai.'})
        else:  # an invented amount must be dropped by the number check
            content = json.dumps({'score': 1, 'better': 'এই মাসে বিক্রি ৯৯,৯৯৯ টাকা।'})
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    monkeypatch.setattr(self_play, 'TRANSPORT', httpx.MockTransport(fake))
    rows, report = self_play.run('http://student.local/v1', 'hisab-chat', '', examples=4, keep_below=4)
    assert report['graded'] == 4 and report['mean_score'] == 1.5 and report['share_good'] == 0
    assert report['new_training_rows'] == 2 and report['rejected_by_checker'] == 2
    assert all(r['source'] == 'synthetic-selfplay' and 'hate' in r['messages'][-1]['content'] for r in rows)
