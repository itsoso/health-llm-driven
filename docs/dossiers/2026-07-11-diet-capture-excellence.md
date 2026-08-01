# Dossier: 饮食打卡极致体验

| 字段 | 值 |
|---|---|
| slug | `diet-capture-excellence` |
| 创建日期 | 2026-07-11 |
| 当前阶段 | S5 实现完成，G3 CI 待验 |
| 状态 | verification_pending |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile Jest + TypeScript / Simulator / backend deploy / EAS TestFlight + production OTA |

## Correct Course

- [x] Correction Block
  - 日期：2026-08-01。
  - 触发：用户确认小红书分享卡必须包含拍摄照片，并可在分享前完成基础图片编辑与隐私涂抹。
  - 旧基线：受保护餐食照片 5 秒未加载时，分享流程退化为完整 metric-only 海报并继续图片分享。
  - 新基线：已确认且 owner-accessible 的原始餐食照片先进入本地 3:4 编辑器，支持裁剪与缩放、90° 旋转、撤销、重做、重置和手动不透明隐私涂抹；完成后生成一次 `1080x1440` PNG，由完整预览、保存和系统分享复用同一个 rendered URI。照片缺失或加载失败时不生成图片海报，只提供重试或分享正文。
  - 设计：[`docs/plans/2026-08-01-xiaohongshu-diet-share-card-design.md`](../plans/2026-08-01-xiaohongshu-diet-share-card-design.md)。
  - 实施：[`docs/plans/2026-08-01-xiaohongshu-diet-share-card.md`](../plans/2026-08-01-xiaohongshu-diet-share-card.md)。
  - 安全 Gate：`privacy_sensitive`；原始 `DietRecord` 照片不可变，编辑与合成仅在本地副本完成，第一版不做自动 QR/条码识别。
  - 回退阶段：S3/S5；需重跑 G3/G4/G5/G6。当前为实现中，不把新分享流程记为已上线。
  - 本轮 Gate：G3=`PENDING`、G4=`PASS`、G5=`PENDING`、G6=`PENDING`；旧分享流程的测试、部署和上线证据只作为 Correction 前历史基线。
  - Run Ledger：`docs/_generated/harness-runs/7779bb67a50d.jsonl`（本地运行证据，不提交）。
  - 用户确认：☑

## S0 · 用户需求（逐字）

> 聚焦睡眠、运动和饮食三个主要功能。先把饮食打卡做到极致，准确性、性能和交互体验做到最好，并且可以分享小红书和微信，截屏，要有高级感，让95和00后人群感觉用这个App很有面子。

- 谁用 / 解决什么 / 现在怎么绕过：高频拍照、语音或文字记餐的 Mobile 用户；当前需要等待黑盒识别、手动核对一段合并文字，再以普通文本分享。
- 锚点用户相关性：饮食是每天发生多次的 Capture 闭环，也是睡眠、运动和代谢分析的数据基础。

## S1 · Discovery（现状勘察）

- 研发方式锁定：本改造必须按 Agent Native、Mobile First 进行。Mobile 是小巴对话链路里的高频 capture surface，不是独立饮食管理应用；相机、相册、文字、语音最终都要回到同一个 pending draft / confirmed DietRecord / Agent follow-up 链路。
- 已有可复用：
  - `mobile/app/diet.tsx` 已有拍照 -> 识别 -> 草稿 -> 人工确认 -> 写入状态流。
  - `backend/app/services/ai/food_recognition.py` 已输出结构化食物、份量、宏量营养和视觉置信度。
  - `backend/app/services/food_nutrition_lookup.py` 与 reviewed food table 已用于语音和聊天草稿，但未接视觉识别。
  - `backend/app/api/diet.py` 已有 owner-scoped 私有图片、写入幂等键和 fail-closed 内容防护。
  - `mobile/utils/share.ts` 已有系统分享和微信可接受的 Web 分享回退。
- 已证实缺口：
  - 视觉结果直接信任模型营养值，明确克数没有用 reviewed food table 校准。
  - 视觉 `meal_description` 可与清洗后的 foods 不一致；fiber 没有完整贯通响应。
  - 确认卡只显示合并描述，未展开每个食物、份量、来源和低置信度。
  - 照片 base64 在识别与确认写入间重复上传，且草稿未具备服务端可恢复身份。
  - 近 30 天生产聚合中饮食记录有数据，但 `ai_recognized` / `image_url` 均无有效样本，食物识别 caller 也无可用时延样本；主入口可观测闭环缺失。
  - 现有分享是文本/链接，没有适配小红书 3:4 与微信分享的图片卡。
- 硬约束：营养是估算，不宣称医学精确；确认前不写 DietRecord；图片 owner 隔离；不引微信私有 SDK；失败必须可见且可重试。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects：`ExecutionEvent`、`WriteIntent`、`HealthTwin`。
- core_loop_step：Capture -> 确认写入 -> Today/Review -> 分享反馈。
- target_surface / safety_level / autonomy_tier：Mobile + Diet API / privacy_sensitive / manual_confirm。
- spec_required：是；改变用户可见识别契约、健康写入数据来源和图片分享行为。
- smallest_end_to_end_slice：一张餐食照片得到可解释草稿，明确克数由营养表校准，用户确认后只写一次。
- stale_surface_to_remove：黑盒合并描述、无来源的伪精确营养、仅文本分享。
- **裁决：PASS**。用户已明确要求按优先级持续直接实施。

## S2 · PRD

- 链接：`docs/prd/2026-07-11-diet-capture-excellence.md`
- 引用权威：R5 Food Voice Capture、R10 Mobile 主体验、R4 确定性写入边界。
- 边界：不做诊断、处方、自动写入、食物秤级精度承诺或微信私有 SDK。
- Agent Native / Mobile First：端上只做一拍/一选/一句话到可解释草稿和确认；确认后的结构化事实进入小巴上下文，由 Agent 负责全天饮食、热量差额、下一餐建议、睡眠/运动联动和分享解释。禁止新增脱离小巴上下文的并行分析或并行写入路径。
- 未决问题：无阻塞问题；外部食物数据库和分享模版 A/B 属后续增量。

