"""Synthetic complete stored imaging narrative, without calendar guessing."""
import json
import pytest
from datetime import date
from app.models.medical_exam import MedicalExam
from app.services.agent_kernel.medical_narrative_read_scope import MedicalNarrativeReadScope
from app.services.health_read import read_owned_imaging_reports


def test_full_older_imaging_assessment_is_not_truncated(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    text='左膝MRI合成报告。'+'合成观察；'*150+'末尾完整结论。'
    expected=MedicalExam(user_id=user.id,exam_date=date(2020,1,1),exam_type='mri',overall_assessment=text)
    db.add(expected)
    db.add(MedicalExam(user_id=user.id,exam_date=date(2026,10,10),exam_type='mri',overall_assessment='左膝MRI未来报告'))
    db.add(MedicalExam(user_id=user.id,exam_date=date(2026,1,1),exam_type='mri',overall_assessment='右膝MRI其他侧'))
    db.commit()
    result=json.loads(read_owned_imaging_reports(db,user.id,MedicalNarrativeReadScope('左膝'),reference_date=date(2026,10,9)))
    assert result['availability']=='available'
    assert [r['id'] for r in result['reports']]==[expected.id]
    assert result['reports'][0]['overall_assessment']==text
    assert json.loads(read_owned_imaging_reports(db,user.id+999,MedicalNarrativeReadScope('左膝'),reference_date=date(2026,10,9)))['availability']=='no_data'


def test_over_budget_narrative_is_explicitly_unavailable_not_cut(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    db.add(MedicalExam(user_id=user.id,exam_date=date(2026,1,1),exam_type='mri',overall_assessment='膝MRI'+'合成'*12000));db.commit()
    result=json.loads(read_owned_imaging_reports(db,user.id,MedicalNarrativeReadScope('膝'),reference_date=date(2026,10,9)))
    assert result['availability']=='requires_selection'
    assert result['reports']==[]
    assert result['reason_code']=='imaging_narrative_over_budget'


def test_imaging_gateway_binds_anatomy_and_blocks_extra_scope():
    from app.services.agent_kernel.types import AgentEnvelope,ExecutionContext,TurnSnapshot,ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    e=AgentEnvelope(user_id=41,channel='chat',text='查看我的左膝MRI报告')
    c=ExecutionContext.for_test(user_id=41,channel='chat');s=TurnSnapshot(e,c,build_intent_frame(e,c))
    for tool,args in [('health_query',{'dimension':'medical_exam'}),('health_manage',{'record_type':'medical_exam','operation':'list'})]:
        result=decide_tool_capability(s,ToolExecutionRequest(tool,args))
        assert result.action=='allow'
        assert result.normalized_tool_name=='health_query'
        assert result.normalized_args=={'dimension':'medical_exam','keyword':'左膝'}
    for args in ({'dimension':'medical_exam','keyword':'右膝'}, {'dimension':'medical_exam','days':365}, {'dimension':'sleep'}, {'dimension':'medical_exam','user_id':99}):
        assert decide_tool_capability(s,ToolExecutionRequest('health_query',args)).action=='block'
    assert decide_tool_capability(s,ToolExecutionRequest('health_analysis',{'analysis_type':'comprehensive'})).action=='block'


def test_selected_report_evidence_provenance_is_server_owned(db,auth_user_and_headers):
    from app.services.health_read import read_selected_medical_exam
    user,_=auth_user_and_headers
    exam=MedicalExam(user_id=user.id,exam_date=date(2026,10,1),exam_type='mri',overall_assessment='合成影像记录')
    db.add(exam);db.commit()
    payload=json.loads(read_selected_medical_exam(db,user.id,exam.id,reference_date=date(2026,10,9)))
    assert payload['original_image_verified'] is False
    assert 'OCR' in payload['evidence_note']
    assert '原始影像' in payload['evidence_note']


@pytest.mark.parametrize('keyword', ['右膝', '膝', '肩关节CT', '同事的肩关节MRI', '肩关节MRI以及睡眠', '肩 2020', '双肩;删除报告'])
def test_keyword_normalization_cannot_expand_user_scope(keyword):
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    envelope = AgentEnvelope(user_id=41, channel='chat', text='查看我的左肩MRI报告')
    context = ExecutionContext.for_test(user_id=41, channel='chat')
    snapshot = TurnSnapshot(envelope, context, build_intent_frame(envelope, context))
    assert decide_tool_capability(snapshot, ToolExecutionRequest('health_query', {'dimension': 'medical_exam', 'keyword': keyword})).action == 'block'


def test_noncanonical_model_keyword_still_cannot_bypass_gateway():
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    envelope = AgentEnvelope(user_id=41, channel='chat', text='我的双肩关节现在有什么样的状况？医院有没有做过核磁共振？诊断结果是怎么样的？')
    context = ExecutionContext.for_test(user_id=41, channel='chat')
    snapshot = TurnSnapshot(envelope, context, build_intent_frame(envelope, context))
    decision = decide_tool_capability(snapshot, ToolExecutionRequest('health_query', {'dimension': 'medical_exam', 'keyword': '双肩关节核磁共振'}))
    assert decision.action == 'block'
    assert decision.reason == 'imaging_narrative_scope_conflict'
