# Reva Personal Health OS PRD

> 状态：v2 可执行基线，2026-06-15
> 目标：把 Reva 从“健康数据和 AI 功能集合”收敛成一个能每天推动中年人变健康的 Personal Health OS。
> 本文替代上一版合并蓝图。上一版中的个人健康细节、泛化口号、外部文档依赖和未验证临床默认值不再作为需求依据。

## 0. 读者和使用方式

本文服务三类人：

- 产品设计：基于本文重新做 IA、三端页面和关键工作流。
- 工程实现：基于本文拆后端、mobile、Mac app、Web 的迭代任务。
- Review/验收：基于本文判断 Claude Code 或其他 agent 的实现是否真的落到了产品目标。

本文的规则：

- 只写会影响行为、数据、提醒、复盘或安全边界的需求。
- 临床建议必须有证据来源、适用范围、风险边界和人工确认路径；没有这些，不进入默认产品逻辑。
- LLM 只做解释、摘要、结构化输入和候选计划生成，不做最终医疗安全裁决。
- 不在公开仓库写入可识别的个人病史、化验值、用药细节或设备组合指纹。

## 1. 产品一句话

Reva 是面向 35-60 岁中年人的个人健康操作系统。它把可穿戴设备、体检、日程、饮食、运动、用药补剂和主观状态组织成一张“今天该做什么、为什么做、做完如何验证”的 Health Agenda，并用三端协同降低执行摩擦。

它不是：

- 不是健康问答机器人。
- 不是 Apple Health、Garmin Connect、RingConn 的替代看板。
- 不是医疗诊断、开方或调药系统。
- 不是为了连续打卡、徽章、积分而设计的习惯 app。

它要解决的问题：

1. 中年人知道要健康，但每天不知道“今天最该做哪三件事”。
2. 有很多设备和数据，但数据没有变成行动。
3. 有行动，但没有复盘机制证明是否真的改善了精力、代谢、恢复和风险。
4. 有慢病、体检异常或长期用药时，提醒和计划缺少医学边界。
5. 想长期坚持，但输入太麻烦，提醒太吵，反馈太空。

## 2. 目标用户

### 2.1 第一目标用户

35-60 岁，工作负荷高，有明确健康改善意愿，通常具备以下一个或多个特征：

- 有代谢风险：体重、腰围、血脂、血糖、脂肪肝、血压或尿酸等指标需要长期管理。
- 恢复变差：睡眠质量、HRV、静息心率、晨起状态、午后困倦或运动恢复明显波动。
- 已经使用设备：Apple Watch、Garmin、RingConn、智能秤、血压计、CGM、体检报告等。
- 有长期事项：用药、补剂、专项复查、年度体检、运动训练、饮食控制。
- 愿意每周投入 15 分钟复盘，但不愿每天花很多时间录入。

### 2.2 不优先服务的人群

- 急性病处理、急救场景和重症监护场景。
- 需要医生直接远程诊疗的人群。
- 儿童、孕产妇、专业运动员等需要特殊医学或训练框架的人群。
- 只想看漂亮数据图、不希望改变行为的人群。

## 3. 北极星指标

### 3.1 结果北极星

产品最终只看两类结果：

- 精力和恢复：主观精力 0-10、睡眠恢复、晨起状态、午后困倦、深度工作时长。
- 长期风险代理指标：体重、腰围、血压、血糖、血脂、肝肾相关指标、炎症指标、运动能力和复查结果。

产品必须承认：多数行为和指标改善只能证明时间相关，不直接证明因果。复盘文案必须区分“观察到相关”和“已证明有效”。

### 3.2 行为北极星

每周完成的“可验证健康行动闭环”数量。

一个闭环必须同时满足：

- 被安排：出现在 Health Agenda。
- 被执行：有完成、跳过、自动观测或调整事件。
- 可解释：知道为什么做，以及没做的原因。
- 可验证：绑定至少一个后续指标或复查结果。
- 可追溯：能追到来源对象、证据等级和变更历史。

