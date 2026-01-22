# Security Procedures

## Required Secrets

Set these environment variables before starting the backend:

- `SECRET_KEY` (>= 32 characters)
- `GARMIN_ENCRYPTION_KEY` (optional, overrides derived key)
- `DEVICE_ENCRYPTION_KEY` (optional, overrides derived key)

## CORS Allowlist

Use a comma-separated allowlist:

```
CORS_ALLOW_ORIGINS=https://executor.life,https://health.executor.life
```

## Dependency Audits

Backend:

```bash
pip-audit -r backend/requirements.txt
```

Frontend:

```bash
npm audit --prefix frontend
```

## Audit Notes

- `pip-audit -r backend/requirements.txt` requires a Python version with prebuilt wheels for `psycopg2-binary`. If you see `pg_config` build errors on Python 3.13, rerun with Python 3.12 or use a build environment that provides Postgres dev headers.
- `pnpm audit` is the source of truth for workspace dependencies when using pnpm.
- Known unresolved advisories in the mini-program toolchain (from `pnpm audit`): `git-clone` and `html-minifier` have no patched versions even after upgrading to Taro `4.1.10`. Mitigation: avoid running `@tarojs/cli` in untrusted environments and prioritize upgrading the Taro toolchain when a fixed release is available.
- Allowlisted advisories for CI gate (see `scripts/pnpm-audit-allowlist.mjs`): `1088948` (got), `1093404` (git-clone), `1105440` (html-minifier). Remove entries when upstream fixes land.
