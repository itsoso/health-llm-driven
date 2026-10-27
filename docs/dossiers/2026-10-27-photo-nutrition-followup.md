# 照片营养缺失追问与汇总修复

| 字段 | 值 |
|---|---|
| 状态 | shipping |
| 当前阶段 | S6 主干已整合，等待精确 CI、后端部署与适用 OTA |

## G1 准入

裁决：PASS。修复截图所示的既有健康查询或原记录补算入口，不增加诊断、自动写入或跨用户读取权限。

- 日期：2026-10-27
- Controller：reva-workflow-router quick_fix；overlay：safety-gate；System Map 按需查询。
- 状态：本地实现与回归；首轮独立审查 NO-GO 已修复；新固定 diff 独立重审 GO；PostgreSQL 验证通过。发布受主干分叉阻断。

## 问题与证据边界

截图显示“最后一张图片 没有计算出热量”返回通用失败；汇总含一条营养缺值记录，却显示“全天合计”及“脂肪适中”。截图不能证明原照片识别、估算服务或保存哪个环节失败，也没有足够信息替用户修改健康记录。

源码确认：旧 composer 采用上游 `sum(value or 0)` 总数，并以非零总数推导全天营养评价；追问无照片到原记录的确定性补算入口。新增 stream 测试进一步发现 panel 在补算入口前分流，已添加闭合请求识别的路由排除。

## 变更与边界

- 逐记录、逐营养项汇总已知值；未知保持 null，真实零保留；原始精度求和后复用展示格式化。附加 nutrition_coverage v1；保留旧 descriptor 信封 v1。
- 新旧移动端卡片均不再展示 缺乏依据的全天充分/不足评价；展示“已知小计”或“已记录合计”和完整性说明。历史卡片由逐餐值重建小计。
- 原句及有限等价完整句只查当前用户、当前会话最后一条图片消息，24 小时内，要求持久化图片列表恰好一张、唯一 ordinal=0、未删除、已绑定的 food asset 与本人原记录。新图未绑定时不跳过它选择更旧记录；不把最近一餐冒充最后一张照片。
- 返回原记录编辑卡等待核对；不自动重放模型或写入。保留原日期、照片、精确营养基线与版本。保存复用现有带版本、幂等键的重新估算接口。定位失败给出饮食页原记录补算入口。
- 编辑卡对未改食物的补算显示明确重新估算文案，不谎称份额已改。
- 不修改数据库 schema、原始数据或 API 写权限；不读取或修复截图用户的真实记录。

## 验证

- Red：汇总新增 8 项全部失败；缺值移动卡 2 项失败；照片定位、普通流与 panel 新测试复现缺入口/分流问题。编辑卡新增测试发现补算按钮文案仍为普通保存。
- Backend：`test_diet_summary_card`、`test_diet_summary_missing_nutrition`、`test_diet_photo_nutrition_repair`、`test_diet_photo_correction`、`test_diet_leftover_correction`、`test_meal_input_clarification`：189 passed。
- Mobile：DietSummaryCard、RecordQualityCard、revaUiBlocks：66 passed；追加汇总边界测试后 DietSummaryCard 单独 6 passed，合计 68 项。
- `npx tsc --noEmit`、`git diff --check`、`./scripts/system-map-check.sh` 通过；无生成物漂移。
- PostgreSQL 使用独立本地临时测试库与合成数据；58 passed（照片定位/普通与 panel 流/原记录补算及现有 recalculate_nutrition 鉴权、失败零写、幂等、版本冲突、审计回执测试）；临时实例测试后停止。初始集群 SQL_ASCII、测试误给 UTC-naive 列传 aware 时间导致的夹具问题已纠正为 UTF8 数据库及模型约定的 naive UTC；不修改产品时间语义。
- 未完成模拟器视觉验收、线上真实照片补算或部署后验收，不以 mocked estimator 结果代替生产模型质量。

## 独立安全审查

- `photo_nutrition_safety` 对 `d0610186b` 裁定 NO-GO：多图消息仅第一张生成 asset 时可能误认最后一张。已补多图单 asset、错位 ordinal、空列表、畸形列表 4 个失败测试，随后加单图列表及 ordinal=0 校验。
- 修复后照片营养、照片编辑、剩余照片邻近回归 76 passed；PostgreSQL 新边界完整复测 24 passed。
- `photo_nutrition_safety_final` 对固定 diff `0ac83453b..6b19d6f3d` 裁定 GO（限定本地源码安全审查），独立验证 backend 42 passed、mobile 52 passed、whitespace 通过。首轮阻断已关闭，无新阻断项。
- 全部任务回归合计 193 个后端场景（189 初轮 + 4 新边界；其中邻近 76 项在修复后重跑），移动端 68 项；PG 初轮 58 项及修复后本任务 24 项均通过。临时 PostgreSQL 实例已停止。
- 实现提交 `d0610186b`、多图修复 `6b19d6f3d`；此文档收尾不扩大受审实现范围。

## 发布门禁

起始 main 相对 origin/main ahead 11 / behind 36，且有其他任务未提交文件。仅提交本任务路径，不 push、merge、deploy 或 OTA。按 AGENTS.md §7 及 deploy 规范，须先恢复可验证目标主干、精确 SHA CI、发布锁/回执与完整集成闸。独立 safety GO 不豁免这些条件。不创建备份或回退副本。


## 本次部署续接（2026-10-27）

用户明确要求“部署和OTA”。本地已将远端 `b99d631023d6ced7762e89611f403efde8022faa` 整合为 `6b8c66628fc68f27e36eeb99b461acb30707d76b`；唯一业务冲突保留体重与睡眠的两条独立范围说明，地图重新生成，未提交工作摘要逐一保持一致。此前“分叉、未合并”的描述为历史断点；当前仍未部署。

整合后相关后端274项、移动端68项通过；独立 integrated_release_safety 对上述精确候选累计diff给出GO，独立后端97+158项、移动端52项通过。System Map、secret scan通过。此次补齐本任务Dossier的可解析状态与G1裁决，随后重新运行一致性闸；不以文档修复替代精确SHA完整CI。生产只读核对为4f8fffed3、三个服务active、发布lease不存在；版本授权、trusted后端validate/deploy及OTA validate/publish待执行。
