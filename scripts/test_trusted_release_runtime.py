"""Installed entry must use the reviewed runtime before any release consumption."""
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_trusted_release_server import SCRIPT, SHA, load_server, policy


class ExecTransferred(Exception):
    pass


def test_real_exec_reenters_isolated_runtime_without_inherited_environment(tmp_path):
    """Exercise execve with synthetic inputs; no installed/root entry is run."""
    child = tmp_path / 'synthetic_launcher.py'
    child.write_text('''
import importlib.util, json, os, sys
from pathlib import Path
if sys.flags.no_site:
    print(json.dumps({
        'flags': [sys.flags.isolated, sys.flags.no_site, sys.flags.dont_write_bytecode],
        'command': os.environ.get('SSH_ORIGINAL_COMMAND'),
        'inherited': sorted(key for key in ('PYTHONPATH', 'HTTPS_PROXY', 'SSL_CERT_FILE', 'SYNTHETIC_TOKEN') if key in os.environ),
    }))
else:
    spec = importlib.util.spec_from_file_location('synthetic_release', ''' + repr(str(SCRIPT)) + ''')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixed = str(Path(sys.executable).resolve())
    module.PYTHON = fixed
    # Ownership of this test interpreter is not the installed root boundary.
    # The existing unit tests separately exercise secure_path rejection.
    def secure(path):
        assert str(path) == fixed
    module.secure_path = secure
    sys.executable = '/synthetic/legacy/python'
    module.normalize_installed_runtime(Path(__file__).absolute(), 'check ' + 'a' * 40)
''')
    env = dict(os.environ)
    env.update({key: 'synthetic' for key in
                ('PYTHONPATH', 'HTTPS_PROXY', 'SSL_CERT_FILE', 'SYNTHETIC_TOKEN')})
    result = subprocess.run([sys.executable, '-I', str(child)], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        'flags': [1, 1, 1], 'command': 'check ' + 'a' * 40, 'inherited': [],
    }


def runtime(executable='/usr/bin/python3', version=(3, 10, 12), **flags):
    values = dict(isolated=1, optimize=0, no_site=0, dont_write_bytecode=0)
    values.update(flags)
    return SimpleNamespace(executable=executable, version_info=version,
        flags=SimpleNamespace(**values), argv=['fixed'], stderr=io.StringIO())


def test_legacy_entry_reexecs_once_with_only_fixed_arguments_and_environment(monkeypatch, tmp_path):
    m = load_server(); monkeypatch.setattr(m, 'sys', runtime())
    interpreter = tmp_path / 'python3.12'; interpreter.write_bytes(b'fixture'); interpreter.chmod(0o755)
    monkeypatch.setattr(m, 'PYTHON', str(interpreter))
    checked = []; monkeypatch.setattr(m, 'secure_path', lambda p: checked.append(p))
    for key in ('PYTHONPATH', 'LD_PRELOAD', 'HTTPS_PROXY', 'SSL_CERT_FILE', 'SECRET_TOKEN'):
        monkeypatch.setenv(key, 'must-not-cross-runtime-boundary')
    installed = Path('/usr/local/lib/reva-release/trusted_release_server.py')
    command = 'check ' + SHA; calls = []
    def transfer(path, args, env):
        calls.append((path, args, env)); raise ExecTransferred
    monkeypatch.setattr(m.os, 'execve', transfer)
    with pytest.raises(ExecTransferred): m.normalize_installed_runtime(installed, command)
    assert checked == [interpreter]
    assert calls == [(str(interpreter), [str(interpreter), '-I', '-S', '-B', str(installed)],
        {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LC_ALL':'C', 'SSH_ORIGINAL_COMMAND':command})]


@pytest.mark.parametrize('fault', ['optimized', 'not_isolated', 'target_version', 'target_site', 'target_bytecode', 'unsafe', 'not_executable', 'directory'])
def test_runtime_rejects_unsafe_or_recursive_transition(monkeypatch, tmp_path, fault):
    m = load_server(); target = tmp_path / 'python3.12'
    if fault == 'directory': target.mkdir()
    else: target.write_bytes(b'fixture'); target.chmod(0o644 if fault == 'not_executable' else 0o755)
    monkeypatch.setattr(m, 'PYTHON', str(target))
    current = runtime()
    if fault == 'optimized': current.flags.optimize = 1
    if fault == 'not_isolated': current.flags.isolated = 0
    if fault.startswith('target_'):
        current = runtime(str(target), (3, 12, 13), no_site=1, dont_write_bytecode=1)
        if fault == 'target_version': current.version_info = (3, 10, 12)
        if fault == 'target_site': current.flags.no_site = 0
        if fault == 'target_bytecode': current.flags.dont_write_bytecode = 0
    monkeypatch.setattr(m, 'sys', current)
    def secure(_):
        if fault == 'unsafe': raise m.LaunchError('unsafe interpreter')
    monkeypatch.setattr(m, 'secure_path', secure)
    monkeypatch.setattr(m.os, 'execve', lambda *a: pytest.fail('unsafe or recursive exec'))
    with pytest.raises(m.LaunchError): m.normalize_installed_runtime(SCRIPT, 'check ' + SHA)


def test_supported_runtime_continues_without_exec(monkeypatch):
    m = load_server()
    monkeypatch.setattr(m, 'sys', runtime(m.PYTHON, (3, 12, 13), no_site=1, dont_write_bytecode=1))
    monkeypatch.setattr(m.os, 'execve', lambda *a: pytest.fail('recursive exec'))
    m.normalize_installed_runtime(SCRIPT, 'check ' + SHA)


@pytest.mark.parametrize('fault', ['sha', 'installed_bytes', 'installed_path', 'optimized', 'exec_failure', None])
def test_main_validates_authority_before_runtime_and_never_consumes_in_parent(monkeypatch, tmp_path, fault):
    m = load_server(); current = runtime()
    if fault == 'optimized': current.flags.optimize = 1
    monkeypatch.setattr(m, 'sys', current)
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m.os, 'umask', lambda _: None)
    monkeypatch.setattr(m.time, 'time', lambda: 100)
    monkeypatch.setattr(m, 'STATE', tmp_path / 'never-created')
    digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    if fault == 'installed_bytes': digest = '0' * 64
    monkeypatch.setattr(m, '_read_private', lambda _: json.dumps(policy(executor_sha256=digest)).encode())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'run ' + ('c' * 40 if fault == 'sha' else SHA))
    def secure(p, **kw):
        if fault == 'installed_path' and p == SCRIPT: raise m.LaunchError('unsafe installed path')
    monkeypatch.setattr(m, 'secure_path', secure)
    calls = []
    def normalize(installed, command):
        calls.append((installed, command))
        if fault == 'exec_failure': raise OSError('exec failed')
        raise ExecTransferred
    monkeypatch.setattr(m, 'normalize_installed_runtime', normalize, raising=False)
    monkeypatch.setattr(m, 'attest_full_ci', lambda _: pytest.fail('parent reached CI'))
    monkeypatch.setattr(m, 'run_once', lambda *a: pytest.fail('parent consumed a release'))
    # main sanitizes ordinary exceptions, including this simulated exec transfer.
    assert m.main() == 1
    assert bool(calls) == (fault in (None, 'exec_failure'))
    assert not m.STATE.exists()
