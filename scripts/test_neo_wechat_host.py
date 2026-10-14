"""OS-adapter tests use only temporary files and a recording command runner."""
import hashlib
import json
import os
import stat

import pytest

from scripts import neo_wechat_host as hostmod
from scripts.neo_wechat_lifecycle_history import digest


def test_public_admission_and_production_issuance_are_unavailable():
    with pytest.raises(hostmod.HostError, match='admission'):
        hostmod.Admission({})
    with pytest.raises(hostmod.HostError, match='admission'):
        hostmod.production_host()


def test_real_runner_rejects_unlisted_command_without_executing():
    runner = hostmod.BoundedRunner()
    with pytest.raises(hostmod.HostError):
        runner.run(('/bin/sh', '-c', 'synthetic-must-never-run'))


def test_recording_runner_rejects_unknown_commands():
    runner = hostmod.RecordingRunner(lambda _args: b'')
    with pytest.raises(hostmod.HostError):
        runner.run(('/usr/bin/systemctl', 'restart', 'health-backend.service'))
    assert runner.calls == []


def test_secure_files_reject_symlinks_hardlinks_and_writable_ancestors(tmp_path):
    root = tmp_path / 'root'
    root.mkdir(mode=0o700)
    (root / 'directory').mkdir(mode=0o755)
    fs = hostmod._Files(root, os.getuid())
    try:
        fs.write_once('directory/original', b'synthetic', 0o600)
        (root / 'directory/link').symlink_to('original')
        with pytest.raises(hostmod.HostError):
            fs.read('directory/link')
        os.link(root / 'directory/original', root / 'directory/hard')
        with pytest.raises(hostmod.HostError):
            fs.read('directory/original')
        os.chmod(root / 'directory', 0o777)
        with pytest.raises(hostmod.HostError):
            fs.read('directory/original')
    finally:
        fs.close()


def test_exclusive_write_and_exact_unlink_preserve_foreign_objects(tmp_path):
    fs = hostmod._Files(tmp_path, os.getuid())
    try:
        owned = fs.write_once('owned', b'synthetic', 0o600)
        with pytest.raises(hostmod.HostError):
            fs.write_once('owned', b'replace', 0o600)
        (tmp_path / 'owned').rename(tmp_path / 'original')
        (tmp_path / 'owned').write_bytes(b'synthetic')
        os.chmod(tmp_path / 'owned', 0o600)
        with pytest.raises(hostmod.HostError):
            fs.unlink_exact('owned', owned)
        assert (tmp_path / 'owned').exists() and (tmp_path / 'original').exists()
    finally:
        fs.close()


