"""A denied media proposal cannot turn a static document request into a write."""
import json
import pytest
from app.services.agent_executor import AgentExecutor

HTML_PROMPT='帮我制定未来十天的锻炼计划，最终生成一个HTML页面。'
DOCUMENT='```html\n<!DOCTYPE html><html><head><title>合成计划</title></head><body><h1>一般活动建议</h1><p>如不适请停止并就医。</p></body></html>\n```'

@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['document','ordinary','extra_write','repeat_tool','plain_text','existing_failure','model_error','unsafe_document','attachment_boundary','read_only'])
async def test_static_html_recovery_is_bounded_and_never_dispatches(db, auth_user_and_headers, monkeypatch, case):
    user,_=auth_user_and_headers
    executor=AgentExecutor(db)
    calls=[]
    async def dispatch(*args,**kwargs):
        pytest.fail('denied media or write must never dispatch')
    monkeypatch.setattr(executor,'_dispatch_tool_request',dispatch)
    async def stream(messages,tools):
        calls.append(tools)
        if len(calls)==1 or case=='repeat_tool':
            if case=='attachment_boundary':
                executor._current_turn_has_attachment = True
            if case=='existing_failure':
                executor._agent_kernel_tool_failure_tools.append('knowledge_search')
            proposed=[{'id':'media','type':'function','function':{'name':'draft_aigc_media','arguments':json.dumps({'prompt':'synthetic document'})}}]
            if case=='extra_write':
                proposed.append({'id':'write','type':'function','function':{'name':'health_record','arguments':json.dumps({'record_type':'exercise','data':{}})}})
            yield {'type':'tool_calls','tool_calls':proposed}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':(DOCUMENT.replace('</body>', '<script>synthetic()</script></body>') if case=='unsafe_document' else DOCUMENT if case in {'document','model_error','read_only'} else '这不是完整HTML文档。')}
            yield {'type':'finish','finish_reason':'error' if case=='model_error' else 'stop'}
    monkeypatch.setattr(executor,'_call_llm_stream',stream)
    events=[e async for e in executor.run_stream(user_id=user.id,channel='typed',message=HTML_PROMPT if case!='ordinary' else '帮我制定未来十天的锻炼计划', read_only_tools=case=='read_only')]
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert len(calls)==(1 if case in {'ordinary','extra_write','existing_failure','attachment_boundary'} else 2)
    if len(calls)==2: assert calls[1]==[]
    assert (done['turn_outcome']['status']=='complete')==(case in {'document','read_only'})
    assert not done.get('write_receipts')
    if case=='document':
        from app.models.agent_conversation import AgentMessage
        saved = db.get(AgentMessage,done['message_id'])
        assert DOCUMENT in saved.content
        user_turn = db.query(AgentMessage).filter_by(conversation_id=saved.conversation_id,role='user').one()
        operations = list(user_turn.meta['write_operations'].values())
        assert operations and all(item['status']=='rejected' for item in operations)
        assert all(item['tool']=='draft_aigc_media' for item in operations)
