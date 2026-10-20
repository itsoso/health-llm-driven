"""One-shot administrative acknowledgement; UNKNOWN remains UNKNOWN.

Does not retire a release, reset data, revoke credentials, or authorize retry.
Its directory is deliberately outside every deployment history consumer.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time

STATE = Path('/var/lib/reva-release')
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}
TERMINAL = 'UNKNOWN_ACCEPTED_AUDIT_ONLY'
RECONCILED = 'FAILED_ACK_RECONCILED_AUDIT_ONLY'
FAILED_ACK_OPERATOR = 'f373e2bc1c89d3ec7d10e8a50ee6ae3bce22a3c4'
FAILED_ACK_INTENT = 'ca5f1c0d3a8bcb32cdcb40afcfa64f44e14d6f8ac2e95de5708baa5a867ce701'
TARGET = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
OPERATION = 'a71c3840b6f24bc79937d178cb838066'
ORIGINAL_OPERATOR = '6d3374d77e69522406abd812c80571ce13ac439c'
CHATLOG_PID = '3202404'
CHATLOG_START = '2816083071'
CHATLOG_KEY = 'SHA256:j52PPMj8cjEgvJqtcRpU/vyp7QXucSGUNemBmtVOdPY'
CHATLOG_AUTH_TIME = '1792382497889802'
CHATLOG_PROFILES = (
    (CHATLOG_PID, CHATLOG_START, CHATLOG_AUTH_TIME, '2026-10-19 04:01:30 UTC', '2026-10-19 04:01:45 UTC'),
    ('2367912', '2825295752', '1792474624683288', '2026-10-20 05:37:00 UTC', '2026-10-20 05:37:15 UTC'),
)


class AcknowledgementError(Exception):
    """Static secret-free diagnostic."""


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def acknowledge(adapter, *, accept_unknown=False, evidence_sha256=None):
    """Inspection has no durable writes. An execution attempt is never reusable."""
    if os.path.lexists(adapter.record):
        raise AcknowledgementError('acknowledgement already attempted; retry forbidden')
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_UNKNOWN_NO_RETRY_AUTHORITY', 'evidence_sha256': fingerprint}
    if accept_unknown is not True:
        raise AcknowledgementError('explicit unknown review write acceptance required')
    if evidence_sha256 != fingerprint:
        raise AcknowledgementError('inspection evidence changed')
    adapter.prepare_record()
    adapter.write('intent.json', {'evidence': evidence, 'evidence_sha256': fingerprint,
        'accept_unknown_review_writes': True, 'original_outcome': 'UNKNOWN'})
    if adapter.inspect() != evidence:
        raise AcknowledgementError('evidence changed after durable intent')
    key = secrets.token_bytes(32)  # Ephemeral; never persisted or printed.
    before = adapter.inspect_account(key)
    adapter.validate_account(before)
    if adapter.inspect() != evidence:
        raise AcknowledgementError('evidence changed during account observation')
    after = adapter.inspect_account(key)
    adapter.validate_account(after)
    if before != after:
        raise AcknowledgementError('current demo snapshot changed')
    if adapter.inspect() != evidence:
        raise AcknowledgementError('final evidence changed')
    result = {'state': TERMINAL, 'original_outcome': 'UNKNOWN',
        'evidence_sha256': fingerprint, 'account': after,
        'authority': {'reset': False, 'retry': False, 'rotation': False, 'deployment': False},
        'historical_no_write_proven': False, 'reset_authorized': False, 'release_unblocked': False}
    adapter.write('completed.json', result)
    return {'state': TERMINAL, 'original_outcome': 'UNKNOWN', 'evidence_sha256': fingerprint}


def reconcile_failed_ack(adapter, *, accept_unknown=False, evidence_sha256=None):
    """Audit a single fixed failed acknowledgement; never complete or replay it."""
    if os.path.lexists(adapter.record):
        raise AcknowledgementError('reconciliation already attempted; no retry')
    evidence = adapter.inspect()
    key = secrets.token_bytes(32)
    before = adapter.inspect_account(key)
    adapter.validate_account(before)
    if adapter.inspect() != evidence:
        raise AcknowledgementError('reconciliation evidence changed')
    after = adapter.inspect_account(key)
    adapter.validate_account(after)
    if before != after or adapter.inspect() != evidence:
        raise AcknowledgementError('reconciliation snapshot changed')
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'RECONCILIATION_INSPECTED_ONLY', 'evidence_sha256': fingerprint}
    if accept_unknown is not True or evidence_sha256 != fingerprint:
        raise AcknowledgementError('fresh explicit reconciliation required')
    # All dependency, account and state proofs precede any new durable record.
    adapter.prepare_record()
    adapter.write('intent.json', {'evidence': evidence, 'evidence_sha256': fingerprint,
        'accept_unknown_review_writes': True, 'original_outcome': 'UNKNOWN'})
    if adapter.inspect() != evidence:
        raise AcknowledgementError('reconciliation evidence changed after intent')
    result = {'state': RECONCILED, 'original_outcome': 'UNKNOWN',
        'evidence_sha256': fingerprint, 'account': after,
        'authority': {'reset': False, 'retry': False, 'rotation': False, 'deployment': False},
        'historical_no_write_proven': False, 'reset_authorized': False, 'release_unblocked': False}
    adapter.write('completed.json', result)
    return {'state': RECONCILED, 'original_outcome': 'UNKNOWN', 'evidence_sha256': fingerprint}


def verify_operator_ci(gate, sha, token_stdin):
    token = gate._stdin_token() if token_stdin else None
    get_json = (lambda url: gate._get_json(url, token=token)) if token is not None else gate._get_json
    gate.verify_release(sha, sha, observed_main=sha, _get_json=get_json)


def context(sha, *, verify_ci=True, token_stdin=False):
    if (re.fullmatch('[a-f0-9]{40}', sha or '') is None or os.geteuid() != 0
            or sys.executable != '/usr/bin/python3.12' or not sys.flags.isolated
            or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or 'SSH_ORIGINAL_COMMAND' in os.environ):
        raise AcknowledgementError('isolated canonical root operator required')
    source = STATE / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/review_maintenance_acknowledgement.py'
    if Path(__file__).absolute() != entry:
        raise AcknowledgementError('canonical acknowledgement entry required')
    for path in [*reversed(entry.parents), entry, entry.with_name('bootstrap_trusted_release.py')]:
        info = path.lstat()
        file = path in (entry, entry.with_name('bootstrap_trusted_release.py'))
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                or (file and info.st_nlink != 1)):
            raise AcknowledgementError('unsafe canonical metadata')
    os.umask(0o077)
    b = load(entry.with_name('bootstrap_trusted_release.py'), 'ack_bootstrap')
    reviewed, server = b.reviewed_source(sha)
    if reviewed != source:
        raise AcknowledgementError('canonical source mismatch')
    helper = source / 'scripts/review_maintenance_retirement.py'
    b.secure(helper)
    retirement = load(helper, 'ack_readonly_helpers')
    if verify_ci:
        gate_path = source / 'scripts/trusted_release_gate.py'
        b.secure(gate_path)
        gate = load(gate_path, 'ack_release_gate')
        verify_operator_ci(gate, sha, token_stdin)
    elif token_stdin:
        raise AcknowledgementError('probe must not consume GitHub credentials')
    return source, b, server, retirement


def validate_profile(old_sha, operation_id):
    if (old_sha, operation_id) != (TARGET, OPERATION):
        raise AcknowledgementError('only the explicitly accepted maintenance is supported')


def validate_failed_pair(start, end, old_sha, operation_id):
    validate_profile(old_sha, operation_id)
    keys = {'operator_sha', 'target_sha', 'operation_id', 'production_identity',
            'production_sha256', 'environment_sha256', 'ci', 'state'}
    if (not isinstance(start, dict) or set(start) != keys or start['state'] != 'STARTED'
            or start['target_sha'] != old_sha or start['operation_id'] != operation_id
            or start['operator_sha'] != ORIGINAL_OPERATOR
            or end != {**start, 'state': 'NEEDS_OPERATOR'}):
        raise AcknowledgementError('exact failed maintenance pair required')


def bounded_read(path, maximum=1_048_576):
    with path.open('rb') as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise AcknowledgementError('SSH evidence exceeds bound')
    return value


def verify_chatlog_authentication(proc, profile=None):
    """Bind the explicitly accepted historical event to this kernel boot."""
    profile = CHATLOG_PROFILES[0] if profile is None else profile
    if profile not in CHATLOG_PROFILES:
        raise AcknowledgementError('unaccepted SSH profile')
    accepted_pid, _, auth_time, since, until = profile
    boot = bounded_read(proc / 'sys/kernel/random/boot_id', 64).decode().strip().replace('-', '')
    if re.fullmatch('[0-9a-f]{32}', boot) is None:
        raise AcknowledgementError('kernel boot identity unavailable')
    result = subprocess.run(['/usr/bin/journalctl', '--no-pager', '-o', 'json', '--boot',
        '--since', since, '--until', until,
        '_PID=' + accepted_pid], env=ENV, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=15)
    if len(result.stdout) > 1_048_576:
        raise AcknowledgementError('SSH authentication evidence exceeds bound')
    accepted = []
    for raw in result.stdout.splitlines():
        event = json.loads(raw)
        message = event.get('MESSAGE')
        if not isinstance(message, str):
            raise AcknowledgementError('SSH authentication event malformed')
        if message.startswith('Accepted '):
            if (event.get('_PID') != accepted_pid or event.get('_UID') != '0'
                    or event.get('_BOOT_ID') != boot
                    or event.get('__REALTIME_TIMESTAMP') != auth_time
                    or re.fullmatch(r'Accepted publickey for root from [^\s]+ port [0-9]+ ssh2: ED25519 '
                                    + re.escape(CHATLOG_KEY), message) is None):
                raise AcknowledgementError('SSH authentication does not match accepted session')
            accepted.append(event)
    if len(accepted) != 1:
        raise AcknowledgementError('unique accepted SSH authentication unavailable')


def dynamic_chatlog_authentication(proc, pid, start_ticks):
    """Authenticate a reconnect by the fixed key, never by a reusable PID alone."""
    boot = bounded_read(proc / 'sys/kernel/random/boot_id', 64).decode().strip().replace('-', '')
    ticks = os.sysconf('SC_CLK_TCK')
    if (re.fullmatch('[a-f0-9]{32}', boot) is None or not pid.isdigit()
            or not start_ticks.isdigit() or type(ticks) is not int or ticks <= 0):
        raise AcknowledgementError('reconnected SSH identity unavailable')
    start_us = int(start_ticks) * 1_000_000 // ticks
    observed_us = int(time.monotonic() * 1_000_000)
    result = subprocess.run(['/usr/bin/journalctl', '--no-pager', '-o', 'json', '--boot',
        '_PID=' + pid], env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=True, timeout=15)
    if len(result.stdout) > 1_048_576:
        raise AcknowledgementError('reconnected SSH authentication exceeds bound')
    accepted = []
    for raw in result.stdout.splitlines():
        event = json.loads(raw)
        message = event.get('MESSAGE')
        if not isinstance(message, str):
            raise AcknowledgementError('reconnected SSH event malformed')
        if not message.startswith('Accepted '):
            continue
        monotonic, timestamp = event.get('__MONOTONIC_TIMESTAMP'), event.get('__REALTIME_TIMESTAMP')
        if (event.get('_PID') != pid or event.get('_BOOT_ID') != boot
                or not isinstance(monotonic, str) or not monotonic.isdigit()
                or not isinstance(timestamp, str) or not timestamp.isdigit()):
            raise AcknowledgementError('reconnected SSH event identity unavailable')
        if int(monotonic) < start_us:
            continue  # A previous incarnation of this PID cannot authenticate this one.
        if (int(monotonic) > observed_us or event.get('_UID') != '0'
                or re.fullmatch(r'Accepted publickey for root from [^\s]+ port [0-9]+ ssh2: ED25519 '
                                + re.escape(CHATLOG_KEY), message) is None):
            raise AcknowledgementError('reconnected SSH authentication differs')
        accepted.append((timestamp, monotonic, boot))
    if len(accepted) != 1:
        raise AcknowledgementError('unique reconnected SSH authentication unavailable')
    return accepted[0]


def chatlog_snapshot(proc, profile=None):
    profile = CHATLOG_PROFILES[0] if profile is None else profile
    if profile not in CHATLOG_PROFILES:
        raise AcknowledgementError('unaccepted SSH profile')
    return _chatlog_snapshot(proc, profile)


def _chatlog_snapshot(proc, profile):
    accepted_pid, accepted_start, _, _, _ = profile
    entry = proc / accepted_pid
    before = bounded_read(entry / 'stat')
    fields = before.rsplit(b')', 1)[-1].split()
    if len(fields) < 20 or fields[19].decode() != accepted_start or fields[4] != b'0':
        raise AcknowledgementError('accepted SSH process identity changed')
    status = bounded_read(entry / 'status')
    uid = [line.split()[1:] for line in status.splitlines() if line.startswith(b'Uid:')]
    if uid != [[b'0'] * 4]:
        raise AcknowledgementError('accepted SSH UID changed')
    argv = bounded_read(entry / 'cmdline')
    if not argv.startswith((b'sshd:', b'sshd-session:')):
        raise AcknowledgementError('accepted process is not SSH')
    descriptors = list((entry / 'fd').iterdir())
    if len(descriptors) > 4096:
        raise AcknowledgementError('SSH descriptor inventory exceeds bound')
    sockets = set()
    for descriptor in descriptors:
        value = os.readlink(descriptor)
        match = re.fullmatch(r'socket:\[([0-9]+)\]', value)
        if match:
            sockets.add(match[1])
    listeners = []
    for name, loopback in (('tcp', '0100007F:13A6'), ('tcp6', '00000000000000000000000001000000:13A6')):
        rows = bounded_read(proc / 'net' / name, 4_194_304).decode().splitlines()
        if not rows or 'local_address' not in rows[0]:
            raise AcknowledgementError('TCP inventory unavailable')
        for row in rows[1:]:
            values = row.split()
            if len(values) < 10:
                raise AcknowledgementError('TCP inventory malformed')
            if (profile not in CHATLOG_PROFILES and values[3] == '0A'
                    and values[1].rsplit(':', 1)[-1] == '13A6'
                    and (values[9] not in sockets or values[1] != loopback or values[7] != '0')):
                raise AcknowledgementError('reconnected SSH listener is not unique')
            if values[9] in sockets and values[3] == '0A':
                if values[1] != loopback or values[7] != '0':
                    raise AcknowledgementError('accepted SSH listener changed')
                listeners.append((name, values[1], values[9]))
    if not listeners:
        raise AcknowledgementError('accepted loopback 5030 listener missing')
    after = bounded_read(entry / 'stat').rsplit(b')', 1)[-1].split()
    identity = fields[1:5] + [fields[19]]
    if len(after) < 20 or after[1:5] + [after[19]] != identity:
        raise AcknowledgementError('accepted SSH process changed during observation')
    return {'identity': identity, 'uid': uid, 'argv': argv, 'listeners': sorted(listeners)}


class _TransientProcessObservation(Exception):
    """Discard the entire observation; never skip an unverified process."""


def assert_acknowledgement_ssh_sessions(proc=Path('/proc')):
    for attempt in range(3):
        try:
            return _acknowledgement_ssh_observation(proc)
        except _TransientProcessObservation:
            if attempt == 2:
                raise AcknowledgementError('process inventory unstable after three complete observations') from None


def _acknowledgement_ssh_observation(proc):
    """Only this one-shot audit accepts the user-identified chatlog tunnel.

    No session is terminated. The generic deployment/retirement checks retain
    their original zero-other-SSH rule. Missing journal proof fails closed.
    """
    ancestors, pid = set(), os.getpid()
    while pid > 1:
        if pid in ancestors or len(ancestors) > 64:
            raise AcknowledgementError('operator ancestry uncertain')
        ancestors.add(pid)
        fields = bounded_read(proc / str(pid) / 'stat').rsplit(b')', 1)[-1].split()
        if len(fields) < 20:
            raise AcknowledgementError('operator ancestry malformed')
        pid = int(fields[1])
    entries = list(proc.iterdir())
    if len(entries) > 100000:
        raise AcknowledgementError('SSH process inventory exceeds bound')
    allowed = None
    selected = None
    dynamic_auth = None
    profiles = {p[0]: p for p in CHATLOG_PROFILES}
    observed = {}
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) in ancestors:
            continue
        try:
            argv = bounded_read(entry / 'cmdline')
        except FileNotFoundError:
            if entry.name in profiles:
                raise
            # No identity was proved: discard the entire observation rather
            # than skipping this PID. A successful attempt still reads all PIDs.
            raise _TransientProcessObservation() from None
        try:
            fields = bounded_read(entry / 'stat').rsplit(b')', 1)[-1].split()
        except FileNotFoundError:
            if entry.name in profiles or argv.startswith((b'sshd:', b'sshd-session:')):
                raise
            raise _TransientProcessObservation() from None
        if len(fields) < 20:
            raise AcknowledgementError('SSH process inventory malformed')
        observed[entry.name] = (argv, fields[1:5] + [fields[19]])
        if fields[1].decode() in profiles:
            raise AcknowledgementError('accepted SSH tunnel has a child process')
        if entry.name in profiles:
            if selected is not None:
                raise AcknowledgementError('multiple accepted SSH profiles present')
            selected = profiles[entry.name]
            args = (proc,) if selected == CHATLOG_PROFILES[0] else (proc, selected)
            allowed = chatlog_snapshot(*args)
            verify_chatlog_authentication(*args)
        elif argv.startswith((b'sshd:', b'sshd-session:')):
            if selected is not None:
                raise AcknowledgementError('other SSH session must finish before acknowledgement')
            # Reject unrelated users/TTY sessions before attempting reconnect
            # authentication, independently of filesystem enumeration order.
            # This shape is necessary, not sufficient: the fixed-key journal,
            # root UID, process identity and sole loopback listener still follow.
            if argv.rstrip(b'\0') not in (b'sshd: root@notty', b'sshd-session: root@notty'):
                raise AcknowledgementError('other SSH session must finish before acknowledgement')
            start_ticks = fields[19].decode()
            dynamic_auth = dynamic_chatlog_authentication(proc, entry.name, start_ticks)
            selected = (entry.name, start_ticks, dynamic_auth[0], None, None)
            allowed = _chatlog_snapshot(proc, selected)
    after = {entry.name for entry in proc.iterdir() if entry.name.isdigit()}
    before = {entry.name for entry in entries if entry.name.isdigit()}
    if after != before:
        removed = before - after
        if not (after - before) and removed and all(
                name in observed and name not in profiles
                and not observed[name][0].startswith((b'sshd:', b'sshd-session:')) for name in removed):
            raise _TransientProcessObservation()
        raise AcknowledgementError('SSH process inventory changed')
    for name, (argv, identity) in observed.items():
        entry = proc / name
        try:
            fields = bounded_read(entry / 'stat').rsplit(b')', 1)[-1].split()
            current_argv = bounded_read(entry / 'cmdline')
        except FileNotFoundError:
            if name in profiles or argv.startswith((b'sshd:', b'sshd-session:')):
                raise
            raise _TransientProcessObservation() from None
        if (len(fields) < 20 or fields[1:5] + [fields[19]] != identity
                or current_argv != argv):
            raise AcknowledgementError('SSH process identity changed')
    if selected is not None and any(identity[0].decode() == selected[0]
                                    for _, identity in observed.values()):
        raise AcknowledgementError('accepted SSH tunnel has a child process')
    if allowed is not None and dynamic_auth is not None:
        if (_chatlog_snapshot(proc, selected) != allowed
                or dynamic_chatlog_authentication(proc, selected[0], selected[1]) != dynamic_auth):
            raise AcknowledgementError('reconnected SSH session changed')
    elif allowed is not None:
        if chatlog_snapshot(*args) != allowed:
            raise AcknowledgementError('accepted SSH session changed')
        verify_chatlog_authentication(*args)
    return ({'exception_used': False} if allowed is None else {
        'exception_used': True, 'pid': int(selected[0]), 'start_ticks': selected[1],
        'uid': 0, 'tty_nr': 0, 'listener_port': 5030, 'loopback_only': True,
        'authenticated_key': CHATLOG_KEY, 'authentication_event_timestamp': selected[2],
        'authority': 'ACKNOWLEDGEMENT_ONLY_USER_CONFIRMED_CHATLOG',
        **({'authentication_monotonic_us': dynamic_auth[1], 'authentication_boot_id': dynamic_auth[2]}
           if dynamic_auth is not None else {})})



def failed_ack_evidence(b):
    record = STATE / 'review-maintenance-acknowledgements' / TARGET
    inventory = b._inventory(record, {'intent.json'})
    if inventory['intent.json']['sha256'] != FAILED_ACK_INTENT:
        raise AcknowledgementError('fixed failed acknowledgement intent differs')
    intent = b._read_json(record / 'intent.json')
    evidence = intent.get('evidence', {})
    if (intent.get('accept_unknown_review_writes') is not True
            or intent.get('original_outcome') != 'UNKNOWN'
            or evidence.get('closing_sha') != FAILED_ACK_OPERATOR
            or evidence.get('old_sha') != TARGET or evidence.get('operation_id') != OPERATION
            or intent.get('evidence_sha256') != digest(evidence)):
        raise AcknowledgementError('fixed failed acknowledgement invalid')
    return inventory, evidence

def make_adapter(source, b, server, helpers, sha, old_sha, operation_id, check, *, reconcile=False):
    validate_profile(old_sha, operation_id)
    class Adapter:
        # Reuse only methods whose dependency closure is read-only. Do not
        # instantiate either retirement Adapter or lease-based RecoveryProof.
        def _quiescent(self):
            self.check()
            self.b._recovery_process_proof()
            self.ssh_observation = assert_acknowledgement_ssh_sessions()
            self.b._recovery_process_proof()
            self.check()
        _services = helpers.Adapter._services
        def inspect(self):
            evidence = helpers.Adapter.inspect(self)
            evidence['ssh_observation'] = self.ssh_observation
            if reconcile:
                inventory, old_evidence = failed_ack_evidence(b)
                if {**evidence, 'closing_sha': FAILED_ACK_OPERATOR} != old_evidence:
                    raise AcknowledgementError('original failed acknowledgement evidence changed')
                evidence['failed_ack'] = inventory
            return evidence

        def __init__(self):
            self.source, self.b, self.server = source, b, server
            self.sha, self.old_sha, self.operation_id = sha, old_sha, operation_id
            self.check = check
            self.record = STATE / ('review-maintenance-ack-reconciliations' if reconcile else 'review-maintenance-acknowledgements') / old_sha
            self.volatile = Path('/run/lock/health-app-release.review-retired-' + old_sha)
            for filename in ('contained_release_retirement.py', 'recover_contained_services.py',
                             'trusted_review_reset.py', 'contained_recovery_proof.py'):
                b.secure(source / 'scripts' / filename)
            self.c = load(source / 'scripts/contained_release_retirement.py', 'ack_file_readers')
            self.r = load(source / 'scripts/recover_contained_services.py', 'ack_health_readers')
            self.reset = load(source / 'scripts/trusted_review_reset.py', 'ack_snapshot_readers')
            proof = load(source / 'scripts/contained_recovery_proof.py', 'ack_service_readers')
            class SystemdReader:
                def show(self, unit, prop):
                    result = subprocess.run(['/usr/bin/systemctl', 'show', unit,
                        '--property=' + prop, '--value'], env=ENV, stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                        check=True, timeout=15)
                    if len(result.stdout) > 65536:
                        raise AcknowledgementError('systemd property exceeds bound')
                    return result.stdout.strip()
            class ServiceReader:
                _no_jobs = proof.RecoveryProof._no_jobs
                _pids = proof.RecoveryProof._pids
                running_services_snapshot = proof.RecoveryProof.running_services_snapshot
                def __init__(self):
                    self.systemd = SystemdReader()
                    self.proc = Path('/proc')
                    self.cgroup = Path('/sys/fs/cgroup')
            self.p = ServiceReader()

        def _lease(self):
            # Check canonical real location as well as its public alias. A
            # missing lease never supplies ownership or retry permission.
            alias = Path('/var/lock')
            info = alias.lstat()
            run = Path('/run/lock').lstat()
            if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                    or os.readlink(alias) != '/run/lock' or not stat.S_ISDIR(run.st_mode)
                    or run.st_uid != 0 or run.st_gid != 0 or stat.S_IMODE(run.st_mode) != 0o1777):
                raise AcknowledgementError('fixed lock parent invalid')
            if any(os.path.lexists(p) for p in (b.BUSINESS_LEASE, Path('/run/lock/health-app-release'))):
                raise AcknowledgementError('active business lease exists')
            return {'state': 'ABSENT_NOT_AUTHORITY'}

        def _base(self):
            base = helpers.Adapter._base(self)
            audit = STATE / 'review-maintenance' / old_sha
            inventory = b._inventory(audit, {'started.json', 'completed.json'})
            start = b._read_json(audit / 'started.json')
            end = b._read_json(audit / 'completed.json')
            validate_failed_pair(start, end, old_sha, operation_id)
            maintenance_path = source / 'scripts/trusted_review_maintenance.py'
            b.secure(maintenance_path)
            maintenance = load(maintenance_path, 'ack_environment_reader')
            identity, environment_digest, unused_raw = maintenance.production_identity(server)
            del unused_raw
            b.secure(STATE / old_sha / 'deployment.env', private=True)
            if (list(identity) != start['production_identity']
                    or environment_digest != start['production_sha256']
                    or hashlib.sha256((STATE / old_sha / 'deployment.env').read_bytes()).hexdigest() != start['environment_sha256']):
                raise AcknowledgementError('maintenance environment changed')
            base['maintenance'] = inventory
            base['production_environment'] = {'identity': list(identity), 'sha256': environment_digest}
            return base

        def prepare_record(self):
            if not self.record.parent.exists():
                self.record.parent.mkdir(mode=0o700)
                helpers.sync(self.record.parent.parent)
            self.c._private_directory(b, self.record.parent)
            self.record.mkdir(mode=0o700)
            helpers.sync(self.record.parent)

        def write(self, name, value):
            if name not in {'intent.json', 'completed.json'}:
                raise AcknowledgementError('unsupported acknowledgement output')
            self.c._private_directory(b, self.record)
            helpers.write_json(self.record / name, value)

        def validate_account(self, value):
            helpers.validate_account_summary(value)

        def inspect_account(self, key):
            self._quiescent()
            process = subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B',
                str(source / 'scripts/review_maintenance_acknowledgement.py'), '--sha', sha,
                '--release-sha', old_sha, '--operation-id', operation_id, '--account-probe',
                *(['--reconcile-failed-ack'] if reconcile else [])],
                env=ENV, input=key, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=180, check=True)
            if len(process.stdout) > 16384:
                raise AcknowledgementError('account proof exceeds bound')
            self._quiescent()
            return json.loads(process.stdout)

        # Inherited mutators must be unreachable, even by accidental dispatch.
        def isolate(self, evidence):
            raise AcknowledgementError('revocation forbidden')

        def archive(self, evidence):
            raise AcknowledgementError('archiving forbidden')

        def _copy_archives(self, evidence):
            raise AcknowledgementError('copies forbidden')

    return Adapter()


def account_child(sha, old_sha, operation_id, *, reconcile=False):
    validate_profile(old_sha, operation_id)
    source, b, server, helpers = context(sha, verify_ci=False)
    record = STATE / 'review-maintenance-acknowledgements' / old_sha
    b.secure(record)
    intent = b._read_json(record / 'intent.json')
    evidence = intent.get('evidence', {})
    if reconcile:
        failed_ack_evidence(b)
    if (intent.get('accept_unknown_review_writes') is not True or intent.get('original_outcome') != 'UNKNOWN'
            or intent.get('evidence_sha256') != digest(evidence) or evidence.get('closing_sha') != (FAILED_ACK_OPERATOR if reconcile else sha)
            or evidence.get('old_sha') != old_sha or evidence.get('operation_id') != operation_id
            or evidence.get('lease') != {'state': 'ABSENT_NOT_AUTHORITY'}
            or os.path.lexists(record / 'completed.json')):
        raise AcknowledgementError('fixed current demo probe authorization invalid')
    key = sys.stdin.buffer.read(33)
    if len(key) != 32:
        raise AcknowledgementError('ephemeral private key required')
    # Parent retains launcher/build locks and checks process quiescence before
    # and after this bounded child. Checking here would reject the parent.
    if os.path.lexists(b.BUSINESS_LEASE):
        raise AcknowledgementError('business lease exists')
    target = b.canonical_source(old_sha)
    reset = helpers.load(source / 'scripts/trusted_review_reset.py', 'ack_reset_readers')
    reset._assert_isolated_search_path()
    reset._validate_production(old_sha, target, b, server)
    # Production proof above validates this root-managed dependency tree.
    sys.path.append('/opt/health-app/backend/venv/lib/python3.12/site-packages')
    environment = reset._parse_maintenance_environment(server.read_production_env())
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(target / 'backend')
    sys.path.insert(0, str(target / 'backend'))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(target, environment)
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        url = make_url(environment['DATABASE_URL'])
        if not url.database:
            raise AcknowledgementError('explicit database required')
        engine = create_engine(url, isolation_level='REPEATABLE READ', connect_args={'connect_timeout': 5})
        try:
            with engine.connect() as connection, connection.begin():
                result = helpers.inspect_account_rows(connection, environment['APP_STORE_REVIEW_DEMO_ACCOUNT'], key, url.database)
        finally:
            engine.dispose()
    return result


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--sha', required=True)
        parser.add_argument('--release-sha', required=True)
        parser.add_argument('--operation-id', required=True)
        parser.add_argument('--accept-unknown-review-writes', action='store_true')
        parser.add_argument('--evidence-sha256')
        parser.add_argument('--token-stdin', action='store_true')
        parser.add_argument('--reconcile-failed-ack', action='store_true')
        parser.add_argument('--account-probe', action='store_true', help=argparse.SUPPRESS)
        args = parser.parse_args()
        if (re.fullmatch('[a-f0-9]{40}', args.release_sha) is None or args.sha == args.release_sha
                or re.fullmatch('[a-f0-9]{32}', args.operation_id) is None
                or (args.evidence_sha256 is not None and re.fullmatch('[a-f0-9]{64}', args.evidence_sha256) is None)):
            raise AcknowledgementError('exact acknowledgement identifiers required')
        validate_profile(args.release_sha, args.operation_id)
        if args.account_probe:
            if args.accept_unknown_review_writes or args.evidence_sha256 or args.token_stdin:
                raise AcknowledgementError('invalid probe arguments')
            result = account_child(args.sha, args.release_sha, args.operation_id, reconcile=args.reconcile_failed_ack)
        else:
            source, b, server, helpers = context(args.sha, token_stdin=args.token_stdin)
            lock = b.STATE / 'launcher.lock'
            b.secure(lock, private=True)
            fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
            build_fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                build = b.STATE / args.release_sha / 'build.lock'
                exists = os.path.lexists(build)
                build_fd = b._acquire_existing_build_lock(args.release_sha)
                def check():
                    b._assert_original_lock(lock, fd)
                    if os.path.lexists(build) != exists:
                        raise AcknowledgementError('build lock presence changed')
                    if build_fd is not None:
                        b._assert_original_lock(build, build_fd)
                adapter = make_adapter(source, b, server, helpers, args.sha, args.release_sha, args.operation_id, check, reconcile=args.reconcile_failed_ack)
                operation = reconcile_failed_ack if args.reconcile_failed_ack else acknowledge
                result = operation(adapter, accept_unknown=args.accept_unknown_review_writes, evidence_sha256=args.evidence_sha256)
            finally:
                if build_fd is not None:
                    os.close(build_fd)
                os.close(fd)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('acknowledgement rejected or incomplete; preserve evidence; do not retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
