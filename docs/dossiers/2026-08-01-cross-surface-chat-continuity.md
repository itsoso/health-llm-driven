# Dossier: Web / Mobile 对话连续性与 Mobile 全屏

| 字段 | 值 |
|---|---|
| slug | `cross-surface-chat-continuity` |
| 创建日期 | 2026-08-01 |
| 当前阶段 | S7 已部署，等待同账号跨端与 iPhone 真机验收 |
| 状态 | deployed_device_smoke_pending |
| 负责 | User / Codex |
| 反馈环 | Web deploy + Mobile production OTA |

## S0 · 用户需求（逐字）

> “支持全屏”
>
> “小巴 这两个字字体太小 要跟正文大小保持协调 或者设计更好的”
>
> “web的对话记录和mobile的对话记录 没有合并和统一”
>
> “好的 整个聊天页面铺满屏幕”

- 谁用 / 解决什么：同一账号在 iPhone 与 Web 使用小巴的人；解决页面像卡片而非主屏、品牌标题偏弱、跨端续接分叉。
- 当前绕过：手工打开历史列表寻找同一 conversation；Web 每次通过带 `?c=` 的链接恢复。

## S1 · Discovery

- Backend `backend/app/api/agent.py` 已提供同一 owner-scoped durable conversation store；不存在 Web/Mobile 两套数据库。
- Mobile `mobile/hooks/useChatEngine.ts` 优先 AsyncStorage conversation id，随后可偏好“每日健康简报”，最后才取服务端最近会话。
- Web `frontend/src/app/ai-assistant/page.tsx` 仅在 URL 有 `?c=` 时恢复，否则保持空白新会话。
- Mobile `ConversationSheet` 对简报/周聊做客户端置顶，Web 使用后端顺序，进一步造成视觉不一致。
- Mobile chat 用 top-only `SafeAreaView` 截断根背景；原生 Stack/Tab 未显式统一 scene background/presentation。
- 硬约束：对话为 L3 健康数据；只能按后端 owner filter 加载，不能按内容或标题合并。

## G1 · 准入裁决

- first_class_objects: `ExecutionEvent`
- core_loop_step: review/converse -> act -> verify
- target_surface / safety_level / autonomy_tier: Mobile + Web + Backend / medium / none
- spec_required: yes（新跨端契约 + 新用户可见行为）
- smallest_end_to_end_slice: 对齐 latest durable 续接与历史顺序；Mobile edge-to-edge + 标题比例。
- stale_surface_to_remove: Web blank-by-default、Mobile briefing/local-id-first、Mobile rounded-card root。
- **裁决：PASS**。不改变健康建议、写入自治或服务端数据结构。
- 用户确认：2026-08-01 已确认整页全屏和推荐的跨端统一方向。

## S2 · PRD

- 链接：`docs/prd/2026-08-01-cross-surface-chat-continuity.md`
- Feature Spec：`docs/specs/active/2026-08-01-cross-surface-chat-continuity.md`
- 权威产品基线：`docs/prd/reva-personal-health-os-prd.md`
- 边界：不物理合并消息、不新增 server pointer、不改 AI/健康写路径。
- 未决问题：无。

## S3 · 规划

- 链接：`docs/plans/2026-08-01-cross-surface-chat-continuity.md`
- 路由：Web 正常部署；Mobile 为 JS/TS/UI-only production OTA。
- 长杆：异步 boot 不能覆盖显式新会话/活跃 stream；全屏仍须尊重 iOS 安全区。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + 现有代码/测试契约检查。
- 已焊入规划：后端 owner-scoped store 仍是唯一真源；显式意图和 active stream 优先；不按标题/内容合并；无 schema 迁移。
- 待拍板分叉：全屏语义已由用户确认为“整个聊天页面铺满屏幕”；无剩余分叉。
- **裁决：PASS**。用户于 2026-08-01 确认推荐方案。

## S4 · 研发任务分解

- 跨端 API 契约：现有 `GET /agent/conversations` 与 detail 接口不变。
- [x] T1 Continuity/history RED tests（Mobile + Web，OTA/Web）
- [x] T2 Mobile canonical resume + server-order sheet（OTA）
- [x] T3 Web no-query latest resume（Web）
- [x] T4 Mobile edge-to-edge root + 32/28 header hierarchy + 44pt actions（OTA）
- [x] T5 G3/G4、CI、Web deploy、Mobile production OTA
- [ ] T6 同账号 Web↔Mobile 双向续接与 iPhone 真机视觉验证
- 并发检查：2026-08-01 开放 PR 已核，无同名/同范围 PR；在干净隔离 worktree 实现。

## S5 · 实现

- 分支：`codex/runtime-write-circuit-recovery`（起点与 `origin/main` 一致的干净 worktree）
- Web：无 `?c=` 时恢复服务端 latest；显式 URL/新对话用 generation guard 防止晚到 bootstrap 覆盖。
- Mobile：可恢复本地 turn 优先，否则恢复 owner-scoped latest；设备旧 id 只作空列表/失败回退；历史列表不再按简报标题重排。
- Mobile UI：根背景真正 edge-to-edge，状态栏透明；top/bottom 都读取动态 safe-area；原生 Stack/Tab scene 背景一致且根页无卡片转场轮廓。
- 品牌层级：头像 32pt、“小巴” 28/34；模型入口和三个一级动作均为 44pt 交互目标。
- feature commit：`4e78d8f87c7e25f08e564d26cb840bd5adb829c2`。
- production deploy/OTA source（含随后合入的 docs-only 主干提交）：`6164452870d3645f97c5f6e426996ab63ad86062`。

