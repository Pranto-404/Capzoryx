import json
from datetime import date
from decimal import Decimal

import httpx

from api.app import hisab_hosted
from api.tests.test_accounts import signup, world


def test_source_requires_one_literal_settled_amount():
    today = date(2026, 11, 22)
    assert hisab_hosted.facts("On 2026-11-21 I paid BDT 1,250.50 to Rahman.", today) == (
        Decimal("1250.50"), "outflow", date(2026, 11, 21)
    )
    assert hisab_hosted.facts("গতকাল রাহমান থেকে ৫০০ টাকা পেলাম।", today) == (
        Decimal("500"), "inflow", date(2026, 11, 21)
    )
    for text in ("I paid 500 BDT and received 50 BDT", "I paid 5,00 BDT", "I paid 1e1 BDT",
                 "I didn't pay BDT 500", "I paid BDT -500", "I paid USD 12, equivalent to BDT 1500",
                 "I paid 50 lakh taka", "On 2026-12-01 I paid BDT 100"):
        assert hisab_hosted.facts(text, today) is None


def test_private_transport_preserves_data_boundary(monkeypatch):
    monkeypatch.setenv("CAPZORYX_HISAB_HF_TOKEN", "synthetic-read-token")
    calls = []
    real_client = httpx.Client
    event = "f" * 32
    prediction = {"kind": "cash", "direction": "outflow", "currency": "BDT", "amount": "1250"}

    def fake(request):
        assert request.headers["authorization"] == "Bearer synthetic-read-token"
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            assert json.loads(request.content) == {"data": ["I paid BDT 1250."]}
            return httpx.Response(200, json={"event_id": event})
        return httpx.Response(200, text="event: heartbeat\n\nevent: complete\ndata: " + json.dumps([prediction]) + "\n\n")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs))
    assert hisab_hosted.hosted_extract("I paid BDT 1250.") == prediction
    assert calls == [("POST", hisab_hosted.SPACE), ("GET", f"{hisab_hosted.SPACE}/{event}")]


def test_hosted_draft_needs_consent_and_never_posts_a_record(world, monkeypatch):
    client, _ = world
    path = "/api/assist/hisab"
    sentence = "I paid BDT 1250 to Rahman."
    assert client.post(path, json={"text": sentence, "consent": True}).status_code == 401
    signup(client, "hisab_owner")
    monkeypatch.setenv("CAPZORYX_HISAB_HF_TOKEN", "synthetic-read-token")
    baseline = client.get("/api/workspace").json()["dataset_revision"]
    prediction = {"kind": "cash", "direction": "outflow", "amount": "1250", "currency": "BDT", "vendor": "Rahman"}
    monkeypatch.setattr(hisab_hosted, "hosted_extract", lambda _: prediction)
    assert client.post(path, json={"text": sentence, "consent": False}).status_code == 403
    reply = client.post(path, json={"text": sentence, "consent": True})
    assert reply.status_code == 200
    assert reply.json()["draft"]["amount_minor"] == 125000
    assert reply.json()["model"] == "Hisab-LM"
    prediction["amount"] = "1200"
    assert client.post(path, json={"text": sentence, "consent": True}).json()["error"]["code"] == "HISAB_REVIEW_NEEDED"
    assert client.get("/api/workspace").json()["dataset_revision"] == baseline
