"""HTML presentation cannot split assertions or supply hidden negations."""
import pytest

from app.services.guidance_validator import _medical_assertion_matching_text


@pytest.mark.parametrize("html,expected", [
    ("<p>你的蛋白质摄入<strong>不足</strong>。</p>", "你的蛋白质摄入不足。"),
    ("<p>你的蛋白质摄入&#19981;&#36275;。</p>", "你的蛋白质摄入不足。"),
    ("<p>不能确认</p><p>你的恢复状态良好。</p>", "不能确认\n\n你的恢复状态良好。"),
    ("<p>你的蛋白质摄入<!--仅为排版-->不足。</p>", "你的蛋白质摄入不足。"),
    ("<p>如果数值 &lt; 5，先核实单位。</p>", "如果数值 < 5,先核实单位。"),
])
def test_shared_matching_view_resolves_inline_html_entities_and_boundaries(html, expected):
    assert _medical_assertion_matching_text(html).strip() == expected


def test_safe_html_output_is_preserved_byte_for_byte():
    from app.services.agent_composed_read_completion import enforce_composed_synthesis_boundaries
    from types import SimpleNamespace

    html = "<p>不能仅凭记录确认你的恢复状态<strong>良好</strong>。</p>"
    completion = SimpleNamespace(complete=True, verified_evidence={"queries": [
        {"query": {"dimension": "diet"}}, {"query": {"dimension": "sleep"}},
    ]})
    result = enforce_composed_synthesis_boundaries(html, completion)
    assert not result.flagged
    assert result.text == html


@pytest.mark.parametrize("html", [
    '<p style="display:none;display:block">你的蛋白质摄入不足。</p>',
    '<p><span hidden>无法确认</span>你的蛋白质摄入不足。</p>',
    '<style>.neg{display:none}</style><p><span class="neg">无法确认</span>你的蛋白质摄入不足。</p>',
    '<p style="visibility:hidden"><span style="visibility:visible">你的蛋白质摄入不足。</span></p>',
    '<p style="display:none-block">你的蛋白质摄入不足。</p>',
    '<head><title>报告</title><body>你的蛋白质摄入不足。</body>',
])
def test_nonsemantic_html_cannot_supply_visibility_or_hidden_negation(html):
    from app.services.agent_composed_read_completion import enforce_composed_synthesis_boundaries
    from types import SimpleNamespace

    completion = SimpleNamespace(complete=True, trusted_fact_summary="已核验记录。",
        verified_evidence={"queries": [{"query": {"dimension": "diet"}}]})
    result = enforce_composed_synthesis_boundaries(html, completion, require_advice_boundary=True)
    assert result.flagged
    assert html not in result.text
