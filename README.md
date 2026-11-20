# Capzoryx

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

## Verify a build

```bash
python -m pytest api/tests -q
npm run build --prefix web
node scripts/check_i18n.cjs
node scripts/extract_ui_strings.cjs --check
```

The development branch is `v2`. Local SQLite is sufficient for development. Hosted instances require a dedicated Turso database and a stable signing key. Deployment details and remaining product milestones are in [the build notes](docs/BUILD.md).
