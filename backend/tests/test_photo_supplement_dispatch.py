from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.api import write_intents as api
from app.services import write_intent_service as dispatcher
from app.services import photo_supplement_intake as service
from app.models.supplement import SupplementRecord
from tests.test_photo_supplement_intake import NOW, presented, scenario  # noqa: F401


@pytest.mark.asyncio
async def test_api_confirms_full_supplement_batch(db, scenario, monkeypatch):
    wi = presented(db, scenario)
    monkeypatch.setattr(service, '_clock', lambda: NOW)
    result = await api.confirm_write_intent(wi.id, current_user=SimpleNamespace(id=scenario[0]), db=db)
    assert result['status'] == 'executed'
    assert len(result['write_receipts']) == 4
    assert db.query(SupplementRecord).count() == 4


def test_generic_pending_list_cannot_offer_incomplete_photo_plan(db, scenario):
    wi = presented(db, scenario)
    assert wi.id not in [row['id'] for row in dispatcher.list_pending(db, scenario[0])]


def test_auto_confirmation_is_rejected(db, scenario):
    wi = presented(db, scenario)
    with pytest.raises(ValueError, match='manual'):
        dispatcher.confirm(db, scenario[0], wi.id, trust_tier='auto')
    assert db.query(SupplementRecord).count() == 0


@pytest.mark.asyncio
async def test_api_unpresented_photo_plan_is_conflict(db, scenario, monkeypatch):
    uid, mid, candidates = scenario
    wi = service.propose(db, uid, mid, candidates, now=NOW)
    monkeypatch.setattr(service, '_clock', lambda: NOW)
    with pytest.raises(HTTPException) as exc:
        await api.confirm_write_intent(wi.id, current_user=SimpleNamespace(id=uid), db=db)
    assert exc.value.status_code == 409
    assert db.query(SupplementRecord).count() == 0


@pytest.mark.asyncio
async def test_api_dismiss_projects_terminal_without_writing(db, scenario):
    from app.models.agent_conversation import AgentMessage
    wi = presented(db, scenario)
    result = await api.dismiss_write_intent(wi.id, current_user=SimpleNamespace(id=scenario[0]), db=db)
    assert result['status'] == 'dismissed'
    card = db.query(AgentMessage).filter_by(role='assistant').one().meta['cards'][0]
    assert card['data']['decision_status'] == 'dismissed'
    assert card['actions'] == []
    assert db.query(SupplementRecord).count() == 0
