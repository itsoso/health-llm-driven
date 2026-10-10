"""Internal metadata-only lifecycle history validation and read-only inspection.

No dispatcher, filesystem I/O, lease mutation, retries or cleanup exist here.
Digests prove consistency, never provenance. Injected authenticate/readback must
come from a separately reviewed canonical host adapter under the ORIGINAL
operation's still-live locks. Passing caller dictionaries is not authentication.
An observed completed file is insufficient: the adapter must authenticate a
separate confirmed durability/final-guard acknowledgement. No current production
entrypoint accepts these histories; immutable dormant install audits stay intact.
"""
import hashlib
import json
import re
import stat

from scripts.neo_wechat_lifecycle import validate_dormant_receipt, LifecycleError

NAMESPACE = 'runtime-lifecycle-v1'
STEPS = {
    'activate': ('verify_prerequisites', 'start_socket', 'start_service',
                 'publish_proxy_include', 'validate_proxy', 'reload_proxy', 'verify_final_state'),
    'stop': ('verify_prerequisites', 'stop_units', 'unpublish_proxy_include',
             'validate_proxy', 'reload_proxy', 'verify_final_state'),
}
BINDING_KEYS = frozenset(('dormant_receipt_sha256', 'provisioning_receipt_sha256',
    'runtime_sha256', 'service_unit_sha256', 'socket_unit_sha256', 'config_sha256', 'proxy_receipt_sha256'))
PRESERVED_KEYS = frozenset(('health_services_sha256', 'keys_identity_sha256',
    'data_directory_identity_sha256', 'audit_root_identity_sha256', 'accounts_groups_sha256'))
_CONTEXT_KEYS = frozenset(('version', 'namespace', 'operation_id', 'kind', 'install_operation_id',
    'provisioning_operation_id', 'dormant_receipt_sha256', 'provisioning_receipt_sha256',
    'runtime_sha256', 'publisher_sha', 'production_sha', 'lease_operation_id', 'lease_identity',
    'expected_bindings', 'expected_preserved'))
_RECORD_KEYS = frozenset(('version', 'namespace', 'operation_id', 'kind', 'sequence', 'phase',
    'step', 'context_sha256', 'dormant_receipt_sha256', 'provisioning_receipt_sha256',
    'runtime_sha256', 'publisher_sha', 'previous_record_sha256', 'evidence_sha256'))
_OBSERVATION_KEYS = frozenset(('version', 'bindings', 'preserved', 'units', 'proxy',
                              'socket_path', 'readiness', 'lease'))
_PROOF_KEYS = frozenset(('version', 'original_provenance', 'context_sha256', 'lease_operation_id',
                        'lease_identity', 'completion'))
_UNITS = frozenset(('neo-wechat.service', 'neo-wechat.socket'))


class HistoryError(ValueError):
    def __init__(self):
        super().__init__('lifecycle_history_rejected')


def _require(condition):
    if not condition:
        raise HistoryError()


def _hex(value, size):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def _canonical(value):
    budget = [512, 65536]
    def check(item, depth):
        budget[0] -= 1
        _require(depth <= 12 and budget[0] >= 0)
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            _require(-(2**63) <= item < 2**64)
            return
        if type(item) is str:
            _require(len(item) <= 4096)
            budget[1] -= len(item)
            _require(budget[1] >= 0)
            return
        if type(item) is list:
            _require(len(item) <= 128)
            for child in item:
                check(child, depth+1)
            return
        _require(type(item) is dict and len(item) <= 64)
        for key, child in item.items():
            _require(type(key) is str)
            check(key, depth+1)
            check(child, depth+1)
    check(value, 0)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    _require(len(raw) <= 65536)
    return raw


def digest(value):
    return hashlib.sha256(_canonical(value).encode('ascii')).hexdigest()


def _copy(value):
    return json.loads(_canonical(value))


def _identity(value):
    return (type(value) is list and len(value) == 2
            and all(type(n) is int and 0 <= n < 2**64 for n in value))


def _lease_identity(value):
    return type(value) is list and len(value) == 2 and all(_identity(v) for v in value) and value[0] != value[1]


def _hash_map(value, keys):
    _require(type(value) is dict and set(value) == keys and all(_hex(v, 64) for v in value.values()))


