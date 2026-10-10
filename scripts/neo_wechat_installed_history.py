"""Read-only installed lifecycle admission, separate from immutable dormant audit.

Call only from a canonical root-controlled release/rotation gate while its
original locks are held. All paths are trusted local caller configuration, never
WeChat/MCP/request inputs. owner_uid exists for synthetic unprivileged tests;
production must use the default root UID. No credential or lease-token CONTENT
is read. The only files read contain bounded lifecycle/evidence metadata.

No durable closure authority protocol is approved here. ANY existing lifecycle
namespace blocks release/rotation, even with fully consistent completed records
and a live original lease. final-guard.json is intentionally NOT a recognized
file: visibility or caller booleans cannot prove fsync or a final guard. Absent
history means NO_LIFECYCLE_HISTORY, never operation success. There is no writer,
cleanup, lease release, retry, recovery mutation, CLI, or positive callback bypass.

The diagnostic history_state="complete" describes ordered record completeness
only. Runtime references to prior provisioning receipts are structurally checked
context assertions, not reconstructed across installed namespaces. Diagnostics
cannot establish original provenance or completion authority.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from scripts import neo_wechat_lifecycle_history as history
from scripts.neo_wechat_lifecycle import validate_dormant_receipt

LIFECYCLE_DIRECTORY = 'neo-wechat-lifecycle'
NAMESPACES = frozenset(('provision-v1', 'runtime-lifecycle-v1'))
MAX_OPERATIONS = 32
MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = 8 * 1024 * 1024
_ROW_NAME = re.compile(r'([0-9]{3})-(intent|verified|completed)\.json')
_EVIDENCE_NAME = re.compile(r'([0-9]{3})-evidence\.json')
_DORMANT_FILES = frozenset(('before.json', 'intent.json', 'lease.json', 'verified.json', 'completed.json'))


class InstalledHistoryError(ValueError):
    def __init__(self):
        super().__init__('neo_wechat_lifecycle_history_blocked')


def _require(value):
    if not value:
        raise InstalledHistoryError()


def _identity(info):
    return [info.st_dev, info.st_ino]


def _metadata(info):
    return dict(dev=info.st_dev, ino=info.st_ino, uid=info.st_uid, gid=info.st_gid,
                mode=info.st_mode, nlink=info.st_nlink, size=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)


def _directory_metadata(info, owner_uid, *, private=False, ancestor=False):
    owners = {0, owner_uid} if ancestor else {owner_uid}
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid in owners and not info.st_mode & 0o022)
    if private:
        _require(stat.S_IMODE(info.st_mode) == 0o700)


def _file_metadata(info, owner_uid, maximum):
    _require(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid and info.st_nlink == 1
             and stat.S_IMODE(info.st_mode) == 0o600 and 0 <= info.st_size <= maximum)


def _bounded_json(raw):
    def unique(pairs):
        value = {}
        for key, child in pairs:
            _require(key not in value)
            value[key] = child
        return value
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(InstalledHistoryError()))
    budget = [4096]
    def check(item, depth):
        budget[0] -= 1
        _require(depth <= 16 and budget[0] >= 0)
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            _require(-(2**63) <= item < 2**64)
            return
        if type(item) is str:
            _require(len(item) <= 8192)
            return
        if type(item) is list:
            _require(len(item) <= 256)
            for child in item:
                check(child, depth+1)
            return
        _require(type(item) is dict and len(item) <= 128)
        for key, child in item.items():
            check(key, depth+1)
            check(child, depth+1)
    check(value, 0)
    return value


class _Tree:
    """Pin every path component and recheck names, descriptors and inventories."""
    def __init__(self, owner_uid):
        _require(type(owner_uid) is int and 0 <= owner_uid < 2**32)
        self.owner_uid = owner_uid
        self.fds = []
        self.links = []
        self.inventories = []
        self.files = []
        self.absences = []
        self.total_bytes = 0

    def _open_directory(self, path, parent=None, *, private=False, ancestor=False):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     **({'dir_fd': parent} if parent is not None else {}))
        self.fds.append(fd)
        info = os.fstat(fd)
        _directory_metadata(info, self.owner_uid, private=private, ancestor=ancestor)
        if parent is not None:
            named = os.stat(path, dir_fd=parent, follow_symlinks=False)
            _require(_identity(info) == _identity(named) and stat.S_ISDIR(named.st_mode))
            self.links.append((parent, path, fd, _identity(info), private, ancestor))
        return fd

    def path(self, path, *, private=False):
        path = Path(path)
        _require(path.is_absolute() and '..' not in path.parts and len(path.parts) > 1)
        current = self._open_directory('/', ancestor=True)
        for index, component in enumerate(path.parts[1:], start=1):
            final = index == len(path.parts)-1
            current = self._open_directory(component, current, private=private if final else False,
                                           ancestor=not final)
        return current

    def child(self, parent, name, *, private=True):
        _require(type(name) is str and re.fullmatch(r'[a-z0-9-]{1,128}', name) is not None)
        return self._open_directory(name, parent, private=private)

    def exists(self, parent, name):
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            self.absences.append((parent, name))
            return False

    def inventory(self, fd, maximum):
        names = set()
        with os.scandir(fd) as entries:
            for entry in entries:
                _require(len(names) < maximum and entry.name not in names)
                names.add(entry.name)
        self.inventories.append((fd, names, maximum))
        return names

    def read(self, parent, name, *, maximum=MAX_FILE_BYTES):
        # Name allowlists are checked by callers before this opens metadata.
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
        self.fds.append(fd)
        before = os.fstat(fd)
        _file_metadata(before, self.owner_uid, maximum)
        expected = _metadata(before)
        _require(_metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected)
        raw = bytearray()
        while len(raw) <= maximum:
            part = os.read(fd, maximum+1-len(raw))
            if not part:
                break
            raw.extend(part)
        self.total_bytes += len(raw)
        _require(len(raw) == before.st_size and len(raw) <= maximum and self.total_bytes <= MAX_TOTAL_BYTES)
        _require(_metadata(os.fstat(fd)) == expected
                 and _metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected)
        self.files.append((parent, name, fd, expected, maximum))
        return _bounded_json(bytes(raw))

    def verify(self):
        for parent, name, fd, expected, private, ancestor in self.links:
            now = os.fstat(fd)
            _directory_metadata(now, self.owner_uid, private=private, ancestor=ancestor)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            _require(_identity(now) == expected == _identity(named) and stat.S_ISDIR(named.st_mode))
        for fd, expected, maximum in self.inventories:
            names = set()
            with os.scandir(fd) as entries:
                for entry in entries:
                    _require(len(names) < maximum)
                    names.add(entry.name)
            _require(names == expected)
        for parent, name in self.absences:
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise InstalledHistoryError()
        for parent, name, fd, expected, maximum in self.files:
            info = os.fstat(fd)
            _file_metadata(info, self.owner_uid, maximum)
            _require(_metadata(info) == expected
                     and _metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected)

    def close(self):
        failed = False
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.fds = []
        if failed:
            raise InstalledHistoryError()


def _original_dormant(tree, state, operation_id):
    old = tree.child(state, 'neo-wechat')
    _require(tree.inventory(old, 2) == {operation_id})
    audit = tree.child(old, operation_id)
    _require(tree.inventory(audit, 6) == _DORMANT_FILES)
    records = {name[:-5]: tree.read(audit, name, maximum=262144) for name in sorted(_DORMANT_FILES)}
    receipt = validate_dormant_receipt(records['completed'])
    _require(records['verified'] == receipt and receipt['operation_id'] == operation_id)
    before = records['before']
    _require(type(before) is dict)
    before_hash = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    _require(before_hash == receipt['evidence_sha256'])
    _require(all(before.get(key) == receipt[key] for key in ('publisher_sha', 'production_sha', 'operation_id')))
    _require(records['intent'] == {'state': 'INSTALL_STARTED', 'evidence_sha256': before_hash,
        'operation_id': operation_id, 'publisher_sha': receipt['publisher_sha']})
    _require(type(records['lease']) is dict and set(records['lease']) == {'identity'}
             and history._lease_identity(records['lease']['identity']))
    return receipt


def _lease_state(context, lease_path, owner_uid):
    if lease_path is None:
        return 'unproven'
    tree = _Tree(owner_uid)
    try:
        fd = tree.path(lease_path, private=True)
        _require(tree.inventory(fd, 5) == {'token', 'label', 'stage', 'started_at'})
        token_identity = None
        # Check only metadata. No lease token, label, stage, or time content read.
        for name in ('token', 'label', 'stage', 'started_at'):
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
            tree.fds.append(child)
            info = os.fstat(child)
            _file_metadata(info, owner_uid, 4096)
            _require(_metadata(info) == _metadata(os.stat(name, dir_fd=fd, follow_symlinks=False)))
            tree.files.append((fd, name, child, _metadata(info), 4096))
            if name == 'token':
                token_identity = _identity(info)
        observed = [_identity(os.fstat(fd)), token_identity]
        tree.verify()
        return 'original_present' if observed == context['lease_identity'] else 'replaced'
    except FileNotFoundError:
        return 'missing'
    except Exception:
        return 'unproven'
    finally:
        tree.close()


def _operation(tree, state, namespace_fd, namespace, operation_id, lease_path):
    _require(re.fullmatch(r'[0-9a-f]{32}', operation_id) is not None)
    fd = tree.child(namespace_fd, operation_id)
    names = tree.inventory(fd, 96)
    _require({'context.json', 'original-dormant.json'} <= names)
    rows_by_sequence = {}
    evidence_names = set()
    for name in names - {'context.json', 'original-dormant.json'}:
        row_match = _ROW_NAME.fullmatch(name)
        evidence_match = _EVIDENCE_NAME.fullmatch(name)
        if row_match:
            sequence = int(row_match[1])
            _require(sequence not in rows_by_sequence)
            rows_by_sequence[sequence] = (name, row_match[2])
        elif evidence_match and namespace == 'runtime-lifecycle-v1':
            evidence_names.add(name)
        else:
            # Includes unapproved final-guard/closure candidates and artifacts.
            raise InstalledHistoryError()
    context = tree.read(fd, 'context.json')
    original_copy = tree.read(fd, 'original-dormant.json')
    _require(type(context) is dict and context.get('namespace') == namespace and context.get('operation_id') == operation_id)
    _require(type(context.get('install_operation_id')) is str
             and re.fullmatch(r'[0-9a-f]{32}', context['install_operation_id']) is not None)
    original = _original_dormant(tree, state, context['install_operation_id'])
    _require(original_copy == original and context.get('dormant_receipt_sha256') == history.digest(original))
    rows = []
    for sequence in sorted(rows_by_sequence):
        name, phase = rows_by_sequence[sequence]
        row = tree.read(fd, name)
        _require(type(row) is dict and type(row.get('sequence')) is int and row['sequence'] == sequence and row.get('phase') == phase)
        rows.append(row)
    if namespace == 'runtime-lifecycle-v1':
        context = history.validate_context(context)
        rows = history.validate_history(context, rows)
        expected_evidence = {f'{row["sequence"]:03d}-evidence.json' for row in rows if row['phase'] == 'verified'}
        _require(evidence_names == expected_evidence)
        for row in rows:
            if row['phase'] == 'verified':
                observed = history.validate_observation(context, tree.read(fd, f'{row["sequence"]:03d}-evidence.json'))
                _require(history.digest(observed) == row['evidence_sha256'])
        complete = bool(rows and rows[-1]['phase'] == 'completed')
        terminal_hash = history.digest(rows[-1]) if rows else None
        kind = context['kind']
    else:
        context = history.validate_provision_context(context, original)
        rows = history.validate_provision_history(context, original, rows)
        complete = len(rows) == 10
        terminal_hash = history.provision_record_digest(rows[-1]) if rows else None
        kind = 'provision'
    return {'namespace': namespace, 'operation_id': operation_id, 'kind': kind,
        'history_state': 'complete' if complete else 'incomplete', 'record_count': len(rows),
        'context_sha256': history.digest(context), 'terminal_record_sha256': terminal_hash,
        'history_sha256': history.digest([history.digest(row) for row in rows]),
        'lease_state': _lease_state(context, lease_path, tree.owner_uid), 'closure_state': 'unapproved'}


def _result(state, reason, operations=None):
    return {'version': 1, 'state': state, 'reason': reason, 'operations': operations or [],
            'authority': 'none', 'executable_actions': []}


def inspect_installed_history(state, *, owner_uid=0, lease_path=None):
    """Return a bounded diagnostic only; malformed history never emits inputs."""
    tree = None
    try:
        tree = _Tree(owner_uid)
        state_fd = tree.path(state)
        if not tree.exists(state_fd, LIFECYCLE_DIRECTORY):
            tree.verify()
            return _result('NO_LIFECYCLE_HISTORY', 'separate_namespace_absent')
        root = tree.child(state_fd, LIFECYCLE_DIRECTORY)
        namespaces = tree.inventory(root, 3)
        _require(namespaces <= NAMESPACES)
        operations = []
        for namespace in sorted(namespaces):
            namespace_fd = tree.child(root, namespace)
            names = tree.inventory(namespace_fd, MAX_OPERATIONS+1)
            _require(len(names) <= (1 if namespace == 'provision-v1' else MAX_OPERATIONS))
            for operation_id in sorted(names):
                _require(len(operations) < MAX_OPERATIONS)
                operations.append(_operation(tree, state_fd, namespace_fd, namespace, operation_id, lease_path))
        tree.verify()
        return _result('RETAIN_UNCERTAIN', 'independent_closure_authority_required', operations)
    except Exception:
        return _result('RETAIN_UNCERTAIN', 'invalid_or_unknown_history')
    finally:
        if tree is not None:
            tree.close()


def assert_installed_history(state, *, owner_uid=0, lease_path=None):
    """Release/rotation gate. Any separate lifecycle namespace blocks today."""
    result = inspect_installed_history(state, owner_uid=owner_uid, lease_path=lease_path)
    if result['state'] != 'NO_LIFECYCLE_HISTORY':
        raise InstalledHistoryError()
    return result
