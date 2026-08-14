# Production infrastructure baseline

The tracked files in this directory are the production security source of
truth. Internal services bind to loopback; only SSH, HTTP redirect/ACME and
HTTPS are public.

> **Current freeze (2026-08-12):** every repo-contained automatic remote/vendor release entrypoint,
> including server/Mac route installation, release upload/restart and recovery, is blocked. The same-UID
> repo bootstrap is not a trust boundary because Git refs/replace, shared info attributes plus local
> filters, hidden untracked import shadows, `BASH_ENV`, and `PYTHONPATH`/`sitecustomize` can alter
> execution. A manual **release** Gate means STOP/BLOCK. Re-enable only through a new dossier and a repo-external
> root-owned launcher with a fixed interpreter, `env -i` allowlist, canonical Git archive/tree
> materialized outside the repo, source/artifact/recovery proof, and a new independent G4. G5/G6
> and App Store submission remain BLOCKED. Server-local setup/admin utilities are a distinct manual
> admin Gate: they may run only on the production host in an explicitly authorized, audited event,
> and no automatic release entrypoint may call them.
> Repo shell rc78 is only an ordinary-invocation tombstone because `BASH_ENV` and caller-defined
> `exit`/`builtin` functions can alter bootstrap. Retained writer legacy must be literal-false and
> syntactically unreachable; runtime/operator paths cannot source/extract/eval it. Isolated marker
> fixture extraction is protocol testing only and is not release proof. `release-dmg.sh` is wholly
> frozen and cannot serve as a checker.

The following block documents a manual-admin provisioning event for a new, empty host only. It is
not a release command and may be used only with explicit host/admin authorization, resolved targets,
and audit/recovery evidence; an automatic release entrypoint must never invoke it. Never paste it
over an existing production virtual host: production Mac routes are installed
only by the guarded bootstrap transaction described below. Install the systemd
units only after creating the locked service account and writable directories:

```bash
sudo useradd --system --home /opt/health-app --shell /usr/sbin/nologin health-app
sudo install -o root -g root -m 0755 -d /opt/health-app/backend/data
sudo install -o root -g root -m 0755 -d /var/lib/health-app
sudo install -o root -g root -m 0755 -d /var/cache/health-app
sudo install -o root -g root -m 0700 -d /var/lib/health-app/release-state
sudo install -o health-app -g health-app -m 0700 -d \
  /var/lib/health-app/uploads \
  /var/lib/health-app/runtime \
  /var/lib/health-app/dedao-kbase \
  /var/lib/health-app/dedao-kbase/workspace \
  /var/lib/health-app/dedao-kbase-review \
  /var/cache/health-app/skills-hub
sudo chown root:health-app /opt/health-app/backend/.env
sudo chmod 0640 /opt/health-app/backend/.env
sudo install -m 0644 infra/systemd/*.service infra/systemd/*.socket \
  /etc/systemd/system/
sudo install -o root -g root -m 0755 -d /etc/nginx/conf.d /etc/nginx/snippets
sudo install -o root -g root -m 0644 infra/nginx/health.executor.life.conf \
  /etc/nginx/conf.d/health.executor.life.conf
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now health-backend.socket health-backend.service \
  celery-worker.service celery-beat.service
sudo bash infra/firewall/apply-ufw.sh
```

`backend/data` contains version-controlled seeds and remains readable but
immutable to `health-app`. User uploads live under
`/var/lib/health-app/uploads` while the candidate is authoritative. The release
transaction merges legacy checkout uploads into that directory without
overwriting conflicts. When the old writers still use legacy uploads, preflight
requires the external tree to be absent or empty; a non-empty external tree has
no authoritative provenance and blocks the release without being deleted.
After prepare, an interrupted external copy is accepted only when every present
path, kind, and file hash is a subset of the sealed legacy manifest. The
transaction verifies the complete destination and then retires the legacy tree.
Before every initial or resumed retirement, the remaining source must be a
deletion-only subset of its sealed manifest with unchanged uid, gid, mode, kind,
and file hash. New, modified, type-changed, or permission-changed source entries
block the transition and are preserved. An old-SHA rollback copies the exact
external tree (including
candidate-window additions and deletions) back to the checkout, verifies it,
and then retires the external tree only when the old effective backend and
worker still identify the checkout as their upload authority. Once an old
release already uses the external tree, rollback keeps that external authority
in place. The transaction derives this choice from both writers' effective
`ReadWritePaths` and rejects disagreement. Thus only the active SHA's upload
tree remains after either transition; the root-only in-flight snapshot is
reaped by terminal cleanup. Skills Hub's
rebuildable cache lives under `/var/cache/health-app/skills-hub`; production
skill install/uninstall never writes the tracked checkout. Celery Beat's
mutable shelf is created by
`StateDirectory=health-app/celery-beat` under
`/var/lib/health-app/celery-beat`; do not place mutable scheduler state back in
the checkout. Mutable gene/legacy-vector data lives under
`/var/lib/health-app/runtime`; Dedao review workspace lives under
`/var/lib/health-app/dedao-kbase/workspace`. The root-only
`/var/lib/health-app/release-state` directory holds crash-recoverable deployment
journals and must not be cleaned by routine release scripts.

