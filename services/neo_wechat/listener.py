"""Strict Linux systemd activation; no socket creation or listener syscalls."""
from __future__ import annotations

import os
import socket
import stat


def _verify_listener(listener, expected_path):
    try:
        info = os.fstat(listener.fileno())
        if (listener.fileno() != 3 or not stat.S_ISSOCK(info.st_mode)
                or listener.family != socket.AF_UNIX
                or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
                or listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1
                or listener.getsockname() != expected_path):
            raise ValueError('socket_activation_required')
        return info.st_dev, info.st_ino
    except (OSError, ValueError):
        raise ValueError('socket_activation_required') from None


class _ActivatedListener(socket.socket):
    """asyncio calls listen() even for supplied listeners; never issue that syscall."""

    def listen(self, backlog=128):
        identity = _verify_listener(self, self._expected_path)
        if identity != self._identity:
            raise ValueError('socket_activation_required')
        # systemd already owns bind/listen/backlog. The unit denies both syscalls.


def inherited_listener(expected_path):
    """Consume exactly the one named systemd FD, before any secret is accessed."""
    activation = {key: os.environ.pop(key, None)
                  for key in ('LISTEN_PID', 'LISTEN_FDS', 'LISTEN_FDNAMES')}
    if activation != {'LISTEN_PID': str(os.getpid()), 'LISTEN_FDS': '1',
                      'LISTEN_FDNAMES': 'neo-wechat-http'}:
        raise ValueError('socket_activation_required')
    listener = None
    try:
        listener = _ActivatedListener(fileno=3)
        listener._expected_path = expected_path
        listener._identity = _verify_listener(listener, expected_path)
        os.set_inheritable(listener.fileno(), False)
        return listener
    except (OSError, ValueError):
        if listener is not None:
            listener.close()
        raise ValueError('socket_activation_required') from None


