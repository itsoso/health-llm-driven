# Dossier: 小巴健康参谋型对话界面

| 字段 | 值 |
|---|---|
| slug | `xiaoba-health-advisor-chat-ui` |
| 创建日期 | 2026-07-13 |
| 当前阶段 | S7 上线验证 |
| 状态 | validating |
| 负责 | Codex |
| 反馈环 | Mobile 本地测试 -> iOS Simulator 视觉验收 -> production OTA |

## S0 · 用户需求

> 再认真做一次分析，给出更加靠谱的UI设计方案。语音输入框就保持微信当前的模仿的样式，先不改动这一块。其他部分参考业界最佳实践，以及当前APP的调性，给出你最好的设计方案出来，要有原型图出来给我看。
>
> 确认

- 谁用 / 解决什么 / 现在怎么绕过：高频使用小巴查询、记录和执行健康行动的 Mobile 用户。当前要在重复状态、长白色气泡、常驻分享动作和多卡竞争中寻找主结论与下一步。
- 锚点用户相关性：目标用户需要低打扰地理解一条结论、执行一个行动，并在需要时查看依据，不应承担调试面板式的信息负担。

## S1 · Discovery

- 已有可复用：`ChatHeader`、`ChatBubble`、`ThinkingStepsPanel`、`ChatTodayFocusCard`、`CardShell`、Reva UI registry、现有微信式 `ChatInputBar`。
- 缺口：回复中状态在顶部和消息内重复；普通回复使用大面积白色容器；分享与透视动作常驻；动态卡片没有统一的一主一次动作语法；思考态存在多个注意力焦点。
- 硬约束：不修改语音输入框样式；不恢复底部四 Tab；不新增健康判断、写路径或自治行为；不伪造健康数据；辅助操作必须渐进披露。

## G1 · 准入裁决

- first_class_objects：`LeverageAction`、`HealthAgendaItem`、`ExecutionEvent` 的 Mobile 呈现与执行入口。
- core_loop_step：`Agenda top action -> Mobile execution -> Execution event`。
- target_surface / safety_level / autonomy_tier：Mobile / low / none。
- spec_required：是，新用户可见交互和信息层级变化。
- smallest_end_to_end_slice：单一思考状态 + 无框回答层级 + 一主一次行动卡 + 长按上下文菜单。
- stale_surface_to_remove：顶部“回复中”徽标、普通回复大白卡、常驻分享动作栏、重复加载指示器。
- **裁决：PASS。** 用户已确认原型方向和实施边界。

## S2 · 设计规格

- 链接：`docs/plans/2026-07-13-xiaoba-health-advisor-chat-ui-design.md`
- 边界：不改模型路由、健康结论、数据查询、语音输入条和底部 IA。
- 验收：首屏只有一个运行状态；普通回复不再形成大白卡；行动卡只保留一个主动作和一个次动作；长按默认突出复制；图片和动态卡片仍可回溯、编辑和分享。
- 未决问题：无。

## S3 · 规划

- 链接：`docs/plans/2026-07-13-xiaoba-health-advisor-chat-ui-implementation-plan.md`
- 反馈环路由：纯 JS/TS/UI，走 production OTA，不走 TestFlight。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge。
- 硬阻断：不得通过隐藏状态降低失败可见性；不得让卡片主按钮直接新增未确认写入；不得修改微信式语音输入交互。
- 待拍板分叉：无，用户已确认推荐方案。
- **裁决：PASS。** 只改端上呈现和既有回调入口。

## S4 · 研发任务分解

- 跨端 API 契约：无变化。
- 任务表：
  - [x] T1 移除顶部重复运行状态。
  - [x] T2 回复辅助动作进入长按菜单。
  - [x] T3 普通 assistant 回答改为无框内容层。
  - [x] T4 卡片分享改为渐进披露。
  - [x] T5 思考面板统一为单一进度源。
  - [x] T6 落地原型三种状态：结论/指标/行动、完整思考态、紧凑饮食草稿。
  - [x] T7 合并“使用数据”和“透视”，补回轻量微信/小红书分享。
  - [x] T8 模拟器视觉验收和 production OTA。
- 并发检查：已 `git fetch` 并审查远端 4 个提交，均为后端工具、Garmin 和图表改动，与本切片不冲突。

## S5 · 实现

