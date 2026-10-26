# 用药通知直接落到本次提醒

| 字段 | 值 |
|---|---|
| 状态 | shipped |
| 当前阶段 | G6 发布回执核验；设备更新应用未观察 |

Status: shipped; backend and OTA verified; device update application unverified
Updated: 2026-10-26

## Decision and problem

用户截图显示点击 18:00 通知后打开空聊天并填入未发送问题。源码确认：后端按 owner/date/time 聚合 `medication_ids`，客户端 `medicationReminderRoute` 丢弃 ID 并生成聊天草稿。此次恢复确定性的提醒落地，不依赖模型解释通知。

以下未发布状态为历史阶段记录，当前交付状态以末尾发布核验为准。

## G1 准入

裁决: PASS。以下准入与既有用药提醒详情契约一致；新增分组页仅读取，由用户逐项确认。

- Classification: bug fix with grouped reminder surface.
- First user fit/core loop: 降低服用记录操作负担，HealthAgendaItem → 用户核对 → ExecutionEvent。
- Source of truth: 认证用户的既有 `/medication/medications/{id}/reminder`；通知只携带 ID 与 occurrence，不是服用证据。
- Target surface: 单项既有详情，多项只读清单，每项进入既有确认页。
- Safety/autonomy: 敏感提醒，用户明确确认才写；不调整剂量，不自动记录，不批量服用。
- Verification window: 当前候选的路由、冷/热启动、账号隔离、日期与失败路径回归。
- Success metric: 有效通知不再打开聊天草稿；全部条目保留，每项都有明确读取状态。
- Burden: 多药需逐项确认，避免一键误记。缺失日期保留待确认，不推断今天。
- Non-goals: 改推送正文、数据库、药物方案、历史数据或模型能力；不查询用户真实健康记录。
- Smallest slice: 解析 ID 列表 → 有界只读 GET → 明确详情按钮 → 复用既有确认与幂等回执。

## Gates and evidence

- G1/G2: 上述准入，复用既有 landing 的 owner/revision/date 守卫；无 schema 变化。
- RED: `/tmp/reva-medication-route-red.log`，真实 server group payload 预期清单而实际 chat。
- Implementation: ID 全量验证，拒绝空/超限/含非法项/相互冲突 ID，不静默截断；仅标识符和 occurrence 入路由。
- 读取失败保留失败行；不把失败解释成未服用；切换账号和过期响应清空/丢弃，返回页面重新读取。
- 最终定向回归：7 suites / 91 tests passed（`/tmp/reva-medication-landing-final-tests.log`）；TypeScript passed（`/tmp/reva-medication-landing-tsc.log`）；System Map check passed。包含冷/热启动分组通知。
- G4 first review NO-GO：无日期/时区冲突 context.log 不能证明原通知 occurrence 完成。已改为优先显示日期待确认/时区需核对、查看并核对，隐藏完成断言；两项带已有日志的测试先 RED 后 GREEN。独立复审 G4 GO，固定候选 `d62bf8a43703f92a1deb75664af7685ee1a7a56b`；裁决只覆盖通知 landing 修复，不代表已发布。
- G5/G6: not published. 当前基线 010d0c5f 的真实模型验收曾失败，后续合成轮次不能替代失败归因；原生依赖差异仍阻断既有 OTA 通道。本修复不得宣称已到用户设备。

## Delivery boundary

不改生产、演示账号或真实健康记录；保留工作树其他修改。已有用药明细写入流程不变，通知点击和分组页均无 POST/model call。

## 2026-10-26 发布续行

完整 CI-mode 暴露本档案缺少机器可识别状态表和 G1 标题；已补齐格式，不改此前安全裁决或发布状态。b01 候选发布不变量 JUnit 4804 项、49 跳过、零失败零错误；档案闸失败不能称完整 CI 通过。用户已确认 c280 TestFlight 来源并授权完成后由本会话接管，GitHub 40158185108 已 completed/success；Apple 处理和新 OTA 基线另行核验。

## 2026-10-26 用户截图复核与发布收口

- 用户再次反馈 18:30 点击提醒仍出现“基于用药提醒”的聊天草稿。旧提交 `845981964` 的 `medicationReminderRoute` 包含截图中的精确文案；修复提交 `89d77ecb0` 已移除该草稿入口，单项进入详情、多项进入只读清单。
- 祖先校验确认该修复已包含在已发布候选 `03434bcabf39be9394a65098159c0ae9c338e434`。本轮没有新增行为改动，也没有重复发布同一候选。
- G5: 精确候选完整 CI `40304979855` 成功；backend `40307096244` 和 OTA `40309165168` 成功，后者于 2026-10-26 18:45:40 Asia/Shanghai 完成，晚于截图时间。完整回执见 [本次发布回执](../reviews/2026-10-26-notebook-release-receipt.json)。
- G6: 本轮 SSH 只读复核生产 HEAD 为 `03434bcabf39be9394a65098159c0ae9c338e434`，后端与两个 Celery 服务 active；原 OTA completed 回执仍为 SUCCEEDED。group `3ed48372-e105-4212-aabd-83ce6688e486`，update `01a177d0-ab37-7612-80ae-8a6d5df049a4`。
- 新鲜回归：通知路由、冷/热启动点击、通知历史、单项/分组页面、提醒读写服务，共 6 suites / 89 tests passed；System Map check passed。打开通知不写服药记录，日期/时区核对及账号隔离守卫保留。
- 验收边界：没有读取真实健康记录、没有写入真实服药记录，没有观察用户手机实际下载/应用该 OTA；截图证明旧行为存在，不能单凭截图确定设备当前版本。可在设置 → 检查更新，待“新版本已准备好”后点“立即更新”，再重新点击原通知。
