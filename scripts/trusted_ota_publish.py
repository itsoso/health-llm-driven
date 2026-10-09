"""One-shot production iOS OTA publisher for a fresh root-owned hosted VM.

Only canonical /opt/reva-release/source is executable. A durable server claim
precedes the single vendor write. Unknown outcomes retain evidence and never
retry. Local export hashes and remote publication are independently reconciled
by the server; successful CLI exit alone does not certify delivery.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import urllib.request

ROOT = Path("/opt/reva-release")
SOURCE = ROOT / "source"
NODE = Path("/opt/hostedtoolcache/node/22.13.0/x64/bin/node")
EAS = SOURCE / "scripts/release-tools/node_modules/eas-cli/bin/run"
EXPO = SOURCE / "mobile/node_modules/expo/bin/cli"
PROJECT = "911ea84f-bc7e-4a12-90cf-33966b6f7398"
RUNTIME = "1.3.5"
NATIVE_SHA = "7fe06d8b34750b6bd56db8d5ec45d1aee705b02e"
NATIVE_BUILD = "09719eb6-2887-4100-9ccb-6533fd9d71ed"
BUNDLE = "life.executor.health"
API_URL = "https://health.executor.life/api"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
FIXED_APP_ENV = {
    "APP_VARIANT": "production",
    "EXPO_PUBLIC_API_URL": API_URL,
    "SENTRY_DISABLE_AUTO_UPLOAD": "true",
    "EXPO_NO_DOTENV": "1",
}
GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_NO_REPLACE_OBJECTS": "1",
}


class PublishError(Exception):
    """Fixed diagnostics only; never vendor payloads or process exceptions."""


# Closed vocabulary: never derive a diagnostic from exception text or vendor data.
DIAGNOSTIC_PHASES = frozenset({
    "private-context", "credential", "gate-before", "source-before", "baseline",
    "baseline-json", "cohort", "cohort-json", "cohort-next", "cohort-next-json",
    "native-binding", "channel-before", "channel-before-json", "channel-binding",
    "environment", "export", "source-after", "artifact", "publication", "admission",
})
DIAGNOSTIC_REASONS = frozenset({
    "operation_failed", "command_failed", "command_timeout", "command_unavailable",
    "metadata_invalid", "verified",
})


class CommandError(PublishError):
    def __init__(self, reason):
        super().__init__("isolated command failed")
        self.reason = reason


class PhaseError(PublishError):
    def __init__(self, phase, reason):
        super().__init__("operation blocked; retry forbidden")
        self.phase = phase
        self.reason = reason


def phase_call(phase, operation, *args, **kwargs):
    if phase not in DIAGNOSTIC_PHASES:
        raise PublishError("unknown diagnostic phase")
    try:
        return operation(*args, **kwargs)
    except PhaseError:
        raise
    except subprocess.TimeoutExpired:
        raise PhaseError(phase, "command_timeout") from None
    except CommandError as exc:
        reason = exc.reason if exc.reason in DIAGNOSTIC_REASONS else "operation_failed"
        raise PhaseError(phase, reason) from None
    except Exception:
        raise PhaseError(phase, "operation_failed") from None


def diagnostic(sha, state, phase, reason):
    if (not isinstance(sha, str) or re.fullmatch(r"[a-f0-9]{40}", sha) is None
            or state not in {"BLOCKED", "ADMISSION_PASSED"}
            or phase not in DIAGNOSTIC_PHASES or reason not in DIAGNOSTIC_REASONS
            or (state == "ADMISSION_PASSED") != (phase == "admission")
            or (state == "ADMISSION_PASSED") != (reason == "verified")):
        raise PublishError("invalid safe diagnostic")
    return {"sha": sha, "state": state, "phase": phase, "reason": reason}


def persist_diagnostic(value):
    # Only an exclusive bounded JSON file under trusted root ancestors; never raw logs.
    value = diagnostic(**value)
    for path in [*reversed(ROOT.parents), ROOT]:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PublishError("untrusted diagnostic root")
    with private_file(ROOT / "ota-diagnostic.json") as stream:
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(ROOT)


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise PublishError("duplicate metadata field")
        result[k] = v
    return result


def parsed(raw):
    try:
        if len(raw) > 2_000_000:
            raise PublishError("vendor metadata exceeds bound")
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PublishError("vendor metadata invalid") from None


def identifier(value):
    return isinstance(value, str) and re.fullmatch(UUID, value) is not None


def validate_builds(base, cohort):
    def validate(item, *, pinned=False):
        if (
            not isinstance(item, dict)
            or not identifier(item.get("id"))
            or any(
                item.get(k) != v
                for k, v in {
                    "platform": "IOS",
                    "status": "FINISHED",
                    "distribution": "STORE",
                    "buildProfile": "production",
                    "appIdentifier": BUNDLE,
                    "isForIosSimulator": False,
                }.items()
            )
            or item.get("app", {}).get("id") != PROJECT
            or item.get("runtime", {}).get("version") != RUNTIME
            or item.get("updateChannel", {}).get("name") != "production"
            or (
                pinned
                and (
                    item["id"] != NATIVE_BUILD
                    or item.get("gitCommitHash") != NATIVE_SHA
                )
            )
        ):
            raise PublishError("native build binding differs")
        fingerprint = item.get("fingerprint")
        if (
            not isinstance(fingerprint, dict)
            or not isinstance(fingerprint.get("hash"), str)
            or re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", fingerprint["hash"])
            is None
        ):
            raise PublishError("native fingerprint missing")
        return fingerprint["hash"]

    expected = validate(base, pinned=True)
    if (
        not isinstance(cohort, list)
        or not 0 < len(cohort) < 100
        or any(not isinstance(b, dict) for b in cohort)
        or len({b.get("id") for b in cohort}) != len(cohort)
        or NATIVE_BUILD not in {b.get("id") for b in cohort}
    ):
        raise PublishError("native cohort incomplete or duplicated")
    for item in cohort:
        if validate(item) != expected:
            raise PublishError("production runtime native fingerprints differ")
    return expected


def validate_channel(value):
    try:
        channel = value["currentPage"]
        branches = channel["updateBranches"]
        mapping = parsed(channel["branchMapping"])
        if (
            channel["name"] != "production"
            or channel["isPaused"] is not False
            or not identifier(channel["id"])
            or not isinstance(branches, list)
            or len(branches) != 1
            or not isinstance(mapping, dict)
            or set(mapping) != {"version", "data"}
            or type(mapping["version"]) is not int
            or mapping["version"] != 0
            or branches[0]["name"] != "production"
            or not identifier(branches[0]["id"])
            or mapping["data"]
            != [{"branchId": branches[0]["id"], "branchMappingLogic": "true"}]
        ):
            raise PublishError("production channel is not one unconditional branch")
        return {
            "channel_id": channel["id"],
            "branch_id": branches[0]["id"],
            "branch_name": "production",
        }
    except (KeyError, TypeError, IndexError, AttributeError):
        raise PublishError("production channel metadata invalid") from None


def validate_environment(payload):
    try:
        if "errors" in payload:
            raise PublishError("EAS environment query failed")
        project = payload["data"]["app"]["byId"]
        if project["id"] != PROJECT:
            raise PublishError("EAS environment project differs")
        variables = project["environmentVariablesIncludingSensitive"]
        shared = project["ownerAccount"]["environmentVariablesIncludingSensitive"]
        if (
            not isinstance(variables, list)
            or not isinstance(shared, list)
            or len(variables) + len(shared) > 1000
        ):
            raise PublishError("EAS environment inventory unavailable")
        result = {}
        for item in [*variables, *shared]:
            name = item["name"]
            if (
                not isinstance(name, str)
                or name not in FIXED_APP_ENV
                or name in result
                or item.get("type") != "STRING"
                or item.get("visibility") not in ("PUBLIC", "SENSITIVE")
                or item.get("value") != FIXED_APP_ENV[name]
            ):
                raise PublishError("unreviewed EAS environment input")
            result[name] = item["value"]
        return result
    except (KeyError, TypeError, AttributeError):
        raise PublishError("EAS environment metadata invalid") from None


def validate_update(value, sha):
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise PublishError("exactly one iOS update required")
    item = value[0]
    if (
        not identifier(item.get("id"))
        or not identifier(item.get("group"))
        or item.get("runtimeVersion") != RUNTIME
        or item.get("platform") != "ios"
        or item.get("branch") != "production"
        or item.get("gitCommitHash") != sha
        or item.get("isRollBackToEmbedded") is not False
        or item.get("message") != "trusted OTA " + sha
    ):
        raise PublishError("published update identity differs")
    return {"sha": sha, "group_id": item["group"], "update_id": item["id"]}


def environment(token):
    # Never inherit NODE_OPTIONS, NODE_PATH, shell init files, CA/proxy overrides,
    # dotenv, npm hooks, credentials or native plugin switches from the runner.
    result = {
        **GIT_ENV,
        "PATH": str(NODE.parent) + ":/usr/bin:/bin",
        "HOME": "/root",
        "CI": "1",
        "NODE_ENV": "production",
        "NO_COLOR": "1",
        "EXPO_NO_TELEMETRY": "1",
        **FIXED_APP_ENV,
    }
    if token is not None:
        result["EXPO_TOKEN"] = token
    return result


def vendor_admission(adapter):
    """Read-only vendor admission. No export, server RPC, or vendor update."""
    phase_call("gate-before", adapter.gate)
    phase_call("source-before", adapter.validate_source)
    base = phase_call("baseline", adapter.eas, ["build:view", NATIVE_BUILD, "--json"], "baseline")
    args = [
        "build:list",
        "--platform",
        "ios",
        "--status",
        "finished",
        "--runtime-version",
        RUNTIME,
        "--channel",
        "production",
        "--limit",
        "50",
        "--offset",
        "0",
        "--json",
        "--non-interactive",
    ]
    cohort = phase_call("cohort", adapter.eas, args, "cohort")
    if not isinstance(cohort, list) or len(cohort) > 50:
        raise PhaseError("cohort", "metadata_invalid")
    if len(cohort) == 50:
        second = phase_call("cohort-next", adapter.eas,
            [
                *args[: args.index("--offset") + 1],
                "50",
                *args[args.index("--offset") + 2 :],
            ],
            "cohort-next",
        )
        if not isinstance(second, list):
            raise PhaseError("cohort-next", "metadata_invalid")
        cohort = cohort + second
    fingerprint = phase_call("native-binding", validate_builds, base, cohort)
    channel_args = [
        "channel:view",
        "production",
        "--limit",
        "50",
        "--offset",
        "0",
        "--json",
        "--non-interactive",
    ]
    mapping = phase_call("channel-binding", validate_channel,
                         phase_call("channel-before", adapter.eas, channel_args, "channel-before"))
    remote_environment = phase_call("environment", adapter.environment)
    return fingerprint, mapping, remote_environment, channel_args


def publish(adapter, sha):
    fingerprint, mapping, remote_environment, channel_args = vendor_admission(adapter)
    phase_call("export", adapter.export)
    phase_call("source-after", adapter.validate_source)
    proof = phase_call("artifact", adapter.artifact)
    claim = {
        "sha": sha,
        "project": PROJECT,
        "runtime": RUNTIME,
        "platform": "ios",
        "channel": "production",
        "branch_id": mapping["branch_id"],
        "branch_name": mapping["branch_name"],
        "artifact": proof,
    }
    adapter.write("ota-claim.json", claim)
    adapter.write(
        "ota-preflight.json",
        {"sha": sha, "native_fingerprint": fingerprint, "mapping": mapping},
    )
    adapter.gate()
    if (
        validate_channel(adapter.eas(channel_args, "channel-preclaim")) != mapping
        or adapter.environment() != remote_environment
        or adapter.artifact() != proof
    ):
        raise PublishError("prepublication inputs changed")
    if adapter.rpc("claim-ota", claim) != {"sha": sha, "state": "CLAIMED"}:
        raise PublishError("server OTA claim not confirmed")
    # Exactly one write opportunity. No retries around this call or any outcome.
    published = adapter.eas(
        [
            "update",
            "--channel",
            "production",
            "--platform",
            "ios",
            "--environment",
            "production",
            "--input-dir",
            str(ROOT / "artifact"),
            "--skip-bundler",
            "--json",
            "--non-interactive",
            "--message",
            "trusted OTA " + sha,
        ],
        "publish",
    )
    receipt = validate_update(published, sha)
    adapter.write("ota-vendor-receipt.json", receipt)
    readback = validate_update(
        adapter.eas(["update:view", receipt["group_id"], "--json"], "readback"), sha
    )
    if (
        readback != receipt
        or adapter.artifact() != proof
        or validate_channel(adapter.eas(channel_args, "channel-after")) != mapping
        or adapter.environment() != remote_environment
    ):
        raise PublishError("published update or channel changed")
    if adapter.rpc("finish-ota", receipt) != {"sha": sha, "state": "SUCCEEDED"}:
        raise PublishError("server manifest verification not confirmed")
    result = {
        **receipt,
        "state": "SUCCEEDED",
        "runtime": RUNTIME,
        "project": PROJECT,
        "channel": "production",
        "platform": "ios",
        "branch_id": mapping["branch_id"],
    }
    adapter.write("ota-receipt.json", result)
    return result


_PATH_ASSETS = frozenset({"publisher", "git_config", "ota_contract", "release_gate", "node", "eas", "expo", "cli_lock", "eas_package"})
_PATH_VIOLATIONS = frozenset({"owner", "writable", "kind", "hardlink"})


class PathTrustError(PublishError):
    def __init__(self, asset, depth, violation):
        super().__init__("root-owned publisher path required")
        self.diagnostic = None
        if isinstance(asset, str) and asset in _PATH_ASSETS and type(depth) is int and 0 <= depth <= 32 and isinstance(violation, str) and violation in _PATH_VIOLATIONS:
            self.diagnostic = {"asset": asset, "ancestor_depth": depth, "violation": violation}


def secure(path, *, private=False, asset=None):
    path = Path(path)
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        kind = stat.S_ISREG if item == path else stat.S_ISDIR
        violation = ("owner" if info.st_uid != 0 else
                     "writable" if info.st_mode & 0o022 else
                     "kind" if not kind(info.st_mode) else
                     "hardlink" if item == path and info.st_nlink != 1 else None)
        if violation:
            depth = 0 if item == path else list(path.parents).index(item) + 1
            raise PathTrustError(asset, depth, violation)
    if private and stat.S_IMODE(info.st_mode) != 0o600:
        raise PublishError("private publisher file requires mode 0600")


def private_file(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, "wb")


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Adapter:
    def __init__(self, sha, contract, token):
        self.sha = sha
        self.contract = contract
        self.token = token

    def run(self, args, tag, *, data=None, with_token=False, timeout=120):
        out_path = ROOT / (tag + ".stdout")
        err_path = ROOT / (tag + ".stderr")
        try:
            with private_file(out_path) as output, private_file(err_path) as error:
                try:
                    result = subprocess.run(
                        args,
                        env=environment(self.token if with_token else None),
                        cwd=SOURCE / "mobile",
                        input=data,
                        stdin=subprocess.DEVNULL if data is None else None,
                        stdout=output,
                        stderr=error,
                        check=False,
                        timeout=timeout,
                    )
                finally:
                    output.flush()
                    os.fsync(output.fileno())
                    error.flush()
                    os.fsync(error.fileno())
                    fsync_directory(ROOT)
            fsync_directory(ROOT)
            if result.returncode != 0:
                raise CommandError("command_failed")
            with out_path.open("rb") as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise PublishError("command output exceeds bound")
            return raw
        except subprocess.TimeoutExpired:
            raise CommandError("command_timeout") from None
        except (OSError, subprocess.SubprocessError):
            raise CommandError("command_unavailable") from None

    def gate(self):
        # Each invocation gets a unique read-only log name; publication is never repeated.
        suffix = "before" if not (ROOT / "gate-before.stdout").exists() else "preclaim"
        self.run(
            [
                "/usr/bin/python3",
                "-I",
                "-S",
                "-B",
                str(SOURCE / "scripts/trusted_release_gate.py"),
                "--sha",
                self.sha,
                "--workflow-sha",
                self.sha,
            ],
            "gate-" + suffix,
        )

    def validate_source(self):
        self.contract.validate_source(SOURCE, self.sha)

    def eas(self, args, tag):
        raw = self.run([str(NODE), str(EAS), *args], tag, with_token=True,
                       timeout=1800 if tag == "publish" else 180)
        try:
            return parsed(raw)
        except PublishError:
            if tag + "-json" in DIAGNOSTIC_PHASES:
                raise PhaseError(tag + "-json", "metadata_invalid") from None
            raise

    def export(self):
        if os.path.lexists(ROOT / "artifact"):
            raise PublishError("export already attempted")
        self.run(
            [
                str(NODE),
                str(EXPO),
                "export",
                "--platform",
                "ios",
                "--output-dir",
                str(ROOT / "artifact"),
                "--dump-assetmap",
                "--source-maps",
            ],
            "export",
            timeout=900,
        )

    def artifact(self):
        proof = self.contract.artifact(ROOT / "artifact")
        self.contract.validate_proof(proof)
        return proof

    def write(self, name, value):
        with private_file(ROOT / name) as stream:
            stream.write(json.dumps(value, sort_keys=True).encode())
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(ROOT)

    def rpc(self, name, value):
        # No caller-selected hosts, config, identity agent or environment forwarding.
        command = [
            "/usr/bin/ssh",
            "-F",
            "/dev/null",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(ROOT / "known_hosts"),
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-i",
            str(ROOT / "key"),
            "root@39.98.206.178",
            name + " " + self.sha,
        ]
        return parsed(
            self.run(
                command,
                name,
                data=json.dumps(value, sort_keys=True).encode(),
                timeout=900,
            )
        )

    def environment(self):
        query = """query TrustedOTAEnvironment($appId: String!, $environment: EnvironmentVariableEnvironment) {
          app { byId(appId: $appId) { id
            environmentVariablesIncludingSensitive(environment: $environment) { name value type visibility }
            ownerAccount { environmentVariablesIncludingSensitive(environment: $environment) { name value type visibility } }
          } }
        }"""

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise PublishError("environment redirect forbidden")

        defaults = ssl.get_default_verify_paths()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cafile = (
            defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
        )
        capath = (
            defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
        )
        if not cafile and not capath:
            raise PublishError("system TLS trust unavailable")
        context.load_verify_locations(cafile=cafile, capath=capath)
        client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
        )
        req = urllib.request.Request(
            "https://api.expo.dev/graphql",
            data=json.dumps(
                {
                    "query": query,
                    "variables": {"appId": PROJECT, "environment": "production"},
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.token,
                "Cache-Control": "no-cache",
                "User-Agent": "reva-trusted-ota/1.0",
            },
            method="POST",
        )
        try:
            with client.open(req, timeout=20) as response:
                if response.status != 200:
                    raise PublishError("environment query unavailable")
                return validate_environment(parsed(response.read(2_000_001)))
        except Exception:
            raise PublishError(
                "production environment verification unavailable"
            ) from None


def context(sha, *, require_credentials=True):
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or sys.executable not in ("/usr/bin/python3", "/usr/bin/python3.12")
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or re.fullmatch("[a-f0-9]{40}", sha) is None
        or Path(__file__).absolute() != SOURCE / "scripts/trusted_ota_publish.py"
    ):
        raise PublishError("fixed isolated root hosted publisher required")
    for asset, path in (
        ("publisher", Path(__file__).absolute()),
        ("git_config", SOURCE / ".git/config"),
        ("ota_contract", SOURCE / "scripts/trusted_ota.py"),
        ("release_gate", SOURCE / "scripts/trusted_release_gate.py"),
        ("node", NODE),
        ("eas", EAS),
        ("expo", EXPO),
        ("cli_lock", SOURCE / "scripts/release-tools/package-lock.json"),
        ("eas_package", SOURCE / "scripts/release-tools/node_modules/eas-cli/package.json"),
    ):
        secure(path, asset=asset)
    if require_credentials:
        for path in (ROOT / "key", ROOT / "known_hosts"):
            secure(path, private=True)
    if os.path.lexists(SOURCE / "scripts/__pycache__") or os.path.lexists(
        SOURCE / ".git/commondir"
    ):
        raise PublishError("cached code or shared checkout forbidden")
    # Check the executable helper bytes before importing; no checkout-selected
    # filters, replace refs, caller environment or mutable module search path.
    for name in ("trusted_ota_publish.py", "trusted_ota.py", "trusted_release_gate.py"):
        expected = subprocess.run(
            [
                "/usr/bin/git",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(SOURCE),
                "show",
                sha + ":scripts/" + name,
            ],
            env=GIT_ENV,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
        if (SOURCE / "scripts" / name).read_bytes() != expected:
            raise PublishError("publisher code differs from reviewed commit")
    package = parsed(
        (
            SOURCE / "scripts/release-tools/node_modules/eas-cli/package.json"
        ).read_bytes()
    )
    lock = parsed((SOURCE / "scripts/release-tools/package-lock.json").read_bytes())
    if (
        package.get("version") != "23.2.0"
        or lock["packages"]["node_modules/eas-cli"]["version"] != "23.2.0"
    ):
        raise PublishError("locked vendor CLI required")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location(
        "reviewed_ota_contract", SOURCE / "scripts/trusted_ota.py"
    )
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    if (
        contract.PROJECT,
        contract.RUNTIME,
        contract.NATIVE_SHA,
        contract.NATIVE_BUILD,
    ) != (PROJECT, RUNTIME, NATIVE_SHA, NATIVE_BUILD):
        raise PublishError("publisher contract differs")
    return contract



# Diagnostic output is selected from closed constants, never exception payloads.
_CONTEXT_REASONS = {
    "fixed isolated root hosted publisher required": "publisher_execution_context_invalid",
    "root-owned publisher path required": "publisher_path_untrusted",
    "cached code or shared checkout forbidden": "publisher_cached_or_shared_source",
    "publisher code differs from reviewed commit": "publisher_code_mismatch",
    "locked vendor CLI required": "publisher_cli_version_mismatch",
    "publisher contract differs": "publisher_contract_mismatch",
}
_SOURCE_REASONS = {
    "wrong source revision": "runtime_source_revision_mismatch",
    "dirty runtime source": "runtime_source_dirty",
    "native or unknown mobile input changed": "native_source_incompatible",
    "runtime/project binding differs": "native_runtime_binding_mismatch",
}


class PreflightError(PublishError):
    def __init__(self, phase, reason, diagnostic=None):
        super().__init__("publisher preflight blocked")
        self.diagnostic = diagnostic
        self.phase = phase
        self.reason = reason


def preflight(sha):
    """Check real publisher/source admission without keys, network or claims."""
    try:
        contract = context(sha, require_credentials=False)
    except Exception as exc:
        reason = (_CONTEXT_REASONS.get(str(exc))
                  if isinstance(exc, PublishError) else None)
        raise PreflightError("publisher_context", reason or "publisher_context_unavailable",
                             exc.diagnostic if isinstance(exc, PathTrustError) else None) from None
    try:
        contract.validate_source(SOURCE, sha)
    except Exception as exc:
        reason = _SOURCE_REASONS.get(str(exc)) if isinstance(exc, ValueError) else None
        raise PreflightError("native_source", reason or "native_source_unavailable") from None
    return contract


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--admission", action="store_true")
    args = parser.parse_args()
    preflight(args.sha)
    if args.preflight:
        print(json.dumps({"state": "PREFLIGHT_PASSED", "phase": "native_source",
                          "reason": "context_and_source_verified"}, sort_keys=True))
        return
    # Publication still rechecks every original context constraint, including
    # private root-owned key files, after the credential-free preflight.
    try:
        contract = phase_call("private-context", context, args.sha,
                              require_credentials=not args.admission)
        token = os.environ.get("EXPO_TOKEN", "")
        if not token or len(token) > 8192 or any(c.isspace() for c in token):
            raise PhaseError("credential", "operation_failed")
        adapter = Adapter(args.sha, contract, token)
        if args.admission:
            vendor_admission(adapter)
            result = diagnostic(args.sha, "ADMISSION_PASSED", "admission", "verified")
            persist_diagnostic(result)
        else:
            result = phase_call("publication", publish, adapter, args.sha)
    except PhaseError as exc:
        result = diagnostic(args.sha, "BLOCKED", exc.phase, exc.reason)
        # Even if durable audit cannot be created, emit only the safe closed object.
        print(json.dumps(result, sort_keys=True), file=sys.stderr)
        try:
            persist_diagnostic(result)
        except Exception:
            print('{"state":"BLOCKED","reason":"diagnostic_persistence_unavailable"}', file=sys.stderr)
        raise
    print(json.dumps(result, sort_keys=True))


def cli():
    try:
        main()
    except PreflightError as exc:
        result = {"state": "BLOCKED", "phase": exc.phase, "reason": exc.reason}
        if exc.diagnostic is not None:
            # Revalidate the closed schema at the output boundary as well.
            value = exc.diagnostic
            if (isinstance(value, dict) and set(value) == {"asset", "ancestor_depth", "violation"}
                    and isinstance(value["asset"], str) and value["asset"] in _PATH_ASSETS
                    and isinstance(value["violation"], str) and value["violation"] in _PATH_VIOLATIONS
                    and type(value["ancestor_depth"]) is int and 0 <= value["ancestor_depth"] <= 32):
                result["path_diagnostic"] = value
        print(json.dumps(result, sort_keys=True), file=sys.stderr)
        return 1
    except PhaseError:
        return 1
    except Exception:
        print(json.dumps({"state": "BLOCKED", "phase": "publication",
                          "reason": "publication_failed_retain_evidence_no_retry"},
                         sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
