#!/usr/bin/env python3
"""Unauthenticated, read-only runner route probe; never a release permission.

A TCP connection and SSH identification line prove only that an endpoint responds
at this fixed address. They do NOT prove authentication, host identity, readiness,
CI success or an unconsumed authorization. Real releases still require all gates.
No credential files, environment values, SSH client or local configuration are read.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import time

HOST = '39.98.206.178'
PORT = 22
TIMEOUT_SECONDS = 5.0
MAX_BANNER_BYTES = 255
_BANNER = re.compile(rb'SSH-2\.0-[\x21-\x7e]+(?: [\x20-\x7e]*)?\r\n\Z')


class TransportBlocked(Exception):
    """Static, non-sensitive reason suitable for the runner receipt."""


def check_transport(started: float) -> None:
    """Read at most one bounded SSH identification line; send no bytes."""
    deadline = started + TIMEOUT_SECONDS
    try:
        peer = socket.create_connection((HOST, PORT), timeout=TIMEOUT_SECONDS)
    except OSError:
        raise TransportBlocked('connect_failed') from None
    try:
        banner = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportBlocked('deadline_exceeded')
            peer.settimeout(remaining)
            try:
                chunk = peer.recv(MAX_BANNER_BYTES - len(banner))
            except socket.timeout:
                raise TransportBlocked('banner_timeout') from None
            except OSError:
                raise TransportBlocked('banner_read_failed') from None
            if time.monotonic() >= deadline:
                raise TransportBlocked('deadline_exceeded')
            if not chunk:
                raise TransportBlocked('banner_missing')
            banner.extend(chunk)
            if len(banner) > MAX_BANNER_BYTES:
                raise TransportBlocked('banner_invalid')
            if b'\n' in banner:
                line = bytes(banner).split(b'\n', 1)[0] + b'\n'
                if not _BANNER.fullmatch(line):
                    raise TransportBlocked('banner_invalid')
                return
            if len(banner) >= MAX_BANNER_BYTES:
                raise TransportBlocked('banner_invalid')
    finally:
        peer.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Fixed endpoint and timeout are policy, not caller-supplied arguments.
    parser.parse_args(argv)
    started = time.monotonic()
    reason = 'ssh_banner_observed'
    status = 'reachable'
    try:
        check_transport(started)
    except TransportBlocked as exc:
        reason = str(exc)
        status = 'blocked'
    except OSError:
        reason = 'socket_failed'
        status = 'blocked'
    print(json.dumps({
        'schema_version': 'runner_transport.v1',
        'stage': 'runner_transport',
        'status': status,
        'reason': reason,
        'elapsed_seconds': round(max(0.0, time.monotonic() - started), 2),
        'timeout_seconds': TIMEOUT_SECONDS,
        'authenticated': False,
        'host_identity_verified': False,
        'claim_consumed': False,
        'read_only': True,
    }, sort_keys=True))
    return 0 if status == 'reachable' else 1


if __name__ == '__main__':
    raise SystemExit(main())
