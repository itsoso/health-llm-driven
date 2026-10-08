# Realtime voice conversation

| Field | Value |
| --- | --- |
| 状态 | TestFlight 1.3.4 (273) delivered; G5 UI acceptance pending |
| 当前阶段 | Candidate authenticated voice UI acceptance; no App Review submission |
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
- 基于 `c4e27dad2` 的 PR CI 已全部通过，但合并时 `main` 又前进到
  `d3b204f28`，分支保护拒绝旧基线合并；候选已再次重放到最新主干。为避免下一次
  CI 期间同类竞态，更新后的 PR 启用受保护 auto-merge，仍不绕过任何必需检查。

### Client release continuation — 2026-10-01

- 用户已明确授权“发布客户端”及“解决问题然后发布”。PR #263 已合入；后端
  发布修复 PR #267 后，生产已运行 `e8fa94a9f2b23c3523fb48364167ee38dfa4ea5d`。
  本次只发布 iOS Ad Hoc 扫码包，不提交 TestFlight 或 App Store，不覆盖本地 WIP。
- 客户端初始候选 `c6f1eb999fd12708a26daa06695c40006c0064aa` 的远端 CI
  `36835476487` 全部通过；其 Mobile 相对已部署 revision 仅有生成类型差异，
  无新的运行时代码/依赖/原生契约变化。干净 `npm ci`、Mobile 324 suites /
  3,190 passed / 1 existing skip、TypeScript、System Map 通过。
- 现有已授权审核测试账号的真实 provider 探针：TTS 完整 PCM 返回，观察到首包
  0.83 秒；合成测试语音经 ASR 往返识别成功；TTS 首包后取消并重连成功。
  真实 Agent 收到 run identity 后取消返回 200，终态 `cancelled`、
  `response_persisted=false`，取消后未观察到 token/tool 事件。探针未写健康记录，
  未新增或修改账号授权。证据位于本机 `/tmp/reva-voice-client.7SMZYt/`。
- 独立 reviewer 对该候选裁决 **NO-GO**：ASR 成功启动后意外 onclose 未释放
  麦克风；TTS 已排队的 enqueue/done continuation 在取消后仍可触及共享播放器。
  同时发现 pending native startup 的取消需要等待清理后才能移交播放器。
  原生 build 273 在本地 archive 阶段主动中断（exit 75），未生成发布回执、未上传，
  不作为可发布候选。新源码须独立红/绿回归、固定提交及复审后才能重新构建。
- 当前同 Dossier 修复 trace：`docs/_generated/harness-runs/3afea3d1caa5.jsonl`
  （本机、不提交）。真实 provider 探针不替代候选 App 的背景切换/授权撤回/慢网
  验收；未验证硬件项保持明确列出，不把模拟器或 mocked tests 当作真机通过。
- 后续真实授权撤回探针仅针对上述审核测试账号：临时撤回既有授权后，活动 TTS /
  ASR 在下一次输入均以 4403 关闭，新连接返回 403；finally 已恢复同一 policy
  version 的原有授权并回读确认。没有更改其他账号、没有生成新的授权范围。
  本机 `consent-probe.log` 保留全部无载荷检查结果。
- 修复期额外 RED/GREEN：AppState 背景转换必须取消采集且不提交 partial；
  正在加载声音设置的 direct speech 在切后台后不得恢复播放或自动开麦。
  两条新测试先失败，补齐 generation 和前台状态门后 Voice hook 16 项全部通过。
- 本地 CI 环境的后端语音/Agent runtime API/流恢复/用户集成测试 67 passed；
  SQLite 仅用于快速契约/生命周期验证。真实 PostgreSQL 语义以该主干远端 CI 的
  `agent-runtime-postgres` 成功结果为证，不把本地 SQLite 当作生产数据库证据。
- 生命周期修复已落地，等待固定提交的独立复审：ASR 记录 terminal error 并通知
  两个消费 Hook，所有异常断线/提前结束均清理 native capture；采集所有权等待
  前序 startup/cleanup，启动中 stop 等价取消，清理失败阻止新所有者。TTS 同样
  通过共享 player ownership 隔离前后会话，取消后不执行排队 enqueue/finish，
  保留 provider/断线错误并拒绝后续 finish，不再将失败报告为成功。
  ASR 首轮 6 个新失败和 startup-stop 独立失败均转绿；TTS 两轮 2/4 个失败均
  转绿。最终定向 ASR/Hook 44 项、TTS 10 项，以及 TypeScript/ESLint 均通过。
