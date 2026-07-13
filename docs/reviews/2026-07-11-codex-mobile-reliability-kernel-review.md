# Codex mobile-agent-reliability-kernel WIP 评审 (2026-07-11)

> 评审对象:本地未推送 2 commits + 107 文件未提交 WIP + 53 新文件(基线 8f349b569,落后 origin/main 110 commits)。
> 评审方式:5 维并行(safety-r4 / correctness / contract / test-quality / deletions)+ 每条 skeptic 对抗核验。

## 总裁定:NEEDS_FIXES_BEFORE_LANDING

Codex 这轮「写闭环 + agentTurnState 可靠性内核」的设计方向是对的:后端写回执 fail-closed、客户端无法自铸 verified 回执、diet 幂等用真复合键,工程质量整体扎实。但存在三个必须先解决的拦路问题:(1) 整个 WIP 建在落后 origin/main 110 个 commit 的陈旧基线上,直接落地会回滚多个已上线的 R4/诚实性/体验修复(含创始人实锤过的问句守卫、goal typed-only auto-confirm、流式 markdown 空白、图片压缩等);(2) 后端首次写工具失败即整轮终止且 finalized 重放,把弱模型自纠环变成用户死胡同;(3) api.generated.ts 双向漂移。全部可修——按协调清单 rebase + 修后端循环 + 重新生成契约后即可落地,但当前树严禁 push / OTA / 发版。(注:多数 finding 未经独立二次核验,但均附具体 file:line 证据;其中一条 PARTIAL 已按核验结论降级。)

## Findings(按严重度)

### [BLOCKER] 陈旧基线(落后 origin/main 110 commits)——落地即回滚多个已上线的安全与体验修复