## S3 · 规划

- 设计：`docs/plans/2026-07-11-diet-capture-excellence-design.md`
- 实施：`docs/plans/2026-07-11-diet-capture-excellence.md`
- Feature Spec：`docs/specs/active/2026-07-11-diet-capture-excellence.md`
- 顺序：P0 准确性/可纠错 -> P0.5 单次上传/幂等 -> P1 图片分享 -> 真机/生产指标。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + 现有 DietRecord / private upload / system share contract 对照。
- 已焊入限制：只有明确重量单位才允许表值覆盖；无确定份量保留估算并降置信；分享必须用户显式触发；未确认草稿不可分享为“已记录”。
- 待拍板分叉：无。
- **裁决：PASS**。定义环文档无待澄清项，进入 P0。

## S4 · 研发任务分解

- [x] T1 视觉结果清洗、份量解析、营养表校准与 provenance（backend deploy）
- [x] T2 Mobile 分项确认卡、低置信提示和修正入口（OTA）
- [x] T3 服务端照片草稿身份、单次大载荷和写入幂等（backend deploy + OTA）
- [x] T4 3:4 高质感饮食分享卡、图片生成和系统分享（EAS）
- [x] T5 识别/确认/纠错/分享埋点与 p50/p95 看板（backend deploy + OTA）
- [x] T5.1 端侧照片压缩、相机返回后计时、成功样本分位数与无正文纠错率（backend deploy + OTA）
- [x] T5.2 模型输出边界、份量真实性、识别日志脱敏与可操作错误语义（backend deploy + OTA）
- [x] T5.3 Agent 草稿、写入连续性和确认卡回执的 iOS SecureStore 兼容（OTA）
- [x] T5.4 视觉模型升级、非思考结构化识别与延迟基准（backend deploy）
- [x] T5.5 单图相册降级、照片清洗信任边界与空闲态 Capture FAB（OTA）
- [x] T5.6 Agent Native Mobile capture deeplink：相机、相册、文字、语音确认后回小巴上下文（OTA）
- [x] T5.7 营养成分表图片与用户实际食用重量本地融合，保证图片、营养、记录和回执单次闭环（backend deploy）
- [x] T5.8 图片消息首个 SSE 确认前断流时，以 `client_turn_id` 核对 Runtime 持久化状态并恢复同一回合（backend deploy + OTA）
- [x] T5.9 失败写入的源消息恢复绑定：用户紧邻回复“重试/需要”时恢复原文字与图片，保留新回合幂等检查点；不确定写入禁止重放（backend deploy）
- [ ] T6 模拟器视觉、真机微信/小红书、生产数据闭环验收
- [x] T6.1 小红书照片必需的本地 3:4 编辑器、裁剪与缩放/90° 旋转/撤销/重做/重置/手动不透明隐私涂抹、完整海报预览，以及预览/保存/分享单一 rendered URI 复用（实现完成，待主干 CI、OTA 与真机目标应用验收；Run Ledger：`docs/_generated/harness-runs/7779bb67a50d.jsonl`）
- Agent Native 验收约束：每个新增 Mobile 饮食入口都必须证明三件事：Agent 可引用 pending draft 或 confirmed DietRecord；确认成功必须有 `diet_record_id` 回执；用户能在小巴对话里继续追问、修正或查看全天影响。
- 并发检查：2026-07-11 `origin/main` 与当前干净集成 worktree 一致；原始用户工作区不纳入暂存。

## S5 · 实现

