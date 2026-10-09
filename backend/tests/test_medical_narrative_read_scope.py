"""Synthetic owned imaging questions preserve a bounded report target."""
import pytest

from app.services.agent_kernel.medical_narrative_read_scope import resolve_medical_narrative_read_scope


@pytest.mark.parametrize('text', [
    '我的双肩关节现在有什么样的状况？医院有没有做过核磁共振？诊断结果是怎么样的？',
    '我的左肩现在是什么状况？做过MRI吗？检查结果是什么？',
    '查看我的双肩关节MRI报告',
    '请查看我自己的肩关节磁共振报告。',
])
def test_owned_complete_imaging_request(text):
    scope = resolve_medical_narrative_read_scope(text)
    assert scope is not None
    assert scope.anatomy == ('左肩' if '左肩' in text else '肩')
    assert scope.modality == 'MRI'
    assert scope.query_args() == {'dimension': 'medical_exam', 'keyword': scope.anatomy}


@pytest.mark.parametrize('text', [
    '查看同事的双肩关节MRI报告',
    '查看我的朋友的肩关节MRI报告',
    '不要查看我的双肩关节MRI报告',
    '假如查看我的双肩关节MRI报告',
    '他说“查看我的双肩关节MRI报告”',
    '查看我的双肩关节MRI报告，然后删除它',
    '我的双肩关节现在是什么状况？医院有没有做过MRI？诊断结果是什么？再查她的睡眠',
    '我的双肩关节现在是什么状况？医院有没有做过MRI？诊断结果是什么？帮我开药',
    '查看我的双肩关节MRI和朋友的CT报告',
    '查看我的双肩关节MRI报告，最近三天的',
    '我的肩关节现在是什么状况？医院有没有做过MRI？他的诊断结果是什么？',
])
def test_unknown_or_foreign_scope_has_no_authority(text):
    assert resolve_medical_narrative_read_scope(text) is None
