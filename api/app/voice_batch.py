"""A week of spending in one voice note: speech to text, then one checked draft per entry.

Flow: audio (opus, up to 3 minutes) -> Whisper large-v3 on Groq (free tier), then Gemini as a fallback -> transcript the
owner can edit -> entries. An AI model splits the transcript, but nothing it says is trusted on its own:
  * every entry must quote words that are really in the transcript,
  * its amount must be a number actually said in those words (digits, Bangla digits, or number words in Bangla,
    Banglish or English, e.g. "dui hajar pachsho", "দেড় হাজার", "2.5k"),
  * its date is worked out here from what was said ("gotokal", "shombar", "3 din age"); a sentence without a date
    belongs to the day mentioned before it.
When no AI service answers, a rule-based splitter makes the drafts. Nothing is saved until the owner confirms;
saving many drafts is one atomic step (see inputs.add_records).
"""
import base64
import binascii
import json
import logging
import re
import time
import unicodedata
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool

from api.app import security as sec
from api.app.accounts import today_bd
from api.app.contracts import Contract
from api.app.routes import db_connection, principal

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/assist')
TRANSPORT = None  # tests inject an httpx.MockTransport
MAX_AUDIO_BYTES = 2_400_000  # about 10 minutes of 32 kbps opus; the recorder stops at 3
MAX_TRANSCRIPT = 4000
MAX_ENTRIES = 40
LOOKBACK_DAYS = 14

# ---------- numbers said aloud ----------
BN_DIGITS = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
_SMALL = {}


def _add(words, start, step=1):
    for i, word in enumerate(words.split()):
        _SMALL[unicodedata.normalize('NFC', word)] = start + i * step


_add('এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো চৌদ্দ পনেরো ষোলো সতেরো আঠারো উনিশ', 1)
_add('বিশ একুশ বাইশ তেইশ চব্বিশ পঁচিশ ছাব্বিশ সাতাশ আটাশ ঊনত্রিশ', 20)
_add('ত্রিশ একত্রিশ বত্রিশ তেত্রিশ চৌত্রিশ পঁয়ত্রিশ ছত্রিশ সাঁইত্রিশ আটত্রিশ ঊনচল্লিশ', 30)
_add('চল্লিশ একচল্লিশ বিয়াল্লিশ তেতাল্লিশ চুয়াল্লিশ পঁয়তাল্লিশ ছেচল্লিশ সাতচল্লিশ আটচল্লিশ ঊনপঞ্চাশ', 40)
_add('পঞ্চাশ একান্ন বাহান্ন তিপ্পান্ন চুয়ান্ন পঞ্চান্ন ছাপ্পান্ন সাতান্ন আটান্ন ঊনষাট', 50)
_add('ষাট একষট্টি বাষট্টি তেষট্টি চৌষট্টি পঁয়ষট্টি ছেষট্টি সাতষট্টি আটষট্টি ঊনসত্তর', 60)
_add('সত্তর একাত্তর বাহাত্তর তিয়াত্তর চুয়াত্তর পঁচাত্তর ছিয়াত্তর সাতাত্তর আটাত্তর ঊনআশি', 70)
_add('আশি একাশি বিরাশি তিরাশি চুরাশি পঁচাশি ছিয়াশি সাতাশি আটাশি ঊননব্বই', 80)
_add('নব্বই একানব্বই বিরানব্বই তিরানব্বই চুরানব্বই পঁচানব্বই ছিয়ানব্বই সাতানব্বই আটানব্বই নিরানব্বই', 90)
_add('one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen '
     'eighteen nineteen', 1)
