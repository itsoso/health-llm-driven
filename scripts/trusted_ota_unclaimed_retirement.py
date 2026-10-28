"""Root-only, one-shot closure of one byte-bound unpublished OTA claim.

No vendor calls, deployment, backup, receipt replacement, or retry. Inspection
uses fresh official GitHub evidence; execution consumes its exact digest before
renaming the original business lease. An interrupted close remains blocked.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

FAILED_SHA = 'da91b5de303313f1fb014bbe045e8f1597d15229'
RUN_ID = 38509318595
RUN_ATTEMPT = 1
WORKFLOW_ID = 370218159
JOB_ID = 115673932021
ARTIFACT_ID = 11869725525
ARTIFACT_SIZE = 2533
ARTIFACT_ZIP_SHA256 = 'dba9fdf15b0098e982627210ea67f29a146d038729ccc2e405fb6230beb2050a'
ROOT_NAME = 'ota-preclaim-closures'
TERMINAL = 'CLOSED_UNPUBLISHED_CLAIM'
ROOT = Path('/var/lib/reva-release')
REPOSITORY = 'itsoso/health-llm-driven'
BASE = 'https://api.github.com/repos/' + REPOSITORY
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
SOURCE_HASHES = {
    '.github/workflows/trusted-ota.yml': '1bb9a097e82057a27196b2c90014f2c02b1665eb150a8808e2508af8823121dd',
    'scripts/trusted_ota_publish.py': '0f6bd54aafa366ed0553b80341835efd86ee41439409d69bde91be7ccdc22af2',
    'scripts/trusted_ota_server.py': 'a7d440420f76d6ed4ed610c162163b48c745ed5ae9ba0f5fd61bca6486a0a981',
    'scripts/trusted_ota.py': '5c740316ffdd8be5279cb1e8226007175c779ba14392eee2b0cb4fc0462c1e80',
}
ENTRY_DIGESTS = {
    'ota-diagnostic.json': 'dfaa9b03ff33c2a1fc6f966b27a4d2277d5349448c25b70dc4560ca75461c711',
    'ota-claim.json': 'c5e4f615a46153a56cb5fec2099786a116d561f25fa41284946e3a7b139f611c',
    'ota-preflight.json': '105dd122c6f7014ebdf66b4b9fe5b5b9eb28318c46258710d512eb4dc06453e1',
}
REQUIRED_STEPS = {
    'Materialize exact canonical source and verify current main CI before credentials': 'success',
    'Prepare exact OTA artifact without consuming a publication claim': 'skipped',
    'Publish one bound iOS artifact and verify server receipt': 'failure',
    'Stage validated OTA audit even when publication is incomplete': 'success',
    'Preserve OTA audit for same-receipt recovery': 'success',
}


class ClosureError(Exception):
    """Static diagnostics only; never tokens, signed URLs, or vendor output."""


# Defaults above remain the original da91 profile for legacy history and callers.
LEGACY_FAILED_SHA = FAILED_SHA
CURRENT_FAILED_SHA = '151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90'
F202_FAILED_SHA = 'f2022e10027bcf35c4225bf1cc898a9001161ecc'
C29D_FAILED_SHA = 'c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf'
A4D_FAILED_SHA = 'a4d922886c859f4a2a43d4322fd43d128bf934f3'
SUPPORTED_FAILED_SHAS = (
    LEGACY_FAILED_SHA, CURRENT_FAILED_SHA, F202_FAILED_SHA, C29D_FAILED_SHA,
    A4D_FAILED_SHA,
)
_SELECTED_PROFILE = None


def select_profile(failed_sha):
    """Select one reviewed, fixed profile per freshly loaded operator module.

    Only same-SHA selection is idempotent. No caller-provided evidence fields
    can alter a profile, and historical consumers select by operation dirname.
    """
    global _SELECTED_PROFILE, FAILED_SHA, RUN_ID, JOB_ID, ARTIFACT_ID
    global ARTIFACT_SIZE, ARTIFACT_ZIP_SHA256, ENTRY_DIGESTS, SOURCE_HASHES
    if failed_sha not in SUPPORTED_FAILED_SHAS or (
            _SELECTED_PROFILE is not None and _SELECTED_PROFILE != failed_sha):
        raise ClosureError('unknown or changed fixed OTA closure profile')
    if _SELECTED_PROFILE == failed_sha:
        return
    if failed_sha == CURRENT_FAILED_SHA:
        FAILED_SHA = CURRENT_FAILED_SHA
        RUN_ID = 39539354647
        JOB_ID = 119023297148
        ARTIFACT_ID = 12318856926
        ARTIFACT_SIZE = 2531
        ARTIFACT_ZIP_SHA256 = '3b466632b5a1dd263378012ad21a0e9090dced2f069ab94935acd12d445b91cb'
        ENTRY_DIGESTS = {
            'ota-diagnostic.json': '216244e2c6ba859fdb85a5d880fe8b59601559c2b246898c18800d923ab96584',
            'ota-claim.json': 'f3261786e09b757ee7c5ca7118dcf0b66345a71062be88c33a01b9725ffc0f4b',
            'ota-preflight.json': '91a314fc581906aa9c649fd504c1ccae1a096df7932d5a4d910ed9d13c621ecd',
        }
        SOURCE_HASHES = {
            '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
            'scripts/trusted_ota_publish.py': 'd3cba2e115f9b14bd0ac02a120b3007e5b17cb68d24ab1f73bcb1aa3afee8db6',
            'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
            'scripts/trusted_ota.py': '6cdb0b1353675215d5660d0b39ac4b347273066aa0ce9fdbb656f45e6ab25abb',
        }
    elif failed_sha == F202_FAILED_SHA:
        FAILED_SHA = F202_FAILED_SHA
        RUN_ID = 39546553940
        JOB_ID = 119045918716
        ARTIFACT_ID = 12321694024
        ARTIFACT_SIZE = 2533
        ARTIFACT_ZIP_SHA256 = '49c2f461f7c089ae770c86c50a77359887fd7090a1bb1fdd412915b2b411a92e'
        ENTRY_DIGESTS = {
            'ota-diagnostic.json': 'e52078e7c9f6cc04e99d752add662df2ca4c1822b1972432f46767b11f0aaae4',
            'ota-claim.json': '95e20f0dd109e1298dbecd9b167b118c7fe4420f70b81e9542ca3714e038a63e',
            'ota-preflight.json': '4a46b4731606e591fe3fb53706b7dd1d954ab3a48fc1e4fedc1c7a1bebffc6e9',
        }
        SOURCE_HASHES = {
            '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
            'scripts/trusted_ota_publish.py': 'd3cba2e115f9b14bd0ac02a120b3007e5b17cb68d24ab1f73bcb1aa3afee8db6',
            'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
            'scripts/trusted_ota.py': '6cdb0b1353675215d5660d0b39ac4b347273066aa0ce9fdbb656f45e6ab25abb',
        }
    elif failed_sha == C29D_FAILED_SHA:
        FAILED_SHA = C29D_FAILED_SHA
        RUN_ID = 40281092624
        JOB_ID = 121434341485
        ARTIFACT_ID = 12633145149
        ARTIFACT_SIZE = 2532
        ARTIFACT_ZIP_SHA256 = 'cdd4b16985fd2a7672b8ad270f2e22a21018e390f698d70e90d55a15cb5cdfe4'
        ENTRY_DIGESTS = {
            'ota-diagnostic.json': '41397c0f02c972d269e894961b5d3a53add5298f23acee85e1099c9c042bd2b4',
            'ota-claim.json': '10cbfd6a886285891762d5dbbd6edf8f3ffda58c08ea040f1fef28f5bda36776',
            'ota-preflight.json': '842135a82961b73bcfda724ebab1b1432abe3642efb5e8fca612798e89fcd468',
        }
        SOURCE_HASHES = {
            '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
            'scripts/trusted_ota_publish.py': 'd8a509e114fae2509fd93d157d713ed61b61c97b97aa358ea61f3a3ce566f63d',
            'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
            'scripts/trusted_ota.py': '2e0c9c20f779e9fb09afb8a2c8625710d1d05265a4886b8a2a43602ac1dd2d56',
        }
    elif failed_sha == A4D_FAILED_SHA:
        FAILED_SHA = A4D_FAILED_SHA
        RUN_ID = 40735832856
        JOB_ID = 122983994390
        ARTIFACT_ID = 12835953802
        ARTIFACT_SIZE = 2565
        ARTIFACT_ZIP_SHA256 = '9c871358a46e2598eecb042d2c895bbfed4ff6b8190a2ce5ef9335f5258c07c9'
        ENTRY_DIGESTS = {
            'ota-diagnostic.json': '63cff0263d191c2c6c120dd1f66c44f0256a445aad0fb202824c67a1836ec73c',
            'ota-claim.json': 'c508ba2abaf836ad05880391bccc2d042029d0302012e209d9fd721131545dda',
            'ota-preflight.json': '69042e0da28fbbf675cb3364e424da3c39b8524d3619bb2475d532f686ae4939',
        }
        SOURCE_HASHES = {
            '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
            'scripts/trusted_ota_publish.py': 'fee188f98bd4b32c671589d2eb8b7624bc6b10ecb60c90170f52ec706cd880c7',
            'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
            'scripts/trusted_ota.py': '7aa82ae1c64cb04ab5a8455731b32bb7b4b427e0313adfb1d62990f392cb5937',
        }
    _SELECTED_PROFILE = failed_sha


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ClosureError('duplicate JSON field')
        value[key] = item
    return value


def parsed(raw):
    if len(raw) > 2_000_000:
        raise ClosureError('evidence exceeds bound')
    return json.loads(raw, object_pairs_hook=unique)


def validate_artifact(raw):
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != ARTIFACT_ZIP_SHA256:
        raise ClosureError('official artifact bytes differ')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if (len(infos) != 3 or {item.filename for item in infos} != set(ENTRY_DIGESTS)
                or any(item.is_dir() or item.flag_bits & 1 or item.file_size > 100_000 for item in infos)):
            raise ClosureError('unknown publication phase or archive inventory')
        entries = {item.filename: parsed(archive.read(item)) for item in infos}
    expected = {'sha': FAILED_SHA, 'state': 'BLOCKED', 'phase': 'claim-ota', 'reason': 'command_failed'}
    if entries['ota-diagnostic.json'] != expected:
        raise ClosureError('not a proved preclaim failure')
    if {name: digest(value) for name, value in entries.items()} != ENTRY_DIGESTS:
        raise ClosureError('reviewed artifact entries differ')
    return entries


def validate_official_metadata(run, jobs, artifact):
    binding = {'id': RUN_ID, 'run_attempt': RUN_ATTEMPT, 'workflow_id': WORKFLOW_ID,
               'path': '.github/workflows/trusted-ota.yml', 'head_sha': FAILED_SHA,
               'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed',
               'conclusion': 'failure'}
    if (not isinstance(run, dict) or any(run.get(k) != v for k, v in binding.items())
            or any(run.get(k, {}).get('full_name') != REPOSITORY for k in ('repository', 'head_repository'))):
        raise ClosureError('exact final failed workflow required')
    if (not isinstance(jobs, dict) or jobs.get('total_count') != 1
            or not isinstance(jobs.get('jobs'), list) or len(jobs['jobs']) != 1):
        raise ClosureError('unexpected publisher jobs')
    job = jobs['jobs'][0]
    if (not isinstance(job, dict) or any(job.get(k) != v for k, v in {
            'id': JOB_ID, 'name': 'ota', 'status': 'completed', 'conclusion': 'failure'}.items())
            or not isinstance(job.get('steps'), list)):
        raise ClosureError('publisher job is not final')
    steps = job['steps']
    if (any(not isinstance(s, dict) for s in steps)
            or len({s.get('name') for s in steps}) != len(steps)
            or any(s.get('status') != 'completed' for s in steps)
            or any(len([s for s in steps if s.get('name') == name and s.get('conclusion') == result]) != 1
                   for name, result in REQUIRED_STEPS.items())):
        raise ClosureError('publisher step binding differs')
    expected_artifact = {
        'id': ARTIFACT_ID,
        'name': f'trusted-ota-{FAILED_SHA}-{RUN_ID}-{RUN_ATTEMPT}',
        'digest': 'sha256:' + ARTIFACT_ZIP_SHA256, 'size_in_bytes': ARTIFACT_SIZE, 'expired': False,
    }
    workflow_run = {'id': RUN_ID, 'repository_id': 1127096388, 'head_repository_id': 1127096388,
                    'head_branch': 'main', 'head_sha': FAILED_SHA}
    if (not isinstance(artifact, dict) or any(artifact.get(k) != v for k, v in expected_artifact.items())
            or artifact.get('workflow_run') != workflow_run):
        raise ClosureError('official artifact provenance differs')
    return {'run': binding, 'job_id': JOB_ID, 'steps': REQUIRED_STEPS,
            'artifact': expected_artifact, 'workflow_run': workflow_run, 'entries': ENTRY_DIGESTS}


def opener():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    defaults = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    capath = defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath:
        raise ClosureError('system TLS trust unavailable')
    context.load_verify_locations(cafile=cafile, capath=capath)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                      urllib.request.HTTPSHandler(context=context))


def read_url(url, token, *, archive=False):
    if not url.startswith(BASE + '/actions/'):
        raise ClosureError('fixed official API origin required')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'reva-ota-preclaim-closure', 'Cache-Control': 'no-cache'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    client = opener()
    try:
        try:
            response = client.open(urllib.request.Request(url, headers=headers), timeout=20)
        except urllib.error.HTTPError as error:
            if not archive or error.code != 302:
                raise
            location = error.headers.get('Location', '')
            part = urllib.parse.urlsplit(location)
            if (part.scheme != 'https' or part.username is not None or part.password is not None
                    or part.port not in (None, 443) or part.fragment
                    or re.fullmatch(r'productionresultssa[0-9]+\.blob\.core\.windows\.net', part.hostname or '') is None):
                raise ClosureError('unexpected official artifact storage origin')
            # Never forward the API credential to the signed storage URL.
            response = client.open(urllib.request.Request(location), timeout=20)
        with response:
            if response.status != 200:
                raise ClosureError('official evidence unavailable')
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ClosureError('official evidence exceeds bound')
            return raw
    except Exception:  # noqa: BLE001 - fixed diagnostics must not expose signed URLs or tokens
        raise ClosureError('fresh official GitHub evidence unavailable') from None


def official_evidence(token):
    run_url = BASE + f'/actions/runs/{RUN_ID}'
    run = parsed(read_url(run_url, token))
    jobs = parsed(read_url(run_url + f'/attempts/{RUN_ATTEMPT}/jobs?per_page=100', token))
    artifact = parsed(read_url(BASE + f'/actions/artifacts/{ARTIFACT_ID}', token))
    proof = validate_official_metadata(run, jobs, artifact)
    entries = validate_artifact(read_url(BASE + f'/actions/artifacts/{ARTIFACT_ID}/zip', token, archive=True))
    if parsed(read_url(run_url, token)) != run:
        raise ClosureError('workflow changed during inspection')
    return proof, entries


def private_directory(server, path):
    server.secure_path(path, directory=True)
    if stat.S_IMODE(path.lstat().st_mode) != 0o700:
        raise ClosureError('private root-owned audit directory required')


def file_identity(server, path):
    server.secure_path(path, private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        server.validate_metadata(info, private=True)
        raw = stream.read(100_001)
        if len(raw) > 100_000:
            raise ClosureError('local proof exceeds bound')
    after = path.lstat()
    if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
        raise ClosureError('original proof file replaced')
    return {'device': info.st_dev, 'inode': info.st_ino, 'sha256': hashlib.sha256(raw).hexdigest()}


def operation_evidence(server, operation):
    if operation != server.STATE / 'ota' / FAILED_SHA:
        raise ClosureError('unsupported failed OTA revision')
    private_directory(server, operation)
    if {p.name for p in operation.iterdir()} != {'intent.json', 'lease.json'}:
        raise ClosureError('claimed, vendor, or partial evidence forbids closure')
    info = operation.lstat()
    claim = server._json(server._read_private(operation / 'intent.json'))
    if digest(claim) != ENTRY_DIGESTS['ota-claim.json']:
        raise ClosureError('original intent differs from official artifact')
    return {'directory': [info.st_dev, info.st_ino],
            'files': {name: file_identity(server, operation / name) for name in ('intent.json', 'lease.json')},
            'claim_sha256': digest(claim)}


def lease_snapshot(server, path, lease):
    server._testflight_lease_parent()
    if (not isinstance(lease, dict) or set(lease) != {'token', 'started_at', 'identity'}
            or not isinstance(lease['token'], str) or re.fullmatch(r'[a-f0-9]{64}', lease['token']) is None
            or not isinstance(lease['started_at'], str) or re.fullmatch(r'[0-9]{1,12}', lease['started_at']) is None
            or not isinstance(lease['identity'], list) or len(lease['identity']) != 4
            or any(type(n) is not int or n < 0 for n in lease['identity'])):
        raise ClosureError('invalid original lease identity')
    info = path.lstat()
    server.validate_metadata(info, directory=True)
    expected = {'token': lease['token'], 'label': 'testflight-check',
                'stage': str(server.STATE / FAILED_SHA), 'started_at': lease['started_at']}
    if stat.S_IMODE(info.st_mode) != 0o700 or {p.name for p in path.iterdir()} != set(expected):
        raise ClosureError('original lease inventory differs')
    files = {}
    for name, value in expected.items():
        # /run/lock is the sole sticky-parent exception, checked above.
        fd = os.open(path / name, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            server.validate_metadata(metadata, private=True)
            raw = stream.read(4097)
        if raw != (value + '\n').encode():
            raise ClosureError('original lease content differs')
        files[name] = {'device': metadata.st_dev, 'inode': metadata.st_ino,
                       'sha256': hashlib.sha256(raw).hexdigest()}
    if [info.st_dev, info.st_ino, files['token']['device'], files['token']['inode']] != lease['identity']:
        raise ClosureError('original lease inode changed')
    return {'directory': [info.st_dev, info.st_ino], 'files': files}


def retired_path(server):
    return server.BUSINESS_LEASE.with_name(server.BUSINESS_LEASE.name + '.ota-unclaimed-' + FAILED_SHA)


def production_health(server):
    if server.read_status(FAILED_SHA, server.STATE / FAILED_SHA) != {'sha': FAILED_SHA, 'state': 'SUCCEEDED'}:
        raise ClosureError('exact production backend terminal required')
    units = ('health-backend', 'celery-worker', 'celery-beat', 'reva-laya')
    for unit in units:
        raw = subprocess.run(['/usr/bin/systemctl', 'show', unit,
            '--property=ActiveState,SubState,MainPID'], env=ENV, stdin=subprocess.DEVNULL,
            capture_output=True, check=True, timeout=20).stdout
        if len(raw) > 4096:
            raise ClosureError('service state exceeds bound')
        pairs = [line.split('=', 1) for line in raw.decode().splitlines()]
        values = unique(pairs)
        if (set(values) != {'ActiveState', 'SubState', 'MainPID'}
                or values['ActiveState'] != 'active' or values['SubState'] != 'running'
                or not values['MainPID'].isdigit() or int(values['MainPID']) <= 0):
            raise ClosureError('production service is not running')
    client = opener()
    for url in ('http://127.0.0.1:8000/api/v1/health', 'https://health.executor.life/api/v1/health'):
        with client.open(urllib.request.Request(url, headers={'Cache-Control': 'no-cache'}), timeout=10) as response:
            raw = response.read(65537)
            if response.status != 200 or len(raw) > 65536:
                raise ClosureError('production health unavailable')
            health = parsed(raw)
            services = {'api': 'running', 'database': 'connected', 'redis': 'connected', 'celery': 'connected'}
            if (not isinstance(health, dict) or health.get('status') != 'healthy'
                    or not isinstance(health.get('services'), dict)
                    or any(health['services'].get(k) != v for k, v in services.items())):
                raise ClosureError('production health is not fully healthy')
    return {'sha': FAILED_SHA, 'terminal': 'SUCCEEDED', 'units': list(units),
            'loopback': 'healthy', 'public': 'healthy'}


class Adapter:
    def __init__(self, bootstrap, server, source, closing_sha, token, check_locks):
        self.b, self.server, self.source = bootstrap, server, source
        self.closing_sha, self.token, self.check_locks = closing_sha, token, check_locks
        self.record = server.STATE / ROOT_NAME / FAILED_SHA

    def check_record_parent(self):
        if os.path.lexists(self.record.parent):
            private_directory(self.server, self.record.parent)
        else:
            self.server.secure_path(self.server.STATE, directory=True)

    def inspect(self):
        b, server = self.b, self.server
        self.check_locks()
        if b.canonical_source(self.closing_sha) != self.source:
            raise ClosureError('closing source changed')
        operator = self.source / 'scripts/trusted_ota_unclaimed_retirement.py'
        server.secure_path(operator)
        operator_sha256 = hashlib.sha256(operator.read_bytes()).hexdigest()
        failed_source = b.canonical_source(FAILED_SHA)
        for name, expected in SOURCE_HASHES.items():
            server.secure_path(failed_source / name)
            if hashlib.sha256((failed_source / name).read_bytes()).hexdigest() != expected:
                raise ClosureError('original publisher control flow differs')
        b._assert_backend_terminated_or_unstarted(FAILED_SHA)
        b._recovery_process_proof()
        b._recovery_production_proof(FAILED_SHA, self.source)
        production = production_health(server)
        operation = server.STATE / 'ota' / FAILED_SHA
        original = operation_evidence(server, operation)
        lease = server._json(server._read_private(operation / 'lease.json'))
        server._assert_testflight_lease(lease, server.STATE / FAILED_SHA)
        if os.path.lexists(retired_path(server)):
            raise ClosureError('lease retirement already attempted')
        original_lease = lease_snapshot(server, server.BUSINESS_LEASE, lease)
        official, entries = official_evidence(self.token)
        if digest(entries['ota-claim.json']) != original['claim_sha256']:
            raise ClosureError('live artifact intent differs')
        b._recovery_process_proof()
        self.check_locks()
        if (operation_evidence(server, operation) != original
                or lease_snapshot(server, server.BUSINESS_LEASE, lease) != original_lease):
            raise ClosureError('original local proof changed')
        return {'failed_sha': FAILED_SHA, 'closing_sha': self.closing_sha,
                'closure_operator_sha256': operator_sha256,
                'source_hashes': SOURCE_HASHES, 'operation': original, 'lease': original_lease,
                'official': official, 'production': production, 'retired_path': str(retired_path(server)),
                'locks': {name: file_identity(server, path) for name, path in {
                    'launcher': server.STATE / 'launcher.lock',
                    'build': server.STATE / FAILED_SHA / 'build.lock'}.items()}}

    def retire_lease(self, evidence):
        server = self.server
        self.check_locks()
        operation = server.STATE / 'ota' / FAILED_SHA
        lease = server._json(server._read_private(operation / 'lease.json'))
        if (operation_evidence(server, operation) != evidence['operation']
                or lease_snapshot(server, server.BUSINESS_LEASE, lease) != evidence['lease']
                or os.path.lexists(retired_path(server))):
            raise ClosureError('final original lease proof changed')
        os.rename(server.BUSINESS_LEASE, retired_path(server))
        server._sync_business_lease_parent()
        if lease_snapshot(server, retired_path(server), lease) != evidence['lease']:
            raise ClosureError('same-inode retirement failed')
        self.check_locks()


def write(adapter, path, value):
    adapter.server._write_private(path, json.dumps(value, sort_keys=True).encode())


def close_transaction(adapter, evidence_sha256=None):
    adapter.check_locks()
    if os.path.lexists(adapter.record):
        raise ClosureError('closure already attempted; retry forbidden')
    adapter.check_record_parent()
    evidence = adapter.inspect()
    if evidence.get('failed_sha') != FAILED_SHA:
        raise ClosureError('unsupported failed revision')
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_UNPUBLISHED_CLAIM', 'evidence_sha256': fingerprint}
    if re.fullmatch(r'[a-f0-9]{64}', evidence_sha256) is None or evidence_sha256 != fingerprint:
        raise ClosureError('inspection evidence changed')
    adapter.record.parent.mkdir(mode=0o700, exist_ok=True)
    adapter.server._sync_directory(adapter.record.parent.parent)
    adapter.check_record_parent()
    adapter.record.mkdir(mode=0o700)
    adapter.server._sync_directory(adapter.record.parent)
    intent = {**evidence, 'state': 'CLOSING_UNPUBLISHED_CLAIM', 'evidence_sha256': fingerprint}
    adapter.check_locks()
    write(adapter, adapter.record / 'intent.json', intent)
    if adapter.inspect() != evidence:
        raise ClosureError('evidence changed after durable close intent')
    adapter.retire_lease(evidence)
    adapter.check_locks()
    write(adapter, adapter.record / 'completed.json', {
        'state': TERMINAL, 'failed_sha': FAILED_SHA, 'intent_sha256': digest(intent)})
    adapter.check_locks()
    return {'sha': FAILED_SHA, 'state': TERMINAL, 'closure_sha256': digest(intent)}


def validate_closed_history(server, operation):
    select_profile(Path(operation).name)
    original = operation_evidence(server, Path(operation))
    record = server.STATE / ROOT_NAME / FAILED_SHA
    private_directory(server, record.parent)
    private_directory(server, record)
    if {p.name for p in record.iterdir()} != {'intent.json', 'completed.json'}:
        raise ClosureError('unfinished closure remains blocked')
    intent = server._json(server._read_private(record / 'intent.json'))
    completed = server._json(server._read_private(record / 'completed.json'))
    keys = {'failed_sha', 'closing_sha', 'closure_operator_sha256', 'source_hashes', 'operation', 'lease', 'official', 'production',
            'retired_path', 'locks', 'state', 'evidence_sha256'}
    if (not isinstance(intent, dict) or set(intent) != keys or intent['failed_sha'] != FAILED_SHA
            or not isinstance(intent['closing_sha'], str) or re.fullmatch(r'[a-f0-9]{40}', intent['closing_sha']) is None
            or intent['closing_sha'] == FAILED_SHA or intent['source_hashes'] != SOURCE_HASHES
            or intent['operation'] != original or intent['retired_path'] != str(retired_path(server))
            or intent['state'] != 'CLOSING_UNPUBLISHED_CLAIM'
            or intent['production'] != {'sha': FAILED_SHA, 'terminal': 'SUCCEEDED',
                'units': ['health-backend', 'celery-worker', 'celery-beat', 'reva-laya'],
                'loopback': 'healthy', 'public': 'healthy'}
            or intent['evidence_sha256'] != digest({k: v for k, v in intent.items() if k not in {'state', 'evidence_sha256'}})
            or completed != {'state': TERMINAL, 'failed_sha': FAILED_SHA, 'intent_sha256': digest(intent)}):
        raise ClosureError('closure binding differs')
    official = intent['official']
    expected_run = {'id': RUN_ID, 'run_attempt': RUN_ATTEMPT, 'workflow_id': WORKFLOW_ID,
        'path': '.github/workflows/trusted-ota.yml', 'head_sha': FAILED_SHA, 'head_branch': 'main',
        'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'failure'}
    if (not isinstance(official, dict) or set(official) != {'run', 'job_id', 'steps', 'artifact', 'workflow_run', 'entries'}
            or official['run'] != expected_run or official['job_id'] != JOB_ID
            or official['steps'] != REQUIRED_STEPS or official['entries'] != ENTRY_DIGESTS):
        raise ClosureError('historical official proof differs')
    validate_official_metadata({**official['run'], 'repository': {'full_name': REPOSITORY},
        'head_repository': {'full_name': REPOSITORY}}, {'total_count': 1, 'jobs': [{
        'id': JOB_ID, 'name': 'ota', 'status': 'completed', 'conclusion': 'failure',
        'steps': [{'name': name, 'status': 'completed', 'conclusion': result} for name, result in REQUIRED_STEPS.items()]}]},
        {**official['artifact'], 'workflow_run': official['workflow_run']})
    # Bind both original control flow and the reviewed closure implementation,
    # without consulting current production, GitHub, or vendor state on history reads.
    source = server.STATE / 'bootstrap' / intent['closing_sha'] / 'source'
    spec = importlib.util.spec_from_file_location('ota_closure_history_bootstrap', source / 'scripts/bootstrap_trusted_release.py')
    bootstrap_path = source / 'scripts/bootstrap_trusted_release.py'
    server.secure_path(bootstrap_path)
    if os.path.lexists(bootstrap_path.parent / '__pycache__'):
        raise ClosureError('cached closure history code forbidden')
    expected = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(source),
        'show', intent['closing_sha'] + ':scripts/bootstrap_trusted_release.py'], env=ENV,
        capture_output=True, check=True, timeout=30).stdout
    if bootstrap_path.read_bytes() != expected:
        raise ClosureError('closure bootstrap differs from canonical source')
    operator = source / 'scripts/trusted_ota_unclaimed_retirement.py'
    server.secure_path(operator)
    operator_bytes = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', '-C', str(source), 'show',
        intent['closing_sha'] + ':scripts/trusted_ota_unclaimed_retirement.py'], env=ENV,
        capture_output=True, check=True, timeout=30).stdout
    if (operator.read_bytes() != operator_bytes
            or hashlib.sha256(operator_bytes).hexdigest() != intent['closure_operator_sha256']):
        raise ClosureError('reviewed closure operator bytes changed')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    b.canonical_source(intent['closing_sha'])
    failed_source = b.canonical_source(FAILED_SHA)
    for name, expected_hash in SOURCE_HASHES.items():
        server.secure_path(failed_source / name)
        if hashlib.sha256((failed_source / name).read_bytes()).hexdigest() != expected_hash:
            raise ClosureError('historical publisher source changed')
    lease = server._json(server._read_private(operation / 'lease.json'))
    if (not isinstance(lease, dict) or set(lease) != {'token', 'started_at', 'identity'}
            or not isinstance(lease['token'], str) or re.fullmatch(r'[a-f0-9]{64}', lease['token']) is None
            or not isinstance(lease['started_at'], str) or re.fullmatch(r'[0-9]{1,12}', lease['started_at']) is None
            or not isinstance(lease['identity'], list) or len(lease['identity']) != 4
            or any(type(n) is not int or n < 0 for n in lease['identity'])):
        raise ClosureError('historical original lease identity invalid')
    expected_locks = {name: file_identity(server, path) for name, path in {
        'launcher': server.STATE / 'launcher.lock',
        'build': server.STATE / FAILED_SHA / 'build.lock'}.items()}
    if intent['locks'] != expected_locks:
        raise ClosureError('original transaction locks changed')
    snapshot = intent['lease']
    expected_content = {'token': lease.get('token'), 'label': 'testflight-check',
                        'stage': str(server.STATE / FAILED_SHA), 'started_at': lease.get('started_at')}
    if (not isinstance(snapshot, dict) or set(snapshot) != {'directory', 'files'}
            or not isinstance(snapshot['files'], dict) or set(snapshot['files']) != set(expected_content)
            or snapshot['directory'] != lease.get('identity', [])[:2]
            or any(snapshot['files'][name].get('sha256') != hashlib.sha256((str(value) + '\n').encode()).hexdigest()
                   for name, value in expected_content.items())
            or [snapshot['files']['token'].get('device'), snapshot['files']['token'].get('inode')] != lease.get('identity', [])[2:]):
        raise ClosureError('historical original lease binding differs')
    if os.path.lexists(retired_path(server)) and lease_snapshot(server, retired_path(server), lease) != snapshot:
        raise ClosureError('retired original lease changed')
    if os.path.lexists(server.BUSINESS_LEASE):
        info = server.BUSINESS_LEASE.lstat()
        if [info.st_dev, info.st_ino] == snapshot['directory']:
            raise ClosureError('consumed original lease revived')
    return {'sha': FAILED_SHA, 'state': TERMINAL, 'closure_sha256': digest(intent)}


def private_github_token(raw):
    if not isinstance(raw, bytes) or len(raw) > 8192:
        raise ClosureError('private read-only GitHub credential required')
    try:
        credentials = parsed(raw)
    except (ValueError, UnicodeError):
        raise ClosureError('private read-only GitHub credential required') from None
    if (not isinstance(credentials, dict) or set(credentials) != {'github_token'}
            or not isinstance(credentials['github_token'], str)
            or re.fullmatch(r'[A-Za-z0-9_.-]{1,4096}', credentials['github_token']) is None):
        raise ClosureError('private read-only GitHub credential required')
    return credentials['github_token']


def verify_closing_ci(source, sha, token):
    if not isinstance(token, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,4096}', token) is None:
        raise ClosureError('private read-only GitHub credential required')
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
        '--sha', sha, '--workflow-sha', sha, '--target', 'full', '--token-stdin'],
        env=ENV, input=token.encode('ascii'), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, check=True, timeout=90)


def context(sha, token):
    if (os.geteuid() != 0 or not sys.flags.isolated or not sys.flags.no_site
            or not sys.flags.dont_write_bytecode or sys.executable != '/usr/bin/python3.12'
            or re.fullmatch(r'[a-f0-9]{40}', sha) is None or sha == FAILED_SHA):
        raise ClosureError('isolated root closing revision required')
    source = ROOT / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/trusted_ota_unclaimed_retirement.py'
    if Path(__file__).absolute() != entry:
        raise ClosureError('canonical closing operator required')
    for file in (entry, entry.with_name('bootstrap_trusted_release.py')):
        for path in [*reversed(file.parents), file]:
            info = path.lstat()
            if (info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                    or not (stat.S_ISREG(info.st_mode) if path == file else stat.S_ISDIR(info.st_mode))
                    or (path == file and info.st_nlink != 1)):
                raise ClosureError('unsafe canonical operator metadata')
        raw = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
            '-C', str(source), 'show', sha + ':scripts/' + file.name], env=ENV,
            capture_output=True, check=True, timeout=30).stdout
        if raw != file.read_bytes():
            raise ClosureError('canonical operator bytes changed')
    if os.path.lexists(entry.parent / '__pycache__'):
        raise ClosureError('cached canonical operator forbidden')
    spec = importlib.util.spec_from_file_location('ota_closing_bootstrap', entry.with_name('bootstrap_trusted_release.py'))
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    checked, server = b.reviewed_source(sha)
    if checked != source:
        raise ClosureError('closing canonical source differs')
    verify_closing_ci(source, sha, token)
    return b, server, source


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--failed-sha', choices=SUPPORTED_FAILED_SHAS, default=LEGACY_FAILED_SHA)
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    select_profile(args.failed_sha)
    # One explicit private credential authorizes both exact CI verification and
    # official artifact readback. Invalid stdin never falls back to disk or env.
    os.umask(0o077)
    token = private_github_token(sys.stdin.buffer.read(8193))
    b, server, source = context(args.sha, token)
    launcher = server.STATE / 'launcher.lock'
    server.secure_path(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = b._acquire_existing_build_lock(FAILED_SHA)
        if build_fd is None:
            raise ClosureError('original build lock required')
        def check():
            b._assert_original_lock(launcher, fd)
            b._assert_original_lock(server.STATE / FAILED_SHA / 'build.lock', build_fd)
        result = close_transaction(Adapter(b, server, source, args.sha,
            token, check), args.evidence_sha256)
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - terminal CLI boundary prints no underlying exception
        print('OTA preclaim closure blocked; preserve evidence; never retry consumed closure', file=sys.stderr)
        sys.exit(1)
