from app.services import photo_supplement_intake as service
from app.services.atomic_capability_registry import attach_action_policy_metadata, validate_dynamic_view
from app.models.agent_conversation import AgentMessage
from tests.test_photo_supplement_intake import NOW, presented, scenario  # noqa: F401


def test_registered_card_roundtrip_is_confirmable(db, scenario):
    wi = presented(db, scenario)
    assistant = db.query(AgentMessage).filter_by(role='assistant').one()
    card = service.build_card(wi)
    card['actions'] = attach_action_policy_metadata(card['type'], card['actions'])
    assert validate_dynamic_view({'surface': 'mobile.chat', 'sections': [{'cards': [card]}]}) == []
    assert all(a['autonomy_tier'] == 'manual_confirm' for a in card['actions'])
    assistant.meta = {**assistant.meta, 'cards': [card]}
    db.commit()
    assert service.confirm(db, scenario[0], wi.id, now=NOW)['status'] == 'executed'
