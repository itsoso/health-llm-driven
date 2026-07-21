#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "必须以 root 运行防火墙基线" >&2
    exit 1
fi

ufw --force reset
ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP redirect and ACME'
ufw allow 443/tcp comment 'HTTPS'

# Defense in depth: these services must remain loopback/VPN-only even if a
# future process accidentally binds to every interface.
ufw deny 3000/tcp comment 'Next.js internal'
ufw deny 5432/tcp comment 'PostgreSQL internal'
ufw deny 6379/tcp comment 'Redis internal'
ufw deny 8000/tcp comment 'FastAPI internal'
ufw deny 8808/tcp comment 'MCP internal'
ufw deny 9090/tcp comment 'Prometheus internal'
ufw deny 9100/tcp comment 'Node exporter internal'

ufw logging low
ufw --force enable
ufw status verbose
