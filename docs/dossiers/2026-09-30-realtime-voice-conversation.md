# Realtime voice conversation

| Field | Value |
| --- | --- |
| 状态 | G4 passed; G5 PR opened |
| 当前阶段 | G5 merge CI gate |
| Controller | product-pipeline |
| Delegate | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 requirement admission

裁决: PASS

- 用户明确要求执行类似 ChatGPT 的实时语音对话改造。
- 首个可交付切片限定为 Mobile `/voice-chat`：复用现有云端实时 ASR，最终转写只提交一次，插话时同时终止本地流和服务端 Agent Run。
- 保留现有 Agent Kernel、健康写入确认和医疗安全边界；本切片不引入 speech-to-speech 直连，不让语音绕过现有工具与确认链。
- 映射到 Mobile Capture / Chat、`ExecutionEvent` 和既有 `WriteIntent`。自主等级保持 `manual_confirm`。
- 麦克风必须由用户显式触发；原始 PCM 仅存在于当前内存会话，不记录、不持久化。

## G2 definition

裁决: PASS

- Feature spec: `docs/specs/active/2026-09-30-realtime-voice-conversation.md`
- PRD: `docs/prd/2026-09-30-realtime-voice-conversation.md`
- Plan: `docs/plans/2026-09-30-realtime-voice-conversation.md`
- 已核对现有 `/chat/transcribe/realtime`、`/agent/stream`、Agent Runtime cancel API、语音 Hook 及邻近测试。
- 不新增数据库、健康数据模型或外部提供商；无需迁移。

## Phase 2 admission and definition

裁决: G1 PASS / G2 PASS

- 用户明确要求继续第二阶段；范围限定为 Agent token 流之后的低延迟语音输出。
- 后端新增同源鉴权的 TTS WebSocket，会话内把文本增量送入现有 DashScope
  CosyVoice，并只回传内存中的 24 kHz mono PCM；不记录文本或音频载荷。
- Mobile 新增本地 PCM 播放模块，收到首个音频分片即可播放，插话时同步停止
  播放、取消 TTS WebSocket 和既有 Agent Run，再打开麦克风。
- 继续保持半双工。当前录音模块使用独占 `.record` session，本阶段不宣称具备
  AEC、边播边录或真正 full-duplex。
- Agent Kernel、工具调用、健康写入确认、AI consent 与 owner isolation 均保持
  权威；不引入 speech-to-speech 捷径。
- 这是原生能力变化，需要新的 iOS 构建，不能通过 OTA 冒充交付。

## G3 evidence

### Phase 2

- RED: Mobile service/source tests failed because `cloudStreamingTts` and the
  `RevaPcmPlayer` Swift source did not exist. Backend protocol collection failed
  because `app.services.realtime_tts` did not exist.
- Focused Mobile: 4 suites, 27 passed, exit 0. Covers authenticated WebSocket
  construction, PCM enqueue/drain, idempotent cancellation, phrase-before-done
  streaming, barge-in ordering, realtime ASR regression, and native source contract.
- Full Mobile: 326 suites, 3,214 passed, one existing skip, exit 0.
- TypeScript: `npx tsc --noEmit --pretty false`, exit 0. Targeted ESLint for all
  touched/new TS files returned no warnings or errors. Repository lint returned
  0 errors and the same 123 pre-existing warnings.
- Backend TTS/ASR/privacy contract: 26 passed, exit 0. Covers bounded text,
  PCM ordering, finish/cancel semantics, route registration, bearer parsing,
  consent-before-provider creation, existing TTS normalization, and ASR regression.
- Expo autolinking discovered both `RevaPcmPlayer` and `RevaPcmStream`; CocoaPods
  installed the new local pod. The dedicated `RevaPcmPlayer` target compiled for
  arm64 iOS Simulator with Xcode 26.6: `BUILD SUCCEEDED`.
- The device-specific Debug full-App build completed successfully for the booted
  iPhone 17 Pro simulator with `SENTRY_DISABLE_AUTO_UPLOAD=true`; the flag only
  bypassed missing local Sentry organization configuration and did not skip native
  compilation or linkage. The resulting `life.executor.health.preview` app installed
  and launched successfully. Runtime voice-provider/authenticated end-to-end testing
  still requires a configured development server and credentials.
- System Map was regenerated from the combined dirty tree and then passed canonical
  graph, mobile navigation, doc drift, and governance checks. `git diff --check` passed.

### Phase 1

- Mobile RED: the focused run failed because voice-chat still loaded Apple
  Speech, `request_persisted` discarded `run_id`, and no Mobile cancel helper
  existed; 51 neighboring assertions remained green.
- Backend RED: `test_agent_stream_passes_canonical_identity_to_executor`
  failed with `KeyError: run_id`, proving the ordinary persisted event did not
  yet expose the runtime identity needed for direct interruption.
- Final focused Mobile: 4 suites, 75 passed, exit 0. Covers partial-only display,
  authoritative final submission, single-submit semantics, server-backed
  barge-in, cancellation failure fail-closed behavior, consent/reset/unmount
  cleanup, and interruption during async voice-style loading.
- Final full Mobile: 324 suites, 3,208 passed, one existing skip, exit 0.
- TypeScript: `npx tsc --noEmit --pretty false`, exit 0.
- Mobile lint: exit 0 with 123 pre-existing warnings and no errors; no warning
  was reported in a touched file except the existing `voice-chat.tsx` warnings.
