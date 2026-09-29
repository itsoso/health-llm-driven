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
RUNTIME = "1.3.4"
NATIVE_SHA = "cad1fd1d33621532e587b265e79f737dfb06d1fe"
NATIVE_BUILD = "bfdd2bc9-db49-4ccd-bfbc-679287be4855"
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


def publish(adapter, sha):
    adapter.gate()
    adapter.validate_source()
    base = adapter.eas(["build:view", NATIVE_BUILD, "--json"], "baseline")
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
    cohort = adapter.eas(args, "cohort")
    if not isinstance(cohort, list) or len(cohort) > 50:
        raise PublishError("native cohort page is invalid")
    if len(cohort) == 50:
        second = adapter.eas(
            [
                *args[: args.index("--offset") + 1],
                "50",
                *args[args.index("--offset") + 2 :],
            ],
            "cohort-next",
        )
        if not isinstance(second, list):
            raise PublishError("native cohort second page invalid")
        cohort = cohort + second
    fingerprint = validate_builds(base, cohort)
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
    mapping = validate_channel(adapter.eas(channel_args, "channel-before"))
    remote_environment = adapter.environment()
    adapter.export()
    adapter.validate_source()
    proof = adapter.artifact()
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


def secure(path, *, private=False):
    path = Path(path)
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        kind = stat.S_ISREG if item == path else stat.S_ISDIR
        if (
            info.st_uid != 0
            or info.st_mode & 0o022
            or not kind(info.st_mode)
            or (item == path and info.st_nlink != 1)
        ):
            raise PublishError("root-owned publisher path required")
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
                raise PublishError("isolated command failed; outcome must be inspected")
            with out_path.open("rb") as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise PublishError("command output exceeds bound")
            return raw
        except (OSError, subprocess.SubprocessError):
            raise PublishError(
                "isolated command outcome unavailable; retry forbidden"
            ) from None

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
        return parsed(
            self.run(
                [str(NODE), str(EAS), *args],
                tag,
                with_token=True,
                timeout=1800 if tag == "publish" else 180,
            )
        )

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


def context(sha):
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
    for path in (
        Path(__file__).absolute(),
        SOURCE / ".git/config",
        SOURCE / "scripts/trusted_ota.py",
        SOURCE / "scripts/trusted_release_gate.py",
        NODE,
        EAS,
        EXPO,
        SOURCE / "scripts/release-tools/package-lock.json",
        SOURCE / "scripts/release-tools/node_modules/eas-cli/package.json",
    ):
        secure(path)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    contract = context(args.sha)
    token = os.environ.get("EXPO_TOKEN", "")
    if not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise PublishError("private Expo credential required")
    result = publish(Adapter(args.sha, contract, token), args.sha)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Trusted OTA blocked; retain original claim and vendor evidence, never retry publication",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