### 3.3 反指标

以下指标上升不是好事：

- 无效提醒数。
- 用户手动录入次数。
- 没有改变计划的数据项数量。
- 未确认就进入计划的临床建议数量。
- 设备冲突但被系统静默平均的次数。
- 计划过载导致的跳过率。

## 4. 产品原则

1. 行动优先：数据只有能改变行动、解释失败或验证结果时才进入核心流。
2. 被动优先：设备可自动采集的，不要求用户手填。
3. 低摩擦输入：默认支持语音、照片、一键完成和自动观测；逐量手填作为兜底。
4. 失败可用：跳过不是坏数据，跳过原因是系统改计划的关键输入。
5. 医学边界前置：慢病、异常指标、用药和专项复查优先于补剂、外观和泛抗衰。
6. 三端分工：mobile 负责日常执行，Mac app 负责桌面工作流，Web 负责报告、后台和长周期管理。
7. 设备不做唯一真相：Apple Watch、Garmin、RingConn 等只是采集源；个人健康数据主权在自有 Health Vault。
8. LLM 不兜底安全：安全判断由规则、证据、阈值和人工确认兜底，LLM 只生成候选和解释。

## 5. MVP 范围

下一阶段 MVP 只做一件事：Health Agenda。

Health Agenda 是用户今天、这周、这个季度该做的健康行动列表。它从已有数据和计划投影而来，所有端看到同一组 item，所有执行事件回写同一条事件流。

### 5.1 MVP 必须包含

- 后端：Agenda projection API、Agenda event log、状态排序、失败原因枚举、基础审计。
- Mobile：Today、Agenda、Capture、Review 的最小闭环。
- Mac app：桌面快速记录、今日计划、导入和复盘入口。
- Web：长期计划、体检/复查、设备数据质量和隐私/审计入口。
- 可穿戴：本阶段不强制做独立 Watch app，但必须为 Apple Watch 通知、快捷操作和后续 watchOS companion 留出事件模型。

### 5.2 MVP 不包含

- 不做完整临床知识库。
- 不做从零训练模型。
- 不做腕上长对话。
- 不做全自动诊断、开方、调药。
- 不做所有设备的深度原生集成。
- 不做复杂游戏化。

## 6. 核心对象

### 6.1 HealthAgendaItem

统一执行层对象。所有今天该做的事情都投影为 HealthAgendaItem。

必填字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | Agenda item ID，稳定可审计 |
| user_id | string | 当前用户，所有查询强制过滤 |
| title | string | 用户可读标题，例如“晨起血压测量” |
| domain | enum | hydration、diet、sleep、training、medication、supplement、measurement、checkup、review、data_quality、safety |
| priority | enum | P0、P1、P2、P3 |
| status | enum | pending、completed、skipped、snoozed、adjusted、auto_observed、expired |
| scheduled_for | datetime | 推荐执行时间 |
| time_window_start | datetime | 可执行时间窗开始 |
| time_window_end | datetime | 可执行时间窗结束 |
| source_type | string | 来源类型，例如 DailyPlan、MedicationSchedule、HealthProblem、HealthProtocol |
| source_id | string | 来源对象 ID |
| reason | string | 为什么今天要做 |
| evidence_level | enum | A、B、C、D、personal |
| safety_level | enum | normal、needs_confirmation、medical_review、urgent |
| automation_path | enum | healthkit、garmin、ringconn、manual、voice、photo、external_device、lab_upload、calendar |
| expected_signal | json | 完成需要的信号，例如一次血压记录、一次 workout、一次用药确认 |
| outcome_links | json | 绑定的指标、Program 或 Problem |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

排序规则：

1. safety_level 为 urgent 或 medical_review 的排最前。
2. priority P0 > P1 > P2 > P3。
3. 时间窗即将关闭的排前。
4. 有明确医生要求、复查到期或用药安排的排前。
5. 低证据补剂、体验型实验和外观目标不能压过医学问题、睡眠恢复和训练安全。

