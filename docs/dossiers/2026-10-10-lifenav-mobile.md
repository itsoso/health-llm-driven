# 完整个人周导航 Mobile

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 原生实现 |

用户原话：「增加mobile 版本」。继续此前已授权的整合、提交和最终部署发布，采用单 surface Quick Flow。

## G1 准入

裁决：PASS。既有个人规划对象的 Mobile 完整编辑，核心循环为计划、执行和回顾，manual_confirm；不扩张健康写权限、通知或外接 LifeNav。移除「详细规划请去 Web」的旧降级说明。

## G2 可行性和规划

裁决：PASS。现有 `/life-navigation` 只有今日添加、完成和简短复盘；Web 已有完整八视图，API/schema 已具备。沿用现有认证、版本 CAS 和私密备份。无新依赖/原生权限/迁移。规格与验收见 [Mobile tech-spec](../specs/active/2026-10-10-lifenav-mobile.md)。用户已授权全部完成；没有待拍板分叉。

## 实现与验证

同一父流程委托 Health Harness：mobile-engineer 独占页面/组件/页面测试，root 负责服务、纯模型、文件 IO 和文档，独立 reviewer 做 G4；不切换分支、不修改其他 session 文件。

run_path：`docs/_generated/harness-runs/afdc5baa28fd.jsonl`（本地，不提交）。

## G3 实现验证

裁决：PASS（本地，远端精确 CI 尚待执行）。先观察八视图缺失、备份 API 缺失以及选中上午仍创建灵活任务的失败回归，再实现。当前四组周导航测试 31 passed，TypeScript 通过；固定 7ed816a7b 的完整源码 Mobile 验证 335 suites、3397 passed、1 skip。共享目录期间 Prompt 会话新增红测试，未覆盖该工作；隔离验证首次缺少 Watch 被源码测试读取的文件，补齐同 SHA 源码后全量真实通过。iOS 实际 Bundle 导出通过（无 dotenv 输入、无 vendor 发布）。后端现有导航契约合跑 48 passed、6 PostgreSQL 专项 skips；本任务未改变数据库语义，PostgreSQL 证明以新候选完整 CI 的实际 PG 集成闸为准。System Map、导航生成物、doc-drift 和 Dossier 一致性通过。

背景只隐藏正文并在同账号内存恢复草稿；账号/consent 变化彻底清除。系统文件选择/分享的 inactive 交接不会取消自身操作，真正 background 或换号仍拒绝迟到返回。严格导入先预览、显式确认，恢复使用当前 revision CAS；临时文件清理测试通过。

## G4 与发布验证

7ed816a7b69193ce721ab183cf666389fdbd4e81 的独立 G4 裁决：GO。随后收紧分享文案为「已打开备份分享」，不把系统分享取消误称文件已保存。

按用户已授权的跨 session 整合，Prompt 会话交接四个冻结 Mobile 文件：`chatTransparency.ts`、其测试、`AnswerEvidencePanel.tsx` 和 `services/chat.ts`。该会话 64 tests/3 suites、TypeScript、独立安全 GO；本流程已核对四个文件摘要相同。只显示实际上报的逐次模型/Token/缓存/耗时及记录核验/结束里程碑，缺调用明细或时钟对齐证据会明确保留未知。不改后端推理、健康写入、提示词或原生依赖；后续 Token 节省方案不混入本批。合并候选重新全量验证与固定 commit 独立 G4。

G5 待精确 CI、后端同 revision 成功回执与可信 OTA；不得重发旧失败 OTA。G6 未验证：iOS 模拟器已启动，但 Mac 锁屏导致 CUA 无法操作，没有拿合成截图或旧包冒充候选 UI 通过。
