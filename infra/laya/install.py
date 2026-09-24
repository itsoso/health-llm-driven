"""First immutable Laya installation, invoked only by the governed deploy.sh.

Backend rollback intentionally leaves this independent, idle service installed.
Unknown partial installs and upgrades stop for operator review; never overwrite.
No health configuration or API key is passed to dependency-install subprocesses.
"""
import argparse
import base64
import grp
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = Path("/opt/reva-laya")
STATE = Path("/var/lib/reva-laya-release")
UNIT = Path("/etc/systemd/system/reva-laya.service")
ENV = Path("/etc/reva-laya/service.env")
BUSINESS_LEASE = Path("/var/lock/health-app-release")
LEASE_ALIAS = Path("/var/lock")
LEASE_SHARED = Path("/run/lock")
ASSETS = ("install.py", "serve.py", "model-manifest.json", "requirements.lock", "reva-laya.service.in", "encoder-config.json.b64", "rl-agent-config.json.b64", "tokenizer-config.json.b64", "model-NOTICE.txt")
EMBEDDED_MODELS = {
    "multilingual/encoder/config.json": "encoder-config.json.b64",
    "multilingual/rl_agent_config.json": "rl-agent-config.json.b64",
    "multilingual/tokenizer/tokenizer_config.json": "tokenizer-config.json.b64",
}
DOWNLOADED_MODELS = {"multilingual/model.safetensors", "multilingual/tokenizer/tokenizer.json"}
CLEAN_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
             "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


class InstallError(RuntimeError):
    """Safe diagnostic code; never include health configuration or credentials."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def secure(path, *, mode=None, shared_parent=None):
    """Root-controlled input, with no symlink or writable ancestor."""
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        protected_tmp_parent = item != path and item == Path('/tmp') and info.st_mode & stat.S_ISVTX
        protected_shared_parent = item != path and item == shared_parent
        if protected_shared_parent and (not stat.S_ISDIR(info.st_mode) or info.st_gid != 0
                                        or stat.S_IMODE(info.st_mode) != 0o1777):
            raise InstallError("unsafe_path_metadata")
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != 0
                or (info.st_mode & 0o022 and not protected_tmp_parent and not protected_shared_parent)):
            raise InstallError("unsafe_path_metadata")
    info = path.stat()
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise InstallError("unexpected_path_mode")
    if path.is_file() and info.st_nlink != 1:
        raise InstallError("unexpected_hardlink")


def resolve_business_lease(path):
    """Resolve only Ubuntu's fixed root-owned /var/lock alias."""
    if Path(path) != BUSINESS_LEASE:
        raise InstallError("unexpected_release_lease")
    info = LEASE_ALIAS.lstat()
    if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or info.st_nlink != 1 or os.readlink(LEASE_ALIAS) != "/run/lock"):
        raise InstallError("unsafe_path_metadata")
    shared = LEASE_SHARED.lstat()
    if (not stat.S_ISDIR(shared.st_mode) or shared.st_uid != 0 or shared.st_gid != 0
            or stat.S_IMODE(shared.st_mode) != 0o1777):
        raise InstallError("unsafe_path_metadata")
    return LEASE_SHARED / BUSINESS_LEASE.name


def write_atomic(path, data, mode=0o600, gid=0):
    path = Path(path)
    tmp = path.with_name(path.name + ".pending")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        os.fchmod(handle.fileno(), mode)
        os.fchown(handle.fileno(), 0, gid)
        handle.flush()
        os.fsync(handle.fileno())
    if path.is_symlink():
        raise InstallError("symlink_destination")
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_receipt(receipt):
    write_atomic(STATE / "install.json", (json.dumps(receipt, sort_keys=True) + "\n").encode())


def command(args, *, timeout=120):
    return subprocess.run([str(x) for x in args], env=CLEAN_ENV, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True, timeout=timeout, text=True).stdout.strip()


