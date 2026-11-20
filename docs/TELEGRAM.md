# Optional Telegram summaries

In-app alerts work without a bot. To activate Telegram, give the API a dedicated bot token, bot username and random webhook secret using `SAFELEDGER_TELEGRAM_BOT_TOKEN`, `SAFELEDGER_TELEGRAM_BOT_USERNAME`, `SAFELEDGER_TELEGRAM_WEBHOOK_SECRET` and `SAFELEDGER_TELEGRAM_ENABLED=1`. Use a secret of 32–256 ASCII letters, numbers, underscores or hyphens. Register the HTTPS `/api/channels/telegram` endpoint with Telegram's setWebhook method and its secret_token field. `SAFELEDGER_PUBLIC_URL` must point to the workspace website.

An owner opens Settings, requests a five-minute code, starts the private bot chat, verifies the displayed account and confirms delivery. The scheduler publishes generic morning and Sunday notices. Sending /stop or disconnecting in Settings cancels the link and queued notices. The webhook accepts private link and stop commands. Financial records can be entered in the authenticated app.
