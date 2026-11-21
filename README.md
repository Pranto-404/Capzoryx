# Capzoryx website

Project start · 21 November 2026

Capzoryx helps a small business owner answer a practical question: will there be enough cash when the next bill comes due? The React app and FastAPI service keep records in the owner's workspace. Cash projections and loan comparisons use integer minor units. Recording a payment requires two people and never initiates a bank transfer.

## Run locally

Use Python 3.12 and Node.js 22 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r api/requirements.lock.txt
cp .env.example .env
python -c 'import secrets; print("SAFELEDGER_SIGNING_KEY=" + secrets.token_hex(32))' >> .env
set -a
source .env
set +a
python -m uvicorn api.app.main:app --host 127.0.0.1 --port 8000
```

Keep the private signing key across restarts. In a second terminal:

```bash
npm ci --prefix web
npm run dev --prefix web
```

Open http://127.0.0.1:5173, create an account and choose **Try a sample business** in the empty overview. The sample uses fictional transactions. Entering your own records also works without any cloud model key.

## Try the new features

- Under **Add records**, choose a bill photo. The device reads a labelled total and lets you check the amount, supplier and dates. You can also type a sentence such as “Rahman ke 4 lakh 20 hajar dilam kal”.
- On **Overview**, load the sample business. The cash-gap section shows how much of the scheduled receipt would need to arrive early to cover the fabric bill.
- Under **Activity**, an owner can publish a signed cash-flow passport once the signing keys are configured. Open its link to verify the signature, print a PDF or scan the QR. Revoking the link disables public verification.

## Verify a build

```bash
python -m pytest api/tests -q
npm run build --prefix web
node scripts/check_i18n.cjs
node scripts/extract_ui_strings.cjs --check
```

Vercel builds the website and installable web app at [capzoryx.vercel.app](https://capzoryx.vercel.app/) from the `web` directory on `main`. The Android build uses the same source and finance API. Local SQLite is sufficient for development. Hosted instances require a dedicated Turso database and a stable signing key. Deployment details and remaining product milestones are in [the build notes](docs/BUILD.md).
