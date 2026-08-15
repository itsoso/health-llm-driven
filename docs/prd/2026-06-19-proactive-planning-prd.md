# PRD:主动式全天规划与自治行动(Proactive Planning OS)

> Status: active product direction · v2 已确认(2026-08-15) · Owner: 产品方向 · 关联:`docs/specs/reva-product-governance-spec.md`(一等对象准入 + 自治分级)、`docs/specs/active/2026-08-15-quiet-proactive-health-day.md`(v2 唯一详细合同)、`docs/specs/active/2026-06-22-time-driven-health-management.md`(领域时点/安全 baseline)、`docs/specs/active/2026-07-17-xiaoba-agent-kernel.md`(查询与修改执行边界)。
> 流程:本 PRD 裁决产品方向;实现按 §6 分期,逐期出 feature spec + safety review 再落地。若与 2026-06-19 的模块化 roadmap 冲突,以 §0.1/§6 的 v2 收敛裁决为准。

## 0. 一句话
把饮食、睡眠、用药/补剂、复查、日历和锻炼收敛成一个安静主动、可查询、可调整、可验证的每日健康操作系统;Mobile 小巴主壳主动显示“现在做什么”,Today/Agenda 展开完整日程,Watch 低摩擦执行,Mac 承担复杂规划与复盘。

## 0.1 v2 产品收敛裁决(2026-08-15)

当前主要问题不再是缺少饮食、睡眠、补剂、日程或锻炼能力,而是这些能力分散在 Daily Artifact、Agenda、Timeline、Day Schedule 和各领域页面里。v2 不再继续堆同级入口,而是把既有能力编排成一个统一的 **Health Day** 产品体验。

Health Day 由三类内容组成:

- **固定承诺**:处方用药、已启用补剂协议、医嘱复查和用户确认过的日历事项。编排器不得静默增删或改变剂量/医嘱;允许在安全约束内解析展示时点。
- **自适应行动**:营养重点、训练强度、恢复、睡前准备等。系统可随睡眠、readiness、日历和执行反馈重排尚未执行的未来项。
- **机会行动**:只有在合适空窗和足够置信度下才出现的低压力建议;不抢占固定承诺,也不靠推送制造负担。

交互原则:

- 系统可自动观察、分析、排序和提醒,但新增、删除或实质调整日程必须生成含 before/after 的 `WriteIntent`,用户一键确认后才执行。
- 处方药、剂量、疗程、补剂购买和任何付费/外部动作始终逐项强确认;LLM 不得替代 SafetyGuardian 或确定性写权限。
- 查询和修改复用 XiaoBa Agent Kernel 的 `IntentFrame -> CapabilityPolicy -> ToolGateway -> receipt` 链路,不得另建 Health Day 专用自然语言执行器。
- Mobile 保持现有 Chat-first 小巴单入口:主壳承载 Health Day 摘要、查询和调整;Today/Agenda 是完整日程详情;Watch 是到点执行面;Mac 是复杂计划与复盘工作台。领域页保留为深钻页面,不再彼此争夺首页主线。
- 主动性默认为“安静主动”:重要变化才重排,低置信观察只进入 Today,不直接打扰用户。

## 1. 自治阶梯(组织框架,贯穿全 PRD)
| 档 | 含义 | 例子 | 确认 |
|---|---|---|---|
| T0 展示 | 只渲染 | 全天时间线 | 无 |
| T1 提醒 | 主动通知 | 会议前 10min、服药前 15min | 无(守 R15 通知预算) |
| T2 准备 | 系统起草,你确认 | 复购单、周健身计划 | 一键确认 |
| T3 执行 | 替你做外部动作 | 调快手电商 skill 下单、写回日历 | **逐笔强确认(财务硬门)** |

**不可退让**:T3 购买永远 human-in-the-loop;系统/助手**不自动扣款、不代输支付凭据**;执行由用户已授权的快手电商 skill 用其自有账号完成。

> 映射说明:T0-T3 是产品交互复杂度阶梯,不是 governance 的自治授权枚举。实际权限仍由
> `read/suggest/manual_confirm/shadow/auto` 与 CapabilityPolicy 决定;T2/T3 不自动获得写权限,
> 其中购买、预约、处方/剂量和其他外部高风险动作保持 `manual_confirm` 或更严。

