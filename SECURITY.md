# Security and data handling

Capzoryx stores financial records and owner-confirmed receipts in a workspace. Signed audit events and historical dataset revisions remain available after an archive. Older signed audit events can contain plaintext record notes. New cash notes are encrypted separately and their keyed digests are included in the signed audit. Historical invoice memos can also appear in immutable dataset snapshots. Avoid entering personal identification numbers, bank passwords or unrelated personal details.

Customer names and optional reminder phones use a per-workspace encryption key. Clearing a workspace with explicit confirmation destroys its customer key and removes stored phone contacts in the active database. Any previously downloaded exports and retained provider backups have their own retention periods.

## Audit verification

Financial writes verify the suffix following the latest signed workspace checkpoint. Checkpoints reference an immutable audit row and are created after at least 32 newly verified events. Database triggers flag historical edits, backfills and deletions. Full workspace and audit exports still verify every event. Keep independently protected database backups and signed exports for recovery from a database rollback.

## Model providers

Smart assist starts off. The settings screen identifies configured providers and the data classes each one may receive. Owners who had enabled the older policy are asked to review it again. A compatible private provider needs explicit confirmation of free service and no-training terms before it can receive records. Aggregator models marked `:free` receive public UI text only. Public UI translations use an account with a verified hard free quota. Keep credentials unset when the terms or hard limits cannot be confirmed.

Hisab-LM can run through an explicit loopback `/v1` URL. List a task in `SAFELEDGER_LOCAL_LLM_TASKS` only after evaluating that exact model for that task. A local model endpoint, verified provider credentials and any hardware must be provisioned separately.

The gateway reserves a daily inference allowance atomically, uses bounded calls and opens a provider circuit for five minutes after three failures within a minute. Telemetry stores a keyed workspace hash, trace, task, provider, model, usage and latency. Prompts, answers and provider keys are excluded from telemetry. The process can reuse a matching explanation for the same workspace for up to a day. Extraction results are never cached.

Follow the incident steps for suspected signing-key exposure. [Incident response](docs/INCIDENT.md)

## AI quality

Workspace owners can open AI quality under Settings → Data to review aggregate model usage and the current synthetic evaluation reference. The administrative cross-workspace endpoint requires an independently configured `SAFELEDGER_ADMIN_TOKEN` of at least 32 characters sent in the `X-Capzoryx-Admin-Token` header. Without that header, `GET /api/admin/ai-quality` requires an owner session and returns that workspace's traces only. Never store the administrative token in a frontend bundle.

Refresh the published aggregate reference using `scripts/quality_reference.py` with the matching local smoke, candidate evaluation and training reports. The table includes sample counts and dataset checksums. Synthetic regressions and self-generated training examples cannot establish accuracy on independent shopkeepers' data.
