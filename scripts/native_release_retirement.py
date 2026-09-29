"""Close the audited legacy native-only upload without inventing backend success.

The fixed legacy profile is deliberately narrow. A root operator at a reviewed,
CI-green canonical source performs inspect -> matching digest -> durable intent
and completion. Old claims, locks and installation bytes are never rewritten.
A consumed or interrupted closure is never resumed. This certifies a completed
vendor upload, not Apple processing, TestFlight availability or App Review.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

OLD_SHA = "cad1fd1d33621532e587b265e79f737dfb06d1fe"
RUN_ID = 36111598240
WORKFLOW_ID = 352404554
REPOSITORY = "itsoso/health-llm-driven"
BUILD_ID = "bfdd2bc9-db49-4ccd-bfbc-679287be4855"
SUBMISSION_ID = "8c5680dc-6719-455e-9c3e-6fd3bbbfeb7b"
ROOT = Path("/var/lib/reva-release")
ROOT_NAME = "native-only-closures"
TERMINAL = "CLOSED_NATIVE_ONLY_VENDOR_UPLOAD"
BASE = "https://api.github.com/repos/" + REPOSITORY
ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_NO_REPLACE_OBJECTS": "1",
}
CANONICAL_HASHES = {
    ".github/workflows/trusted-release.yml": "3f37eab8434236bb53cb7a36d2cb98ba48a522bb3755085867c8c189f2bfe0d1",
    "scripts/trusted_eas_build.py": "c669e95caaa626a9e62cb24251a22d710b73b4211fa1e2ef52a969b2f916154a",
    "scripts/trusted_release_server.py": "2813c7da51a7098db2d193b126384397baa6d3044e0fd966a59852dfa26e18b6",
}
# Attested log bytes are fixed evidence, not an exemption from live GH checks.
LOG_SHA256 = "9c81c0783e9b560a39915a9963b765a7e2196866312f714fbf40b32903e3d9c4"
JOB_IDS = {
    "preflight": 107997785323,
    "ios-build": 107997785532,
    "build-permission": 107997786281,
    "backend": 107997786681,
    "testflight": 108000349684,
    "release-result": 108001520095,
}
JOB_NAMES = set(JOB_IDS)
BUILD_STEP = "Build once without uploading to Apple"
REQUIRED_STEPS = {
    "preflight": (
        "Materialize canonical source and check exact CI without production credentials",
    ),
    "build-permission": (
        "Check actual server readiness without consuming authorization",
    ),
    "ios-build": (
        "Claim one build in this job before every vendor create attempt",
        BUILD_STEP,
    ),
    "testflight": (
        "Claim one-time TestFlight upload permission before exposing vendor credentials",
        "Revalidate and upload the exact finished build",
    ),
    "release-result": ("Join backend deployment and TestFlight upload outcomes",),
}


class RetirementError(Exception):
    """Fixed, secret-free operator diagnostics."""


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RetirementError("duplicate metadata field")
        result[key] = value
    return result


def json_value(raw):
    return json.loads(raw, object_pairs_hook=unique)


def jobs_map(value):
    if (
        not isinstance(value, dict)
        or value.get("total_count") != 6
        or not isinstance(value.get("jobs"), list)
        or len(value["jobs"]) != 6
        or any(not isinstance(j, dict) for j in value["jobs"])
    ):
        raise RetirementError("incomplete native workflow jobs")
    jobs = {j.get("name"): j for j in value["jobs"]}
    if set(jobs) != JOB_NAMES or len(jobs) != 6:
        raise RetirementError("unexpected native workflow jobs")
    if any(j.get("status") != "completed" for j in jobs.values()):
        raise RetirementError("native workflow jobs not terminal")
    return jobs


def steps_map(job):
    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise RetirementError("invalid native steps")
    result = {s.get("name"): s for s in steps}
    if len(result) != len(steps):
        raise RetirementError("duplicate native steps")
    return result


def validate_vendor(run, jobs, prior, log):
    expected = {
        "id": RUN_ID,
        "run_attempt": 2,
        "workflow_id": WORKFLOW_ID,
        "path": ".github/workflows/trusted-release.yml",
        "head_sha": OLD_SHA,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
    }
    if (
        not isinstance(run, dict)
        or any(run.get(k) != v for k, v in expected.items())
        or any(
            not isinstance(run.get(k), dict) or run[k].get("full_name") != REPOSITORY
            for k in ("repository", "head_repository")
        )
    ):
        raise RetirementError("exact native workflow terminal required")
    current = jobs_map(jobs)
    first = jobs_map(prior)
    for name, job in current.items():
        if job.get("id") != JOB_IDS[name] or job.get("conclusion") != (
            "skipped" if name == "backend" else "success"
        ):
            raise RetirementError("native-only job identity or terminal differs")
        steps = steps_map(job)
        for required in REQUIRED_STEPS.get(name, ()):
            if (
                steps.get(required, {}).get("conclusion") != "success"
                or steps[required].get("status") != "completed"
            ):
                raise RetirementError("native vendor step did not succeed")
    # Attempt 1 failed before vendor create. Never close a profile with an
    # uncertain earlier create/upload, even if a later rerun happens to pass.
    if (
        first["backend"].get("conclusion") != "skipped"
        or first["testflight"].get("conclusion") != "skipped"
        or first["ios-build"].get("conclusion") != "failure"
        or steps_map(first["ios-build"]).get(BUILD_STEP, {}).get("conclusion")
        != "skipped"
    ):
        raise RetirementError("earlier native attempt may have reached vendor")
    try:
        lines = log.decode("utf-8").splitlines()
    except (UnicodeError, AttributeError):
        raise RetirementError("native vendor log invalid") from None
    # Anchored vendor stdout, not the displayed shell source/environment block.
    body = [
        re.sub(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ", "", line) for line in lines
    ]
    submission = (
        "Submission details: https://expo.dev/accounts/itsoso/projects/health-pilot/submissions/"
        + SUBMISSION_ID
    )
    if (
        body.count(BUILD_ID) != 1
        or body.count(submission) != 1
        or body.count("✔ Submitted your app to Apple App Store Connect!") != 1
        or body.count(
            "Your binary has been successfully uploaded to App Store Connect!"
        )
        != 1
    ):
        raise RetirementError("exact vendor build and upload terminal missing")
    return {
        "state": "VENDOR_UPLOAD_SUCCEEDED",
        "run_id": RUN_ID,
        "run_attempt": 2,
        "workflow_id": WORKFLOW_ID,
        "build_id": BUILD_ID,
        "submission_id": SUBMISSION_ID,
        "log_sha256": hashlib.sha256(log).hexdigest(),
        "jobs_sha256": digest(jobs),
        "prior_jobs_sha256": digest(prior),
        "canonical_hashes": CANONICAL_HASHES,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener():
    defaults = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = (
        defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    )
    capath = defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath:
        raise RetirementError("system TLS trust unavailable")
    context.load_verify_locations(cafile=cafile, capath=capath)
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )


def validate_log_redirect(url):
    part = urllib.parse.urlsplit(url)
    if (
        part.scheme != "https"
        or part.hostname != "productionresultssa18.blob.core.windows.net"
        or part.username is not None
        or part.password is not None
        or part.port not in (None, 443)
        or part.fragment
    ):
        raise RetirementError("unexpected GitHub log storage origin")
    return True


def read_url(url, token, *, logs=False):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reva-native-retirement",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    client = opener()
    try:
        try:
            response = client.open(
                urllib.request.Request(url, headers=headers), timeout=20
            )
        except urllib.error.HTTPError as error:
            if not logs or error.code != 302:
                raise
            location = error.headers.get("Location", "")
            validate_log_redirect(location)
            # Signed storage URL receives no GitHub token or caller headers.
            response = client.open(urllib.request.Request(location), timeout=20)
        with response:
            if response.status != 200:
                raise RetirementError("native metadata unavailable")
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise RetirementError("native metadata bound exceeded")
            return data
    except Exception:
        raise RetirementError("native GitHub evidence unavailable") from None


def vendor_evidence(token):
    run = json_value(read_url(BASE + f"/actions/runs/{RUN_ID}", token))
    jobs = json_value(
        read_url(BASE + f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100", token)
    )
    prior = json_value(
        read_url(BASE + f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100", token)
    )
    log = read_url(
        BASE + f"/actions/jobs/{JOB_IDS['testflight']}/logs", token, logs=True
    )
    proof = validate_vendor(run, jobs, prior, log)
    if proof["log_sha256"] != LOG_SHA256:
        raise RetirementError("reviewed native vendor log bytes differ")
    if json_value(read_url(BASE + f"/actions/runs/{RUN_ID}", token)) != run:
        raise RetirementError("native workflow changed during inspection")
    return proof


def workspace_evidence(b):
    workspace = b.STATE / OLD_SHA
    inventory = b._inventory(
        workspace,
        {
            "build-started.json",
            "native-started.json",
            "testflight-base.json",
            "build.lock",
        },
    )
    for name in ("build-started.json", "native-started.json"):
        if b._read_json(workspace / name) != {"sha": OLD_SHA, "state": "STARTED"}:
            raise RetirementError("native claim differs")
    proof = b._read_json(workspace / "testflight-base.json")
    if (
        not isinstance(proof, dict)
        or set(proof) != {"sha", "state", "production_sha"}
        or proof["sha"] != OLD_SHA
        or proof["state"] != "COMPATIBLE"
        or not isinstance(proof["production_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", proof["production_sha"]) is None
        or proof["production_sha"] == OLD_SHA
        or (workspace / "build.lock").read_bytes() != b""
    ):
        raise RetirementError("native-only production binding differs")
    return {"production_sha": proof["production_sha"], "inventory": inventory}


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def close_transaction(adapter, evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise RetirementError("closure already attempted; retry forbidden")
    adapter.check_record_parent()
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED_NATIVE_ONLY_UPLOAD", "evidence_sha256": fingerprint}
    if evidence_sha256 != fingerprint:
        raise RetirementError("native inspection evidence changed")
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        sync(adapter.record.parent.parent)
    adapter.check_record_parent()
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {
        **evidence,
        "evidence_sha256": fingerprint,
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    write_json(adapter.record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise RetirementError("native evidence changed after durable intent")
    write_json(
        adapter.record / "completed.json",
        {"state": TERMINAL, "old_sha": OLD_SHA, "intent_sha256": digest(intent)},
    )
    return {"state": TERMINAL, "sha": OLD_SHA, "receipt": receipt}


def private_directory(b, path):
    b.secure(path)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RetirementError("root-only native audit directory required")


def canonical_profile(b):
    source = b.canonical_source(OLD_SHA)
    for name, expected in CANONICAL_HASHES.items():
        b.secure(source / name)
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise RetirementError("native legacy executor profile differs")


def no_conflicts(b):
    for name in (
        "recoveries",
        "partial-laya-closures",
        "contained-release-closures",
        "unchanged-release-closures",
        "review-maintenance-closures",
        "lost-closure-receipt-acknowledgments",
        "contained-service-recoveries",
    ):
        if os.path.lexists(b.STATE / name / OLD_SHA):
            raise RetirementError("conflicting native closure history")


class Adapter:
    def __init__(self, b, source, closing_sha, token, check_locks, production_sha):
        self.b = b
        self.source = source
        self.closing_sha = closing_sha
        self.production_sha = production_sha
        self.token = token
        self.check_locks = check_locks
        self.record = b.STATE / ROOT_NAME / OLD_SHA

    def check_record_parent(self):
        if os.path.lexists(self.record.parent):
            private_directory(self.b, self.record.parent)
        else:
            self.b.secure(self.record.parent.parent)

    def inspect(self):
        b = self.b
        self.check_locks()
        no_conflicts(b)
        canonical_profile(b)
        if b.canonical_source(self.closing_sha) != self.source:
            raise RetirementError("closing source changed")
        b._assert_idle()
        b._recovery_process_proof()
        if os.path.lexists(b.BUSINESS_LEASE):
            raise RetirementError("business release lease present")
        installation = b._installation_evidence(OLD_SHA, b.CONFIG, b.INSTALLED.parent)
        workspace = workspace_evidence(b)
        b._recovery_production_proof(self.production_sha, self.source)
        vendor = vendor_evidence(self.token)
        authorized = b._recovery_file_identity(b.AUTHORIZED)
        locks = {
            "launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
            "build": b._recovery_file_identity(b.STATE / OLD_SHA / "build.lock"),
        }
        b._assert_idle()
        b._recovery_process_proof()
        self.check_locks()
        if os.path.lexists(b.BUSINESS_LEASE):
            raise RetirementError("business release lease appeared")
        return {
            "old_sha": OLD_SHA,
            "closing_sha": self.closing_sha,
            "production_sha": self.production_sha,
            "workspace": workspace,
            "installation": installation,
            "authorized": authorized,
            "locks": locks,
            "vendor": vendor,
        }


def closed_evidence(b, sha, receipt, *, historical=False):
    if sha != OLD_SHA:
        raise RetirementError("unsupported native legacy revision")
    no_conflicts(b)
    canonical_profile(b)
    record = b.STATE / ROOT_NAME / sha
    private_directory(b, record.parent)
    private_directory(b, record)
    b._inventory(record, {"intent.json", "completed.json"})
    intent = b._read_json(record / "intent.json")
    completed = b._read_json(record / "completed.json")
    required = {
        "old_sha",
        "closing_sha",
        "production_sha",
        "workspace",
        "installation",
        "authorized",
        "locks",
        "vendor",
        "evidence_sha256",
        "receipt_sha256",
    }
    if (
        not isinstance(intent, dict)
        or set(intent) != required
        or intent["old_sha"] != sha
        or not isinstance(intent["closing_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", intent["closing_sha"]) is None
        or intent["closing_sha"] == sha
        or intent["evidence_sha256"]
        != digest(
            {
                k: v
                for k, v in intent.items()
                if k not in {"evidence_sha256", "receipt_sha256"}
            }
        )
        or completed
        != {"state": TERMINAL, "old_sha": sha, "intent_sha256": digest(intent)}
    ):
        raise RetirementError("native closure intent or terminal invalid")
    if (
        not isinstance(receipt, str)
        or re.fullmatch("[a-f0-9]{64}", receipt) is None
        or not isinstance(intent["receipt_sha256"], str)
        or not secrets.compare_digest(
            hashlib.sha256(receipt.encode()).hexdigest(), intent["receipt_sha256"]
        )
    ):
        raise RetirementError("durably issued native closure receipt required")
    source = b.canonical_source(intent["closing_sha"])
    expected_vendor = {
        "state": "VENDOR_UPLOAD_SUCCEEDED",
        "run_id": RUN_ID,
        "run_attempt": 2,
        "workflow_id": WORKFLOW_ID,
        "build_id": BUILD_ID,
        "submission_id": SUBMISSION_ID,
        "log_sha256": LOG_SHA256,
        "canonical_hashes": CANONICAL_HASHES,
    }
    vendor = intent["vendor"]
    if (
        not isinstance(vendor, dict)
        or set(vendor) != set(expected_vendor) | {"jobs_sha256", "prior_jobs_sha256"}
        or any(vendor.get(k) != v for k, v in expected_vendor.items())
        or any(
            not isinstance(vendor[k], str)
            or re.fullmatch("[a-f0-9]{64}", vendor[k]) is None
            for k in ("jobs_sha256", "prior_jobs_sha256")
        )
    ):
        raise RetirementError("native vendor proof differs")
    if (
        workspace_evidence(b) != intent["workspace"]
        or not isinstance(intent["production_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", intent["production_sha"]) is None
    ):
        raise RetirementError("original native workspace changed")
    config, library = b._archives(sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = b.CONFIG, b.INSTALLED.parent
    if b._installation_evidence(sha, config, library) != intent["installation"]:
        raise RetirementError("native installation or revocation changed")
    if {
        "launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
        "build": b._recovery_file_identity(b.STATE / sha / "build.lock"),
    } != intent["locks"]:
        raise RetirementError("native original locks changed")
    if not historical:
        b._recovery_production_proof(intent["production_sha"], source)
        b._assert_idle()
        b._recovery_process_proof()
    return {
        "state": TERMINAL,
        "closure": digest(completed),
        "workspace": intent["workspace"],
    }


def context(sha):
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or "SSH_ORIGINAL_COMMAND" in os.environ
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or sys.executable != "/usr/bin/python3.12"
        or re.fullmatch("[a-f0-9]{40}", sha) is None
        or sha == OLD_SHA
    ):
        raise RetirementError("isolated canonical root operator required")
    source = ROOT / "bootstrap" / sha / "source"
    entry = source / "scripts/native_release_retirement.py"
    if Path(__file__).absolute() != entry:
        raise RetirementError("fixed canonical native operator required")
    for path in [
        *reversed(entry.parents),
        entry,
        entry.with_name("bootstrap_trusted_release.py"),
    ]:
        info = path.lstat()
        if (
            info.st_uid != 0
            or info.st_gid != 0
            or info.st_mode & 0o022
            or stat.S_ISLNK(info.st_mode)
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
            or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
        ):
            raise RetirementError("native canonical operator metadata unsafe")
    if os.path.lexists(entry.parent / "__pycache__"):
        raise RetirementError("cached native operator code forbidden")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location(
        "native_closing_bootstrap", entry.with_name("bootstrap_trusted_release.py")
    )
    b = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = b
    spec.loader.exec_module(b)
    if b.canonical_source(sha) != source:
        raise RetirementError("canonical native source differs")
    # Execute only fixed OS tools with replacement refs and environment config disabled.
    subprocess.run(
        [
            "/usr/bin/python3.12",
            "-I",
            "-S",
            "-B",
            str(source / "scripts/trusted_release_gate.py"),
            "--sha",
            sha,
            "--workflow-sha",
            sha,
        ],
        env=ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=90,
    )
    return b, source


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--production-sha", required=True)
    parser.add_argument("--evidence-sha256")
    args = parser.parse_args()
    b, source = context(args.sha)
    if re.fullmatch("[a-f0-9]{40}", args.production_sha) is None:
        raise RetirementError("exact current production SHA required")
    if (
        args.evidence_sha256 is not None
        and re.fullmatch("[a-f0-9]{64}", args.evidence_sha256) is None
    ):
        raise RetirementError("exact native evidence digest required")
    # Credentials are read only after the canonical operator/CI gate, never via
    # argv, developer checkout, environment hooks or a caller-selected file.
    raw = sys.stdin.read(8193)
    if len(raw) > 8192:
        raise RetirementError("credential input exceeds bound")
    secret = json_value(raw)
    if (
        not isinstance(secret, dict)
        or set(secret) != {"github_token"}
        or not isinstance(secret["github_token"], str)
        or not secret["github_token"]
        or any(c.isspace() for c in secret["github_token"])
    ):
        raise RetirementError("private read-only GitHub credential required")
    b.secure(b.STATE / "launcher.lock", private=True)
    fd = os.open(b.STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = b._acquire_existing_build_lock(OLD_SHA)
        if build_fd is None:
            raise RetirementError("original native build lock required")

        def check():
            b._assert_original_lock(b.STATE / "launcher.lock", fd)
            b._assert_original_lock(b.STATE / OLD_SHA / "build.lock", build_fd)

        result = close_transaction(
            Adapter(b, source, args.sha, secret["github_token"], check, args.production_sha),
            args.evidence_sha256,
        )
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Native retirement blocked; preserve original evidence and do not retry consumed closure",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
