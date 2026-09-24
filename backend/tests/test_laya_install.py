"""Fail-closed deployment boundaries; no subprocess touches the test host."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("laya_install", ROOT / "infra/laya/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def config(**changes):
    values = dict(DECISION_PROVIDER="laya", DECISION_MODE="on",
                  DECISION_ADMIN_CONTROL_ENABLED="true",
                  DECISION_BASE_URL="http://127.0.0.1:8092/v1",
                  DECISION_MODEL="multilingual", DECISION_API_KEY="a" * 48)
    values.update(changes)
    return "\n".join(f"{key}={value}" for key, value in values.items())


@pytest.mark.parametrize("change", [
    {"DECISION_API_KEY": "short"}, {"DECISION_BASE_URL": "http://remote/v1"},
    {"DECISION_MODEL": "english"}, {"DECISION_ADMIN_CONTROL_ENABLED": "false"},
    {"DECISION_MODE": "invalid"}, {"DECISION_API_KEY": "$(id)" * 10},
])
def test_rejects_noncanonical_production_config(change):
    with pytest.raises(installer.InstallError):
        installer.parse_config(config(**change))


def test_config_is_data_not_shell_and_duplicates_fail():
    assert installer.parse_config(config())["DECISION_API_KEY"] == "a" * 48
    assert installer.parse_config("DECISION_PROVIDER=jev\nDECISION_API_KEY=unused") is None
    assert installer.parse_config(config(DECISION_MODE="off", DECISION_API_KEY="")) is None
    assert installer.parse_config(config(DECISION_MODE="shadow"))["DECISION_MODE"] == "shadow"
    with pytest.raises(installer.InstallError):
        installer.parse_config(config() + "\nDECISION_API_KEY=second")
    with pytest.raises(installer.InstallError):
        installer.parse_config(config().replace("DECISION_MODE=on", "export DECISION_MODE=on"))


def test_only_completed_identical_install_can_be_reused():
    expected = {"generation": "a" * 64, "unit_sha256": "b" * 64, "env_sha256": "c" * 64}
    assert installer.reusable({**expected, "state": "INSTALLED"}, expected)
    for receipt in ({**expected, "state": "ACTIVATING"},
                    {**expected, "state": "INSTALLED", "env_sha256": "d" * 64}, {}):
        with pytest.raises(installer.InstallError):
            installer.reusable(receipt, expected)


def test_download_hash_failure_never_publishes_model(tmp_path, monkeypatch):
    import io
    monkeypatch.setattr(installer, "urlopen", lambda *a, **kw: io.BytesIO(b"wrong"))
    target = tmp_path / "model.safetensors"
    with pytest.raises(installer.InstallError):
        installer.download_model("https://huggingface.co/test", target,
                                 {"sha256": "a" * 64, "bytes": 5})
    assert not target.exists()


def test_existing_partial_install_refuses_before_any_command(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "STATE", tmp_path)
    (tmp_path / "install.json").write_text('{"state":"ACTIVATING"}')
    monkeypatch.setattr(installer, "secure", lambda *a, **kw: None)
    monkeypatch.setattr(installer, "command", lambda *a, **kw: pytest.fail("Unknown install must not run a command"))
    with pytest.raises(installer.InstallError):
        installer.existing_install({})


@pytest.mark.parametrize("properties", [
    "LoadState=loaded\nFragmentPath=/usr/lib/systemd/system/reva-laya.service\nDropInPaths=\nUnitFileState=disabled",
    "LoadState=not-found\nFragmentPath=\nDropInPaths=/run/systemd/system/reva-laya.service.d/override.conf\nUnitFileState=",
])
def test_unknown_vendor_or_runtime_unit_blocks_install(monkeypatch, properties):
    monkeypatch.setattr(installer, "command", lambda *a, **kw: properties)
    with pytest.raises(installer.InstallError, match="unmanaged_laya_systemd_unit"):
        installer.assert_unit_absent()


@pytest.mark.parametrize("bad", ["wrong_primary", "extra_group", "shared_group", "shared_uid", "supplementary"])
def test_account_cannot_share_credentials_with_other_users(monkeypatch, bad):
    from types import SimpleNamespace
    account = SimpleNamespace(pw_name="reva-laya", pw_uid=990, pw_gid=991,
                              pw_dir="/nonexistent", pw_shell="/usr/sbin/nologin")
    group = SimpleNamespace(gr_gid=999 if bad == "wrong_primary" else 991,
                            gr_mem=["someone"] if bad == "extra_group" else [])
    users = [account]
    if bad in {"shared_group", "shared_uid"}:
        users.append(SimpleNamespace(pw_name="someone", pw_uid=990 if bad == "shared_uid" else 1000,
                                     pw_gid=991 if bad == "shared_group" else 1000))
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda name: account)
    monkeypatch.setattr(installer.pwd, "getpwall", lambda: users)
    monkeypatch.setattr(installer.grp, "getgrnam", lambda name: group)
    monkeypatch.setattr(installer.os, "getgrouplist", lambda *a: [991, 1000] if bad == "supplementary" else [991])
    with pytest.raises(installer.InstallError, match="laya_account_not_isolated"):
        installer.validate_account()


def test_missing_venv_cannot_pass_generation_verification(tmp_path, monkeypatch):
    import json
    source, generation = tmp_path / "source", tmp_path / "generation"
    source.mkdir(); generation.mkdir()
    for name in installer.ASSETS:
        data = json.dumps({"files": {}}) if name == "model-manifest.json" else "fixture"
        (source / name).write_text(data)
        (generation / name).write_text(data)
        (generation / name).chmod(0o644)
    monkeypatch.setattr(installer, "secure", lambda path, **kw: Path(path).lstat())
    monkeypatch.setattr(installer, "command", lambda *a, **kw: pytest.fail("Missing venv must fail before inventory"))
    with pytest.raises(FileNotFoundError):
        installer.verify_generation(source, generation)


def test_dependency_version_drift_blocks_reuse(tmp_path, monkeypatch):
    source, generation = tmp_path / "source", tmp_path / "generation"
    source.mkdir(); generation.mkdir()
    (source / "requirements.lock").write_text("laya==0.3.11\n")
    (generation / "model-manifest.json").write_text('{"files":{}}')
    venv = generation / "venv"
    (venv / "lib/python3.12/site-packages").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("fixture")
    (venv / "bin").mkdir()
    (venv / "bin/python").write_text("fixture")
    (venv / "bin/python").chmod(0o755)
    monkeypatch.setattr(installer, "ASSETS", ())
    monkeypatch.setattr(installer, "secure", lambda path, **kw: Path(path).lstat())
    monkeypatch.setattr(installer, "command", lambda *a, **kw: '[["laya","0.3.10"]]')
    with pytest.raises(installer.InstallError, match="laya_dependency_lock_mismatch"):
        installer.verify_generation(source, generation)


def test_running_but_disabled_service_is_not_healthy(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(installer, "validate_account", lambda: SimpleNamespace(pw_uid=990))
    monkeypatch.setattr(installer, "command", lambda *a, **kw: (
        "ActiveState=active\nSubState=running\nMainPID=99\nNRestarts=0\n"
        f"FragmentPath={installer.UNIT}\nDropInPaths=\nUser=reva-laya\nGroup=reva-laya\nUnitFileState=disabled"
    ))
    with pytest.raises(installer.InstallError, match="laya_service_identity"):
        installer.service_identity(tmp_path)


def test_deploy_prepares_before_stopping_backend_and_activates_after_checkout():
    script = (ROOT / "deploy.sh").read_text()
    body = script.split("deploy_backend() {", 1)[1].split("deploy_frontend() {", 1)[0]
    assert body.index("prepare_laya_service") < body.index("systemctl stop health-backend.socket")
    assert body.index("$remote_git_sync &&") < body.index("$activate_laya_service &&") < body.index("systemctl restart health-backend.socket")
