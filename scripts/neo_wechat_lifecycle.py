"""Pure, versioned lifecycle evidence planning; no production authority or I/O.

Hashes prove consistency only. The caller must obtain records and observations
from a reviewed trusted executor under the original locks; this module cannot
authenticate those inputs. FINALIZATION_CANDIDATE is a review classification,
never permission to write a receipt, release a lease, or run a command.

Today's installer does not create this per-step schema. Its incomplete audits
therefore remain uncertain. In particular, missing leases are never recreated,
partial installations are never declared safe to dismantle, and a recorded
finalization intent is never replayed. No new record belongs in the current
installer's audit directory until its history validator is separately reviewed.
"""

import hashlib
import json
import re


RECONCILIATION_STEPS = (
    'verify_dormant_inventory', 'verify_original_lease', 'finalize_existing_receipt',
)
DEACTIVATION_STEPS = (
    'verify_exact_bridge_publication_and_original_receipts',
    'record_stop_and_unpublish_intent',
    'stop_and_disable_only_neo_wechat_unit',
    'unpublish_only_recorded_exact_bridge_nginx_include',
    'validate_nginx_configuration_before_reload',
    'reload_nginx_only_after_validation',
    'verify_bridge_inactive_and_exact_routes_unpublished',
    'verify_health_services_unchanged_and_owner_material_preserved',
    'record_confirmed_stop_and_unpublish_receipt',
)
_REMAINING_GATES = (
    'reviewed_canonical_executor_and_exact_commit_admission',
    'fresh_trusted_locked_observation',
    'authenticated_original_audit_and_lease_provenance',
    'reviewed_history_schema_and_finalization_protocol',
)
_RECEIPT_KEYS = frozenset((
    'state', 'publisher_sha', 'production_sha', 'operation_id', 'evidence_sha256',
    'runtime_sha256', 'proxy_gid', 'activated', 'nginx_included',
    'health_services_unchanged', 'secrets_created',
))
_RECORD_KEYS = frozenset((
    'version', 'operation_id', 'kind', 'dormant_receipt_sha256',
    'previous_record_sha256', 'sequence', 'step', 'phase', 'evidence_sha256',
))
_OBSERVATION_KEYS = frozenset((
    'version', 'install_operation_id', 'dormant_receipt_sha256', 'runtime_sha256',
    'publisher_sha', 'production_sha', 'bridge', 'nginx', 'health', 'config',
    'data', 'terminal', 'lease',
))


class LifecycleError(ValueError):
    """Constant error that cannot expose supplied evidence or owner material."""

    def __init__(self):
        super().__init__('lifecycle_evidence_rejected')


def _require(condition):
    if not condition:
        raise LifecycleError()


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _canonical(value):
    """Bounded plain JSON; no floats, arbitrary objects, or unbounded recursion."""
    budget = [512, 65536]

    def check(item, depth):
        budget[0] -= 1
        _require(depth <= 12 and budget[0] >= 0)
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            _require(-(2 ** 63) <= item < 2 ** 64)
            return
        if type(item) is str:
            _require(len(item) <= 4096)
            budget[1] -= len(item)
            _require(budget[1] >= 0)
            return
        if type(item) is list:
            _require(len(item) <= 128)
            for child in item:
                check(child, depth + 1)
            return
        _require(type(item) is dict and len(item) <= 64)
        for key, child in item.items():
            _require(type(key) is str)
            check(key, depth + 1)
            check(child, depth + 1)

    check(value, 0)
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    _require(len(encoded) <= 65536)
    return encoded


def digest(value):
    """Digest a bounded JSON value, not a signature or provenance assertion."""
    return hashlib.sha256(_canonical(value).encode('ascii')).hexdigest()


def validate_dormant_receipt(value):
    """Validate the existing dormant receipt schema and return a detached copy."""
    encoded = _canonical(value)
    _require(type(value) is dict and set(value) == _RECEIPT_KEYS)
    _require(value['state'] == 'INSTALLED_DORMANT')
    _require(all(value[key] is False for key in ('activated', 'nginx_included', 'secrets_created')))
    _require(value['health_services_unchanged'] is True)
    _require(type(value['proxy_gid']) is int and 0 < value['proxy_gid'] < 2 ** 32)
    _require(_hex(value['operation_id'], 32))
    _require(all(_hex(value[key], 40) for key in ('publisher_sha', 'production_sha')))
    _require(all(_hex(value[key], 64) for key in ('evidence_sha256', 'runtime_sha256')))
    return json.loads(encoded)


