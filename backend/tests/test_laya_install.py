"""Fail-closed deployment boundaries; no subprocess touches the test host."""
import importlib.util
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.parametrize("stderr,expected", [
    ("ERROR: THESE PACKAGES DO NOT MATCH THE HASHES", "hash_mismatch"),
    ("ERROR: No matching distribution found", "distribution_unavailable"),
    ("ResolutionImpossible: conflicting dependencies", "dependency_conflict"),
    ("ReadTimeoutError: private-host", "network_timeout"),
    ("CERTIFICATE_VERIFY_FAILED", "tls_verification"),
    ("No space left on device", "disk_full"),
    ("private arbitrary failure", "subprocess"),
])
def test_install_step_reports_closed_error_category_without_raw_output(monkeypatch, stderr, expected):
    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["private-command"],
                                            output="sensitive-value", stderr=stderr)
    monkeypatch.setattr(installer, "command", failed)
    with pytest.raises(installer.InstallError) as caught:
        installer.install_step("dependencies", ["irrelevant"], timeout=1200)
    assert str(caught.value) == f"dependencies_failed_{expected}"


def test_install_step_timeout_is_not_success_and_preserves_no_output(monkeypatch):
    def failed(*args, **kwargs):
        raise subprocess.TimeoutExpired(["private-command"], 10, output=b"sensitive-value")
    monkeypatch.setattr(installer, "command", failed)
    with pytest.raises(installer.InstallError, match="^dependencies_failed_timeout$"):
        installer.install_step("dependencies", ["irrelevant"])


def test_install_step_rejects_unknown_stage_before_command(monkeypatch):
    monkeypatch.setattr(installer, "command", lambda *a, **kw: pytest.fail("must not execute"))
    with pytest.raises(installer.InstallError, match="^unknown_install_step$"):
        installer.install_step("sensitive-value", ["irrelevant"])


def test_install_step_preserves_success_and_timeout_argument(monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "command", lambda args, **kw: calls.append((args, kw)) or "success")
    assert installer.install_step("dependencies", ["synthetic"], timeout=321) == "success"
    assert calls == [(["synthetic"], {"timeout": 321})]


def test_dependency_mirror_keeps_original_hashes_and_cpu_binary_boundary(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(installer, "install_step", lambda *args, **kwargs: calls.append((args, kwargs)))
    installer.install_dependencies(tmp_path)
    (stage, args), kwargs = calls[0]
    assert stage == "dependencies" and kwargs == {"timeout": 1200}
    assert args[:5] == [tmp_path / "venv/bin/python", "-I", "-m", "pip", "--isolated"]
    assert args[args.index("--index-url") + 1] == "https://pypi.tuna.tsinghua.edu.cn/simple"
    assert "--extra-index-url" not in args
    assert args[args.index("--find-links") + 1] == "https://download.pytorch.org/whl/cpu/torch/"
    assert {"--require-hashes", "--only-binary=:all:", "--no-cache-dir"} <= set(map(str, args))
    assert args[-2:] == ["-r", tmp_path / "requirements.lock"]
    assert not {"--trusted-host", "--no-deps", "--ignore-installed"} & set(map(str, args))


def metadata(kind, mode, *, uid=0, gid=0, nlink=1):
    return SimpleNamespace(st_mode=kind | mode, st_uid=uid, st_gid=gid, st_nlink=nlink)


def test_fixed_ubuntu_lock_alias_resolves_to_root_sticky_runtime(monkeypatch):
    values = {
        installer.LEASE_ALIAS: metadata(stat.S_IFLNK, 0o777),
        installer.LEASE_SHARED: metadata(stat.S_IFDIR, 0o1777),
    }
    monkeypatch.setattr(Path, "lstat", lambda self: values[self])
    monkeypatch.setattr(os, "readlink", lambda path: "/run/lock")
    assert installer.resolve_business_lease(installer.BUSINESS_LEASE) == Path("/run/lock/health-app-release")


@pytest.mark.parametrize("damage", ["alias_owner", "alias_target", "shared_mode", "other_path"])
def test_lock_alias_drift_is_rejected(monkeypatch, damage):
    values = {
        installer.LEASE_ALIAS: metadata(stat.S_IFLNK, 0o777, uid=1 if damage == "alias_owner" else 0),
        installer.LEASE_SHARED: metadata(stat.S_IFDIR, 0o755 if damage == "shared_mode" else 0o1777),
    }
    monkeypatch.setattr(Path, "lstat", lambda self: values[self])
    monkeypatch.setattr(os, "readlink", lambda path: "/tmp" if damage == "alias_target" else "/run/lock")
    path = Path("/tmp/other") if damage == "other_path" else installer.BUSINESS_LEASE
    with pytest.raises(installer.InstallError):
        installer.resolve_business_lease(path)


def test_only_fixed_runtime_lock_may_cross_root_sticky_parent(monkeypatch):
    target = Path("/run/lock/health-app-release")
    values = {
        target: metadata(stat.S_IFDIR, 0o700),
        Path("/run/lock"): metadata(stat.S_IFDIR, 0o1777),
        Path("/run"): metadata(stat.S_IFDIR, 0o755),
        Path("/"): metadata(stat.S_IFDIR, 0o755),
    }
    monkeypatch.setattr(Path, "lstat", lambda self: values[self])
    monkeypatch.setattr(Path, "stat", lambda self: values[self])
    installer.secure(target, mode=0o700, shared_parent=Path("/run/lock"))
    with pytest.raises(installer.InstallError):
        installer.secure(target, mode=0o700)


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
    monkeypatch.setattr(installer, "open_model_url", lambda *a, **kw: io.BytesIO(b"wrong"))
    target = tmp_path / "model.safetensors"
    with pytest.raises(installer.InstallError):
        installer.download_model("https://huggingface.co/test", target,
                                 {"sha256": "a" * 64, "bytes": 5})
    assert not target.exists()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "invalid_encoding"])
