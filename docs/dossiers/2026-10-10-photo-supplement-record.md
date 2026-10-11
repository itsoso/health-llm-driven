# 图片多补剂记录目标未绑定

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 跨会话集成验证，固定候选 G4 与发布待完成 |

primary controller: health-harness-orchestrator；overlay: safety-gate。

## G1 准入
裁决：PASS。用户截图中“记录四种补剂 NAC 2粒 其他各1粒”带照片，收到 health_record_target_mismatch 的笼统名称或剂量缺失提示。要求准确记录已服用数量，不授予推断瓶身含量、换算剂量或凭模型自由描述自动写入的权限。

## 根因证据
- agent_executor._analyze_image_with_vision 对非餐食图片仅生成普通图片描述；描述进入模型messages，但不是绑定owner/source的结构化补剂候选。
- capability_policy._health_record_target_status依据用户原文目标核对名称与数量，不会把自由图片描述当用户授权。因而模型提出四种名称时可能与原文NAC及“其他”无法逐项对应。
- 当前无该截图对应线上完整工具trace；不能断定具体拒绝参数，更不能宣称四项已保存。
- 同图“分析刚才的运动”原代码误将“刚才”当非本人主体，独立只读复现；共享工作区已有另一session recent-workout修复，本线程不重复修改其文件。

## G2 方案与边界
待完整评审：结构化图片识别候选绑定当前用户、source message与图片；仅识别商品名称，不把标签每份含量当实际服用量。显式NAC2粒与其余各1粒需验证候选数量、NAC唯一匹配和单位；未知项保留未知并针对该项澄清。预览确认后走已有受控写入和逐项回执，失败/部分成功不能整体报成功。不得直接放宽target_mismatch或让OCR文字成为写权限。
缺少已授权真实模型评测入口的阻断仍在，不能以mock声称原图识别验证通过。图片批量记录完整功能尚未修复。

## G3 局部报错修复
先失败测试后修改：附图+补剂的target_mismatch说明“图片识别结果未能与本次要求逐项对应”，给出清晰标签或逐项名称数量的补充方式，明确未执行记录。其余target mismatch文案及所有写入校验不变。
未提交/未上线。待补真实流验证、独立审查及候选集成；本局部文案修复不算图片记录功能交付。

## 2026-10-10 聊天 UI 局部优化（未发布）

用户补充截图要求优化聊天界面，本次仅整理展示层，不更改补剂写入授权或失败判定。
- `ChatBubble`：全部图片具备可渲染 source 且尾部附件数吻合时，隐藏重复附件标记；保留原始消息用于复制、回放和无障碍。受保护图片无认证或数量不符时保留提示。
- `AnswerEvidencePanel`：没有详情且没有操作时不渲染空栏；只有处理日志时标题为“处理详情”，降低底色强调，真实来源和结构化依据仍为“回答依据”。技术耗时、模型、Token、失败详情继续可展开。
- 先新增失败测试，再做最小修改；初次 RED 包含三项目标行为失败，另一个复制按钮测试的标签写错已纠正。
- 最终相关 7 套 Jest / 166 项通过（`/tmp/reva-chat-ui-final.log`）；`npx tsc --noEmit` 通过（`/tmp/reva-chat-ui-tsc.log`）。
- 该组件未被 System Map selector 索引，已回到源码与实际组件测试核对。地图包装脚本因 PATH 无 python3.12 未能启动，另行直接执行现有 venv 下 checker。
- 无模拟器视觉验收、无固定 SHA CI、未提交/部署/OTA；继续遵守统一 owner 的提交冻结。

## 2026-10-10 外部 Agent 服用量契约补齐

用户新增截图：外部 Agent 宣称 NAC 2粒、其余各1粒已记录，却说明仅写入 taken。尚无该调用线上 trace，不能判定实际命中接口或补改历史记录。
代码确认数据库已有 `SupplementRecord.actual_dosage`，单条 `/api/v1/supplements/records` 和按名称 `/records/intake-batch` 均支持；旧按 ID `/records/batch` 的 item 缺字段且回执只有 action，形成接口能力不一致。

G2 局部方案 PASS：复用 actual_dosage，不新增 dosage_count、不迁移数据。按 ID 批量接口逐项接收明确实际服用量，返回落库 record_id/date/taken/actual_dosage。未提供时保留历史值；新记录未知量返回 null，不能据常规剂量/瓶身规格补全。本人校验仍在整批写入前；按现有同日唯一记录 upsert，不累加次数。日期由请求明确提供。旧数据不从截图自动回填。

