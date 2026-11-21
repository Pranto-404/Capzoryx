"""Hugging Face private Space adapter for owner-reviewed BDT cash drafts."""
import json
import os
import re
import threading
import time
from datetime import date, timedelta
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool

from api.app import security as sec
from api.app.agents.errors import ProviderError
from api.app.agents.provider import strict_json
from api.app.accounts import today_bd
from api.app.assist import BANGLA_DIGITS, normalize_draft, parse_amount
from api.app.contracts import Contract
from api.app.routes import db_connection, principal

router = APIRouter(prefix="/api")
SPACE = "https://pranto-404-capzoryx-hisab-inference.hf.space/gradio_api/call/extract"
SLOT = threading.BoundedSemaphore(1)
ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
AMOUNT = re.compile(r"(?<![\w,.-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w,]|\.\d)")
TAKA = re.compile(r"\b(?:bdt|taka|tk)\b|টাকা|৳", re.I)
OTHER_CURRENCY = re.compile(r"\b(?:usd|eur|gbp|inr|sar|aed|cad|aud|jpy|cny|dollar|dollars|rupee|rupees|euro|euros)\b|[$€£₹¥]", re.I)
INFLOW = re.compile(r"\b(?:received|pailam|pelam|peyechi)\b|পেলাম|পেয়েছি|পেয়েছি", re.I)
OUTFLOW = re.compile(r"\b(?:paid|spent|dilam|diyechi)\b|দিলাম|দিয়েছি|দিয়েছি|খরচ করলাম", re.I)
YESTERDAY = re.compile(r"\b(?:yesterday|gotokal)\b|গতকাল", re.I)
AMBIGUOUS = re.compile(r"\b(?:not|never|didn.t|unpaid|pending|due|will|tomorrow|million|thousand|lakh|lacs?|hajar|hazar|koti|crore)\b|হাজার|লাখ|লক্ষ|কোটি|বাকি|দিইনি", re.I)


def configured():
    return bool(os.getenv("CAPZORYX_HISAB_HF_TOKEN", "").strip())


def facts(sentence, today):
    """Require a single, explicit taka amount in a statement of completed cash movement."""
    text = sentence.translate(BANGLA_DIGITS)
    directions = (bool(INFLOW.search(text)), bool(OUTFLOW.search(text)))
    if not TAKA.search(text) or OTHER_CURRENCY.search(text) or sum(directions) != 1 or AMBIGUOUS.search(text):
        return None
    dates = ISO_DATE.findall(text)
    numeric = ISO_DATE.sub("", text)
    amounts = [parse_amount(match) for match in AMOUNT.findall(numeric)]
    if len(dates) > 1 or len(amounts) != 1 or re.search(r"(?<!\d)-\s*\d", numeric):
        return None
    amount = amounts.pop()
    if amount is None or not Decimal("0") < amount <= Decimal("10000000000"):
        return None
    try:
        day = date.fromisoformat(dates[0]) if dates else today - timedelta(days=int(bool(YESTERDAY.search(text))))
    except ValueError:
        return None
    if day > today:
        return None
    return amount, "inflow" if directions[0] else "outflow", day


def hosted_extract(sentence):
    """Keep the Space credential server-side and accept only the private endpoint's result."""
    key = os.environ.get("CAPZORYX_HISAB_HF_TOKEN", "").strip()
    if not key:
        raise ProviderError("HISAB_NOT_AVAILABLE")
    if not SLOT.acquire(blocking=False):
        raise ProviderError("HISAB_BUSY")
    deadline = time.monotonic() + 24
    try:
        with httpx.Client(
            headers={"Authorization": f"Bearer {key}"},
            follow_redirects=False,
            timeout=httpx.Timeout(21, connect=4),
            trust_env=False,
        ) as client:
            reply = client.post(SPACE, json={"data": [sentence]}, timeout=6)
            if reply.status_code != 200:
                raise ProviderError("HISAB_NOT_AVAILABLE")
            ticket = reply.json().get("event_id")
            if not isinstance(ticket, str) or not re.fullmatch(r"[a-f0-9]{32}", ticket):
                raise ProviderError("HISAB_NOT_AVAILABLE")
            with client.stream("GET", f"{SPACE}/{ticket}", headers={"Accept": "text/event-stream"}) as events:
                if events.status_code != 200:
                    raise ProviderError("HISAB_NOT_AVAILABLE")
                event = ""
                for line in events.iter_lines():
                    if time.monotonic() >= deadline or len(line) > 8192:
                        break
                    if line.startswith("event: "):
                        event = line[7:]
                        if event == "error":
                            break
                    elif event == "complete" and line.startswith("data: "):
                        values = strict_json(line[6:])
                        if isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict):
                            return values[0]
                        break
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    finally:
        SLOT.release()
    raise ProviderError("HISAB_NOT_AVAILABLE")


class ExtractBody(Contract):
    text: str = Field(min_length=3, max_length=400)
    consent: StrictBool


@router.post("/assist/hisab")
def extract(body: ExtractBody, actor=Depends(principal), db=Depends(db_connection)):
    if actor.role != "owner":
        sec.fail(403, "OWNER_REQUIRED")
    if not body.consent:
        sec.fail(403, "EXTERNAL_AI_CONSENT_REQUIRED")
    if not configured():
        raise ProviderError("HISAB_NOT_AVAILABLE")
    sec.budgets(db, [("hisab:" + actor.business_id, 4), ("hisab-hosted", 10)])
    if sec.runtime_dataset(db, actor.business_id).currency != "BDT":
        sec.fail(422, "HISAB_BDT_ONLY")
    today = today_bd()
    source = facts(body.text, today)
    if source is None:
        sec.fail(422, "HISAB_ONE_CASH_RECORD")
    amount, direction, when = source
    prediction = hosted_extract(body.text)
    if (prediction.get("kind") != "cash" or prediction.get("currency") != "BDT"
            or parse_amount(prediction.get("amount")) != amount or prediction.get("direction") != direction):
        sec.fail(422, "HISAB_REVIEW_NEEDED")
    vendor = prediction.get("vendor")
    vendor = vendor.strip() if isinstance(vendor, str) else ""
    if vendor.casefold() not in body.text.casefold():
        vendor = ""
    draft = normalize_draft(
        dict(kind="cash", amount=format(amount, "f"), direction=direction, currency="BDT",
             date=when.isoformat(), vendor=vendor, status="cleared"),
        "BDT",
        today,
    )
    return dict(draft=draft, model="Hisab-LM", simulation_only=True)
