import json
from pathlib import Path

import pytest

from scripts.check_app_store_release_pack import REAL_DEVICE_CHECKS
from scripts.check_simulator_review_acceptance import validate_simulator_acceptance

SHA = 'a' * 40
EAS = '11111111-1111-4111-8111-111111111111'


def evidence():
    return {
        'candidate': {'build_id': '271', 'app_version': '1.3.3', 'eas_build_id': EAS,
                      'git_commit_hash': SHA, 'build_profile': 'production',
                      'dtxcode': '2620', 'dtplatform_version': '26.2'},
        'simulator': {'source_sha': SHA, 'configuration': 'Release', 'build_id': '1',
                      'device': 'iPhone simulator', 'ios_version': '26.5'},
        'tested_at': '2026-09-10T09:00:00Z', 'tester': 'QA',
        'risk_acceptance': {'accepted': True, 'accepted_by': 'release owner',
                            'reference': 'Explicit user authorization in release thread'},
        'checks': {name: {'status': 'passed', 'evidence': 'capture.png'} if name in {
            'demo_account_login', 'today_context_open_dismiss', 'personal_center_privacy_policy'
        } else {'status': 'unverified', 'reason': 'Not covered by this simulator run'}
                   for name in REAL_DEVICE_CHECKS},
        'accepted_unverified_checks': [name for name in REAL_DEVICE_CHECKS if name not in {
            'demo_account_login', 'today_context_open_dismiss', 'personal_center_privacy_policy'}],
    }


def validate(tmp_path, payload, consent=True):
    path=tmp_path/'acceptance.json'
    path.write_text(json.dumps(payload))
    return validate_simulator_acceptance(path, required_checks=REAL_DEVICE_CHECKS,
        expected_build_id='271', expected_app_version='1.3.3', expected_eas_build_id=EAS,
        expected_git_commit_hash=SHA, accept_risk=consent)


def test_simulator_accepts_explicit_matching_risk_record(tmp_path):
    assert validate(tmp_path, evidence()) == []


@pytest.mark.parametrize('mutation', ['consent','identity','source','debug','failed','missing','reason','ack','core','boolean','approval','sdk','xcode'])
def test_simulator_fails_closed(tmp_path, mutation):
    payload=evidence()
    if mutation=='identity': payload['candidate']['build_id']='270'
    if mutation=='source': payload['simulator']['source_sha']='b'*40
    if mutation=='debug': payload['simulator']['configuration']='Debug'
    if mutation=='failed': payload['checks']['wechat_share_handoff']['status']='failed'
    if mutation=='missing': del payload['checks']['wechat_share_handoff']
    if mutation=='reason': payload['checks']['wechat_share_handoff']['reason']=''
    if mutation=='ack': payload['accepted_unverified_checks']=[]
    if mutation=='core': payload['checks']['demo_account_login']={'status':'unverified','reason':'missing'}
    if mutation=='boolean': payload['checks']['demo_account_login']=True
    if mutation=='approval': payload['risk_acceptance']['accepted']=False
    if mutation=='sdk': payload['candidate']['dtplatform_version']='25.0'
    if mutation=='xcode': payload['candidate']['dtxcode']='2500'
    assert validate(tmp_path,payload,consent=mutation!='consent')


@pytest.mark.parametrize('payload', [None, [], {'checks': []}])
def test_malformed_evidence_returns_failure(tmp_path, payload):
    assert validate(tmp_path,payload)