- T1：明确克重且命中审核食物表时覆盖模型营养值；只有数据层 `calibration_names` 显式批准的身份可覆盖，部分表字段采用 `mixed` 来源，“鸡肉/鸡蛋/豆腐”等泛化名称保留视觉估算并提示核对。商业多模态模型收到食物语境或 Mobile 默认纯图片提示时也必须先经过同一清洗与校准链路；普通视觉降级描述明确禁止作为饮食写入参数。
- T2：确认卡展示逐项食物、份量、热量、置信度、营养表/视觉估算来源，低置信或未校准份量提示核对。
- T3：识别成功返回 owner-scoped `photo_draft_token`，确认不再重复上传 Base64；确认、取消和过期清理用行锁串行化，成功确认后由 DietRecord 接管图片并删除草稿行，取消/过期擦除识别正文且在图片删除成功后删行，删除失败保留最小重试句柄并显式报错。正式记录删除采用可恢复 tombstone，每日任务按数据库引用恢复或物理删除。Mobile 以用户隔离的 SecureStore 保存 24 小时紧凑快照，不保存 Base64 或无界模型正文，进程重启后可恢复并继续确认或取消；缓存写入失败不阻断服务端确认，App 启动即执行过期物理清理。
- T4（2026-08-01 Correction 前历史基线）：新增固定 3:4 饮食故事卡；iOS 以 point/PixelRatio、Android 以 bitmap pixel 分别请求，模拟器实测输出 1080x1440 PNG。等待受保护图片加载，5 秒无终态自动使用指标版卡片；图片或原生捕获不可用时降级为不含私有 URL/标识的文本系统分享，系统分享结束后释放临时 PNG。分享图不含用户名或其他健康数据。该 metric-only fallback 已被本轮 Correction 替代，不是当前实现目标。
- T5：新增无正文的识别/确认/分享终态事件，观测聚合直接输出各阶段样本数、失败数、p50、p95；识别响应另带 vision/calibration/photo_draft/total 分段耗时。
- 上线前复核发现生产 `food_items` 为空，原校准迁移只能更新既有行，导致营养表校准在生产无法命中。标准部署现于受控迁移后幂等执行 `seed_food_nutrition.py`，并以测试锁定 6 项审核食物、6 项营养值和严格 `calibration_names`，不允许泛化“鸡肉”进入鸡胸肉校准范围。
- T5.1：相机不再直接生成 12MP 原图 Base64；饮食与聊天共用 OTA-safe 图片承重工具，最长边限制 1568px、JPEG q0.7 且不放大小图，并在识别/草稿持久化后清理临时编码文件。相机返回后显示“正在优化照片”，完成后才开始上传识别；埋点新增无正文的端侧准备耗时、压缩后字节数和确认纠错标记。观察看板只以 completed 样本计算 p50/p95，同时单列 attempts、failures、cancelled 和 correction rate，避免把取景和取消时间当成模型时延。
- T5.2：视觉 JSON 现在经过字段白名单、有限数值、最多 12 项、重复项和 intake intent 清洗；药物、补剂、卡片文字不会进入饮食草稿，负值/非数字/越界置信度转为未知。照片份量新增 `portion_basis` / `portion_confidence`，营养表校准后仍保持视觉估算；Mobile 显示“表值 × 估算份量”和定性识别信号，不再把模型自报置信度展示为精确百分比。正常与异常识别日志只记录长度、计数和错误类型，供应商正文、食物名和异常正文不写日志或回传。
- T5.3：iOS 原生模拟器暴露对话草稿、最新已验证写入回执和确认卡防重复回执使用了带冒号的非法 SecureStore 键，导致草稿恢复、跨轮饮食上下文和卡片回执静默降级。三类敏感值现使用仅含字母、数字、点、下划线和连字符的用户隔离键；AsyncStorage 元数据/索引键保持兼容，旧版 completion tombstone 继续可识别，且不再尝试删除从未能写入 Keychain 的非法旧键。
- T5.4：生产视觉模型仍停留在官方已列为旧版的 `qwen-vl-max`。公开餐食样本对比确认，直连 DashScope 的 `qwen3-vl-flash` 在非思考模式下保持合法结构化结果，并避免把外观相似的裹酱鸡肉高置信猜成宫保鸡丁；食物识别服务现只对 Qwen3 视觉模型显式发送 `enable_thinking=false`，旧 provider 保持兼容。
- T5.5：饮食 FAB 新增单图相册入口，相机与相册只在取图阶段分叉，后续共用 1568px/JPEG q0.7 预处理、识别、服务端草稿、SecureStore 恢复与人工确认。照片候选已通过 Backend 结构化食物清洗，Mobile 不再用把“片”视作药片的通用文字启发式二次拒绝“橙子片”等食物；文字、语音和外部草稿仍保留本地防护。Capture FAB 只在 `idle` 显示，选图、识别、待确认、修正和保存时隐藏，避免遮挡确认卡和并发取图。
- T5.6：`/diet?capture=photo|library|text|voice&return_to=chat` 全部进入同一 quick draft 状态机；确认成功后统一把 `diet/quick_capture`、`diet_record_id` 和本餐结构化摘要推回小巴对话上下文。这样 Agent 对话可以继续回答“全天热量如何、下一餐怎么调、刚才那餐要不要修正”，Mobile 不再只有拍照入口能完成 Agent Native 闭环。已有草稿恢复或当前页面已有 quick draft 时不会再启动第二个 capture，避免从后台/重载回来重复弹相机、相册或输入框。
- T5.7：包装营养成分表只允许视觉模型提取标签基准值（每 100g 或每份），用户输入的实际食用重量只在受信任的后端本地解析和换算，不把整段健康对话追加发送给视觉供应商。标签营养不再被通用食物表覆盖；缺少或存在多个重量时 fail closed 并明确要求补充，不得把标签基准量误写成实际摄入。恢复结构化识别错误分支依赖的餐食语境判断，并用完整 `run_stream` 回归锁定：同一回合只写一次，图片关联、饮食卡和写入回执使用同一 `DietRecord`，模型冗余的不完整写调用不能覆盖成功结果。
- T5.8：iOS 在 App 切换、弱网或上传大图时可能先收到 XHR `onerror(status=200)` 或 SSE 正常关闭，首个 `request_persisted` 事件却尚未抵达设备；旧客户端把传输断开等同于业务拒绝，错误保留草稿并显示“发送失败”，用户重试后存在重复记录风险。Backend 新增 owner-scoped、无健康正文的回合状态查询，只返回 Run、持久化、会话和重试控制元数据；图片上传前创建的消息占位行不构成成功回执，只有 Runtime 绑定了 source message 才返回 `request_persisted=true`，部分 assistant checkpoint 也必须有 `client_turn_finalized=true` 才算最终回复。Mobile 在首个确认前断流时以原 `client_turn_id` 做最多约 1 秒的短暂核对；权威确认后清理草稿并从持久化历史恢复服务端图片和最终回复，失败、取消或待核对 Run 则映射为对应终态而不是继续显示“处理中”。无法取得权威状态时仍保持 fail closed，不会凭 HTTP 200 猜测成功。

## G3 · 测试闸

> 以下测试证据属于 2026-08-01 Correction 前的历史基线，不证明本轮可编辑小红书分享流程已完成。

