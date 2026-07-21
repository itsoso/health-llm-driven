from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_ports_are_loopback_only() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    for service_name in ("db", "redis", "backend", "mcp-server", "frontend"):
        ports = compose["services"][service_name].get("ports", [])
        assert ports, f"{service_name} must declare an explicit loopback port binding"
        assert all(str(port).startswith("127.0.0.1:") for port in ports), (
            f"{service_name} exposes a host port beyond loopback: {ports}"
        )


def test_systemd_units_use_dedicated_user_and_sandbox() -> None:
    unit_dir = ROOT / "infra" / "systemd"
    service_names = ("health-backend.service", "celery-worker.service", "celery-beat.service")

    for name in service_names:
        body = (unit_dir / name).read_text()
        assert "User=health-app" in body
        assert "Group=health-app" in body
        assert "User=root" not in body
        assert "NoNewPrivileges=true" in body
        assert "PrivateTmp=true" in body
        assert "ProtectSystem=strict" in body

    socket = (unit_dir / "health-backend.socket").read_text()
    assert "ListenStream=127.0.0.1:8000" in socket


def test_nginx_and_firewall_do_not_publish_internal_services() -> None:
    nginx = (ROOT / "infra" / "nginx" / "health.executor.life.conf").read_text()
    assert "proxy_pass http://127.0.0.1:8000" in nginx
    assert "server_tokens off" in nginx

    firewall = (ROOT / "infra" / "firewall" / "apply-ufw.sh").read_text()
    for public_port in ("22/tcp", "80/tcp", "443/tcp"):
        assert f"allow {public_port}" in firewall
    for internal_port in ("3000/tcp", "5432/tcp", "6379/tcp", "8000/tcp", "8808/tcp", "9090/tcp", "9100/tcp"):
        assert f"deny {internal_port}" in firewall


def test_legacy_production_installer_is_fail_closed() -> None:
    body = (ROOT / "deploy_production.sh").read_text()
    assert "SECURITY BLOCK" in body
    assert "User=root" not in body
    assert "--bind 0.0.0.0:8000" not in body