- 独立 reviewer 已对固定代码提交 `6bc52c309aa7cf376b255332d58c09075bc6f41c`
  完成复审并给出 **G4 fixed-code GO**，独立重跑四个受影响套件 54 passed。
  最终 Mobile 全量 324 suites / 3,210 passed / 1 existing skip（exit 0）。
  该 GO 仅针对代码安全：精确合并主干 CI、原生制品及候选 UI 验收仍为 G5 条件。
- 生命周期修复 PR #269 已合入精确 main
  `fe3f34e4f82af9f1147293b8bde05dca75aba203`，CI `36840705330` SUCCESS。
  独立兼容性复核确认该客户端仍兼容已部署后端 `e8fa94a9`，本轮未部署 main
  上其他后端功能。完整 Mobile tree 与固定复审源码 `6bc52c309` 相同。
- Release 模拟器 build 273 已编译、安装并启动；实际构建源码为 `6bc52c309`，
  SDK0 / production 通道，不代表 Rokid 硬件或 Ad Hoc 通道验收。应用未登录，
  已请求用户手动认证；可执行的语音 UI、插话、后台和异常恢复检查仍待完成。
- 从干净、精确绿色 `fe3f34e4f` 构建的正式 `rokid-production` Ad Hoc
  `1.3.4 (273)` Archive / export 成功，IPA SHA-256 为
  `3421effe429daf336faaae8f206f0762af0d1176f26548fc149476a535db9ebc`。
  包装脚本随后因系统 Bash 3.2 的空数组 nounset 展开失败，未创建发布回执、
  未上传。只读排查又复现 `codesign` 可选证书前缀参数必须使用等号绑定。
- 上述发布工具兼容修复不改变校验边界：空数组不传多余参数，非空回执路径保留
  参数边界及 verifier 失败退出码；证书叶子仍必须匹配描述文件授权证书。
  两项真实 RED 转 GREEN，脚本/安全回归 52 passed；修复后的只读 `verify_app`
  对同一 IPA 严格校验通过，build 273、通道正确、已登记设备数 1。
  原失败记录和原包源码身份保持不变，未伪造或跨 SHA 重绑定回执。
  工具复审、正式包装回执及已登录候选 UI 仍独立裁决；G5/G6 不标完成。

### TestFlight native-only continuation — 2026-10-01

- 用户明确要求发布 TestFlight，并在发布密钥修复后要求继续部署。
- 已只读核验受控后端部署 `36861632116` 成功，生产源码及原始
  `SUCCEEDED` 回执均绑定 `30ac1c67be7b2df79363ac7509f70f8a56ce4834`；
  该流程的 iOS 构建和上传均未运行。此前私钥解析失败的运行保留，不重放。
- 本次提交仅追加审计文档，为 `target=testflight` 提供独立候选；不修改
  Mobile、后端或发布器代码，不重新部署后端、不重写其成功回执。
- 后续须核验该候选精确 main CI、CI-mode 集成闸、独立安全复核及
  canonical 授权轮换，再先 validate、后执行一次 TestFlight-only 发布。
  续发闸必须证明生产代码、原始回执、服务健康和候选运行时代码一致。
- 沿用已验证的专用 cloud key；授权切换只通过 canonical bootstrap，
  保留历史 intent、消费标记和锁 inode，不清理或复用旧发布状态。
- 只使用本次 workflow 返回的精确 EAS STORE production build ID 上传。
  构建、上传、Apple processing 和同包 UI 验收分别记录；尚未创建本次
  vendor 构建，不预先宣称 TestFlight 可用或 G5/G6 完成，不提交 App Review。

### TestFlight delivery confirmed — 2026-10-01

- 最终候选 `e19043ecb269e20f3bc0a546165e43d467f1fc8c`：独立 G4 GO、
  精确 CI `36872307842`、validate `36872453915`、新鲜 CI-mode 集成 67 项通过。
- 受控 TestFlight-only 发布 `36877321184` 全部必要 job 成功；不重复部署后端，
  继续使用真实 SUCCEEDED 回执绑定且健康的生产 `30ac1c67be7b2df79363ac7509f70f8a56ce4834`。
