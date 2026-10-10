"""Synthetic inherited listeners; no production paths or credentials are used."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

from services.neo_wechat import server


CHILD = r'''
import asyncio, os, socket, sys
from unittest.mock import patch
from services.neo_wechat.listener import inherited_listener, _ActivatedListener
fd, expected, mode = int(sys.argv[1]), sys.argv[2], sys.argv[3]
if fd != 3:
    os.dup2(fd, 3)
    os.close(fd)
os.set_inheritable(3, True)
os.environ.update(LISTEN_PID=str(os.getpid()), LISTEN_FDS='1', LISTEN_FDNAMES='neo-wechat-http')
if mode == 'wrong_pid': os.environ['LISTEN_PID'] = str(os.getpid()+1)
if mode == 'wrong_count': os.environ['LISTEN_FDS'] = '2'
if mode == 'zero_count': os.environ['LISTEN_FDS'] = '0'
if mode == 'bad_count': os.environ['LISTEN_FDS'] = '01'
if mode == 'wrong_name': os.environ['LISTEN_FDNAMES'] = 'other'
if mode == 'extra_name': os.environ['LISTEN_FDNAMES'] += ':other'
if mode == 'missing_env': os.environ.pop('LISTEN_PID')
if mode == 'missing_fd': os.close(3)
# Darwin does not implement SO_ACCEPTCONN for AF_UNIX (ENOPROTOOPT).
# Keep production fail-closed. Only this synthetic integration harness supplies
# that Linux-only flag for a socket the parent actually called listen() on.
# The native Linux isolation probe must exercise the unmodified getsockopt path.
if sys.platform == 'darwin' and mode not in ('tcp', 'datagram', 'regular_file', 'missing_fd'):
    raw_getsockopt = _ActivatedListener.getsockopt
    def synthetic_acceptconn(self, level, option, *args):
        if level == socket.SOL_SOCKET and option == socket.SO_ACCEPTCONN:
            return 0 if mode == 'not_listening' else 1
        return raw_getsockopt(self, level, option, *args)
    _ActivatedListener.getsockopt = synthetic_acceptconn
try:
    listener = inherited_listener(expected)
except ValueError as exc:
    assert str(exc) == 'socket_activation_required'
    assert all(k not in os.environ for k in ('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES'))
    if mode in ('valid', 'uvicorn', 'recheck'): raise
    print('rejected')
    sys.exit(0)
assert mode in ('valid','uvicorn','recheck'), 'invalid listener accepted'
assert listener.fileno() == 3 and not os.get_inheritable(3)
assert all(k not in os.environ for k in ('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES'))
with patch.object(socket.socket, 'listen', side_effect=AssertionError('raw listen forbidden')):
    listener.listen(2048)
    if mode == 'recheck':
        listener.close()
        try: listener.listen(2048)
        except ValueError as exc: assert str(exc) == 'socket_activation_required'
        else: raise AssertionError('closed descriptor accepted')
    elif mode == 'uvicorn':
        import uvicorn
        async def app(scope, receive, send):
            assert scope['type'] == 'http'
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'synthetic-ok'})
        async def check():
            instance = uvicorn.Server(uvicorn.Config(app, loop='asyncio', lifespan='off',
                log_config=None, access_log=False, log_level='critical'))
            task = asyncio.create_task(instance.serve(sockets=[listener]))
            for _ in range(200):
                if instance.started: break
                if task.done(): await task
                await asyncio.sleep(.01)
            assert instance.started
            reader, writer = await asyncio.open_unix_connection(expected)
            writer.write(b'GET / HTTP/1.1\r\nHost: synthetic.example\r\nConnection: close\r\n\r\n')
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 3)
            assert b'200 OK' in response and b'synthetic-ok' in response
            writer.close()
            await writer.wait_closed()
            instance.should_exit = True
            await asyncio.wait_for(task, 3)
        asyncio.run(check())
listener.close()
print('accepted')
'''


@pytest.mark.parametrize('mode', [
    'valid', 'uvicorn', 'recheck', 'wrong_pid', 'wrong_count', 'zero_count', 'bad_count',
    'wrong_name', 'extra_name', 'missing_env', 'missing_fd', 'wrong_path',
    'tcp', 'datagram', 'not_listening', 'regular_file',
])
def test_real_inherited_socket_contract(mode):
    with tempfile.TemporaryDirectory(prefix='neo-', dir='/tmp') as directory:
        expected = str(Path(directory) / 'bridge.sock')
        if mode == 'regular_file':
            resource = open(Path(directory) / 'file', 'w+b')
        else:
            family = socket.AF_INET if mode == 'tcp' else socket.AF_UNIX
            kind = socket.SOCK_DGRAM if mode == 'datagram' else socket.SOCK_STREAM
            resource = socket.socket(family, kind)
            resource.bind(('127.0.0.1', 0) if family == socket.AF_INET else expected)
            if kind == socket.SOCK_STREAM and mode != 'not_listening':
                resource.listen(8)
        try:
            result = subprocess.run([sys.executable, '-c', CHILD, str(resource.fileno()),
                expected + '.other' if mode == 'wrong_path' else expected, mode],
                pass_fds=(resource.fileno(),), capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == ('accepted' if mode in ('valid','uvicorn','recheck') else 'rejected')
        finally:
            resource.close()


def test_main_rejects_activation_before_reading_config_credentials_or_store(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['server', '--config', '/etc/neo-wechat/config.json',
                                     '--socket', '/run/neo-wechat/bridge.sock'])
    for key in ('LISTEN_PID', 'LISTEN_FDS', 'LISTEN_FDNAMES'):
        monkeypatch.delenv(key, raising=False)
    reads = []
    monkeypatch.setattr(server, 'private_file', lambda *a, **kw: reads.append(a))
    monkeypatch.setattr(server, 'read_credential', lambda *a, **kw: reads.append(a))
    monkeypatch.setattr(server, 'Store', lambda *a, **kw: reads.append(a))
    with pytest.raises(ValueError, match='socket_activation_required'):
        server.main()
    assert reads == []


def test_main_starts_collector_with_verified_listener_and_forces_asyncio(monkeypatch):
    import base64
    import json
    import threading
    import uvicorn
    events = []
    entered = threading.Event()

    class Listener:
        def close(self): events.append('socket_closed')
    listener = Listener()
    def activated(path):
        assert path == '/run/neo-wechat/bridge.sock'
        events.append('listener_verified')
        return listener
    config = {'owner':'synthetic-owner', 'origin':'https://bridge.example',
              'client_id':'neo', 'redirect_uri':'https://client.example/callback', 'proxy_gid':123}
    def read(path, **kwargs):
        assert events[0] == 'listener_verified'
        events.append('read')
        if str(path).endswith('config.json'): return json.dumps(config).encode()
        if Path(path).name == 'encryption_key': return base64.b64encode(b's'*32)
        return b'synthetic'
    class State:
        def __init__(self, *args): events.append('store_opened')
        def close(self): events.append('store_closed')
    class FakeService:
        def __init__(self, *args, **kwargs): self.stop = threading.Event()
        def collect(self):
            events.append('collector_started')
            entered.set()
            self.stop.wait(3)
        def app(self): return lambda *args: None
    class Server:
        def __init__(self, config):
            assert config.loop == 'asyncio'
        def run(self, sockets):
            assert sockets == [listener]
            assert entered.wait(1), 'collector must start on explicit service start'
            events.append('uvicorn_started')

    monkeypatch.setattr(sys, 'argv', ['server', '--config', '/etc/neo-wechat/config.json',
                                     '--socket', '/run/neo-wechat/bridge.sock'])
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', '/synthetic/credentials')
    monkeypatch.setattr(server, 'inherited_listener', activated)
    monkeypatch.setattr(server, 'private_file', read)
    monkeypatch.setattr(server, 'read_credential', lambda directory, name: read(Path(directory) / name))
    monkeypatch.setattr(server, 'Store', State)
    monkeypatch.setattr(server, 'Service', FakeService)
    monkeypatch.setattr(uvicorn, 'Server', Server)
    server.main()
    assert events[0] == 'listener_verified'
    assert events.index('collector_started') < events.index('uvicorn_started')
    assert events[-2:] == ['socket_closed', 'store_closed']


def test_main_closes_inherited_listener_if_configuration_fails(monkeypatch):
    calls = []
    class Listener:
        def close(self): calls.append('closed')
    monkeypatch.setattr(sys, 'argv', ['server', '--config', '/etc/neo-wechat/config.json',
                                     '--socket', '/run/neo-wechat/bridge.sock'])
    monkeypatch.setattr(server, 'inherited_listener', lambda path: Listener())
    def failed(*args, **kwargs): raise ValueError('synthetic_bad_config')
    monkeypatch.setattr(server, 'private_file', failed)
    with pytest.raises(ValueError, match='synthetic_bad_config'):
        server.main()
    assert calls == ['closed']
