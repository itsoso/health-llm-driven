"""Read-only evidence for the 274 mixed release. Never grants upload permission.

Fixed incident identity is necessary but insufficient: live GitHub and Expo
evidence, canonical source hashes and the original server claims must all agree.
Secrets remain in memory; no vendor create, submit, restart or cleanup exists here.
"""
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "itsoso/health-llm-driven"
RUN = {"id": 37116403140, "run_attempt": 1, "workflow_id": 352404554,
       "path": ".github/workflows/trusted-release.yml", "head_branch": "main",
       "head_sha": "514c8c28a87ad5761a6f66b284c19a69dff33e8f",
       "event": "workflow_dispatch", "status": "completed", "conclusion": "failure"}
JOB_IDS = {"preflight": 111183965068, "build-permission": 111183994381,
           "ios-build": 111184079510, "backend": 111184079533,
           "testflight": 111185249225, "release-result": 111185422034}
JOB_RESULTS = {name: "success" if name in {"preflight", "build-permission", "ios-build"}
               else "failure" for name in JOB_IDS}
STEPS = {
    "preflight": {"Materialize canonical source and check exact CI without production credentials": "success"},
    "build-permission": {"Check actual server readiness without consuming authorization": "success"},
    "ios-build": {"Claim one build in this job before every vendor create attempt": "success",
                  "Build once without uploading to Apple": "success"},
    "backend": {"Start the fixed server-side release capability": "failure"},
    "testflight": {"Claim one-time TestFlight upload permission before exposing vendor credentials": "failure",
                   "Revalidate and upload the exact finished build": "skipped"},
    "release-result": {"Join backend deployment and TestFlight upload outcomes": "failure"},
}
BUILD = {"id": "63b61a31-058c-44e5-bb82-67727ca7d073", "gitCommitHash": RUN["head_sha"],
         "status": "FINISHED", "platform": "IOS", "distribution": "STORE",
         "buildProfile": "production", "appIdentifier": "life.executor.health",
         "appVersion": "1.3.4", "appBuildVersion": "274", "isForIosSimulator": False,
         "app": {"id": "911ea84f-bc7e-4a12-90cf-33966b6f7398"}, "submissions": []}
HASHES = {
    ".github/workflows/trusted-release.yml": "31bffd5121410fdd612405d763ee13a0c4cd5085b75e7853c7724df1694bd08c",
    "scripts/trusted_eas_build.py": "c669e95caaa626a9e62cb24251a22d710b73b4211fa1e2ef52a969b2f916154a",
    "scripts/trusted_release_server.py": "48b0dae34bf990b18d7ca29dd3f9765b9d7b4ed1a5ad0cb429e93d39956bdc65",
    "scripts/release-tools/package-lock.json": "8783ead6d1744795c34191e5dd2d191af45db0427b3ec103ab9fb72dcf79e333",
    "mobile/eas.json": "5bc3d2a782228051e4fd5348a56a08628c41f6cc73773684f455ca9efa39d51f",
    "mobile/app.json": "78b28864c418b3760222bcbf7f8481f493fd9fc198181c1c23040397c210706a",
}
LOG_HASH = "6ebf2b921b54225dfc62b6aec59014c92213a7a367981bbcfc2fca73b629ba3d"
JOBS_HASH = "c9321070532105cf367379484031d45d2eee6872b675efc242a55f1858b4c0df"
BASE = "https://api.github.com/repos/" + REPOSITORY
EXPO = "https://api.expo.dev/graphql"
QUERY = """query($buildId: ID!) { builds { byId(buildId: $buildId) {
 id gitCommitHash status platform distribution buildProfile appIdentifier
 appVersion appBuildVersion isForIosSimulator app { id } submissions { id }
} } }"""