- 分支：按项目约定在 `main` 实施。
- 已实现：紧凑 Header、无框 assistant、结论层、指标网格、单行动卡、单一流式分析面板、停止入口、合并依据抽屉、微信/小红书分享、渐进式卡片分享、紧凑饮食草稿。
- 2026-07-14 视觉加固：行动卡从突兀的深色大色块收敛为浅色内联操作区；空占位建议不再生成卡片；短写入回执按普通正文排版，不再套用大字号“小巴结论”。
- 未改变：微信式语音输入、后端 Agent 路由、健康判断、安全规则、写入确认与回执语义。

## G3 · 测试闸

- Mobile 定向 Jest：10 suites / 186 tests PASS。
- TypeScript：`npx tsc --noEmit` PASS。
- 定向 ESLint：0 errors；6 个既有 warnings，未冒充修复。
- `git diff --check`：PASS。

## G4 · 安全闸

- 不触及用药、诊断、基因、化验、安全规则、认证或新写路径。
- 中断/错误回复不会被包装成“小巴结论”，也不会暴露微信/小红书分享；错误仍保持可见。
- 行动卡按钮只发送后续 Agent 请求，不绕过既有写入确认和回执校验。
- **裁决：PASS。**

## S6 · 部署

- 路由：`mobile-ota`。
- production OTA：`e78e1949-c9ef-491e-8dc6-a31b978a0b8c`。
- iOS update：`019f5eb9-39e2-7844-baaf-a541608bb6ea`，runtime `1.3.1`。
- 对应主干：`62ad02c36df698167c89c819644c133e34a9fac7`。

## G5 · 部署健康闸

- EAS production 发布成功，iOS bundle 与 runtime `1.3.1` 匹配。
- **裁决：PASS。**

## S7 · 上线验证

- iPhone 17 Pro Simulator 连续两次冷启动后加载 production OTA。
- 截图：`/tmp/xiaoba-chat-ota-e78e1949.png`。
- 已验证：紧凑 Header、无框“小巴结论”、单一“依据与过程”入口、微信/小红书轻量分享、微信式输入框保持不变。
- 流式思考态与饮食草稿态不在真实账号制造测试记录，由 G3 自动化交互测试覆盖。

## G6 · 验证闸

- 待用户在真实设备冷启动后确认视觉层级和触控手感。

## S8 · 沉淀

- 待回写。

## 2026-07-16 · 多图连续拍照修复

- 用户问题：从“拍照记餐”进入后第一张照片立即触发发送，Agent 流式回复期间第二次相机入口被阻断；预览区的加号还只会打开相册。
- 根因：相机采集与消息提交耦合，无法形成“一轮多图、一次 Agent 请求”的明确状态。
- 修复：第一张和后续照片统一进入可持久化草稿，预览区分别提供“继续拍照”和“继续从相册选择”；最多 9 张，用户点击发送后才把全部图片作为同一餐上下文提交。
- 数据边界：照片只是同一轮识别上下文。除提示词约束外，Agent executor 已增加 mobile 图片记餐首轮的确定性 draft-only 闸门；即使模型自行传入 `confirmed=true` 也只生成待确认草稿，不写入 `DietRecord`，后续用户明确确认才允许写入。
- G3：相关 Mobile 回归合计 5 suites / 90 tests PASS；Backend 确认闸门纳入 138 项 focused pytest 并通过；`tsc --noEmit` PASS；`git diff --check` PASS。
- 发布路由：纯 Mobile TS，随本轮 production OTA 发布；真机相机连续调用待 G6 确认。

## 2026-07-16 · 今日重点条件状态条修订