### 6.2 AgendaEvent

所有端对 item 的操作都写 AgendaEvent，不直接改业务事实。

必填字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | event ID |
| user_id | string | 当前用户 |
| agenda_item_id | string | 对应 item |
| event_type | enum | completed、skipped、snoozed、adjusted、auto_observed、confirmed、rejected |
| occurred_at | datetime | 发生时间 |
| source_surface | enum | mobile、mac、web、watch、system、external_agent |
| input_mode | enum | tap、voice、photo、manual_form、device_sync、import、automation |
| value | json | 数值、剂量、餐食、训练结果等 |
| skip_reason | enum | no_time、forgot、not_available、too_tired、wrong_place、too_hard、symptom、social_interruption、device_missing、other |
| confidence | number | 0-1 |
| raw_payload_ref | string | 原始输入引用，敏感内容按权限存储 |
| audit_ref | string | 审计引用 |

事件规则：

- completed 和 auto_observed 必须能追到明确输入或设备信号。
- medication、measurement、checkup 不能默认完成。
- skipped 必须尽量捕获 skip_reason；没有原因时可为 other，但周复盘要提示补充。
- 同一 item 多端重复完成必须幂等，不能造成重复用药、重复饮食或重复训练记录。

### 6.3 HealthProgram

8-12 周目标容器。Program 不直接提醒用户，Program 投影 Agenda item。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | program ID |
| user_id | string | 当前用户 |
| name | string | 例如“12 周代谢改善” |
| domain | enum | metabolic、recovery、training、sleep、medication_safety、checkup |
| status | enum | draft、active、paused、completed、archived |
| start_date | date | 开始日期 |
| end_date | date | 结束日期 |
| primary_metrics | json | 主要验证指标 |
| secondary_metrics | json | 次要指标 |
| protocol_ids | json | 绑定协议 |
| review_cadence | enum | weekly、biweekly、monthly |
| owner | enum | user、doctor、coach、system |

### 6.4 HealthProtocol

协议是“默认怎么做”的容器，解决重复决策和重复录入。

例子：

- 饮水：固定水杯协议。
- 饮食：标准餐模板协议。
- 睡眠：睡前流程协议。
- 训练：固定训练课表协议。
- 用药：药盒和时点协议。
- 测量：晨起体重、固定姿势血压协议。
- 复查：年度体检和专项复查协议。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | protocol ID |
| user_id | string | 当前用户 |
| domain | enum | 同 Agenda domain |
| name | string | 协议名称 |
| status | enum | active、paused、archived |
| mechanism | enum | fixed_container、pre_commit、passive_device、environment_default、manual_template |
| cadence | string | daily、weekly、quarterly、event_triggered 等 |
| default_time_window | json | 默认时间窗 |
| implied_quantity | json | 协议隐含数量，例如水量、餐食模板、训练时长 |
| completion_rule | json | 完成规则 |
| manual_override_allowed | boolean | 必须默认为 true |
| safety_policy | json | 禁止默认完成、需要确认、红线等 |
| evidence_level | enum | A、B、C、D、personal |
| linked_program_id | string | 可空 |

协议规则：

- 协议轨和手工轨写同一底层记录。
- 手工轨永远存在，协议轨只是低摩擦默认路径。
- 用药、血压、血糖、体检复查不能靠“默认完成”。
- 设备缺失时不假装完成，要生成 data_quality item 或降级为手动确认。

### 6.5 HealthProblem

医学问题登记。它不是诊断引擎，而是把已知问题、医生结论、复查节奏和红线阈值产品化。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | problem ID |
| user_id | string | 当前用户 |
| name | string | 例如血压管理、脂肪肝随访、结节复查、长期用药安全 |
| status | enum | active、monitoring、resolved、archived |
| risk_level | enum | P0、P1、P2、P3 |
| diagnosis_summary | text | 用户/医生录入摘要，非系统自动诊断 |
| evidence_refs | json | 医生报告、化验、影像或指南引用 |
| red_lines | json | 需要升级的阈值或症状 |
| follow_up_plan | json | 上次检查、下次检查、检查项目、负责科室 |
| linked_program_ids | json | 相关 Program |
| owner | enum | user、doctor、system |

