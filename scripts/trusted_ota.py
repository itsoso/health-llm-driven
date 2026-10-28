"""Fixed production/iOS OTA contract shared by isolated publisher and server.

No credential reads, mutable CLI selection, URL inputs, or publication here.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = '911ea84f-bc7e-4a12-90cf-33966b6f7398'
RUNTIME = '1.3.6'
CHANNEL = 'production'
NATIVE_SHA = 'ae7a5972921ee9d51eec2c90c7893e6941d2d7ff'
NATIVE_BUILD = 'ea1dda2a-86b3-4e46-adf8-b2b024465154'
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


# Historical 279/280 source exceptions remain byte-pinned for direct contract
# tests. Source admission is now anchored at delivered Store build 283, so any
# future change to these paths still requires the exact reviewed bytes.
REVIEWED_NATIVE_SOURCE = {
    "mobile/package-lock.json": "67d904e88b8281dd80b4d5557ae3abb8d2ad84da0db939b1ca6c701b938128ff",
    "mobile/package.json": "bb79d63ae1df54f0fd72a66084e2ddb76e16debbcfdb2b6f78ff4d34721c2e47",
    "mobile/patches/README.md": "6f29d7e280799a8b087c9acdeaaec111ef8557cbecfac22ab74ff6dd1e4a2e26",
    "mobile/patches/expo++@expo+cli+55.0.33.patch": "44d57d89a089b7208c542b1039ff4d4fa98f6d8f2300bedc61ff60d84412f3bb",
    "mobile/patches/zod+4.6.6.patch": "33390b357702fb46b88d6b66fdd60f4bcb02c086d81584f067a1e8db1ef10c84",
    "mobile/scripts/security-dependency-compat.node.cjs": "4f1be9b511770eea3af2cc7e08ec6b39252531c84727cd9d350fb6fcb6d97689"
}

# Historical 281/282 branding inputs remain byte-pinned. Build 283 is the
# current native source baseline and contains the reviewed guardian icon.
REVIEWED_BRANDING_SOURCE = {
    "mobile/app.json": "3541b8c2c6c0e1812da8e54e7b2907f802dde01b2e3e0e502156d11442998506",
    "mobile/app.config.ts": "8c20bce465bb7af015e9f9fb3960dbfa7d812765453fba1e20003b4471c5e787",
    "mobile/assets/images/icon.png": "5277b77a0271f0c0dea3de5eae662e7ba95c669072fb666ebc6420dc726ecddf",
    "mobile/assets/images/splash-icon.png": "e63daad1a321f01a85e2e218382eeebd7046810410fc9deb52b15bd2ae8b32a3",
    "mobile/assets/images/adaptive-icon.png": "5277b77a0271f0c0dea3de5eae662e7ba95c669072fb666ebc6420dc726ecddf",
    "mobile/assets/images/favicon.png": "82d0e7466c6c841f58295f24d79b6c82c03a9d3d53abdeb88620ad940b92eb32",
    "mobile/plugins/withWatchApp.js": "a11578c1f5c1a79faa4d48168f83ba7c1cf9e066d3dc28bfb38b1380e78a27ff",
    "mobile/plugins/withIntentsExtension.js": "077af163629ae5994428b0969be1a6b52e3e4fd03ca5e9781577154c09e965c2",
    "mobile/plugins/__tests__/withWatchApp.test.js": "cb5df3b4071d7f766dcc6ff629d4cd58af09f24cd88c65ad39bae3c4324d25f2",
    "mobile/modules/rokid-bridge/__tests__/rokidBridge.test.ts": "1c3e48bf17d810ca53fc07a96aa8e8c314a6d9728cc68f6aaed5b82691f3d586",
    "mobile/scripts/__tests__/parser-security.test.js": "44506c591e87653cf7682cbd135ae32fa29ec747c980d3d7740c63f0f1d183dd",
    "mobile/strings/zh.ts": "d56a37332d467540ad0c97bdafeb142e681c1167e6e70d126ab1203c84ed3689",
    "mobile/PRODUCT_MAP.md": "c237dcc6039ca4a0235b42f65f5ed8c4b5b4f440e536ec9a30c091f16d9fe435"
}

def validate_production_environment():
    if os.environ.get('APP_VARIANT', 'production') != 'production' or any(
            os.environ.get(key, '') not in ('', '0') for key in (
                'REVA_IPAD_ENABLED', 'ROKID_IOS_SDK_ENABLED', 'INCLUDE_WATCH_APP',
                'INCLUDE_SIRI_INTENTS', 'REVA_ANDROID_INTERNAL')):
        raise ValueError('native or unknown mobile input changed')


def validate_runtime_changes(paths, *, root=None):
    validate_production_environment()
    # A conservative OTA boundary. Anything outside known JS source/test or
    # asset directories requires a reviewed native baseline update.
    prefixes = ('mobile/app/', 'mobile/components/', 'mobile/hooks/', 'mobile/services/',
                'mobile/types/', 'mobile/constants/', 'mobile/stores/', 'mobile/utils/',
                'mobile/contexts/', 'mobile/lib/', 'mobile/applib/', 'mobile/__tests__/', 'packages/shared/src/')
    reviewed = {**REVIEWED_NATIVE_SOURCE, **REVIEWED_BRANDING_SOURCE}
    for path in paths:
        if path in reviewed:
            if root is None:
                raise ValueError('native or unknown mobile input changed')
            native = Path(root) / path
            if (any(parent.is_symlink() for parent in (native, *native.parents))
                    or not native.is_file()
                    or hashlib.sha256(native.read_bytes()).hexdigest() != reviewed[path]):
                raise ValueError('native or unknown mobile input changed')
            continue
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
    validate_runtime_changes(changed, root=root)
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