工作树基于 8f349b569,落后 origin/main (e77586fab) 110 个 commit,且 70+ 个文件双方都改过。若 Codex 的文件版本在 merge 中获胜(或从本树 force-push / OTA),生产将回退:① backend/app/services/intake_intent_classifier.py 缺 origin 的 _is_intake_question 问句守卫(「午餐我吃了啥?」又会生成饮食写草稿——直接违反「查询回合绝不谎报写操作」),且 Codex 在同文件加了 10 个药名 marker,必然冲突;② agent_executor.py:1534 的 _TYPED_ONLY_AUTO_CONFIRM_KINDS 缺 goal(origin 8c3c099d2 已收紧)——语音渠道 goal 记录会跳过确认轮,违反「override 只能收紧」;③ mobile 侧丢失 sanitizeChatStreamToken(流式 markdown 空白,9a932fe16)、useMediaPicker 压缩管线(df3dd4160,回到 30-45MB 未压缩上传)、逐条消息选模型 mergeModelIntoExtraContext(edbb49a0f/#229)、fallbackReasons 路由透明化;④ ChatInputBar.tsx:393 重新引入「回复期间语音键失灵」bug(af980b69a 已修),并复活了创始人明确删除的 AGENT_MODES 段(1e1a77efb);⑤ ChatBubble 缺 JSON 泄漏清洗和真实进度条,回到 width:78% 假进度(4bdbcd4aa 已定性为 UI 谎报)。另外本地 commit 8347bdc14 是 origin 4954ffe39 的分叉孪生(同消息同 7 文件),origin 侧已有 15 个后续修复。−19035 行删除已核实全部是 diff 基线 artifact,本地 commits 零删除。

**修法**:在独立 worktree rebase 到 origin/main,把上述 5 组已上线行为当作显式冲突解决清单逐项核对(每项必须 origin 行为存活);丢弃本地 8347bdc14,让 origin 的 voice composer 系获胜,Codex 的 composerState/实时听写 WIP 重放到其上;rebase 后对合并版后端重跑 mobile+frontend 的 npm run generate-types。在完成前:禁止从本 checkout push、OTA、mobile-local-qr.sh --upload(其新增的 latest/ alias 会用落后 110 commits 的 IPA 覆盖稳定安装页)和 _run-mobile-tf.sh(本树还是 pre-2026-07-08 配置,会撞 Apple internal-group 拒绝)。

### [BLOCKER] 首次写工具失败即整轮报错 + finalized 永久重放——日常记录流程死胡同,废掉弱模型自纠环

backend/app/services/agent_executor.py:任何 health_record 调用即算 write attempted(1351-1352);校验失败返回 'Error:…' → 回执为 None → 进 unverified_write_tools(4163-4170)→ 整轮以 _UNVERIFIED_WRITE_USER_MESSAGE 终止(4252-4262),永远走不到 4292 让模型读错误自纠的 continue;multi_model 路径直接 raise(3049-3054)。该轮随后被持久化为 client_turn_finalized + error(4590-4613);客户端重试同文本 → 同指纹复用 turnId(useChatEngine.ts:745-750)→ 后端逐字重放同一错误(3203-3212)。快路由弱模型漏参是已知常态(饮水 2000 记成 250 的 400-fail-loud 设计正是为了让模型轮内自纠),现在第一次漏参就把用户钉死在错误里,重试也无解。

**修法**:区分两类:(a) 干净失败('Error:' 开头、未派发写入)→ 记 write_completed=false、发 failed tool_result 后 continue 让模型自纠(可按指纹限重试次数);turn 级终止 + 未验证回执文案只保留给 (b) 声称成功但无可验证身份的结果。同时不要把确定性 'Error:' 结果在 checkpoint 里判成 'uncertain'(1212-1221),并把 completion_status=error 且零回执的轮排除出 finalized 重放,让用户显式重试能真正重跑。

### [BLOCKER] api.generated.ts 双向漂移:既缺本次 WIP 自己的 schema 变更,又落后 origin 279 行

mobile/frontend 两份生成文件(同 blob,61090 行)是在陈旧后端上中途生成的:grep 确认 0 命中 (1) AgentRequest.client_turn_id(agent.py:513,而 chat.ts:196 已在发送);(2) POST /diet/records 的 Idempotency-Key header 参数(diet.py:58-65);(3) DietRecordBase.ai_raw_result(schemas/diet.py:34);(4) upload.py:328/359/404 三条新路由。同时 origin 的版本是 61369 行——origin 新增的 schema(如 MedicalExamResponse.conclusions_count)已被静默丢掉。这正是 sleep_hours/float→int 事故的静默漂移类;两份生成文件在 rebase 时必然冲突,任何一侧手工保留都会丢掉另一方向的契约。

**修法**:rebase 完成后,对合并后的后端在 mobile/ 和 frontend/ 各跑一次 npm run generate-types 并同变更提交;api.generated.ts 的 merge 冲突永远用重新生成解决,禁止手工挑边。重生成后逐项验证 client_turn_id、Idempotency-Key、ai_raw_result、三条 upload 路由、以及 origin 的 conclusions_count 全部在场。

### [MAJOR] 重试按钮双重漏洞:语音输入被洗白成 channel='typed'(绕过 symptom 确认门),且可能重放错误的历史消息造成重复写入

① chat.tsx:737-740 retryLastTextTurn 调 sendMessage 不带 sendOpts,useChatEngine.ts:790-792 默认 channel='typed';UIMessage 不保存原轮 channel,语音症状轮失败后一键重试即以 typed 权限自动确认写入(agent_executor.py:1476 只对 typed 放行 symptom/rhinitis auto-confirm),并给语音输入打上 source='manual' 溯源。channel 定义为传输层声明,这是对该门的直接绕过。② chat.tsx:705-709 选「最后一条无图用户消息」重试:若失败的是图片轮,会跳过它挑到更早的文本消息 → 指纹不同 → 铸新 turnId → 后端全新执行一条已完成的轮;若那条是「我喝了一杯水」则重复写入(写去重仅 per-turn,agent_executor.py:2986-3002)。

**修法**:把发起 channel 和原始请求(文本+图片引用)持久化到 AgentTurnState/用户 UIMessage,重试严格绑定失败轮本身:同 turnId、同 channel、同内容重放;图片无法复水则禁用重试并说明,禁止回退到更早消息。加 jest 用例:语音发送→失败→重试→断言出站 body channel !== 'typed';失败图片轮→断言不会重发更早文本轮。

### [MAJOR] 写回执门对已知成功形状确定性误报失败(补剂按名自动注册 / NFC debounce),错误文案还诱导重复注册

agent_executor.py:6560-6563 补剂自动注册成功返回纯 message JSON,无 id/record_id → _receipt_resource_identity(1238-1266)取不到身份 → 整轮被替换成「本次操作没有取得可验证的写入回执…再重试」并置 error——虽然注册和打卡都成功了。nfc.py:105-108 的 status='debounced'(record_id=None)不在拒绝状态集(1200-1205)里,同样落到 unverified:幂等成功被渲染成用户可见失败。文案引导重试 → 重跑 auto-register → 重复补剂定义(重复 DSI 面)。无任何补剂按名场景的回归测试。

**修法**:审计 _WRITE_RECEIPT_TOOL_NAMES 全部结果形状,成功 payload 必须携带结构化身份:补剂自动注册返回 {message, id, resource_type:'supplement_log', record_id};debounced 视为幂等成功返回去重记录身份(或显式 already-recorded 回执)。加回归测试:补剂按名(新建+已存在)、supplement_group、debounced tap,各断言产出回执且轮正常完成。

### [MAJOR] 新客户端硬依赖后端新 SSE 字段:OTA 先于后端部署 → 所有成功记录轮显示失败

useChatEngine.ts:975-987 对旧后端(不发 write_attempted/write_completed/receipt)的 health_record tool_result:writes 推断为 true 而 toolSucceeded 为 false → reducer 判 failed / write_receipt_missing_identity;done 无 write_receipts 同样判失败(agentTurnState.ts:200-211)。本仓库 mobile JS 走 OTA 独立发布——若 OTA 先落地(或后端回滚),全量用户的每次成功记录都显示失败 + 重试按钮(叠加上一条,重试还会引重复提交)。fail-closed 方向本身正确,但把部署顺序变成了正确性硬依赖。

**修法**:严格执行「后端 deploy →(journalctl/探针轮验证 prod tool_result 携带 write_attempted/receipt)→ generate-types → OTA」;同时给客户端加版本兼容:仅当事件携带 write_attempted 字段时才启用严格推断,老后端缺字段时降级为旧行为并软提示,避免 OTA/部署顺序倒置放大成全量假失败。

### [MAJOR] agentTurnState reducer 首次写失败即终态,吞掉后续成功重试与 done 事件

agentTurnState.ts:129-141 写工具失败 → phase 'failed';第 99 行终态后除 recover 外丢弃所有后续事件——即使后端修好自纠环,同轮内第二次成功的 tool_finished(receiptVerified:true)和 done 也被忽略:UI 挂错误/重试 chip 而正确回答在下面正常流出,failed 快照进存储,agent_turn_terminal 遥测报假失败。测试只覆盖读工具失败→recover(agentTurnState.test.ts:78),无「写失败→写成功→done」序列。

**修法**:写工具失败在 reducer 层设为非终态(如 running + pendingErrorCode 或非终态 write_failed),认证只在 done 由现有 hadWrite/writeVerified 门做(它已 fail-closed)。补 reducer 测试:tool_finished(write,fail) → tool_finished(write,success,receiptVerified) → done ⇒ completed。

### [MAJOR] spec 前言声明「migration: none / 仅 additive receipt」,但 WIP 实际带两个 DB 迁移 + 新 API 面 + 签名上传子系统

docs/specs/active/2026-07-09-mobile-agent-reliability-kernel.md:112-113 写 'apis: additive tool_result.data.receipt only' / 'migration: none';现实是两个 managed 迁移(20260709 client_turn_id / 20260710 diet client_action_id,pg+sqlite 双文件)、agent.py 新增 client_turn_id/channel 参数、diet 的 Idempotency-Key header、agent_executor 的重放机制、以及全新 backend/app/services/private_uploads.py 签名 URL 系统重写 upload.py。只有未提交的 dossier 承认「第二轮加固」,spec/plan 未更新。本仓库有 check_dossier_consistency.py 硬闸,后续 agent 读 spec 会得出「无需迁移」而跳过部署迁移步。

**修法**:同一变更内更新 spec front-matter(migration: 两个 managed 迁移;apis: 枚举 client_turn_id、channel、Idempotency-Key、签名上传 URL)和 plan 的 Architecture 行,提交前跑 check_dossier_consistency.py;或把第二轮加固拆成独立 spec/plan 对,让每份文档保持真实。

### [MAJOR] 仓库根明文密钥备份 + 5.5GB artifacts(含真实用户 HRV 数据)未被 gitignore,距离 git add -A 误提交一步之遥

.env.backup-20260705-pre-sms(159 行,含 KEY/SECRET/TOKEN)git check-ignore 退出 1——.gitignore 只有字面 .env/.env.local,不匹配该文件名。artifacts/ 共 5.5GB(ios-local-install 5.4GB IPA/构建产物;reports/ 下 hrv_6m_user3_raw/daily 是真实 user-3 HRV 导出),同样未 ignore 且目录内已有一个被 track 的文件,无法假定整目录被忽略。本仓库有 git add -A 误扫 untracked 文件的前科(worktree node_modules symlink 事故),而 Codex 正从这棵树活跃提交。

**修法**:把 .env.backup 挪出仓库(如 ~/backups/),或至少在下一次提交前给 .gitignore 加 `.env.backup*`(保留 !.env.example);加 `artifacts/`(为 wk1-c1-coldstart/ 那份文档单独 carve-out 或迁走)和 design/screenshots/;把 hrv_6m_user3_* 用户数据移出仓库(AGENTS.md §5)。

### [MAJOR] 测试假护栏三连:幂等/复用/回执门都只测了「不变」方向,受控变量从未取不同值

① test_diet.py:85 唯一幂等测试是同用户+同 key+同 payload 两次 → 1 条;没测不同 key 建第二条、跨用户同 key(索引 (user_id, client_action_id) 的 user 维度未验)、同 key 改 payload 时 diet.py:68-74 静默返回旧记录的语义——过度去重回归会绿灯下静默丢真实重复饮食记录。② useChatEngine turn-id 只测同指纹复用(test:714),没测失败轮后发不同消息应铸新 turnId——若指纹退化成常量,新问题会被后端重放旧答案且全绿。③ normalizeWriteReceipt(writeReceipt.ts:52-73)是客户端写声明门的全部,却零负例:verified:false / 'true' 字符串 / 缺 resource_id / 缺 completed_at 都没测,门若松动,未验证写入会渲染成已验证并注入下一轮 continuity 上下文,现有测试照样全绿。

**修法**:按「幂等测试必须在受控变量取不同值」补齐:diet 加不同 key→2 条、第二用户同 key→各自成功、同 key 改 payload→显式钉死语义;useChatEngine 加失败轮后不同文本→断言 streamChat 收到新 turnId;writeReceipt.test.ts 加 4 个 normalizeWriteReceipt 拒绝负例 + rememberVerifiedWriteReceipt 抛 write_receipt_unverified + 历史恢复丢弃未验证回执的用例。

### [MAJOR] 复杂度预算大规模超标:agent_executor.py 膨胀到 7423 行(+1579),恰好也是最重的 rebase 冲突面

工作树 vs HEAD:agent_executor.py 5844→7423(origin 侧是 6559,三方合并将是全仓库最痛的冲突);useChatEngine.ts 759→1303;ChatInputBar.tsx 957→1281;新组件 ChatTodayFocusCard.tsx 525 行(新文件应 ≤500)。CLAUDE.md 明令「新加功能禁止往 1000+ 行的文件继续堆」。讽刺的是新模块本身(agentTurnState/writeReceipt/private_uploads)都拆得很好,只是编排层的 +1753 行回执/重放/持久化逻辑全堆进了预算规则明确保护的两个文件。

**修法**:落地前抽模块:_write_receipt_from_tool_result/_WRITE_RECEIPT_TOOL_NAMES → services/write_receipts.py;_replay_client_turn/_persist_turn_write_state/_recover_client_turn_write_checkpoint → services/agent_turn_replay.py(仿 origin 已有的 agent_send_meta.py 先例);mobile 侧把轮恢复/continuity 接线抽成 useAgentTurnRecovery hook,ChatTodayFocusCard 的 full/compact 变体拆分。这也直接减小 rebase 冲突面。

### [MINOR] goals/supplements 新 PUT/DELETE 缺跨用户隔离负例——但 origin/main 已有同功能且带隔离测试,真实风险是 merge 时被覆盖

WIP 的 goals.py:126/142、supplements.py:449/465(LLM 经 health_manage 可达的硬删除端点)只有 owner happy-path 测试(test_goals.py:30,61;test_supplements.py:359,391),无 403/404 负例。但核验发现 origin 8c3c099d2 已上线同一批端点且带完整隔离测试(test_goal_detail_update_delete_are_user_scoped 等)——Codex 这是陈旧基线上的平行重实现,覆盖更差。风险不是「全仓库无红测试」,而是 merge 解决时用 Codex 的测试文件覆盖掉 origin 的隔离测试。

**修法**:rebase 时该组文件以 origin 版本为准(端点+测试都取 origin);若 Codex 版有增量再叠加,并确认 test_goal_detail_update_delete_are_user_scoped / test_supplement_record_update_delete_are_scoped_to_current_user 在合并后依然在场且绿。

### [MINOR] 客户端两处手抄后端权威列表,漂移风险(dietIntakeGuard markers / write-tool 谓词)

① mobile/utils/dietIntakeGuard.ts:14-28 逐字复制后端 DIET_MANAGEMENT_MARKERS,31-38 又用正则重实现药物/补剂子集——而 Codex 同时在后端加了 10 个药名(伏诺拉生等),mobile 正则不认识;好在后端 _assert_diet_food_items_allowed(diet.py:39-50)仍是每条写路径的权威,不会漏拦,但两份手维护清单必然静默分叉(drug_lexicon 单一事实源重构就是为终结这类漂移)。② chat.ts writeAttemptFromToolCall 硬编码镜像后端 _WRITE_RECEIPT_TOOL_NAMES(agent_executor.py:1139),今天对齐,加新写工具时客户端会静默漏标,无 parity 测试。

**修法**:dietIntakeGuard 收缩为仅管理意图判定,药物/补剂分类交给后端 400 detail 透传(或从后端源生成到 packages/shared 供两端消费);writeAttempted 改为纯粹消费后端下发的 write_attempted 字段(删客户端推断),或至少加一个 jest 钉死两侧集合并注释指向 agent_executor.py:1139。顺带建议后端权威侧补「去掉/清除/作废」等管理词。

### [MINOR] 死代码上加新测试:chatResultActions.ts / BriefingStrip.tsx 已无生产消费者,P0-6 文档与代码漂移

T6 重写后 ChatBubble 已不引用 chatResultActions(生产 importer 为零,仅测试文件引用),BriefingStrip 同理——但本次 WIP 还给这个孤儿新增了「药物类回复路由到 medication 草稿确认页」测试,plan 文档 P0-6 仍把该路由描述为在线行为。测试给死代码制造覆盖率幻觉;而「assistant 散文→写入」正是写声明不变量最想清除的路径,留着可被重新接线。计划 Task 10 步骤 4-5 本来就要求删除。

**修法**:按计划自己的步骤 4:删除 chatResultActions.ts + BriefingStrip.tsx 及其测试,清掉三个 ChatBubble 测试文件里的僵尸 jest.mock,同变更修正 P0-6 计划条目;或者若 medication 草稿路由确实要保留,把它重新接进新的 ChatBubble 动作面。

### [MINOR] recover 路径绕过 done 的写验证门——写声明硬门只存在于一层

agentTurnState.ts:200-211 的 done 门会把 hadWrite 且 writeVerified!==true 判 failed(有测试),但 recover 分支(241-263)serverStatus:'completed' 直通 phase 'completed',无验证证据也能认证。目前唯一调用方 useChatEngine 在派发前查了回执(有测试),但第二个派发点或调用方重构就能让未验证写入被认证为完成,且 reducer 测试全绿。

**修法**:在 recover 分支镜像 done 门(serverStatus completed + hadWrite + writeVerified!==true → failed/write_receipt_missing_identity),并补对应 reducer transition 测试。

### [MINOR] 手表语音 auto-confirm 白名单扩三项(waist/sleep/excretion)仅以测试清单改动放行,需安全评审签字

test_watch_voice_record_failclosed.py 把 waist/sleep/excretion 加进 auto-confirm 允许列表,同 diff 里 sleep 从手动确认侧的示例换成了 unknown_metric(第 84 行)——政策放宽纯靠改测试表达。三项都是测量值而非症状记录(typed-only 规则针对症状),大概率没问题,但 R4 边界变更应是被记录的决策而非静默测试编辑。

**修法**:让 safety-privacy-reviewer 对三项新增签字,决策记入 dossier G4 节;负例(unknown_metric 保持手动确认)保留。

### [MINOR] 病理 narrative 项 OCR is_abnormal=True 被存成 'normal',under-alarm 方向被新测试钉死

test_medical_exams.py 新用例:OCR 返回 {name:'病理诊断', value:None, value_text:'胃窦后壁黏膜慢性轻度炎伴糜烂…', is_abnormal:True},断言 abnormal_count==0 且 item.is_abnormal=='normal'。让叙事项不进数值异常门的意图正确、结论原文也保留了,但任何按 is_abnormal 消费的下游会对病理报告 under-alarm,且该行为现在被绿测试锁定为正确。

**修法**:引入第三态(如 'narrative'/'unknown')或保留 OCR 异常标记同时把 value=None 项排除出数值 abnormal_count;请安全评审确认哪些下游读 is_abnormal 后再定语义。

### [MINOR] 杂项收尾:30s stream-hold 丢 token(存量)、hydration 无 .catch、brain 图标、占位函数、Idempotency-Key 校验不对称、绿测声明未完全独立复核

① useChatEngine.ts:230/446-451 的 LOCAL_STREAM_HOLD_MS=30s 未改:超 30s 的深分析流在切前台重载后 token 静默丢失、done 卡片孤挂(存量问题,但可靠性内核 campaign 是修它的正确位置)。② useChatEngine.ts:409-429 hydration promise 链无 .catch,未登录挂载抛 unhandled rejection(431-439 的 persist effect 有 catch)。③ apps/mac FeatureViews.swift:1297 ThinkingProcessTrace 用了 SF symbol 'brain'——创始人明令禁用脑图标。④ agentTurnState.ts:79-81 agentTurnPhaseFromStatus 忽略 stage 参数恒返 'running',签名撒谎。⑤ chatCardActions.ts:159-166 normalizeIdempotencyKey 未校验 min_length=8(后端 diet.py:58-65 有),当前不可达但失败分类会混。⑥ 本次评审现场只复核了 mobile jest(34/34 过,但需 --forceExit,open-handle 债)与部分后端组;dossier 的 '581 passed' 未端到端独立重跑,且历史教训 pytest|tail 会吃退出码。

**修法**:①流活跃期间延长 hold 或围绕活跃 aId 合并服务端历史而非整表替换;②补 .catch(镜像 438 行);③换成 ellipsis/disclosure 三角等中性图形;④实现 stage→phase 映射或删函数内联 'running';⑤client 校验补 length<8;⑥落地前从最终树不经 tail 直跑两组后端测试,并用 --detectOpenHandles 烧掉 jest 挂起句柄后去掉 --forceExit。

## 做得好的(保持原样)
- 后端写回执链是真·fail-closed:回执只从后端工具结果结构化 payload 构造(agent_executor.py:1269-1315),从不来自 LLM 文本;拒绝失败标记、要求 resource id,写入无回执则整轮以诚实文案报错而非谎称「已记录」——服务端写声明硬门是真的。
- 崩溃/中断恢复不会重复执行或夸大写入:派发前先提交 in_flight checkpoint(2580-2631)+ 完整写计划 sealed fingerprints(2633-2671),只有每个指纹都有匹配回执才报 complete,不确定态显式让用户先查再记。
- 客户端双层防线:agentTurnState 把 writing/verifying 当纯 UI 相位而非证据,done 时 hadWrite 无验证即判 failed;normalizeWriteReceipt 拒绝一切非 verified===true + 完整身份的回执——任何客户端路径都铸不出假 verified。
- R4 draft→confirm 端到端保留:卡片动作要求 requires_manual_confirm===true + 端点 allowlist,饮食卡/饮食屏/agent 工具三条路径都收敛到服务端权威守卫 _assert_diet_food_items_allowed。
- channel 穿线是相对 origin 的真修复(origin 的 mobile 从未传 channel,按住说话也默认 typed);现在传输层声明 + 后端白名单 fail-closed,未声明渠道走确认。
- diet 幂等做法教科书级:Idempotency-Key header 模式校验 + (user_id, client_action_id) partial unique 索引 + IntegrityError replay,pg+sqlite 双迁移配对;客户端 Keychain 降级墓碑挡重复点击但绝不伪造回执细节。
- 上传安全测试大幅加强而非削弱:被删的单条 404 断言换成了完整 authz 矩阵(匿名 401/跨用户 403/owner 200/签名能力 200/篡改签名 401/TTL≤5min/旧路径封锁)。
- 回执拒绝负例 battery 出色(8 个参数化用例,含软失败 JSON、ok:false、[NEEDS_CONFIRMATION]);turn 重放套件覆盖跨账户隔离、孤儿写入不重跑、锁竞争回收、执行前 checkpoint。
- 遥测严格 schema allowlist、无自由文本无资源 id,两端 sanitizer 逐字对齐(phase 集合、时长分桶、SAFE_TOKEN 正则完全一致)。
- composer 接受协议是真实可靠性升级:发送在服务端 request_persisted ACK 才算被接受,失败时文本+图片草稿完整恢复并提示——消息不再 fire-and-forget 丢失。
- 工程卫生干净:14 个新模块零 console.log/零 TODO、1:1 测试镜像;计划文档甚至预先自知仓库状态风险(Task 16 明令禁止从脏/落后工作区部署)。
- −19035 行删除恐慌完全解除:两个本地 commit 一个文件都没删,40 个『deleted file』全是 diff 基线 artifact(origin 侧新增文件);Codex 也没碰任何发版配置。

## Rebase / 落地协调清单(必读)
- voice composer 血统:本地 8347bdc14 是 origin 4954ffe39 的分叉孪生(同 commit message、同 7 文件),origin 侧对 ChatInputBar.tsx 另有 15 个后续修复——rebase 时 origin 系默认获胜,Codex 的 composerState/实时听写 WIP 重放到其上;本地 docs/specs/active/2026-07-06-mobile-wechat-voice-composer.md 与 origin docs/plans/ 同名文档会重复,留 origin 版。
- rebase 必查清单(origin 已上线、本工作树缺失,冲突解决时 origin 行为必须存活):sanitizeChatStreamToken(9a932fe16 流式 markdown 空白)、useMediaPicker 压缩管线 + package.json expo-image-manipulator(df3dd4160)、逐条消息选模型 mergeModelIntoExtraContext + setPerMessageModelId + fallbackReasons(edbb49a0f/#229)、hold-to-talk 流式期间可用(af980b69a)、stripLeakedStructuredJsonFragments + ThinkingIndeterminateBar(203359cb0/4bdbcd4aa)、创始人删掉的 AGENT_MODES 段勿复活(1e1a77efb)。
- 后端 rebase 必查:intake_intent_classifier.py 恢复 _is_intake_question 问句守卫的同时保留 Codex 新增的 10 个药名 marker(必然 both-modified 冲突);_TYPED_ONLY_AUTO_CONFIRM_KINDS 必须含 goal(origin 8c3c099d2);goals/supplements PUT/DELETE 端点+隔离测试以 origin 为准;agent_executor.py 三方(base 5844 / origin 6559 / 本地 7423 行)是最重冲突,建议先按复杂度预算 finding 抽模块再合。
- api.generated.ts(mobile+frontend)冲突永远重新生成解决,禁止手工挑边——rebase 后对合并后端各跑一次 npm run generate-types 并同 change 提交。
- mobile/app.json 语音插件 hunk 相对 origin 是净 no-op(origin 已带同配置,TestFlight build 110/111 已发)——rebase 后该 hunk 应消失,确认 app.json vs origin 无 diff 即无需额外 native build。
- 上线顺序硬依赖:后端 deploy(并在 prod 验证 tool_result 携带 write_attempted/receipt,journalctl 或探针轮)→ generate-types → OTA;顺序倒置会造成全量假失败(finding 6)。
- 本 checkout 发版全面冻结直到 rebase 完成:禁 mobile-local-qr.sh --upload(WIP 新增的 latest/ alias 用 rsync --delete 会把落后 110 commits 的 IPA 覆盖到稳定安装页——建议给脚本加 HEAD-behind-origin 拒绝守卫)、禁 _run-mobile-tf.sh(本树还是 pre-2026-07-08 配置,会撞 Apple 'Cannot add internal group' 假失败)、禁 OTA(MEMORY 铁律:OTA 必从 origin/main 干净 worktree 发)。
- channel threading 在 origin 侧仍是 pending 缺口——Codex 的传输层 channel 穿线是对它的真修复,rebase 后应保留并落地;但先修 finding 4 的重试洗白洞,否则穿线的收益被重试路径掏空。
- thinking-trace 相关:Codex 在 apps/mac 的 ThinkingProcessTrace 用了 'brain' SF symbol(创始人禁用),与另一团队 mobile 侧 thinking pill 的图标风格对齐时一并换掉。

---

## 附录 A — 安全评审签字裁定(2026-07-12)\n\n> 评审人:safety-privacy-reviewer(READ-ONLY,不改代码,只裁定)\n> 应 Codex reliability-kernel WIP 评审的两条 [MINOR] 请求(§手表语音 auto-confirm 白名单 / §病理 narrative is_abnormal)出具。\n> 核验基线:MAIN 工作树未提交 WIP(HEAD e2e9add34)逐字读取,并与 `git show origin/main:<file>` 对比。\n\n---\n\n### 裁定 1 — 手表语音 auto-confirm 白名单三项(waist / sleep / excretion)\n\n**核验到的事实(改变了这条的定性):**\n\n1. `_FAST_RECORD_AUTO_CONFIRM_KINDS` / `_TYPED_ONLY_AUTO_CONFIRM_KINDS` 在 `agent_executor.py:1510` / `:1534`。\n2. **origin/main 早已上线本行为**:`git show origin/main:backend/app/services/agent_executor.py` 里 `_FAST_RECORD_AUTO_CONFIRM_KINDS` 已含 `waist/sleep/excretion`(且不在 typed-only 集内),即生产上这三项语音通道本就免确认。WIP 只是在**落后 110 commit 的陈旧基线**上把同一行为重新推导了一遍 —— 这不是一次新的 R4 边界扩张,是对已裁决行为的平行重实现。因此风险等级从\"未记录的政策放宽\"下调为\"重复既有决策 + 需补签字入档\"。\n3. 三项均为**测量值**,不是症状/用药记录;typed-only 门(`{\"symptom\",\"rhinitis\"}`)的原始意图是拦症状类转写失真,与测量无关。\n4. **可逆性已核实**:三项都有 agent 层 DELETE/LIST 映射(`agent_executor.py:6687` 列表、`:6711` 删除:`/waist/records/{id}`、`/sleep/records/{id}`、`/excretion/records/{id}`),误记可编辑/删除。\n5. **excretion 结构核实**(`agent_executor.py:6398-6432`):字段是 `type∈{bowel,urine}` + `stool_type` / `urine_color` / `urine_amount`,**无自由文本症状字段**;黑便/血便/血尿这类急性信号由 LLM 归为 symptom(→ 走 typed-only 门)或由 Safety Guardian 症状红线(`symptoms.py`)在写后评估捕获——确认门不是急性告警的责任方,Safety Guardian 是,且它 post-write、通道无关地跑。\n\n**逐项 VERDICT:**\n\n| kind | 裁定 | 理由 |\n|---|---|---|\n| **waist(腰围 cm)** | **APPROVE** | 纯数值、可逆、非医疗级。误转写顶多让代谢综合征 5 项标准之一取错值,而该判定需命中 3/5 且已有源新鲜度护栏(≤180 天),单值 blast radius 低,方向可 over/under 但均非急性、可编辑纠正。origin 已上线。 |\n| **sleep(睡眠时长)** | **APPROVE** | 测量值、可逆、非医疗级。喂 readiness 评分(advisory,非安全硬门)。契约漂移风险(`sleep_hours` vs `total_sleep_minutes`)是类型问题,与确认门无关。origin 已上线。 |\n| **excretion(排便/排尿)** | **APPROVE** | 结构化(type + Bristol stool_type),无自由文本;可逆。急性 GI/泌尿信号走 symptom(typed-only 门)或 Safety Guardian,不经由此结构记录绕过。origin 已上线。 |\n| **unknown_metric** | **PASS(仍 fail-closed)** | 已核实:`_auto_confirm_fast_record_args` 逻辑 `kind not in _FAST_RECORD_AUTO_CONFIRM_KINDS → requires_confirmation`(`:1473-1477`),`test_fast_record_unknown_type_keeps_manual_confirmation_gate`(`test_watch_voice_record_failclosed.py:83`)断言 `_fast_record_requires_confirmation is True`。未知 kind 恒回退手动确认,负例保留。 |\n\n**CONDITION(阻断级,必须在 rebase 时解决,否则本裁定的 APPROVE 不成立):**\n\n> **`goal` 缺 typed-only 门 —— 这是 under-gate,不是本三项的问题,但同处一张白名单必须一并纠正。**\n> WIP 工作树:`_TYPED_ONLY_AUTO_CONFIRM_KINDS = {\"symptom\", \"rhinitis\"}`(`:1534`)。\n> origin/main:`{\"symptom\", \"rhinitis\", \"goal\"}`(origin 8c3c099d2 已收紧)。\n> WIP 把 `goal` 放进 AUTO 集却没放进 typed-only 集 → 语音/未声明通道的 goal 记录会跳过确认。这与\"override 只能收紧\"直接冲突(也是主评审 BLOCKER #2)。**rebase 后必须让 origin 的 `goal` typed-only 门存活;合并版 `_TYPED_ONLY_AUTO_CONFIRM_KINDS` 必须含 `goal`。** 建议加一条回归:`goal` + 非 typed 通道 → `_fast_record_requires_confirmation is True`。\n\n**入档:** 本三项 APPROVE 计入 dossier G4;typed-only 负例(unknown_metric、goal 语音通道)保留。**签字前提是上面的 goal CONDITION 在合并版中兑现。**\n\n---\n\n### 裁定 2 — 病理 narrative 项 is_abnormal 语义\n\n**VERDICT:REJECT 当前行为(选项 c),改为选项 (b) —— fail-closed。**\n\n**Codex WIP 实际改了什么(`medical_exams.py` OCR 导入路径,diff vs HEAD):**\n- `:519` `is_ab_flag = \"abnormal\" if (it.get(\"is_abnormal\") and value is not None) else \"normal\"` —— value=None 的病理项被压回 `'normal'`。\n- `:551` MedicalIndicator `\"is_abnormal\": bool(it.get(\"is_abnormal\")) and value is not None` —— 同样压成 `False`。\n- `:562` `abnormal_count = sum(1 for i in items if i.get(\"is_abnormal\") and i.get(\"value\") is not None)`。\n- (好的部分)新增 `value_text` / `original_value_text` 落库 —— 结论原文没丢。\n\n**is_abnormal 下游消费者全量枚举(grep backend + twin + frontend + mobile):**\n\n*读 `MedicalExamItem.is_abnormal`(String)的:*\n| 位置 | 影响 |\n|---|---|\n| `services/health_analysis.py:349` `!= 'normal'` 过滤 abnormal_items | 病理项被排除 → **AI 健康分析看不到病理异常(under-alarm)** |\n| `services/exam_explain_service.py:216` | 病理项被排除 → 化验解读遗漏 |\n| `services/conversation_starters.py:250-251` `!= \"normal\"` | 病理项不触发主动对话 |\n| `api/medical_exams.py:128` / frontend `medical-exams/*`、mobile `medical-exam-detail.tsx:124/238` | 展示按 normal 渲染(不标红、排序靠后) |\n\n*读 `MedicalIndicator.is_abnormal`(Boolean,`family_health.py:61`)的:*\n| 位置 | 影响 |\n|---|---|\n| **`twin/_collectors.py:429` `is_abnormal == True`** | **最严重**:`fetch_medical_exam_abnormal` 构建 Twin 异常体检视图。见下。 |\n| `twin/_collectors.py:445` `\"value\": ind.value if ind.value is not None else ind.value_text` | 该收集器**本就为 value=None 的 narrative 设计了 value_text 兜底**——但仅对 `is_abnormal==True` 的项生效。 |\n| `services/memory_extractor.py:194` | 只对 abnormal 抽记忆 → 病理结论不进长期记忆 |\n| `services/insight_generator.py:197`、`health_read.py:199/277`、`orchestrator/arbitration.py:118`、`api/genetic_data.py:2104`、`services/family_weekly_digest.py:168` | 各自 abnormal 过滤,narrative 被静默剔除 |\n\n**决定性证据(为什么 c 不可接受):**\n`twin/_collectors.py` 第 429 行按 `is_abnormal == True` 过滤,第 445 行**已经写好** value=None → value_text 的兜底逻辑。也就是说:Twin 收集器本就打算把病理 narrative 的原文带进数字孪生,唯一的闸就是 `is_abnormal==True`。Codex 的改动恰好把这个闸置成了 False → **病理结论(founder 实锤的\"胃窦…慢性轻度炎伴糜烂\",乃至将来可能的\"肠化生/不典型增生/腺癌\")从此完全不进 Twin**,所有读 twin.labs 异常的 specialist 与 Safety Guardian 都看不到它。这是直接的、安全相关的 under-alarm,方向错误。value_text 虽落了库,但被同一个 is_abnormal 闸挡在 Twin 之外,等于孤儿数据。\n\n**为什么选 (b) 而不是 (a):**\n- `MedicalIndicator.is_abnormal` 是 **Boolean 列**,存不下第三态('narrative'/'unknown'),选项 (a) 需要 DB 迁移或新增列,并把语义劈成 String(MedicalExamItem)+ 三态两种表示 —— 正是这种双表示漂移酿成了本 bug。**避免。**\n- 选项 (b) 零迁移:让 narrative 保持 `is_abnormal=True`,只把**数值 abnormal_count** 与 is_abnormal 解耦。所有安全相关消费者(Twin/分析/解读/starters/memory)恢复正确,`_collectors:445` 的 value_text 兜底自动生效。\n\n**推荐落地(选项 b,fail-closed,零迁移):**\n1. **回退旗标压制**:`:519` 改回 `is_ab_flag = \"abnormal\" if it.get(\"is_abnormal\") else \"normal\"`;`:551` 改回 `\"is_abnormal\": bool(it.get(\"is_abnormal\"))`。→ 病理 narrative 保持 abnormal,进 Twin/安全/分析/记忆。\n2. **保留 Codex 的 value_text / original_value_text 落库**(这部分是对的,且是 `_collectors:445` 兜底能工作的前提)。\n3. **数值 abnormal_count 的正确修法**:Codex 想\"病理项不污染数值异常计数\"这个动机本身合理,但修反了方向。两条可接受路径:\n   - (首选,零 schema 改)让 `abnormal_count` **计入** narrative flagged 项 —— 一份病理报告 badge 显示\"1 项异常\"是**正确且安全(over-alarm 侧)**的;或\n   - (需改响应 schema + 两端 generate-types)拆成 `numeric_abnormal_count` + `narrative_flagged_count`,badge 显示\"N 项数值异常 · M 项结论待复核\"。\n   **硬约束:badge 绝不能对含 flagged 病理结论的报告显示成让用户/下游理解为\"无异常\"的形态。** 当前 WIP 会让纯病理报告 `abnormal_count==0` → 卡片落到\"待复核\"甚至被误读为正常,这是 under-alarm。\n4. **回归测试**(把语义钉成 fail-closed 而非现在钉成\"病理=normal\"):\n   - OCR 返回 `{value:None, value_text:'胃窦…慢性轻度炎伴糜烂', is_abnormal:True}` → 断言落库 `MedicalExamItem.is_abnormal=='abnormal'` 且 `MedicalIndicator.is_abnormal is True`;\n   - 断言该 indicator 出现在 `fetch_medical_exam_abnormal` 结果里且 `value` 回落到 value_text;\n   - 断言 badge/count 不呈现为\"无异常\"。\n\n**迁移/消费者影响:** 零 DB 迁移(选项 b 首选路径)。若选拆双计数,则需改 `import_medical_exam_from_image` 响应 schema + 跑 mobile/frontend `npm run generate-types`(注意本 WIP 已有 api.generated.ts 双向漂移,主评审 BLOCKER #3——两者一并处理)。\n\n**founder 实锤:** MEMORY `project_founder_gastric_biopsy_hp_negative.md` 的胃窦活检正是 `{value:None, value_text:'胃窦慢性轻度炎', is_abnormal:True}` 形状。当前 WIP 会让 founder 自己的体检病理在 Twin/安全/分析里全线消失——这条 under-alarm 会直接打在锚点用户真实数据上。**方向必须 fail-closed。**\n\n---\n\n**总签字:**\n- 裁定 1:waist/sleep/excretion 语音 auto-confirm **APPROVE**;unknown_metric fail-closed **PASS**。**放行前提 = goal typed-only 门在合并版中兑现(阻断 CONDITION)。**\n- 裁定 2:当前病理 narrative is_abnormal 语义 **REJECT(no-go)**,按选项 (b) fail-closed 整改并补回归后方可放行。\n\n— safety-privacy-reviewer, 2026-07-12\n```\n\n---\n\nTwo notes for you (the leader) outside the doc itself:\n\n1. **Adjudication 1 turned out milder than the review framed it** — waist/sleep/excretion auto-confirm is already live on `origin/main`, so the WIP isn't introducing a new boundary, just re-deriving shipped behavior on a stale base. The real hazard hiding in the same allowlist is the **`goal` typed-only regression** (WIP dropped it; origin has it). I folded that in as a blocking CONDITION because it's the same file/decision surface and it's under-gate.\n\n2. **Adjudication 2 is a genuine no-go in the under-alarm direction.** The decisive evidence is `backend/app/twin/_collectors.py:429`+`:445` — the Twin collector was explicitly built to carry `value=None` narrative items via `value_text`, gated only on `is_abnormal==True`. Codex's flag-zeroing severs exactly that path, so pathology conclusions vanish from the Digital Twin entirely (Safety Guardian + specialists never see them). Recommend option (b), zero migration, keeping Codex's genuinely-good `value_text` storage.\n\nAll file:line references in the doc are against the current MAIN working tree (`agent_executor.py`, `medical_exams.py`, `twin/_collectors.py`, `models/family_health.py`)."}],"stop_reason":"end_turn","stop_sequence":null,"stop_details":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":3582,"cache_read_input_tokens":112962,"output_tokens":11137,"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":3582},"inference_geo":"not_available","iterations":[{"input_tokens":2,"output_tokens":11137,"cache_read_input_tokens":112962,"cache_creation_input_tokens":3582,"cache_creation":{"ephemeral_5m_input_tokens":3582,"ephemeral_1h_input_tokens":0},"type":"message"}],"speed":"standard"},"diagnostics":null},"requestId":"req_011CcwdEWJaxsAStrUddfLmg","attributionAgent":"safety-privacy-reviewer","type":"assistant","uuid":"5ef00c1c-4ba3-4d53-b9d6-21588595bbe0","timestamp":"2026-07-12T05:42:06.571Z","userType":"external","entrypoint":"claude-desktop","cwd":"/Users/liqiuhua/work/personal/health-llm-driven","sessionId":"6146257c-7ef5-4de6-a35d-fe4eb3602077","version":"2.1.205","gitBranch":"main","slug":"majestic-conjuring-lightning"}