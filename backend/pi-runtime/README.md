# Reva official Pi runtime

This private Node package runs the official `@earendil-works/pi-agent-core`
`Agent` (0.85.1). Pi owns conversation state, the model/tool loop, schema
validation, sequential tool execution, turn stopping and cancellation. Python
remains the only model transport and tool executor. This package adds no
filesystem, shell, browser, network or credential tools. The neutral Pi model
descriptor is metadata only and never selects a provider.

Requirements: Node >=22.19.0. Install the committed exact dependency graph with
`bash install.sh` in this directory; run `npm test` and `npm audit` here.
The installer checks the host Node version, installs with the committed lockfile
using `npm ci --omit=dev --ignore-scripts`, then checks exact installed Pi versions
and official API imports. Missing or old Node/npm fails deployment;
the installer never provisions global runtimes or OS packages.
Start one process per execution with `node index.mjs`; Node sessions are never
shared or persisted. The Python parent supplies a minimal environment without
credentials, imposes a wall-clock timeout, and terminates/reaps the child when
the caller disconnects. Installing this package does not deploy it.

## JSONL protocol

Input/output carry private JSON objects, one per line. No diagnostic payloads are
printed. A frame may not exceed 8 MiB. Only one RPC is outstanding; IDs are
monotonically increasing decimal strings and must match exactly.

1. Python sends `{type: "start", messages, tools, max_turns}`. Messages use OpenAI
   system/user/assistant/tool format; system messages must precede the transcript,
   which must end in a user or tool result. User content may contain text and
   base64 PNG/JPEG/WebP/GIF data URLs. Remote URLs and unsupported message types
   fail explicitly. Function tools declare object parameter schemas and unique
   names. `max_turns` is an integer from 1 through 128.
2. Pi emits `{type: "model_request", id, messages, tools}`. Python replies with
   `{type: "model_response", id, content, tool_calls, finish_reason}`. Content is a
   string, calls are an OpenAI function-call array, and finish reason is `stop`,
   `tool_calls`, `length` or `error`. Tool IDs remain unique throughout the
   session. Calls on `length`/`error` responses are never executed.
3. Pi emits `{type: "tool_request", id, tool_call_id, name, arguments}` only after
   validating the tool and its arguments. Python replies with
   `{type: "tool_response", id, content, is_error, terminate?}`. Content is a
   string; flags are booleans. Tools execute sequentially. Original argument
   strings are preserved in the OpenAI transcript. Pi's optional argument
   coercion is blocked: executed arguments must exactly match the model's
   original parsed object and Python's approved checkpoint.
4. `terminate: true` finalizes the current result and aborts Pi's sequential batch
   **before any sibling tool runs**, then produces normal `done`. Python supplies
   any deterministic user-facing terminal message.
5. Pi emits `{type: "done", messages, content, finish_reason, turns}` and exits 0.
   `finish_reason` is `stop`, `length` or `error`. Provider errors are completed
   protocol exchanges with error status, not successful output. Reaching the cap
   while tools request continuation produces `length` after current results have
   settled. A final text answer at the cap still produces `stop`.

Python can send `{type: "cancel"}` at any time. Cancellation, premature input EOF,
malformed input, mismatched/unsolicited replies and runtime failures emit
`{type: "error", code}` and exit 1. Fixed codes contain no frame data:
`CANCELLED`, `INPUT_CLOSED`, `PROTOCOL_ERROR`, `INVALID_START`,
`INVALID_MODEL_RESPONSE`, `INVALID_TOOL_RESPONSE`, `FRAME_TOO_LARGE`,
`RUNTIME_ERROR`. There is no fallback execution loop.

Offline subprocess tests exercise the real installed Pi with scripted replies;
they never contact a model provider or execute health tools. Production
transport, authenticated tenant isolation and write side-effect reconciliation
also require the Python integration tests.
