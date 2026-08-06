# Dossier: Agent 健康写入终态一致性

| 字段 | 值 |
|---|---|
| slug | `agent-write-outcome-consistency` |
| 创建日期 | 2026-08-06 |
| 当前阶段 | G4 最终复评 GO；进入提交、主干 CI 与部署健康闸 |
| 状态 | building |
| 负责 | Codex + release owner |
| 反馈环 | Backend deploy + Web deploy + Mobile OTA/1.3.3 candidate |

## Correct Course

- [x] Correction Block
  - 触发:第二张生产截图证明早餐图片问题不是孤立 bug，旧用药/补剂卡与 Agent 终态也可互相矛盾。
  - 旧基线:只修早餐草稿外键顺序和无图 fallback。
  - 新基线:增加跨饮食/用药/补剂的终态卡片一致性闸，同时修复两条已证实根因。
  - 回退阶段:S1
  - 需重跑 Gate:G1、G2、G3、G4、G5、G6
  - 用户确认(若 scope/风险变):已确认，2026-08-06
- [x] Correction Block（部署后生产烟测）
  - 触发:`记录这张早餐图片，仅用于发布验证` 被确定性路由为 AIGC；首次修正后又因 `图片` 包含裸 `片` 被误判为用药。
  - 旧基线:只验证图片资产保存和通用饮食写入不降级。
  - 新基线:餐次图片记录必须先进入 diet；只有显式生成媒体才进入 AIGC；裸 `片` 不再作为用药子串授权。
  - 回退阶段:S5
  - 需重跑 Gate:G3、G4、G5、G6

## S0 · 用户需求(逐字)

> “保存早餐还是有问题”
>
> “类似的bug还不少”

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1):核心用户在 Agent 中记录饮食、用药或补剂；当前只能看到矛盾结果后重试或转到独立页面核对。
- 锚点用户相关性:低摩擦、可验证的健康写入是 Mobile Agent 正式版核心路径。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `agent_write_outcome.py` 与 `agent_turn_outcome.py` 已按执行事实分类写入/回合终态。
  - `medication_intake_batch.py` 已有服务端 `WriteIntent`、手动确认、回执和幂等执行。
  - `agent.py` 是最终 query 派生卡片的统一组合点。
  - `contextual_meal_photo_service.py` 已有草稿与资产的单事务保存入口。
- 缺什么:
  - 用药批次解析不支持单药“数量在药名前”。
  - Agent 主分类器与摄入分类器对同一句话结论不同。
  - route-only 用药/补剂卡被客户端当作 pending。
  - failed/blocked 回合仍可追加 query 派生摄入卡。
  - 图片父草稿与子资产没有显式 flush 顺序；失败后通用饮食写入未被阻断。
  - 通用 `图片/图像` 先于具体健康域匹配；裸 `片` 又与 `图片` 发生子串碰撞。
- 硬约束 / 平台·安全边界:
  - 用药永久 `manual_confirm`；受控药名；不猜药、不改剂量。
  - 只有回执可证明成功；图片与记录失败必须 fail loud。
  - 不记录真实健康文本到 telemetry。

## G1 · 准入裁决

- first_class_objects:`WriteIntent`, `ExecutionEvent`
- core_loop_step:execution -> confirmed event -> Health Twin
- target_surface / safety_level / autonomy_tier:Backend+Mobile+Web / medical_boundary / manual_confirm
- spec_required:是，涉及跨端卡片契约与健康写入安全语义。
- smallest_end_to_end_slice:两条生产原句 + 共享 terminal card suppression。
- stale_surface_to_remove:route-only 卡片的伪“待确认”展示。
- **裁决**:PASS —— 修复既有核心写入闭环，不扩大自治范围。
- 用户确认:已确认。

## S2 · PRD

- 链接:`docs/specs/active/2026-08-06-agent-write-outcome-consistency.md`
- 引用的权威 R 号:R5、R11、R12。
- 边界(不做):不做状态机大重写、DB migration、药物建议或营养算法重做。
- 验收 Gate:回执/真实 pending/失败三态与正文、卡片、数据库一致。
- 未决问题:无。

## S3 · 规划