def validate_context(value):
    context = _copy(value)
    _require(type(context) is dict and set(context) == _CONTEXT_KEYS)
    _require(type(context['version']) is int and context['version'] == 1)
    _require(context['namespace'] == NAMESPACE and type(context['kind']) is str and context['kind'] in STEPS)
    _require(all(_hex(context[k], 32) for k in ('operation_id', 'install_operation_id',
                                              'provisioning_operation_id', 'lease_operation_id')))
    _require(context['lease_operation_id'] == context['operation_id'])
    _require(context['operation_id'] not in (context['install_operation_id'], context['provisioning_operation_id']))
    _require(_lease_identity(context['lease_identity']))
    _require(all(_hex(context[k], 40) for k in ('publisher_sha', 'production_sha')))
    _require(all(_hex(context[k], 64) for k in ('dormant_receipt_sha256', 'provisioning_receipt_sha256', 'runtime_sha256')))
    _hash_map(context['expected_bindings'], BINDING_KEYS)
    _hash_map(context['expected_preserved'], PRESERVED_KEYS)
    _require(all(context['expected_bindings'][k] == context[k]
                 for k in ('dormant_receipt_sha256', 'provisioning_receipt_sha256', 'runtime_sha256')))
    return context


def _validate_lease(context, lease):
    _require(type(lease) is dict and set(lease) == {'operation_id', 'identity'})
    _require(lease['operation_id'] == context['lease_operation_id'])
    _require(_lease_identity(lease['identity']) and lease['identity'] == context['lease_identity'])


def validate_observation(context, value):
    context = validate_context(context)
    observed = _copy(value)
    _require(type(observed) is dict and set(observed) == _OBSERVATION_KEYS)
    _require(type(observed['version']) is int and observed['version'] == 1)
    _require(observed['bindings'] == context['expected_bindings'])
    _require(observed['preserved'] == context['expected_preserved'])
    _require(type(observed['units']) is dict and set(observed['units']) == _UNITS)
    for row in observed['units'].values():
        _require(type(row) is dict and set(row) == {'state', 'unit_file_state', 'dropins'})
        _require(row['state'] in ('active', 'inactive') and row['unit_file_state'] == 'static' and row['dropins'] == [])
    proxy = observed['proxy']
    _require(type(proxy) is dict and set(proxy) == {'entry', 'loaded', 'validated'})
    _require(proxy['entry'] in ('absent', 'recorded') and proxy['loaded'] in ('absent', 'recorded')
             and type(proxy['validated']) is bool)
    _require(observed['socket_path'] in ('absent', 'recorded'))
    _require(observed['readiness'] in ('unknown', 'ready', 'stopped'))
    _validate_lease(context, observed['lease'])
    return observed


def _protocol(kind):
    return [(step, phase) for step in STEPS[kind] for phase in ('intent', 'verified')] + [('complete', 'completed')]


def validate_history(context, records):
    context = validate_context(context)
    protocol = _protocol(context['kind'])
    _require(type(records) is list and len(records) <= len(protocol))
    previous = digest(context)
    result = []
    for index, source in enumerate(records):
        row = _copy(source)
        _require(type(row) is dict and set(row) == _RECORD_KEYS)
        _require(type(row['version']) is int and row['version'] == 1)
        _require(type(row['sequence']) is int and row['sequence'] == index+1)
        _require(all(row[key] == context[key] for key in ('namespace', 'operation_id', 'kind',
            'dormant_receipt_sha256', 'provisioning_receipt_sha256', 'runtime_sha256', 'publisher_sha')))
        _require(row['context_sha256'] == digest(context) and row['previous_record_sha256'] == previous)
        _require((row['step'], row['phase']) == protocol[index])
        _require(row['evidence_sha256'] is None if row['phase'] == 'intent' else _hex(row['evidence_sha256'], 64))
        if row['phase'] == 'completed':
            _require(row['evidence_sha256'] == result[-1]['evidence_sha256'])
        result.append(row)
        previous = digest(row)
    return result


def make_record(context, records, phase, step, evidence=None):
    context = validate_context(context)
    rows = validate_history(context, records)
    _require(type(phase) is str and type(step) is str)
    if phase == 'intent':
        _require(evidence is None)
        evidence_hash = None
    else:
        evidence_hash = digest(validate_observation(context, evidence))
    row = {key: context[key] for key in ('version', 'namespace', 'operation_id', 'kind',
        'dormant_receipt_sha256', 'provisioning_receipt_sha256', 'runtime_sha256', 'publisher_sha')}
    row.update(sequence=len(rows)+1, phase=phase, step=step, context_sha256=digest(context),
               previous_record_sha256=digest(rows[-1]) if rows else digest(context), evidence_sha256=evidence_hash)
    validate_history(context, rows+[row])
    return row


def _unique(pairs):
    value = {}
    for key, child in pairs:
        _require(key not in value)
        value[key] = child
    return value


def decode_history(context, raw):
    _require(type(raw) is bytes and len(raw) <= 131072)
    try:
        lines = raw.splitlines()
        _require(len(lines) <= 15 and all(line for line in lines))
        records = [json.loads(line, object_pairs_hook=_unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(HistoryError())) for line in lines]
        return validate_history(context, records)
    except (ValueError, UnicodeError, RecursionError):
        raise HistoryError() from None


