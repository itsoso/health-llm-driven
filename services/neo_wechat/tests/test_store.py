import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from services.neo_wechat.store import Store, StoreError, MAX_BYTES

KEY = bytes(range(32))


@pytest.fixture
def state_dir(tmp_path):
    path = tmp_path / 'state'
    path.mkdir(mode=0o700)
    return path


def test_encryption_restart_and_copy(state_dir):
    s = Store(state_dir, KEY, 'owner')
    with s.transaction() as st:
        st['login'] = {'secret': 'synthetic-sensitive-value'}
    snapshot = s.read()
    snapshot['login']['secret'] = 'tampered'
    assert s.read()['login']['secret'] == 'synthetic-sensitive-value'
    assert b'synthetic-sensitive-value' not in (state_dir / 'state.enc').read_bytes()
    s.close()
    with Store(state_dir, KEY, 'owner') as reopened:
        assert reopened.read()['login'] == {'secret': 'synthetic-sensitive-value'}


def test_transaction_abort(state_dir):
    with Store(state_dir, KEY, 'owner') as s:
        with pytest.raises(ValueError):
            with s.transaction() as st:
                st['login'] = 'never-published'
                raise ValueError('abort')
        assert s.read()['login'] is None


def test_real_second_process_cannot_acquire(state_dir):
    with Store(state_dir, KEY, 'owner'):
        code = 'from services.neo_wechat.store import Store; from pathlib import Path; Store(Path(__import__("sys").argv[1]),bytes(range(32)),"owner")'
        result = subprocess.run([sys.executable, '-c', code, str(state_dir)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'store_locked' in result.stderr
    with Store(state_dir, KEY, 'owner'):
        pass


def test_wrong_owner_key_or_tamper_rejected(state_dir):
    with Store(state_dir, KEY, 'owner') as s:
        with s.transaction() as st:
            st['login'] = None
    for key, owner in [(KEY, 'other'), (bytes(32), 'owner')]:
        with pytest.raises(StoreError, match='store_invalid'):
            Store(state_dir, key, owner)
    raw = bytearray((state_dir / 'state.enc').read_bytes())
    raw[-1] ^= 1
    (state_dir / 'state.enc').write_bytes(raw)
    with pytest.raises(StoreError, match='store_invalid'):
        Store(state_dir, KEY, 'owner')


def test_private_paths_and_links(state_dir, tmp_path):
    state_dir.chmod(0o755)
    with pytest.raises(StoreError, match='store_permissions'):
        Store(state_dir, KEY, 'owner')
    state_dir.chmod(0o700)
    target = tmp_path / 'target'
    target.write_bytes(b'x')
    target.chmod(0o600)
    (state_dir / 'state.enc').symlink_to(target)
    with pytest.raises(StoreError):
        Store(state_dir, KEY, 'owner')
    (state_dir / 'state.enc').unlink()
    os.link(target, state_dir / 'state.enc')
    with pytest.raises(StoreError):
        Store(state_dir, KEY, 'owner')


def test_missing_directory_not_implicitly_created(tmp_path):
    with pytest.raises(StoreError):
        Store(tmp_path / 'missing', KEY, 'owner')


@pytest.mark.parametrize('failure_call', [1, 2])
def test_fsync_uncertainty_poison_and_no_memory_publish(state_dir, failure_call):
    with Store(state_dir, KEY, 'owner') as s:
        before = s.read()
        real = os.fsync
        calls = 0
        def fail(fd):
            nonlocal calls
            calls += 1
            if calls == failure_call:
                raise OSError('synthetic disk failure')
            return real(fd)
        with patch('services.neo_wechat.store.os.fsync', side_effect=fail):
            with pytest.raises(StoreError, match='store_uncertain'):
                with s.transaction() as st:
                    st['login'] = {'a': 1}
        assert s._state == before
        with pytest.raises(StoreError, match='store_unavailable'):
            s.read()
        with pytest.raises(StoreError, match='store_unavailable'):
            with s.transaction():
                pass


def test_size_cap_and_nonfinite_are_rejected_without_poison(state_dir):
    with Store(state_dir, KEY, 'owner') as s:
        with pytest.raises(StoreError, match='store_invalid'):
            with s.transaction() as st:
                st['login'] = float('nan')
        with pytest.raises(StoreError, match='store_capacity'):
            with s.transaction() as st:
                st['login'] = 'x' * MAX_BYTES
        assert s.read()['login'] is None


def test_real_process_restart_recovers_encrypted_state(state_dir):
    code = '''
import sys
from pathlib import Path
from services.neo_wechat.store import Store
with Store(Path(sys.argv[1]), bytes(range(32)), 'owner') as s:
    with s.transaction() as state:
        state['login'] = {'counter': 42}
'''
    result = subprocess.run([sys.executable, '-c', code, str(state_dir)], capture_output=True, text=True)
    assert result.returncode == 0
    with Store(state_dir, KEY, 'owner') as reopened:
        assert reopened.read()['login'] == {'counter':42}


def test_nested_transaction_denied_and_candidate_not_retained(state_dir):
    with Store(state_dir, KEY, 'owner') as s:
        with s.transaction() as state:
            with pytest.raises(StoreError, match='store_nested_transaction'):
                with s.transaction():
                    pass
            state['login'] = {'counter':1}
        state['login']['counter'] = 99
        assert s.read()['login']['counter'] == 1


def test_fork_cannot_reuse_store_instance(state_dir):
    with Store(state_dir, KEY, 'owner') as s:
        pid = os.fork()
        if pid == 0:
            try:
                s.read()
            except StoreError:
                os._exit(0)
            os._exit(1)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
