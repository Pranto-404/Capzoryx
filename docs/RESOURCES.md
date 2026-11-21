# Free service configuration

| Use | Resource | Configuration |
| --- | --- | --- |
| Website | Vercel Capzoryx, branch main | Project root directory `web`. The public website is https://capzoryx.vercel.app. |
| Installable app | Vercel capzoryx-app, branch v2 | Repository root. The app is https://capzoryx-app.vercel.app. Android signing and installation instructions are in the v2 resource guide. |
| Live API | Render capzoryx-staging-api | Despite its historical service name, this service and its Turso database serve the live website and app. Synthetic tests run locally or against an isolated QA origin. |
| QA | Vercel capzoryx-qa and Render capzoryx-qa-api | Dedicated API on the free Singapore instance. Supply its own Turso URL/token and independent signing key. Verify the deployed commit and libSQL readiness before starting its 24-hour soak. |
| Model evaluation | Local CPU | The browser parser and deterministic finance engine work without external keys. Train the optional tagger locally. Independently written samples can be collected at /field-kit/index.html. |
| Optional QLoRA | Owner’s local RTX 5060 Ti, or a free CUDA notebook | Compare the base models on the validation split before tuning. Use the final test split after selection. Keep weights, model credentials and private evaluation files outside the public repository. |
| Optional notifications | Cloudflare Workers Free and GitHub Actions | Set separate staging and live tick secrets using the deployment instructions in infra/notification-tick. New alerts are readable in Activity. |
| Optional delivery | VAPID, Firebase or Telegram | Configure only a channel chosen by the owner. Device and recipient consent are required before delivery. |

The hosted app does not require a paid AI key, paid SMS, a Student Pack, or a Play Store account. Student benefits and any free GPU quota are personal account entitlements. The owner can claim them through the relevant provider if eligible. Retain the free plan when quotas run out.

## Isolated staging

1. Create a free database named `capzoryx-qa` in the owner's Turso organization. In its dashboard, copy its own libSQL URL and create a token scoped to that database.
2. Put the values in the QA Render service as `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. Save the environment and deploy branch v2. Keep the existing website's secrets in its own service.
3. Use the QA frontend to check `/api/health` for the candidate commit and `/api/ready` for `libsql`. The QA scheduler, API, and test workspace must all use these isolated resources.
4. Run a full 24-hour soak with synthetic records, verify the notification schedule and perform the rollback drill before claiming production qualification.

For seasonal cash-planning alerts, Pohela Boishakh uses 14 April in Bangladesh. The operator can supply locally agreed Eid planning dates as comma-separated ISO dates in `CAPZORYX_EID_PLANNING_DATES`. Active workspaces receive one owner inbox reminder 30 days before each event.
