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


def exercise_monitor(guard):
    import re
    import threading
    import monitor_ingress_repair as monitor

    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('refusing to change host network')
    peer='reva-monitor-test-'+str(os.getpid())
    ip='/usr/sbin/ip'
    guard.run(ip,'netns','add',peer)
    try:
        guard.run(ip,'link','add','monitor-in','type','veth','peer','name','monitor-out')
        guard.run(ip,'link','set','monitor-out','netns',peer)
        guard.run(ip,'link','set','monitor-in','up')
        guard.run(ip,'netns','exec',peer,ip,'link','set','monitor-out','up')
        for family,left,right in (('-4','198.18.0.1/30','198.18.0.2/30'),('-6','fd00:5245::1/64','fd00:5245::2/64')):
            guard.run(ip,family,'addr','add',left,'dev','monitor-in',*(['nodad'] if family=='-6' else []))
            guard.run(ip,'netns','exec',peer,ip,family,'addr','add',right,'dev','monitor-out',*(['nodad'] if family=='-6' else []))
        def serve(listener):
            def echo(connection):
                with connection:
                    while data:=connection.recv(16):connection.sendall(data)
            while True:
                connection,_=listener.accept()
                threading.Thread(target=echo,args=(connection,),daemon=True).start()
        for family in (socket.AF_INET,socket.AF_INET6):
            for port in (9090,9100):
                listener=socket.socket(family)
                listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                if family==socket.AF_INET6:listener.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
                listener.bind(('::' if family==socket.AF_INET6 else '0.0.0.0',port));listener.listen()
                threading.Thread(target=serve,args=(listener,),daemon=True).start()
        for binary,chain,_ in monitor.FAMILIES:
            guard.run(binary,'-N',chain)
            guard.run(binary,'-A','INPUT','-j',chain)
            guard.run(binary,'-A',chain,'-i','lo','-j','ACCEPT')
            guard.run(binary,'-A',chain,'-m','conntrack','--ctstate','RELATED,ESTABLISHED','-j','ACCEPT')
        client='''import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET);s.settimeout(1)
try:
 s.connect((sys.argv[1],int(sys.argv[2])));s.sendall(b'ping');assert s.recv(4)==b'ping'
except OSError:sys.exit(0 if sys.argv[3]=='new-blocked' else 3)
if sys.argv[3]=='new-blocked':sys.exit(4)
print('CONNECTED',flush=True);sys.stdin.readline()
try:s.sendall(b'ping');s.recv(4)
except OSError:sys.exit(0)
sys.exit(5)
'''
        clients=[]
        for address in ('198.18.0.1','fd00:5245::1'):
            for port in (9090,9100):
                p=subprocess.Popen([ip,'netns','exec',peer,sys.executable,'-I','-c',client,address,str(port),'existing'],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                assert p.stdout.readline().strip()=='CONNECTED'
                clients.append(p)
        # Load precisely the persistent transform in the isolated kernel. This
        # proves reload semantics, serialization and preserved OUTPUT rules.
        for binary,chain,_ in monitor.FAMILIES:
            before=guard.run(binary+'-save','-t','filter')
            wanted=monitor.config_after(before,chain)
            clean=lambda raw:[re.sub(r'^(:\S+ \S+) \[\d+:\d+\]$',r'\1 [COUNTERS]',line) for line in raw.splitlines() if not line.startswith('#')]
            subprocess.run([binary+'-restore','--test','--noflush','--wait','5'],input=wanted,text=True,check=True,capture_output=True)
            assert clean(guard.run(binary+'-save','-t','filter'))==clean(before)
            subprocess.run([binary+'-restore','--wait','5'],input=wanted,text=True,check=True,capture_output=True)
            actual=guard.run(binary+'-save','-t','filter')
            monitor.verify_delta(clean(before),clean(actual),chain)
        for p in clients:
            p.communicate('\n',timeout=4)
            assert p.returncode==0
        for address in ('198.18.0.1','fd00:5245::1'):
            for port in (9090,9100):
                p=subprocess.run([ip,'netns','exec',peer,sys.executable,'-I','-c',client,address,str(port),'new-blocked'],capture_output=True,timeout=4)
                assert p.returncode==0
        for address in ('127.0.0.1','::1'):
            for port in (9090,9100):
                with socket.create_connection((address,port),timeout=1) as s:
                    s.sendall(b'ping');assert s.recv(4)==b'ping'
        print('NATIVE_MONITOR_IPV4_IPV6_NEW_EXISTING_DENY_LOOPBACK_RELOAD_PASS')
    finally:
        guard.run(ip,'netns','delete',peer)


if __name__ == '__main__':
    import harden_public_host
    exercise(harden_public_host)
    exercise_monitor(harden_public_host)