def fixture(tmp_path, kind='activate'):
    from scripts.test_neo_wechat_runtime_lifecycle import context
    ctx = context(kind)
    root = tmp_path / 'synthetic-root'
    root.mkdir(mode=0o700)
    for path in ('etc/systemd/system', 'etc/neo-wechat', 'etc/nginx/neo-wechat',
                 'etc/nginx/sites-available', 'var/lib/neo-wechat',
                 'var/lib/reva-release/neo-wechat-lifecycle', 'run/neo-wechat',
                 'opt/neo-wechat/releases/' + '2' * 40):
        (root / path).mkdir(parents=True, exist_ok=True)
        os.chmod(root / path, 0o755)
    os.chmod(root / 'etc/neo-wechat', 0o710)
    os.chmod(root / 'var/lib/neo-wechat', 0o700)
    os.chmod(root / 'var/lib/reva-release/neo-wechat-lifecycle', 0o700)
    uid, gid = os.getuid(), os.getgid()
    files = {
        'etc/systemd/system/neo-wechat.service': (b'synthetic-service', 0o644),
        'etc/systemd/system/neo-wechat.socket': (b'synthetic-socket', 0o644),
        'etc/neo-wechat/config.json': (b'{"origin":"https://health.executor.life"}', 0o640),
        'etc/neo-wechat/encryption_key': (b'never-open-this-synthetic-key', 0o600),
        'etc/neo-wechat/admin_password_hash': (b'never-open-this-synthetic-hash', 0o600),
        'etc/neo-wechat/slack_webhook': (b'never-open-this-synthetic-webhook', 0o600),
        'etc/nginx/sites-available/health.executor.life': (b'server {\ninclude /etc/nginx/neo-wechat/*.conf;\n}\n', 0o644),
        'etc/nginx/nginx.conf': (b'synthetic-main-nginx', 0o644),
        'opt/neo-wechat/releases/' + '2' * 40 + '/application.py': (b'synthetic-runtime', 0o644),
        'etc/passwd': (f'neo-wechat:x:{uid}:{gid}::/nonexistent:/usr/sbin/nologin\nnginx:x:{uid}:{gid}::/nonexistent:/usr/sbin/nologin\n'.encode(), 0o644),
        'etc/group': (f'neo-wechat:x:{gid}:\nneo-wechat-proxy:x:{gid}:neo-wechat,nginx\n'.encode(), 0o644),
    }
    for name, (raw, mode) in files.items():
        path = root / name
        path.write_bytes(raw)
        os.chmod(path, mode)
    runtime_inventory = {'application.py': hashlib.sha256(b'synthetic-runtime').hexdigest()}
    ctx['runtime_sha256'] = ctx['expected_bindings']['runtime_sha256'] = digest(runtime_inventory)
    health = {name: {'ActiveState': 'active', 'SubState': 'running', 'MainPID': '10',
        'NRestarts': '0', 'ActiveEnterTimestampMonotonic': '100', 'FragmentPath': '/synthetic',
        'DropInPaths': ''} for name in hostmod.HEALTH_UNITS}
    state = {'active': kind == 'stop', 'socket': kind == 'stop', 'loaded': kind == 'stop'}
    def responder(args):
        if args[:2] == ('/usr/bin/systemctl', 'show'):
            unit = args[2]
            if unit in health:
                return '\n'.join(f'{key}={value}' for key, value in health[unit].items()).encode()
            active = state['socket' if unit.endswith('.socket') else 'active']
            return ('LoadState=loaded\nActiveState=' + ('active' if active else 'inactive')
                + '\nUnitFileState=static\nDropInPaths=\nFragmentPath=/etc/systemd/system/' + unit).encode()
        if args[:2] == ('/usr/bin/systemctl', 'start'):
            state['socket' if args[2].endswith('.socket') else 'active'] = True
        if args[:2] == ('/usr/bin/systemctl', 'stop'):
            state['active'] = state['socket'] = False
        if args[:3] == ('/usr/bin/systemctl', 'reload', 'nginx.service'):
            state['loaded'] = (root / 'etc/nginx/neo-wechat/locations.conf').exists()
        if args[0] == '/usr/bin/curl':
            if state['loaded']:
                return b'{"resource":"https://health.executor.life/neo-wechat/mcp"}\n200'
            return b'not-found\n404'
        return b''
    runner = hostmod.RecordingRunner(responder)
    manifest = dict(runtime_revision='2' * 40, runtime_inventory=runtime_inventory,
        bridge_uid=uid, bridge_gid=gid, proxy_gid=gid, nginx_user='nginx',
        proxy_fragment=b'synthetic-reviewed-locations', proxy_ownership=None,
        dormant_receipt={'synthetic': 'dormant'}, provision_receipt={'synthetic': 'provision'})
    if kind == 'stop':
        (root / hostmod.FRAGMENT).write_bytes(manifest['proxy_fragment'])
        os.chmod(root / hostmod.FRAGMENT, 0o644)
    fs = hostmod._Files(root, uid)
    try:
        if kind == 'stop':
            manifest['proxy_ownership'] = fs.metadata(hostmod.FRAGMENT)
        for tag, path in hostmod.PUBLIC_BINDINGS.items():
            ctx['expected_bindings'][tag] = hashlib.sha256(fs.read(path)).hexdigest()
        for tag, receipt in (('dormant_receipt_sha256', manifest['dormant_receipt']),
                             ('provisioning_receipt_sha256', manifest['provision_receipt'])):
            ctx[tag] = ctx['expected_bindings'][tag] = digest(receipt)
        manifest['config_identity'] = fs.metadata('etc/neo-wechat/config.json')
        manifest['secret_identities'] = {name: fs.metadata('etc/neo-wechat/' + name) for name in hostmod.SECRETS}
        manifest['proxy_receipt'] = dict(slot_identity=fs.metadata(hostmod.SLOT),
            slot_sha256=hashlib.sha256(fs.read(hostmod.SLOT)).hexdigest(),
            main_sha256=hashlib.sha256(fs.read('etc/nginx/nginx.conf')).hexdigest(),
            fragment_sha256=hashlib.sha256(manifest['proxy_fragment']).hexdigest())
        ctx['expected_bindings']['proxy_receipt_sha256'] = digest(manifest['proxy_receipt'])
        ctx['expected_preserved'] = hostmod._preserved_snapshot(fs, runner, manifest)
    finally:
        fs.close()
    admission = hostmod._synthetic_admission_for_tests(root=root, context=ctx, manifest=manifest,
        guard=lambda: None, runner=runner)
    host = hostmod.Host(admission)
    # The sandbox denies AF_UNIX bind. Only socket metadata is synthetic; all
    # journal, config, inventory and proxy filesystem operations are real.
    original_metadata = host.fs.metadata
    def metadata(name, **kwargs):
        if name == 'run/neo-wechat/bridge.sock':
            return dict(mode=stat.S_IFSOCK | 0o660, uid=uid, gid=gid) if state['socket'] else None
        return original_metadata(name, **kwargs)
    host.fs.metadata = metadata
    return root, ctx, host, runner, state