规则：

- HealthProblem 可以生成 checkup、measurement、review、safety 类 Agenda item。
- 风险分层必须可追溯，不能由 LLM 单独生成。
- 到期复查、趋势恶化或红线命中必须升级为 P0/P1 item。
- 产品文案必须说“建议复查/咨询医生/关注趋势”，不能说“你被诊断为”。

### 6.6 SourceQuality

设备和数据源质量对象。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| metric | string | 指标，例如 sleep、hrv、steps、workout、bp、weight |
| winning_source | string | 当前采用来源 |
| candidate_sources | json | 候选来源 |
| freshness | enum | fresh、stale、missing |
| agreement | enum | high、medium、low、conflict |
| confidence | number | 0-1 |
| last_seen_at | datetime | 最近数据时间 |
| action_if_stale | string | 过期时生成的 item 或降级路径 |

规则：

- 冲突时不能简单平均。
- 安全相关指标宁可降置信，也不能静默用单源覆盖。
- 数据过期要影响 Agenda，而不是只在设置页显示。

## 7. API 需求

### 7.1 Agenda API

`GET /api/agenda/today`

返回今天的 item。

查询参数：

- `date`: 可选，默认为用户本地今天。
- `domains`: 可选，多选。
- `include_completed`: 默认 false。
- `surface`: mobile、mac、web、watch，用于裁剪展示字段，不改变排序事实。

验收：

- 50 个 item 内 p95 < 300ms。
- 返回结果必须只包含当前用户数据。
- 同一用户同一日期在三端排序一致。

`GET /api/agenda/range`

返回一段日期内 item，用于周视图、复查日历和 Web。

`POST /api/agenda/items/{item_id}/events`

写入执行事件。

验收：

- 支持幂等 key。
- 重复完成不重复写入底层事实。
- medication 和 supplement 必须带剂量或 schedule 引用。
- skipped 支持结构化 skip_reason。

`POST /api/agenda/rebuild`

重新投影 Agenda。仅系统、管理员或授权 agent 可调用。

验收：

- 不删除已有 event。
- projection 可重放。
- rebuild 结果可审计。

### 7.2 Capture API

`POST /api/capture/food/voice-drafts`

输入语音转写文本，输出待确认餐食草稿。

要求：

- 保存 raw_text 引用。
- 输出 meal_type、foods、estimated_quantity、confidence、needs_confirmation。
- 低置信度最多追问一个问题。
- 不追求克级精确，优先形成长期可比较记录。

`POST /api/capture/manual`

统一手工记录入口，支持饮水、饮食、症状、精力、测量、补剂、运动 RPE。

要求：

- 可绑定 agenda_item_id。
- 不绑定时也能创建事实记录，并在需要时反向满足 Agenda item。

### 7.3 Program 和 Protocol API

`GET /api/health-programs`

`POST /api/health-programs`

`GET /api/health-protocols`

`POST /api/health-protocols`

`PATCH /api/health-protocols/{id}`

要求：

- Protocol 修改要保留版本历史。
- Active protocol 改动后要触发 Agenda rebuild。
- 高风险协议需要 confirmation_state，不允许直接生效。

### 7.4 HealthProblem API

`GET /api/health-problems`

`POST /api/health-problems`

`PATCH /api/health-problems/{id}`

要求：

- 不允许 LLM 单独创建 active problem；LLM 只能创建 draft。
- active problem 必须有用户确认，医学高风险项需要医生/报告引用。
- follow_up_plan 到期自动生成 Agenda item。

### 7.5 Device Router API

`GET /api/device-router/status`

返回每个关键指标的数据源质量。

要求：

- 显示 Apple Watch、Garmin、RingConn、手工、外部设备、化验上传等来源状态。
- stale/missing/conflict 要能生成 data_quality Agenda item。

