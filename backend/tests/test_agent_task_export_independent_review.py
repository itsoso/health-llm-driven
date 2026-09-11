"""Independent synthetic export association counterexamples."""

from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from tests.test_agent_task_export import _export, _owner, _run


def test_same_owner_and_conversation_wrong_turn_assistant_is_not_attributed(db):
    owner = _owner(db, 'review-owner')
    run, _ = _run(db, owner)
    wrong_turn_message = AgentMessage(
        conversation_id=run.conversation_id, role='assistant',
        client_turn_id='turn-43-1789099200000', content='SYNTHETIC-PRIVATE-HEALTH',
        meta={'resolution_status': 'completed', 'perf': {'end_to_end_total_ms': 99}},
    )
    db.add(wrong_turn_message)
    db.flush()
    run.assistant_message_id = wrong_turn_message.id
    exported = _export(db, owner)
    row = exported['snapshots'][0]
    assert row['task_elapsed_ms'] is None
    assert row['resolution_status'] == 'unknown'
    assert exported['assistant_metadata_coverage']['unmatched'] == 1


def test_real_save_message_owner_scoped_storage_key_matches_the_run(db):
    owner = _owner(db, 'review-storage-owner')
    run, _ = _run(db, owner)
    message = AgentConversationService(db).save_message(
        run.conversation_id, 'assistant', 'SYNTHETIC-PRIVATE-HEALTH',
        meta={'perf': {'end_to_end_total_ms': 321}},
        client_turn_id=run.client_turn_id, client_turn_user_id=owner.id,
    )
    assert message.client_turn_id != run.client_turn_id
    run.assistant_message_id = message.id
    exported = _export(db, owner)
    assert exported['snapshots'][0]['task_elapsed_ms'] == 321
    assert exported['assistant_metadata_coverage']['matched'] == 1