_add('twenty thirty forty fifty sixty seventy eighty ninety', 20, 10)
# Banglish (romanised Bangla) as people type and as speech engines spell it.
for words, value in [('ek ak', 1), ('dui du duii', 2), ('tin teen', 3), ('char', 4), ('panch pach paach', 5),
                     ('choy chhoy soy', 6), ('saat sat', 7), ('aat aath', 8), ('noy nou', 9), ('dosh dos', 10),
                     ('egaro', 11), ('baro', 12), ('tero', 13), ('choddo', 14), ('ponero', 15), ('sholo', 16),
                     ('shotero', 17), ('atharo', 18), ('unish', 19), ('bish bis', 20), ('tirish tiris trish', 30),
                     ('chollish cholish', 40), ('ponchash ponchas', 50), ('shaat shat', 60), ('sottor', 70),
                     ('ashi', 80), ('nobboi', 90)]:
    for word in words.split():
        _SMALL.setdefault(word, value)
_HUNDREDS = {}
for i, forms in enumerate(['এক', 'দুই দু', 'তিন', 'চার', 'পাঁচ', 'ছয় ছ', 'সাত', 'আট', 'নয়']):
    for form in forms.split():
        for ending in ('শ', 'শো', 'শত'):
            _HUNDREDS[unicodedata.normalize('NFC', form + ending)] = (i + 1) * 100
for i, forms in enumerate(['ek', 'du dui', 'tin', 'char', 'pach panch', 'choy chhoy', 'sat saat', 'at aat', 'noy']):
    for form in forms.split():
        for ending in ('sho', 'sh', 'show', 'shoto'):
            _HUNDREDS[form + ending] = (i + 1) * 100
HUNDRED = {'hundred', 'শ', 'শো', 'শত', 'sho', 'shoto'}
SCALES = {'thousand': 1000, 'হাজার': 1000, 'hajar': 1000, 'hazar': 1000, 'k': 1000,
          'lakh': 100_000, 'lac': 100_000, 'lakhs': 100_000, 'লাখ': 100_000, 'লক্ষ': 100_000,
          'million': 1_000_000, 'crore': 10_000_000, 'কোটি': 10_000_000, 'koti': 10_000_000}
FRACTIONS = {'দেড়': 1.5, 'der': 1.5, 'deŗ': 1.5, 'আড়াই': 2.5, 'arai': 2.5, 'adai': 2.5}
HALF_MORE = {'সাড়ে', 'sare', 'shade', 'sharhe'}
TOKEN = re.compile(r'\d+(?:[.,]\d+)*(?:\.\d+)?k?|[\wঀ-৿]+', re.UNICODE)


def _norm(text):
    return unicodedata.normalize('NFC', text.translate(BN_DIGITS)).casefold()


def _digit(token):
    raw = token[:-1] if token.endswith('k') else token
    try:
        value = float(raw.replace(',', ''))
    except ValueError:
        return None
    return value * 1000 if token.endswith('k') else value


def spoken_amounts(text):
    """Every amount said in `text`, as numbers in major units ("2 hajar 500" -> 2500, "দেড় হাজার" -> 1500)."""
    found = set()
    tokens = TOKEN.findall(_norm(text))
    i = 0
    while i < len(tokens):
        start = i
        total, current, fraction, half, seen = 0.0, 0.0, 0.0, False, False
        while i < len(tokens):
            word = tokens[i]
            number = _digit(word) if word[0].isdigit() else None
            if number is not None:
                current += number
            elif word in _SMALL:
                current += _SMALL[word]
            elif word in _HUNDREDS:
                current += _HUNDREDS[word]
            elif word in HUNDRED and seen:
                current = max(current, 1) * 100
            elif word in FRACTIONS:
                fraction = FRACTIONS[word]
            elif word in HALF_MORE:
                half = True
            elif word in SCALES and (seen or fraction):
                base = fraction or current or 1
                total += (base + (0.5 if half else 0)) * SCALES[word]
                current, fraction, half = 0.0, 0.0, False
            elif word == 'and' and seen:
                pass
            else:
                break
            seen = True
            i += 1
        if seen:
            value = total + current
            if value > 0:
                found.add(round(value, 2))
        if i == start:
            i += 1
    return found


