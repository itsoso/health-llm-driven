# Dossier: 小巴健康参谋型对话界面

| 字段 | 值 |
|---|---|
| slug | `xiaoba-health-advisor-chat-ui` |
| 创建日期 | 2026-07-13 |
| 当前阶段 | S4 需求分解 |
| 状态 | building |
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
  - [ ] T1 移除顶部重复运行状态。
  - [ ] T2 回复辅助动作进入长按菜单。
  - [ ] T3 普通 assistant 回答改为无框内容层。
  - [ ] T4 卡片分享改为渐进披露。
  - [ ] T5 思考面板统一为单一进度源。
  - [ ] T6 测试、模拟器视觉验收和 production OTA。
- 并发检查：已 `git fetch` 并审查远端 4 个提交，均为后端工具、Garmin 和图表改动，与本切片不冲突。

## S5 · 实现

- 分支 / commit：按项目约定在最新 `main` 实施，待回写。

## G3 · 测试闸

- 待回写。

## G4 · 安全闸

- 不触及用药、诊断、基因、化验、安全规则、认证或新写路径；仍需检查 UI 没有掩盖错误与证据入口。
- 待回写。

## S6 · 部署

- 路由：`mobile-ota`。
- 待回写。

## G5 · 部署健康闸

- OTA 发布结果与运行时兼容性待回写。

## S7 · 上线验证

- iOS Simulator 截图和 production OTA 真机验收待回写。

## G6 · 验证闸

- 待用户在 OTA 后确认。

## S8 · 沉淀

- 待回写。
