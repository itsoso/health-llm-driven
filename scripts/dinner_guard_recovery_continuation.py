"""Fixed single continuation authorized on 2026-10-23 after contained failure.

Preserves the consumed original intent. No deploy, lease clearance, credentials,
configuration writes, backups, or caller-selectable operation/audit identifiers.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import stat
import re
import traceback

PRIOR_RECOVERY = '6492f31789edf257ace6710cdfdff7b6c6c3b8b6'
PRIOR_DIGEST = '3d9c4ba906fae58c67c25d18bbc0ea2a18be37176a6745347a74387f3f2446a2'
INTENT_PIN = 'bb519db5741aeed48403c686f0f5c7539f0fa77c86a813ad3bdad8f3ae7c7367'
CONTINUATION = 'continuation-20261023-static-unit-proof'
IDENTITY_FIELDS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_ctime_ns', 'st_mtime_ns')


def need(value):
    if not value:
        raise RuntimeError('fixed continuation evidence rejected')


def verify_bridge(old, current, raw_pins, static_pins):
    need(set(old['units']) == set(current['units']) == set(raw_pins) == set(static_pins))
    bridged = dict(current)
    bridged['units'] = {}
    for unit, entry in current['units'].items():
        need(entry['effective_sha256'] == static_pins[unit])
        need(old['units'][unit]['effective_sha256'] == raw_pins[unit])
        bridged['units'][unit] = {**entry, 'effective_sha256': raw_pins[unit]}
    need(bridged == old)


def literal_pins(raw):
    tree = ast.parse(raw)
    matches = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'UNIT_CONFIG_PINS' for t in n.targets)]
    need(len(matches) == 1)
    return ast.literal_eval(matches[0].value)


def validate_intent(data, base):
    need(set(data) == {'recovery_sha', 'failed_sha', 'production_sha', 'snapshot', 'evidence_sha256'})
    need(data['recovery_sha'] == PRIOR_RECOVERY and data['failed_sha'] == base.FAILED
         and data['production_sha'] == base.PRODUCTION and data['evidence_sha256'] == PRIOR_DIGEST)
    evidence = {k: v for k, v in data.items() if k != 'evidence_sha256'}
    need(hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == PRIOR_DIGEST)


def exception_summary(error):
    result, seen = [], set()
    while error is not None and id(error) not in seen and len(result) < 5:
        seen.add(id(error))
        result.append({'exception_type': type(error).__name__,
                       'frames': [{'function': f.name, 'line': f.lineno}
                                  for f in traceback.extract_tb(error.__traceback__)[-12:]]})
        error = error.__cause__ or error.__context__
    return result


class ContinuationProof:
    def __init__(self, base, underlying, audit, original_identity, original, raw_pins):
        self.base, self.underlying, self.audit = base, underlying, audit
        self.original_identity, self.original, self.raw_pins = original_identity, original, raw_pins
        self.failed_sha, self.production_sha = base.FAILED, base.PRODUCTION
        self.phase = 'initial'
        self.first_failure = None

    def original_unchanged(self):
        self.base.secure(self.audit, True)
        names = {p.name for p in self.audit.iterdir()}
        need(names in ({'intent.json'}, {'intent.json', CONTINUATION}))
        ident, raw = self.base.identity(self.audit / 'intent.json', pin=INTENT_PIN)
        need(ident == self.original_identity and json.loads(raw) == self.original)

    def _snapshot(self):
        self.phase = 'snapshot_original'
        self.original_unchanged()
        self.phase = 'snapshot_current'
        current = self.underlying.snapshot()
        self.phase = 'snapshot_static_bridge'
        verify_bridge(self.original['snapshot'], current, self.raw_pins, self.base.UNIT_STATIC_CONFIG_PINS)
        self.original_unchanged()
        return {**current, 'prior_consumed_intent': self.original_identity,
                'prior_recovery_sha': PRIOR_RECOVERY, 'prior_evidence_sha256': PRIOR_DIGEST}

    def _stopped(self):
        self.phase = 'stopped_services'
        self.original_unchanged()
        self.underlying.stopped()
        for unit in ('health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service'):
            systemd = self.underlying.base.systemd
            need(systemd.show(unit, 'ActiveState') == 'inactive'
                 and systemd.show(unit, 'SubState') == 'dead'
                 and systemd.show(unit, 'MainPID') in ('0', '')
                 and not self.underlying.base._pids(unit))
        self.original_unchanged()

    def _running_snapshot(self):
        self.phase = 'running_services'
        self.original_unchanged()
        return self.underlying.running_snapshot()


    def invoke(self, name):
        try:
            return getattr(self, '_' + name)()
        except BaseException as error:
            if self.first_failure is None:
                self.first_failure = {'phase': self.phase, 'exceptions': exception_summary(error)}
            raise

    def snapshot(self):
        return self.invoke('snapshot')

    def stopped(self):
        return self.invoke('stopped')

    def running_snapshot(self):
        return self.invoke('running_snapshot')


def run_continuation(base, source, core, bootstrap, underlying, args):
    need(Path(__file__).absolute() == source / 'scripts/dinner_guard_recovery_continuation.py')
    need(args.accept_20261023_continuation and args.sha != PRIOR_RECOVERY)
    audit = base.STATE / 'contained-service-recoveries' / base.FAILED
    base.secure(audit.parent, True)
    base.secure(audit, True)
    need({p.name for p in audit.iterdir()} == {'intent.json'})
    need(not os.path.lexists(audit / CONTINUATION))
    ident, raw = base.identity(audit / 'intent.json', pin=INTENT_PIN)
    original = json.loads(raw)
    validate_intent(original, base)
    prior = bootstrap.canonical_source(PRIOR_RECOVERY)
    _, source_raw = base.identity(prior / 'scripts/dinner_guard_recovery.py')
    raw_pins = literal_pins(source_raw)
    need(raw_pins == base.UNIT_CONFIG_PINS)
    proof = ContinuationProof(base, underlying, audit, ident, original, raw_pins)
    target = audit / CONTINUATION
    def observe(stage):
        proof.phase = stage
    try:
        result = core.recover_services(proof, target, args.sha, args.evidence_sha256, stage_observer=observe)
        proof.original_unchanged()
        return {**result, 'prior_recovery_sha': PRIOR_RECOVERY,
                'prior_intent_sha256': INTENT_PIN, 'continuation': CONTINUATION}
    except BaseException as error:
        # Static phase, exception class and code locations only: no exception
        # messages, locals, subprocess output, secrets or application payloads.
        diagnostic = {'state': 'CONTINUATION_FAILED', 'phase': getattr(error, 'recovery_stage', proof.phase),
                      'exception_type': type(error).__name__, 'prior_intent_sha256': INTENT_PIN,
                      'exceptions': exception_summary(error), 'first_proof_failure': proof.first_failure,
                      'frames': [{'function': f.name, 'line': f.lineno}
                                 for f in traceback.extract_tb(error.__traceback__)]}
        if os.path.isdir(target):
            core._write(target / 'failure.json', diagnostic)
        print(json.dumps(diagnostic, sort_keys=True), file=sys.stderr)
        raise


def validate_entry(entry):
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site
         and sys.flags.dont_write_bytecode and not sys.flags.optimize)
    entry = Path(entry).absolute()
    need(re.fullmatch(r'/var/lib/reva-release/bootstrap/[a-f0-9]{40}/source/scripts/dinner_guard_recovery_continuation\.py', str(entry)))
    helper = entry.with_name('dinner_guard_recovery.py')
    for path in [*reversed(entry.parents), entry, helper]:
        info = path.lstat()
        need(info.st_uid == 0 and not info.st_mode & 0o022)
        need(stat.S_ISDIR(info.st_mode) if path in entry.parents else
             stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    return helper


def main():
    path = validate_entry(__file__)
    spec = importlib.util.spec_from_file_location('dinner_continuation_base', path)
    base = importlib.util.module_from_spec(spec)
    before = path.lstat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(1000001)
        after = os.fstat(stream.fileno())
    named = path.lstat()
    need(len(raw) <= 1000000 and all(getattr(before, k) == getattr(opened, k) ==
         getattr(after, k) == getattr(named, k) for k in IDENTITY_FIELDS))
    exec(compile(raw, str(path), 'exec', dont_inherit=True), base.__dict__)
    base.main(continuation=lambda *args: run_continuation(base, *args))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('fixed continuation failed; preserve original and continuation evidence', file=sys.stderr)
        sys.exit(1)