客户端示例（合成 ID，仅说明接口）：
```json
{"record_date":"2026-10-10","checkins":[{"supplement_id":101,"taken":true,"actual_dosage":"2粒"},{"supplement_id":102,"taken":true,"actual_dosage":"1粒"}]}
```
回查 `/api/v1/supplements/me/date/{record_date}` 的 `record.actual_dosage`；不要读取 definition.dosage 当成本次数量。数量未落库时不得宣称该数量已记录。单条接口仍可使用已有 actual_dosage。

G3：两项新测试先 RED（422 拒绝 actual_dosage），实现后 SQLite 全部59项通过；继续补未知数量/非法载荷反例和真实 PostgreSQL 回读测试。OpenAPI 与 Web/Mobile 类型已由生成器同步。本局部契约修复不等于图片识别授权链路或外部 Noe 实测已完成。无提交/发布，遵守 owner 冻结。

### 数量契约本地收口证据
- SQLite最终64项通过，另补取消服用/显式null清除测试1项通过（共65项）；实际PostgreSQL首批59项通过并生成coverage（219.75s，`/tmp/reva-supp-dose-pg.log`），新增6项单独PG验证中。PG日志有测试schema drop/create期间后台scheduler查询已删除smart_reminders的噪声，不把这些日志当线上任务或业务验收证据。
- 两端API类型生成成功；Mobile与Web `tsc --noEmit` 均exit0；System Map直接checker与diff检查通过。最终生成变化仅新增批量请求数量字段、响应schema和说明；后一次重生成只更新字段注释。
- 独立安全文件预审GO，补null/取消语义后复审保持GO。非固定SHA G4，不代替完整CI/发布。审查确认并发首次插入仍可能触发现有唯一约束错误并返回失败；不得宣称并发无错重放。
- 数量仅凭显式请求落库；旧布尔接口调用不自动获得数量证明。外部Noe仍需刷新契约并提交actual_dosage、核对回执，未进行该端到端验证，也未回填用户历史记录。
- 最后新增6项真实PostgreSQL全部通过（`/tmp/reva-supp-dose-pg-final6.log`）；与首批59项合计覆盖65项，生产逻辑期间未变，仅补测试和OpenAPI字段说明。2026-10-10 12:22通过pg_ctl status确认测试PG已停止（no server running）。本地API契约修复完成，固定SHA审查、CI、部署及外部Agent实测仍待统一发布。

## 2026-10-10 发布后续修复断点

统一 owner 已确认 15a04365 后端/Web/OTA 持久成功；这不证明图片补剂完整链路交付。owner 已释放 agent_executor 本地编辑，仍禁止本线程暂存/提交/发布。
当前源码复核：SupplementDraftCard 的 actions 由外层处理；inline_cards._supplement_draft_actions 提供跳补剂页及问小巴，并非没有任何动作。atomic_capability_registry 将 supplement_draft 限为 route.open/suggest_only，尚无确认写入。附图单项及批量 health_record 的拒绝必须保留。
拟评估复用 write_intent.confirm/dismiss 的本人、来源消息、实际展示计划、原子执行与回执重放约束；不能只给卡片添加未经绑定的写按钮。共享 registry/write_intent_service 与生成地图修改已发 owner 协调，尚未修改这些源码。药物批量既有实现可作为边界参考，不直接将药物日志或剂量语义用于补剂。
本轮 System Map checker 通过；executor 路径未索引，已直接检查源码及 test_attachment_supplement_write_requires_text_confirmation。新增功能尚无 RED/GREEN 证据，未宣称实现。

### 图片候选数量绑定首个本地切片
owner 已允许本任务 registry/inline actions/write-intent 及生成地图本地修改，继续冻结提交发布。新增 photo_supplement_preview 纯函数与测试：仅处理明确的“记录四种补剂 NAC 2粒 其他各1粒”封闭语法，要求候选总数一致、NAC 唯一、名称完整且无重复；不从标签含量或模型 actual_dosage 推断摄入量，不接收模型 user_id。返回值只是不落库的待确认预览，不能用作写授权。
先缺模块收集失败，再占位实现获得实际 RED 2 failed/11 passed；实现后 GREEN 13 passed，日志 /tmp/reva-photo-supp-preview-{red,green}.log。未接视觉模型、持久来源绑定、卡片或写意图，尚无PG/端到端/G4证据。新服务文件带来的地图生成待后续同步；本切片不代表图片补剂记录功能完成。外部推荐TDD能力在本地skill路径缺失，遵照AGENTS测试先行；未启用superpowers。