- 新 STORE / production 包 `1.3.4 (273)`，EAS build
  `20d5e73a-a6b9-4c70-ad69-e63d31e058f2`；submission
  `fcfbb57d-4804-4a36-9c57-eab062bf321e` 于 14:50:03 UTC 确认上传成功。
- Apple 处理已完成，ASC 显示 273 `Ready to Submit`，已关联原有内部测试组
  `内部测试`、`Team (Expo)`，4 个邀请；未新增外部测试组或提交 App Review。
- 下载确切 IPA 的 SHA-256 为
  `01096258d356b66b55c3aaf4a590068fb8767cc06b90442f71e8272b1e06dcf1`；
  严格签名、bundle/version、production channel/runtime 与生产 entitlement 检查通过。
  此 STORE 包不等同于此前源码和通道不同的 Ad Hoc 273。
- 发布修复与授权审计见 `2026-10-01-release-documentation-drift.md`。
  发布已交付；已登录候选的语音、插话、前后台及异常恢复 UI 尚未实际验收，
  G5/G6 不标完成，不宣称 App Store 审核或正式上架。

### Simulator test checkpoint — 2026-10-02 09:30 +08:00

- User requested simulator testing only. No business-code edits, credential
  extraction, backend deployment, new build/upload or App Review submission.
- Target: iPhone 17 Pro, iOS 26.5, installed Release build 273. Simulator source
  is actually `6bc52c309aa7cf376b255332d58c09075bc6f41c`, not e190. Git comparison
  confirms its tracked Mobile tree equals the Store candidate's Mobile tree.
  Installed executable and embedded main.jsbundle hashes match the previously
  built simulator artifact. This is source-equivalence evidence, not proof of
  Store/native configuration equality or the currently selected OTA bundle.
- Existing authenticated session opened successfully; no fresh login or
  SecureStore credential-write roundtrip was performed.
- Native UI observation: chat composer realtime transcription starts and stops;
  recognized text remains an unsent draft. During active listening, Home switches
  the app to background; reopening shows listening disabled, without automatic
  restart. Test-generated drafts were cleared, no chat message was sent.
- Automated boundary simulation: 7 suites / 108 tests passed in 3.25 seconds:
  useVoiceConversation, useVoiceRecording, cloudRealtimeAsr, cloudStreamingTts,
  voiceSessionCoordinator, aiConsent and chatStream. Includes partial/final
  de-duplication, interruption/cancellation failure, background cleanup, ASR
  disconnect, consent revocation and streaming TTS lifecycle. These mock-boundary
  checks are not native audio or live end-to-end proof. Log:
  `/tmp/reva-voice-client.7SMZYt/simulator-voice-regression.log`.
- Continuous-voice UI remains unverified: current chat header intentionally has
  history instead of the old voice-conversation action (see chat.test.tsx).
  The composer microphone is transcription, not the `/voice-chat` experience.
  No continuous-voice entry was found in the tested chat/main menu surfaces.
- Simulator deep-link limitation: installed native plist registers only
  `exp+health-pilot`, not configured `health`; Safari rejects the latter. The
  former is also registered by other installed QA apps and resolves to a different
  app. That switch was canceled. No unrelated QA app was removed or modified.
- Full spoken request/streaming playback/barge-in, live disconnect recovery,
  fresh login persistence and real-device audio remain unverified. Do not mark
  G5/G6 complete. No production health records were deliberately written.
- System Map passed after correcting this shell's Python PATH. Original selector
  was not indexed, so relevant source and tests were inspected directly.

### Realtime voice publication follow-up — 2026-10-03

- User explicitly requested publication of the realtime voice feature after the
  partial simulator result. Scope: restore a reachable chat-menu entry, prevent
  overlapping composer/voice sessions, verify and deliver through reviewed release.
  Preserve the existing history action, consent and health-write authority.
- Bounded follow-up run: `docs/_generated/harness-runs/686a2fa61fbd.jsonl`, linked
  to this same feature. Prior feature/release records are not reset or relabeled.
- Task checkout fast-forwarded to canonical `f966e97394005bc0b9f297b4132ef5ab61500e2a`,
  preserving the previous local simulator notes and original user workspace WIP.
- Current main CI `37080647733` is FAILED: Mobile, frontend and release consumers
  reject `braces@3.0.3` advisory `GHSA-vfj7-8cjw-p6xm`; release aggregation fails
  as a consequence. Existing node-forge backport is verified, not the blocker.
  Registry latest is still 3.0.3. No audit bypass, new vendor task or external push.