# ---------- dates said aloud ----------
WEEKDAYS = {
    0: ('monday', 'সোমবার', 'shombar', 'sombar', 'somobar', 'shomobar'),
    1: ('tuesday', 'মঙ্গলবার', 'mongolbar', 'mongalbar'),
    2: ('wednesday', 'বুধবার', 'budhbar', 'budbar', 'budhobar'),
    3: ('thursday', 'বৃহস্পতিবার', 'brihospotibar', 'bishudbar', 'bishudbar', 'brihoshpotibar'),
    4: ('friday', 'শুক্রবার', 'shukrobar', 'sukrobar'),
    5: ('saturday', 'শনিবার', 'shonibar', 'sonibar'),
    6: ('sunday', 'রবিবার', 'robibar', 'robbar', 'রোববার'),
}
TODAY_WORDS = ('today', 'আজ', 'আজকে', 'aj', 'aaj', 'ajke', 'aajke')
YESTERDAY_WORDS = ('yesterday', 'গতকাল', 'gotokal', 'gotokaal', 'kal', 'kalke', 'কাল', 'কালকে')
DAY_BEFORE_WORDS = ('পরশু', 'porshu', 'porsu', 'poshu')
AGO = re.compile(r'(\d+)\s*(?:din|দিন|days?)\s*(?:age|আগে|ago)')


def said_day(text, today):
    """The day a phrase refers to, or None. Weekdays mean the most recent one (today included)."""
    words = TOKEN.findall(_norm(text))
    lowered = _norm(text)
    if 'day before yesterday' in lowered or any(w in words for w in DAY_BEFORE_WORDS):
        return today - timedelta(days=2)
    match = AGO.search(lowered)
    if match is None:
        for word, value in _SMALL.items():  # "tin din age", "তিন দিন আগে"
            if value <= 13 and re.search(rf'(?<!\w){re.escape(word)}\s*(?:din|দিন|days?)\s*(?:age|আগে|ago)', lowered):
                return today - timedelta(days=value)
    elif int(match.group(1)) <= LOOKBACK_DAYS:
        return today - timedelta(days=int(match.group(1)))
    for weekday, names in WEEKDAYS.items():
        if any(n in words or (not n.isascii() and n in lowered) for n in names):
            return today - timedelta(days=(today.weekday() - weekday) % 7)
    if any(w in words for w in YESTERDAY_WORDS):
        return today - timedelta(days=1)
    if any(w in words for w in TODAY_WORDS):
        return today
    iso = re.search(r'(20\d\d)-(\d\d)-(\d\d)', lowered)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    return None


# ---------- splitting without AI ----------
INCOME = re.compile(r'\b(?:received|got|earned|sold|sale|sales|collected|income|pelam|pailam|peyechi|peyesi|paisi|'
                    r'bikri|becha|bechlam|joma)\b|পেয়েছি|পেলাম|পাইলাম|বিক্রি|বেচা|বেচলাম|আয়|জমা', re.I)
BILL = re.compile(r'\b(?:baki|due|owe|bill pending|unpaid)\b|বাকি|পাওনা', re.I)
SPLIT = re.compile(r'[.](?!\d)|[।!?;\n]+|,(?!\d)|\b(?:tarpor|tarpore|then|arpor|erpor|after that|and then)\b|তারপর|এরপর|আর তারপর', re.I)


def rule_entries(transcript):
    """A sentence-by-sentence reading used when no AI service is available: one entry per part with an amount."""
    entries = []
    for part in SPLIT.split(transcript):
        part = part.strip(' ,-')
        if len(part) < 3:
            continue
        amounts = spoken_amounts(part)
        if len(amounts) != 1:  # none, or two numbers that cannot be told apart without help
            continue
        kind = 'bill' if BILL.search(part) else 'income' if INCOME.search(part) else 'expense'
        entries.append(dict(evidence=part, amount=next(iter(amounts)), type=kind, when='', party='', category='', note=part[:120]))
    return entries


