"""Error surfaces must not invent a failed health task or expose internals."""
import pytest
from app.services.llm.error_messages import safe_llm_error_message

@pytest.mark.parametrize('error', [RuntimeError('internal synthetic-private-detail'), RuntimeError('timeout'), RuntimeError('429'), RuntimeError('insufficient_quota')])
def test_failure_copy_is_task_neutral_and_private(error):
    message = safe_llm_error_message(error)
    assert '健康建议' not in message
    assert 'synthetic-private-detail' not in message
    assert '重试' in message

def test_unknown_failure_does_not_claim_provider_outage():
    assert safe_llm_error_message(RuntimeError('pi_tool_response_missing')) == '本轮回答未能完成，请稍后重试。'

def test_failure_site_does_not_include_exception_text_or_frame_locals():
    from app.services.llm.error_messages import safe_error_site
    namespace = {'__name__': 'app.services.synthetic_incident'}
    exec(compile("def fail():\n private = 'synthetic-health-and-secret'\n raise RuntimeError(private)\n", '/private/synthetic-secret.py', 'exec'), namespace)
    try:
        namespace['fail']()
    except RuntimeError as error:
        assert safe_error_site(error) == 'app.services.synthetic_incident:3'
    assert safe_error_site(RuntimeError('synthetic-health-and-secret')) == 'unknown'