def test_adapter_claim_and_journal_use_real_exclusive_private_files(tmp_path):
    root, ctx, host, runner, _state = fixture(tmp_path)
    try:
        host.assert_fresh(ctx)
        host.claim(ctx)
        from scripts.neo_wechat_lifecycle_history import make_record
        row = make_record(ctx, [], 'intent', 'verify_prerequisites')
        host.append_record(row)
        op = root / hostmod.LIFECYCLE / 'runtime-lifecycle-v1' / ctx['operation_id']
        assert set(p.name for p in op.iterdir()) == {'context.json', 'original-dormant.json', '001-intent.json'}
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in op.iterdir())
        with pytest.raises(hostmod.HostError):
            host.claim(ctx)
    finally:
        host.close()


def test_proxy_requires_existing_exact_slot_and_foreign_entry_never_removed(tmp_path):
    root, ctx, host, runner, _state = fixture(tmp_path)
    try:
        host.claim(ctx)
        host._pending = 'publish_proxy_include'
        host.publish_proxy_include(ctx['expected_bindings']['proxy_receipt_sha256'])
        assert (root / hostmod.FRAGMENT).read_bytes() == b'synthetic-reviewed-locations'
        owned = root / hostmod.FRAGMENT
        owned.rename(owned.with_name('held'))
        owned.write_bytes(b'synthetic-reviewed-locations')
        host._pending = 'unpublish_proxy_include'
        with pytest.raises(hostmod.HostError):
            host.unpublish_proxy_include(ctx['expected_bindings']['proxy_receipt_sha256'])
        assert owned.exists()
    finally:
        host.close()


def test_no_secret_contents_are_read_by_guard(tmp_path, monkeypatch):
    root, ctx, host, runner, _state = fixture(tmp_path)
    original = host.fs.read
    def guarded(name, **kwargs):
        assert name not in {'etc/neo-wechat/' + value for value in hostmod.SECRETS}
        return original(name, **kwargs)
    monkeypatch.setattr(host.fs, 'read', guarded)
    try:
        host.guard(ctx)
    finally:
        host.close()


@pytest.mark.parametrize('kind,terminal', [('activate', 'ACTIVE_UNVERIFIED'), ('stop', 'STOPPED_UNPUBLISHED')])
def test_full_runtime_real_files_recorded_commands(tmp_path, kind, terminal):
    from scripts.neo_wechat_runtime_lifecycle import run
    root, ctx, host, runner, state = fixture(tmp_path, kind)
    try:
        result = run(ctx, host)
        assert result['state'] == terminal and result['lease_released'] is False
        assert host.records[-1]['phase'] == 'completed'
        assert bool((root / hostmod.FRAGMENT).exists()) == (kind == 'activate')
        assert state['active'] == state['socket'] == (kind == 'activate')
        assert all(call[:2] != ('/usr/bin/systemctl', 'enable') for call in runner.calls)
    finally:
        host.close()


