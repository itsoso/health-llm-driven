# Production infrastructure baseline

The tracked files in this directory are the production security source of
truth. Internal services bind to loopback; only SSH, HTTP redirect/ACME and
HTTPS are public.

Install the systemd units only after creating the locked service account and
writable directories:

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
sudo install -m 0644 infra/nginx/health.executor.life.conf \
  /etc/nginx/sites-available/health.executor.life
sudo ln -sfn /etc/nginx/sites-available/health.executor.life \
  /etc/nginx/sites-enabled/health.executor.life
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
