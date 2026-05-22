# Secrets Management

## Current Rule

- Root `.env` is the single local source of truth for production configuration and is ignored by git.
- `deploy.sh` filters deployment-only keys from root `.env` and writes the result to `backend/.env` on the server.
- Before every `deploy.sh -e`, backend deploy, or full deploy that syncs env, the server-side `backend/.env` is copied in the same directory as `.env.backup.YYYYMMDD_HHMMSS`.
- Server env backups keep file permissions restrictive and the script keeps the newest 20 backup files to avoid unbounded growth.
- Do not print, paste, or commit secret values. Logs and tickets should mention key names only.

## Emergency Edits

Direct server edits should be limited to emergency recovery. After any emergency edit, copy the intended final value back into the local root `.env` before the next deploy, otherwise the next env sync will overwrite it.

## Rotation

- Rotate immediately after any suspected leak, accidental commit, or broad copy/paste exposure.
- Rotate LLM gateway, payment, OAuth, and health-data integration keys at least quarterly.
- Prefer creating a replacement key first, deploying it, verifying service health, then revoking the old key.

## Long-Term Direction

Phase 1 keeps the current root `.env` workflow but stores an encrypted backup in a human-managed vault such as 1Password or Bitwarden. The plaintext `.env` exists only on the operator machine and production server.

Phase 2 should move the source of truth to an encrypted file such as `ops/secrets.enc.env` managed with SOPS and age, or to 1Password CLI. `deploy.sh` can then generate the transient root `.env` locally before sync.

Phase 3 should use a production secret manager such as Infisical, Doppler, HashiCorp Vault, or the cloud provider secret manager. Deployments should fetch secrets just in time with audit logs, access control, and rotation history, while avoiding long-lived plaintext copies outside runtime hosts.