来源绑定调查继续：AgentMessage 通过 AgentConversation.user_id 归属用户，图片URL在上传完成后写入 image_url JSON数组。现有 medication_intake_batch 确认会校验来源与持久化展示计划，water_backfill 则有独立confirm分支，可参考但不得共享领域写语义。独立只读设计审查 photo_supplement_binding_review 已启动，等待裁决后再接确认handler。System Map已重新生成，checker全通过，生成差异仅新增服务文件派生计数。

### 完整预览展示与持久意图实现中

独立设计审查裁决：纯展示 helper 可继续，完整写入链路在源绑定、完整持久卡、锁后TTL、事务回滚、回执回查与并发证据齐备前仍 BLOCK。采用独立 photo_supplement_intake kind，首版仅匹配本人已存在且唯一的补剂定义，不从图片自动创建定义。
Mobile SupplementDraftCard 新增 items/taken_date/decision_status 展示：所有条目逐项显示名称和明确数量，不截断第五项；终态区分已记录/取消/过期，保留原单项 suggestion 跳转流程。目标测试先 RED 5 项失败，实现后组件与 registry 共 107 项通过，tsc exit0，git diff --check 通过（/tmp/reva-supp-card-{red,green,tsc}.log）。这只是本地组件证据，无模拟器视觉验收、未发布。
独立服务 photo_supplement_intake 首轮 SQLite 16 项通过（/tmp/photo-supp-intake-final.log），仍未接 API/executor。主线程审读发现锁后TTL、终态回放核验真实记录、重复propose参数变化及事务释放、assistant完成状态/同turn绑定仍需补强，已交还实现者在原两文件范围补 RED/GREEN。尚未允许卡片写动作进入 registry/executor；不得将这轮单元测试当完整安全链路或真实PG验收。

### 确认服务加固与 API 分派切片

- helper 拒绝 NAC2/NAC600mg/NAC123 等无边界数字前缀：RED 3 failed/13 passed → GREEN 16 passed，/tmp/reva-supp-name-{red,green}.log。
- 服务第一轮安全加固 13 RED →29 GREEN；独立复审另发现覆盖助手全文、未冻结同名产品规格两项阻断。保留助手原文/其它元数据，合并顶层回执，冻结 definition_dosage/product_id 并确认锁后比较：新增4 RED →33 GREEN。规格值来自已有补剂定义，标记 strength_source=supplement_definition，不冒充OCR。
- Mobile 规格与本次数量分离，新增1 RED →组件及registry 108 GREEN，tsc exit0（/tmp/reva-supp-strength-{red,green,tsc}.log）。
- 真实 PostgreSQL 服务33+并发4共37项通过，43.58s（/tmp/reva-photo-supp-intake-pg-final.log）。两连接覆盖同源propose只有一个intent、重复confirm仅一批、confirm/dismiss竞争一致、不同source同日写一胜一冲突。图片读取使用合成fixture，不是真图识别或线上验收。
- 独立复审允许该服务切片进入API接线，仍非端到端/发布GO。write_intent_service 分派新kind confirm/dismiss，拒绝auto、从generic Home pending隐藏；API将领域冲突映射脱敏409，其它错误仍失败。分派5项先全RED，服务/API相邻合计42 SQLite GREEN（/tmp/reva-supp-dispatch-{red,green}.log）。分派+服务+并发真实PG最终验证中。
- 尚未接vision/executor、registry policy兼容、Mobile严格批次回执和过期分支，不能通过本切片按钮实际完成图片记录。仍禁止本线程暂存/commit/push/deploy/OTA。
- API分派5+服务33+真实并发4最终 PostgreSQL 42项全部通过，53.43s（/tmp/reva-supp-dispatch-pg.log）。测试PG fast shutdown请求60秒超时，尚未确认停止，需核验；不影响已退出0的测试结果。System Map checker与git diff --check通过。下一断点：先为Mobile补剂批次回执/终态分支写RED测试；再让build_card通过正式registry加policy后仍可精确确认，最后独立session接vision/executor，防服务commit提交共享dirty对象。
- 随后只读核验 pg_ctl status 返回 no server running，服务器日志明确 database system is shut down；此前超时是checkpoint/同步尚未完成，未强杀。测试PG最终已关闭。

### Mobile 回执与正式 registry 卡片接线