# ---------- splitting with AI ----------
SPLIT_SYSTEM = (
    'You split a small business owner\'s voice note into separate money entries. The note may be Bangla, Banglish '
    '(Bangla in English letters) or English, and may contain speech-recognition mistakes.\n'
    'Return JSON only: {"entries":[{"evidence":"the exact words of the note for this one entry, copied character for '
    'character","amount":number as said (taka, digits only),"type":"expense|income|bill","when":"the words that say '
    'which day, copied from the note, or empty","party":"who was paid or who paid, or empty","category":"one or two '
    'English words such as rent, transport, stock, salary, utilities, food, sales, repair, other","note":"a short '
    'description in the language of the note"}]}\n'
    'Rules: one entry for every separate payment, purchase or sale, even when they share a sentence; never merge two '
    'amounts; never invent an amount or a payment that was not said; convert number words to digits '
    '("dui hajar pachsho" = 2500, "দেড় হাজার" = 1500); if the speaker corrects an amount ("na na, 600"), give only '
    'the corrected amount; type "bill" only for money still owed to a supplier; skip plans, questions and amounts '
    'that are not money paid or received.')


def _providers():
    from api.app.chat import llm
    return [p for p in llm.available() if not p.own]


def ai_entries(transcript, deadline):
    """Entries from the first AI service that returns valid JSON in time, or None."""
    from api.app.chat import llm
    messages = [{'role': 'system', 'content': SPLIT_SYSTEM}, {'role': 'user', 'content': transcript}]
    for provider in _providers():
        timeout = min(20, deadline - time.monotonic())
        if timeout <= 2:
            break
        payload = {'model': provider.model_name, 'messages': messages, 'temperature': 0, 'max_tokens': 2500,
                   'response_format': {'type': 'json_object'}}
        try:
            with httpx.Client(transport=TRANSPORT, trust_env=False, follow_redirects=False, timeout=timeout) as client:
                response = client.post(provider.url + '/chat/completions', json=payload, headers={'Authorization': 'Bearer ' + provider.key})
                if response.status_code == 400:  # a model without JSON mode: ask again without it
                    payload.pop('response_format')
                    response = client.post(provider.url + '/chat/completions', json=payload, headers={'Authorization': 'Bearer ' + provider.key})
            if response.status_code == 429:
                llm.rest(provider, 600)
                continue
            if response.status_code != 200:
                llm.rest(provider, 120)
                continue
            content = response.json()['choices'][0]['message']['content'] or ''
            content = content[content.find('{'):content.rfind('}') + 1]
            entries = json.loads(content).get('entries')
            if isinstance(entries, list):
                return entries, provider.name
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            continue
    return None


# ---------- checking and turning entries into drafts ----------
def _words(text):
    return [w for w in TOKEN.findall(_norm(text)) if len(w) > 1 or w.isdigit()]


def quoted(evidence, transcript):
    """The entry quotes the note: its words appear in the transcript (speech engines may differ in small ways)."""
    words = _words(evidence)
    if not words:
        return False
    known = set(_words(transcript))
    return sum(w in known for w in words) / len(words) >= 0.8


CATEGORY = re.compile(r'^[a-z][a-z /&-]{0,30}$')


