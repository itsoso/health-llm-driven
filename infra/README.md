# Production infrastructure baseline

The tracked files in this directory are the production security source of
truth. Internal services bind to loopback; only SSH, HTTP redirect/ACME and
HTTPS are public.

Install the systemd units only after creating the locked service account and
writable directories:

```bash
sudo useradd --system --home /opt/health-app --shell /usr/sbin/nologin health-app
sudo install -o health-app -g health-app -m 0700 -d \
  /opt/health-app/backend/{logs,uploads,data,private_media} \
  /opt/health-app/.health-skills-cache
sudo chown root:health-app /opt/health-app/backend/.env
sudo chmod 0640 /opt/health-app/backend/.env
sudo install -m 0644 infra/systemd/* /etc/systemd/system/
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

Do not expose PostgreSQL, Redis, FastAPI, Next.js, MCP, Prometheus, Grafana or
Node Exporter directly to the Internet. Remote operator access must use SSH
port forwarding or an authenticated VPN.