- 链接:`docs/plans/2026-08-06-agent-write-outcome-consistency.md`
- 分阶段 + 反馈环路由:Backend RED/GREEN -> card choke point -> Web/Mobile presentation -> G3/G4 -> deploy -> prod smoke -> iOS release resume。
- 长杆 / spike:PostgreSQL 父子 flush 顺序与生产合成账号验证。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge + 两次生产根因取证。
- 硬阻断(已焊进规划):不用 LLM 作为写入真源；疑问/否定/历史/未知药名继续拒绝；失败不生成替代写入入口。
- 待拍板分叉:系统性小切片、单句热修或总状态机重写；用户选择系统性小切片。
- **裁决**:PASS —— 用户于 2026-08-06 确认 B 方案。

## S4 · 研发任务分解

- 跨端 API 契约:Agent SSE 继续使用现有字段；只为 route-only legacy card 增加可选 `presentation_state=suggestion`。
- 任务表:
  - [x] T1 用药生产原句 parser/intent/zero-LLM flow。
  - [x] T2 终态 query card suppression 与 suggestion contract。
  - [x] T3 Web/Mobile 真实展示。
  - [x] T4 早餐图片父子原子保存与 no-fallback guard。
  - [ ] T5 餐食图片确定性路由修复、G3/G4、重新部署、生产验证与 1.3.3 release gate。
- 并发检查:已 fetch `origin/main`；开放 PR 无相同范围；隔离 worktree 基线与 `origin/main` 一致。

## S5 · 实现

- 委托:当前 Codex 会话，未使用子 agent。
- 分支/commit:`codex/ios-1-3-3-app-store-release` / 当前 HEAD（G4 review candidate）。
- 实现摘要:
  - 单个受控药物支持“数量在药名前”的明确已服句式，仍走 durable `WriteIntent` 手动确认。
  - Agent 主分类器只把确定性解析成功的药名后缀表达提升为用药域；模型提议入口在创建 `WriteIntent` 前强制限定受控别名或用户已有药物。
  - 失败/阻断终态在 API 卡片组合点压制 query 派生卡。
  - route-only 用药/补剂卡显式标记 suggestion，Web/Mobile 展示“待核对/去记录”。
  - 图片父草稿先 flush，再插入资产；失败或待确认关闭通用 diet 写入适配器。
  - 餐次语义优先于通用附件名词；显式“生成短视频”等创作请求仍优先进入 AIGC；移除会命中 `图片` 的裸 `片` 用药子串。

## G3 · 测试闸

- 已通过:
  - Backend 增量集成:419 passed（7 个相关测试文件，SQLite）。
  - Backend 图片执行器整套重跑:103 passed（实现整理后新鲜证据）。
  - G4 修复整组:216 passed（用药计划、Agent 完整流程、主意图分类、受控药物自动创建）。
  - PostgreSQL 16 真实语义:9 passed（未知药名拒绝、用户已有药物兼容、并发幂等、父子 FK/事务顺序与图片锁）。
  - Web:336 passed；production build 通过；全量 ESLint 0 error（33 个既有 warning）。
  - Mobile:2404 passed、1 skipped；TypeScript、design token gate 通过。
  - 结构/模型闸:secret scan、doc drift、101 dossiers、LLM live-change、12+50+12+9 个零成本回归全部通过。
  - 静态阻塞闸:Ruff F821/F822/E9 与 Python compileall 通过；`git diff --check` 通过。
- 路由回归新鲜证据:媒体授权对抗聚焦集 280 passed；分类器、工具裁剪、Agent capability/food vision 1057 passed；用药与 App Store release-pack 聚焦集 126 passed；基础 release-pack checker PASS。
- AIGC 确认链最终证据:后端确认/令牌/API/网关/能力/force 660 passed，分类器 579 passed；Mobile 卡片+通用 action 115 passed，Web 卡片 40 passed；release-pack 48 passed。Ruff、两端 TypeScript、两端 lint 0 errors、基础 App Store checker/preflight 与 `git diff --check` PASS；generated OpenAPI types 已同步并通过 worktree venv 临时全量重生成逐字节复核。
  - 审核账号 live gate:登录、身份、今日计划、每日工件、固定简报会话及精确合成消息对均 PASS；未输出凭证。
- 集成闸:当前路由候选本地闸与独立 G4 均通过；等待 commit 后主干 CI 真实色。
- main CI 真实色:pending。
- 跨家族 capstone:pending。
- **裁决**:pending（当前路由候选尚未进入主干 CI）。

## G4 · 安全闸

