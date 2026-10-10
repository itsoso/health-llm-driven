"""Bounded internal lifecycle orchestration against an injected trusted host.

There is NO production adapter, CLI, command runner, owner-input surface, boot
enablement or release-lease cleanup here. Hashes and observations are consistency
checks, not authentication. The caller's guard must establish canonical code,
exact release admission, original runtime operation lease, authenticated prior
receipts, directory/unit/config/proxy identities and permission to perform this
bounded operation. No WeChat message may supply that authority or these inputs.

Host protocol (all methods must raise on uncertain outcomes):
* guard(context), assert_fresh(context): read-only checks; return None on success.
* observe(context): bounded metadata snapshot per the history contract. It must
  verify exact unit bytes/drop-ins, credential METADATA, preserved Health process
  identities, and the precise proxy receipt/path/inode/content; no secret values.
  "recorded" is an authenticated exact match, never merely any present include.
* claim(context): exclusive durable runtime-lifecycle-v1 operation claim, rejecting
  existing or unresolved attempts even under another operation ID. It returns
  None only after durable ownership. It must not touch dormant/provision audits.
* append_record(row): append once with file/parent fsync, return None only when
  durable. Visible completion bytes alone are not confirmation after a failure.
* start_unit(name), stop_units(tuple), publish_proxy_include(receipt_digest),
  unpublish_proxy_include(receipt_digest), reload_proxy(receipt_digest): fixed
  bounded effects only, return None. stop_units makes one request for both units.
  Proxy methods compare exact current metadata immediately before their effect;
  they never remove or replace a foreign include or reload an unvalidated config.
* validate_proxy(), check_readiness(kind): read-only checks, return True only on
  confirmed success. Readiness must not create QR, tokens, messages or grants.

Every effect has a durable intent first and guarded fresh readback afterwards.
Any exception after claim begins is uncertain: retain the original lease and
evidence, never automatically retry, compensate, purge, or infer success from a
completed record. A separately reviewed history/dispatcher integration is still
required. Restart=on-failure does not establish host-reboot startup.
"""
import copy

from scripts.neo_wechat_lifecycle_history import (
    STEPS, make_record, validate_context, validate_observation,
)


SERVICE = 'neo-wechat.service'
SOCKET = 'neo-wechat.socket'


class RuntimeLifecycleError(RuntimeError):
    """Fixed errors contain no host output, paths or owner material."""


def _require(value):
    if not value:
        raise ValueError('lifecycle contract rejected')


def _state(observation):
    return dict(service=observation['units'][SERVICE]['state'],
                socket=observation['units'][SOCKET]['state'],
                entry=observation['proxy']['entry'], loaded=observation['proxy']['loaded'],
                validated=observation['proxy']['validated'],
                socket_path=observation['socket_path'], readiness=observation['readiness'])


def run(context, host):
    """Run a fresh bounded operation; never resume an existing record prefix."""
    claimed = False
    try:
        ctx = validate_context(context)
        activating = ctx['kind'] == 'activate'
        expected = dict(service='inactive' if activating else 'active',
            socket='inactive' if activating else 'active',
            entry='absent' if activating else 'recorded',
            loaded='absent' if activating else 'recorded', validated=not activating,
            socket_path='absent' if activating else 'recorded',
            readiness='unknown' if activating else 'ready')
        records = []

        def observe():
            _require(host.guard(copy.deepcopy(ctx)) is None)
            observed = validate_observation(ctx, host.observe(copy.deepcopy(ctx)))
            _require(_state(observed) == expected)
            return observed

        def record(phase, step, observation=None):
            row = make_record(ctx, records, phase, step, evidence=observation)
            _require(host.append_record(copy.deepcopy(row)) is None)
            records.append(row)
            return row

        observe()
        _require(host.assert_fresh(copy.deepcopy(ctx)) is None)
        observe()
        # A failed claim can still have persisted its namespace or lease.
        claimed = True
        _require(host.claim(copy.deepcopy(ctx)) is None)
        observe()
        proxy_receipt = ctx['expected_bindings']['proxy_receipt_sha256']

        for step in STEPS[ctx['kind']]:
            observe()
            record('intent', step)
            observe()  # Detect drift during intent persistence before acting.
            if step == 'verify_prerequisites':
                pass  # Fresh guarded metadata checks above are the whole step.
            elif step == 'start_socket':
                _require(host.start_unit(SOCKET) is None)
                expected.update(socket='active', socket_path='recorded')
            elif step == 'start_service':
                _require(host.start_unit(SERVICE) is None)
                expected['service'] = 'active'
            elif step == 'stop_units':
                _require(host.stop_units((SOCKET, SERVICE)) is None)
                expected.update(service='inactive', socket='inactive',
                                socket_path='absent', readiness='unknown')
            elif step == 'publish_proxy_include':
                _require(host.publish_proxy_include(proxy_receipt) is None)
                expected.update(entry='recorded', validated=False)
            elif step == 'unpublish_proxy_include':
                _require(host.unpublish_proxy_include(proxy_receipt) is None)
                expected.update(entry='absent', validated=False)
            elif step == 'validate_proxy':
                _require(host.validate_proxy() is True)
                expected['validated'] = True
            elif step == 'reload_proxy':
                _require(expected['validated'] is True)
                _require(host.reload_proxy(proxy_receipt) is None)
                expected['loaded'] = expected['entry']
            elif step == 'verify_final_state':
                _require(host.check_readiness(ctx['kind']) is True)
                expected['readiness'] = 'ready' if activating else 'stopped'
            else:
                raise ValueError('unknown lifecycle step')
            observed = observe()
            record('verified', step, observed)
            observe()

        final_observation = observe()
        terminal = record('completed', 'complete', final_observation)
        observe()  # Failure here leaves visible completion bytes but no success.
        return dict(state='ACTIVE_UNVERIFIED' if activating else 'STOPPED_UNPUBLISHED',
                    operation_id=ctx['operation_id'], terminal_record=copy.deepcopy(terminal),
                    acceptance_complete=False, remote_revocation_confirmed=False,
                    lease_released=False)
    except BaseException:
        raise RuntimeLifecycleError('runtime_lifecycle_uncertain' if claimed
                                    else 'runtime_lifecycle_precondition_failed') from None
