# Build notes · 21 November 2026

## Release scope

The application baseline includes owner accounts, two-step sign-in, workspace sharing, manual records, a Bangla/Banglish text parser, 7- and 30-day forecasts, loan comparison, PDF reports and an append-only audit trail. The team’s MIT-licensed components are included under LICENSE. This repository has its own release history. The date on a synthetic transaction is a financial test input.

## Staging

For the public website, import the repository root into Vercel and select main as its production branch. Develop the installable app on v2. The existing free Render staging API follows v2 and serves both clients. The frontend sends same-origin /api requests to the designated Render service. Configure SAFELEDGER_CORS_ORIGINS and SAFELEDGER_PUBLIC_URL with the exact new frontend origin. The service starts via bash render_start.sh. Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN for a new database and provide a stable SAFELEDGER_SIGNING_KEY of 64 lowercase hex characters. Keep secrets in the service dashboard.

The pilot uses a sleeping Render free instance. Keep-alive workflows consume shared instance hours. The React build, local parser and financial calculations need no API credits. Smart assist starts off. Leave cloud credentials, translation billing and paid fallback unset on the free pilot. Stop at free-tier limits.

Before live testing, compare /api/health build_commit with the staged Git commit and verify /api/ready reports libsql. Use disposable synthetic workspaces for deployment checks.

## Plan audit

The idea document’s five-hour demo and the plan book’s 310-hour roadmap have different completion criteria. A PDF export alone cannot substantiate a signed passport. A text parser alone cannot substantiate speech accuracy or a newly trained model. Evaluate each added capability independently.

| Package | Acceptance evidence |
| --- | --- |
| Capture and speech | Extract a draft, review the amount and counterparty, and persist only after confirmation. Evaluate voice on 30 consented or synthetic clips. |
| Gap-fixer | Simulate changes against the same dated movements, exclude protected obligations and retain source IDs. Report cases where the reserve cannot be restored. |
| Passport | Sign aggregate-only payloads and verify signature, expiry and revocation from a phone. |
| AI gateway and models | Enforce data classes and provider terms, evaluate held-out examples, publish measured scores before enabling model routes. |
| PWA and Android | Test installed shell, offline drafts, logout cleanup and duplicate-free replay. Qualify the Android package on a device. |
| Receivables and alerts | Link settlements to ledger inputs atomically, enforce role checks and verify time zones, quiet hours and reminder deduplication. |

The release checklist includes organizer confirmation of code-reuse rules before any event submission.

## Implemented in this build

- **Photo capture** reads printed English or Bangla bills locally with Tesseract. The worker, OCR engine and language data are served by the frontend. A clearly labelled total becomes an editable draft. Conflicting totals and incompatible currencies require manual review.
- **Text and dictation** support combined lakh/hajar amounts and tense-aware dates. Compatible browsers can use an installed on-device speech pack. The 30-clip voice accuracy gate and Android device test are pending.
- **Customer receivables (WP29)** are available to owners under Invoices. Record a debt once, then confirm each partial or full receipt against it. The receipt adds one cleared cash inflow and reduces the projected amount by the same value. Names and optional reminder numbers are encrypted using a random workspace key. Clearing the workspace erases its customer key and contact rows. Financial records can still be restored for 30 days.
- **Cash-gap planning** simulates advancing part of one scheduled receipt to the first shortfall date. Options show the amount, source record and remaining maximum gap. A receipt returns to its original baseline on its due date. These are projections.
- **Cash-flow passports** can be issued and revoked by an owner in Activity. The link and printable QR identify an aggregate report. The verifier checks the Ed25519 signature, expiry and revocation. Signer configuration uses SAFELEDGER_PASSPORT_ACTIVE_KEY and SAFELEDGER_PASSPORT_KEYS. The public key map is shipped in web/public/.well-known/capzoryx-passport-key.json. Keep retired public keys until all links signed with them expire.
- **Phone installation (WP11)** includes Add bill and Ask shortcuts, a network-first shell and local offline entry. Reviewed drafts sync on app open or reconnection only to the same owner, workspace and currency. Android shared text opens a review screen. API responses stay outside Cache Storage. Signing out clears stored drafts, shares and cached assets. Run the production web build, then `node scripts/check_pwa.cjs` with Playwright Chromium and the API Python environment. The OS share picker still needs a device or emulator check.
- **Cloud privacy** starts with Smart assist off. The on-device parser and bill reader work without an account at an AI provider. Remote extraction and planning require a compatible provider explicitly cleared for free, no-training processing. The staging service has no AI billing credentials.

## Free-tier release gates

The staging API belongs to the Mahin_404 workspace, in Singapore. Its frontend rewrite targets https://capzoryx-staging-api.onrender.com. Keep production and staging credentials separate. Configure a new Turso database before sending any staging traffic. A local keypair can be used in a separate development checkout by replacing the public key map and setting the corresponding private key through the environment.

Keep main protected with pull requests and the backend, frontend and dependency-audit CI jobs. Verify branch protection in the repository settings. Publish model scores, mobile speech claims and native-app distribution only after their device and dataset gates pass.