- 触发:用药 + 健康写路径。
- 首次独立评审:commit `9c0921031`；reviewer 发现未知“药名样式”可被宽泛分类器和 LLM medication tool 带入 durable `WriteIntent`，裁决 **NO-GO**。
- 回上游修复:分类器只提升确定性受控药名；`propose_medication_intake_items` 只接受受控别名/规范名或该用户已有 Medication，并新增服务边界、分类器、完整 Agent 流程负例。
- 修复后自审:未知名称在创建 `WriteIntent` 前 fail closed，零 MedicationLog；用户已有药物与受控药物兼容路径保留。
- 独立复审:commit `70ab2a63d`，17 个定向用例及动态跨用户反例通过；Critical / Important / Minor 均无，工作树和 HEAD 完整性校验通过；该裁决仅覆盖已部署的健康写入候选。
- 当前 Correct Course 首次独立复评:`G4: NO-GO`，无 Critical，发现通用图片既成事实、否定媒体生成仍可授权 AIGC 草稿，以及审核 live gate 可向 HTTP 或跨 origin redirect 泄露密码/Bearer token。
- 回上游修复:普通记录与既成事实不再把媒体域变成创作授权；媒体生成否定词在授权前 fail closed；工具裁剪必须核验 `media_generation_request` reason；审核请求 HTTPS-only 且禁止全部重定向，并在基础 URL 与每次请求双层校验。
- 同一 reviewer 二次复评仍为 `G4: NO-GO`，无 Critical：常见“不想/没让/不是我的意思”等后缀否定漏判；裸子串邻近法还误伤“分别/别的”、跨分句新指令和“取消旧任务后重新生成”。
- 二次回上游修复:否定识别改为显式短语、分句边界与局部重新授权关联；追加“取消重新生成”和后句无关否定边界后，53 个聚焦对抗用例先 RED 后全部转绿。
- 第三次独立复评继续报 `G4: NO-GO`，无 Critical：`不希望/没打算/不再/不应/不该/避免` 及 provider 确认表达仍可强制 AIGC 工具；“分别生成早餐图和午餐图”则被误归饮食域。
- 第三次回上游修复曾扩展显式否定短语并补充受控图片简称，但 reviewer 继续复现插入式否定、事实/状态陈述误授权，以及“否定旧动作后明确新动作”和内容约束被全句布尔误杀；正式裁决仍 `G4: NO-GO`（2 Important、无 Critical/Minor）。
- 架构级回上游修复首版移除“媒体目标 + 生成词”授权和全句否定布尔，改为分句/动作顺序的 fail-closed command frame；新一轮独立复评仍 `G4: NO-GO`（4 Important、无 Critical/Minor）：冒号切句丢归属、provider 撤销/veto 未独立、AI/模型禁用被当内容约束、事实尾部黑名单误伤 prompt 内容且全局 question 短路吞新命令。
- 再次回上游修复:冒号保留引用归属；provider consent 独立于创作动作并保持 veto 到后续明确 provider 确认；补充“发给/先别发/先等等”等撤销；内容约束拒绝 AI/provider/model；创作动作只校验最终输出目标后的命令式尾部，不扫描 prompt 主题词；prompt 内嵌动作不再成为控制动作；question 按各动作 frame 自裁量并扩展“再/而是”切换。144 个聚焦对抗用例、路由广集 921 passed，用药与发布闸 126 passed，Ruff 及结构闸 PASS；等待独立复评。
- 后续独立复评仍 `G4: NO-GO`（4 Important、2 类 Minor，无 Critical）：通用说话人/示例标签仍能跨标点丢归属，provider veto 不 sticky，确认后的事实/延期分句被丢弃，动作名词/事实谓词仍能借后续媒体名词授权；同时发现当前用户确认、归属后重新声明及 prompt 内容同义表达误拒绝。
- 本轮回上游修复把 reviewer 的 24 个安全反例和 11 个正向反例完整落测，并新增 16 个同构变体：开放类说话人改按报告动词识别；归属上下文只由明确当前用户转折重领；provider 确认后的任何非明确新媒体命令都会令授权失效，上传/分享/外部服务 veto 只有后续明确 provider 确认可解除；动作名词与未引用的嵌套动作不能形成命令；prompt 内容 marker 与控制段隔离。最新证据为 220 个聚焦对抗、997 项路由广集及 126 项用药/发布闸全部 PASS，基础 release-pack、Ruff、secret、101 dossiers、doc drift 与 `git diff --check` PASS；等待同一 reviewer 再复评。
- 同一 reviewer 再复评仍 `G4: NO-GO`（4 Important、3 类 Minor，无 Critical）：reporting 同义词与引号作用域、确认后被 attribution 提前跳过的元描述、出站限制同义词及动作名词同义词仍可绕过；provider 重确认、当前用户 reclaim、purpose clause 与 prompt 内容又有误拒绝。reviewer 的新矩阵为 27 个安全反例和 25 个正向反例。
- 本轮不再以同义词扩表作为安全边界：先移除全部引号内容的控制权限；任意未知前导默认进入 attribution，只有受控目的/问题上下文或明确转折重领可恢复；无前缀裸动作仅接受直接输出对象语法；明确 create action 到最终输出对象之间整体视为 payload，只有动作前与最终输出后的控制文本能设 veto；provider confirm 的非命令后继在 attribution 处理前即令授权失效。完整 reviewer 矩阵再加 8 个开放词汇变体现为 280 focused、1057 route-wide、126 medication/release 全绿，Ruff 与 diff-check PASS；等待独立复评。
- 最新评审为 `CONDITIONAL GO`，新增阻断条件集中在真实外发确认链：闭合 provider 语法与 deny-first、owner-scoped 完整 prompt GET、短时绑定 review token、POST provider 前 fail-closed、Mobile/Web 初始禁用与完整纯文本展示、通用 action 防绕过、复杂源图片保持 general toolset 且 gateway provider-veto。现已用共用闭合语法、HMAC 绑定 token、no-store 投影、客户端 runtime-only token 和能力网关逐条整改，等待同一 reviewer 给出最终 G4 GO/NO-GO。
- 下一轮复评返回 `G4: NO-GO`（Critical 0 / Important 2 / Minor 2）：分行 provider 确认仍可被闭合 matcher 吞空白后 force，且 gateway 漏掉断网/手机上/服务商/云上四类 local-only 变体；另有 token 整秒边界和生成类型复核项。修复现拒绝闭合语法中的任意空白、扩展 local-only 传输边界、使用严格 token 过期比较，并证明固定 OpenAPI 生成器输出与两端当前类型逐字节一致；聚焦 9/9、相关 616/616、分类器 576/576、Ruff/diff-check PASS，等待再次独立复评。
- 最终回上游修复关闭 classifier 旧开放 fallback，令 classifier/force 共用闭合 provider grammar；内部空格、Tab、换行全部 fail closed，同时保留“确认发送来源图片后生成 5 秒短视频”的合法复杂正例。capability choke point 将本地执行、数据驻留、禁止外发/上云和固定英文 privacy frame 建模为确定性 veto。独立 reviewer 重放 660 项相关后端、579 项完整分类器、115 项 Mobile、40 项 Web、良性内容矩阵及 OpenAPI 逐字节复核，Critical / Important / Minor 均为 0。
- **裁决**:`G4: GO`（仅授权提交、推送和进入部署 Gate；主干 CI、G5/G6 未通过前不得上线）。

