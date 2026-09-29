"""Real packets, only inside a fresh network namespace; never the host network.

Run as root: unshare --net python3 scripts/test_public_host_network_native.py
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace


def exercise(guard):
    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('refusing to change host network')
    guard.pwd.getpwnam = lambda name: SimpleNamespace(pw_uid={'health-app': 65531, 'health-web': 65532}[name])
    guard.run('/usr/sbin/ip', 'link', 'set', 'lo', 'up')
    guard.network_guard()
    guard.network_guard()

    def exchange(address, port, server_uid, client_uid, allowed):
        family = socket.AF_INET6 if ':' in address else socket.AF_INET
        read, write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read)
            try:
                os.setgroups([])
                os.setgid(server_uid)
                os.setuid(server_uid)
                with socket.socket(family) as listener:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.settimeout(2)
                    listener.bind((address, port))
                    listener.listen(1)
                    os.write(write, b'R')
                    with listener.accept()[0] as connection:
                        connection.settimeout(2)
                        if connection.recv(4) != b'ping':
                            os._exit(3)
                        connection.sendall(b'pong')
                os._exit(0)
            except OSError:
                os._exit(0 if not allowed else 4)
        os.close(write)
        assert os.read(read, 1) == b'R'
        os.close(read)
        client = '''import os,socket,sys
os.setgroups([]); os.setgid(int(sys.argv[3])); os.setuid(int(sys.argv[3]))
try:
    with socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET) as s:
        s.settimeout(1); s.connect((sys.argv[1],int(sys.argv[2]))); s.sendall(b'ping')
        assert s.recv(4)==b'pong'
except OSError:
    sys.exit(10)
'''
        result = subprocess.run([sys.executable, '-I', '-c', client, address, str(port), str(client_uid)], capture_output=True, timeout=4)
        _, status = os.waitpid(pid, 0)
        assert result.returncode == (0 if allowed else 10), (address, port, server_uid, client_uid, result.returncode)
        assert os.waitstatus_to_exitcode(status) == 0

    for address in ('127.0.0.1', '::1'):
        # The server UID must be able to reply to an arbitrary client ephemeral port.
        exchange(address, 30001, 65532, 0, True)
        exchange(address, 8000, 65531, 65532, True)
        exchange(address, 5432, 0, 65531, True)
        for uid in (65531, 65532):
            exchange(address, 5052, 0, uid, False)
            exchange(address, 8545, 0, uid, False)
    guard.run('/usr/sbin/ip', 'addr', 'add', '100.100.100.200/32', 'dev', 'lo')
    exchange('100.100.100.200', 80, 0, 65531, False)
    guard.run('/usr/sbin/iptables', '-I', 'OUTPUT', '1', '-j', 'ACCEPT')
    try:
        guard.network_guard()
    except RuntimeError as error:
        assert 'not first' in str(error)
    else:
        raise AssertionError('permissive rule before UID boundary was accepted')
    print('NATIVE_IPV4_IPV6_REPLY_DENY_ORDER_PASS')


if __name__ == '__main__':
    import harden_public_host
    exercise(harden_public_host)
