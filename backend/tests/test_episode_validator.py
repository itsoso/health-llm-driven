from app.services.episode.protocol_registry import ProtocolAction
from app.services.episode.validator import validate_actions, validate_text


def test_validate_text_blocks_blacklist_and_replaces_output():
    result = validate_text("请给我一个处方，并调整降压药剂量 mg/kg")
    assert result.ok is False
    assert result.action == "replace"
    assert "超出我作为健康助理的安全边界" in result.safe_text
    assert result.disclaimer


def test_validate_text_appends_disclaimer_for_graylist_terms():
    result = validate_text("这个补剂可能有什么副作用？")
    assert result.ok is True
    assert result.action == "append_disclaimer"
    assert result.disclaimer
    assert result.safe_text.endswith(result.disclaimer)


def test_validate_actions_sets_disclaimer_for_graylist_keyword():
    actions = [
        ProtocolAction(
            template_id="test.action",
            action_type="intervention",
            title="关注副作用",
        )
    ]
    result = validate_actions(actions)
    assert result.ok is True
    assert result.disclaimer