- 最新 focused backend regression：179 passed、1 PostgreSQL-only test skipped；同一并发测试在本机真实 PostgreSQL 运行 1 passed，覆盖 confirm/confirm、confirm/cancel、confirm/purge、cancel/purge。
- 合并最新主干后 full Mobile regression：233 suites、1625 passed；最终整改 focused regression：40 passed；TypeScript check passed。
- managed migration：SQLite 12 passed；PostgreSQL 实跑确认 `豆腐` 默认不校准、`北豆腐` 可校准、未知行默认关闭。
- Dossier consistency、OpenAPI type generation、system-map generation、doc-drift checks passed。
- iPhone 17 Pro 模拟器原生构建成功；430x932 页面和分享预览无重叠，系统分享面板成功接收 PNG；像素检查为 1080x1440、非空图像。
- LLM live-change regression gate：invariants 12/12、health_agent_core 50/50、真实 orchestrator 5/5，平均分 0.94；原始证据保存在本机 `/tmp/harness-live-final-20260711.log`。闸门同时修正两项既有误报：空数据回答允许提及待补指标但仍禁止串入其他 case 的具体数值；LLM judge 现在可见该 case 的 Twin / specialist 证据，不再把有来源的个性化数据误判为编造。
- Linux CI 的原 `s-u` 大分片连续两次在 `test_telegram_webhook.py` 完成后、进入 `test_timeline_agenda_lifecycle.py` 前停住；同命令本机 1090/1090 在 133.21 秒通过。为隔离进程级顺序污染且保持覆盖完整，将该分片拆成 `s`、`t[a-e]`、`t[f-z]+u` 三个独立 pytest 进程。第三次 run 中 `s` 和 `t[a-e]` 已通过，但新进程的 `t[f-z]+u` 仍超出 12 分钟；因此 Linux pytest timeout 改用可中断主线程的 `signal` 模式，该诊断分片开启逐测试输出，并为所有后端 shard 增加 20 分钟 job 上限，确保后续失败能给出具体栈而非无限等待。
- 营养目录部署补丁 focused regression：32 passed；`bash -n deploy.sh` 与全部 pre-commit hooks passed。
- Linux 全仓权威闸门：GitHub Actions run `29159958346` attempt 3 SUCCESS；四个首轮冻结分片均通过失败作业重跑恢复，最终 Backend tests enforcement 通过。
- 待执行：真机微信/小红书目标应用投递。Backend 全仓本地测试仍保留既有跨用例污染问题，Linux CI 为全仓权威闸门。
- 2026-07-12 上线前生产只读审计：近 30 天 116 条饮食记录中，AI 标记、图片、`food_id` 和新版饮食终态事件样本均为 0；因此当前不能宣称真实识别准确率或时延达标，需新 TestFlight/OTA 产生样本后再验收。
- T5.1 发布回归：Mobile 全量 `233 suites / 1626 tests`、受影响 focused `66 tests`、TypeScript 通过；Backend 饮食/营养/事件联合回归 `112 tests` 通过；lint `0 errors`（保留全仓 97 条既有 warnings）；pre-commit、doc drift 与 Dossier consistency 全绿。
- T5.2 发布前回归：Backend 识别清洗/营养校准/Diet API/Agent vision 联合 `74 tests` 通过；Mobile focused `24 tests` 与全量 `233 suites / 1626 tests` 通过；TypeScript 通过，OpenAPI 生成仅新增 4 行份量字段；lint `0 errors`（97 条既有 warnings）；带项目 venv 的全部 pre-commit、doc drift 与 Dossier consistency 通过。独立审查另以 RED 测试修复“益生菌酸奶”被补剂规则误删的假阳性。
- T5.3 原生存储回归：先以严格 SecureStore 键校验得到 15 个 RED 失败，并以 2 个 RED 用例锁定遗留清理失败不得阻断新存储；最终 focused `5 suites / 114 tests`、全量 `233 suites / 1632 tests` 通过；TypeScript 通过，lint `0 errors`（97 条既有 warnings）。iPhone 17 Pro 模拟器连续重载仅保留无定位能力的 GPS 警告，不再出现 `[ChatInputBar] draft restore failed`、`draft persistence failed` 或非法 SecureStore 键错误。
- T5.3 Linux 权威闸门：GitHub Actions run `29170917830` SUCCESS，24/24 作业完成；`t-f-v` 首次尝试按 600 秒截止时间终止，干净进程重试后 `266 passed`，最终 Backend tests enforcement 通过。head commit 为 `401ec2810e2073e84ac571d108c44bbe3c8f5216`。
- T5.4 本地只读基准：同一 Mobile 1568px/JPEG q0.7 输入下，旧 `qwen-vl-max` 两张餐食耗时 11.9s / 13.5s，新 `qwen3-vl-flash` 为 6.0s / 6.3s，平均从约 12.7s 降至约 6.2s；非餐食 App 截图在 1.7s 正确拒绝。TokenPlan 的 `qwen3.6-flash` 与 `qwen3.7-plus` 路径分别约 20s 和 13.6-17.9s，未采用。配置和请求契约先得到 2 个预期 RED，最终识别安全回归 `12 passed`；修改后真实服务复测成功。显式 live LLM gate 另通过 invariants `12/12`、health-agent-core `50/50`、真实 orchestrator `5/5`，平均分 `0.94`、无 regression。
- T5.4 Linux 权威闸门：GitHub Actions run `29172663161` SUCCESS；backend quality、type drift、Frontend、Mobile、macOS、18 个后端分片与最终 Backend tests enforcement 全部通过。`agent-i-z` 与 `t-f-v` 首进程达到 600 秒截止线后由 CI 脚本终止，干净进程重试后分别在 11m27s / 11m40s 完成，未隐藏断言失败。
- T5.5 先以 RED 锁定相册入口、单图识别和取消恢复，再以现场公开餐食图复现“橙子片”被误判成药片并增加 RED；模拟器首次实测发现预授权会主动弹出全图库权限，依据 Expo ImagePicker 当前纯图片契约删除预请求，并以 2 个 RED 锁定成功/取消路径都不请求全图库。最终相册/内容边界/FAB focused regression `3 suites / 40 tests`、Mobile 全量 `234 suites / 1636 tests` 与 TypeScript 通过。全量 Jest 断言完成后仍报告仓库既有 open handle，使用 `--forceExit` 取得明确 0 退出码；不把该警告表述为已修复。iPhone 17 Pro 模拟器完成相册 -> 生产识别 -> 3 项待确认草稿，进程重载后草稿恢复且 Capture FAB 不再遮挡卡片。
- T5.5 Linux 权威闸门：GitHub Actions run `29174866840` 最终 SUCCESS；Mobile TypeScript/Jest、Frontend、macOS、type drift、backend quality、18 个后端分片与 Backend tests enforcement 全部通过。首轮仅既有 `test_exercise_dedup` 在高负载 runner 上跨过生产代码的 1 秒去重窗口而失败（测试文案仍写 5 秒），失败分片干净重跑通过；本轮没有后端代码改动。
- T5.6 RED/GREEN：先用 RED 证明 `capture=library&return_to=chat`、`capture=text&return_to=chat` 和 `capture=voice&return_to=chat` 均不会触发对应入口；再补最小 switch 分发。最终 `mobile/app/__tests__/dietCapture.test.tsx` 完整回归 `30 passed`，覆盖四种入口确认后均通过 `pushChatWithContext` 带 `diet/quick_capture` 上下文回到小巴。聊天入口 focused regression `4 passed`；`npx tsc --noEmit` 通过；Mobile lint `0 errors / 97 existing warnings`；Mobile 全量 Jest `234 suites / 1639 tests` 通过，仍保留仓库既有 open handle warning，不表述为已修复。
- T5.7 RED/GREEN：先复现营养标签按 100g 返回后未结合“20 克”实际食用量、通用食物表覆盖标签值、错误分支调用缺失方法三类问题；最终食品识别/营养校准/Agent 图片写入 focused regression `59 passed`，饮食写入、图片事务、回执和恢复相关扩展回归 `264 passed`。完整流式用例验证 20g 坚果由 655 kcal/100g 换算为 131 kcal，生成且关联唯一记录和图片，缺少食用量时零写入并要求补充。
- T5.7 真实模型回归（2026-07-27）：首次隔离 SQLite 因缺少 `llm_usage_logs` 被成本护栏 fail closed，未发生有效模型放行；初始化独立临时成本账本后重跑，`invariants 12/12`、`health_agent_core 50/50`、真实 `orchestrator 5/5` 通过，Orchestrator 平均分 `0.98`、无 regression，11 项轨迹契约全部通过。实际模型为 `MiniMax-M2.5`，原始 JSON 仅保存在本机 `/tmp/diet-photo-live-llm-eval-20260727.json`。
- T5.8 RED/GREEN：先以 `网络请求失败 (status: 200)` 且首个 SSE 持久化事件未到达复现客户端误判，RED 证明状态核对从未调用；新增 Runtime 状态接口后，Backend owner isolation、无正文响应及“图片占位消息/部分回复不得提前确认” `3/3` 通过，Runtime API/Service 扩展回归 `65/65` 通过。Mobile 覆盖异常断流、clean close、服务端图片 URI 恢复、部分回复保持运行和不可重试终态映射，相关输入、图片草稿、聊天流和恢复回归 `164/164` 通过；TypeScript、OpenAPI 双端生成类型、目标 ESLint（0 error）与 Python Ruff 均通过。
- T5.9 RED/GREEN：先复现失败助手询问是否重试后，用户回复“需要”只把两个字送入新 Run，原始饮食文本、营养和图片全部丢失；新增内容最小化 `retry_source_turn` 绑定后，恢复链路、目标约束和完成状态 `113/113` 通过，Agent 核心回归 `451/451` 通过，Runtime API、并发、reconcile 与断流恢复 `224 passed / 3 skipped`。测试覆盖 owner/conversation scope、紧邻顺序、重试的重试、客户端同 Turn 接管、原图片复用不重复上传、已验证/不确定写入禁止重放，以及含明确营养数值时保留营养但不误拆“牛肉和风沙拉”等完整菜名。
- T5.9 最终回归（2026-07-28）：合并最新主干后恢复链路、目标约束和完成状态 `119 passed`，Agent 核心 `452 passed`，Runtime API、并发、reconcile 与断流恢复 `224 passed / 3 skipped`，完整恢复测试文件 `25 passed`；真实模型闸门 `invariants 12/12`、`health_agent_core 50/50`、`orchestrator 5/5` 通过，Orchestrator 平均分 `0.94`、无 regression。实际模型为 `MiniMax-M2.5`，原始 JSON 仅保存在本机 `/tmp/agent-write-recovery-live-eval.json`，不提交模型回答或健康正文。
- T6.1 实现：聊天卡与饮食记录页统一进入 `DietShareComposer`；已确认且 owner-accessible 的照片先在本地编辑副本中完成缩放裁剪、90° 旋转、撤销/重做/重置和不透明隐私涂抹，再只捕获一次 `1080x1440` PNG。完整预览、保存和系统分享复用该 URI；关闭或重试时按 session generation 隔离异步回调并幂等清理捕获、物化和编辑临时文件。无照片、照片加载失败或捕获失败时不生成 metric-only 海报，仅保留重试或去标识正文分享。
- T6.1 本地回归（2026-08-01）：Mobile 全量 `287 suites / 2256 passed / 1 skipped`；分享、编辑、隐私、聊天、饮食入口与遥测 focused `9 suites / 221 passed`；TypeScript、Expo lint、设计令牌闸均通过，raw hex 从基线 `599` 降为 `596`。Backend 事件契约与观测回归在真实 PostgreSQL 上 `96 passed`。iOS dismissed 与原生可识别的取消单列 `cancelled`；Android `expo-sharing` 无法区分完成与取消，因此不伪造终态。移动端独立分享白名单和 Backend schema 均拒绝其他饮食指标、任意错误码、`image_uri`、食物正文、记录 ID 与热量等私有字段。
- T5.2 首次 CI run `29164922239` 中 type drift 在补齐 Frontend 生成类型后通过，但 Linux `a-b` 分片连续两次远超历史绿灯的 4 分 23 秒，并在 `test_agent_health_manage.py` 与 `test_agent_intervention_cycle_tool.py` 边界失去输出；该边界组合本机 `30/30` 通过，`c-d` 重跑也在 3 分 36 秒通过。判定为既有进程级顺序污染而非饮食断言回归，将 86 个 `a-b` 测试文件拆为非 Agent、`agent_[a-h]`、`agent_[i-z]` 三个互斥进程；文件覆盖校验为 `86 -> 86`、差集 0。
- T5.2 CI run `29166225719` 验证上述三个新分片分别在 3 分 2 秒、2 分 15 秒和 1 分 24 秒通过；同轮旧 `t[f-z]+u` 分片在 69% 处进入 `test_twin_builder.py` 后冻结，并被 20 分钟上限终止，其他 16 个作业均通过。本机同命令 `392/392` 在 31.23 秒通过；据逐用例日志将其拆为 `t[f-v]`、`t[w-z]`、`u` 三个干净进程，原 24 个文件覆盖校验仍为 `24 -> 24`、差集 0。
- T5.2 CI run `29166933157` 中 `t[f-v]`、`t[w-z]`、`u` 已分别在 1 分 44 秒、1 分 25 秒和 1 分 28 秒通过；唯一剩余的旧 `s` 大分片进入 `test_schedule_into_agenda.py` 后失去输出，其他 18 个作业均通过。本机同一 643 项命令也在该模块首个用例后停住，但该模块单跑 `8/8`、与前一模块配对 `26/26`、`s[c-k]` 分组 `55/55` 均通过，确认是更长前序造成的进程状态污染；将 58 个 `s` 文件拆为 `s[a-b]`、`s[c-k]`、`s[l-z]`，覆盖校验为 `58 -> 58`、差集 0。
- T5.2 CI run `29167500244` 验证三个新 `s` 分片分别在 1 分 22 秒、1 分 32 秒和 3 分 34 秒通过；唯一剩余的旧 `n-r` 大分片超过 16 分钟无输出，其他 20 个作业均通过。本机同一 808 项命令也在 `protocol` 区域后停止输出，而独立 `p` 分片 `239/239` 在 69.61 秒通过；将原 87 个文件拆为 `n-o`、`p`、`q-r` 三个进程，文件覆盖校验为 `87 -> 87`、差集 0。
- T5.2 最终 Linux 权威闸门：GitHub Actions run `29168150924` SUCCESS；18 个后端测试分片、backend quality、最终 Backend tests enforcement、type drift、Frontend、Mobile 与 macOS 全部通过，head commit 为 `c6d3d3f4942fee7a1f92730f33d9326d600be4c0`。
- Linux 全仓权威闸门：GitHub Actions run `29163241845` SUCCESS；frontend、Mobile、macOS、type drift、backend quality、10 个后端测试分片及最终 backend enforcement 全部通过。
- **2026-08-01 Correction 前历史裁决：PASS**。
- **本轮 G3 裁决：PENDING**。本地实现与回归已通过；仍须以提交后的主干 CI 作为集成权威闸门，不能只凭本地测试进入部署。