@pytest.mark.parametrize('extra', ['extra.py', '__pycache__', 'link', 'fifo'])
def test_runtime_exact_inventory_blocks_extra_nodes(tmp_path, extra):
    root, ctx, host, runner, state = fixture(tmp_path)
    path = root / 'opt/neo-wechat/releases' / ('2'*40) / extra
    if extra == '__pycache__':
        path.mkdir()
    elif extra == 'link':
        path.symlink_to('application.py')
    elif extra == 'fifo':
        os.mkfifo(path)
    else:
        path.write_bytes(b'extra')
    try:
        with pytest.raises(hostmod.HostError):
            host.guard(ctx)
        assert not (root / hostmod.LIFECYCLE / 'runtime-lifecycle-v1').exists()
    finally:
        host.close()


def test_fifo_read_fails_without_blocking(tmp_path):
    os.mkfifo(tmp_path / 'fifo')
    fs = hostmod._Files(tmp_path, os.getuid())
    try:
        with pytest.raises(hostmod.HostError):
            fs.read('fifo')
    finally:
        fs.close()


def test_changed_durable_intent_stops_following_effect(tmp_path):
    from scripts.neo_wechat_lifecycle_history import make_record
    root, ctx, host, runner, state = fixture(tmp_path)
    try:
        host.claim(ctx)
        host.append_record(make_record(ctx, [], 'intent', 'verify_prerequisites'))
        (root / host.op / '001-intent.json').write_bytes(b'changed')
        with pytest.raises(hostmod.HostError):
            host.guard(ctx)
        assert not state['active']
    finally:
        host.close()


@pytest.mark.parametrize('kind,effect', [('activate', 'start'), ('stop', 'stop'), ('activate', 'reload'), ('stop', 'reload')])
def test_uncertain_recorded_command_preserves_history_no_replay(tmp_path, kind, effect):
    from scripts.neo_wechat_runtime_lifecycle import run, RuntimeLifecycleError
    root, ctx, host, runner, state = fixture(tmp_path, kind)
    original = runner.responder
    failed = []
    def responder(args):
        result = original(args)
        if args[:2] == ('/usr/bin/systemctl', effect):
            failed.append(args)
            raise RuntimeError('synthetic private output')
        return result
    runner.responder = responder
    try:
        with pytest.raises(RuntimeLifecycleError, match='runtime_lifecycle_uncertain'):
            run(ctx, host)
        assert len(failed) == 1
        assert host.records[-1]['phase'] == 'intent'
        with pytest.raises(RuntimeLifecycleError):
            run(ctx, host)
        assert len(failed) == 1
        assert (root / host.op / 'context.json').exists()
        assert (root / 'etc/neo-wechat/encryption_key').exists()
    finally:
        host.close()


def test_missing_runtime_parent_is_absent_but_symlink_parent_rejected(tmp_path):
    (tmp_path / 'run').mkdir()
    fs = hostmod._Files(tmp_path, os.getuid())
    try:
        assert fs.metadata('run/neo-wechat/bridge.sock', absent=True) is None
        (tmp_path / 'run/neo-wechat').symlink_to(tmp_path / 'other')
        with pytest.raises(hostmod.HostError):
            fs.metadata('run/neo-wechat/bridge.sock', absent=True)
    finally:
        fs.close()


