#!/usr/bin/env python3
"""Run simulator operations without desktop UI; keep private local receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import plistlib
import sys
import time
import uuid


def command(argv, timeout=60):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def artifact_hash(app):
    digest = hashlib.sha256()
    for path in sorted(app.rglob('*')):
        if path.is_file():
            digest.update(str(path.relative_to(app)).encode())
            digest.update(b'\0')
            with path.open('rb') as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(block)
    return digest.hexdigest()


def capture(device, bundle, output, lock_command, *, run=command, require_locked=False, xctestrun=None):
    try:
        parsed_device = uuid.UUID(device)
    except ValueError as exc:
        raise ValueError("Explicit simulator UUID required") from exc
    if str(parsed_device) != device.lower():
        raise ValueError("Explicit simulator UUID required")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {
        'tested_at': datetime.now(timezone.utc).isoformat(),
        'device': device, 'bundle_id': bundle, 'source_sha': None,
        'functional_acceptance': 'unverified', 'status': 'running',
        'privacy': 'private', 'transport': 'simctl',
    }
    def lock_state():
        value = run(lock_command)
        if value not in ('locked', 'unlocked'):
            raise RuntimeError('Mac lock state unavailable')
        return value
    try:
        receipt['lock_before'] = lock_state()
        if require_locked and receipt['lock_before'] != 'locked':
            raise RuntimeError('Mac is not locked')
        app = Path(run(['xcrun', 'simctl', 'get_app_container', device, bundle, 'app']))
        receipt['installed_app_sha256'] = artifact_hash(app)
        run(['xcrun', 'simctl', 'launch', device, bundle])
        if run is command:
            time.sleep(2)
        if xctestrun:
            receipt['transport'] = 'simctl+xctest'
            receipt['xctestrun_sha256'] = hashlib.sha256(Path(xctestrun).read_bytes()).hexdigest()
            run(['xcodebuild', 'test-without-building', '-xctestrun', str(xctestrun),
                 '-destination', f'platform=iOS Simulator,id={device}',
                 '-parallel-testing-enabled', 'NO', '-maximum-concurrent-test-simulator-destinations', '1',
                 '-resultBundlePath', str(output / 'tests.xcresult')], timeout=600)
            receipt['ui_test_execution'] = 'passed'
            run(['xcrun', 'simctl', 'launch', device, bundle])
            if run is command:
                time.sleep(2)
        run(['xcrun', 'simctl', 'io', device, 'screenshot', str(output / 'screen.png')])
        receipt['screenshot_sha256'] = hashlib.sha256((output / 'screen.png').read_bytes()).hexdigest()
        receipt['lock_after'] = lock_state()
        if require_locked and receipt['lock_after'] != 'locked':
            raise RuntimeError('Mac unlocked during run')
        receipt['status'] = 'passed'
        return receipt
    except Exception as exc:
        receipt['status'] = 'failed'
        receipt['error_type'] = type(exc).__name__
        raise
    finally:
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        for path in output.iterdir():
            if path.is_file():
                path.chmod(0o600)


def mac_lock_state():
    state = plistlib.loads(subprocess.check_output(["/usr/sbin/ioreg", "-a", "-l", "-d", "1"], timeout=10))
    value = state.get("IOConsoleLocked") if isinstance(state, dict) else None
    if type(value) is not bool:
        raise RuntimeError("Mac lock state unavailable")
    return "locked" if value else "unlocked"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True, help='Explicit simulator UUID; never use ambiguous booted')
    parser.add_argument('--bundle-id', default='life.executor.health')
    parser.add_argument('--output', type=Path, required=True, help='New private local directory')
    parser.add_argument('--require-locked', action='store_true')
    parser.add_argument('--wait-for-lock', type=int, default=0, help='Wait up to 600 seconds for manual screen lock')
    parser.add_argument('--xctestrun', type=Path, help='Built candidate UI test suite, optional')
    args = parser.parse_args()
    if not 0 <= args.wait_for_lock <= 600:
        parser.error('--wait-for-lock must be between 0 and 600')
    if args.wait_for_lock and not args.require_locked:
        parser.error('--wait-for-lock requires --require-locked')
    os.environ.setdefault('DEVELOPER_DIR', '/Applications/Xcode.app/Contents/Developer')
    # Prevent idle system sleep only; no display wake or security changes.
    guard = subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
    try:
        deadline = time.monotonic() + args.wait_for_lock
        while args.wait_for_lock and mac_lock_state() != 'locked':
            if time.monotonic() >= deadline:
                raise RuntimeError('Timed out waiting for manual Mac lock')
            time.sleep(1)
        capture(args.device, args.bundle_id, args.output, [sys.executable, str(Path(__file__).resolve()), '--lock-state'], require_locked=args.require_locked, xctestrun=args.xctestrun)
    finally:
        guard.terminate()
        guard.wait(timeout=10)
    print(f'Simulator receipt: {args.output / "receipt.json"}')


if __name__ == '__main__':
    if sys.argv[1:] == ['--lock-state']:
        print(mac_lock_state())
    else:
        main()