## G4 · 安全闸

> 以下安全证据与 PASS 裁决属于 2026-08-01 Correction 前的历史基线。

- 触发：健康数据写入、AI 营养估算、私有图片和社交分享。
- 已落实：owner scope、确认/取消/清理行锁、真实 PostgreSQL 竞态证明、确认幂等、取消后正文擦除、草稿与正式记录图片失败可重试、SecureStore 用户隔离且非阻断、恢复前服务端 token 终态校验、编辑时 Mobile/Backend 双层 provenance 清理、分享前显式操作、分享产物去身份化和临时文件释放。
- T5.9 安全复核：恢复控制面只保存 source/root/trigger message id 和原因码，不保存健康正文、工具参数或图片内容；源消息和图片读取强制 owner scope；仅明确 retryable 且没有回执、没有 `in_flight/uncertain/verified` 检查点时提供动作。恢复 Run 使用新的 client turn 写入检查点和幂等身份，原图片只作为 owner-scoped 媒体来源复用。
- T6.1 自动化安全证据：原始 `DietRecord` 与原照片只读，所有编辑作用于本地副本；涂抹 SVG 与导出叠层均锁定 `strokeOpacity=1`、圆头与圆角；低置信视觉结果隐藏精确宏量值和个性化建议；海报不渲染用户名、内部 ID、照片 URI、来源 token 或置信度；所有临时资源关闭/重试时 exact-once 清理。分享终态遥测只含 phase、duration、has_photo、枚举 target 与错误码，客户端和 Backend 双层白名单拒绝健康正文及标识符。
- T6.1 最终双重独立复核：规格审查与代码质量/安全审查在修复分享遥测字段夹带、自由错误码夹带、平台终态矩阵和不透明颜色约束后再次检查，均未发现 Critical、Important 或 Minor；定向复核分别验证 Mobile、Backend PostgreSQL、TypeScript、设计令牌与 diff hygiene。
- 同一独立审查代理连续五轮核对；最后一轮未发现 P0/P1/P2。
- **2026-08-01 Correction 前历史裁决：PASS**。
- **本轮 G4 裁决：PASS**。自动化安全证据与双重独立评审均通过；真机导出像素与目标应用接收不冒充安全代码审查证据，继续归 G6 验收。

