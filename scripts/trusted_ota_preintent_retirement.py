"""Close one reviewed OTA claim failure that left no server OTA intent.

This operator never creates an OTA intent, releases a lease, calls Expo, or
authorizes retry. It binds the failed workflow and official audit artifact to
the completed overlapping frontend publication without assigning causality,
then writes one durable closure.
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
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

FAILED_SHA = '53f9c6aee3eb30d8937a4582e206cce47de80157'
RUN_ID = 40861067214
RUN_ATTEMPT = 1
WORKFLOW_ID = 370218159
JOB_ID = 123404134816
ARTIFACT_ID = 12890544500
ARTIFACT_SIZE = 2566
ARTIFACT_ZIP_SHA256 = '261128bc5c7ba573a6df56fb6a33255610ce877d2009e6018131fdc8180fde50'
FRONTEND_OPERATION = 'dbbb6a5caeb94991ab079a39b7a1275d'
ROOT_NAME = 'ota-preintent-failure-closures'
TERMINAL = 'CLOSED_PREINTENT_OTA_FAILURE'
ROOT = Path('/var/lib/reva-release')
REPOSITORY = 'itsoso/health-llm-driven'
BASE = 'https://api.github.com/repos/' + REPOSITORY
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
SOURCE_HASHES = {
    '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
    'scripts/trusted_ota_publish.py': '18766c3b0138d501e65e8254ae24a31f2baadc5f9be0d8aee3e3c228e47cc0b5',
    'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
    'scripts/trusted_ota.py': '16c3e5e691882e9776e344803f0739152537d04af52012bebf31ec9df00b2061',
}
ENTRY_DIGESTS = {
    'ota-diagnostic.json': 'd10b0cd7b1b17bbcf56f7df3b722fdfe9a8a5e868833fef79884a8a04c966e22',
    'ota-claim.json': '8ca573a71cb59efa414fb5354fd3d9e782fae29e68e73a7d55c007c34540baa3',
    'ota-preflight.json': 'ecde82a7ee45ff1b1d6ac2f81d28079a4f10ba82faa0202faab4f6e78abbf69a',
}
REQUIRED_STEPS = {
    'Materialize exact canonical source and verify current main CI before credentials': 'success',
    'Prepare exact OTA artifact without consuming a publication claim': 'skipped',
    'Publish one bound iOS artifact and verify server receipt': 'failure',
    'Stage validated OTA audit even when publication is incomplete': 'success',
    'Preserve OTA audit for same-receipt recovery': 'success',
}
FRONTEND_COMPLETED = {
    'artifact_digest': 'ce4bc5edb76665afc2d12225050bcc667e81155ba0ed6aba6d6f90fd04e510f9',
    'backups_digest': {},
    'frontend_tree': 'f4f93952253fc797190d33b7af7be87700c3b662',
    'kind': 'frontend-publication',
    'operation_id': FRONTEND_OPERATION,
    'production_sha': FAILED_SHA,
    'proof_sha256': {
        'before.json': '98b420570b0323f7f6c23b58b1da3ce2391add504322c0a20b43bdb7ceca7dd8',
        'build.log': 'ca0832794058f905f7cde882323982dc4a0071dc477a887f30026b03f9ab7564',
        'install-started.json': 'c4fb2b89b9b3fc7f82716a14f747403ef89103ff6fdef0723a35a5bf624c72fd',
        'verified.json': '4ae5c25f08d0425baaa671ef8fe462ed230d78963198475074215e847bb27fe2',
    },
    'publication_policy': 'no-backup-v1',
    'publisher_sha': FAILED_SHA,
    'state': 'FRONTEND_SUCCEEDED',
}


class ClosureError(Exception):
    """Static diagnostics only; never tokens, signed URLs, or private output."""


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


def private_github_token(raw):
    if (not isinstance(raw, bytes) or not raw or len(raw) > 8192
            or re.fullmatch(rb'[A-Za-z0-9_.-]{1,8192}', raw) is None):
        raise ClosureError('private read-only GitHub credential required')
    return raw.decode('ascii')


def validate_artifact(raw):
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != ARTIFACT_ZIP_SHA256:
        raise ClosureError('official artifact bytes differ')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        expected_names = {'ota-diagnostic.json', 'ota-claim.json', 'ota-preflight.json'}
        if (len(infos) != 3 or {item.filename for item in infos} != expected_names
                or any(item.is_dir() or item.flag_bits & 1 or item.file_size > 100_000 for item in infos)):
            raise ClosureError('unknown publication phase or archive inventory')
        raw_entries = {item.filename: archive.read(item) for item in infos}
        if ({name: hashlib.sha256(value).hexdigest() for name, value in raw_entries.items()}
                != ENTRY_DIGESTS):
            raise ClosureError('reviewed artifact entries differ')
        entries = {name: parsed(value) for name, value in raw_entries.items()}
    expected = {'sha': FAILED_SHA, 'state': 'BLOCKED', 'phase': 'claim-ota', 'reason': 'command_failed'}
    if entries['ota-diagnostic.json'] != expected:
        raise ClosureError('not a proved pre-intent claim failure')
    if any(name in entries for name in ('ota-vendor-receipt.json', 'ota-receipt.json')):
        raise ClosureError('vendor evidence forbids pre-intent failure closure')
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
    if (any(not isinstance(step, dict) for step in steps)
            or len({step.get('name') for step in steps}) != len(steps)
            or any(step.get('status') != 'completed' for step in steps)
            or any(len([step for step in steps if step.get('name') == name
                        and step.get('conclusion') == result]) != 1
                   for name, result in REQUIRED_STEPS.items())):
        raise ClosureError('publisher step binding differs')
    expected_artifact = {
        'id': ARTIFACT_ID,
        'name': f'trusted-ota-{FAILED_SHA}-{RUN_ID}-{RUN_ATTEMPT}',
        'digest': 'sha256:' + ARTIFACT_ZIP_SHA256,
        'size_in_bytes': ARTIFACT_SIZE,
        'expired': False,
    }
    workflow_run = {'id': RUN_ID, 'repository_id': 1127096388,
                    'head_repository_id': 1127096388, 'head_branch': 'main',
                    'head_sha': FAILED_SHA}
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
               'User-Agent': 'reva-ota-pre-intent-failure-closure', 'Cache-Control': 'no-cache',
               'Authorization': 'Bearer ' + token}
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
            response = client.open(urllib.request.Request(location), timeout=20)
        with response:
            if response.status != 200:
                raise ClosureError('official evidence unavailable')
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ClosureError('official evidence exceeds bound')
            return raw
    except Exception:  # noqa: BLE001 - fixed diagnostics must not expose private URLs or tokens
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
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ClosureError('local proof exceeds bound')
    after = path.lstat()
    if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
        raise ClosureError('local proof file replaced')
    return {'device': info.st_dev, 'inode': info.st_ino,
            'sha256': hashlib.sha256(raw).hexdigest()}


def frontend_publication_evidence(server):
    operation = server.STATE / 'frontend-publications' / FRONTEND_OPERATION
    private_directory(server, operation)
    names = {'before.json', 'build.log', 'completed.json', 'install-started.json',
             'intent.json', 'verified.json'}
    if {path.name for path in operation.iterdir()} != names:
        raise ClosureError('overlapping frontend publication inventory differs')
    completed = server._json(server._read_private(operation / 'completed.json'))
    if completed != FRONTEND_COMPLETED:
        raise ClosureError('overlapping frontend publication is not complete')
    for name, expected in completed['proof_sha256'].items():
        if hashlib.sha256(server._read_private(operation / name)).hexdigest() != expected:
            raise ClosureError('overlapping frontend publication proof differs')
    return {'operation_id': FRONTEND_OPERATION, 'completed': completed,
            'files': {name: file_identity(server, operation / name) for name in sorted(names)}}


def production_health(server):
    if server.read_status(FAILED_SHA, server.STATE / FAILED_SHA) != {'sha': FAILED_SHA, 'state': 'SUCCEEDED'}:
        raise ClosureError('exact production backend terminal required')
    head = subprocess.run(['/usr/bin/git', '-C', '/opt/health-app', 'rev-parse', 'HEAD'], env=ENV,
                          stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=20).stdout.decode().strip()
    if head != FAILED_SHA:
        raise ClosureError('production revision differs')
    units = ('health-backend', 'celery-worker', 'celery-beat', 'health-frontend')
    for unit in units:
        raw = subprocess.run(['/usr/bin/systemctl', 'show', unit,
            '--property=ActiveState,SubState,MainPID'], env=ENV, stdin=subprocess.DEVNULL,
            capture_output=True, check=True, timeout=20).stdout
        values = unique(line.split('=', 1) for line in raw.decode().splitlines())
        if (set(values) != {'ActiveState', 'SubState', 'MainPID'}
                or values['ActiveState'] != 'active' or values['SubState'] != 'running'
                or not values['MainPID'].isdigit() or int(values['MainPID']) <= 0):
            raise ClosureError('production service is not running')
    client = opener()
    for url in ('http://127.0.0.1:8000/api/v1/health', 'https://health.executor.life/api/v1/health'):
        with client.open(urllib.request.Request(url, headers={'Cache-Control': 'no-cache'}), timeout=10) as response:
            raw = response.read(65537)
            health = parsed(raw)
            if response.status != 200 or len(raw) > 65536 or health.get('status') != 'healthy':
                raise ClosureError('production health unavailable')
    return {'sha': FAILED_SHA, 'state': 'SUCCEEDED', 'units': list(units),
            'loopback': 'healthy', 'public': 'healthy'}


def installed_consumer_evidence(bootstrap, server, source, closing_sha):
    """Prove the closure-aware executor is installed before durable closure."""
    canonical = source / 'scripts/trusted_release_server.py'
    server.secure_path(canonical)
    expected = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', '-C', str(source), 'show',
        closing_sha + ':scripts/trusted_release_server.py'], env=ENV,
        capture_output=True, check=True, timeout=30).stdout
    if canonical.read_bytes() != expected:
        raise ClosureError('canonical closing consumer changed')
    executor_sha256 = hashlib.sha256(expected).hexdigest()
    policy_path = bootstrap.CONFIG / 'authorized-release.json'
    bootstrap.secure(policy_path, private=True)
    policy = bootstrap._read_json(policy_path)
    try:
        server.validate_policy(policy, now=int(time.time()))
    except Exception:  # noqa: BLE001 - expose only a fixed closure diagnostic
        raise ClosureError('closure-aware release authorization required') from None
    if (policy['sha'] != closing_sha
            or policy['executor_sha256'] != executor_sha256):
        raise ClosureError('closure-aware release authorization required')
    bootstrap.secure(bootstrap.INSTALLED, private=True)
    if hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest() != executor_sha256:
        raise ClosureError('closure-aware installed executor required')
    return {
        'sha': closing_sha,
        'executor_sha256': executor_sha256,
        'authorization': policy,
        'authorization_file': file_identity(server, policy_path),
        'installed_executor': file_identity(server, bootstrap.INSTALLED),
    }


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
        operator = self.source / 'scripts/trusted_ota_preintent_retirement.py'
        server.secure_path(operator)
        consumer = installed_consumer_evidence(b, server, self.source, self.closing_sha)
        failed_source = b.canonical_source(FAILED_SHA)
        for name, expected in SOURCE_HASHES.items():
            server.secure_path(failed_source / name)
            if hashlib.sha256((failed_source / name).read_bytes()).hexdigest() != expected:
                raise ClosureError('original publisher control flow differs')
        if (os.path.lexists(server.STATE / 'ota' / FAILED_SHA)
                or os.path.lexists(server.STATE / 'ota-preclaim-closures' / FAILED_SHA)
                or os.path.lexists(server.BUSINESS_LEASE)):
            raise ClosureError('claim or business lease now exists')
        frontend = frontend_publication_evidence(server)
        official, _entries = official_evidence(self.token)
        production = production_health(server)
        self.check_locks()
        if (os.path.lexists(server.STATE / 'ota' / FAILED_SHA)
                or os.path.lexists(server.BUSINESS_LEASE)
                or frontend_publication_evidence(server) != frontend
                or installed_consumer_evidence(b, server, self.source, self.closing_sha) != consumer):
            raise ClosureError('pre-intent failure proof changed')
        return {'failed_sha': FAILED_SHA, 'closing_sha': self.closing_sha,
                'closure_operator_sha256': hashlib.sha256(operator.read_bytes()).hexdigest(),
                'installed_consumer': consumer,
                'source_hashes': SOURCE_HASHES, 'official': official,
                'frontend_publication': frontend, 'production': production,
                'locks': {name: file_identity(server, path) for name, path in {
                    'launcher': server.STATE / 'launcher.lock',
                    'build': server.STATE / FAILED_SHA / 'build.lock'}.items()},
                'ota_state_absent': True, 'business_lease_absent': True}


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
        return {'state': 'INSPECTED_PREINTENT_OTA_FAILURE', 'evidence_sha256': fingerprint}
    if re.fullmatch(r'[a-f0-9]{64}', evidence_sha256 or '') is None or evidence_sha256 != fingerprint:
        raise ClosureError('inspection evidence changed')
    adapter.record.parent.mkdir(mode=0o700, exist_ok=True)
    adapter.server._sync_directory(adapter.record.parent.parent)
    adapter.check_record_parent()
    adapter.record.mkdir(mode=0o700)
    adapter.server._sync_directory(adapter.record.parent)
    intent = {**evidence, 'state': 'CLOSING_PREINTENT_OTA_FAILURE',
              'evidence_sha256': fingerprint}
    adapter.check_locks()
    write(adapter, adapter.record / 'intent.json', intent)
    if adapter.inspect() != evidence:
        raise ClosureError('evidence changed after durable close intent')
    write(adapter, adapter.record / 'completed.json', {
        'state': TERMINAL, 'failed_sha': FAILED_SHA, 'intent_sha256': digest(intent)})
    adapter.check_locks()
    return {'sha': FAILED_SHA, 'state': TERMINAL, 'closure_sha256': digest(intent)}


def validate_closed_history(server, record):
    record = Path(record)
    if record != server.STATE / ROOT_NAME / FAILED_SHA:
        raise ClosureError('unknown OTA pre-intent failure closure')
    private_directory(server, record.parent)
    private_directory(server, record)
    if {path.name for path in record.iterdir()} != {'intent.json', 'completed.json'}:
        raise ClosureError('unfinished pre-intent failure closure remains blocked')
    intent = server._json(server._read_private(record / 'intent.json'))
    completed = server._json(server._read_private(record / 'completed.json'))
    keys = {'failed_sha', 'closing_sha', 'closure_operator_sha256', 'installed_consumer', 'source_hashes',
            'official', 'frontend_publication', 'production', 'locks', 'ota_state_absent',
            'business_lease_absent', 'state', 'evidence_sha256'}
    if (not isinstance(intent, dict) or set(intent) != keys or intent['failed_sha'] != FAILED_SHA
            or not isinstance(intent['closing_sha'], str)
            or re.fullmatch(r'[a-f0-9]{40}', intent['closing_sha']) is None
            or intent['closing_sha'] == FAILED_SHA or intent['source_hashes'] != SOURCE_HASHES
            or intent['frontend_publication']['completed'] != FRONTEND_COMPLETED
            or intent['production'] != {'sha': FAILED_SHA, 'state': 'SUCCEEDED',
                'units': ['health-backend', 'celery-worker', 'celery-beat', 'health-frontend'],
                'loopback': 'healthy', 'public': 'healthy'}
            or intent['ota_state_absent'] is not True or intent['business_lease_absent'] is not True
            or intent['state'] != 'CLOSING_PREINTENT_OTA_FAILURE'
            or intent['evidence_sha256'] != digest({k: v for k, v in intent.items()
                                                    if k not in {'state', 'evidence_sha256'}})
            or completed != {'state': TERMINAL, 'failed_sha': FAILED_SHA,
                              'intent_sha256': digest(intent)}):
        raise ClosureError('pre-intent failure closure binding differs')
    consumer = intent['installed_consumer']
    source = server.STATE / 'bootstrap' / intent['closing_sha'] / 'source'
    closing_executor = source / 'scripts/trusted_release_server.py'
    server.secure_path(closing_executor)
    expected_executor = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
        '-C', str(source), 'show', intent['closing_sha'] + ':scripts/trusted_release_server.py'],
        env=ENV, capture_output=True, check=True, timeout=30).stdout
    if closing_executor.read_bytes() != expected_executor:
        raise ClosureError('historical closing consumer changed')
    executor_sha256 = hashlib.sha256(expected_executor).hexdigest()
    authorization = consumer.get('authorization') if isinstance(consumer, dict) else None
    try:
        server.validate_policy(authorization, now=0)
    except Exception:  # noqa: BLE001 - historical validator emits one fixed diagnostic
        raise ClosureError('closure-aware installed consumer binding differs') from None

    def valid_identity(value, expected_sha256=None):
        return (isinstance(value, dict) and set(value) == {'device', 'inode', 'sha256'}
                and type(value['device']) is int and value['device'] >= 0
                and type(value['inode']) is int and value['inode'] > 0
                and isinstance(value['sha256'], str)
                and re.fullmatch(r'[a-f0-9]{64}', value['sha256']) is not None
                and (expected_sha256 is None or value['sha256'] == expected_sha256))

    if (not isinstance(consumer, dict) or set(consumer) != {
            'sha', 'executor_sha256', 'authorization', 'authorization_file', 'installed_executor'}
            or consumer['sha'] != intent['closing_sha']
            or consumer['executor_sha256'] != executor_sha256
            or authorization['sha'] != intent['closing_sha']
            or authorization['executor_sha256'] != executor_sha256
            or not valid_identity(consumer['authorization_file'])
            or not valid_identity(consumer['installed_executor'], executor_sha256)):
        raise ClosureError('closure-aware installed consumer binding differs')
    official = intent['official']
    expected_run = {'id': RUN_ID, 'run_attempt': RUN_ATTEMPT, 'workflow_id': WORKFLOW_ID,
        'path': '.github/workflows/trusted-ota.yml', 'head_sha': FAILED_SHA,
        'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed',
        'conclusion': 'failure'}
    if (not isinstance(official, dict) or set(official) != {
            'run', 'job_id', 'steps', 'artifact', 'workflow_run', 'entries'}
            or official['run'] != expected_run or official['job_id'] != JOB_ID
            or official['steps'] != REQUIRED_STEPS or official['entries'] != ENTRY_DIGESTS):
        raise ClosureError('historical official proof differs')
    validate_official_metadata({**official['run'],
        'repository': {'full_name': REPOSITORY},
        'head_repository': {'full_name': REPOSITORY}}, {'total_count': 1, 'jobs': [{
        'id': JOB_ID, 'name': 'ota', 'status': 'completed', 'conclusion': 'failure',
        'steps': [{'name': name, 'status': 'completed', 'conclusion': result}
                  for name, result in REQUIRED_STEPS.items()]}]},
        {**official['artifact'], 'workflow_run': official['workflow_run']})
    if frontend_publication_evidence(server) != intent['frontend_publication']:
        raise ClosureError('historical frontend publication changed')
    operator = source / 'scripts/trusted_ota_preintent_retirement.py'
    server.secure_path(operator)
    expected = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(source),
        'show', intent['closing_sha'] + ':scripts/trusted_ota_preintent_retirement.py'],
        env=ENV, capture_output=True, check=True, timeout=30).stdout
    if (operator.read_bytes() != expected
            or hashlib.sha256(expected).hexdigest() != intent['closure_operator_sha256']):
        raise ClosureError('reviewed pre-intent failure closure operator changed')
    failed_source = server.STATE / 'bootstrap' / FAILED_SHA / 'source'
    for name, expected_hash in SOURCE_HASHES.items():
        server.secure_path(failed_source / name)
        if hashlib.sha256((failed_source / name).read_bytes()).hexdigest() != expected_hash:
            raise ClosureError('historical publisher source changed')


def verify_closing_ci(source, sha, token):
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B',
        str(source / 'scripts/trusted_release_gate.py'), '--sha', sha,
        '--workflow-sha', sha, '--target', 'full', '--token-stdin'], env=ENV,
        input=token.encode('ascii'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=90)


def context(sha, token):
    if (os.geteuid() != 0 or not sys.flags.isolated or not sys.flags.no_site
            or not sys.flags.dont_write_bytecode or sys.executable != '/usr/bin/python3.12'
            or re.fullmatch(r'[a-f0-9]{40}', sha) is None or sha == FAILED_SHA):
        raise ClosureError('isolated root closing revision required')
    source = ROOT / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/trusted_ota_preintent_retirement.py'
    if Path(__file__).absolute() != entry:
        raise ClosureError('canonical closing operator required')
    for file in (entry, entry.with_name('bootstrap_trusted_release.py')):
        for path in [*reversed(file.parents), file]:
            info = path.lstat()
            if (info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                    or not (stat.S_ISREG(info.st_mode) if path == file else stat.S_ISDIR(info.st_mode))
                    or (path == file and info.st_nlink != 1)):
                raise ClosureError('unsafe canonical operator metadata')
        expected = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
            '-c', 'core.fsmonitor=false', '-C', str(source), 'show', sha + ':scripts/' + file.name],
            env=ENV, capture_output=True, check=True, timeout=30).stdout
        if expected != file.read_bytes():
            raise ClosureError('canonical operator bytes changed')
    if os.path.lexists(entry.parent / '__pycache__'):
        raise ClosureError('cached canonical operator forbidden')
    spec = importlib.util.spec_from_file_location('ota_preintent_closing_bootstrap',
                                                  entry.with_name('bootstrap_trusted_release.py'))
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    checked, server = bootstrap.reviewed_source(sha)
    if checked != source:
        raise ClosureError('closing canonical source differs')
    verify_closing_ci(source, sha, token)
    return bootstrap, server, source


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    os.umask(0o077)
    token = private_github_token(sys.stdin.buffer.read(8193))
    bootstrap, server, source = context(args.sha, token)
    launcher = server.STATE / 'launcher.lock'
    server.secure_path(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = bootstrap._acquire_existing_build_lock(FAILED_SHA)
        if build_fd is None:
            raise ClosureError('original build lock required')
        def check():
            bootstrap._assert_original_lock(launcher, fd)
            bootstrap._assert_original_lock(server.STATE / FAILED_SHA / 'build.lock', build_fd)
        result = close_transaction(Adapter(bootstrap, server, source, args.sha, token, check),
                                   args.evidence_sha256)
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - terminal CLI emits only a closed diagnostic
        print('OTA pre-intent failure closure blocked; preserve evidence; retry forbidden', file=sys.stderr)
        sys.exit(1)
