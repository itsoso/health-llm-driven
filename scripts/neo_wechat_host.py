"""Concrete filesystem/command adapter with production issuance DISABLED.

No CLI or supported production-admission issuer exists. A private Python token is
not evidence of canonical execution, G4, current-main CI, or durable closure.
Only an explicit temporary-directory synthetic factory can create an Admission;
it requires a RecordingRunner and cannot select the fixed production filesystem.
The OS effects below are real implementations exercised against temporary files.
Real stop remains BLOCKED at the stopped-upstream 502 intermediate observation:
HTTP response checks cannot prove the currently loaded nginx generation. The
current adapter deliberately fails closed there; canonical loaded-topology proof
is a required integration prerequisite, not inferred from a cached 200 response.

Future production integration must mint a separately reviewed authenticated
capability, pin full nginx topology and prior ownership, and establish closure
authority. The current installed-history gate blocks ALL lifecycle histories.
No host method emits final-guard files, releases leases, enables boot, reads
credential contents, contacts providers, or infers authority from a completed file.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import tempfile
import time

from scripts.neo_wechat_lifecycle_history import digest, validate_context, validate_history, validate_observation


LIFECYCLE = 'var/lib/reva-release/neo-wechat-lifecycle'
SLOT = 'etc/nginx/sites-available/health.executor.life'
FRAGMENT = 'etc/nginx/neo-wechat/locations.conf'
ORIGIN = 'https://health.executor.life'
SLOT_LINE = b'include /etc/nginx/neo-wechat/*.conf;'
UNITS = ('neo-wechat.service', 'neo-wechat.socket')
HEALTH_UNITS = ('health-backend.service', 'health-backend.socket', 'celery-worker.service', 'celery-beat.service')
SECRETS = ('encryption_key', 'admin_password_hash', 'slack_webhook')
PUBLIC_BINDINGS = {'service_unit_sha256': 'etc/systemd/system/neo-wechat.service',
    'socket_unit_sha256': 'etc/systemd/system/neo-wechat.socket', 'config_sha256': 'etc/neo-wechat/config.json'}
HEALTH_PROPERTIES = 'ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestampMonotonic,FragmentPath,DropInPaths'
UNIT_PROPERTIES = 'LoadState,ActiveState,UnitFileState,FragmentPath,DropInPaths'
META = ('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'ctime_ns')
_SEAL = object()
_ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}


class HostError(RuntimeError):
    pass


class _AbsentPath(HostError):
    pass


def _require(condition):
    if not condition:
        raise HostError('neo_wechat_host_rejected')


def _metadata(info):
    return {key: getattr(info, 'st_' + key) for key in META}


def _stable(info):
    return {key: info[key] for key in ('dev', 'ino', 'uid', 'gid', 'mode')}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _http_command():
    return ('/usr/bin/curl', '--silent', '--show-error', '--noproxy', '*',
        '--connect-timeout', '2', '--max-time', '5', '--max-filesize', '65536',
        '--resolve', 'health.executor.life:443:127.0.0.1', '--write-out', '\n%{http_code}',
        ORIGIN + '/.well-known/oauth-protected-resource/neo-wechat/mcp')


def _allowed(args):
    allowed = {('/usr/sbin/nginx', '-t'), ('/usr/bin/systemctl', 'reload', 'nginx.service'),
        ('/usr/bin/systemctl', 'stop', 'neo-wechat.socket', 'neo-wechat.service'), _http_command()}
    allowed |= {('/usr/bin/systemctl', 'start', unit) for unit in UNITS}
    allowed |= {('/usr/bin/systemctl', 'show', unit, '--property=' + UNIT_PROPERTIES, '--all') for unit in UNITS}
    allowed |= {('/usr/bin/systemctl', 'show', unit, '--property=' + HEALTH_PROPERTIES, '--all') for unit in HEALTH_UNITS}
    _require(type(args) is tuple and args in allowed)


class BoundedRunner:
    """Exact allowlist, clean environment, bounded output, and a hard deadline."""
    def run(self, args):
        _allowed(args)
        process = None
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=dict(_ENV), close_fds=True, start_new_session=True)
            output = bytearray()
            total = 0
            deadline = time.monotonic() + 20
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    _require(time.monotonic() < deadline)
                    for event, _mask in selector.select(min(0.1, max(0, deadline-time.monotonic()))):
                        raw = os.read(event.fileobj.fileno(), 8192)
                        if not raw:
                            selector.unregister(event.fileobj)
                            continue
                        total += len(raw)
                        _require(total <= 131072)
                        if event.data:
                            output.extend(raw)
                _require(process.wait(timeout=max(0.01, deadline-time.monotonic())) == 0)
            return bytes(output)
        except BaseException:
            raise HostError('neo_wechat_command_uncertain') from None
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    process.stdout.close()
                    process.stderr.close()
                except BaseException:
                    raise HostError('neo_wechat_command_cleanup_uncertain') from None


class RecordingRunner:
    """Explicit synthetic runner: it never calls Popen or an OS command."""
    def __init__(self, responder):
        self.responder, self.calls = responder, []

    def run(self, args):
        _allowed(args)
        self.calls.append(args)
        value = self.responder(args)
        _require(type(value) is bytes and len(value) <= 131072)
        return value


class _Files:
    """Descriptor-relative, no-follow access beneath one pinned owned directory."""
    def __init__(self, root, uid=0):
        self.uid = uid
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.identity = _stable(_metadata(os.fstat(self.fd)))
        self._directory(self.fd)

    def close(self):
        os.close(self.fd)

    def _directory(self, fd):
        info = os.fstat(fd)
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.uid and not info.st_mode & 0o022)

    def _parent(self, name):
        _require(type(name) is str and name and not name.startswith('/'))
        parts = name.split('/')
        _require(all(part not in ('', '.', '..') for part in parts))
        _require(_stable(_metadata(os.fstat(self.fd))) == self.identity)
        fd = os.dup(self.fd)
        try:
            self._directory(fd)
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = child
                self._directory(fd)
            return fd, parts[-1]
        except FileNotFoundError:
            os.close(fd)
            if name == 'run/neo-wechat/bridge.sock' and part == 'neo-wechat':
                raise _AbsentPath('neo_wechat_path_absent') from None
            raise HostError('neo_wechat_path_rejected') from None
        except BaseException:
            os.close(fd)
            raise HostError('neo_wechat_path_rejected') from None

    def metadata(self, name, *, absent=False):
        try:
            fd, leaf = self._parent(name)
        except _AbsentPath:
            if absent:
                return None
            raise HostError('neo_wechat_path_rejected') from None
        try:
            try:
                value = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if absent:
                    return None
                raise
            return _metadata(value)
        except BaseException:
            raise HostError('neo_wechat_path_rejected') from None
        finally:
            os.close(fd)

    def read(self, name, *, limit=2*1024*1024):
        parent, leaf = self._parent(name)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == self.uid and before.st_nlink == 1
                     and not before.st_mode & 0o022 and before.st_size <= limit)
            raw = bytearray()
            while len(raw) <= limit:
                block = os.read(fd, min(65536, limit+1-len(raw)))
                if not block:
                    break
                raw.extend(block)
            _require(len(raw) <= limit and _metadata(os.fstat(fd)) == _metadata(before)
                     and _metadata(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) == _metadata(before))
            return bytes(raw)
        except BaseException:
            raise HostError('neo_wechat_read_rejected') from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def entries(self, name):
        parent, leaf = self._parent(name)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            self._directory(fd)
            values = set()
            with os.scandir(fd) as entries:
                for entry in entries:
                    _require(len(values) < 10000)
                    values.add(entry.name)
            return values
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def exact_inventory(self, base, expected):
        """Reject extra code, directories, caches, symlinks and special nodes."""
        _require(type(expected) is dict and 0 < len(expected) <= 10000)
        directories = {''}
        for name in expected:
            _require(type(name) is str and len(name) <= 1024)
            parts = name.split('/')
            _require(len(parts) <= 32 and all(p not in ('', '.', '..', '__pycache__') for p in parts))
            directories.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        seen, pending, count = {}, [''], 0
        while pending:
            relative = pending.pop()
            for leaf in self.entries(base + ('/' + relative if relative else '')):
                count += 1
                _require(count <= 20000)
                name = relative + '/' + leaf if relative else leaf
                path = base + '/' + name
                meta = self.metadata(path)
                _require(meta['uid'] == self.uid and not meta['mode'] & 0o022)
                if stat.S_ISDIR(meta['mode']):
                    _require(name in directories)
                    pending.append(name)
                else:
                    _require(name in expected and stat.S_ISREG(meta['mode']) and meta['nlink'] == 1)
                    seen[name] = _sha(self.read(path, limit=64*1024*1024))
        _require(seen == expected)

    def mkdir(self, name):
        parent, leaf = self._parent(name)
        child = None
        try:
            os.mkdir(leaf, 0o700, dir_fd=parent)
            child = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.fchmod(child, 0o700)
            self._directory(child)
            os.fsync(child)
            os.fsync(parent)
        except BaseException:
            raise HostError('neo_wechat_write_uncertain') from None
        finally:
            if child is not None:
                os.close(child)
            os.close(parent)

    def write_once(self, name, raw, mode=0o600):
        _require(type(raw) is bytes and len(raw) <= 131072 and mode in (0o600, 0o644))
        parent, leaf = self._parent(name)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
            os.fchmod(fd, mode)
            position = 0
            while position < len(raw):
                amount = os.write(fd, raw[position:])
                _require(amount > 0)
                position += amount
            os.lseek(fd, 0, os.SEEK_SET)
            _require(os.read(fd, len(raw)+1) == raw)
            info = os.fstat(fd)
            _require(info.st_uid == self.uid and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == mode)
            _require(os.stat(leaf, dir_fd=parent, follow_symlinks=False) == info)
            os.fsync(fd)
            os.fsync(parent)
            return _metadata(info)
        except BaseException:
            raise HostError('neo_wechat_write_uncertain') from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def unlink_exact(self, name, expected):
        parent, leaf = self._parent(name)
        try:
            actual = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            _require(_metadata(actual) == expected and stat.S_ISREG(actual.st_mode) and actual.st_nlink == 1)
            os.unlink(leaf, dir_fd=parent)
            os.fsync(parent)
        except BaseException:
            raise HostError('neo_wechat_unlink_uncertain') from None
        finally:
            os.close(parent)


class Admission:
    __slots__ = ('_context', '_manifest', '_root', '_root_identity', '_guard', '_runner', '_uid')

    def __init__(self, *args, **kwargs):
        raise HostError('neo_wechat_admission_unavailable')

    def __setattr__(self, name, value):
        raise HostError('neo_wechat_admission_immutable')

    @property
    def context(self):
        return copy.deepcopy(self._context)

    def recheck(self):
        try:
            _require(type(self._runner) is RecordingRunner and self._root != Path('/'))
            _require(_stable(_metadata(self._root.lstat())) == self._root_identity)
            _require(self._guard() is None)
        except BaseException:
            raise HostError('neo_wechat_admission_rejected') from None


def production_host(*_args, **_kwargs):
    raise HostError('neo_wechat_admission_unavailable')


def _synthetic_admission_for_tests(*, root, context, manifest, guard, runner):
    path = Path(root).resolve(strict=True)
    temporary = Path(tempfile.gettempdir()).resolve()
    _require(path != temporary and path.is_relative_to(temporary) and type(runner) is RecordingRunner)
    _require(path.is_dir() and path.lstat().st_uid == os.geteuid() and callable(guard))
    value = object.__new__(Admission)
    for key, item in dict(_context=validate_context(context), _manifest=copy.deepcopy(manifest),
        _root=path, _root_identity=_stable(_metadata(path.lstat())), _guard=guard, _runner=runner,
        _uid=os.geteuid()).items():
        object.__setattr__(value, key, item)
    value.recheck()
    return value


def _properties(raw):
    result = {}
    for line in raw.decode('ascii').splitlines():
        key, value = line.split('=', 1)
        _require(key not in result)
        result[key] = value
    return result


def _preserved_snapshot(fs, runner, manifest):
    health = {}
    for unit in HEALTH_UNITS:
        row = _properties(runner.run(('/usr/bin/systemctl', 'show', unit, '--property='+HEALTH_PROPERTIES, '--all')))
        _require(set(row) == set(HEALTH_PROPERTIES.split(',')) and row['ActiveState'] == 'active')
        health[unit] = row
    keys = {name: fs.metadata('etc/neo-wechat/'+name) for name in SECRETS}
    for row in keys.values():
        _require(row['uid'] == fs.uid and row['nlink'] == 1 and row['mode'] == stat.S_IFREG | 0o600)
    account_rows = []
    for line in fs.read('etc/passwd').decode().splitlines():
        parts = line.split(':')
        if parts[0] in ('neo-wechat', manifest['nginx_user']):
            _require(len(parts) == 7)
            account_rows.append([parts[0], *parts[2:]])
    groups = []
    for line in fs.read('etc/group').decode().splitlines():
        parts = line.split(':')
        if parts[0] in ('neo-wechat', 'neo-wechat-proxy'):
            _require(len(parts) == 4)
            groups.append([parts[0], parts[2], parts[3]])
    _require(len(account_rows) == 2 and len(groups) == 2)
    return dict(health_services_sha256=digest(health), keys_identity_sha256=digest(keys),
        data_directory_identity_sha256=digest(_stable(fs.metadata('var/lib/neo-wechat'))),
        audit_root_identity_sha256=digest(_stable(fs.metadata(LIFECYCLE))),
        accounts_groups_sha256=digest({'accounts': account_rows, 'groups': groups}))


class Host:
    def __init__(self, admission):
        _require(type(admission) is Admission)
        admission.recheck()
        self.admission = admission
        self.ctx, self.manifest = admission.context, copy.deepcopy(admission._manifest)
        self.fs = _Files(admission._root, admission._uid)
        self.runner = admission._runner
        self.records, self._pending, self._observed = [], None, None
        self._journal = {}
        self._claimed, self._validated, self._ready = False, None, 'unknown'
        self._proxy_owned = copy.deepcopy(self.manifest.get('proxy_ownership'))
        self.op = LIFECYCLE + '/runtime-lifecycle-v1/' + self.ctx['operation_id']

    def close(self):
        self.fs.close()

    def _proxy_signature(self):
        receipt = self.manifest['proxy_receipt']
        _require(digest(receipt) == self.ctx['expected_bindings']['proxy_receipt_sha256'])
        _require(self.fs.metadata(SLOT) == receipt['slot_identity'] and _sha(self.fs.read(SLOT)) == receipt['slot_sha256'])
        _require(sum(line.strip() == SLOT_LINE for line in self.fs.read(SLOT).splitlines()) == 1)
        _require(_sha(self.fs.read('etc/nginx/nginx.conf')) == receipt['main_sha256'])
        _require(self.fs.entries('etc/nginx/neo-wechat') <= {'locations.conf'})
        meta = self.fs.metadata(FRAGMENT, absent=True)
        _require((meta is None) == (self._proxy_owned is None))
        if meta is not None:
            _require(self._proxy_owned is not None and meta == self._proxy_owned)
            _require(meta['mode'] == stat.S_IFREG | 0o644 and meta['uid'] == self.fs.uid and meta['nlink'] == 1)
            _require(_sha(self.fs.read(FRAGMENT)) == receipt['fragment_sha256'])
        return digest({'slot': receipt, 'entry': meta})

    def guard(self, context):
        try:
            _require(validate_context(context) == self.ctx)
            self.admission.recheck()
            for tag, path in PUBLIC_BINDINGS.items():
                _require(_sha(self.fs.read(path)) == self.ctx['expected_bindings'][tag])
            _require(self.fs.metadata('etc/neo-wechat/config.json') == self.manifest['config_identity'])
            for name in SECRETS:
                _require(self.fs.metadata('etc/neo-wechat/'+name) == self.manifest['secret_identities'][name])
            _require(_preserved_snapshot(self.fs, self.runner, self.manifest) == self.ctx['expected_preserved'])
            inventory = self.manifest['runtime_inventory']
            _require(type(inventory) is dict and 0 < len(inventory) <= 10000)
            revision = self.manifest['runtime_revision']
            _require(type(revision) is str and len(revision) == 40 and all(c in '0123456789abcdef' for c in revision))
            self.fs.exact_inventory('opt/neo-wechat/releases/'+revision, inventory)
            _require(digest(inventory) == self.ctx['runtime_sha256'])
            _require(digest(self.manifest['dormant_receipt']) == self.ctx['dormant_receipt_sha256'])
            _require(digest(self.manifest['provision_receipt']) == self.ctx['provisioning_receipt_sha256'])
            self._proxy_signature()
            if self._claimed and self._journal:
                _require(self.fs.entries(self.op) == set(self._journal))
                for name, (identity, expected) in self._journal.items():
                    _require(self.fs.metadata(self.op+'/'+name) == identity
                             and _sha(self.fs.read(self.op+'/'+name)) == expected)
        except BaseException:
            raise HostError('neo_wechat_guard_rejected') from None

    def assert_fresh(self, context):
        self.guard(context)
        _require(not self._claimed and self.fs.metadata(LIFECYCLE+'/runtime-lifecycle-v1', absent=True) is None)

    def claim(self, context):
        self.assert_fresh(context)
        self._claimed = True
        self.fs.mkdir(LIFECYCLE+'/runtime-lifecycle-v1')
        self.fs.mkdir(self.op)
        self._json(self.op+'/context.json', self.ctx)
        self._json(self.op+'/original-dormant.json', self.manifest['dormant_receipt'])

    def _json(self, path, value):
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()
        identity = self.fs.write_once(path, raw)
        self._journal[path.rsplit('/', 1)[1]] = (identity, _sha(raw))

    def append_record(self, row):
        self.guard(self.ctx)
        _require(self._claimed)
        rows = validate_history(self.ctx, self.records+[row])
        seq = row['sequence']
        if row['phase'] == 'verified':
            observed = validate_observation(self.ctx, self._observed)
            _require(digest(observed) == row['evidence_sha256'])
            self._json(self.op+f'/{seq:03d}-evidence.json', observed)
        self._json(self.op+f'/{seq:03d}-{row["phase"]}.json', row)
        self.records = rows
        self._pending = row['step'] if row['phase'] == 'intent' else None

    def _effect(self, name):
        self.guard(self.ctx)
        _require(self._claimed and self._pending == name)
        # An uncertain command can never be repeated on this object.
        self._pending = None

    def start_unit(self, unit):
        _require(unit in UNITS)
        self._effect('start_socket' if unit == 'neo-wechat.socket' else 'start_service')
        self.runner.run(('/usr/bin/systemctl', 'start', unit))

    def stop_units(self, units):
        _require(units == ('neo-wechat.socket', 'neo-wechat.service'))
        self._effect('stop_units')
        self.runner.run(('/usr/bin/systemctl', 'stop', *units))
        self._ready = 'unknown'

    def publish_proxy_include(self, receipt):
        _require(receipt == self.ctx['expected_bindings']['proxy_receipt_sha256'])
        self._effect('publish_proxy_include')
        _require(self.fs.metadata(FRAGMENT, absent=True) is None)
        raw = self.manifest['proxy_fragment']
        _require(type(raw) is bytes and _sha(raw) == self.manifest['proxy_receipt']['fragment_sha256'])
        self._proxy_owned = self.fs.write_once(FRAGMENT, raw, 0o644)
        self._validated = None

    def unpublish_proxy_include(self, receipt):
        _require(receipt == self.ctx['expected_bindings']['proxy_receipt_sha256'])
        self._effect('unpublish_proxy_include')
        self._proxy_signature()
        _require(self._proxy_owned is not None)
        self.fs.unlink_exact(FRAGMENT, self._proxy_owned)
        self._proxy_owned, self._validated = None, None

    def validate_proxy(self):
        self._effect('validate_proxy')
        before = self._proxy_signature()
        self.runner.run(('/usr/sbin/nginx', '-t'))
        _require(self._proxy_signature() == before)
        self._validated = before
        return True

    def reload_proxy(self, receipt):
        _require(receipt == self.ctx['expected_bindings']['proxy_receipt_sha256'])
        self._effect('reload_proxy')
        _require(self._validated is not None and self._proxy_signature() == self._validated)
        self.runner.run(('/usr/bin/systemctl', 'reload', 'nginx.service'))
        _require(self._proxy_signature() == self._validated)

    def _loaded(self):
        raw = self.runner.run(_http_command())
        body, status = raw.rsplit(b'\n', 1)
        if status == b'404':
            return 'absent'
        _require(status == b'200')
        value = json.loads(body)
        _require(type(value) is dict and value.get('resource') == ORIGIN+'/neo-wechat/mcp')
        return 'recorded'

    def observe(self, context):
        self.guard(context)
        units = {}
        for unit in UNITS:
            row = _properties(self.runner.run(('/usr/bin/systemctl', 'show', unit, '--property='+UNIT_PROPERTIES, '--all')))
            _require(set(row) == set(UNIT_PROPERTIES.split(',')) and row['LoadState'] == 'loaded'
                     and row['FragmentPath'] == '/etc/systemd/system/'+unit and row['DropInPaths'] == ''
                     and row['UnitFileState'] == 'static' and row['ActiveState'] in ('active', 'inactive'))
            units[unit] = dict(state=row['ActiveState'], unit_file_state='static', dropins=[])
        socket_meta = self.fs.metadata('run/neo-wechat/bridge.sock', absent=True)
        if socket_meta is not None:
            _require(socket_meta['mode'] == stat.S_IFSOCK | 0o660 and socket_meta['uid'] == self.manifest['bridge_uid']
                     and socket_meta['gid'] == self.manifest['proxy_gid'])
        signature = self._proxy_signature()
        loaded = self._loaded()
        if self.ctx['kind'] == 'stop' and not self._claimed:
            _require(self._proxy_owned is not None and loaded == 'recorded')
            self.runner.run(('/usr/sbin/nginx', '-t'))
            _require(self._proxy_signature() == signature and self._loaded() == 'recorded')
            self._validated, self._ready = signature, 'ready'
        observed = dict(version=1, bindings=copy.deepcopy(self.ctx['expected_bindings']),
            preserved=_preserved_snapshot(self.fs, self.runner, self.manifest), units=units,
            proxy=dict(entry='recorded' if self._proxy_owned is not None else 'absent',
                loaded=loaded, validated=self._validated == signature),
            socket_path='recorded' if socket_meta is not None else 'absent', readiness=self._ready,
            lease=dict(operation_id=self.ctx['lease_operation_id'], identity=copy.deepcopy(self.ctx['lease_identity'])))
        self._observed = validate_observation(self.ctx, observed)
        return copy.deepcopy(self._observed)

    def check_readiness(self, kind):
        _require(kind == self.ctx['kind'])
        self._effect('verify_final_state')
        expected = 'recorded' if kind == 'activate' else 'absent'
        _require(self._loaded() == expected)
        self._ready = 'ready' if kind == 'activate' else 'stopped'
        return True