## S6 · 部署（2026-08-01 Correction 前历史基线）

- 路由：backend deploy -> type sync -> TestFlight。因新增原生分享依赖，本版本不向缺少该模块的旧二进制发送 OTA。
- Backend 已从干净的 `origin/main` 完成第三次增量部署；最终生产 commit 为 `612de0bc54aa0b83f25ee4a116a0b161bc08820d`。
- 第三次部署前 PostgreSQL 备份：`/opt/health-app/backups/health_db_2026-07-12_02-27.sql.gz`，38 MB，权限 `0600`，完整性与 force-RLS 检查通过。
- TestFlight 构建：版本 `1.3.1 (221)`，EAS build `a6886f1c-d94f-4463-8a2e-90aeb12bce4c`；submission `4e54e7b1-1a9c-498c-8569-83deb950514a` 已成功上传 App Store Connect。
- production OTA：runtime `1.3.1`，update group `7a83e627-d87d-49df-8a83-de59c2867567`，iOS update `019f5272-ec99-760e-ad91-7097c018a0db`；EAS `update:view` 复核 branch、commit、runtime 与非回滚状态一致。
- T5.2 后端从干净且与 `origin/main` 一致的 worktree 通过 `./deploy.sh -b` 增量部署，生产 commit 更新为 `c6d3d3f4942fee7a1f92730f33d9326d600be4c0`；本轮无新迁移。
- T5.2 部署前 PostgreSQL 备份：`/opt/health-app/backups/health_db_2026-07-12_05-12.sql.gz`，38 MB，权限 `0600`，两张 force-RLS 表的数据段完整性检查通过。
- T5.2 production OTA：runtime `1.3.1`，update group `2f5f9559-9838-404a-a03c-ebdfb3c334c9`，iOS update `019f530b-0ec6-7838-aaa3-721414a37189`；EAS `update:view` 复核 branch=`production`、commit、runtime 与 `isRollBackToEmbedded=false` 一致。
- T5.3 production OTA：runtime `1.3.1`，update group `2a6f06a0-2e83-454e-a98f-a10fc0b11e9f`，iOS update `019f5364-6518-7807-b4d9-c8433f7c8c59`；EAS `update:view` 复核 branch=`production`、commit=`401ec2810e2073e84ac571d108c44bbe3c8f5216`、runtime 与 `isRollBackToEmbedded=false` 一致。
- T5.4 后端通过干净 worktree 的 `./deploy.sh -b -y` 部署，生产 Git HEAD 为 `087808dd3e45619f5fa2a6f052ed65c622ab551a`，环境已同步为 `LLM_VISION_MODEL=qwen3-vl-flash`；本轮无新迁移。
- T5.4 部署前 PostgreSQL 备份：`/opt/health-app/backups/health_db_2026-07-12_07-59.sql.gz`，38 MB、权限 `0600`，两张 force-RLS 表的数据段完整性检查通过。
- T5.5 production OTA：runtime `1.3.1`，update group `8831e015-4afd-4871-839f-741147b67776`，iOS update `019f53f4-ba80-7e83-9050-ccd6faeaa2ac`；EAS `update:view` 复核 branch=`production`、commit=`d8cdc1d1e3d69eaf962615ddead3e57ebaecfae0`、runtime 与 `isRollBackToEmbedded=false` 一致。
- T5.6 production OTA：runtime `1.3.1`，update group `fd730fd7-22dd-4cd6-962a-260267e51f31`，iOS update `019f54d5-4bb7-7476-b49b-b9d5b95d837e`；EAS `update:view` 复核 branch=`production`、commit=`da579f055def97902f25c3a7edc3b0992d17df1d`、runtime 与 `isRollBackToEmbedded=false` 一致。
- T5.7 Backend 已从干净且与 `origin/main` 一致的部署副本通过 `./deploy.sh -b -y` 发布；生产 Git HEAD 为 `32ac803bc9f36f7c4e015f7045de6a6b551e6ed4`，本轮无新 migration。部署前备份为 `/var/backups/health-app/database/health_db_2026-07-27_21-16-48_221912.sql.gz`，41 MB、权限 `0600`，force-RLS 数据段、恢复演练和异地加密归档校验通过。
- T5.8 Backend 已从干净且与 `origin/main` 一致的部署副本通过 `./deploy.sh -b -y` 发布；生产 Git HEAD 为 `b2ee0ec6c19ebf79fd227cf97a3050cc0b7b226a`，本轮无新 migration。部署前备份为 `/var/backups/health-app/database/health_db_2026-07-27_23-28-00_233292.sql.gz`，41 MB、权限 `0600`，force-RLS 数据段、234 表恢复演练与站外加密归档哈希/HMAC 校验通过。
- T5.8 production OTA：runtime `1.3.2`，update group `d1c14bea-b018-4e28-a0b0-5a7352986ed0`，iOS update `019fa439-1a11-79ce-9b93-65c0a5011016`；发布脚本复核 channel=`production`、commit=`b2ee0ec6c19ebf79fd227cf97a3050cc0b7b226a`、active group/update 与发布结果一致。
- T5.9 Backend 已从干净且与 `origin/main` 一致的部署副本通过 `./deploy.sh -b` 发布；恢复逻辑代码提交为 `6c2b1c48`，生产 Git HEAD 为 `4bd96fa62a75da8a8b06aee8ccc76764bcf205f7`，本轮无新 migration。部署前备份为 `/var/backups/health-app/database/health_db_2026-07-29_10-32-43_309421.sql.gz`，41 MB、权限 `0600`，force-RLS 数据段、234 表恢复演练与站外加密归档哈希/HMAC 校验通过。该变更为纯 Backend，不发布 Mobile OTA。