## 8. 三端产品需求

### 8.1 Mobile

Mobile 是日常主体验，必须优先做。

底部入口：

1. Today
2. Agenda
3. Capture
4. Programs
5. Review

#### Today

显示今天最重要的 3-5 件事。

必须有：

- 今日状态灯：Green、Yellow、Red、Gray。Gray 表示数据不足，不允许伪装成安全。
- Top Actions：按 Agenda 排序显示。
- 每个 action 支持完成、跳过、稍后、调整。
- 跳过时展示短原因选择，不超过 8 个。
- 有 P0/P1 安全项时置顶。

不能有：

- 大段 AI 解释。
- 复杂图表。
- 鼓励连续打卡的视觉压力。

#### Agenda

显示 today/week/month。

必须有：

- 按时间窗分组。
- 按 domain 筛选。
- 显示来源：来自 Program、Protocol、Problem、DeviceQuality 或系统复盘。
- 支持查看“为什么现在提醒我”。

#### Capture

统一输入入口。

必须有：

- 语音记食物。
- 拍照/文本记食物作为已有能力入口。
- 快速饮水、症状、精力、RPE、测量手填。
- 协议轨和手工轨切换。

语音记食物 v1：

- 用户说“午饭牛肉饭半份，加无糖咖啡”。
- App 生成待确认草稿。
- 用户一键确认或改 meal_type/份量。
- 成功后若存在相关 Agenda item，同步完成。

#### Programs

显示 8-12 周目标，不做复杂配置。

必须有：

- 当前 active program。
- 绑定指标。
- 本周行动完成率。
- 下次复盘时间。

#### Review

每周 15 分钟复盘。

必须回答三件事：

- 这周做了什么？
- 哪些指标变了？
- 下周计划怎么改？

### 8.2 Mac App

Mac app 是桌面工作台，不复制 mobile。

必须有：

- 今日 Agenda 侧栏或小窗。
- 快速记录：键盘输入、语音转文字、剪贴板体检/报告导入。
- 长对话：用户问“为什么今天训练降级”，展示可追溯解释。
- Trace：展示某个建议来自哪些数据、规则和计划。
- Review 工作台：适合周复盘和 90 天复盘。

Mac app 不做：

- 替代 mobile 的日常提醒。
- 复杂后台管理。
- 无审计的 agent 自动改计划。

### 8.3 Web

Web 是后台、报告和长周期管理，不做主日常体验。

必须有：

- Health Vault 数据源状态。
- HealthProblem 列表和复查日历。
- Program/Protocol 管理。
- 体检报告上传和结构化结果确认。
- 隐私、授权、导出、删除、审计日志。
- Apple Health XML fallback。

Web 不做：

- 作为主要打卡入口。
- 复杂实时提醒。

### 8.4 Apple Watch 方向

MVP 不强制独立 Watch app，但事件模型必须支持 Watch。

Apple Watch 适合做：

- 当前状态灯 complication。
- Smart Stack 今日最重要行动。
- 到点轻提醒。
- 完成、跳过、稍后、调整。
- 语音记食物。
- 症状/精力一键打标。
- 训练前 readiness gate。

Apple Watch 不适合做：

- 长表单。
- 长 AI 对话。
- 复杂营养编辑。
- 医疗解释和报告阅读。
- 常驻录音。

Watch v1 是否做独立 app 的决策标准：

- 如果 mobile 通知 + shortcut 已能完成 80% 腕上操作，先不做独立 app。
- 如果需要 complication、离线记录、训练前实时 gate 或语音入口，再做 watchOS companion。

## 9. 可穿戴和硬件策略

### 9.1 当前设备分工

Apple Watch：

- 最适合提醒、即时反馈、语音、状态灯、快捷操作、Apple Health 桥接。

Garmin：

- 最适合训练、跑步、负荷、恢复、运动记录和 endurance 指标。

RingConn：

