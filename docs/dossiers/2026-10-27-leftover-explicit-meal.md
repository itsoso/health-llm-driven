# 剩菜照片明确餐次直接核对

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 独立安全审查 GO；已交唯一发布者，等待最终批次模型闸、CI 与上线 |

## G1 准入

裁决：PASS。用户提供小气候聊天截图并要求协调图标优化、修复饮食修正问题。沿用现有 [剩菜修正规格](../specs/diet-leftover-correction.md)，修复已有流程的冗余澄清，不增加自动保存、视觉精确性或跨用户权限。Controller 为 health-harness-orchestrator，safety-gate overlay；System Map 该路径未索引，中央校验通过，已读源码及相邻测试。

本地 Harness trace：`docs/_generated/harness-runs/8579a79a1da7.jsonl`。

## 归属与交付

- 品牌任务 `01a17c3a-39a5-7360-9adf-015ae50cbb0f` 负责聊天左上角图标和最终统一发布/送审，状态见 [品牌 Dossier](2026-10-27-xiaoqihou-brand.md)。本任务不写品牌/icon 文件，不独立发布。
- 本任务拥有 `diet_leftover_correction.py`、对应回归、本 Dossier 与现有规格的增量；已通知发布者额外占用 `agent_executor.py` 的 panel 分流排除条件，不改其他 executor 逻辑或品牌任务正在处理的送审状态。最终给发布者固定提交、测试及独立安全审查证据，再由其绑定最终完整 CI 和发布候选。
- 原截图的真实健康记录和图片不用于模型重放，不代用户修改原餐。

## G2 根因与方案

基线 `8f7d94696424f92ff57243edb906cd6d2dd14a3a`。其已有 `e8be03fbc` 修复无图补充入口，当前普通及 multi-model 两种入口的“根据剩菜照片修正今天午餐记录”均可接续合成的本人同日唯一照片，不能把历史拒绝回复当作新版本重现。

仍存在的问题：附图“记录这餐 剩余这么多 计算下今晚真正摄入量”在完整 caption 语法中已包含明确晚餐，却只用于生成“再说一次晚餐”的澄清示例。新增真实入口和提案测试在原实现得到 4 failed / 71 passed，复现该多余步骤。

修复仅允许完整 caption 同时具备记录/计算请求以及唯一今日餐次时进入原提案流程；裸照片、无餐次、不同餐次冲突、他人、历史/未来日期、否定、引用和假设不构成授权。不从消息时间猜餐次。仍核验本人当前会话消息、今日唯一原餐、原始照片和份量；照片比较只返回待确认卡，没有保存回执。确认沿用原记录 ID、版本和幂等边界。

## G3 验证

- 基线 60 项通过。新增回归先 RED 4 项，修复后首轮 75 项通过；随后去掉入口测试中非必需的 preprocess 判定桩，继续验证真实判断链。
- 保留无图午餐在普通及 multi-model 模式的实际 stream 回归，通用模型调用被失败哨兵禁止，必须返回原记录的确认卡。
- 路径级 LLM change gate 返回无需 live；视觉模型、schema、prompt 和结果计算未变化。该自动判断不代表真实视觉质量验收，最终发布批次仍由唯一发布者运行适用闸门。
- PostgreSQL、最终邻近回归及 G4 尚待完成，不宣称已上线。

后续 G3：去掉 preprocess 桩后，CI-mode 邻近 429 项通过；完整剩菜 PostgreSQL 75 项通过，覆盖同 ID 确认、幂等与旧 revision 冲突。进一步添加无图计算 caption 的普通/panel 回归，panel 路径 RED，确认通用分析会提前截走不以“记录”开头的合法计算请求；需要为已闭合的剩菜请求增加明确排除，其他 panel 条件保留。首轮失败哨兵是 coroutine，改为同接口 async generator 后重新验证 RED，避免以接口桩错误冒充路由问题。

最终本地 G3：同接口 panel 哨兵 RED 为 1 failed / 3 passed；限定修复后，CI-mode 431 passed、零 skip，含剩菜、照片修正、照片营养追问、写意图范围。真实 PostgreSQL 增量复跑普通/panel 两类文字续接 4 passed、零 skip，原 75 项结果保留，两个集合有重叠不相加。第一个临时库退出命令超过60秒，日志证明 shutdown checkpoint 耗时77.48秒；随后独立 `pg_ctl status` 确认无运行服务才清理本任务目录，原 stop_exit=1 保留。第二个临时库正常关闭并清理。中央地图校验通过。

实际最终改动包含 `agent_executor.py`，路径级 LLM change gate 因此明确要求真实模型回归；前述“无需 live”仅对应尚未补 panel 条件的中间范围，不能用于最终发布。未调用真实模型、未声明豁免、未设置仓库确认变量。已告知唯一发布者在最终合并候选运行适用 live gate、绑定精确 SHA 与完整 CI，再统一发布；本任务 G3 局部通过不等于 G5/G6 或线上真实照片验收。

## G4 与统一发布交接

独立 reviewer `leftover_explicit_meal_safety` 对固定代码提交 `ea779bbe42a1c30bc20aa6ca8ee5330c01b813c1` 给出 GO，无阻断项。审查方独立完整回归 77 passed / 0 skipped，另外 4 个正例与 92 个否定/引用/他人/日期/取消反例全部通过，中央地图 PASS；证据 `/tmp/reva-leftover-independent-review.xml`、`.log`。确认 panel 排除仍进入原 owner/current-message/date/image/readonly checks，未新增自动写权限。

本任务仅本地 commit，没有 push、模型调用、授权轮换、后端或 OTA 发布。唯一发布者为品牌任务，已交接固定源提交与所有验证边界；图标、审核准备与后端修复汇合后必须重新绑定模型与完整 CI，不能用本地 GO 或旧线上版本冒充此次截图路径已上线。