def checked_drafts(raw_entries, transcript, today, currency, digits):
    """Validated drafts in the order they were said; entries that fail a check are reported, not silently fixed."""
    drafts, dropped, day = [], [], None
    seen = set()
    for raw in (raw_entries or [])[:MAX_ENTRIES]:
        if not isinstance(raw, dict):
            continue
        evidence = str(raw.get('evidence') or '').strip()[:400]
        if not quoted(evidence, transcript):
            dropped.append(dict(evidence=evidence[:120], reason='NOT_IN_NOTE'))
            continue
        try:
            amount = round(float(str(raw.get('amount')).replace(',', '')), 2)
        except (TypeError, ValueError):
            amount = 0
        said = spoken_amounts(evidence) or spoken_amounts(transcript)
        if amount <= 0 or amount not in said:
            dropped.append(dict(evidence=evidence[:120], reason='AMOUNT_NOT_SAID'))
            continue
        warnings = []
        spoken = said_day(str(raw.get('when') or ''), today) or said_day(evidence, today)
        if spoken is not None:
            day = spoken
        elif day is None:
            warnings.append('No day was said, so today is used. Change it if needed.')
        effective = day or today
        if effective > today or effective < today - timedelta(days=60):
            warnings.append('Check the date.')
            effective = min(max(effective, today - timedelta(days=60)), today)
        kind = raw.get('type') if raw.get('type') in ('expense', 'income', 'bill') else 'expense'
        party = re.sub(r'[\x00-\x1f]+', ' ', str(raw.get('party') or '')).strip()[:60]
        category = str(raw.get('category') or '').strip().casefold()
        category = category if CATEGORY.match(category) else ''
        note = re.sub(r'[\x00-\x1f]+', ' ', str(raw.get('note') or evidence)).strip()[:160]
        key = (kind, amount, effective, _norm(evidence))
        if key in seen:
            continue
        seen.add(key)
        minor = int(round(amount * 10 ** digits))
        if len(said) > 1 and len(spoken_amounts(evidence)) > 1:
            warnings.append('Two numbers were said here. Check that this is the right amount.')
        memo = ' · '.join(x for x in (category.capitalize() if category else '', party, note) if x)[:200]
        draft = dict(ok=True, kind='invoice' if kind == 'bill' else 'cash', entry_type=kind, amount_minor=minor,
                     currency=currency, workspace_currency=currency, currency_mismatch=False,
                     effective_on=effective.isoformat(), memo=memo, warnings=warnings, can_save=True,
                     confidence=0.9 if not warnings else 0.6, evidence=evidence, party=party, category=category)
        if kind == 'bill':
            draft.update(due_on=(effective + timedelta(days=7)).isoformat(), vendor_name=party or 'Supplier',
                         invoice_number=f'VOICE-{effective:%Y%m%d}-{len(drafts) + 1}')
        else:
            draft.update(direction='inflow' if kind == 'income' else 'outflow', status='cleared')
        drafts.append(draft)
    return drafts, dropped


def split_note(transcript, today, currency, digits, *, use_ai=True, deadline=None):
    """(drafts, dropped, method). The AI split is used when it yields at least as many checked drafts as the rules."""
    rules, rule_dropped = checked_drafts(rule_entries(transcript), transcript, today, currency, digits)
    if use_ai:
        found = ai_entries(transcript, deadline or time.monotonic() + 30)
        if found:
            drafts, dropped = checked_drafts(found[0], transcript, today, currency, digits)
            if drafts:
                # Anything the rule reader found that the AI left out is offered too, marked for checking.
                taken = {d['amount_minor'] for d in drafts}
                covered = ' '.join(d['evidence'] for d in drafts)
                for extra in rules:
                    if extra['amount_minor'] not in taken and not quoted(extra['evidence'], covered):
                        extra['warnings'].append('Found by the backup reader. Check it, or untick it if it is not a payment.')
                        extra['confidence'] = 0.5
                        drafts.append(extra)
                return drafts, dropped, 'ai'
    return rules, rule_dropped, 'rules'


# ---------- speech to text ----------
WHISPER_MODELS = ('whisper-large-v3', 'whisper-large-v3-turbo')
VOCABULARY = ('টাকা হাজার শো লাখ বিকাশ নগদ রকেট ভাড়া বেতন বিল বাকি বিক্রি খরচ দোকান মাল ডেলিভারি গতকাল পরশু আজ '
              'taka hajar bKash Nagad')