- 最适合睡眠、夜间 HRV、恢复、皮温、低打扰长期佩戴。

系统要做的是 source arbitration，不是把三份数据都画出来。

### 9.2 可扩展硬件

按价值优先级：

1. 医用级上臂血压计：中年健康高价值，适合固定测量协议。
2. 智能体重秤或体脂秤：体重趋势、体脂、肌肉量作为代谢和训练反馈。
3. CGM 阶段性使用：2-4 周战役，用于饮食和睡眠行为反馈，不长期制造焦虑。
4. 室内 CO2、PM2.5、温湿度传感器：鼻炎、睡眠、精力相关。
5. 睡眠环境设备：遮光、温控、白噪声或空气净化，只有能影响行动才接入。
6. 药盒：用药确认和补剂分装协议。

不优先：

- 低可信“抗衰”硬件。
- 没有输出 API 或只能看厂商 app 的封闭设备。
- 不能改变计划的娱乐型健康硬件。

### 9.3 数据主权

要求：

- 原始或准原始数据进入自己的 Health Vault。
- 第三方平台只做采集源和显示终端。
- 可导出、可删除、可撤权。
- 敏感字段加密存储。
- 所有外部 agent 访问必须最小权限、审计和可撤销。

## 10. 通知策略

提醒是稀缺资源。

### 10.1 分级

P0：必须响应。

- 处方药关键时点。
- 医生要求复查当天。
- 明确危险阈值或危险症状。
- 训练安全红灯。

要求：

- 可用腕表强提醒和手机提醒。
- 每周 P0 不应超过 3 条，除非确有医疗原因。

P1：推荐执行。

- 训练开始。
- 睡前流程。
- 饮水明显不足。
- 测量到期。

要求：

- 轻提醒。
- 可忽略。
- 不连续轰炸。

P2：只记录不推送。

- 步数同步。
- 体重同步。
- 普通数据导入。
- 周报素材收集。

### 10.2 安静时间

- 睡前 90 分钟后只允许 P0。
- 工作深度专注时段只允许 P0 和用户指定 P1。
- 周主动提醒总量默认不超过 15 条。

## 11. 典型工作流

### 11.1 早晨 2 分钟

1. RingConn 同步睡眠和 HRV。
2. Garmin/Apple 数据进入 Router。
3. 系统生成今日状态灯。
4. Today 显示 3 件事：例如测量、训练建议、用药或睡前安排。
5. 用户只处理异常项。

验收：

- 数据缺失时显示 Gray 和 data_quality item。
- 训练建议能解释是由睡眠、HRV、主观疲劳还是症状影响。

### 11.2 训练前

1. 训练 item 到时间窗。
2. 系统读取恢复状态、近期训练负荷、症状和日程。
3. 输出 Green/Yellow/Red。
4. Watch 或 mobile 给出执行、降级或休息建议。
5. 训练后 Garmin workout 自动满足 item，用户补 RPE/疼痛。

验收：

- 急性症状或危险信号优先于 Garmin readiness。
- Red 不能被文案包装成“挑战一下”。

### 11.3 语音记食物

1. 用户在 mobile 或 Watch 说一句自然语言。
2. 系统转成餐食草稿。
3. 置信度高则一键确认，低则追问一个问题。
4. 记录写入 DietRecord，并关联 Agenda event。
5. 周复盘只看模式和趋势，不追求单餐精确。

验收：

- 原始语音转写可追溯。
- 模型低置信不得静默写入确定事实。

### 11.4 复查到期

1. HealthProblem 中某项 follow_up_plan 到期。
2. 系统生成 checkup Agenda item。
3. Web 显示复查日历，mobile Today 在临近时提醒。
4. 用户上传报告。
5. 系统结构化提取，用户确认后进入趋势。
6. 如红线命中，生成 medical_review 或 urgent item。

验收：

- 没有医生/报告证据时，系统不能自动改变诊断摘要。
- 红线必须可追溯到用户确认的 Problem 配置或证据库。