def validate_records(receipt, records):
    """Accept only a prefix of the original-operation reconciliation protocol.

    Record kinds for activation, provisioning, or later stop operations are not
    defined here. No path, command, secret, or caller-selected step is accepted.
    """
    original = validate_dormant_receipt(receipt)
    _require(type(records) is list and len(records) <= 6)
    receipt_hash = digest(original)
    previous = receipt_hash
    result = []
    for index, row in enumerate(records):
        encoded = _canonical(row)
        _require(type(row) is dict and set(row) == _RECORD_KEYS)
        _require(type(row['version']) is int and row['version'] == 1)
        _require(type(row['sequence']) is int and row['sequence'] == index + 1)
        _require(row['operation_id'] == original['operation_id'])
        _require(row['kind'] == 'finalize_install')
        _require(row['dormant_receipt_sha256'] == receipt_hash)
        _require(row['previous_record_sha256'] == previous)
        _require(row['step'] == RECONCILIATION_STEPS[index // 2])
        _require(row['phase'] == ('intent' if index % 2 == 0 else 'verified'))
        _require(row['evidence_sha256'] is None if index % 2 == 0 else _hex(row['evidence_sha256'], 64))
        detached = json.loads(encoded)
        result.append(detached)
        previous = digest(detached)
    return result


def _identity(value):
    return (type(value) is list and len(value) == 2
            and all(type(pair) is list and len(pair) == 2
                    and all(type(item) is int and 0 <= item < 2 ** 64 for item in pair)
                    for pair in value)
            and value[0] != value[1])


def _exact_inventory(receipt, observation):
    _canonical(observation)
    _require(type(observation) is dict and set(observation) == _OBSERVATION_KEYS)
    _require(type(observation['version']) is int and observation['version'] == 1)
    _require(observation['install_operation_id'] == receipt['operation_id'])
    _require(observation['dormant_receipt_sha256'] == digest(receipt))
    _require(all(observation[key] == receipt[key]
                 for key in ('publisher_sha', 'production_sha', 'runtime_sha256')))
    for key, expected in (('bridge', 'inactive_static'), ('nginx', 'unpublished'),
                          ('health', 'unchanged'), ('config', 'empty'),
                          ('data', 'empty'), ('terminal', 'absent')):
        _require(observation[key] == expected)
    lease = observation['lease']
    _require(type(lease) is dict and set(lease) == {
        'state', 'operation_id', 'recorded_identity', 'observed_identity'})
    _require(lease['state'] == 'original_present')
    _require(lease['operation_id'] == receipt['operation_id'])
    _require(_identity(lease['recorded_identity']) and _identity(lease['observed_identity']))
    _require(lease['recorded_identity'] == lease['observed_identity'])


def classify_recovery(receipt, records, observation):
    """Classify consistent input only; all malformed or partial input stays held."""
    classification = 'RETAIN_UNCERTAIN'
    try:
        original = validate_dormant_receipt(receipt)
        rows = validate_records(original, records)
        _exact_inventory(original, observation)
        observation_hash = digest(observation)
        # A finalization intent has an unknown outcome: never replay it. Missing
        # step evidence from today's installer also cannot be synthesized here.
        if len(rows) == 4 and all(rows[index]['evidence_sha256'] == observation_hash
                                  for index in (1, 3)):
            classification = 'FINALIZATION_CANDIDATE'
    except LifecycleError:
        pass
    return dict(classification=classification, authority='none', executable_actions=[],
                remaining_gates=list(_REMAINING_GATES))


def deactivation_plan(receipt):
    """Fixed advisory stop/unpublish plan; receipt does not prove live state."""
    validate_dormant_receipt(receipt)
    return dict(authority='none', executable_actions=[], steps=list(DEACTIVATION_STEPS),
                preserve=['keys', 'encrypted_data', 'audit', 'accounts', 'groups'],
                revocation='requires_separate_confirmed_receipt',
                remaining_gates=list(_REMAINING_GATES))