def _proof(context, value, terminal_hash):
    proof = _copy(value)
    _require(type(proof) is dict and set(proof) == _PROOF_KEYS)
    _require(type(proof['version']) is int and proof['version'] == 1)
    _require(proof['original_provenance'] == 'authenticated' and proof['context_sha256'] == digest(context))
    _require(proof['lease_operation_id'] == context['lease_operation_id'])
    _require(_lease_identity(proof['lease_identity']) and proof['lease_identity'] == context['lease_identity'])
    completion = proof['completion']
    _require(type(completion) is dict and set(completion) == {'record_sha256', 'fsync_confirmed', 'final_guard_confirmed'})
    _require(completion['record_sha256'] == terminal_hash and completion['fsync_confirmed'] is True
             and completion['final_guard_confirmed'] is True)
    return proof


def _terminal(context, observed):
    active = context['kind'] == 'activate'
    _require(all(row['state'] == ('active' if active else 'inactive') for row in observed['units'].values()))
    _require(observed['proxy'] == {'entry': 'recorded' if active else 'absent',
                                  'loaded': 'recorded' if active else 'absent', 'validated': True})
    _require(observed['socket_path'] == ('recorded' if active else 'absent'))
    _require(observed['readiness'] == ('ready' if active else 'stopped'))


def _result(classification='RETAIN_UNCERTAIN'):
    return {'classification': classification, 'authority': 'none', 'executable_actions': [],
            'preserve_original_lease': True}


def inspect_recovery(context, records, *, authenticate=None, readback=None):
    """Inspect only. Missing final durability acknowledgement is always uncertain.

    authenticate must validate original receipt/record provenance and the live
    original lease under locks, not trust hashes or booleans supplied by a user.
    readback must inspect exact bounded host metadata, never credential contents.
    Both are injected trusted code, not API fields. Even confirmed completion
    grants no permission to write, replay, release locks, stop, or remove anything.
    """
    try:
        context = validate_context(context)
        rows = validate_history(context, records)
        _require(len(rows) == len(_protocol(context['kind'])) and callable(authenticate) and callable(readback))
        proof = _proof(context, authenticate(_copy(context)), digest(rows[-1]))
        observed = validate_observation(context, readback(_copy(context)))
        _terminal(context, observed)
        _require(digest(observed) == rows[-1]['evidence_sha256'])
        _require(_proof(context, authenticate(_copy(context)), digest(rows[-1])) == proof)
        return _result('CONFIRMED_ORIGINAL_COMPLETION')
    except Exception:
        return _result()


# Existing provision-v1 writer remains unchanged. Its raw newline-canonical
# record hashes differ intentionally from the runtime dictionary hash chain.
PROVISION_FILES = ('encryption_key', 'admin_password_hash', 'slack_webhook', 'config.json')
_PROVISION_CONTEXT_KEYS = frozenset(('version', 'namespace', 'operation_id', 'install_operation_id',
    'dormant_receipt_sha256', 'publisher_sha', 'runtime_sha256', 'production_sha',
    'lease_operation_id', 'lease_identity', 'config_identity', 'audit_root_identity',
    'owner_uid', 'audit_gid', 'bridge_gid'))
_FILE_METADATA_KEYS = frozenset(('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns'))
_PROVISION_BASE_KEYS = frozenset(('version', 'kind', 'phase', 'sequence', 'operation_id',
    'dormant_receipt_sha256', 'publisher_sha', 'previous_record_sha256'))


def validate_provision_context(value, dormant_receipt):
    try:
        original = validate_dormant_receipt(dormant_receipt)
    except LifecycleError:
        raise HistoryError() from None
    context = _copy(value)
    _require(type(context) is dict and set(context) == _PROVISION_CONTEXT_KEYS)
    _require(type(context['version']) is int and context['version'] == 1 and context['namespace'] == 'provision-v1')
    _require(all(_hex(context[key], 32) for key in ('operation_id', 'install_operation_id', 'lease_operation_id')))
    _require(context['install_operation_id'] == original['operation_id'])
    _require(context['operation_id'] != context['install_operation_id'])
    _require(context['lease_operation_id'] == context['operation_id'] and _lease_identity(context['lease_identity']))
    _require(context['dormant_receipt_sha256'] == digest(original))
    _require(all(context[key] == original[key] for key in ('production_sha', 'runtime_sha256')))
    _require(_hex(context['publisher_sha'], 40))
    _require(_identity(context['config_identity']) and _identity(context['audit_root_identity'])
             and context['config_identity'] != context['audit_root_identity'])
    _require(all(type(context[key]) is int and 0 <= context[key] < 2**32
                 for key in ('owner_uid', 'audit_gid', 'bridge_gid')))
    return context