## 2. 2026-06-19 历史基线(不可作为当前缺口清单)

本节只保留初版 PRD 的立项快照。2026-06-22 之后多个模块已经落地;当前能力与上线状态以
`docs/specs/active/2026-06-22-time-driven-health-management.md` §1.5 和 `docs/system-map/product-map.md` 为准。
- 五域智能调度(药/补剂/餐+营养/睡眠/运动),避开日历忙闲 + 上下班;全天时间线(mobile)。
- calendar v2 多源详细拉 + 30min 自动同步 + LLM 脱敏 seam。
- 服药提醒扫描(`scan_medication_reminders`);Watch standalone;Rokid 俯卧撑姿态/计数 app(团队/Codex)。
- Mac:有 `AgendaClient` 数据访问,**无时间线视图**。
- **无**:事件前提前量提醒、健身计划编排、动作图文指导、任何购物/复购。

## 3. 能力模块

以下模块是 Health Day 的能力来源和深钻页面,不是并列的首页导航或各自独立的规划真源。

### A. 全天时间线规划(Mobile ✅ → Mac 补)— T0
Mac App 加时间线视图(SwiftUI 24h 网格,复用 `/schedule/today` + `/calendar/events`,与 mobile 同契约)。Mac 轻量对等:看 + 确认为主。

### B. 事件前提醒(会议 -10min / 服药前)— T1
Celery 扫描"未来 N 分钟将开始的项"→ 推送。每类可配提前量(默认:会议 10、服药 15、锻炼 20、餐 0 分钟)。会议来自 CalendarEvent;**进 LLM 必脱敏**,推给本人的通知可带标题。统一过 `proactive_coordinator` 稀缺门防刷屏。

### C. 健身编排 + 动作指导
- C1 周健身计划(T2):按目标 + 训练负荷(ACWR)生成难/易/休,落时间线,你确认排期。
- C2 动作图文指导(T0/T1):点锻炼项 →「俯卧撑怎么做」分解步骤 + 常见错误,hedged 教练内容;伤病红线降级就医。
- C3 Rokid 实时姿态(复用团队 rokid-pushup):戴眼镜做俯卧撑 → 实时纠正 + 计数。

### D. 定期复购 / 自动买补剂(走一方服务端 Agent)
- D1 复购检测 + 提醒(T2):按补剂依从消耗 + 包装量估"快用完"→「X 还剩 ~5 天,补货?」+ 备好品牌/规格。不下单。
- D2 一键下单(T3):你确认 → **调快手电商服务端 Agent**(团队开发)用你的快手账号下单。新增一等对象 `ReorderIntent`(走 Write 层 manual_confirm + 审计)。**默认逐笔确认**;可选「常驻自动复购」= 显式开 + 单品 + 月额上限 + 每单通知(不静默)。系统不代输支付凭据。
- 准入:过 governance 一等对象 Gate + safety/privacy review(财务面)。

### E. 统一 Health Day 编排与控制面(v2 主线)

- 目标态由后端复用 `DailyOperatingPlan`、`HealthAgendaItem` 和滚动 7 天 runtime projection 形成同一份带版本的每日投影;`DailyArtifact` 只从中选择一个今日重点,不另算计划。授权版本/客户端接入须先通过 G2;V2-A1 只有内部无副作用 shadow。
- 小巴主壳只突出现在/下一项和一个今日重点;Today 详情固定为四个语义槽:现在、今日重点、今日日程、快速记录。完成、延后、跳过和调整都从具体 item 发起。
- 有意义的新数据、日历变化或执行反馈只重排未来自适应项;固定承诺和已执行事实保持稳定。
- 晚间用不到一分钟完成复盘;周复盘把执行/跳过原因和指标变化回流到 `InterventionCycle` / protocol 调整建议。