def test_realistic_stop_502_retains_uncertainty_and_never_unpublishes(tmp_path):
    from scripts.neo_wechat_runtime_lifecycle import run, RuntimeLifecycleError
    root, ctx, host, runner, state = fixture(tmp_path, 'stop')
    original = runner.responder
    def responder(args):
        if args[0] == '/usr/bin/curl' and state['loaded'] and not state['active']:
            return b'synthetic nginx bad gateway\n502'
        return original(args)
    runner.responder = responder
    try:
        with pytest.raises(RuntimeLifecycleError, match='runtime_lifecycle_uncertain'):
            run(ctx, host)
        assert not state['active'] and not state['socket']
        assert (root / hostmod.FRAGMENT).exists()
        assert host.records[-1]['step'] == 'stop_units' and host.records[-1]['phase'] == 'intent'
        assert not any(call[:2] == ('/usr/bin/systemctl', 'reload') for call in runner.calls)
        with pytest.raises(RuntimeLifecycleError):
            run(ctx, host)
        assert sum(call[:2] == ('/usr/bin/systemctl', 'stop') for call in runner.calls) == 1
    finally:
        host.close()


@pytest.mark.parametrize('kind', ['activate', 'stop'])
@pytest.mark.parametrize('point', [1, 2, 3, 4])
def test_namespace_fsync_uncertainty_retains_created_evidence(tmp_path, monkeypatch, kind, point):
    from scripts.neo_wechat_runtime_lifecycle import run, RuntimeLifecycleError
    root, ctx, host, runner, state = fixture(tmp_path, kind)
    original = os.fsync
    count = []
    def fsync(fd):
        count.append(fd)
        original(fd)
        if len(count) == point:
            raise OSError('synthetic private host text')
    monkeypatch.setattr(os, 'fsync', fsync)
    try:
        with pytest.raises(RuntimeLifecycleError, match='runtime_lifecycle_uncertain'):
            run(ctx, host)
        assert (root / hostmod.LIFECYCLE / 'runtime-lifecycle-v1').exists()
        assert not any(call[1] in ('start', 'stop', 'reload') for call in runner.calls if len(call) > 1)
        with pytest.raises(RuntimeLifecycleError):
            run(ctx, host)
    finally:
        host.close()


@pytest.mark.parametrize('kind,sequence', [(kind, sequence) for kind, limit in [('activate', 15), ('stop', 13)] for sequence in range(1, limit+1)])
def test_every_durable_record_unknown_ack_blocks_replay(tmp_path, kind, sequence):
    from scripts.neo_wechat_runtime_lifecycle import run, RuntimeLifecycleError
    root, ctx, host, runner, state = fixture(tmp_path, kind)
    original = host.fs.write_once
    def write_once(path, raw, mode=0o600):
        result = original(path, raw, mode)
        if path.rsplit('/', 1)[-1].startswith(f'{sequence:03d}-') and not path.endswith('-evidence.json'):
            raise hostmod.HostError('synthetic durability acknowledgment unknown')
        return result
    host.fs.write_once = write_once
    try:
        with pytest.raises(RuntimeLifecycleError, match='runtime_lifecycle_uncertain'):
            run(ctx, host)
        records = list((root / host.op).glob(f'{sequence:03d}-*.json'))
        assert records
        effect_count = len([call for call in runner.calls if len(call)>1 and call[1] in ('start', 'stop', 'reload')])
        with pytest.raises(RuntimeLifecycleError):
            run(ctx, host)
        assert effect_count == len([call for call in runner.calls if len(call)>1 and call[1] in ('start', 'stop', 'reload')])
    finally:
        host.close()


def test_disappeared_owned_include_cannot_be_reported_as_recorded(tmp_path):
    root, ctx, host, runner, state = fixture(tmp_path, 'stop')
    (root / hostmod.FRAGMENT).unlink()
    try:
        with pytest.raises(hostmod.HostError):
            host.observe(ctx)
        assert not (root / hostmod.LIFECYCLE / 'runtime-lifecycle-v1').exists()
    finally:
        host.close()


def test_admission_guard_exception_has_no_private_output(tmp_path):
    root, ctx, host, runner, state = fixture(tmp_path)
    def guard():
        raise RuntimeError('synthetic private output')
    try:
        with pytest.raises(hostmod.HostError, match='^neo_wechat_admission_rejected$'):
            hostmod._synthetic_admission_for_tests(root=root, context=ctx,
                manifest=host.manifest, guard=guard, runner=runner)
    finally:
        host.close()
