# Secrets Management

## Current Rule

- Root `.env` is the single local source of truth for production configuration and is ignored by git.
- `deploy.sh` filters deployment-only keys from root `.env` and writes the result to `backend/.env` on the server.
- Before every `deploy.sh -e`, backend deploy, or full deploy that syncs env, the server-side `backend/.env` is copied outside the Git worktree to `/var/backups/health-app/env/.env.YYYYMMDD_HHMMSS` (or `$HEALTH_BACKUP_ROOT/env`).
- Runtime `.env` and its backups are mode `0600`; backup directories are mode `0700`. The newest 20 env backups are retained.
- Database backups live under `/var/backups/health-app/database`, never under `/opt/health-app`, so Git synchronization cannot stash or remove them.
- Production backend deploys require a successful database dump, isolated restore drill, age-encrypted off-host upload, and remote listing verification before code synchronization starts.
- Do not print, paste, or commit secret values. Logs and tickets should mention key names only.

## Emergency Edits

Direct server edits should be limited to emergency recovery. After any emergency edit, copy the intended final value back into the local root `.env` before the next deploy, otherwise the next env sync will overwrite it.

## Rotation

- Rotate immediately after any suspected leak, accidental commit, or broad copy/paste exposure.
- Rotate LLM gateway, payment, OAuth, and health-data integration keys at least quarterly.
- Prefer creating a replacement key first, deploying it, verifying service health, then revoking the old key.

## Encrypted Off-Host Backup

Production must configure `BACKUP_AGE_RECIPIENT`, `BACKUP_OFFSITE_RCLONE_DEST`, and an independent random `BACKUP_INTEGRITY_KEY` of at least 32 characters. The destination must be an off-host object-storage remote configured in `rclone`; the private age identity must not be installed on the production host. Each archive carries a locally authenticated HMAC manifest binding its source hash, ciphertext hash, and object name, so coordinated replacement of the remote object and checksum is rejected. `BACKUP_OFFSITE_RETENTION_DAYS` defaults to 35 and local verified backup retention defaults to 7 copies. A missing tool, destination, recipient, integrity key, restore failure, upload failure, or failed hash/HMAC verification blocks deployment.

## Long-Term Direction

Phase 1 keeps the current root `.env` workflow but stores an encrypted backup in a human-managed vault such as 1Password or Bitwarden. The plaintext `.env` exists only on the operator machine and production server.

Phase 2 should move the source of truth to an encrypted file such as `ops/secrets.enc.env` managed with SOPS and age, or to 1Password CLI. `deploy.sh` can then generate the transient root `.env` locally before sync.

Phase 3 should use a production secret manager such as Infisical, Doppler, HashiCorp Vault, or the cloud provider secret manager. Deployments should fetch secrets just in time with audit logs, access control, and rotation history, while avoiding long-lived plaintext copies outside runtime hosts.
