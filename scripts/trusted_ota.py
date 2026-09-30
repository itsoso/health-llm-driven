"""Fixed production/iOS OTA contract shared by isolated publisher and server.

No credential reads, mutable CLI selection, URL inputs, or publication here.
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT = '911ea84f-bc7e-4a12-90cf-33966b6f7398'
RUNTIME = '1.3.4'
CHANNEL = 'production'
NATIVE_SHA = 'cad1fd1d33621532e587b265e79f737dfb06d1fe'
NATIVE_BUILD = 'bfdd2bc9-db49-4ccd-bfbc-679287be4855'
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}


def digest(data):
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON field')
        value[key] = item
    return value


def read_json(stream, bound=2000000):
    raw = stream.read(bound + 1)
    if len(raw) > bound:
        raise ValueError('oversized input')
    return json.loads(raw, object_pairs_hook=unique)


def validate_runtime_changes(paths):
    # A conservative OTA boundary. Anything outside known JS source/test or
    # asset directories requires a reviewed native baseline update.
    prefixes = ('mobile/app/', 'mobile/components/', 'mobile/hooks/', 'mobile/services/',
                'mobile/types/', 'mobile/constants/', 'mobile/stores/', 'mobile/utils/',
                'mobile/contexts/', 'mobile/lib/', 'mobile/applib/', 'mobile/__tests__/', 'packages/shared/src/')
    for path in paths:
        if path.startswith(prefixes) and Path(path).suffix in ('.ts', '.tsx', '.js', '.jsx', '.json'):
            continue
        if path.startswith('mobile/assets/') and Path(path).suffix in ('.png', '.jpg', '.jpeg', '.webp', '.svg'):
            continue
        raise ValueError('native or unknown mobile input changed')


def git(root, *args):
    return subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-C', str(root), *args], env=ENV, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30).stdout


def validate_source(root, sha):
    if re.fullmatch(r'[0-9a-f]{40}', sha) is None or git(root, 'rev-parse', 'HEAD').decode().strip() != sha:
        raise ValueError('wrong source revision')
    if git(root, 'status', '--porcelain', '--untracked-files=all', '--', 'mobile', 'packages/shared'):
        raise ValueError('dirty runtime source')
    git(root, 'merge-base', '--is-ancestor', NATIVE_SHA, sha)
    changed = git(root, 'diff', '--name-only', '--no-renames', NATIVE_SHA, sha, '--', 'mobile', 'packages/shared').decode().splitlines()
    validate_runtime_changes(changed)
    config = json.loads((root / 'mobile/app.json').read_text())['expo']
    if (config['version'] != RUNTIME or config['runtimeVersion'] != {'policy': 'appVersion'} or config['extra']['eas']['projectId'] != PROJECT):
        raise ValueError('runtime/project binding differs')


def artifact(directory):
    directory = Path(directory).resolve(strict=True)
    metadata = read_json((directory / 'metadata.json').open())
    if metadata.get('version') != 0 or set(metadata['fileMetadata']) != {'ios'}:
        raise ValueError('only iOS export is authorized')
    ios = metadata['fileMetadata']['ios']
    def hashed(path):
        if not isinstance(path, str) or Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('export path escapes artifact')
        resolved = directory / path
        if resolved.is_symlink() or not resolved.is_file() or not resolved.resolve().is_relative_to(directory):
            raise ValueError('unsafe export file')
        return digest(resolved.read_bytes())
    return {'launch': hashed(ios['bundle']), 'assets': sorted(set(hashed(item['path']) for item in ios['assets']))}


def validate_proof(proof):
    if (not isinstance(proof, dict) or set(proof) != {'launch', 'assets'} or not isinstance(proof['assets'], list)
            or len(proof['assets']) > 5000 or proof['assets'] != sorted(set(proof['assets']))
            or any(not isinstance(v, str) or re.fullmatch(r'[A-Za-z0-9_-]{43}', v) is None for v in [proof['launch'], *proof['assets']])):
        raise ValueError('invalid artifact proof')


def validate_manifest(payload, update_id, proof):
    validate_proof(proof)
    if (re.fullmatch(UUID, update_id) is None or not isinstance(payload, dict)
            or payload.get('id') != update_id or payload.get('runtimeVersion') != RUNTIME
            or payload.get('extra', {}).get('eas', {}).get('projectId') != PROJECT
            or payload.get('launchAsset', {}).get('hash') != proof['launch']
            or not isinstance(payload.get('assets'), list)
            or sorted(set(item.get('hash') for item in payload['assets'])) != proof['assets']):
        raise ValueError('published manifest differs from claimed bytes')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--artifact', type=Path)
    args = parser.parse_args()
    try:
        if not sys.flags.isolated:
            raise ValueError('isolated interpreter required')
        root = Path(__file__).resolve().parents[1]
        validate_source(root, args.sha)
        if args.artifact:
            proof = artifact(args.artifact)
            validate_proof(proof)
            print(json.dumps({'sha': args.sha, 'project': PROJECT, 'runtime': RUNTIME, 'platform': 'ios', 'channel': CHANNEL, 'artifact': proof}, sort_keys=True))
    except Exception:
        print('OTA source/artifact validation failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