def _file_metadata(context, name, value):
    metadata = _copy(value)
    _require(type(metadata) is dict and set(metadata) == _FILE_METADATA_KEYS)
    _require(all(type(v) is int and 0 <= v < 2**64 for v in metadata.values()))
    _require(metadata['nlink'] == 1 and 0 < metadata['size'] <= 8192)
    _require(metadata['uid'] == context['owner_uid'])
    _require(metadata['gid'] == (context['bridge_gid'] if name == 'config.json' else context['audit_gid']))
    _require(metadata['mode'] == stat.S_IFREG | (0o640 if name == 'config.json' else 0o600))
    return metadata


def provision_record_digest(record):
    """Hash metadata record serialization only; never accepts credential bytes."""
    return hashlib.sha256((_canonical(record)+'\n').encode('ascii')).hexdigest()


def validate_provision_history(context, dormant_receipt, records):
    context = validate_provision_context(context, dormant_receipt)
    _require(type(records) is list and len(records) <= 10)
    protocol = [('intent', None)] + [(phase, name) for name in PROVISION_FILES
                                    for phase in ('intent', 'verified')] + [('completed', None)]
    previous = context['dormant_receipt_sha256']
    result = []
    identities = set()
    for index, source in enumerate(records):
        row = _copy(source)
        phase, name = protocol[index]
        keys = _PROVISION_BASE_KEYS | ({'filename'} if name else set())
        if phase == 'verified':
            keys |= {'file_identity'}
        if phase == 'completed':
            keys |= {'state', 'activation_authorized'}
        _require(type(row) is dict and set(row) == keys)
        _require(type(row['version']) is int and row['version'] == 1)
        _require(type(row['sequence']) is int and row['sequence'] == index)
        _require(row['kind'] == 'provision' and row['phase'] == phase)
        _require(all(row[key] == context[key] for key in ('operation_id', 'dormant_receipt_sha256', 'publisher_sha')))
        _require(row['previous_record_sha256'] == previous)
        if name:
            _require(row['filename'] == name)
        if phase == 'verified':
            metadata = _file_metadata(context, name, row['file_identity'])
            identity = (metadata['dev'], metadata['ino'])
            _require(identity not in identities)
            identities.add(identity)
        if phase == 'completed':
            _require(row['state'] == 'PROVISIONED_DORMANT' and row['activation_authorized'] is False)
        result.append(row)
        previous = provision_record_digest(row)
    return result


def _provision_observation(context, rows, value):
    observed = _copy(value)
    keys = {'version', 'namespace', 'operation_id', 'install_operation_id', 'dormant_receipt_sha256',
            'publisher_sha', 'runtime_sha256', 'production_sha', 'config_identity', 'audit_root_identity',
            'lease', 'files', 'bridge', 'proxy', 'health_services_unchanged'}
    _require(type(observed) is dict and set(observed) == keys)
    _require(type(observed['version']) is int and observed['version'] == 1)
    for key in ('namespace', 'operation_id', 'install_operation_id', 'dormant_receipt_sha256',
                'publisher_sha', 'runtime_sha256', 'production_sha', 'config_identity', 'audit_root_identity'):
        _require(observed[key] == context[key])
    _require(observed['bridge'] == 'inactive_static' and observed['proxy'] == 'unpublished'
             and observed['health_services_unchanged'] is True)
    _validate_lease(context, observed['lease'])
    files = observed['files']
    _require(type(files) is dict and set(files) == set(PROVISION_FILES))
    expected = {row['filename']: row['file_identity'] for row in rows if row['phase'] == 'verified'}
    for name, metadata in files.items():
        _require(_file_metadata(context, name, metadata) == expected[name])
    return observed


def inspect_provision_recovery(context, dormant_receipt, records, *, authenticate=None, readback=None):
    """Legacy provision completion presence alone is never a success receipt.

    A separately reviewed adapter must authenticate the original successful
    fsync/final-guard acknowledgement; existing provision-v1 files contain no
    such acknowledgement. Partial credentials or a lost lease are never repaired.
    """
    try:
        context = validate_provision_context(context, dormant_receipt)
        rows = validate_provision_history(context, dormant_receipt, records)
        _require(len(rows) == 10 and callable(authenticate) and callable(readback))
        terminal_hash = provision_record_digest(rows[-1])
        proof = _proof(context, authenticate(_copy(context)), terminal_hash)
        _provision_observation(context, rows, readback(_copy(context)))
        _require(_proof(context, authenticate(_copy(context)), terminal_hash) == proof)
        return _result('CONFIRMED_ORIGINAL_COMPLETION')
    except Exception:
        return _result()