客户端补剂批次独立分支先10 RED/2 passed，实现后新12项与原chatCardActions共92 GREEN，tsc exit0（/tmp/reva-supp-actions-{red,green,tsc}.log）。确认/取消前要求同卡intent及完整逐项ID/数量/日期；成功要求全部supplement_record回执逐项匹配数量、日期、intent、资源类型及唯一性，禁止空回执泛化成功；取消竞争被确认赢得时返回可核验已执行结果，过期/取消不冒称已写入。
真实registry卡片往返测试先因动作未注册RED，再发现取消缺manual标记；已让build_card在生成阶段使用attach_action_policy_metadata，保留完整对象相等校验，并为confirm/dismiss都标注manual。supplement_draft允许受控write_intent动作，普通suggestion仍保留route.open。服务/API/registry组合最终结果见/tmp/reva-supp-card-contract-green.log。没有新增路由/schema；已更新地图并checker通过。
下一断点：尚未接vision/executor的结构化识别、独立事务propose、durable同轮卡片与流式输出；Mobile外层卡片终态刷新/实际点击仍需端到端验证。本轮不宣称完整图片功能修好或已上线；无暂存/提交/发布。

### 结构化图片名称与执行器接入中

新增 photo_supplement_recognition，只在封闭请求语法匹配后调用配置的vision服务，要求严格JSON名称列表，忽略模型身份/数量/日期字段，未知/缺项/HTTP错误均显式失败。调用者必须先执行现有AI同意校验；是否preprocess图片不能当作同意证据。识别适配先行为RED 6 failed/4 passed，后含helper29项GREEN（合成HTTP，未发送用户图片/未做真实模型评测）。
执行器持久用户原文会追加“附图数量”尾缀，导致服务闭合语法无法匹配。新增测试1 RED后修复：仅在已核验本人图片数量与准确尾缀一致时，从数量解析文本中移除该尾缀；源完整文本仍冻结并确认时重验。服务/识别/正式卡片49项GREEN，/tmp/reva-supp-caption-green.log。
agent_executor及真实run_stream测试由已分配实现者修改中，尚未最终审查/PG验收。要求propose与assistant持久化使用隔离session、同turn完整finalized卡、同意拒绝不调用模型、无补剂事实写入直到后续确认。不得在该断点宣称端到端完成。
- executor 接线首4项RED后，真实run_stream SQLite最终9项通过（/tmp/photo-supp-executor-final.log），包括原preprocess策略下合法请求可进入完整待确认卡、同意拒绝、缺配置、只读、识别错误/未知定义不进入泛化写入，隔离session不提交executor dirty。模型、媒体、同意测试均合成，非真实图片验收；下一步PG实际执行流和独立安全复审，以及客户端重载终态验证。

### 真实 PG 接线阻断与终态修复

PG运行真实stream+正式卡片11项初次4 failed/7 passed（/tmp/reva-supp-stream-pg.log），不能算通过。只读SQL定位AgentMessage.created_at无时区列默认datetime.now(UTC) aware，Asia/Shanghai连接落库偏移8小时，TTL正确拒绝未来source；已向owner协调消息时间默认值文件所有权。禁止通过放宽TTL或只改测试连接UTC掩盖生产问题。
独立复审另两阻断已先RED复现：API两连接预加载pending的identity map旧值导致第二次确认409；终态残留pending ID/kind。_intent现锁内populate_existing；_project仅清除本intent索引并在独占模式且无其它pending时重算outcome，保留其它回执/原文。真实PG服务38+并发5共43项GREEN，50.54s（/tmp/reva-supp-review-fixes-pg.log）。此证据不覆盖上述未修的消息时间问题。
Mobile历史恢复补supplement_draft scoped receipt/decisionStatus，ChatBubble补实际终态数据投影与补剂过期文案，均先RED；回归运行中。测试PG已发送fast shutdown，不使用强杀，最终状态待核对。
- Mobile终态恢复/点击/回执相关3套247项GREEN，tsc exit0（/tmp/reva-supp-terminal-{green,tsc}.log），diffcheck通过。测试PG最后status仍running（已收到shutdown），下一次需核验关闭，勿复用未结束进程跑drop/create。

### UTC 持久化修复与 Runtime 复审阻断

此前PG已正常关闭，本轮确认后重启专用55487测试端口。新增 test_agent_message_utc_persistence 在真实PG SET LOCAL TIME ZONE Asia/Shanghai 下1项RED，明确落库值偏移8小时。仅将AgentMessage.created_at既有无时区列的默认值改为UTC-naive，无schema变更、不调整历史数据、不放宽TTL；已通知owner协调。时间回归与真实stream/卡片契约共12项PG GREEN（/tmp/reva-supp-stream-utc-green.log）；服务/并发/API分派48项PG GREEN（/tmp/reva-supp-final-pg.log）；消息API及识别/helper相邻88项SQLite GREEN（/tmp/reva-supp-message-neighbors.log）。