- Backend ASR/runtime contract: 13 passed, exit 0. Covers early canonical run
  identity, queued/running/cross-owner cancellation, and realtime speech proxy
  helpers. An initial environmentless invocation attempted localhost Postgres
  and was rejected; the successful run explicitly used isolated in-memory
  SQLite, appropriate here because no database behavior changed.
- System Map, mobile navigation, doc drift, skill governance, secret scan, and
  `git diff --check` passed.
- Global dossier consistency remains blocked by the unrelated pre-existing
  `2026-09-29-prompt-history-medication-clarification.md` malformed dossier;
  this dossier was not named by that failure.

## G4 / G5 / G6

- 用户于 2026-10-01 指示“继续按规划往下执行”，已授权创建仅包含本功能的
  本地固定 commit 并进入独立 safety review；审查完成前不宣称 G4 通过。
- 用户随后明确授权提交、合并 `main` 和部署；采用隔离 voice-only PR，避免把原
  工作区 `main` 中夹带的其他未发布提交带入发布。
- G6 生产路径未验证，不得以本地测试替代。

### G4 initial safety review and remediation

- 固定提交 `135249a5c` 的首次独立 safety review 裁决为 **NO-GO**：默认
  Agent Runtime 关闭时缺少可取消 run identity；TTS 下游发送失败可能造成 relay
  与有界队列互锁；PCM 缺少字节级会话上限和播放高低水位回压。
- 已补齐 owner-scoped 本地 run/turn 注册、状态查询与取消；跨 owner 请求返回 404。
  Mobile 在非终态且仍无 `run_id` 时 fail closed，不会打开竞争麦克风；仅在请求尚未
  发出（voice-style preflight）时允许纯本地中断。
- TTS bridge 现在限制单分片 256 KiB、总 PCM 180 秒、绝对会话时限和 provider
  cleanup；下游断开会传播失败并取消 provider，stop/relay 同轮完成竞态有回归覆盖。
- iOS PCM player 同步实施 256 KiB 单分片、180 秒会话上限，以及 8 秒/4 秒
  high/low-water promise backpressure；stop 会拒绝所有等待中的 enqueue。
- 修复后验证：后端相关 75 passed（含真实 WebSocket 未认证、已认证且已同意、
  未同意握手路径）；Mobile 全量 326 suites / 3,215 passed / 1
  existing skip；`npx tsc --noEmit` 与定向 ESLint 通过；`RevaPcmPlayer` arm64
  iOS Simulator target `BUILD SUCCEEDED`。
- 修复固定提交：`226e0f779`（基于 Phase 2 提交 `135249a5c`）。新的独立
  reviewer 已对这两个精确提交完成只读复核并给出 **`G4 verdict: GO`**：三个原
  blocker 均已解除，未发现新的 Critical/High 阻断问题。因此 G4 裁决为 PASS。
- reviewer 记录的非阻断风险：mode-off registry 为进程内状态，多 worker 落到
  不同进程时会安全 fail closed 但插话可能不可用；极端 provider callback burst
  仍需压测/监控；Simulator 构建不能替代真机 AudioSession、蓝牙/来电中断与性能。
- G5 前仍需真实凭据/真实后端端到端验证首包、思考中/播放中插话、断网/慢客户端、
  授权撤回和后台切换，并确认取消后旧 Agent 不再工具写入或继续播报。

### G5 release preparation

- 发布准备开始时 `origin/main` 为 `fb0165f7d`；原工作区 `main` 除本功能三个提交外还领先
  6 个其他功能提交和 1 个 merge commit，并带有与本功能无关的未提交修改，不能
  将其整体作为本功能发布候选直接推送。
- 已从 `origin/main` 创建隔离 worktree，并仅 cherry-pick 本功能三个提交；得到
  voice-only 候选 `5691092e9`（前序为 `40f888933`、`c9568dd97`），无冲突且
  工作树干净，证明本功能不依赖前述其他本地提交。
- 候选验证：后端相关测试 75 passed；Mobile 全量 324 suites / 3,190 passed /
  1 existing skip；`npx tsc --noEmit`、System Map、`git diff --check`、密钥扫描
  和 Skill 治理均通过。候选套件数少于原工作区，是因为隔离候选未包含其他本地
  功能及其测试。
- voice-only 候选已推送并创建 PR #263。首轮 CI 在实现测试前被新披露的依赖
  安全公告阻断：Mobile `axios 1.18.1`，后端 `urllib3 2.7.0` 与
  `PyJWT 2.14.0`。同期合入 `main` 的安全 PR #261 已将它们升级到经审查的
  `axios 1.20.0`、`urllib3 2.8.0`、`PyJWT 2.15.0`；语音候选已改以该
  `c4e27dad2` 主干为基线，不重复覆盖安全修复。
- 依赖修复验证：Mobile OSV / npm audit 和后端 pip-audit 均通过，后端语音与
  依赖契约 80 passed，干净 `npm ci` 后 TypeScript、解析器安全、实时 TTS 和
  原生播放器契约均通过。首轮 Mobile 全量在补跑 postinstall 前仅两个解析器
  用例失败，补跑后定向用例通过；第二次全量执行因 Jest 异步句柄未退出而人工
  终止，最终以 PR 的干净 CI 运行作为合并裁决。
- 当前断点：PR #263 的最新主干基线 CI 必须全部通过；合入后还必须等待精确
  `main` revision 的 CI 绿色才能部署。该原生 iOS 变化不符合 OTA 边界，后续
  只能走新的原生构建；真实凭据端到端场景仍未完成。
