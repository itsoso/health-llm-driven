"""Real history reads retain provenance and exact recoverable duplicate content."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services import history_compaction as hc
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_history_budget import apply_provider_history_references

LONG_ANSWER = ('既往记录仅供回顾，不能视作本轮医嘱。\n'
               '复查时间是 2026-10-18；青霉素过敏；曾出现胸痛，应及时就医。\n' * 70)
COMPLETE_META = {"client_turn_finalized": True, "finish_reason": "stop",
                 "completion_status": "complete", "turn_outcome": {"status": "complete"}}


def seed(db, auth_user_and_headers, bodies, metas=None):
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id, title="synthetic history budget")
    db.add(conv)
    db.flush()
    rows = []
    for i, (role, content) in enumerate(bodies):
        row = AgentMessage(conversation_id=conv.id, role=role, content=content,
            created_at=datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=i),
            meta=deepcopy(metas[i] if metas else COMPLETE_META if role == 'assistant' else {}))
        db.add(row)
        rows.append(row)
    db.commit()
    return AgentConversationService(db), conv, rows


def test_build_messages_compacts_only_exact_older_answer_repeats(db, auth_user_and_headers, monkeypatch, record_property):
    bodies = [('user', '请回顾'), ('assistant', LONG_ANSWER), ('user', '再回顾'),
              ('assistant', LONG_ANSWER), ('user', '继续'), ('assistant', '最近答复和未完成的追问？'),
              ('user', '按你前面说的日期呢？')]
    svc, conv, rows = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', False)
    baseline = svc.build_messages(conv.id)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    original = svc.build_messages(conv.id)
    assert original == baseline  # Pi and last-six-message consumers stay exact.
    result = apply_provider_history_references(original, svc.provider_history_references)
    assert original == baseline
    assert len(result) == len(baseline)
    assert result[1] == baseline[1]
    assert LONG_ANSWER not in result[3]['content']
    assert f'消息编号：{rows[1].id}' in result[3]['content']
    assert f'消息编号：{rows[3].id}' in result[3]['content']
    assert '正文完全相同' in result[3]['content']
    assert '不代表再次执行' in result[3]['content']
    assert result[-2:] == baseline[-2:]
    assert all(result[i] == baseline[i] for i, (role, _) in enumerate(bodies) if role == 'user')
    assert sum(len(m['content']) for m in result) < sum(len(m['content']) for m in baseline) * 0.65
    assert rows[3].content == LONG_ANSWER
    for name, messages in [('before', baseline), ('after', result)]:
        record_property(name + '_chars', sum(len(m['content']) for m in messages))
        record_property(name + '_utf8_bytes', sum(len(m['content'].encode()) for m in messages))


@pytest.mark.parametrize('protected', [
    {}, {**COMPLETE_META, 'write_receipts': [{'id': 71, 'verified': True}]},
    {**COMPLETE_META, 'pending_write_intent_ids': [8]},
    {**COMPLETE_META, 'pending_choice': {'question': '先做哪项？'}},
    {**COMPLETE_META, 'read_task': {'queries': []}},
    {**COMPLETE_META, 'turn_outcome': {'status': 'waiting_for_user'}},
    {**COMPLETE_META, 'client_turn_finalized': False},
    {**COMPLETE_META, 'garmin_sync_job': None},
])
def test_protected_or_unknown_state_is_not_compacted(db, auth_user_and_headers, monkeypatch, protected):
    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', LONG_ANSWER), ('user', '三'), ('assistant', '追问？'), ('user', '是')]
    metas = [{}, COMPLETE_META, {}, protected, {}, COMPLETE_META, {}]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies, metas)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    result = svc.build_messages(conv.id)
    assert LONG_ANSWER in result[3]['content']
    assert svc.provider_history_references == ()


def test_nonidentical_long_history_overflows_without_truncation(db, auth_user_and_headers, monkeypatch, caplog):
    bodies = [('user', '我对青霉素过敏，还有胸痛' + '背景' * 9000),
              ('assistant', LONG_ANSWER), ('user', '继续' + '补充' * 9000)]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    with caplog.at_level('INFO'):
        result = svc.build_messages(conv.id)
    assert result[0]['content'].endswith(bodies[0][1])
    assert result[1]['content'].endswith(LONG_ANSWER)
    assert result[2]['content'] == bodies[2][1]
    assert 'history_budget' in caplog.text and 'overflow=1' in caplog.text
    assert bodies[0][1] not in caplog.text and LONG_ANSWER not in caplog.text


def test_smaller_window_bridges_valid_fold_without_losing_intermediate_turns(db, auth_user_and_headers, monkeypatch):
    bodies = [('user' if i % 2 == 0 else 'assistant', f'original-{i}') for i in range(21)]
    svc, conv, rows = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(hc.settings, 'llm_history_compaction', True)
    monkeypatch.setattr(hc, '_cache_get', lambda cid: {'folded_thru_id': rows[4].id, 'summary': '旧窗口摘要',
        'folded_prefix_sha256': hc._prefix_fingerprint(rows[:5])})
    result = svc.build_messages(conv.id, limit=6)
    assert '旧窗口摘要' in result[0]['content']
    assert f'消息编号：{rows[4].id}' in result[0]['content']
    assert len(result) == 17
    assert [m['content'].partition('\n')[2] for m in result[1:-1]] == [f'original-{i}' for i in range(5, 20)]
    assert result[-1]['content'] == 'original-20'


def test_foreign_fold_boundary_never_attaches_summary(db, auth_user_and_headers, monkeypatch):
    svc, conv, _ = seed(db, auth_user_and_headers, [('user', str(i)) for i in range(20)])
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(hc.settings, 'llm_history_compaction', True)
    monkeypatch.setattr(hc, '_cache_get', lambda cid: {'folded_thru_id': 9999999, 'summary': 'FOREIGN'})
    result = svc.build_messages(conv.id, limit=6)
    assert all('FOREIGN' not in m['content'] for m in result)


def test_last_assistant_and_changed_number_are_never_referenced(db, auth_user_and_headers, monkeypatch):
    changed = LONG_ANSWER.replace('2026-10-18', '2026-10-19')
    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', changed), ('user', '三'), ('assistant', LONG_ANSWER), ('user', '继续')]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    result = svc.build_messages(conv.id)
    assert result[3]['content'].endswith(changed)
    assert result[5]['content'].endswith(LONG_ANSWER)


def test_duplicate_source_outside_selected_window_is_not_referenced(db, auth_user_and_headers, monkeypatch):
    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', LONG_ANSWER), ('user', '三'), ('assistant', '最近'), ('user', '继续')]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(hc.settings, 'llm_history_compaction', False)
    result = svc.build_messages(conv.id, limit=4)
    assert result[0]['content'].endswith(LONG_ANSWER)
    assert '正文完全相同' not in result[0]['content']


def test_sanitized_history_neither_references_raw_text_nor_reads_fold(db, auth_user_and_headers, monkeypatch):
    from dataclasses import replace
    from app.services.health_evidence import delivery

    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', LONG_ANSWER), ('user', '三'), ('assistant', '最近'), ('user', '继续')]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    original_project = delivery.project_persisted_health_messages
    def project(rows):
        return tuple(replace(p, content='旧答已失效', sanitized=True) if p.role == 'assistant' else p
                     for p in original_project(rows))
    monkeypatch.setattr(delivery, 'project_persisted_health_messages', project)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(hc.settings, 'llm_history_compaction', True)
    def forbidden_cache(cid):
        pytest.fail('Sanitized overflow must never reuse an old fold')
    monkeypatch.setattr(hc, '_cache_get', forbidden_cache)
    result = svc.build_messages(conv.id, limit=4)
    assert all(LONG_ANSWER not in m['content'] for m in result)
    assert result[0]['content'].endswith('旧答已失效')


def test_flag_off_preserves_exact_window_fold_requirement(db, auth_user_and_headers, monkeypatch):
    bodies = [('user' if i % 2 == 0 else 'assistant', f'original-{i}') for i in range(21)]
    svc, conv, rows = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', False)
    monkeypatch.setattr(hc.settings, 'llm_history_compaction', True)
    monkeypatch.setattr(hc, '_cache_get', lambda cid: {'folded_thru_id': rows[4].id, 'summary': 'OLD'})
    result = svc.build_messages(conv.id, limit=6)
    assert len(result) == 6
    assert all('OLD' not in m['content'] for m in result)


@pytest.mark.parametrize('mutation', ['remove_source', 'reorder', 'source_user', 'changed_source', 'tool_call'])
def test_transport_rechecks_source_presence_order_and_roles(db, auth_user_and_headers, monkeypatch, mutation):
    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', LONG_ANSWER), ('user', '三'), ('assistant', '最近'), ('user', '继续')]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    messages = svc.build_messages(conv.id)
    assert len(svc.provider_history_references) == 1
    target = messages[3]
    if mutation == 'remove_source':
        messages.pop(1)
    elif mutation == 'reorder':
        messages[1], messages[3] = messages[3], messages[1]
    elif mutation == 'source_user':
        messages[1] = {**messages[1], 'role': 'user'}
    elif mutation == 'changed_source':
        messages[1] = {**messages[1], 'content': messages[1]['content'] + 'changed'}
    else:
        target['tool_calls'] = [{'id': 'c1'}]
    assert apply_provider_history_references(messages, svc.provider_history_references) == messages


def test_another_conversation_clears_prepared_references(db, auth_user_and_headers, monkeypatch):
    bodies = [('user', '一'), ('assistant', LONG_ANSWER), ('user', '二'),
              ('assistant', LONG_ANSWER), ('user', '三'), ('assistant', '最近'), ('user', '继续')]
    svc, conv, _ = seed(db, auth_user_and_headers, bodies)
    monkeypatch.setattr(hc.settings, 'domain_prompt_optimization', True)
    svc.build_messages(conv.id)
    assert svc.provider_history_references
    _, other, _ = seed(db, auth_user_and_headers, [('user', '独立会话')])
    assert svc.build_messages(other.id) == [{'role': 'user', 'content': '独立会话'}]
    assert svc.provider_history_references == ()