## 4. 表面契约
| 端 | 角色 |
|---|---|
| Mobile | Chat-first 小巴主壳(Health Day 摘要/查询/调整)+ Today/Agenda 详情 + material change 确认 + 动作指导 |
| Mac | 复杂计划、冲突处理、数据审查和复盘工作台 |
| Watch | 下一项 + 到点完成/稍后/跳过回执(standalone) |
| Rokid 眼镜 | 俯卧撑实时姿态指导 |
| 后端 | 唯一 composition/safety/write authority + 调度 + 提醒决策 + 外部 intent + 脱敏门 + 审计 |

## 5. 安全 / 隐私 / 自治硬边界
- 财务:逐笔确认;不自动扣款;不代输支付凭据;快手 skill 用用户自有账号执行。
- 医疗:提醒/计划/指导全 hedged,不开方/不调剂量/不出因果裁决;红线降级就医。
- 隐私:会议标题/参会人进 LLM 必脱敏(沿用 `calendar_event_for_llm`)。
- 通知预算:T1 过稀缺门防刷屏。
- 自治审计:T2/T3 全落 write_intent 审计,可追溯可撤销。

## 6. 分期 Roadmap(v2 rebase)

2026-06-19 roadmap 的主要软件能力已在后续切片中落地;硬件 adapter 和真实外部 provider 仍是外部边界。v2 按“先统一读,再统一写,最后放开安静主动”推进:

1. **V2-A1 · 内部只读影子**:在不改变 API/客户端、不写 DB、不物化计划、不 mutation、不推送的前提下,用单一 pure composer 生成 canonical manifest/artifact,在 backend/service fixture 层与 `DailyOperatingPlan`、Agenda、Schedule、Daily Artifact/DynamicView、Calendar 和当前 `/timeline/today` compatibility projection 的 assembled 旧输出做确定性 diff。该阶段只有非授权 keyed digest,不产生客户端 `plan_version`,也不 mount 带本地提醒副作用的 Today。
2. **V2-A2/B · 授权快照 + Mobile 收敛**:G2 通过后,由服务端唯一 snapshot owner 生成 monotonic generation/opaque `plan_version`;在 Chat-first 小巴主壳展示 now/next + one top action,Today 详情只保留“现在 / 今日重点 / 今日日程 / 快速记录”四个语义槽。`/timeline/today` 先保留为 compatibility projection;Day Schedule 的工作时间/依从写入迁到 typed commands 后,再按动态点击审计收敛真正重复的 UI。历史事件 Timeline 不在此范围。
3. **V2-C · 查询与修改**:把查询、完成、跳过、延后、调整统一接入 Agent Kernel;修改展示 before/after,确认后幂等执行并返回可验证 receipt;版本冲突必须重新预览确认。
4. **V2-D · 安静主动重排**:先 shadow,再逐步启用早晨、新鲜健康信号、重要日历变化、执行反馈和用户明确调整五类触发;只改未来自适应项。
5. **V2-E · 复盘与退役**:接通晚间/周复盘与 `InterventionCycle` 反馈,验证完成率、跳过原因、通知关闭率和调整成功率;依赖清零后归档重复 planner/surface。

真外卖/挂号 provider、支付和 P3 硬件 adapter 不阻塞 v2 主线;它们继续按各自安全评审和真机/账号条件独立推进。

## 7. Open(不阻塞 V2-A1)

- 真实外卖/挂号/购物 provider 的调用契约与账号授权方式;支付永远由用户自己完成。
- 硬件 posture/screen-focus adapter 的首个真机与数据最小化实现。
- 真正重复 UI 的具体收敛顺序;`/timeline/today` 当前是 Chat/Today compatibility read seam,Day Schedule 仍拥有工作时间/服药依从写入,历史事件 Timeline 不在本 feature 退役范围。必须先迁 ownership,再做动态点击/依赖审计,不得先删后补。

## 8. Changelog
| 日期 | 变更 |
|---|---|
| 2026-06-19 | 初稿;D2 下单定为快手电商 skill;提前量默认 + 分期 + Mac 轻量对等 定稿 |
| 2026-08-15 | v2 产品收敛确认:从功能模块扩张转向统一 Health Day;确定安静主动、可查询可修改、Chat-first 小巴单入口 + Today/Agenda 详情、统一 Agent Kernel 写边界和五阶段收敛 roadmap。 |
