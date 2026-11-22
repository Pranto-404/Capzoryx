# Chat channels: Telegram, WhatsApp and in-app chat

All three use one conversation brain in `api/app/chat/`:

- `understand.py` turns a message into a topic (balance, income, expenses, payables, receivables, forecast,
  summary), a time window, modifiers (overdue, "who/list"), small talk, or a cash-entry draft. It reads Bangla,
  Banglish and English, tolerates one-letter typos, and replies in the language the owner used.
- `brain.py` gets every figure from the deterministic finance engine (`copilot/books.compute`), remembers the last
  topic for six hours so "ar goto mashe?" works, and formats taka the Bangladeshi way (৳12,50,000).
- Cash entries from chat are drafts. They are saved only when the owner has turned on **chat entries** in Settings
  and taps **Save** for that entry. Every save goes through the normal append-only, audited record path.
- A language model is used only for questions the brain cannot answer, only if the owner turned on smart assist and
  a provider is configured, and with a short reply cap (`SAFELEDGER_CHAT_MAX_TOKENS`, default 220).

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
6. In Capzoryx: Settings → WhatsApp → Connect WhatsApp. The owner sends the prefilled `LINK XXXXXXXX` message and
   confirms the number on the website.

Replies are sent inside WhatsApp's free 24-hour customer-service window. Scheduled reminders are not sent on
WhatsApp because business-initiated messages need paid templates.

## Tests

`api/tests/test_chat_brain.py`, `test_telegram_channel.py`, `test_whatsapp_channel.py`.
