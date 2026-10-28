"""Inspect the actual Store IPA without executing it or fully unpacking it.

Only the main Mach-O is written to a private temporary directory for codesign.

This supplements static Expo configuration checks; it is not a signature or
hardware acceptance check. Callers must independently bind the expected digest
to the trusted build receipt and obtain candidate-specific risk acceptance.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import re
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

# Narrow admission for the independently reviewed GPS candidate. A new source
# requires fresh native-scope review, even if its configuration looks similar.
REVIEWED_JOURNEY_SOURCE = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
REVIEWED_JOURNEY_SOURCES = frozenset({
    REVIEWED_JOURNEY_SOURCE,
    '83876750fcbb404255b7439482688fee82a490d4',
    'ae7a5972921ee9d51eec2c90c7893e6941d2d7ff',
})


def inspect_ipa(path: Path, expected_sha256: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('invalid IPA digest')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha256:
            raise ValueError('IPA digest does not match build receipt')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or len(names) > 50000:
                raise ValueError('duplicate or excessive IPA entries')
            if sum(entry.file_size for entry in entries) > 2_000_000_000:
                raise ValueError('excessive expanded IPA size')
            for entry in entries:
                parts = PurePosixPath(entry.filename).parts
                if (entry.filename.startswith('/') or '..' in parts
                        or '\\' in entry.filename
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('unsafe IPA entry')
                if 'PlugIns' in parts or 'Watch' in parts or any(p.endswith('.appex') for p in parts):
                    raise ValueError('unreviewed embedded application or extension')
                if any(p.endswith('.app') and (index != 1 or parts[0] != 'Payload')
                       for index, p in enumerate(parts)):
                    raise ValueError('unreviewed nested application')
            roots = {PurePosixPath(name).parts[1] for name in names
                     if len(PurePosixPath(name).parts) >= 2
                     and PurePosixPath(name).parts[0] == 'Payload'
                     and PurePosixPath(name).parts[1].endswith('.app')}
            if len(roots) != 1:
                raise ValueError('IPA must contain exactly one main application')
            main = f'Payload/{next(iter(roots))}/Info.plist'
            entry = archive.getinfo(main)
            if entry.file_size > 1_000_000:
                raise ValueError('oversized application plist')
            plist = plistlib.loads(archive.read(entry))
            if not isinstance(plist, dict):
                raise ValueError('application plist must be a dictionary')
            return plist


def validate_capabilities(plist: dict, *, journey_usage: tuple[str, str] | None,
                          gps_risk_accepted: bool) -> list[str]:
    failures = []
    for key in ('NSLocationAlwaysUsageDescription', 'NSBluetoothAlwaysUsageDescription',
                'NSBluetoothPeripheralUsageDescription', 'NSSiriUsageDescription',
                'RokidCXRAuthCallbackScheme'):
        if key in plist:
            failures.append(f'unreviewed actual IPA capability: {key}')
    modes = plist.get('UIBackgroundModes', [])
    always = plist.get('NSLocationAlwaysAndWhenInUseUsageDescription')
    if modes or always is not None:
        if modes != ['location']:
            failures.append('actual IPA background modes must be exactly location')
        if not journey_usage or len(journey_usage) != 2:
            failures.append('background location requires reviewed frozen-source dailyJourney configuration')
        elif (plist.get('NSLocationWhenInUseUsageDescription'), always) != journey_usage:
            failures.append('actual IPA location usage differs from reviewed frozen source')
        if gps_risk_accepted is not True:
            failures.append('background location requires candidate-specific GPS risk acceptance')
    elif not isinstance(modes, list):
        failures.append('invalid background modes type')
    return failures


def inspect_entitlements(path: Path, expected_sha256: str) -> dict:
    """Read signed Mach-O entitlements with Apple's tool; never launch the binary."""
    plist = inspect_ipa(path, expected_sha256)
    executable = plist.get('CFBundleExecutable')
    if not isinstance(executable, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', executable):
        raise ValueError('invalid main executable')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha256:
            raise ValueError('IPA changed before signature inspection')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            main = next(n for n in archive.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', n))
            binary = archive.getinfo(main.removesuffix('Info.plist') + executable)
            if binary.file_size > 500_000_000:
                raise ValueError('oversized executable')
            with tempfile.TemporaryDirectory(prefix='reva-store-entitlements-') as directory:
                target = Path(directory) / 'binary'
                target.write_bytes(archive.read(binary))
                target.chmod(0o600)
                result = subprocess.run(['/usr/bin/codesign', '--display', '--entitlements', '-', '--xml', str(target)],
                                        capture_output=True, check=True, timeout=30)
    entitlements = plistlib.loads(result.stdout)
    if not isinstance(entitlements, dict):
        raise ValueError('invalid signed entitlements')
    return entitlements


def validate_entitlements(entitlements: dict, team_id: str) -> list[str]:
    expected = {
        'application-identifier': f'{team_id}.life.executor.health',
        'aps-environment': 'production', 'beta-reports-active': True,
        'com.apple.developer.associated-domains': ['applinks:health.executor.life'],
        'com.apple.developer.healthkit': True,
        'com.apple.developer.team-identifier': team_id, 'get-task-allow': False,
    }
    if not re.fullmatch(r'[A-Z0-9]{10}', team_id):
        return ['invalid reviewed signing team']
    if set(entitlements) != set(expected) or any(
        type(entitlements[k]) is not type(v) or entitlements[k] != v for k, v in expected.items()
    ):
        return ['actual signed entitlements differ from reviewed production scope']
    return []


def validate_store_artifact(ipa: Path, receipt_path: Path, evidence_path: Path,
                            *, root: Path, build_id: str, eas_build_id: str,
                            source_sha: str) -> list[str]:
    """Bind observed build receipt, acceptance and actual bytes at final submission."""
    try:
        receipt = json.loads(receipt_path.read_text())['native']
        evidence = json.loads(evidence_path.read_text())
        candidate = evidence['candidate']
        if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
            raise ValueError('invalid frozen source revision')
        expected = {'source_sha': source_sha, 'build': build_id, 'eas_build_id': eas_build_id}
        if receipt.get('kind') != 'IOS_STORE' or any(receipt.get(k) != v for k, v in expected.items()):
            raise ValueError('native build receipt does not match submission candidate')
        if (candidate.get('build_profile') != 'production'
                or candidate.get('git_commit_hash') != source_sha or candidate.get('build_id') != build_id
                or candidate.get('eas_build_id') != eas_build_id
                or candidate.get('ipa_sha256') != receipt.get('ipa_sha256')
                or candidate.get('app_version') != receipt.get('version')):
            raise ValueError('acceptance evidence does not match native receipt')
        plist = inspect_ipa(ipa, receipt['ipa_sha256'])
        for key, value in {'CFBundleIdentifier': 'life.executor.health',
                           'CFBundleVersion': build_id,
                           'CFBundleShortVersionString': receipt['version'],
                           'UIDeviceFamily': [1],
                           'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait'],
                           'ITSAppUsesNonExemptEncryption': False}.items():
            if type(plist.get(key)) is not type(value) or plist.get(key) != value:
                raise ValueError(f'actual IPA identity or scope mismatch: {key}')
        if (int(plist.get('DTXcode', '0')) < 2600
                or int(str(plist.get('DTPlatformVersion', '0')).split('.')[0]) < 26):
            raise ValueError('actual IPA uses unsupported Store toolchain')
        if (plist.get('DTXcode') != candidate.get('dtxcode')
                or plist.get('DTPlatformVersion') != candidate.get('dtplatform_version')
                or any(type(value) is not int for value in plist['UIDeviceFamily'])):
            raise ValueError('actual IPA platform evidence mismatch')
        config = subprocess.run(['git', 'show', f'{source_sha}:mobile/app.config.ts'],
                                cwd=root, capture_output=True, text=True, check=True, timeout=10).stdout
        usage = None
        if (source_sha in REVIEWED_JOURNEY_SOURCES
                and "const DAILY_JOURNEY_RUNTIME = '1.3.6';" in config and receipt['version'] == '1.3.6'
                and 'const dailyJourney = config.version === DAILY_JOURNEY_RUNTIME' in config
                and 'isIosBackgroundLocationEnabled: dailyJourney' in config):
            values = [re.search(r"const " + key + r" = '([^']+)';", config)
                      for key in ('JOURNEY_LOCATION_USAGE', 'JOURNEY_BACKGROUND_USAGE')]
            if all(values):
                usage = tuple(match.group(1) for match in values)
        risk = evidence.get('gps_risk_acceptance', {})
        accepted = (risk.get('accepted') is True and bool(risk.get('accepted_by'))
                    and bool(risk.get('reference')) and risk.get('candidate') == candidate
                    and risk.get('unverified_checks') == ['locked_screen_continuity', 'battery_consumption', 'background_recovery'])
        failures = validate_capabilities(plist, journey_usage=usage, gps_risk_accepted=accepted)
        failures.extend(validate_entitlements(inspect_entitlements(ipa, receipt['ipa_sha256']), receipt.get('signing_team_id', '')))
        return failures
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile,
            plistlib.InvalidFileException, subprocess.SubprocessError):
        return ['actual Store IPA evidence validation failed; inspect candidate artifacts and receipt']