- 用户问题：顶部“今日重点”长期重复同一行动和计数，关闭后仍显示占位入口，形成视觉疲劳。
- 方案：正常对话默认不显示；仅在安全/状态变化、Agent 运行或可恢复失败、到期/逾期、90 分钟内精确排程时显示单行状态条；完整计划从 `更多操作 > 今日计划` 打开。
- Feature Spec：`docs/specs/active/2026-07-16-mobile-chat-context-strip.md`。
- 设计与计划：更新 `docs/plans/2026-07-08-mobile-chat-today-focus-design.md` 和 `docs/plans/2026-07-08-mobile-chat-today-focus-implementation-plan.md`。
- G1：PASS。映射 `HealthAgendaItem / LeverageAction`，Mobile surface，safety `low`，无新写路径。
- G2：PASS。沿用现有 Today timeline 和 Agent turn state；缺失或含糊的排程时间不触发状态条；安全状态优先。
- S4 / S5：完成测试先行研发。移除常驻“今日重点”卡片、折叠占位入口和首屏加载骨架；新增按 `安全 > Agent 状态 > 到期/逾期 > 90 分钟内精确排程` 选择的单行状态条，关闭后完全释放空间；`更多操作 > 今日计划` 保留稳定入口。
- G3：PASS。相关 Jest `3 suites / 52 tests` 通过；TypeScript `tsc --noEmit` 通过；目标文件 ESLint 通过；`git diff --check` 通过。
- G5 本地构建：PASS。设置 `SENTRY_DISABLE_AUTO_UPLOAD=true` 后 iPhone 17 Pro 模拟器 Debug build 成功安装；Sentry 上传要求组织配置，不影响本地编译产物。
- G6 模拟器验证：PASS。逾期状态显示为单行 `已过时段 · 复查:血脂四项`，无常驻标题、计数或空占位，对话与输入栏未被遮挡。证据：`/tmp/mobile-chat-context-strip-final.png`。
- G5 生产 OTA：PASS。`production` / runtime `1.3.1`，update group `c79a55aa-fd14-4192-8894-b7ad71a6f457`，iOS update `019f6a31-9e36-787d-b4e2-c36786c3b170`，脚本已回读校验发布结果。
- 当前状态：S7 已发布，待真实设备冷启动完成最终 G6 触控与视觉确认。

## 2026-07-17 · 时间段提醒边界优化

- 用户问题：顶部时间段提醒是否合理，避免把时间骨架提示误显示成聊天提醒。
- 根因：90 分钟近期开关只检查 `scheduled_for`，没有排除 `status=info` 或不可执行的 advisory。
- 调整：保留 90 分钟精确排程窗口，但仅允许 `pending + can_complete` 的可执行项进入 Agent 顶部；纯时间窗提示继续留在 Today 时间线。
- 验证：Mobile context resolver / context strip 20 项测试通过，TypeScript 检查通过，diff 校验通过。

## 2026-08-11 · 顶部 Chrome 顺序优化（Quick Flow）

- 用户需求：按优先级继续优化顶部区域，并重新设计不够醒目的“新建会话”铅笔图标。
- G1：PASS。复用 `HealthAgendaItem / LeverageAction` 的既有 Mobile 呈现，不新增产品对象、健康语义、写路径或自治行为。
- 设计决策：条件状态条先去冗余、支持长标题和状态播报；新建会话采用“对话气泡 + 加号 + 浅绿首要态”；更多操作从齿轮改为省略号；小巴品牌区再轻量收紧。
- 备选取舍：单独加号过于泛化；方框铅笔仍接近“编辑”；组合气泡加号最能表达“开启新会话”。
- S2/S3：计划见 `docs/plans/2026-08-11-mobile-chat-chrome-refinement.md`。
- G2：PASS。纯 React Native UI，保持现有 callback、数据源、风险优先级和写入边界；可 OTA，但 iOS 1.3.3 (256) 正在等待 App Review，本切片暂不发 production OTA。
- 实现结果：普通/注意状态条去掉重复时钟图标并压至 40pt，支持两行标题；风险/错误仍保留状态图标；流式状态增加 polite live region。新建会话改为“对话气泡 + 加号”浅绿首要态，历史保持中性，更多操作改为省略号；小巴头像/标题/箭头收紧为 22/20/12pt，模型触发区仍保持至少 44pt。
- G3：PASS。3 个定向 Jest suite 共 15 项通过；TypeScript `--noEmit`、定向 ESLint、设计 token 闸与 `git diff --check` 通过。
- G4：PASS。只修改显示与触控反馈，callback、健康语义、用户隔离、写入和推送出口均未改变；风险态视觉优先级保留。
- 模拟器复核：Release 原生构建、安装与启动通过（0 error，6 个既有 build warning）；干净模拟器停在登录页，未在无审核账号凭据的情况下越权进入会诊页，因此真实页面肉眼复核明确记为待后续已登录环境补做。组件层渲染、尺寸、图标、触控与无障碍契约已由 15 项测试覆盖。
- 当前状态：S6，代码可集成；production OTA 继续暂停，避免 App Review 等待期出现审核包与线上 JS 差异。