### 11.5 周复盘

1. 系统聚合执行率、skip_reason、设备质量、指标变化。
2. 生成三段：本周做了什么、指标有什么变化、下周怎么改。
3. 用户确认计划调整。
4. 调整 Program/Protocol，触发 Agenda rebuild。

验收：

- 至少展示一个“系统计划哪里设计得不好”的结论，而不是指责用户。
- 下周计划减少或调整无效提醒。

## 12. 安全和隐私要求

### 12.1 用户隔离

- 所有查询必须从 current_user 派生 user_id。
- 不允许前端传 user_id 决定数据归属。
- legacy `/user/{user_id}` 风格接口必须迁移或加所有权检查。

### 12.2 敏感信息

- 健康数据、用药、基因、报告、token、设备凭据按敏感等级处理。
- 日志必须脱敏。
- 审计日志记录数据导出、授权、删除、外部 agent 调用、计划自动变更。

### 12.3 医疗边界

- 不诊断。
- 不开方。
- 不自行调药。
- 不把补剂或低证据实验包装成医疗建议。
- 红线触发时给出就医/咨询医生路径。

### 12.4 LLM 边界

LLM 可以：

- 结构化语音和文本输入。
- 总结复盘。
- 解释已有规则为什么触发。
- 生成候选计划草稿。

LLM 不可以：

- 单独创建 active HealthProblem。
- 单独改变处方、剂量或复查结论。
- 覆盖确定性安全规则。
- 在缺数据时编造状态。

### 12.5 Web 安全

- 不使用不受控的 `dangerouslySetInnerHTML` 或裸 HTML 渲染健康建议。
- token 不应长期放 localStorage。
- 远程管理和外部 agent 接入需要 host key、最小权限和审计。

## 13. 验收标准

### 13.1 后端

- `GET /api/agenda/today` 能从至少三类来源投影 item：用药/补剂、训练/恢复、测量/复查。
- `POST /api/agenda/items/{id}/events` 支持 completed、skipped、snoozed、adjusted、auto_observed。
- 事件写入幂等。
- 所有 Agenda 查询强制用户隔离。
- 数据源 stale/missing/conflict 能生成 data_quality item。
- Agenda rebuild 可重放，不删除历史 event。

### 13.2 Mobile

- Today 能展示状态灯和 Top Actions。
- Agenda 能按时间窗显示今天和本周。
- Capture 能完成语音食物草稿和至少 3 个手工快速记录。
- Review 能生成周复盘草稿。
- 完成/跳过任一 item 后，刷新 Today 和 Agenda 状态一致。

### 13.3 Mac App

- 能显示今日 Agenda。
- 能通过桌面输入快速创建或满足一条记录。
- 能查看某条建议的 trace。
- 能进入周复盘。

### 13.4 Web

- 能管理 HealthProblem、Program、Protocol。
- 能显示复查日历。
- 能上传体检报告并进入确认流程。
- 能查看设备数据源状态。
- 能导出和删除用户健康数据。

### 13.5 Watch/可穿戴准备

- Agenda event 模型支持 source_surface=watch。
- item 字段能裁剪成 Watch 可展示内容。
- 通知分级支持 P0/P1/P2。
- 语音食物和一键完成不依赖 Web。

## 14. 迭代路线图

### R0：PRD 和设计基线

产物：

- 本 PRD。
- 三端 IA 草图。
- AgendaItem/Event/Protocol/Problem 数据契约。
- 安全 review checklist。

完成标准：

- 设计、后端、mobile、Mac、Web 都能从本文拆任务。
- 没有个人敏感病史写入公开文档。

### R1：Agenda 后端骨架

产物：

- Agenda projection service。
- Agenda event table。
- today/range/events API。
- 基础排序和状态机。
- user_id 隔离和审计。

完成标准：

- 从现有 Daily Plan、用药/补剂、训练/恢复、测量/复查至少三类来源生成 item。
- API 有单元测试和权限测试。

### R2：Mobile 日常闭环

