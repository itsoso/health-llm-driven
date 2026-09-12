/** Official Pi owns the loop. Python owns model credentials and every tool effect. */
import { Agent } from '@earendil-works/pi-agent-core';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';
import { isDeepStrictEqual } from 'node:util';

const MAX_FRAME_BYTES = 8 * 1024 * 1024;
const model = {
  id: 'reva-python-transport', name: 'Reva Python transport', api: 'openai-completions',
  provider: 'reva-local', baseUrl: '', reasoning: false, input: ['text', 'image'],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 1000000, maxTokens: 1000000,
};
const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
function requireValue(condition, code) { if (!condition) throw new Error(code); }
function assistant(content, stopReason = 'stop') {
  return { role: 'assistant', content, api: model.api, provider: model.provider, model: model.id, usage: structuredClone(usage), stopReason, timestamp: Date.now() };
}
function parseCalls(calls, code) {
  requireValue(Array.isArray(calls), code);
  const ids = new Set();
  return calls.map((call) => {
    requireValue(object(call) && call.type === 'function' && typeof call.id === 'string' && call.id.length > 0 && !ids.has(call.id), code);
    requireValue(object(call.function) && typeof call.function.name === 'string' && call.function.name.length > 0 && typeof call.function.arguments === 'string', code);
    ids.add(call.id);
    let args;
    try { args = JSON.parse(call.function.arguments); } catch { throw new Error(code); }
    requireValue(object(args), code);
    return { type: 'toolCall', id: call.id, name: call.function.name, arguments: args };
  });
}
function importMessages(messages) {
  const systems = [];
  const history = [];
  const knownCalls = new Map();
  for (const message of messages) {
    requireValue(object(message), 'INVALID_START');
    if (message.role === 'system') {
      requireValue(history.length === 0 && typeof message.content === 'string', 'INVALID_START');
      systems.push(message);
      continue;
    }
    let converted;
    if (message.role === 'user') {
      let content = message.content;
      if (Array.isArray(content)) {
        content = content.map((part) => {
          requireValue(object(part), 'INVALID_START');
          if (part.type === 'text') {
            requireValue(typeof part.text === 'string', 'INVALID_START');
            return { type: 'text', text: part.text };
          }
          requireValue(part.type === 'image_url' && object(part.image_url) && typeof part.image_url.url === 'string', 'INVALID_START');
          const match = /^data:(image\/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/]+={0,2})$/.exec(part.image_url.url);
          requireValue(match !== null, 'INVALID_START');
          return { type: 'image', mimeType: match[1], data: match[2] };
        });
      } else requireValue(typeof content === 'string', 'INVALID_START');
      converted = { role: 'user', content, timestamp: Date.now() };
    } else if (message.role === 'assistant') {
      requireValue(message.content == null || typeof message.content === 'string', 'INVALID_START');
      const calls = parseCalls(message.tool_calls ?? [], 'INVALID_START');
      for (const call of calls) {
        requireValue(!knownCalls.has(call.id), 'INVALID_START');
        knownCalls.set(call.id, call.name);
      }
      converted = assistant([...(message.content ? [{ type: 'text', text: message.content }] : []), ...calls], calls.length ? 'toolUse' : 'stop');
    } else if (message.role === 'tool') {
      requireValue(typeof message.content === 'string' && typeof message.tool_call_id === 'string' && knownCalls.has(message.tool_call_id), 'INVALID_START');
      converted = { role: 'toolResult', toolCallId: message.tool_call_id, toolName: knownCalls.get(message.tool_call_id), content: [{ type: 'text', text: message.content }], isError: false, timestamp: Date.now() };
    } else throw new Error('INVALID_START');
    converted.openaiOriginal = structuredClone(message);
    history.push(converted);
  }
  requireValue(history.length > 0 && ['user', 'toolResult'].includes(history.at(-1).role), 'INVALID_START');
  return { systems, history };
}
function exportMessages(systems, messages) {
  return [...systems, ...messages.map((message) => {
    if (message.openaiOriginal) return message.openaiOriginal;
    if (message.role === 'assistant') {
      const calls = message.content.filter((part) => part.type === 'toolCall').map((part) => ({ id: part.id, type: 'function', function: { name: part.name, arguments: JSON.stringify(part.arguments) } }));
      return { role: 'assistant', content: message.content.filter((part) => part.type === 'text').map((part) => part.text).join(''), ...(calls.length ? { tool_calls: calls } : {}) };
    }
    if (message.role === 'toolResult') return { role: 'tool', tool_call_id: message.toolCallId, content: message.content.map((part) => {
      requireValue(part.type === 'text', 'RUNTIME_ERROR');
      return part.text;
    }).join('\n') };
    throw new Error('RUNTIME_ERROR');
  })];
}