独立只读复审仍BLOCK：新补剂confirm未复用Runtime现时owner-scoped写准入，可能绕过circuit_paused/unavailable。executor已知暂停入口先补2项RED，再禁止识别及生成可确认intent，整套stream12项SQLite GREEN（/tmp/reva-supp-runtime-{red,green}.log）。确认阶段在提议后新发生暂停的竞态尚未修复：需复用scoped reconciliation语义并持锁至写入提交，保留已执行intent只读回执重放；已向正在修Runtime事件的统一owner协调接口与锁语义，未改其Runtime文件。这是发布阻断，不是完整安全验收通过。

本轮无暂存/提交/发布；未做真实模型、用户照片、模拟器或线上个人数据验收。测试PG已请求正常fast shutdown，最终停止状态需后续核验。

### Runtime 确认准入本地收口

上一轮PG已确认正常停止。本轮未改owner的Runtime文件，仅在photo确认服务复用现有selection、singleton锁和owner-scoped admission：pending确认锁后refresh状态并现时重查，锁持有至记录/回执/终态同事务commit，SQL或配置不可用拒写；executed先验证原记录再只读重放。未解除任何账户暂停或改生产状态。

暂停后确认、控制不可用先2 RED（/tmp/reva-supp-confirm-runtime-red.log）；最初服务/API46 SQLite GREEN，后补scoped已ack暂停可通行与PG实际flush期间另一连接100ms锁超时、提交后可获锁。最终服务42+并发6+API5+stream12共65真实PG GREEN，80.70s（/tmp/reva-supp-runtime-final-pg.log）。独立只读复审解除本次Runtime旁路BLOCK，未发现新增可行动安全阻断，未独立重跑测试，非固定SHA G4。System Map checker与diffcheck通过。

已通知统一owner所复用的私有接口与锁语义，候选整合时需与其Runtime事件修复同步核验。此批可交本地代码整合审查，仍未提交、完整CI、部署、OTA或模拟器验收，不代表原始照片识别质量已验收。测试PG再次正常fast shutdown，最终停止状态待核验。

- 2026-10-10 22:18 后续核验：pg_ctl status 返回 no server running，专用测试PG已正常停止。统一owner仍在处理旧写入未决记录的恢复路径并核验补剂暂停边界；本线程未重复测试或操作发布。

- 2026-10-10 22:23 紧凑wait_threads确认统一owner本轮结束：其报告旧写入状态覆盖修复已有365项相邻/51项PG通过但未发布；线上旧写入结果仍未决，恢复需管理员认证入口，已在owner线程询问用户。此处仅记录owner报告，未独立复验其测试、不重复询问、不清除暂停。本补剂批次仍待统一整合与发布。

- 2026-10-11 01:00 owner最新报告：记录服务active，受影响账号新请求准入通过，保护检查未再暂停，旧1条未决记录及尝试/操作/消息摘要保持不变。仅为owner报告的服务恢复证据，不等于补剂候选已发布或真实补剂事实写入验收。已协调其恢复收尾后继续整合本补剂/时间/Mobile批次及Runtime兼容验证；本线程发布冻结不变。

## 2026-10-11 统一整合与原文授权加固

继续用户既有“整合全部 session 后发布”授权；以已部署 main `2456ccb795ef6971d39bdaa4053bb9b961be7eda` 为基线。Mobile 独立只读兼容验证 6 套相关 Jest 376 项通过、tsc exit 0，覆盖照片终态与现有周摘要/有界恢复。System Map 检查通过（新增三个服务由代码生成）。

整合审读发现对原文直接 strip 会把四空格/Tab 代码材料提升为候选请求；新增反例先 RED 4 failed/33 passed，复用现有原始材料过滤后 GREEN 37 passed。展示、识别分派和持久来源 propose 使用同一封闭请求检查；补源消息反例，不创建写意图或记录。确认仍要求完整持久卡、本人来源、冻结数量与定义、Runtime 锁下准入、原子写入、逐项数据库回执。

真实模型评测按用户长期指令跳过，不把合成图片/模型 fixture 当原图识别或个人记录验收。固定候选 PostgreSQL、独立 G4、CI-mode、完整 main CI、后端及 OTA 尚待后续证据。