- User delegated dependency repair to a different Codex task. This task does not
  modify dependency guards and has no exception to push while main is red.
  That task subsequently pushed `474c446c7` and `c820d69b3`; exact CI
  `37085081299` is still running at this checkpoint.
- Current trusted OTA contract pins old native build 272 / cad1fd1d, not Store
  273; its native-path/cohort rules must not be bypassed. Delivery route is still
  pending this release assessment, not presumed OTA-compatible.

### Voice entry verification checkpoint — 2026-10-03

- Local commits `34c551431`, `73ca8d7cc`, `3a3a610c8` restore Chat → 更多操作 →
  实时语音对话, without auto-start or removing history/transcription controls.
- Independent safety review twice returned NO-GO: pending stop/cancel cleanup
  released navigation early, then the actual dictation hook swallowed native
  cancellation rejection. Both received failing regression tests before repair.
  Hook cleanup is now explicitly pending/failed; failed cleanup remains sticky,
  visibly warns the user, and prevents subsequent capture and voice navigation.
- Final independent source review returned GO for cumulative `3a3a610c8`, with
  173 focused tests independently passing. This is not a CI or native-audio waiver.
- Fresh full Mobile Jest: 324 suites, 3220 passed, 1 skipped; TypeScript passed.
  Project CI-mode runner: 66 backend realtime ASR/TTS/API/integration tests passed
  using SQLite, not a substitute for PostgreSQL or complete remote CI gates.
  System Map including regenerated navigation graph passed. Local logs are under
  `/tmp/reva-voice-release.Jtlenr/`.
- A Release simulator app built successfully from the committed `3a3a610c8`
  Mobile source, passed strict signature verification, and was installed on
  iPhone 17 / iOS 26.5 (`2D49F985-8B2F-4BE1-BAA8-CA5A672D9428`). Build label
  273 is local simulator metadata, NOT a replacement or proof of Store build 273.
  The app launched to its login page; authenticated voice UI acceptance awaits
  user login. No credentials extracted or injected, and no health writes made.
- Production read-only snapshot remains `30ac1c67be7b2df79363ac7509f70f8a56ce4834`;
  GitHub relay enabled/active, listening only on IPv6 loopback, resolver verified.
  No new production deployment, vendor build, upload, or App Review occurred.

### Authenticated simulator continuation — 2026-10-03

- User completed login directly in the simulator. Native UI confirmed the new
  chat-menu voice entry opens the voice page idle, with no automatic recording.
  Microphone permission was granted through the system prompt for this test.
- Explicit start reached listening. After Home and reopening the app, the voice
  page was idle rather than automatically restarting capture. Exit returned to
  the original chat; its history action and composer remained available.
- Two observed ASR turns contained only `。` yet triggered the clarification
  response. This is an invalid-transcript acceptance finding, NOT proof of a
  meaningful spoken conversation or silence correctness. No controlled spoken
  sample or audible playback/barge-in verification has completed. G6 stays open.
- This remains the installed local `3a3a610c8` simulator source, not a Store build.
  Voice commits were rebased unchanged onto the separately owned dependency
  repair; new main is `c89fee38744ca789d0ac1c6c43a3b202207bebb9` with CI
  `37085749065` still in progress at this checkpoint. No production release or
  authorization rotation was performed; the explicit rotation question is pending.

### Visible voice entry refinement — 2026-10-03

- User confirmed their simulator voice sample worked, then requested a more
  discoverable entry. That user report is not independent playback instrumentation
  and does not close the punctuation-only finding or release authorization gate.
- Added a persistent green labelled 实时语音 shortcut above the composer, outside
  the message list, with a pulse icon and minimum 44-point touch target. Flexible
  width/text avoids a fixed-width header squeeze. Hide during multi-selection;
  preserve header history/new chat and the separate transcription controls.
- The shortcut and existing menu entry use the same guarded callback; navigation
  remains explicit-start-only. Added regression cases for direct visibility,
  streaming/composer-busy refusal, cleanup completion and selection-mode hiding.
  RED: four new tests failed because the visible shortcut was absent.
- GREEN: 177 focused tests, TypeScript, full Mobile regression (324 suites,
  3224 passed / 1 skipped), secret scan, dossier consistency, System Map and
  diff whitespace checks passed. Local implementation commit `4cd2c82db`.