let activeAgent;
let started = false;
let terminal = false;
let pending;
let sequence = 0;
let input = Buffer.alloc(0);
function emit(frame) {
  if (!terminal) process.stdout.write(`${JSON.stringify(frame)}\n`);
}
function finish(frame, exitCode) {
  if (terminal) return;
  terminal = true;
  activeAgent?.abort();
  pending?.reject(new Error('CANCELLED'));
  pending = undefined;
  process.stdin.pause();
  process.stdout.write(`${JSON.stringify(frame)}\n`, () => process.exit(exitCode));
}
function fail(code) { finish({ type: 'error', code }, 1); }
function rpc(type, payload) {
  requireValue(!terminal && !pending, 'PROTOCOL_ERROR');
  const id = String(++sequence);
  return new Promise((resolve, reject) => {
    pending = { id, type: type.replace('_request', '_response'), resolve, reject };
    emit({ type, id, ...payload });
  });
}

async function run(frame) {
  requireValue(Array.isArray(frame.messages) && Array.isArray(frame.tools) && Number.isInteger(frame.max_turns) && frame.max_turns > 0 && frame.max_turns <= 128, 'INVALID_START');
  const { systems, history } = importMessages(frame.messages);
  const names = new Set();
  const callIds = new Set(history.flatMap((message) => message.role === 'assistant' ? message.content.filter((part) => part.type === 'toolCall').map((part) => part.id) : []));
  let turns = 0;
  let terminalTool = false;
  let capped = false;
  const tools = frame.tools.map((tool) => {
    requireValue(object(tool) && tool.type === 'function' && object(tool.function), 'INVALID_START');
    const definition = tool.function;
    requireValue(typeof definition.name === 'string' && /^[A-Za-z_][A-Za-z0-9_-]{0,127}$/.test(definition.name) && !names.has(definition.name), 'INVALID_START');
    requireValue(object(definition.parameters) && definition.parameters.type === 'object' && (definition.description === undefined || typeof definition.description === 'string'), 'INVALID_START');
    names.add(definition.name);
    return {
      name: definition.name, label: definition.name, description: definition.description ?? '', parameters: definition.parameters,
      execute: async (toolCallId, args) => {
        requireValue(!terminalTool && !terminal, 'CANCELLED');
        const response = await rpc('tool_request', { tool_call_id: toolCallId, name: definition.name, arguments: args });
        requireValue(typeof response.content === 'string' && typeof response.is_error === 'boolean' && (response.terminate === undefined || typeof response.terminate === 'boolean'), 'INVALID_TOOL_RESPONSE');
        if (response.terminate === true) {
          terminalTool = true;
          // Pi sequential execution checks its abort signal after finalizing this result.
          // The batch termination hint alone would still execute sibling writes.
          activeAgent.abort();
        }
        return { content: [{ type: 'text', text: response.content }], details: { bridgeIsError: response.is_error }, terminate: response.terminate === true };
      },
    };
  });
  activeAgent = new Agent({
    initialState: { systemPrompt: systems.map((m) => m.content).join('\n\n'), messages: history, tools, model },
    toolExecution: 'sequential',
    // Pi permits schema coercion; Reva must execute exactly what its Python checkpoint approved.
    beforeToolCall: async ({ toolCall, args }) => isDeepStrictEqual(toolCall.arguments, args) ? undefined : { block: true, reason: 'INVALID_TOOL_ARGUMENTS' },
    afterToolCall: async ({ result, isError }) => ({ isError: isError || result.details?.bridgeIsError === true }),
    shouldStopAfterTurn: ({ message }) => {
      capped = turns >= frame.max_turns && message.content.some((part) => part.type === 'toolCall') && !terminalTool;
      return terminalTool || capped || message.stopReason === 'length';
    },
    streamFn: () => { throw new Error('RUNTIME_ERROR'); },
  });
  activeAgent.streamFunction = (_model, context) => {
    const stream = createAssistantMessageEventStream();
    void (async () => {
      try {
        turns++;
        const response = await rpc('model_request', { messages: exportMessages(systems, context.messages), tools: frame.tools });
        requireValue(typeof response.content === 'string' && ['stop', 'tool_calls', 'length', 'error'].includes(response.finish_reason), 'INVALID_MODEL_RESPONSE');
        const calls = parseCalls(response.tool_calls, 'INVALID_MODEL_RESPONSE');
        for (const call of calls) {
          requireValue(!callIds.has(call.id), 'INVALID_MODEL_RESPONSE');
          callIds.add(call.id);
        }
        const message = assistant([...(response.content ? [{ type: 'text', text: response.content }] : []), ...calls], ['length', 'error'].includes(response.finish_reason) ? response.finish_reason : calls.length ? 'toolUse' : 'stop');
        message.openaiOriginal = { role: 'assistant', content: response.content, ...(response.tool_calls.length ? { tool_calls: response.tool_calls } : {}) };
        if (message.stopReason === 'error') stream.push({ type: 'error', reason: 'error', error: message });
        else stream.push({ type: 'done', reason: message.stopReason, message });
      } catch (error) {
        fail(error.message === 'INVALID_MODEL_RESPONSE' ? error.message : 'RUNTIME_ERROR');
        const message = assistant([], 'error');
        message.errorMessage = 'RUNTIME_ERROR';
        stream.push({ type: 'error', reason: 'error', error: message });
      }
    })();
    return stream;
  };
  await activeAgent.continue();
  if (terminal) return;
  const lastAssistant = activeAgent.state.messages.findLast((message) => message.role === 'assistant');
  requireValue(lastAssistant && lastAssistant.stopReason !== 'aborted', 'RUNTIME_ERROR');
  finish({ type: 'done', messages: exportMessages(systems, activeAgent.state.messages), content: lastAssistant.content.filter((part) => part.type === 'text').map((part) => part.text).join(''), finish_reason: lastAssistant.stopReason === 'error' ? 'error' : capped || lastAssistant.stopReason === 'length' ? 'length' : 'stop', turns }, 0);
}
function receive(frame) {
  requireValue(object(frame), 'PROTOCOL_ERROR');
  if (frame.type === 'cancel') { fail('CANCELLED'); return; }
  if (!started) {
    requireValue(frame.type === 'start', 'PROTOCOL_ERROR');
    started = true;
    void run(frame).catch((error) => fail(error.message === 'INVALID_START' ? 'INVALID_START' : 'RUNTIME_ERROR'));
    return;
  }
  requireValue(pending && frame.id === pending.id && frame.type === pending.type, 'PROTOCOL_ERROR');
  const request = pending;
  pending = undefined;
  // Reject malformed results here, before Pi can treat an exception as a normal tool failure.
  if (frame.type === 'tool_response' && !(typeof frame.content === 'string' && typeof frame.is_error === 'boolean' && (frame.terminate === undefined || typeof frame.terminate === 'boolean'))) {
    request.reject(new Error('INVALID_TOOL_RESPONSE'));
    fail('INVALID_TOOL_RESPONSE');
    return;
  }
  request.resolve(frame);
}
process.stdin.on('data', (chunk) => {
  if (terminal) return;
  input = Buffer.concat([input, chunk]);
  if (input.length > MAX_FRAME_BYTES) { fail('FRAME_TOO_LARGE'); return; }
  let newline;
  while (!terminal && (newline = input.indexOf(10)) >= 0) {
    const line = input.subarray(0, newline);
    input = input.subarray(newline + 1);
    try { receive(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(line))); }
    catch { fail('PROTOCOL_ERROR'); }
  }
});
process.stdin.on('end', () => { if (!terminal) fail('INPUT_CLOSED'); });
process.stdin.on('error', () => fail('INPUT_CLOSED'));
process.stdout.on('error', () => process.exit(1));
process.on('SIGTERM', () => fail('CANCELLED'));
process.on('SIGINT', () => fail('CANCELLED'));
