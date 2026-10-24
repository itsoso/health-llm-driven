# 用药通知直接落到本次提醒

Status: implementation; not published
Updated: 2026-10-24

## Decision and problem

用户截图显示点击 18:00 通知后打开空聊天并填入未发送问题。源码确认：后端按 owner/date/time 聚合 `medication_ids`，客户端 `medicationReminderRoute` 丢弃 ID 并生成聊天草稿。此次恢复确定性的提醒落地，不依赖模型解释通知。

## Requirement admission

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
- G4 first review NO-GO：无日期/时区冲突 context.log 不能证明原通知 occurrence 完成。已改为优先显示日期待确认/时区需核对、查看并核对，隐藏完成断言；两项带已有日志的测试先 RED 后 GREEN。复审 pending。
- G5/G6: not published. 当前基线 010d0c5f 的真实模型验收曾失败，后续合成轮次不能替代失败归因；原生依赖差异仍阻断既有 OTA 通道。本修复不得宣称已到用户设备。

## Delivery boundary

不改生产、演示账号或真实健康记录；保留工作树其他修改。已有用药明细写入流程不变，通知点击和分组页均无 POST/model call。
