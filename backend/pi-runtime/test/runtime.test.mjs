import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { test } from 'node:test';

const entry = new URL('../index.mjs', import.meta.url);
const tool = { type: 'function', function: { name: 'record', description: 'Record a synthetic value', parameters: { type: 'object', properties: { value: { type: 'integer' } }, required: ['value'], additionalProperties: false } } };
const call = (id, args = '{"value":7}') => ({ id, type: 'function', function: { name: 'record', arguments: args } });
const start = (extra = {}) => ({ type: 'start', messages: [{ role: 'system', content: 'Synthetic test only' }, { role: 'user', content: 'hello' }], tools: [tool], max_turns: 4, ...extra });

async function run(initial, reply) {
  const child = spawn(process.execPath, [entry.pathname], { stdio: ['pipe', 'pipe', 'pipe'], env: { PATH: process.env.PATH } });
  const frames = [];
  let stderr = '';
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  child.stdin.on('error', () => {}); // A rejected frame may close input before its sender finishes.
  const timer = setTimeout(() => child.kill('SIGKILL'), 8000);
  const reader = createInterface({ input: child.stdout });
  const processing = (async () => {
    for await (const line of reader) {
      const frame = JSON.parse(line);
      frames.push(frame);
      const response = reply?.(frame, frames);
      if (response === 'EOF') child.stdin.end();
      else if (response) child.stdin.write(`${JSON.stringify(response)}\n`);
    }
  })();
  const result = new Promise((resolve) => child.once('close', (code, signal) => resolve({ code, signal })));
  child.stdin.write(`${JSON.stringify(initial)}\n`);
  const exit = await result;
  clearTimeout(timer);
  await processing;
  assert.equal(stderr, '', 'health payloads and frames must never enter stderr');
  assert.equal(exit.signal, null, 'runtime must settle without timeout');
  return { frames, code: exit.code };
}
const modelResponse = (request, tool_calls = [], content = '') => ({ type: 'model_response', id: request.id, content, tool_calls, finish_reason: tool_calls.length ? 'tool_calls' : 'stop' });

test('official Pi owns model -> sequential tools -> model and preserves IDs and arguments', async () => {
  let requests = 0;
  const args = '{ "value": 7 }';
  const result = await run(start(), (frame) => {
    if (frame.type === 'model_request') {
      requests++;
      if (requests === 1) return modelResponse(frame, [call('write-1', args), call('write-2')]);
      assert.deepEqual(frame.messages.at(-3).tool_calls, [call('write-1', args), call('write-2')]);
      assert.deepEqual(frame.messages.slice(-2).map((m) => m.tool_call_id), ['write-1', 'write-2']);
      return modelResponse(frame, [], 'complete');
    }
    if (frame.type === 'tool_request') return { type: 'tool_response', id: frame.id, content: 'recorded', is_error: false };
  });
  assert.equal(result.code, 0);
  assert.deepEqual(result.frames.map((f) => f.type), ['model_request', 'tool_request', 'tool_request', 'model_request', 'done']);
  assert.deepEqual(result.frames.filter((f) => f.type === 'tool_request').map((f) => f.arguments), [{ value: 7 }, { value: 7 }]);
  assert.equal(result.frames.at(-1).content, 'complete');
  assert.equal(result.frames.at(-1).turns, 2);
});

test('user image data URLs and history tool IDs survive conversion', async () => {
  const messages = [
    { role: 'system', content: 'Synthetic' },
    { role: 'user', content: [{ type: 'text', text: 'image' }, { type: 'image_url', image_url: { url: 'data:image/png;base64,aGVsbG8=', detail: 'high' } }] },
    { role: 'assistant', content: null, tool_calls: [call('history')] },
    { role: 'tool', tool_call_id: 'history', content: 'old result' },
    { role: 'user', content: 'next' },
  ];
  const result = await run(start({ messages }), (frame) => {
    if (frame.type === 'model_request') {
      assert.deepEqual(frame.messages, messages);
      return modelResponse(frame, [], 'done');
    }
  });
  assert.equal(result.code, 0);
});

for (const [label, args] of [['missing required', '{}'], ['coercible string', '{"value":"7"}'], ['additional property', '{"value":7,"extra":1}']]) {
  test(`invalid tool arguments (${label}) never execute`, async () => {
    let requests = 0;
    const result = await run(start(), (frame) => {
      if (frame.type === 'model_request') return ++requests === 1 ? modelResponse(frame, [call('bad', args)]) : modelResponse(frame, [], 'corrected');
    });
    assert.equal(result.code, 0);
    assert.equal(result.frames.some((f) => f.type === 'tool_request'), false);
    assert.equal(result.frames.at(-1).content, 'corrected');
  });
}

test('terminal result stops sibling tools and further model calls', async () => {
  const result = await run(start(), (frame) => {
    if (frame.type === 'model_request') return modelResponse(frame, [call('first'), call('must-not-run')]);
    if (frame.type === 'tool_request') return { type: 'tool_response', id: frame.id, content: 'awaiting confirmation', is_error: false, terminate: true };
  });
  assert.equal(result.code, 0);
  assert.deepEqual(result.frames.map((f) => f.type), ['model_request', 'tool_request', 'done']);
  assert.equal(result.frames.at(-1).messages.at(-1).content, 'awaiting confirmation');
});