- Rebuilt and installed the Release simulator app from that Mobile source;
  signature verification passed and login was preserved. Native UI confirmed
  shortcut visibility, direct navigation to idle voice, exit back to chat, and
  keyboard-open visibility/navigation without automatic recording. No controlled
  narrow-device or large-font rendering pass is claimed. Evidence logs remain in
  `/tmp/reva-voice-release.Jtlenr/visible-entry-*.log`.
- Before replacing the prior simulator app, its old voice screen stayed in the
  answering state and two close attempts did not visibly navigate. Replacement
  then relaunched successfully. Cause is unverified; the new idle-page exit check
  does not prove that in-flight playback cleanup issue resolved. Keep this separate
  from the entry-layout acceptance and do not declare voice G6 fully passed.
- No push or production release performed for this visible-entry refinement.

### Header voice entry refinement — 2026-10-03

- User approved the top-right design instead of the above-composer shortcut.
  Header now keeps neutral history/more and a separate green pulse-icon + 语音
  capsule at the far right. New chat moves into more; the bottom shortcut is
  removed, preserving composer space and the existing transcription controls.
- Both voice entries still use the unchanged guarded navigation callback. The
  header entry is hidden in multi-selection and never auto-starts the microphone.
  No provider, permission, consent, cleanup, or health-write behavior changes.
- RED: the updated header regression failed on missing pulse/voice action.
  Updated screen contracts require exactly one visible header shortcut, no
  bottom duplicate, guarded navigation and working new-chat menu behavior.
- GREEN: 181 focused tests and TypeScript passed; full Mobile regression passed
  324 suites / 3224 tests with 1 skipped. Secret scan, dossier consistency,
  System Map and diff whitespace checks passed.
- Implementation `70a7460a3` was built into the existing Release simulator target;
  build/signature/install succeeded with login retained. Native iPhone 17 UI
  confirmed the far-right green voice capsule, removal of the composer shortcut,
  navigation into idle voice and back, visible history, and new chat in more.
  No microphone session or health write was started by this layout acceptance.
  Logs: `/tmp/reva-voice-release.Jtlenr/header-entry-*.log`.
- This is local simulator UI acceptance only. The pending audio findings and
  production authorization gate remain open. Remote main advanced independently;
  this task did not push, merge, deploy, or publish a vendor build in this turn.

### Authorized acceptance and release continuation — 2026-10-03

- User explicitly authorized closing the historical Store 273 lifecycle and
  rotating its release identity to the new verified candidate: revoke only the
  old managed identities, destroy its loopback private key, preserve immutable
  audit evidence and retain the existing permission scope. This is not approval
  to clear unknown leases, replay vendor tasks or submit App Review.
- Follow-up run: `docs/_generated/harness-runs/45cba1f4e1a3.jsonl`, bounded to
  16000 allocated tokens for acceptance closure and independent review. The
  earlier exhausted run and its findings remain intact.
- Clean task checkout rebased the four local entry/UI-audit commits onto
  `b6bfece100f6c7e7a94a1526331abdce217f2284`; exact main CI `37087232514`
  is successful. Original user checkout and unrelated work remain untouched.
- Read-only production check at 02:25 UTC found production still `30ac1c67`,
  managed authorization still `e19043ec`, and backend/worker/beat active.
  A new `deploy:backend` business lease created at 02:05:02 UTC is present,
  pointing to `/tmp/health-app-backup-preflight-15202-1790993101`. Its terminal
  state and owner are not yet proven. No lease, staged configuration, identity
  or production state was changed by this task. Rotation/deployment stays
  blocked until the existing operation has a verified terminal disposition.
- Source fix `a267b3db7` rejects punctuation-only ASR results without dropping
  single Unicode letters/numbers. It also fixes a proven synchronous splitter
  loop: reinserting a short phrase before the same punctuation never advanced.
  The new scan advances or consumes input, retaining short phrases for the next
  chunk/tail. This can explain an unresponsive screen, but the old simulator
  incident's exact triggering chunk was not captured and is not claimed proven.
- RED: 9 failing new cases / 24 passing prior cases. GREEN: 63 focused cases and
  TypeScript passed; full Mobile regression 324 suites / 3241 passed, 1 skipped.
  Independent fixed-candidate safety review GO with 108 tests independently
  passing. Tests include reset/unmount during an unresolved short-phrase Agent
  stream, cancellation and no microphone reopening.