class ProofError(Exception):
    """Static errors only; never include HTTP bodies, URLs or credentials."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProofError("duplicate evidence field")
        result[key] = value
    return result


def validate(run, jobs, build, log):
    if (not isinstance(run, dict) or any(run.get(k) != v for k, v in RUN.items())
            or any(not isinstance(run.get(k), dict) or run[k].get("full_name") != REPOSITORY
                   for k in ("repository", "head_repository"))):
        raise ProofError("mixed release workflow differs")
    if not isinstance(jobs, dict) or jobs.get("total_count") != 6 or not isinstance(jobs.get("jobs"), list) or len(jobs["jobs"]) != 6:
        raise ProofError("mixed release jobs incomplete")
    current = {}
    for job in jobs["jobs"]:
        if not isinstance(job, dict) or job.get("name") not in JOB_IDS or job["name"] in current:
            raise ProofError("mixed release jobs ambiguous")
        name = job["name"]
        expected = {"id": JOB_IDS[name], "run_id": RUN["id"], "head_sha": RUN["head_sha"],
                    "run_attempt": 1, "status": "completed", "conclusion": JOB_RESULTS[name]}
        if any(job.get(k) != v for k, v in expected.items()):
            raise ProofError("mixed release job not terminal")
        steps = {}
        if not isinstance(job.get("steps"), list) or len(job["steps"]) > 64:
            raise ProofError("mixed release steps missing")
        for step in job["steps"]:
            if not isinstance(step, dict) or not isinstance(step.get("name"), str) or step["name"] in steps or step.get("status") != "completed":
                raise ProofError("mixed release steps ambiguous")
            steps[step["name"]] = step.get("conclusion")
        if any(steps.get(k) != v for k, v in STEPS[name].items()):
            raise ProofError("mixed release vendor boundary differs")
        current[name] = {**expected, "steps": steps}
    if build != BUILD or type(build.get("isForIosSimulator")) is not bool:
        raise ProofError("exact finished unsubmitted artifact required")
    try:
        body = [re.sub(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ", "", s) for s in log.decode().splitlines()]
    except (AttributeError, UnicodeError):
        raise ProofError("invalid build log") from None
    link = "https://expo.dev/accounts/itsoso/projects/health-pilot/builds/" + BUILD["id"]
    if sum(link in line and not line.startswith((" ", "echo", "printf")) for line in body) != 1:
        raise ProofError("vendor build log identity missing")
    return {"profile": "finished-build-unuploaded-v1", "failed_sha": RUN["head_sha"],
            "run_id": RUN["id"], "run_attempt": 1, "build_id": BUILD["id"],
            "build": build, "canonical_hashes": HASHES, "jobs_sha256": digest(current),
            "log_sha256": hashlib.sha256(log).hexdigest()}


def validate_history(value, failed_sha):
    fixed = {"profile": "finished-build-unuploaded-v1", "failed_sha": RUN["head_sha"],
             "run_id": RUN["id"], "run_attempt": 1, "build_id": BUILD["id"],
             "build": BUILD, "canonical_hashes": HASHES}
    if (failed_sha != RUN["head_sha"] or not isinstance(value, dict)
            or set(value) != set(fixed) | {"jobs_sha256", "log_sha256"}
            or any(value.get(k) != v for k, v in fixed.items())
            or value.get("log_sha256") != LOG_HASH or value.get("jobs_sha256") != JOBS_HASH
            or any(not isinstance(value.get(k), str) or re.fullmatch(r"[0-9a-f]{64}", value[k]) is None
                   for k in ("jobs_sha256", "log_sha256"))):
        raise ProofError("invalid built artifact history")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read(url, headers, *, payload=None, log=False):
    # Ignore caller SSL_CERT_FILE/SSL_CERT_DIR overrides just as the other
    # isolated release operators do; use the compiled system trust locations.
    defaults = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    capath = defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath:
        raise ProofError("system TLS trust unavailable")
    context.load_verify_locations(cafile=cafile, capath=capath)
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    headers = {"User-Agent": "reva-release-evidence/1.0", **headers}
    try:
        try:
            response = client.open(urllib.request.Request(url, data=payload, headers=headers), timeout=20)
        except urllib.error.HTTPError as error:
            if not log or error.code != 302:
                raise
            target = error.headers.get("Location", "")
            p = urllib.parse.urlsplit(target)
            if (p.scheme != "https" or re.fullmatch(r"productionresultssa[0-9]+\.blob\.core\.windows\.net", p.hostname or "") is None
                    or p.username or p.password or p.port not in (None, 443) or p.fragment):
                raise ProofError("untrusted log redirect")
            # Never forward the GitHub credential to signed storage.
            response = client.open(urllib.request.Request(target), timeout=20)
        with response:
            data = response.read(2_000_001)
            if response.status != 200 or len(data) > 2_000_000:
                raise ProofError("vendor evidence bound exceeded")
            return data
    except Exception:
        raise ProofError("vendor evidence unavailable") from None


def collect(github_token, expo_session, source):
    for path, expected in HASHES.items():
        if hashlib.sha256((source / path).read_bytes()).hexdigest() != expected:
            raise ProofError("failed release canonical code differs")
    headers = {"Authorization": "Bearer " + github_token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache"}
    run_url = BASE + "/actions/runs/" + str(RUN["id"])
    def parsed(url):
        return json.loads(read(url, headers), object_pairs_hook=unique)
    run = parsed(run_url)
    jobs = parsed(run_url + "/attempts/1/jobs?per_page=100")
    log = read(BASE + "/actions/jobs/" + str(JOB_IDS["ios-build"]) + "/logs", headers, log=True)
    raw = read(EXPO, {"expo-session": expo_session, "Content-Type": "application/json"},
               payload=json.dumps({"query": QUERY, "variables": {"buildId": BUILD["id"]}}).encode())
    result = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(result, dict) or result.get("errors") or result.get("data") is None:
        raise ProofError("Expo artifact evidence unavailable")
    try:
        proof = validate(run, jobs, result["data"]["builds"]["byId"], log)
    except (KeyError, TypeError):
        raise ProofError("Expo artifact evidence malformed") from None
    if proof["log_sha256"] != LOG_HASH or parsed(run_url) != run:
        raise ProofError("reviewed vendor evidence changed")
    validate_history(proof, RUN["head_sha"])
    return proof