## G5 · 部署健康闸（2026-08-01 Correction 前历史基线）

- 生产受控迁移状态正常：`20260711_200000_create_diet_photo_drafts` 与 `20260711_201000_add_food_calibration_names` 已应用，本轮无重复迁移。
- 部署内营养目录 seed 明确输出 `6 food_items, 6 food_nutrients`；部署后只读 SQL 复核为 6/6，豆腐校准名仅 `北豆腐/老豆腐`，鸡胸肉校准名不含泛化“鸡肉”。
- `health-backend`、`celery-worker`、`celery-beat` 均为 active；部署健康分 `60/60 PASS`；skills manifest 本地/线上均为 22。
- 公网及服务器本机 `/api/v1/health` 均返回 healthy，API、PostgreSQL、Redis、Celery 全部 connected/running。
- T5.1 增量部署后 `health-backend` 为 active；公网 `/api/v1/health` 再次返回 healthy，production OTA 已绑定同一代码 commit。
- T5.2 增量部署后 `health-backend`、`celery-worker`、`celery-beat` 均为 active，服务器 Git HEAD 为 `c6d3d3f49`，部署健康分 `60/60 PASS`；公网健康仍为 healthy，服务器本机 OpenAPI 的 `FoodItem` 已包含 `portion_basis` 与 `portion_confidence`。
- T5.4 增量部署后 `health-backend` 为 active，部署健康分 `60/60 PASS`，skills manifest 本地/线上均为 22；公网 `/api/v1/health` 返回 API、PostgreSQL、Redis、Celery 全部 healthy/connected。
- T5.7 增量部署后 `health-backend`、`celery-worker`、`celery-beat` 均正常，部署健康分 `60/60 PASS`；公网 `/api/v1/health` 返回 API running、PostgreSQL/Redis/Celery connected。公网 skills manifest 的 HTTP/2 请求出现可恢复传输告警，HTTP/1.1 已验证可读取有效 manifest，不影响 Backend 健康闸。
- T5.8 增量部署健康分 `60/60 PASS`，skills manifest 本地/线上均为 22；公网 `/api/v1/health` 返回 `healthy`，API running、PostgreSQL/Redis/Celery connected。
- T5.9 主干 CI run `30416635659` 全绿，包含 Agent Runtime PostgreSQL 语义、真实模型回归、Backend 全分片、Frontend、Mobile、Mac 与类型漂移闸门；一次性真实模型授权变量已在 CI 结束后删除。部署后健康分 `60/60 PASS`，skills manifest 本地/线上均为 22；正确生产入口 `https://health.executor.life/api/v1/health` 经正式域名 SNI 返回 HTTP 200，API running、PostgreSQL/Redis/Celery connected。
- **2026-08-01 Correction 前历史裁决：PASS**。
- **本轮 G5 裁决：PENDING**。可编辑小红书分享流程尚未通过主干 CI、production OTA 发布和发布后健康验证。

