# Health Harness 交付流程优化

| 字段 | 值 |
| --- | --- |
| 状态 | completed |
| 当前阶段 | G6 工程工具交付验收完成 |

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

已观察 OTA prepare 10 项 RED、startup helper 14 项 RED、ledger 4 项 RED、doctor 3 项 RED、性能报告 13 项 RED、workflow 3 项 RED。组合定向 325 passed / 1 macOS 不适用 skip；适配器治理与包合同 115 passed；来源治理、System Map、秘密扫描及 diff-check 通过。固定实现提交 `aada1ad598cead66db3792ff43a8a833c2834830` 在干净源码快照中执行当前 CI YAML 的完整 release-invariants 命令：2844 passed、20 skipped、84 subtests passed，538.97 秒，退出码 0。快照内治理/包/ledger/doctor 130 passed，193 份 Dossier 检查通过；未将其他任务的脏文件带入候选。远端真实 Linux startup/export 已通过，见 G5/G6。工作区 `.venv/bin/python3.12` 可用但不在 PATH；测试使用独立临时 Python 3.12 环境，不修改全局解释器。

## G4 安全审查

裁决：GO，独立 reviewer 审查固定实现提交 `aada1ad598cead66db3792ff43a8a833c2834830`，250 passed / 1 skipped；额外验证伪造 authority、未知 OTA 结果、证据路径穿越和矛盾诊断状态。四项前向场景通过：保留他人脏文件、沿用 S5 父 run、未知发布不重发、扫码安装不转 TestFlight。该 GO 不替代精确 SHA CI 或部署许可。任何 BLOCK 回实现，不绕过来源、精确 CI、授权、消费记录或租约。

## G5 发布与 G6 验收

本轮已 push 工程实现与证据，不执行生产部署或 OTA publish。已有生产发布 `38020468119` 归其原运行所有：只读复验后端 SUCCEEDED、生产 SHA=346035f78、租约已释放、五项服务 active；封存 generation 1 覆盖四条历史记录。部署脚本 finalized=346 秒；远端 checkout 阶段从 3→100 秒，Pi install 123→129 秒，不据单次观测宣称稳定提速。原回执见 `docs/reviews/2026-10-10-harness-existing-release-readback.json`。同 SHA 发布不重发。源码交付、CI、生产工具启用、供应商上传、Apple processing、模拟器验收分别记录。

旧 SHA 的 OTA run `38020977702` 在发布器调用前因 GitHub metadata unavailable 失败；本轮只读核对失败日志，不重发。新 CI 和工具交付需要精确提交的远端验证，不需为本轮工程工具改动另建原生 TestFlight 包。

## 最终精确提交验证

G5/G6：PASS（工程工作流与工具范围）。实现提交 `aada1ad598` 与证据提交组成候选 `bd80c9663b9e7635c49c4366875c005c7554a1f0`，CI `38021812837` 31/31 成功，墙钟 544 秒。新增真实 OTA runner 检查 100 秒，release-invariants 247 秒，最长后端分片 418 秒；本次观察在既有 CI 基线范围内，不宣称稳定提速。

同候选 trusted OTA validate `38022366081` 成功，下载审计工件确认 `PREPARATION_PASSED / preparation / verified`；publish 步骤 skipped，无 claim 消费或 vendor update。本轮没有新原生构建、TestFlight 上传或应用 UI 验收。最终记录提交只归档该候选的证据，不继承或生成新 SHA 的发布许可；下次发布仍须当时当前 main 的完整 CI、同 SHA 后端和新 validate。

结构化证据：`docs/reviews/2026-10-10-harness-delivery-verification.json`。

## 2026-10-13：发布速度续接

用户反馈“发布的速度还是很慢”。本次以同一49d候选的实际运行证据续接，先区分监控改进与尚待实现的授权事务去重，不把方案宣称为生产提速。

基线：完整CI38332269936的有效job执行跨度645秒，最长balanced-10为562秒；可信发布38333973742的有效job跨度450秒，其中backend410秒。两者均不含最早runner开始之前的排队。bootstrap-stage完成至rotate完成的本机日志墙钟间隔510.61秒，包含操作间等待，不能当成纯授权CPU/IO耗时。revoke前端历史核验52.06秒、读取868831232字节；key-retirement同类核验47.34秒、读取812875776字节。静态源码确认当前rotation已有锁内memo，但独立revoke/retirement/rotate不共享核验上下文。单次样本不作为稳定P95。

本轮已实现的低风险改进：`scripts/release_run_status.py`只读取固定canonical仓库的一个run，绑定完整SHA和run attempt。单次读取超时12秒，最多3次读请求和2/4秒退避，预算约42秒；不轮询等待数分钟。读取错误不输出原始stderr，未知状态退出2；成功/失败/进行中分别退出0/1/3，所有结果release_authority=false。没有dispatch、rerun、取消或发布动作，没有使用旧观察结果授权下一步。用它替代本会话反复重建的长时间gh run watch，调用间由外层继续工作和汇报。

RED12 FAIL/13 PASS（新增模块未实现），GREEN29 PASS，官方CI-mode runner真实退出0。新增真实GitHub标题兼容回归：Trusted release的run-name带target与SHA，不能以静态workflow名误拒绝；错误输入SHA仍拒绝。首次线上只读观察因此返回identity_mismatch，保留并修复后再验证；不把unknown当成功。System Map全局检查通过；初次python3.12不在PATH的环境失败保留，随后使用项目解释器路径通过。

后续授权性能实现优先级（尚未交付）：

1. 将revoke、private-key retirement与rotate设计为同一原launcher/build锁内的可恢复事务，只对已核验且fingerprint未变化的备份使用事务内memo；回执、小文件权限/摘要、租约、活体前端和锁inode仍在各状态转换重查。先补原始失败/中断/漂移测试再实现，跨进程持久缓存旧安全裁决不在方案内。需要保护root-only原回执，明确各步失败后的继续语义，禁止自动重放发布。
2. 固定候选后并行独立审查与本机集成检查；安全GO前不push。避免同一固定SHA无新改动时重跑同一广域套件；保留完整精确主干CI与相称专项验证，不跳过安全/来源门。
3. 从本次最长后端分片的现有timing工件定位耗时用例与安装等待，再按历史多个成功run验证分片或依赖复用；不凭单次数据盲目改worker数。后端410秒须用deploy分段证据继续拆分，不能推断均为构建。

验收目标：正常状态读取单次≤42秒预算，未知不伪装成功；下一版授权事务同批active备份内容读取一次、状态转换仍可检测漂移，发布结果与恢复语义不变。整个发布时长改善仍待后续同范围自然发布确认。本轮工具改进不需要后端重部署、OTA或TestFlight，不修改任何生产授权或历史备份。
