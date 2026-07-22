import json
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


def test_frontend_production_server_binds_to_loopback() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    start = package["scripts"]["start"]

    assert "-H 127.0.0.1" in start
    assert "-p 30001" in start


def test_deploy_stages_current_backup_scripts_before_preflight() -> None:
    body = (ROOT / "deploy.sh").read_text()
    backup_body = body[body.index("backup_database() {") :]
    stage_call = backup_body.index("stage_backup_preflight_scripts")
    backup_call = backup_body.index('BACKUP_OFFSITE_REQUIRED=1 bash \\"$REMOTE_BACKUP_RUNNER\\"')

    assert stage_call < backup_call
    for script_name in (
        "backup_db.sh",
        "verify_backup_restore.sh",
        "archive_backup_offsite.sh",
    ):
        assert script_name in body


def test_migration_role_default_privileges_reach_runtime() -> None:
    body = (ROOT / "backend" / "scripts" / "provision_database_roles.sql").read_text()

    assert "ALTER DEFAULT PRIVILEGES FOR ROLE health_app_migrator" in body
    assert body.count("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO health_app_runtime") >= 2
    assert body.count("GRANT USAGE, SELECT ON SEQUENCES TO health_app_runtime") >= 2


def test_legacy_production_installer_is_fail_closed() -> None:
    body = (ROOT / "deploy_production.sh").read_text()
    assert "SECURITY BLOCK" in body
    assert "User=root" not in body
    assert "--bind 0.0.0.0:8000" not in body