- Fresh CI-mode backend voice/API/integration runner: 66 passed (SQLite contract
  checks, not PostgreSQL/full remote CI). System Map, secrets, dossier consistency
  and whitespace checks passed. Logs: `/tmp/reva-voice-release.Jtlenr/acceptance-*`
  and `independent-safety-a267.log`.
- Release simulator rebuild from the fixed Mobile source, strict code signature
  verification and install succeeded. Local label 273 remains simulator-only;
  it does not replace the existing Store 273 or prove a new TestFlight upload.
- Native UI on that rebuilt app retained login and the top-right entry. Entry
  opened idle; explicit microphone start reached listening; close returned to
  chat; re-entry was idle with no automatic restart. No meaningful spoken sample,
  audible short-phrase completion or playback-time exit was established in this
  check; do not substitute these UI checks for those remaining native paths.

### User-requested menu-only voice entry — 2026-10-04

- User found the top-right green voice capsule too large/prominent and requested
  returning voice to more. Removed only the header shortcut and its unused props
  and styles. History/more stay compact; new chat and realtime voice remain in
  more. The separate composer dictation control is unchanged.
- Menu navigation retains streaming/composer-busy guards and opens `/voice-chat`
  without automatic microphone start. No voice engine, permission, consent,
  health-write or backend behavior changed.
- RED: the new header regression failed because the prominent pulse shortcut was
  still present (1 failed / 3 passed). GREEN: 155 focused tests passed, including
  menu navigation, selection exit, history and composer cleanup protections.
  Full Mobile regression passed 326 suites / 3284 tests, with 1 skipped and
  1 snapshot passed. TypeScript, System Map, secrets, dossier consistency and
  whitespace checks passed. Full regression log:
  `/tmp/reva-menu-only-voice-jest-20261004.log`.
- Changes are local to the existing task worktree based on main `765b4cdb3`;
  the original dirty checkout was not changed. This UI revision has not been
  committed, pushed, deployed or uploaded to TestFlight. No new native simulator
  acceptance is claimed by the mocked UI regression tests.

### Menu-only entry native publication — 2026-10-04

- User authorized publication and then explicitly requested a new TestFlight
  package after the existing OTA native-baseline check blocked hot update.
  The OTA boundary was preserved; no OTA vendor call was made.
- Candidate `a8853dea1207163aaa412974dddfbc050ce3eeea` was integrated into main.
  Independent G4 returned GO with 187 focused tests and TypeScript passing.
  Main CI `37171099156` completed successfully. Fresh CI-mode voice/Agent
  integration passed 35 tests (SQLite contract scope, not PostgreSQL proof).
- Trusted validate `37171529156` passed. Canonical server staging independently
  verified the candidate and exact CI. Initial source fetches timed out before
  release authorization changed; preparing a local known-commit negotiation ref
  and fetching canonical GitHub over HTTP/1.1 completed staging. No release or
  vendor operation was retried. Normal retirement revoked 903's exact identities,
  destroyed only its revoked loopback private key and installed a885 authorization;
  historical evidence and the long-lived Expo credential were preserved.
- Trusted release `37172029300` completed success, including backend, iOS build,
  TestFlight upload and final result. Actual production HEAD and server SUCCEEDED
  receipt both equal a885. Public health is healthy; API runs and DB/Redis/Celery
  are connected. Backend/worker/beat are active with zero restarts.
- New iOS STORE production build **1.3.4 (275)** is
  `7c9396db-4bf1-44e1-bfc3-7e9ff187bfac`, FINISHED, bound to a885 and the existing
  app/project. A separate fresh Expo GraphQL read confirmed exactly one submission,
  `a8a03353-4deb-4c61-975f-d445c09a8df1`, FINISHED, IOS, correct project, ASC app
  `6763569720`, and exact submitted build. This is a new package, not reused 274.
- Workflow elapsed 13m15s (02:45:31–02:58:46 UTC). Jobs: source preflight 9s,
  readiness 28s, backend 6m05s, iOS build job 8m05s, TestFlight job 4m13s.
  Build/upload job times include their own dependency preparation and checks;
  Apple processing and same-package download/acceptance durations are unknown.
- Apple processing/tester availability remains unverified because the observed
  App Store Connect browser session is at sign-in. No App Review or public App
  Store submission was requested or performed. Same-package device/simulator
  acceptance is not inferred from build/upload success. This entry is audit-only,
  not a new runtime release candidate.