def test_embedded_model_config_failure_never_uses_network(tmp_path, monkeypatch, damage):
    import base64
    import shutil
    source = tmp_path / "source"
    shutil.copytree(ROOT / "infra/laya", source)
    broken = source / "encoder-config.json.b64"
    if damage == "missing":
        broken.unlink()
    elif damage == "corrupt":
        broken.write_bytes(base64.b64encode(b"corrupt") + b"\n")
    else:
        broken.write_bytes(b"corrupt")
    monkeypatch.setattr(installer, "download_model", lambda *a: pytest.fail("Broken embedded config must block before network"))
    with pytest.raises((installer.InstallError, FileNotFoundError)):
        installer.install_model_files(source, tmp_path / "generation")


def test_model_downloads_use_only_fixed_mirror_and_keep_original_hashes(tmp_path, monkeypatch):
    import json
    source = ROOT / "infra/laya"
    manifest = json.loads((source / "model-manifest.json").read_text())
    calls = []
    monkeypatch.setattr(installer.os, "fchown", lambda *args: None)
    monkeypatch.setattr(installer, "download_model", lambda url, target, metadata: calls.append((url, target, metadata)))
    generation = tmp_path / "generation"
    installer.install_model_files(source, generation)
    assert len(calls) == 2
    for url, target, metadata in calls:
        name = str(target.relative_to(generation / "models"))
        assert url == f"https://hf-mirror.com/{manifest['repository']}/resolve/{manifest['revision']}/{name}"
        assert metadata == manifest["files"][name]
    for name in ("multilingual/encoder/config.json", "multilingual/rl_agent_config.json", "multilingual/tokenizer/tokenizer_config.json"):
        data = (generation / "models" / name).read_bytes()
        assert installer.sha(data) == manifest["files"][name]["sha256"]


@pytest.mark.parametrize("url", ["http://cas-bridge.xethub.hf.co/file", "https://localhost/file", "https://cas-bridge.xethub.hf.co.evil.test/file", "https://user:pass@cas-bridge.xethub.hf.co/file", "https://cas-bridge.xethub.hf.co:8080/file"])
def test_model_redirect_outside_verified_https_hosts_is_rejected(url):
    from urllib.request import Request
    with pytest.raises(installer.InstallError, match="model_redirect_rejected"):
        installer.ModelRedirectHandler().redirect_request(Request("https://hf-mirror.com/file"), None, 302, "Found", {}, url)


def test_verified_cdn_redirect_preserves_get_and_no_authorization():
    from urllib.request import Request
    request = installer.ModelRedirectHandler().redirect_request(
        Request("https://hf-mirror.com/file"), None, 302, "Found", {}, "https://cas-bridge.xethub.hf.co/file?public-signature=synthetic",
    )
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") is None


def test_deploy_exports_exact_model_asset_allowlist():
    import ast
    script = (ROOT / "deploy.sh").read_text()
    line = next(line for line in script.splitlines() if line.startswith("assets = ("))
    assert ast.literal_eval(line.removeprefix("assets = ")) == installer.ASSETS
    assert {"encoder-config.json.b64", "rl-agent-config.json.b64", "tokenizer-config.json.b64", "model-NOTICE.txt"} <= set(installer.ASSETS)


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
    source.mkdir()
    generation.mkdir()
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
    source.mkdir()
    generation.mkdir()
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
