"""HTML is a static answer format, never media creation authority."""
import pytest
from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope, exercise_plan_prompt
from app.services.agent_input_tool_scope import scope_tools_for_exercise_plan

BASE = '请为我设计未来14天的运动计划'
HTML = BASE + '，最终生成一个HTML页面。'

@pytest.mark.parametrize('text', [HTML, BASE + '，最后生成一个html页面。',
    '今天是否适合运动？给我推荐适合我的运动方式以及运动强度，最终生成一个HTML页面。'])
def test_closed_html_request_has_static_output_contract(text):
    scope = resolve_exercise_plan_scope(text)
    assert scope is not None
    assert scope.output_format == 'html'
    prompt = exercise_plan_prompt(scope)
    for required in ('```html', '<!DOCTYPE html>', '<html>', '<head>', '<body>',
                     'draft_aigc_media', '脚本', '网络', '保存', '发布'):
        assert required in prompt
    assert '只能使用本轮实际开放的工具' in prompt
    tools = [{'function': {'name': name}} for name in
             ('knowledge_search', 'draft_aigc_media', 'health_record', 'health_query')]
    assert [t['function']['name'] for t in scope_tools_for_exercise_plan(tools,text)] == ['knowledge_search']


def test_plain_exercise_keeps_plain_output_and_existing_scope():
    scope = resolve_exercise_plan_scope(BASE)
    assert scope.output_format == 'text'
    assert '```html' not in exercise_plan_prompt(scope)
    assert scope.evidence_dimensions == ()

@pytest.mark.parametrize('text', ['“'+HTML+'”', '朋友说'+HTML,
    HTML+'发布到网上', HTML+'保存到我的记录',
    BASE+'，最终生成一个HTML页面并执行脚本。',
    '给朋友设计运动计划，最终生成一个HTML页面。'])
def test_unclosed_or_foreign_html_request_has_no_scope(text):
    assert resolve_exercise_plan_scope(text) is None
