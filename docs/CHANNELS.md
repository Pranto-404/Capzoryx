# Chat channels: Telegram, WhatsApp and in-app chat

All three use one conversation brain in `api/app/chat/`:

- `understand.py` turns a message into a topic (balance, income, expenses, payables, receivables, forecast,
  summary), a time window, modifiers (overdue, "who/list"), small talk, or a cash-entry draft. It reads Bangla,
  Banglish and English, tolerates one-letter typos, and replies in the language the owner used.
- `brain.py` gets every figure from the deterministic finance engine (`copilot/books.compute`), remembers the last
  topic for six hours so "ar goto mashe?" works, and formats taka the Bangladeshi way (৳12,50,000).
- Cash entries from chat are drafts. They are saved only when the owner has turned on **chat entries** in Settings
  and taps **Save** for that entry. Every save goes through the normal append-only, audited record path.
- `llm.py` handles open conversation the brain cannot answer, like a person would: the team's own Hisab-Chat model
  first (`ml/hisab_chat/`), then free API tiers in order — Groq, Gemini, Cerebras, OpenRouter, Mistral, GitHub
  Models. Set any subset of `CAPZORYX_CHAT_<NAME>_KEY` (and `CAPZORYX_CHAT_HISAB_URL`). A provider that hits its
  quota rests for 10 minutes. Replies are capped at `CAPZORYX_CHAT_MAX_TOKENS` (300) and any reply that states an
  amount not found in the owner's facts or message is thrown away. Ledger facts go only to the own model, or to
  cloud providers when the owner turned on smart assist.
- The last six turns are kept, sealed with the workspace key, for six hours so follow-ups have context.

## Telegram

Already live. After a deploy the API re-registers the webhook with `message` and `callback_query` updates so the
inline Save/Cancel/List buttons work. Morning reminders become a short figure summary only for owners who turned on
book replies; otherwise they stay detail-free.

## WhatsApp (Meta WhatsApp Cloud API)

1. In Meta for Developers create an app → add **WhatsApp**. Note the **Phone number ID** and add a real business
   number (or use the test number while developing).
2. Create a **permanent access token** for a system user with `whatsapp_business_messaging`.
3. Copy the app's **App secret** (App settings → Basic).
4. On the Render API service set:
   `SAFELEDGER_WHATSAPP_ENABLED=1`, `SAFELEDGER_WHATSAPP_TOKEN`, `SAFELEDGER_WHATSAPP_PHONE_ID`,
   `SAFELEDGER_WHATSAPP_APP_SECRET`, `SAFELEDGER_WHATSAPP_VERIFY_TOKEN` (any random 16+ characters) and
   `SAFELEDGER_WHATSAPP_NUMBER` (the business number, digits only, e.g. `8801XXXXXXXXX`).
5. In WhatsApp → Configuration set the callback URL to `https://capzoryx.vercel.app/api/channels/whatsapp`
   (or the Render URL) with the same verify token, then subscribe to the **messages** field.
6. In Capzoryx: Settings → WhatsApp → Connect WhatsApp. WhatsApp opens with `LINK XXXXXXXX` filled in; the owner
   taps Send and the chat is connected. Settings updates by itself.

Replies are sent inside WhatsApp's free 24-hour customer-service window. Scheduled reminders are not sent on
WhatsApp because business-initiated messages need paid templates.

## Connecting is one step

Settings → Connect opens the chat app. On Telegram the code travels in the `/start` link; on WhatsApp the owner taps
Send on the prefilled message. The single-use code (5 or 10 minutes) came from the signed-in owner's page, so the
chat is linked immediately with book replies on. Chat entries stay off until the owner turns them on.

## Payment SMS (bKash, Nagad, Rocket, banks)

Settings → Payment SMS → Set up SMS forwarding gives a secret link. Install a free Android SMS forwarder (for example
"SMS to URL Forwarder"), add a rule for bKash, Nagad, Rocket and bank senders, and paste the link. Each message is
parsed by `services/wallet.py`; OTP/PIN and promotional messages are dropped without being stored. A clear payment
becomes a pending draft, the owner gets a Telegram message with Save/Skip, and Settings lists it too. Nothing reaches
the ledger before Save, and a double tap cannot save twice.

## Tests

`api/tests/test_chat_brain.py`, `test_chat_llm.py`, `test_telegram_channel.py`, `test_whatsapp_channel.py`, `test_sms_inbox.py`.
