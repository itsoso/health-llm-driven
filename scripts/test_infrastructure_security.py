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
        assert "/tmp/tts_cache" not in body

    socket = (unit_dir / "health-backend.socket").read_text()
    assert "ListenStream=127.0.0.1:8000" in socket


def test_backend_keeps_process_local_garmin_mfa_challenges_on_one_worker() -> None:
    """MFA challenge state cannot cross a uvicorn process boundary yet."""
    unit_dir = ROOT / "infra" / "systemd"
    body = (unit_dir / "health-backend.service").read_text()
    exec_start = next(line for line in body.splitlines() if line.startswith("ExecStart="))

    assert "--workers 1" in exec_start
    assert "--workers 2" not in exec_start

    # Production deploys the runtime-state drop-in transactionally while the
    # base unit in /etc may predate the checkout. The deployed artifact must
    # therefore reset and replace ExecStart too, not only the repository unit.
    dropin = (unit_dir / "dropins" / "health-backend-runtime-state.conf").read_text()
    dropin_exec_starts = [
        line for line in dropin.splitlines() if line.startswith("ExecStart=")
    ]
    assert dropin_exec_starts[0] == "ExecStart="
    assert "--workers 1" in dropin_exec_starts[1]
    assert all("--workers 2" not in line for line in dropin_exec_starts)


def test_celery_beat_state_is_outside_the_trusted_worktree() -> None:
    body = (ROOT / "infra" / "systemd" / "celery-beat.service").read_text()
    read_write_paths = next(
        line for line in body.splitlines() if line.startswith("ReadWritePaths=")
    )

    assert "StateDirectory=health-app/celery-beat" in body
    assert "StateDirectoryMode=0700" in body
    assert (
        "--schedule=/var/lib/health-app/celery-beat/celerybeat-schedule"
        in body
    )
    assert "/opt/health-app/backend/data" not in read_write_paths
    assert "/var/lib/health-app/runtime" not in read_write_paths


def _nonempty_read_write_paths(body: str) -> set[str]:
    values: list[str] = []
    for line in body.splitlines():
        if line.startswith("ReadWritePaths="):
            values = line.removeprefix("ReadWritePaths=").split()
    return {value.removeprefix("-") for value in values}


def test_each_systemd_unit_has_only_its_exact_external_write_boundary() -> None:
    unit_dir = ROOT / "infra" / "systemd"
    expected = {
        "health-backend.service": {
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/dedao-kbase",
        },
        "celery-worker.service": {
            "/var/lib/health-app/uploads",
            "/var/lib/health-app/dedao-kbase",
        },
        "celery-beat.service": {
            "/var/lib/health-app/celery-beat",
        },
    }
    dropin_dir = unit_dir / "dropins"

    for name, exact_paths in expected.items():
        base_paths = _nonempty_read_write_paths(
            (unit_dir / name).read_text()
        )
        dropin_paths = _nonempty_read_write_paths(
            (dropin_dir / name.replace(".service", "-runtime-state.conf"))
            .read_text()
        )
        assert base_paths == exact_paths
        assert dropin_paths == exact_paths
        assert all(
            not path.startswith("/opt/health-app/")
            for path in base_paths | dropin_paths
        )


def test_backend_env_example_contains_the_production_runtime_contract() -> None:
    assignments: dict[str, list[str]] = {}
    for raw_line in (ROOT / "backend" / ".env.example").read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        assignments.setdefault(name, []).append(value)

    assert assignments["APP_ENV"] == ["production"]
    assert assignments["DEBUG"] == ["False"]
    assert assignments["HEALTH_RUNTIME_DATA_DIR"] == [
        "/var/lib/health-app/runtime"
    ]
    assert assignments["HEALTH_UPLOAD_DIR"] == [
        "/var/lib/health-app/uploads"
    ]
    assert assignments["HEALTH_SKILLS_CACHE_DIR"] == [
        "/var/cache/health-app/skills-hub"
    ]
    assert assignments["DEDAO_KBASE_REVIEW_ARTIFACT_DIR"] == [
        "/var/lib/health-app/dedao-kbase/workspace"
    ]
    assert assignments["LEGACY_KNOWLEDGE_RUNTIME_ENABLED"] == ["false"]


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
