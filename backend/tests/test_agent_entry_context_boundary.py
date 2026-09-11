import pytest
from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor

@pytest.mark.asyncio
@pytest.mark.parametrize('query,context,candidate,forbidden', [
 ('给我建议', '用户从补剂页进入，正在查看鱼油与剂量。', '建议把鱼油增加到每天四粒。', '增加到每天四粒'),
 ('你好，聊聊今天', None, '建议每天服用布洛芬两片。', '服用布洛芬两片'),
 ('查看今天的步数', None, '建议把鱼油增加到每天四粒。', '增加到每天四粒'),
 ('查看今天的步数', None, '<tool_response>INTERNAL_SENTINEL</tool_response>', '<tool_response>'),
])
async def test_untrusted_text_never_reaches_client_before_final_gate(db, auth_user_and_headers, monkeypatch,query,context,candidate,forbidden):
 user,_=auth_user_and_headers
 executor=AgentExecutor(db)
 monkeypatch.setattr(executor,'_build_system_prompt',lambda *_a,**_k:'合成测试上下文。')
 monkeypatch.setattr(executor,'_build_system_knowledge_prompt_context',lambda *_a,**_k:'')
 async def stream(messages,tools):
  yield {'type':'content','text':candidate}
  yield {'type':'finish','finish_reason':'stop'}
 async def completion(messages,tools):
  return {'content':candidate,'finish_reason':'stop'}
 monkeypatch.setattr(executor,'_call_llm_stream',stream)
 monkeypatch.setattr(executor,'_call_llm',completion)
 events=[e async for e in executor.run_stream(user_id=user.id,message=query,extra_context=context,channel='typed')]
 done=next(e['data'] for e in reversed(events) if e['event']=='done')
 saved=db.get(AgentMessage,done['message_id'])
 assert forbidden not in saved.content
 streamed=''.join(e['data'].get('content','') for e in events if e.get('event')=='token')
 assert forbidden not in streamed, f'Already released: {streamed!r}'

 # Removing protocol text must not relabel the attempt as a completed answer.
 if candidate.startswith('<tool_response>'):
  assert done['completion_status'] == 'error'
  assert done['turn_outcome']['status'] == 'failed'
  assert 'protocol_leak' in saved.meta['output_quality_flags']
 else:
  assert done['turn_outcome']['status'] == 'blocked'
  assert done['turn_outcome']['category'] == 'medical_evidence_required'