## S7 · 上线验证（2026-08-01 Correction 前历史基线）

- iPhone 17 Pro 模拟器已验证照片确认、固定 1080x1440 分享图、系统分享面板与无重叠布局。
- Backend 生产迁移、营养目录、服务状态和公网健康检查已验证。
- TestFlight `1.3.1 (221)` 已成功上传 App Store Connect；Apple 处理完成状态尚未单独核实，因此不宣称当前已可安装。
- build 221 对应 runtime `1.3.1` 的 production OTA 已发布；设备冷启或后台超过 30 秒后可拉取。当前生产仍无新版终态样本，不宣称真实 p50/p95 或纠错率已达标。
- T5.2 OTA 已绑定 build 221 的 runtime `1.3.1` 与生产 commit `c6d3d3f49`；当前仍不以模拟器、单测或模型自报置信度替代真机照片准确率与份量误差验收。
- T5.4 生产服务只读 smoke：同一公开 1568px 测试图在 8.755s 成功返回“甜酸口味鸡肉块、蛋炒饭、橙子片”等可见食物，未再误报为宫保鸡丁；测试图只临时写入服务器 `/tmp`，调用后已删除。该样本证明部署和模型路由生效，但不替代真实用户照片的 p50/p95 与纠错率。
- T5.5 模拟器实链路：同一公开餐食图经 Mobile 相册入口和生产 API 返回“橙子鸡、咖喱炒饭、橙子片”3 项草稿；修复前被 Mobile 二次误判为用药/补剂，修复后正常进入待确认且没有写入正式 DietRecord。截图保存在本机 `/tmp/reva-library-draft-no-fab.png`。
- T5.5 OTA 已绑定 build 221 的 runtime `1.3.1` 与代码提交 `d8cdc1d1e`；设备冷启或后台超过 30 秒后可拉取。真机相册权限体验、微信和小红书投递仍保持待验证，不以 EAS 发布成功替代终端验收。
- T5.6 OTA 已绑定 build 221 的 runtime `1.3.1` 与代码提交 `da579f055`；设备冷启或后台超过 30 秒后可拉取。自动化已证明相机、相册、文字、语音四种 Mobile 入口确认后都会带 `diet/quick_capture` 上下文回到小巴；真实设备语音输入和真机目标应用分享仍需继续验收。
- T5.9 失败写入恢复已部署至生产 Backend。自动化与真实模型回归已证明窄确认短语可以在同一用户、同一会话、紧邻顺序且没有已验证或不确定写入时恢复原文字与图片，并为新 Run 使用新的幂等身份；仍需在真机生产会话中人为触发一次可重试失败并完成“重试/需要”闭环，作为最终终端证据。
- 待真机验证：相机实拍 -> 识别 -> 修正 -> 确认单次写入，以及分享图分别投递微信和小红书。

## G6 · 验证闸（2026-08-01 Correction 前历史基线）

- 模拟器与生产后端验证通过；T5.9 生产部署与公网健康已通过，真机失败写入恢复及目标应用投递尚缺终端证据。
- **2026-08-01 Correction 前历史裁决：PENDING**。当时状态为 `device_validation_pending`，不进入完成态。
- **本轮 G6 裁决：PENDING**。待真机验证照片编辑、用户审阅完整预览、保存与小红书系统分享均复用同一 `1080x1440` rendered URI，且照片失败不生成 metric-only 海报。

## S8 · 沉淀

- 决策 1：审核营养目录是校准链路的运行时前置条件，必须由标准部署幂等补齐，不能只依赖可选手工 seed。
- 决策 2：新增原生分享依赖必须发新二进制；旧二进制禁止接收会引用缺失原生模块的 OTA。
- 决策 3：社交分享验收必须覆盖目标应用真机接收，不以系统分享面板出现代替微信/小红书成功投递。
- 决策 4：营养标签的基准份量与用户实际摄入量必须作为两个字段处理；视觉模型只提取标签，实际摄入换算在本地完成。任何标签图片写入都必须同时证明营养值大于零、图片已关联、写入回执可验证且没有并行失败文案。
