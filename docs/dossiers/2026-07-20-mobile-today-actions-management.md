# Dossier: Mobile 今日行动管理闭环

| 字段 | 值 |
|---|---|
| slug | `mobile-today-actions-management` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S8 上线验证 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | Mobile Jest / iOS Simulator / production OTA |

## S0 · 用户需求（逐字）

> 点击管理活动会跳转到第二张图片，但是无法跳回来，另外列表也有问题，无法管理，重新梳理这个链路，优化。

- 用户从小巴的今日行动卡进入管理页，需要处理今天要做的事并可靠返回对话。
- 当前只能进入全量行动/告警列表，无法形成完成闭环。

## S1 · Discovery

- 后端 `backend/app/services/inline_cards.py` 将今日管理入口写成 `/alerts`。
- `/alerts` 位于隐藏 Tab，`headerShown=false`，页面无返回入口。
- `mobile/app/(tabs)/alerts.tsx` 查询全部 active action cards 和 safety alerts，不是今日议程。
- `mobile/app/agenda.tsx` 已有 `/agenda/today` 和 `/agenda/complete` 能力，但页面信息重复、缺少返回和完整管理操作。

## G1 · RequirementAdmission

- classification: `bugfix + product_change`
- first_class_objects: `LeverageAction`, `AgendaItem`, `EvidenceEvent`
- core_loop_step: `recommend -> act -> measure`
- target_surface: `Mobile`
- source_of_truth: `/agenda/today`, `/agenda/complete`
- safety_level: `medical_boundary`
- autonomy_tier: `manual_confirm`
- smallest_end_to_end_slice: 小巴卡片进入今日议程，完成/跳过写回，返回小巴并刷新。
- stale_surface_to_remove: 今日管理不再进入 `/alerts`；安全告警页继续独立保留。
- **裁决：PASS**。用户已确认方案 A。

## S2/S3 · 设计与规划

- 设计：`docs/plans/2026-07-20-mobile-today-actions-management-design.md`
- 实施：`docs/plans/2026-07-20-mobile-today-actions-management.md`
- 非目标：不新增自动执行、不修改药物剂量、不重做语音输入、不删除安全告警页。
- 未决问题：无。

## G2 · 可行性与安全压测

- 复用已有接口，无新 schema、无新原生能力，Mobile 可 OTA。
- 所有健康写入保持用户确认；失败不显示成功。
- **裁决：PASS**。用户选择方案 A。

## S4 · 研发任务

- [x] T1 动态卡片路由改为 `/agenda`
- [x] T2 今日事项分组与文案纯函数
- [x] T3 完成/跳过写回与缓存刷新
- [x] T4 今日行动管理页面与返回闭环
- [x] T5 模拟器验证、文档、提交、OTA

## G3 · 测试闸

- PASS: 后端动态卡片与今日视图回归 `44 passed`。
- PASS: Mobile 今日行动、写回 Hook、Agenda service 和动态卡片注册回归 `81 passed`。
- PASS: `/agenda` 页面补充双行提交锁定验证，页面专项 `6 passed`。
- PASS: `npx tsc --noEmit`。
- PASS: 本批文件 ESLint 无错误。
- PASS: `npm run design:check`，设计 token 未新增漂移。
- PASS: `python3 scripts/check_doc_drift.py`，代码派生系统地图一致。
- PASS: 从提交 `63db2494f` 重建 iPhone 17 Pro 模拟器原生壳，Xcode build 成功（0 errors）。
- PASS: 模拟器真实深链打开 `/agenda`；空态、紧凑标题栏和无底部 Tab 的页面结构正确。
- PASS: 空态“返回小巴”和顶部返回键均实际点击验证，可回到原小巴对话；冷启动深链也有确定回退路径。
- 主干首次运行的旧 `v-z + services` 超大分片连续两次超过 600 秒进程时限；没有断言失败，但 Gate 仍按失败处理。已拆为 `voice-watch`、`wearable-reports`、`workday-workout`、`write-z`、`services` 五个隔离进程，并增加工作流合同测试。
- PASS: 新分片本地按 CI 参数完整覆盖原 360 项：`159 + 63 + 61 + 68 + 9 passed`；工作流合同 `7 passed`。
- 后续主干运行又暴露旧 `agent-a-h` 单进程包含数百项测试、偶发耗尽两次 600 秒的问题；已按 agent core / executor 文件族拆成五个隔离进程。
- PASS: agent 新分片本地按 CI 参数完整覆盖 `577` 项：`30 + 21 + 152 + 322 + 52 passed`；工作流合同扩展后 `8 passed`。
- 同轮还发现旧 `a-b-rest` 通过扫描整个 tests 目录构建超大进程；已拆为 `a-early`、`a-late`、`b`，并保持 agent 与 App Store demo 独立。
- PASS: a/b 新分片本地按 CI 参数完整覆盖 `701` 项：`265 + 252 + 184 passed`。
- 真实账号当日无行动，因此有数据的分组、行级锁定和操作菜单由页面组件测试覆盖，不为视觉验收伪造健康行动。
- **裁决：PASS。**

## G4 · 安全闸

- 今日列表只消费当前用户鉴权后的 `/agenda/today`，不新增跨用户查询。
- 完成和跳过继续复用 `/agenda/complete` 的显式人工确认；跳过必须选择原因。
- “稍后”只改变当前会话排序，并明确提示未写成完成，不伪造服务端回执。
- 写入失败保持原状态并显示错误，不做乐观成功声明。
- 未修改药物剂量、诊断逻辑、安全阈值或推送隐私出口。
- **裁决：GO。**

## S6 · 提交与集成

- 设计与计划：`42e67ae9a`。
- 实现：`63db2494f`。
- `main` 已推送到 `origin/main`；未纳入并行会话的无关工作树改动。

## G5 · 部署健康闸

- 后端从干净的 `origin/main` worktree 部署，生产提交为 `63db2494`。
- 部署健康度 `60/60 PASS`，skills manifest `22 = 22`。
- 生产 `/api/v1/agenda/today` 未鉴权返回 `401`，证明路由已加载；`/health` 返回 `200`。
- 后端近期日志未发现新的 error / critical / traceback / RLS superuser 告警。
- **裁决：PASS。**

## S7 · Mobile 发布

- production OTA runtime：`1.3.2`。
- EAS update group：`e04c34df-c835-496d-9ce3-76849f421217`。
- iOS update：`019f7dcf-af87-7780-ad69-c891ce6a7398`。
- 发布提交：`63db2494f1e8436e42517dc608756769da266b12`。
- 原生兼容性：`1.3.2` 生产壳已包含 `expo-video`；本切片没有新增原生模块，OTA runtime 匹配。

## G6 · 上线验证

- 生产后端、鉴权路由和 OTA 发布标识均已验证。
- 用户端需杀掉 App 后重新打开并应用更新，再从小巴行动卡点击“管理今日行动”完成最终真机验收。
- **裁决：PASS（技术上线）；真机用户体验纳入下一反馈环。**