test('max turns caps the official loop after a complete tool result', async () => {
  const result = await run(start({ max_turns: 1 }), (frame) => {
    if (frame.type === 'model_request') return modelResponse(frame, [call('last')]);
    if (frame.type === 'tool_request') return { type: 'tool_response', id: frame.id, content: 'done', is_error: false };
  });
  assert.equal(result.code, 0);
  assert.equal(result.frames.at(-1).finish_reason, 'length');
  assert.equal(result.frames.at(-1).turns, 1);
});

test('length-truncated model responses never execute tools', async () => {
  const result = await run(start(), (frame) => frame.type === 'model_request' ? { ...modelResponse(frame, [call('truncated')]), finish_reason: 'length' } : undefined);
  assert.equal(result.code, 0);
  assert.deepEqual(result.frames.map((f) => f.type), ['model_request', 'done']);
  assert.equal(result.frames.at(-1).finish_reason, 'length');
});

for (const [label, response, code] of [
  ['wrong correlation', (f) => ({ ...modelResponse(f, [], 'SECRET_TEST_VALUE'), id: 'wrong' }), 'PROTOCOL_ERROR'],
  ['input EOF', () => 'EOF', 'INPUT_CLOSED'],
  ['cancellation', () => ({ type: 'cancel' }), 'CANCELLED'],
  ['malformed argument JSON', (f) => modelResponse(f, [call('bad-json', '{')]), 'INVALID_MODEL_RESPONSE'],
]) {
  test(`${label} fails explicitly without hanging or leaking response`, async () => {
    const result = await run(start(), (frame) => frame.type === 'model_request' ? response(frame) : undefined);
    assert.equal(result.code, 1);
    assert.deepEqual(result.frames.at(-1), { type: 'error', code });
    assert.equal(JSON.stringify(result.frames).includes('SECRET_TEST_VALUE'), false);
  });
}

test('unsupported remote image fails before model transport', async () => {
  const result = await run(start({ messages: [{ role: 'user', content: [{ type: 'image_url', image_url: { url: 'https://example.org/private.png' } }] }] }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.frames, [{ type: 'error', code: 'INVALID_START' }]);
});

test('duplicate tool IDs across model turns fail before repeated execution', async () => {
  const result = await run(start(), (frame) => {
    if (frame.type === 'model_request') return modelResponse(frame, [call('same-id')]);
    if (frame.type === 'tool_request') return { type: 'tool_response', id: frame.id, content: 'recorded', is_error: false };
  });
  assert.equal(result.code, 1);
  assert.equal(result.frames.filter((frame) => frame.type === 'tool_request').length, 1);
  assert.deepEqual(result.frames.at(-1), { type: 'error', code: 'INVALID_MODEL_RESPONSE' });
});

test('unknown tool produces an error result without any tool execution', async () => {
  let requests = 0;
  const result = await run(start(), (frame) => {
    if (frame.type === 'model_request') {
      if (++requests === 1) return modelResponse(frame, [{ ...call('unknown'), function: { name: 'not_registered', arguments: '{}' } }]);
      assert.equal(frame.messages.at(-1).role, 'tool');
      return modelResponse(frame, [], 'corrected');
    }
  });
  assert.equal(result.code, 0);
  assert.equal(result.frames.some((frame) => frame.type === 'tool_request'), false);
});

for (const [label, response, code] of [
  ['EOF while executing tool', () => 'EOF', 'INPUT_CLOSED'],
  ['cancel while executing tool', () => ({ type: 'cancel' }), 'CANCELLED'],
  ['malformed tool response', (f) => ({ type: 'tool_response', id: f.id, content: 'SECRET_TEST_VALUE' }), 'INVALID_TOOL_RESPONSE'],
]) {
  test(label, async () => {
    const result = await run(start(), (frame) => {
      if (frame.type === 'model_request') return modelResponse(frame, [call('pending')]);
      if (frame.type === 'tool_request') return response(frame);
    });
    assert.equal(result.code, 1);
    assert.deepEqual(result.frames.at(-1), { type: 'error', code });
    assert.equal(JSON.stringify(result.frames).includes('SECRET_TEST_VALUE'), false);
  });
}

test('error tool result remains available for the next model turn', async () => {
  let requests = 0;
  const result = await run(start(), (frame) => {
    if (frame.type === 'model_request') {
      if (++requests === 1) return modelResponse(frame, [call('error-result')]);
      assert.equal(frame.messages.at(-1).content, 'SAFE_ERROR_CODE');
      return modelResponse(frame, [], 'failed honestly');
    }
    if (frame.type === 'tool_request') return { type: 'tool_response', id: frame.id, content: 'SAFE_ERROR_CODE', is_error: true };
  });
  assert.equal(result.code, 0);
  assert.equal(result.frames.at(-1).content, 'failed honestly');
});

test('explicit provider error never dispatches included tool calls', async () => {
  const result = await run(start(), (frame) => frame.type === 'model_request' ? { ...modelResponse(frame, [call('must-not-run')], 'provider error'), finish_reason: 'error' } : undefined);
  assert.equal(result.code, 0);
  assert.deepEqual(result.frames.map((frame) => frame.type), ['model_request', 'done']);
  assert.equal(result.frames.at(-1).finish_reason, 'error');
});

test('frames exceeding the shared 8 MiB limit fail before model transport', async () => {
  const result = await run(start({ messages: [{ role: 'user', content: 'x'.repeat(8 * 1024 * 1024) }] }));
  assert.equal(result.code, 1);
  assert.deepEqual(result.frames, [{ type: 'error', code: 'FRAME_TOO_LARGE' }]);
});