Do not expose PostgreSQL, Redis, FastAPI, Next.js, MCP, Prometheus, Grafana or
Node Exporter directly to the Internet. Remote operator access must use SSH
port forwarding or an authenticated VPN.

## One-time Mac download route bootstrap

> **Frozen:** automated Mac route apply/rollback currently returns 78 before lock or SSH. The
> commands below document the reserved protocol only; do not execute or bypass them until a new
> dossier, recovery proof and independent G4 explicitly re-enable this writer.
> Direct nginx/Mac Python production CLI is frozen too. Protocol tests require strict non-root,
> explicit test mode and paths wholly beneath fixed non-production roots (macOS `/private/tmp` or
> `/private/var/folders`; `/tmp` elsewhere, ignoring caller `TMPDIR`). Local `create-candidate`
> requires the same isolation, emits metadata only and cannot touch nginx or production state.

The future formal Mac release needs `/mac/current.json` and immutable
`/mac/releases/<source-sha>/<artifact-sha>.dmg` routes in the active production
virtual host. They are not installed by any current path. The reserved bootstrap identifier returns
78 and is intentionally omitted as a copyable command.

The command uses the unified local and remote release locks, a fixed production
host and pinned SSH key. On an older live config it inserts one include into the
real `/etc/nginx/conf.d/health.executor.life.conf`; on the tracked baseline it
recognizes the already-installed exact include without rewriting it. The
managed snippet lives at
`/etc/nginx/snippets/reva-mac-release-routes.conf`. Both paths preserve the existing
`/xiaoba-mac.dmg` location byte-for-byte. Root-owned receipts, journals and
backups live under `/var/lib/health-app/mac-nginx-bootstrap` (mode `0700`),
outside nginx include roots. The transaction validates `nginx -t`, reloads and
checks nginx active state, verifies route markers/statuses, and proves the
legacy DMG HTTP hash is unchanged. A failed activation restores the exact prior
files; an interrupted operation is reconciled from its journal on the next run.

The reserved route-rollback identifier also returns 78. There is no raw nginx/SSH fallback.

This is only a pre-first-formal-release escape hatch. It is rejected before reading or mutating nginx
when any formal Mac current/previous receipt, transaction journal, or public current manifest exists.
After a formal release, use the Mac release recovery/rollback commands; never remove its routes.
This transaction does not inspect, rewrite or remove duplicate server configs. If the required legacy
anchor or target metadata is not exact, it fails closed.

## Formal Mac Developer ID release

> **Frozen:** publish/recover/rollback are not active production paths. Protocol files and tests do
> not establish a live Mac release.

The future publisher requires a trustworthy materialized source; a clean checkout matching
`origin/main` is not sufficient. The reserved publish identifier currently returns 78.

The transaction signs and notarizes locally, verifies the mounted DMG, installs immutable bytes,
then advances current/stable through a journaled crash-recoverable sequence. Each pointer is
replaced atomically; terminal proof requires the receipt, current manifest and stable route to agree.
If SSH, a signal, or final public proof is
ambiguous, do not rerun publish or delete the root-only
`/var/lib/health-app/release-state/deploy.lock`; reconcile the retained exact
transaction first through a future independently approved recovery path. The current recovery
identifier returns 78 and must not be bypassed.

Future rollback must restore the previous verified receipt while preserving the monotonic
version/build high-water mark. The current rollback identifier returns 78.

Successful G5/G6 verification requires the root-owned private receipt/disk identity and matching
public HTTPS bytes at `/mac/current.json`, the content-addressed URL in that manifest, and
`/xiaoba-mac.dmg`. The response markers, manifest fields, byte size and SHA-256 must all agree.

Current G5/G6 are BLOCKED because no automatic production release entrypoint is authorized.
Re-enable route/Mac/server release entrypoints only through a new dossier and repo-external
root-owned launcher with fixed interpreter,
`env -i`, canonical archive/tree materialization outside the same-UID writable repo, and independent
G4 approval.