def parse_config(text):
    selected = {}
    for line in text.splitlines():
        if line.startswith("export DECISION_"):
            raise InstallError("noncanonical_decision_config")
        if not line.startswith("DECISION_"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name in selected:
            raise InstallError("duplicate_or_invalid_decision_config")
        selected[name] = value
    if selected.get("DECISION_PROVIDER") != "laya" or selected.get("DECISION_MODE") == "off":
        return None
    required = {"DECISION_ADMIN_CONTROL_ENABLED": "true",
                "DECISION_BASE_URL": "http://127.0.0.1:8092/v1", "DECISION_MODEL": "multilingual"}
    if selected.get("DECISION_MODE") not in {"on", "shadow"} or any(selected.get(key) != value for key, value in required.items()):
        raise InstallError("invalid_laya_production_config")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", selected.get("DECISION_API_KEY", "")):
        raise InstallError("invalid_laya_private_key")
    return selected


def context(args):
    if sys.platform != "linux" or os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise InstallError("unsupported_execution_context")
    lock, stage = resolve_business_lease(args.lock), Path(args.stage)
    secure(lock, mode=0o700, shared_parent=LEASE_SHARED)
    secure(stage, mode=0o700)
    for name, expected in (("token", args.token + "\n"), ("stage", str(stage) + "\n")):
        secure(lock / name, mode=0o600, shared_parent=LEASE_SHARED)
        if not hmac.compare_digest((lock / name).read_text(), expected):
            raise InstallError("release_lease_mismatch")
    secure(stage / "staged.sha256", mode=0o400)
    candidate = stage / "backend.env.candidate"
    secure(candidate, mode=0o400)
    matches = [line.split() for line in (stage / "staged.sha256").read_text().splitlines()
               if len(line.split()) == 2 and line.split()[1] == candidate.name]
    if len(matches) != 1 or matches[0][0] != sha(candidate.read_bytes()):
        raise InstallError("candidate_env_not_sealed")
    source = Path(__file__).resolve().parent
    secure(source, mode=0o700)
    secure(source / "source.json", mode=0o400)
    proof = json.loads((source / "source.json").read_text())
    if proof.get("sha") != args.sha or set(proof.get("files", {})) != set(ASSETS):
        raise InstallError("candidate_source_binding")
    for name in ASSETS:
        secure(source / name, mode=0o400)
        if sha((source / name).read_bytes()) != proof["files"][name]:
            raise InstallError("candidate_source_hash")
    return source, parse_config(candidate.read_text())


def expected_install(source, config):
    digest = sha(b"".join(name.encode() + b"\0" + (source / name).read_bytes() for name in ASSETS))
    generation = BASE / "generations" / digest
    unit = (source / "reva-laya.service.in").read_text().replace("@GENERATION@", str(generation)).encode()
    env = ("LAYA_API_KEY=" + config["DECISION_API_KEY"] + "\n").encode()
    expected = {"generation": digest, "unit_sha256": sha(unit), "env_sha256": sha(env)}
    return generation, unit, env, expected


def reusable(receipt, expected):
    if receipt.get("state") != "INSTALLED" or any(receipt.get(k) != v for k, v in expected.items()):
        raise InstallError("existing_install_requires_operator")
    return True


def existing_install(expected):
    path = STATE / "install.json"
    if path.exists() or path.is_symlink():
        secure(path, mode=0o600)
        receipt = json.loads(path.read_text())
        reusable(receipt, expected)
        return receipt
    return None


def assert_unit_absent():
    properties = command(["/usr/bin/systemctl", "show", "reva-laya.service",
                          "-p", "LoadState,FragmentPath,DropInPaths,UnitFileState"])
    values = dict(line.split("=", 1) for line in properties.splitlines())
    if values != {"LoadState": "not-found", "FragmentPath": "", "DropInPaths": "", "UnitFileState": ""}:
        raise InstallError("unmanaged_laya_systemd_unit")


class ModelRedirectHandler(HTTPRedirectHandler):
    """Only the observed mirror and upstream HTTPS CDN may receive model GETs."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in {"hf-mirror.com", "cas-bridge.xethub.hf.co"}
                or parsed.port not in {None, 443} or parsed.username is not None or parsed.password is not None):
            raise InstallError("model_redirect_rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_model_url(url, *, timeout):
    return build_opener(ProxyHandler({}), ModelRedirectHandler()).open(url, timeout=timeout)


def download_model(url, target, metadata):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    partial = target.with_name(target.name + ".part")
    digest, count = hashlib.sha256(), 0
    with open_model_url(url, timeout=60) as response, partial.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > metadata["bytes"]:
                raise InstallError("model_size_mismatch")
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if count != metadata["bytes"] or digest.hexdigest() != metadata["sha256"]:
        raise InstallError("model_hash_mismatch")
    partial.chmod(0o644)
    os.replace(partial, target)


def install_model_files(source, generation):
    manifest = json.loads((source / "model-manifest.json").read_text())
    if (manifest["repository"] != "convaiinnovations/laya"
            or not re.fullmatch(r"[0-9a-f]{40}", manifest["revision"])
            or set(manifest["files"]) != set(EMBEDDED_MODELS) | DOWNLOADED_MODELS):
        raise InstallError("invalid_model_origin")
    embedded = {}
    for name, asset in EMBEDDED_MODELS.items():
        try:
            data = base64.b64decode((source / asset).read_bytes().strip(), validate=True)
        except ValueError:
            raise InstallError("embedded_model_invalid_encoding") from None
        metadata = manifest["files"][name]
        if len(data) != metadata["bytes"] or sha(data) != metadata["sha256"]:
            raise InstallError("embedded_model_hash_mismatch")
        embedded[name] = data
    # Validate every embedded file before any model write or network request.
    for name, data in embedded.items():
        target = generation / "models" / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        write_atomic(target, data, 0o644)
    print("LAYA_MODEL_SOURCE hf-mirror.com; original upstream SHA256 manifest required")
    for name in sorted(DOWNLOADED_MODELS):
        url = f"https://hf-mirror.com/{manifest['repository']}/resolve/{manifest['revision']}/{name}"
        download_model(url, generation / "models" / name, manifest["files"][name])


def verify_generation(source, generation):
    secure(generation, mode=0o755)
    for name in ASSETS:
        secure(generation / name, mode=0o644)
        if (generation / name).read_bytes() != (source / name).read_bytes():
            raise InstallError("generation_source_mismatch")
    manifest = json.loads((generation / "model-manifest.json").read_text())
    for name, metadata in manifest["files"].items():
        target = generation / "models" / name
        secure(target, mode=0o644)
        with target.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if target.stat().st_size != metadata["bytes"] or digest != metadata["sha256"]:
            raise InstallError("installed_model_hash_mismatch")
    venv = generation / "venv"
    for target in (venv, venv / "pyvenv.cfg", venv / "lib/python3.12/site-packages"):
        secure(target)
    python = venv / "bin/python"
    if not python.is_file() or not os.access(python, os.X_OK):
        raise InstallError("missing_laya_interpreter")
    secure(python.resolve())
    # Inspect distribution metadata through the fixed system interpreter, without
    # importing site/.pth files or any installed third-party Python as root.
    inventory = json.loads(command(["/usr/bin/python3.12", "-I", "-S", "-c",
        "import importlib.metadata as m,json,sys; print(json.dumps([(d.metadata['Name'], d.version) for d in m.distributions(path=[sys.argv[1]])]))",
        venv / "lib/python3.12/site-packages"]))
    expected = dict(re.findall(r"^([a-z0-9-]+)==([^\s]+)", (source / "requirements.lock").read_text(), re.M))
    actual = {}
    for name, version in inventory:
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in actual:
            raise InstallError("duplicate_laya_distribution")
        actual[name] = version
    if not expected or any(actual.get(name) != version for name, version in expected.items()) or set(actual) - set(expected) - {"pip"}:
        raise InstallError("laya_dependency_lock_mismatch")
    # Ensure the immutable dependency tree cannot be changed by the service uid.
    for directory, dirs, files in os.walk(generation / "venv"):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            if path.is_symlink():
                secure(path.resolve())
            else:
                secure(path)


def prepare(source, config, args):
    generation, unit, env, expected = expected_install(source, config)
    STATE.mkdir(mode=0o700, exist_ok=True)
    secure(STATE, mode=0o700)
    receipt_path = STATE / "install.json"
    if receipt_path.exists():
        secure(receipt_path, mode=0o600)
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("state") == "PREPARED" and receipt.get("lease") == sha(args.token.encode()) and all(
            receipt.get(k) == v for k, v in expected.items()
        ):
            verify_generation(source, generation)
            return
        reusable(receipt, expected)
        verify_install(source, config)
        return
    if UNIT.exists() or UNIT.is_symlink() or ENV.parent.exists() or generation.exists():
        raise InstallError("unmanaged_or_partial_laya_install")
    # First activation precedes backend shutdown only if the exact old source
    # exported by the governed publisher has no decision integration.
    proof = json.loads((source / "source.json").read_text())
    if proof.get("old_has_decisions") is not False:
        raise InstallError("first_install_old_backend_can_call_laya")
    assert_unit_absent()
    BASE.mkdir(mode=0o755, exist_ok=True)
    secure(BASE, mode=0o755)
    (BASE / "generations").mkdir(mode=0o755, exist_ok=True)
    secure(BASE / "generations", mode=0o755)
    # Intent precedes every generation write. A crash remains an explicit BLOCK.
    receipt = {**expected, "state": "PREPARING", "candidate_sha": args.sha, "lease": sha(args.token.encode())}
    save_receipt(receipt)
    generation.mkdir(mode=0o755)
    for name in ASSETS:
        write_atomic(generation / name, (source / name).read_bytes(), 0o644)
    python = Path("/usr/bin/python3.12")
    secure(python.resolve())
    command([python, "-I", "-m", "venv", generation / "venv"])
    # Binary wheels only; the complete CPU dependency closure is hash pinned.
    command([generation / "venv/bin/python", "-I", "-m", "pip", "--isolated", "install",
             "--require-hashes", "--only-binary=:all:", "--no-cache-dir",
             "--index-url", "https://pypi.org/simple",
             "--extra-index-url", "https://download.pytorch.org/whl/cpu",
             "-r", generation / "requirements.lock"], timeout=1200)
    install_model_files(source, generation)
    write_atomic(generation / "reva-laya.service", unit, 0o644)
    command(["/usr/bin/systemd-analyze", "verify", generation / "reva-laya.service"])
    verify_generation(source, generation)
    save_receipt({**receipt, "state": "PREPARED"})
    print("LAYA_PREPARED")


def service_identity(generation):
    account = validate_account()
    properties = command(["/usr/bin/systemctl", "show", "reva-laya.service",
                          "-p", "ActiveState,SubState,MainPID,NRestarts,FragmentPath,DropInPaths,User,Group,UnitFileState"])
    values = dict(line.split("=", 1) for line in properties.splitlines())
    if any(values.get(key) != value for key, value in {
        "ActiveState": "active", "SubState": "running", "FragmentPath": str(UNIT),
        "DropInPaths": "", "User": "reva-laya", "Group": "reva-laya",
        "UnitFileState": "enabled",
    }.items()) or not re.fullmatch(r"[1-9][0-9]*", values.get("MainPID", "")):
        raise InstallError("laya_service_identity")
    pid = values["MainPID"]
    expected_argv = [str(generation / "venv/bin/python"), "-I", str(generation / "serve.py")]
    if Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0").decode().split("\0") != expected_argv:
        raise InstallError("laya_process_identity")
    if Path(f"/proc/{pid}").stat().st_uid != account.pw_uid:
        raise InstallError("laya_process_user")
    return values


def probe(key):
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:8092/health", timeout=5) as response:
        health = json.load(response)
    if health != {"status": "ok", "loaded": ["multilingual"], "device": "cpu"}:
        raise InstallError("laya_health_contract")
    payload = json.dumps({"model": "multilingual", "state": "Hello, this is a synthetic deployment check.", "questions": {
        "choice": {"type": "choice", "instructions": "Greeting?", "criteria": {"yes": "Greeting", "no": "Not greeting"}},
        "score": {"type": "score", "instructions": "Is the message polite?", "criteria": ["Not polite", "Polite"]},
        "noul": {"type": "noul", "instructions": "Is the message a greeting?"},
    }}).encode()
    for bearer, expected in (("invalid", 401), (key, 200)):
        request = Request("http://127.0.0.1:8092/v1/systemone", data=payload,
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + bearer})
        try:
            with opener.open(request, timeout=30) as response:
                if response.status != expected:
                    raise InstallError("laya_auth_contract")
                result = json.load(response)
                if set(result.get("answers", {})) != {"choice", "score", "noul"}:
                    raise InstallError("laya_inference_contract")
        except HTTPError as exc:
            if exc.code != expected or expected == 200:
                raise InstallError("laya_http_contract") from None


def validate_account():
    account = pwd.getpwnam("reva-laya")
    group = grp.getgrnam("reva-laya")
    if (account.pw_uid == 0 or account.pw_gid != group.gr_gid
        or account.pw_dir != "/nonexistent" or account.pw_shell != "/usr/sbin/nologin"
        or set(group.gr_mem) - {"reva-laya"}
        or set(os.getgrouplist("reva-laya", account.pw_gid)) != {account.pw_gid}
        or any(other.pw_name != "reva-laya" and (other.pw_gid == group.gr_gid or other.pw_uid == account.pw_uid)
               for other in pwd.getpwall())):
        raise InstallError("laya_account_not_isolated")
    return account


def verify_install(source, config):
    generation, unit, env, expected = expected_install(source, config)
    account = validate_account()
    secure(UNIT, mode=0o644)
    secure(ENV, mode=0o640)
    if UNIT.read_bytes() != unit or not hmac.compare_digest(ENV.read_bytes(), env):
        raise InstallError("laya_install_drift")
    if ENV.stat().st_gid != account.pw_gid:
        raise InstallError("laya_credential_group")
    verify_generation(source, generation)
    command(["/usr/bin/systemd-analyze", "verify", UNIT])
    before = service_identity(generation)
    probe(config["DECISION_API_KEY"])
    time.sleep(7)  # cross RestartSec; never declare a crash loop healthy
    if before != service_identity(generation):
        raise InstallError("laya_service_unstable")
    probe(config["DECISION_API_KEY"])


def activate(source, config, args):
    generation, unit, env, expected = expected_install(source, config)
    secure(STATE / "install.json", mode=0o600)
    receipt = json.loads((STATE / "install.json").read_text())
    if receipt.get("state") == "INSTALLED":
        reusable(receipt, expected)
        verify_install(source, config)
        return
    if receipt != {**expected, "state": "PREPARED", "candidate_sha": args.sha, "lease": sha(args.token.encode())}:
        raise InstallError("laya_activation_not_prepared")
    verify_generation(source, generation)
    if UNIT.exists() or UNIT.is_symlink() or ENV.parent.exists():
        raise InstallError("unmanaged_laya_service")
    assert_unit_absent()
    if command(["/usr/bin/ss", "-H", "-lnt", "sport = :8092"]):
        raise InstallError("laya_port_in_use")
    save_receipt({**receipt, "state": "ACTIVATING"})
    try:
        account = pwd.getpwnam("reva-laya")
    except KeyError:
        command(["/usr/sbin/useradd", "--system", "--no-create-home", "--home-dir", "/nonexistent",
                 "--shell", "/usr/sbin/nologin", "--user-group", "reva-laya"])
        account = pwd.getpwnam("reva-laya")
    account = validate_account()
    ENV.parent.mkdir(mode=0o750)
    os.chown(ENV.parent, 0, account.pw_gid)
    write_atomic(ENV, env, 0o640, account.pw_gid)
    write_atomic(UNIT, unit, 0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "reva-laya.service"])
    deadline = time.monotonic() + 90
    while True:
        try:
            probe(config["DECISION_API_KEY"])
            break
        except (URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise InstallError("laya_startup_timeout") from None
            time.sleep(1)
    verify_install(source, config)
    save_receipt({**receipt, "state": "INSTALLED"})
    print("LAYA_INSTALLED_VERIFIED")


def main():
    # Generations must be readable by the separate service account. Private
    # receipts/source/credentials use explicit 0700/0600/0640 modes throughout.
    os.umask(0o022)
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "provision", "activate", "verify"))
    for name in ("sha", "lock", "token", "stage"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    source, config = context(args)
    if config is None:
        print("LAYA_NOT_SELECTED")
        return
    if args.phase in {"prepare", "provision"}:
        prepare(source, config, args)
        if args.phase == "provision":
            source, config = context(args)  # recheck the lease before service mutation
            activate(source, config, args)
    elif args.phase == "activate":
        activate(source, config, args)
    else:
        if existing_install(expected_install(source, config)[3]) is None:
            raise InstallError("missing_laya_install_receipt")
        verify_install(source, config)
        print("LAYA_VERIFIED")


if __name__ == "__main__":
    try:
        main()
    except (InstallError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        # subprocess stdout/stderr may contain URL errors; do not echo it or env.
        print("LAYA_BLOCKED:" + (str(exc) if isinstance(exc, InstallError) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1) from None
