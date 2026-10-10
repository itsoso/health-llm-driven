"""Negative deployment contracts: a package inspection is never activation."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "neo_deploy", Path(__file__).with_name("trusted_neo_wechat.py")
)
neo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(neo)


def test_candidate_digest_changes_with_every_input():
    assert neo.digest({"files": {"a": "one"}}) != neo.digest({"files": {"a": "two"}})
    assert neo.digest({"a": 1, "b": 2}) == neo.digest({"b": 2, "a": 1})


@pytest.mark.parametrize("value", ["", "a" * 39, "A" * 40, "../source", True])
def test_revision_is_exact_hex(value):
    with pytest.raises(neo.DeployError):
        neo.checked_revision(value)


def test_unit_contains_only_isolated_bridge_paths():
    raw = neo.render_unit("a" * 40)
    assert b"User=neo-wechat\n" in raw
    assert b"Group=neo-wechat\n" in raw
    assert b"SupplementaryGroups=neo-wechat-proxy\n" in raw
    assert b"/opt/neo-wechat/releases/" + b"a" * 40 + b"/venv/bin/python" in raw
    assert b"--socket /run/neo-wechat/bridge.sock" in raw
    assert b"ReadWritePaths=/var/lib/neo-wechat /run/neo-wechat\n" in raw
    assert b"LoadCredential=encryption_key:/etc/neo-wechat/encryption_key\n" in raw
    assert b"EnvironmentFile=" not in raw
    assert b"WorkingDirectory=/opt/health" not in raw
    assert b"WantedBy=" not in raw  # no install/enable default


def test_proxy_template_never_creates_tcp_listener_or_health_route():
    raw = neo.proxy_bytes().decode()
    assert "listen " not in raw
    assert "location ^~ /neo-wechat/ {" in raw
    assert "location = /.well-known/oauth-authorization-server/neo-wechat {" in raw
    assert "location = /.well-known/oauth-protected-resource/neo-wechat/mcp {" in raw
    assert raw.count("proxy_pass http://unix:/run/neo-wechat/bridge.sock;") == 3
    assert raw.count("access_log off;") == 3
    assert raw.count("error_log /dev/null crit;") == 3
    assert "$request_uri" not in raw


def test_unit_rejects_template_directive_injection():
    with pytest.raises(neo.DeployError):
        neo.render_unit("a" * 40 + "\nExecStart=/bin/sh")


def test_package_inventory_rejects_symlink_and_hardlink(tmp_path):
    item = tmp_path / "x"
    item.write_text("x")
    link = tmp_path / "linked"
    link.symlink_to(item)
    with pytest.raises(neo.DeployError):
        neo.file_digest(link)
    import os
    os.link(item, tmp_path / "hard")
    with pytest.raises(neo.DeployError):
        neo.file_digest(item)


def test_file_digest_does_not_return_file_content(tmp_path):
    item = tmp_path / "x"
    item.write_text("synthetic-private-value")
    result = neo.file_digest(item)
    assert len(result["sha256"]) == 64
    assert "synthetic-private-value" not in str(result)


def test_deploy_mode_precedes_health_env_loading():
    raw = Path(neo.__file__).parents[1].joinpath("deploy.sh").read_text()
    assert raw.index('"--neo-wechat"') < raw.index('ENV_FILE=')


def test_apply_rejected_before_any_inspection(monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("apply must not inspect/read credentials or contact production")
    monkeypatch.setattr(neo, "inspect", unexpected)
    assert neo.main(["--apply"]) == 78
    assert "NEO_WECHAT_INSTALL_BLOCKED" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["--install", "--activate", "--rollback"])
def test_no_hidden_mutating_mode(mode, monkeypatch, capsys):
    monkeypatch.setattr(neo, "inspect", lambda *_: pytest.fail("mutation mode must stop first"))
    assert neo.main([mode]) == 78
    assert '"production_changed": false' in capsys.readouterr().out


def test_exact_ci_requires_current_main_even_documentation_descendants():
    from types import SimpleNamespace
    gate = SimpleNamespace(_get_json=object(), _main_sha=lambda _: "b" * 40,
                           verify_release=lambda *_a, **_k: pytest.fail("stale main reached CI"))
    with pytest.raises(neo.DeployError, match="current main"):
        neo.exact_full_ci(gate, "a" * 40)


def test_exact_ci_never_uses_backend_only_admission():
    from types import SimpleNamespace
    calls = []
    gate = SimpleNamespace(_get_json=object(), _main_sha=lambda _: "a" * 40,
                           verify_release=lambda *a, **k: calls.append((a, k)) or {"green": True})
    assert neo.exact_full_ci(gate, "a" * 40) == {"green": True}
    assert calls == [(("a" * 40, "a" * 40), {"observed_main": "a" * 40, "target": "full"})]


def test_exact_ci_rejects_main_change_after_attestation():
    from types import SimpleNamespace
    revisions = iter(["a" * 40, "b" * 40])
    gate = SimpleNamespace(_get_json=object(), _main_sha=lambda _: next(revisions),
                           verify_release=lambda *_a, **_k: {"green": True})
    with pytest.raises(neo.DeployError, match="main changed"):
        neo.exact_full_ci(gate, "a" * 40)


def package_fixture(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/trusted_neo_wechat.py").write_text("# synthetic")
    (tmp_path / "deploy.sh").write_text("# synthetic")
    (tmp_path / "services/neo_wechat").mkdir(parents=True)
    (tmp_path / "services/neo_wechat/core.py").write_text("# synthetic")
    (tmp_path / "infra/neo-wechat").mkdir(parents=True)
    return tmp_path


def test_inventory_fails_before_reading_secret_named_file(tmp_path, monkeypatch):
    root = package_fixture(tmp_path)
    forbidden = root / "services/neo_wechat/.env"
    forbidden.write_text("DO-NOT-READ")
    original = neo.file_digest
    def guarded(path):
        assert path != forbidden
        return original(path)
    monkeypatch.setattr(neo, "file_digest", guarded)
    with pytest.raises(neo.DeployError, match="unexpected package file"):
        neo.package_inventory(root)


def test_inventory_rejects_directory_symlink(tmp_path):
    root = package_fixture(tmp_path)
    (root / "services/neo_wechat/escape").symlink_to(root / "scripts", target_is_directory=True)
    with pytest.raises(neo.DeployError, match="unsupported package object"):
        neo.package_inventory(root)


def test_local_package_claims_no_production_authority(tmp_path, monkeypatch, capsys):
    root = package_fixture(tmp_path)
    monkeypatch.setattr(neo, "ROOT", root)
    monkeypatch.setattr(neo, "inspect", lambda *_: pytest.fail("local package must not inspect production"))
    assert neo.main(["--package-only", "--publisher-sha", "a" * 40]) == 0
    raw = capsys.readouterr().out
    assert "NEO_WECHAT_LOCAL_PACKAGE_ONLY_UNTRUSTED" in raw
    assert '"production_changed": false' in raw


def test_oversize_file_is_not_read(tmp_path):
    path = tmp_path / "large.py"
    with path.open("wb") as stream:
        stream.truncate(neo.MAX_FILE_BYTES + 1)
    with pytest.raises(neo.DeployError):
        neo.file_digest(path)


def test_runtime_install_command_is_hash_locked_and_binary_only():
    args = neo.runtime_install_command("a" * 40)
    assert "--require-hashes" in args
    assert "--only-binary=:all:" in args
    assert "--no-deps" in args
    assert "--isolated" in args
    assert "User=neo-wechat" in args
    assert "ProtectSystem=strict" in args
    assert "ProtectHome=yes" in args
    assert "PrivateTmp=yes" in args
    assert "--no-cache-dir" in args
    assert "https://pypi.org/simple" in args


def test_preflight_requires_complete_runtime_sources(tmp_path):
    root = package_fixture(tmp_path)
    with pytest.raises(neo.DeployError, match="runtime"):
        neo.runtime_inputs(root)


def transaction_fixture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    state = tmp_path / "state"
    state.mkdir()
    (state / "launcher.lock").write_bytes(b"")
    lease = tmp_path / "business-lease"
    monkeypatch.setattr(neo, "STATE", state)
    monkeypatch.setattr(neo, "LEASE", lease)
    monkeypatch.setattr(neo, "secure_path", lambda *_a, **_k: None)
    def identity(*_args):
        return tuple((p.stat().st_dev, p.stat().st_ino) for p in (lease, lease / "token"))
    helper = SimpleNamespace(_assert_lock=lambda *_: None, _lease_identity=identity, _revision_proof=lambda *_: None)
    server = SimpleNamespace(_sync_business_lease_parent=lambda: None)
    monkeypatch.setattr(neo, "load_reviewed", lambda _: (tmp_path, helper, None, server, None))
    plan = {"publisher_sha": "a" * 40, "production_sha": "b" * 40,
            "operation_id": "c" * 32, "files": {}, "health_services": {}, "protected_metadata": {}}
    monkeypatch.setattr(neo, "inspect", lambda *_a, **_k: plan)
    monkeypatch.setattr(neo, "health_snapshot", lambda: {})
    monkeypatch.setattr(neo, "protected_metadata", lambda: {})
    monkeypatch.setattr(neo, "package_inventory", lambda *_: {})
    return state, lease, plan


def receipt(plan):
    return {"state": "INSTALLED_DORMANT", "publisher_sha": plan["publisher_sha"],
            "production_sha": plan["production_sha"], "operation_id": plan["operation_id"],
            "evidence_sha256": neo.digest(plan), "runtime_sha256": "d" * 64, "proxy_gid": 123,
            "activated": False, "nginx_included": False, "health_services_unchanged": True,
            "secrets_created": False}


def test_durable_intent_and_complete_lease_precede_install(tmp_path, monkeypatch):
    import json
    state, lease, plan = transaction_fixture(tmp_path, monkeypatch)
    audit = state / "neo-wechat" / plan["operation_id"]
    def payload(*args):
        assert json.loads((audit / "intent.json").read_text())["state"] == "INSTALL_STARTED"
        assert json.loads((audit / "before.json").read_text()) == plan
        assert {p.name for p in lease.iterdir()} == {"token", "label", "stage", "started_at"}
        assert (audit / "lease.json").exists()
        args[2]()
        return receipt(plan)
    monkeypatch.setattr(neo, "install_payload", payload)
    assert neo.install_dormant(plan) == receipt(plan)
    assert not lease.exists()
    assert json.loads((audit / "completed.json").read_text()) == receipt(plan)
    assert {p.name for p in audit.iterdir()} == {"before.json", "intent.json", "lease.json", "verified.json", "completed.json"}


def test_uncertain_install_keeps_original_lease_and_audit(tmp_path, monkeypatch):
    state, lease, plan = transaction_fixture(tmp_path, monkeypatch)
    def crash(*_args):
        raise TimeoutError("synthetic unknown systemd result")
    monkeypatch.setattr(neo, "install_payload", crash)
    with pytest.raises(neo.DeployError, match="unknown"):
        neo.install_dormant(plan)
    audit = state / "neo-wechat" / plan["operation_id"]
    assert lease.exists()
    assert (audit / "intent.json").exists()
    assert (audit / "failed.json").exists()
    assert not (audit / "completed.json").exists()
    original_inode = lease.stat().st_ino
    with pytest.raises(FileExistsError):
        neo.install_dormant(plan)
    assert lease.stat().st_ino == original_inode


def test_completion_fsync_failure_does_not_claim_success(tmp_path, monkeypatch):
    state, lease, plan = transaction_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(neo, "install_payload", lambda *_: receipt(plan))
    original = neo.write_json
    def failing(path, value):
        if path.name == "completed.json":
            raise OSError("synthetic persistence failure")
        original(path, value)
    monkeypatch.setattr(neo, "write_json", failing)
    with pytest.raises(neo.DeployError, match="unknown"):
        neo.install_dormant(plan)
    audit = state / "neo-wechat" / plan["operation_id"]
    assert (audit / "verified.json").exists()
    assert (audit / "failed.json").exists()
    assert not (audit / "completed.json").exists()


def load_history():
    spec = importlib.util.spec_from_file_location("neo_history", Path(neo.__file__).with_name("trusted_release_server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finished_history_is_bound_and_incomplete_history_blocks(tmp_path, monkeypatch):
    state, _lease, plan = transaction_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(neo, "install_payload", lambda *_: receipt(plan))
    neo.install_dormant(plan)
    history = load_history()
    monkeypatch.setattr(history, "secure_path", lambda *_a, **_k: None)
    history.assert_neo_wechat_history(state)
    audit = state / "neo-wechat" / plan["operation_id"]
    (audit / "completed.json").unlink()
    with pytest.raises(history.LaunchError, match="unfinished"):
        history.assert_neo_wechat_history(state)


def test_history_rejects_forged_binding(tmp_path, monkeypatch):
    import json
    state, _lease, plan = transaction_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(neo, "install_payload", lambda *_: receipt(plan))
    neo.install_dormant(plan)
    history = load_history()
    monkeypatch.setattr(history, "secure_path", lambda *_a, **_k: None)
    audit = state / "neo-wechat" / plan["operation_id"]
    forged = receipt(plan)
    forged["evidence_sha256"] = "e" * 64
    for name in ("completed.json", "verified.json"):
        (audit / name).write_text(json.dumps(forged))
    with pytest.raises(history.LaunchError, match="binding"):
        history.assert_neo_wechat_history(state)


def test_success_receipt_never_authorizes_activation(tmp_path, monkeypatch):
    import json
    state, _lease, plan = transaction_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(neo, "install_payload", lambda *_: receipt(plan))
    neo.install_dormant(plan)
    history = load_history()
    monkeypatch.setattr(history, "secure_path", lambda *_a, **_k: None)
    audit = state / "neo-wechat" / plan["operation_id"]
    altered = receipt(plan)
    altered["activated"] = True
    for name in ("completed.json", "verified.json"):
        (audit / name).write_text(json.dumps(altered))
    with pytest.raises(history.LaunchError, match="terminal"):
        history.assert_neo_wechat_history(state)


def test_secret_files_not_created_by_dormant_payload():
    import inspect
    raw = inspect.getsource(neo.install_payload)
    assert "slack_webhook" not in raw
    assert "admin_password_hash" not in raw
    assert "encryption_key" not in raw
    for action in ("start", "restart", "reload", "enable"):
        assert '"' + action + '"' not in raw


def test_runtime_rejects_links_after_dependency_install(tmp_path):
    (tmp_path / "escape").symlink_to("/etc/passwd")
    with pytest.raises(neo.DeployError, match="links"):
        list(neo.runtime_entries(tmp_path))


def test_post_claim_production_change_blocks_host_mutation(tmp_path, monkeypatch):
    _state, lease, plan = transaction_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(neo, "health_snapshot", lambda: {"changed": True})
    monkeypatch.setattr(neo, "install_payload", lambda *_: pytest.fail("stale production must not install"))
    with pytest.raises(neo.DeployError, match="unknown"):
        neo.install_dormant(plan)
    assert lease.exists()


def test_lease_parent_sync_never_opens_var_lock_alias(tmp_path, monkeypatch):
    _state, lease, plan = transaction_fixture(tmp_path, monkeypatch)
    original = neo.sync_directory
    def sync(path):
        assert path != lease.parent
        original(path)
    monkeypatch.setattr(neo, "sync_directory", sync)
    monkeypatch.setattr(neo, "install_payload", lambda *_: receipt(plan))
    neo.install_dormant(plan)


def test_runtime_command_hides_all_existing_private_roots():
    args = neo.runtime_install_command("a" * 40)
    for path in ("/opt", "/var/lib", "/var/log", "/var/cache", "/var/backups", "/srv", "/data", "/mnt", "/media"):
        assert any(path in item for item in args if "Paths=" in item or "TemporaryFileSystem=" in item)
    assert "PIP_CONFIG_FILE=/dev/null" in args


def test_generated_lock_comments_and_qr_asset_are_admitted(tmp_path):
    root = package_fixture(tmp_path)
    service = root / "services/neo_wechat"
    for name in ("__init__.py", "server.py", "store.py", "oauth.py", "qr.js", "README.md"):
        (service / name).write_text("# synthetic")
    (service / "requirements.lock").write_text("example==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n    # via example\n")
    assert neo.runtime_inputs(root)["bytes"] > 0
    assert "services/neo_wechat/qr.js" in neo.package_inventory(root)


def test_ordinary_deploy_checks_bridge_when_no_vision_history():
    raw = Path(neo.__file__).parents[1].joinpath("deploy.sh").read_text()
    block = raw[raw.index("def git(*args):") - 1100:raw.index("def git(*args):")]
    assert 'Path("/var/lib/reva-release/neo-wechat")' in block
    assert "if not roots:" in block

