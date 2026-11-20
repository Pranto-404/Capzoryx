# Build notes · 21 November 2026

## Release scope

The application baseline includes owner accounts, two-step sign-in, workspace sharing, manual records, a Bangla/Banglish text parser, 7- and 30-day forecasts, loan comparison, PDF reports and an append-only audit trail. The team’s MIT-licensed components are included under LICENSE. This repository has its own release history. The date on a synthetic transaction is a financial test input.

## Staging

Use the repository root on Vercel and branch v2 on Render. The frontend sends same-origin /api requests to the designated Render service. Configure SAFELEDGER_CORS_ORIGINS and SAFELEDGER_PUBLIC_URL with the exact new frontend origin. The service starts via bash render_start.sh. Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN for a new database and provide a stable SAFELEDGER_SIGNING_KEY of 64 lowercase hex characters. Keep secrets in the service dashboard.

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