## S6 · 部署

- 路由:backend-deploy + Web deploy + conditional Mobile OTA/1.3.3 candidate。
- 已部署 SHA:`f6e353c88b539c93c5ee81d76a52f699a7decbf5`；当前路由修复尚未部署，回滚点为该 SHA 的前序生产版本。

## G5 · 部署健康闸

- 健康分:已部署 `f6e353c88` 后端/前端健康分 60/60，服务、PostgreSQL、Redis、Celery 与外部 `/api/v1/health` 正常。
- prod smoke:用药原句得到且仅得到一个可确认批次，确认前用药事实哈希不变并完成清理；早餐图片原句未产生 diet card，反而创建 AIGC 草稿，已清理并回退 S5。
- **裁决**:pending（上一轮生产烟测已证明已部署版本仍存在餐食图片误路由；当前已回到 S5，修复部署并重验前不得进入 EAS 候选构建）。

## S7 · 上线验证

- 真实路径验证:合成 QA 账号运行两条生产用例；真机核对卡片语义。
- 结果:用药路径 PASS；早餐图片路径 FAIL，误建测试 AIGC 草稿已删除，无已知残留。

## G6 · 验证闸

- 需求在 prod 对 anchor 用户真成立?:否，早餐图片主路径仍被确定性路由阻断。
- 真机/发布用户确认:pending。
- **裁决**:pending。

## S8 · 沉淀

- 新坑沉淀:pending。
- 文档同步:本 spec/plan/dossier；必要时更新 release dossier。
- 状态:building。
