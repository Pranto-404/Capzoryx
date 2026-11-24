# Capzoryx Copilot: competition brief

**Idea.** A multilingual AI that spots a small business's cash crunch early and helps fix it. It reads bills, messages
and voice notes, forecasts cash gaps and proposes rescue plans.

**Direction.** Multi-entry voice capture and batch drafting.

## Challenge 1: a whole week of spending in one voice note, every entry a separate draft

Where: **Add records → Voice note** (website, installed app and Android app).

1. **Record** up to 3 minutes (opus, about 32 kbps), or type or paste the note. Live browser dictation is the fallback
   when recording is not possible.
2. **Speech to text.** The note goes to **Whisper large-v3** on Groq (free tier); `whisper-large-v3-turbo` and then
   Gemini audio are tried if it is busy. The engine gets a hint list of Bangla money words and the workspace's
   supplier names, so names and "hajar" come out right. The transcript is shown and the owner can correct it. The
   audio is not stored. (`api/app/voice_batch.py`)
3. **Split into entries.** An AI model splits the transcript. Nothing it returns is trusted until it passes these
   checks:
   - every entry must quote words that are really in the note;
   - its amount must be a number actually said. Digits, Bangla digits and number words in Bangla, Banglish and
     English are understood: "dui hajar pachsho", "দেড় হাজার", "sare tin hajar", "2.5k", "1,20,000";
   - the date is worked out on the server from what was said: "aj", "gotokal", "porshu", "3 din age", "shombar",
     "শুক্রবার", "Sunday". A sentence with no day belongs to the day said before it.

   Entries that fail are listed as "not turned into drafts", with the reason. A second, rule-based reader always
   runs too. It makes the drafts when no AI service answers, and it adds anything the AI missed, marked "check".
   Self-corrections ("na na, 600") keep the corrected amount and are flagged for a second look.
4. **Batch review.** One card per entry: type (paid, received, bill still to pay), amount, date and note. Each can be
   edited or unticked. Totals are shown before saving.
5. **Save all, atomically.** `POST /api/workspace/records/batch` adds every chosen record in one transaction (all or
   none). It is safe to retry: sending the same batch again is recognised and not saved twice.

Tests: `api/tests/test_voice_batch.py` (29 cases) and `scripts/check_voice_batch_browser.cjs` (a real browser on a
phone-sized screen: one note becomes 5 drafts, one is edited, one unticked, and 4 are saved together).

## Challenge 2: the cash radar stays honest when a customer pays late

Where: **Overview** and **Cash flow → Cash radar**. Logic is in `api/app/services/radar.py`.

- **Learns habits.** For each customer, the median number of days they paid after the due date. With fewer than two
  payments it uses the business-wide habit; with no history, the due date.
- **Realistic dates.** Each open invoice is expected on due date + habit. Money later than the customer's habit is
  marked "later than usual". Money more than 30 days overdue *and* two weeks past the habit is "doubtful" and is not
  counted as arriving tomorrow.
- **Three outlooks, side by side:** everyone pays on the due date (the plain forecast), realistic, and "late money
  does not come".
- **Alert levels:**
  - **Alert** only when the *realistic* outlook falls below the safety reserve within 14 days.
  - **Watch** (in the app, no notification) when only the stress case does. The radar names the customers it depends
    on.
  - **All clear** otherwise.
- **No crying wolf:**
  - An alert is sent once per episode. It is sent again only if the shortfall comes at least 3 days earlier, grows by
    25% or more, or a week has passed. The episode closes when the shortfall disappears, for example when the late
    customer pays.
  - Overdue reminders start only after a customer is later than their own usual habit.

Tests: `api/tests/test_radar.py`. They cover:
- a late payer moving a real shortfall into view;
- slightly late money giving a quiet watch, not an alarm;
- long-overdue money not being counted;
- one alert per episode;
- no nagging within a customer's habit.

## Demo script (3 minutes)

1. Sign in, open **Add records**, tap **Record a voice note** and say:
   "Shombar dokan bhara 5000 taka dilam, tarpor transport e 300. Budhbar Rahim theke 12 hajar pelam. Shukrobar biddut
   bill 1,850. Aj chaa nasta 250."
2. Show the transcript, then **Make drafts**: five cards, with dates worked out from the weekdays.
3. Correct one amount, untick one, then **Save 4 records**. The balance and forecast update at once.
4. Open **Cash flow → Cash radar**. Show the three outlooks and the customer list ("usually pays 8 days late →
   expected 2 Dec").
5. Explain the alert rule: alert only on the realistic outlook, once per episode; a late payer within their habit is
   not chased.

## What the server needs

- `CAPZORYX_CHAT_GROQ_KEY`: Whisper speech to text and the AI splitter (free at console.groq.com).
- Optional backups: `CAPZORYX_CHAT_GEMINI_KEY` and the other free keys in `docs/AI_KEYS.md`.
- Smart assist must be on in the workspace before a recording or a note is sent to these services. Without it, typed
  notes are split by the rule-based reader on the server.
