import hashlib
import json
import plistlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_store_ipa_capabilities import inspect_ipa, validate_capabilities, validate_entitlements


def test_reads_actual_plist_and_binds_digest(tmp_path):
    path = tmp_path / 'candidate.ipa'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Payload/app.app/Info.plist', plistlib.dumps({'CFBundleVersion': '279'}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert inspect_ipa(path, digest)['CFBundleVersion'] == '279'
    with pytest.raises(ValueError, match='digest'):
        inspect_ipa(path, '0' * 64)


@pytest.mark.parametrize('extra', ['Payload/other.app/Info.plist', 'Payload/app.app/Other.app/Info.plist', 'Payload/app.app/PlugIns/hidden.appex/Info.plist', 'Payload/app.app/Watch/hidden.app/Info.plist', '../escape'])
def test_hidden_or_ambiguous_package_rejected(tmp_path, extra):
    path = tmp_path / 'candidate.ipa'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Payload/app.app/Info.plist', plistlib.dumps({}))
        archive.writestr(extra, plistlib.dumps({}))
    with pytest.raises(ValueError):
        inspect_ipa(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_background_location_requires_exact_risk_and_source_usage():
    plist = {'UIBackgroundModes': ['location'], 'NSLocationAlwaysAndWhenInUseUsageDescription': 'explicit daily opt in', 'NSLocationWhenInUseUsageDescription': 'foreground'}
    assert validate_capabilities(plist, journey_usage=('foreground', 'explicit daily opt in'), gps_risk_accepted=True) == []
    assert validate_capabilities(plist, journey_usage=None, gps_risk_accepted=True)
    assert validate_capabilities(plist, journey_usage=('foreground', 'explicit daily opt in'), gps_risk_accepted=False)
    for modes in (['location', 'audio'], ['location', 'location'], 'location'):
        assert validate_capabilities(dict(plist, UIBackgroundModes=modes), journey_usage=('foreground', 'explicit daily opt in'), gps_risk_accepted=True)
    assert validate_capabilities(dict(plist, NSBluetoothAlwaysUsageDescription='hidden'), journey_usage=('foreground', 'explicit daily opt in'), gps_risk_accepted=True)


def test_no_background_does_not_allow_always_permission():
    assert validate_capabilities({'NSLocationAlwaysAndWhenInUseUsageDescription': 'hidden'}, journey_usage=None, gps_risk_accepted=False)


def test_entitlements_reject_extra_capability_and_boolean_coercion():
    values = {'application-identifier': 'ABCDEFGHIJ.life.executor.health',
              'aps-environment': 'production', 'beta-reports-active': True,
              'com.apple.developer.associated-domains': ['applinks:health.executor.life'],
              'com.apple.developer.healthkit': True,
              'com.apple.developer.team-identifier': 'ABCDEFGHIJ', 'get-task-allow': False}
    assert validate_entitlements(values, 'ABCDEFGHIJ') == []
    assert validate_entitlements(dict(values, **{'com.apple.developer.siri': True}), 'ABCDEFGHIJ')
    assert validate_entitlements(dict(values, **{'get-task-allow': 0}), 'ABCDEFGHIJ')
    assert validate_entitlements(values, 'OTHERTEAM1')


@pytest.mark.parametrize('mutation', ['none', 'source', 'eas', 'digest', 'team', 'risk', 'platform', 'family'])
def test_candidate_binding_end_to_end(tmp_path, monkeypatch, mutation):
    import scripts.check_store_ipa_capabilities as gate
    source = gate.REVIEWED_JOURNEY_SOURCE
    plist = {'CFBundleIdentifier': 'life.executor.health', 'CFBundleVersion': '279',
             'CFBundleShortVersionString': '1.3.6', 'UIDeviceFamily': [1],
             'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait'],
             'ITSAppUsesNonExemptEncryption': False, 'DTXcode': '2660', 'DTPlatformVersion': '26.5',
             'UIBackgroundModes': ['location'], 'NSLocationWhenInUseUsageDescription': 'foreground',
             'NSLocationAlwaysAndWhenInUseUsageDescription': 'daily opt in'}
    if mutation == 'family':
        plist['UIDeviceFamily'] = [True]
    ipa = tmp_path / 'test.ipa'
    with zipfile.ZipFile(ipa, 'w') as archive:
        archive.writestr('Payload/app.app/Info.plist', plistlib.dumps(plist))
    digest = hashlib.sha256(ipa.read_bytes()).hexdigest()
    candidate = {'git_commit_hash': source, 'build_id': '279', 'eas_build_id': 'eas-test',
                 'ipa_sha256': digest, 'app_version': '1.3.6', 'build_profile': 'production',
                 'dtxcode': '2660', 'dtplatform_version': '26.5'}
    native = {'kind': 'IOS_STORE', 'source_sha': source, 'build': '279', 'version': '1.3.6',
              'eas_build_id': 'eas-test', 'ipa_sha256': digest, 'signing_team_id': 'ABCDEFGHIJ'}
    risk = {'accepted': True, 'accepted_by': 'synthetic tester', 'reference': 'synthetic test authorization',
            'candidate': dict(candidate), 'unverified_checks': ['locked_screen_continuity', 'battery_consumption', 'background_recovery']}
    if mutation == 'source': native['source_sha'] = '0' * 40
    if mutation == 'eas': candidate['eas_build_id'] = 'other'
    if mutation == 'digest': native['ipa_sha256'] = candidate['ipa_sha256'] = '0' * 64
    if mutation == 'team': native['signing_team_id'] = 'OTHERTEAM1'
    if mutation == 'risk': risk['accepted'] = False
    if mutation == 'platform': candidate['dtxcode'] = '2600'
    receipt = tmp_path / 'receipt.json'; receipt.write_text(json.dumps({'native': native}))
    evidence = tmp_path / 'evidence.json'; evidence.write_text(json.dumps({'candidate': candidate, 'gps_risk_acceptance': risk}))
    config = "const DAILY_JOURNEY_RUNTIME = '1.3.6';\nconst dailyJourney = config.version === DAILY_JOURNEY_RUNTIME;\nisIosBackgroundLocationEnabled: dailyJourney;\nconst JOURNEY_LOCATION_USAGE = 'foreground';\nconst JOURNEY_BACKGROUND_USAGE = 'daily opt in';"
    monkeypatch.setattr(gate.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout=config))
    monkeypatch.setattr(gate, 'inspect_entitlements', lambda *a: {
        'application-identifier': 'ABCDEFGHIJ.life.executor.health', 'aps-environment': 'production',
        'beta-reports-active': True, 'com.apple.developer.associated-domains': ['applinks:health.executor.life'],
        'com.apple.developer.healthkit': True, 'com.apple.developer.team-identifier': 'ABCDEFGHIJ', 'get-task-allow': False})
    failures = gate.validate_store_artifact(ipa, receipt, evidence, root=tmp_path,
                                          build_id='279', eas_build_id='eas-test', source_sha=source)
    assert bool(failures) is (mutation != 'none')


def test_final_submit_requires_actual_ipa():
    import os
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith('APP_STORE_')}
    result = subprocess.run([sys.executable, str(root / 'scripts/check_app_store_release_pack.py'), '--final-submit'],
                            cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert 'final submit requires actual --ipa' in result.stderr
