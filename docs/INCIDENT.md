# Suspected key exposure

1. Set `SAFELEDGER_READ_ONLY=1` on the affected API and restart it. Confirm a normal read returns successfully and a harmless empty POST returns HTTP 503 with `READ_ONLY_MODE`. Logout remains available. Already running requests can finish during deployment.
2. Preserve a private database snapshot and an owner-authorized workspace audit export with the time and chain head. Record which environment, key and providers could have been affected. Treat the snapshot and export as sensitive.
3. Revoke affected sessions using an authorized administrative database connection. Revoke exposed external provider credentials at their issuer. Keep private values out of incident reports.
4. Obtain the owner's recovery decision. In-place replacement of `SAFELEDGER_SIGNING_KEY` breaks historical audit verification, TOTP secrets, customer key unwrapping and pending email codes. Rehearse recovery with an isolated copy and a key-versioned migration before replacing that key.
5. Verify audit integrity, sign-in, permissions and cash reconciliation against the isolated copy. Restore write access only after the owner accepts the recovery evidence.