产物：

- Today。
- Agenda。
- Capture 快速记录。
- 语音食物草稿。
- 周 Review 草稿。

完成标准：

- 用户能从 mobile 完成一天的核心健康行动，不需要 Web。

### R3：Mac App 工作台

产物：

- 今日 Agenda 小窗。
- 快速记录。
- Trace。
- 周复盘工作台。

完成标准：

- 用户在桌面工作时能记录、理解和复盘，不打断主流程。

### R4：Web 后台和报告

产物：

- HealthProblem 管理。
- Program/Protocol 管理。
- 复查日历。
- 设备数据质量。
- 报告上传确认。
- 隐私和审计。

完成标准：

- 长周期健康管理和数据治理不依赖 mobile 小屏。

### R5：Apple Watch companion 决策

先用 mobile 通知和 shortcut 验证。

如果满足以下任一条件，再做独立 watchOS app：

- complication 对执行率明显有提升。
- 训练前 gate 需要腕上即时反馈。
- 语音记食物在 Watch 上使用频率高。
- 离线记录是刚需。

### R6：Outcome Proof

产物：

- 7/30/90 天复盘。
- Program 指标趋势。
- 个人响应强弱。
- 计划调整记录。
- n=1 实验的 washout 和置信度。

完成标准：

- 用户能回答“过去 90 天哪些行为可能让哪些指标变好，哪些没有用”。

## 15. 实现顺序

建议按以下顺序执行：

1. 清理文档和安全边界：删除敏感个人细节，补齐 PRD 自包含契约。
2. 后端先做 AgendaItem 和 AgendaEvent，不先做复杂 UI。
3. 把现有计划、用药/补剂、训练恢复、测量复查投影进 Agenda。
4. Mobile 做 Today 和 Agenda，确保能完成和跳过。
5. Capture 接入语音食物和快速手填。
6. Mac app 做今日小窗、快速记录和 Trace。
7. Web 做 HealthProblem、Program、Protocol 和复查日历。
8. 做 Router 数据质量和通知分级。
9. 再决定是否做独立 Watch app。
10. 最后做 Outcome Proof 和 n=1 严谨化。

不建议先做：

- 大而全的健康知识库。
- 完整 watchOS app。
- 复杂 Agent 自动规划。
- 新模型训练。
- 花哨 dashboard。

## 16. Review 清单

评审实现时逐条问：

- 这项功能是否生成、完成或改变了 Agenda item？
- 是否同时支持低摩擦路径和手工兜底？
- 是否能解释为什么提醒用户？
- 用户跳过后，系统是否学到了原因？
- 数据缺失时是否诚实显示，而不是伪装正常？
- 医疗风险是否由规则和证据处理，而不是 LLM 自行判断？
- 三端是否看到同一事实，而不是各做一套状态？
- 是否有 user_id 隔离、审计、脱敏和撤权路径？
- 是否能在 7/30/90 天复盘中证明价值？

## 17. 关键开放问题

1. 现有后端哪些对象最适合作为 Agenda projection source，需要代码 review 后确定。
2. Mobile、Mac、Web 的现有导航和状态管理是否能承载统一 Agenda store。
3. 语音食物先走系统语音转写还是已有输入法/第三方转写。
4. Apple Watch 先做通知/shortcut 还是直接 watchOS companion。
5. HealthProblem 的证据库和红线阈值由谁维护，如何版本化。
6. 外部 agent 调用 Agenda rebuild 和计划调整时的授权边界。

## 18. Definition of Done

一个版本只有同时满足以下条件才算完成：

- 用户每天能在 mobile 看到今天最重要的健康行动。
- 用户能用一键、语音、设备同步或手填完成行动。
- Mac app 能支持桌面快速记录和解释。
- Web 能管理长期计划、复查和数据权限。
- 所有端共享同一 Agenda event 事实。
- 安全、隐私、医疗边界有测试或人工 review 证据。
- 周复盘能基于真实执行事件提出下周调整。
