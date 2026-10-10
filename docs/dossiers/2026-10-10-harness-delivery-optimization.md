# Health Harness 交付流程优化

| 字段 | 值 |
| --- | --- |
| 状态 | in_progress |
| 当前阶段 | S5 实现与增量验证 |

## G1 范围与授权

裁决：PASS。

用户在 CI、部署、OTA、TestFlight 复盘后要求“按照你的规划实施”。本轮优化既有工程交付链，不新增健康产品行为。Controller 为 health-harness-orchestrator，safety-gate overlay；适配器修改按 skill-creator。superpowers 禁用。沿用 main，保留所有其他业务改动，只提交本任务文件。

run_path：`docs/_generated/harness-runs/19e0be37a2cc.jsonl`（本地，不提交）。

## G2 计划与验收

裁决：PASS。实现范围沿用用户批准的复盘规划，失败恢复不扩大发布权限。

1. 接续 `346035f78` 已实现的历史封存和 transport 优化，取得生产原回执与分段计时，不重复发布。2026-10-10 首次检查发现 run `38020468119` 正在执行，生产有同 SHA STARTED 和业务租约；本轮仅只读跟踪。
2. OTA 增加真实 export/制品/漂移检查到 claim 之前的 prepare 模式，fresh runner validate 调用它；禁止 RPC claim/vendor update。发布仍重新验证并只 export/publish 一次，失败恢复保留原回执。
3. 既有 ledger 增加交付证据关联及保守的恢复建议，始终只是索引，不作为发布许可；补只读环境诊断。
4. 汇总 GitHub job/step 的 CI、部署、构建、上传计时，分开首轮、重跑、预检与真实执行；未知 Apple processing/安装验收保持未知。
5. 统一 Claude/Codex Harness 适配器的分支、文件归属、授权、单 ledger 与发布语义。保留现有 16-worker CI，不再追逐已否决的单样本重排或 12-worker 方案。

## 基线

上轮读取最近 80 次运行，24 次 2026-10-09 起首轮成功的 16-worker 完整 CI 中位 498.5 秒，范围 438–560 秒。26 次 Trusted release 中 15 次绿色仅 preflight。Build 275/276 的 upload claim 步骤为 57/166 秒，构建步骤为 425/435 秒；仅是两次观测，不推断稳定收益或因果。

## G3 验证

已观察 OTA prepare 10 项 RED、startup helper 14 项 RED、ledger 4 项 RED、doctor 3 项 RED、性能报告 13 项 RED、workflow 3 项 RED。组合定向 325 passed / 1 macOS 不适用 skip；适配器治理与包合同 115 passed；来源治理、System Map、秘密扫描及 diff-check 通过。完整 CI-mode 工具集成仍待固定提交验证。工作区 `.venv/bin/python3.12` 可用但不在 PATH；测试使用独立临时 Python 3.12 环境，不修改全局解释器。

## G4 安全审查

待固定提交独立审查。任何 BLOCK 回实现，不绕过来源、精确 CI、授权、消费记录或租约。

## G5 发布与 G6 验收

本轮尚未 push/deploy/OTA。已有生产发布 `38020468119` 归其原运行所有：只读复验后端 SUCCEEDED、生产 SHA=346035f78、租约已释放、五项服务 active；封存 generation 1 覆盖四条历史记录。部署脚本 finalized=346 秒；远端 checkout 阶段从 3→100 秒，Pi install 123→129 秒，不据单次观测宣称稳定提速。原回执见 `docs/reviews/2026-10-10-harness-existing-release-readback.json`。同 SHA 发布不重发。源码交付、CI、生产工具启用、供应商上传、Apple processing、模拟器验收分别记录。