## G3 · 测试闸

- **PASS（本地）**：
  - Mobile 全量：287 suites，2262 passed，1 skipped；focused continuity/header/chat 141 assertions 复跑通过。
  - Web 全量：53 files，311 tests；focused page URL/竞态 18 tests；两端 `tsc --noEmit` 通过。
  - Backend conversation API：在 CI 对齐环境 `APP_ENV=development AGENT_RUNTIME_MODE=off` 下 48/48 通过，含新增 latest-first 与既有 owner isolation。
  - Mobile `design:check` 通过（raw hex 596 ≤ baseline 599）；targeted ESLint 0 errors（8 条既有 warnings）。
  - `check_doc_drift.py`、95 份 Dossier consistency、frontend page-freeze、`git diff --check` 均通过。
- 本机 `npm run build` 因已安装的 optional Next SWC 包为空、受限网络无法重取而不可执行；代码 typecheck/Vitest 已绿，发布前仍以 GitHub `frontend-build`（含 clean install + production build）为硬阻断。
- **PASS（CI）**：
  - feature commit `4e78d8f87` 的 GitHub Actions run `30730652072`：44/44 jobs success，含 frontend production build、Mobile 全量 Jest/typecheck、Backend 全分片、Mac、type drift 与 release invariants。
  - 最终生产 source `616445287` 的 run `30731563615`：44/44 jobs success。
  - 中间 docs-only main run `30730960303` 的 `backend-test-a-early` 曾在两个不同既有 agenda 测试位置各超时 600 秒、无断言失败；一次受控 failed-jobs rerun 通过，随后最终 source 的独立全量 run 全绿，不以重复重跑替代最终证据。

## G4 · 安全闸

- 触发：健康消息跨端展示与 owner-scoped history。
- **PASS**：API/schema/auth 均未改变；客户端只消费现有 authenticated owner-scoped list/detail，绝不按标题/内容合并；48 项后端 conversation API 覆盖 owner isolation。
- qwen3.7-max 匿名设计评测（未发送源码/路径/账号/健康数据）：`PASS_WITH_CONCERNS`。
  - 采纳：把模型入口和一级动作实体交互区提升到 44pt；确认动态 safe-area top/bottom 均有测试与实现。
  - 不采纳为本期 blocker：新增 server active pointer（与 Spec non-goal 冲突，且 local durable turn 已保护进行中写回执）；取消底层 latest 网络请求（generation guard 已在落状态前丢弃过期响应，取消只优化资源、不改变正确性）。

## S6 · 部署

- 路由：frontend deploy + Mobile production OTA。
- feature commit：`4e78d8f87c7e25f08e564d26cb840bd5adb829c2`。
- production source/deploy SHA：`6164452870d3645f97c5f6e426996ab63ad86062`。
- iOS production OTA：runtime `1.3.2`；group `5ae84fdf-0e71-4121-a34a-86dd6a747f51`；update `019fc0af-ce41-7259-8800-1d3451bb3682`；EAS dashboard `https://expo.dev/accounts/itsoso/projects/health-pilot/updates/5ae84fdf-0e71-4121-a34a-86dd6a747f51`。
- Mobile 上一已知可用回滚目标：group `8120489e-ab4c-47b2-a5ee-0b031486bfec`；iOS update `019fbff2-b49f-7023-88dc-bce236ad2d96`；执行前 dry-run `./scripts/mobile-ota-rollback.sh production`，确认后追加 `--confirm`。
- Web/backend 生产发布：`./deploy.sh --all --yes` 从一次性干净 `main` 克隆执行；数据库备份、234 表恢复演练、站外加密归档哈希/HMAC、schema rollback probe 均通过；服务器回滚点 `354ca6925e24d15a391e51a6bfd8967e4f57933e`。

## G5 · 部署健康闸

- **PASS**：
  - 生产 Next.js build 通过，73/73 静态页面生成；`health-frontend` PM2 online。
  - 后端目标 SHA 核验通过，最终健康度 `60/60 PASS`；runtime-only KB staged contract 与 22/22 skills manifest 一致。
  - 公网 `GET https://health.executor.life/api/v1/health` 返回 `healthy`，API/PostgreSQL/Redis/Celery 全连接。
  - 公网 `GET https://health.executor.life/ai-assistant` 返回 HTTP 200；未登录 `GET /api/v1/agent/conversations` 返回 401，owner-scoped 鉴权边界正常。

## S7 · 上线验证

- 同账号 Web→Mobile、Mobile→Web 各创建/续接一次；核对 conversation id 与历史顺序。
- iPhone 核对 status bar 全屏、刘海安全区、标题层级、键盘/Home Indicator。

## G6 · 验证闸

- 自动化/公网 smoke：PASS。
- 真机/发布用户确认：待完成；本机无可用 iOS Simulator runtime，不能伪造 status bar、刘海、键盘/Home Indicator 与 Web↔Mobile 同账号双向续接证据。
- 裁决：`PENDING_TRUE_DEVICE`，仅阻止 Dossier 关闭，不回滚已通过 G3-G5 的 production 发布。

## S8 · 沉淀

- 状态：等待真机证据后回流跨端 parity / Dossier shipped。