def _vocabulary(db, business):
    """Names the owner uses (suppliers and customers) help the speech engine spell them; at most a few dozen words."""
    names = set()
    try:
        ds = sec.original_dataset(db, business)
        names |= {i.vendor_id.replace('-', ' ') for i in ds.invoices[-60:]}
    except Exception:  # noqa: BLE001 - a hint only
        pass
    hint = VOCABULARY + ' ' + ' '.join(sorted(names)[:30])
    return hint[:600]


def whisper(audio, mime, language, hint):
    from api.app.market import groq_key
    key = groq_key()
    if not key:
        return None, 'groq: no key'
    reasons = []
    for model in WHISPER_MODELS:
        try:
            with httpx.Client(transport=TRANSPORT, trust_env=False, follow_redirects=False, timeout=60) as client:
                response = client.post('https://api.groq.com/openai/v1/audio/transcriptions',
                                       headers={'Authorization': 'Bearer ' + key},
                                       data={'model': model, 'language': language, 'temperature': '0', 'response_format': 'json',
                                             'prompt': hint},
                                       files={'file': ('note.' + ('ogg' if 'ogg' in mime else 'mp4' if 'mp4' in mime else 'webm'), audio, mime)})
            if response.status_code == 200:
                text = str(response.json().get('text') or '').strip()
                if text:
                    return text, model
            reasons.append(f'{model} {response.status_code}')
        except (httpx.HTTPError, ValueError) as error:
            reasons.append(f'{model} {type(error).__name__}')
    return None, '; '.join(reasons)


def gemini_transcript(audio, mime, language, hint):
    from api.app.market import GEMINI_MODELS, gemini_key
    key = gemini_key()
    if not key:
        return None, 'gemini: no key'
    ask = ('Transcribe this voice note exactly as spoken, in the language spoken ('
           + ('Bangla, write Bangla words in Bangla script' if language == 'bn' else 'English') +
           '). Write amounts as the speaker said them. Do not add, translate or summarise anything. '
           'Words that may appear: ' + hint)
    body = {'contents': [{'parts': [{'inline_data': {'mime_type': mime.split(';')[0], 'data': base64.b64encode(audio).decode()}},
                                    {'text': ask}]}], 'generationConfig': {'temperature': 0}}
    reasons = []
    for model in GEMINI_MODELS[:2]:
        try:
            with httpx.Client(transport=TRANSPORT, trust_env=False, follow_redirects=False, timeout=60) as client:
                response = client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                                       headers={'x-goog-api-key': key}, json=body)
            if response.status_code == 200:
                parts = response.json()['candidates'][0]['content']['parts']
                text = ''.join(p.get('text', '') for p in parts).strip()
                if text:
                    return text, model
            reasons.append(f'{model} {response.status_code}')
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as error:
            reasons.append(f'{model} {type(error).__name__}')
    return None, '; '.join(reasons)


def hf_transcript(audio, mime, language, hint):
    """Whisper large-v3 on Hugging Face's free inference, with the HF token Render already has."""
    import os
    key = (os.getenv('CAPZORYX_HISAB_HF_TOKEN') or os.getenv('HF_TOKEN') or '').strip()
    if not key:
        return None, 'hf: no key'
    try:
        with httpx.Client(transport=TRANSPORT, trust_env=False, follow_redirects=False, timeout=90) as client:
            response = client.post('https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3',
                                   headers={'Authorization': 'Bearer ' + key, 'Content-Type': mime.split(';')[0]}, content=audio)
        if response.status_code == 200:
            text = str(response.json().get('text') or '').strip()
            if text:
                return text, 'hf-whisper-large-v3'
        return None, f'hf {response.status_code}'
    except (httpx.HTTPError, ValueError, AttributeError) as error:
        return None, f'hf {type(error).__name__}'


