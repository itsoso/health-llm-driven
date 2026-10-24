# Edu identity activation on Health

This operation activates only the Health issuer. The Edu host, existing Edu owner mapping,
credential revocation, and browser/native acceptance remain separate operations.

Publish the reviewed issuer backend first and verify its exact `SUCCEEDED` revision.
Publish the `/connect/edu` frontend with its strict-origin metadata, exact Edu form-action,
and no-store response. Install the reviewed canonical publisher with exact current-main
CI and independent safety approval. Activation rejects different installed issuer code,
unknown authentication configuration, stale authorization, and an occupied release lease.

Use the canonical `deploy.sh --activate-edu-login` entry with exact `--publisher-sha`,
`--production-sha`, and the explicitly confirmed positive Health `--owner-id`.
Stdin is a bounded JSON object containing only `owner_token` and `shared_secret`.
The owner token may be an existing opaque non-proxy Health API credential or a
personal Health session JWT. JWTs are verified by the installed Health decoder in a
health-app subprocess, via stdin only; expired or proxy-bearing claims are rejected. The live
identity and read-only database check must both match the explicit approved, active,
non-managed owner. The shared secret must be a newly provisioned dedicated 64-character
lowercase hexadecimal secret, securely delivered to both hosts. Do not put either value
in arguments, shell history, logs, or source. Use a protected operator input source.

Without `--apply`, the command performs read-only readiness checks. With `--apply`, it
acquires the release lease, journals original configuration digests, atomically writes
only the five fixed `EDU_SSO_` settings, restarts Health, checks effective process settings
and readiness, verifies owner identity and anonymous endpoint rejection, then records
`CONFIGURATION_SUCCEEDED`. No previous configuration, code, or secret copy is created;
only the secret digest is stored in the journal, with the active secret in the runtime env.
Unrelated environment bytes, owner/group and permissions are preserved.

On an unknown outcome, keep the lease and journal. Inspect the protected state and use
`--resume --apply` with the original revision, owner and secret binding. Never remove the
lease, rotate the secret, or start another operation to bypass uncertainty. A resumed
write/restart uses the original intended state; unexpected configuration drift is rejected.
An incomplete lease setup or teardown needs operator investigation and is not silently
reconstructed. Completion is configuration proof only; separately verify the existing
Edu data, browser login and the installed App with Health credentials before claiming cutover.
