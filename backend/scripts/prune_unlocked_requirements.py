"""Remove stale distributions after installing the reviewed, complete hash lock."""
import argparse
import importlib.metadata
from pathlib import Path
import re
import subprocess
import sys


def unlocked(lock, distributions=None):
    expected = set()
    for line in lock.read_text().splitlines():
        if not line or line[0].isspace() or line.startswith(('#', '--')):
            continue
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9._-]*)==[^;\\\s]+\s*\\?', line)
        if not match:
            raise ValueError('invalid exact production lock')
        expected.add(re.sub(r'[-_.]+', '-', match[1]).lower())
    if 'pip' not in expected:
        raise ValueError('installer must be pinned before exact environment sync')
    installed = set()
    for distribution in importlib.metadata.distributions() if distributions is None else distributions:
        name = distribution.metadata['Name']
        if not name or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name):
            raise ValueError('invalid installed package identity')
        installed.add(re.sub(r'[-_.]+', '-', name).lower())
    return sorted(installed - expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('lock', type=Path)
    args = parser.parse_args()
    extra = unlocked(args.lock)
    if args.check:
        if extra:
            print('unlocked distributions: ' + ', '.join(extra), file=sys.stderr)
            return 1
        return 0
    if extra:
        subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '--yes', *extra], check=True)
    if unlocked(args.lock):
        raise RuntimeError('unlocked distributions remain')
    return 0


if __name__ == '__main__':
    sys.exit(main())