def transcribe(audio, mime, language, hint):
    text, used = whisper(audio, mime, language, hint)
    if text:
        return text, used
    log.warning('voice note: whisper unavailable (%s)', used)
    text, used2 = gemini_transcript(audio, mime, language, hint)
    if text:
        return text, used2
    log.warning('voice note: gemini unavailable (%s)', used2)
    text, used3 = hf_transcript(audio, mime, language, hint)
    if text:
        return text, used3
    log.warning('voice note: hugging face unavailable (%s)', used3)
    return None, None


def speech_available():
    import os
    from api.app.market import gemini_key, groq_key
    return bool(groq_key() or gemini_key() or os.getenv('CAPZORYX_HISAB_HF_TOKEN') or os.getenv('HF_TOKEN'))


# ---------- routes ----------
class VoiceNote(Contract):
    audio_b64: str = Field(min_length=100, max_length=MAX_AUDIO_BYTES * 4 // 3 + 8)
    mime: str = Field(pattern=r'^audio/(webm|ogg|mp4|mpeg|wav|x-m4a|aac)(;codecs=[a-z0-9.]+)?$')
    language: str = Field(pattern=r'^(bn|en)$')
    consent: StrictBool


class NoteText(Contract):
    transcript: str = Field(min_length=2, max_length=MAX_TRANSCRIPT)
    consent: StrictBool = False  # may the note go to an AI service to be split (otherwise rules only)


def _owner_or_bookkeeper(actor):
    if actor.role not in ('owner', 'bookkeeper'):
        sec.fail(403, 'RECORDKEEPER_REQUIRED')


def _cloud_allowed(db, actor):
    from api.app.assist import owner_allows_cloud
    return owner_allows_cloud(db, actor.business_id)


@router.get('/voice-note')
def voice_note_status(actor=Depends(principal), db=Depends(db_connection)):
    return dict(speech=speech_available(), cloud_allowed=_cloud_allowed(db, actor), max_seconds=180, simulation_only=True)


@router.post('/voice-note')
def voice_note(body: VoiceNote, actor=Depends(principal), db=Depends(db_connection)):
    """Audio to text. The audio goes to the speech service and is not stored anywhere by Capzoryx."""
    _owner_or_bookkeeper(actor)
    if not body.consent or not _cloud_allowed(db, actor):
        sec.fail(403, 'VOICE_CONSENT_REQUIRED')
    sec.budgets(db, [('voice-note:' + actor.user_id, 6), ('voice-note-all', 30)])
    try:
        audio = base64.b64decode(body.audio_b64, validate=True)
    except (ValueError, binascii.Error):
        sec.fail(422, 'INVALID_VOICE_AUDIO')
    if not 1000 <= len(audio) <= MAX_AUDIO_BYTES:
        sec.fail(422, 'INVALID_VOICE_DURATION')
    with sec.transaction(db):
        hint = _vocabulary(db, actor.business_id)
    text, model = transcribe(audio, body.mime, body.language, hint)
    if not text:
        sec.fail(503, 'SPEECH_SERVICE_BUSY')
    return dict(transcript=text[:MAX_TRANSCRIPT], engine='whisper' if 'whisper' in model else 'gemini', simulation_only=True)


@router.post('/batch-drafts')
def batch_drafts(body: NoteText, actor=Depends(principal), db=Depends(db_connection)):
    """One checked draft per entry in the note. Nothing is saved here."""
    _owner_or_bookkeeper(actor)
    sec.budgets(db, [('batch-drafts:' + actor.user_id, 10)])
    with sec.transaction(db):
        ds = sec.original_dataset(db, actor.business_id)
        cloud = body.consent and _cloud_allowed(db, actor)
    from api.app.currencies import CURRENCIES
    digits = CURRENCIES[ds.currency]['digits']
    drafts, dropped, method = split_note(body.transcript.strip(), today_bd(), ds.currency, digits, use_ai=cloud)
    return dict(drafts=drafts, dropped=dropped, method=method, simulation_only=True)
