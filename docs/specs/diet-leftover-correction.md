# 餐后剩余照片修正

> Status: implementation
> Updated: 2026-10-22
> Dossier: docs/dossiers/2026-10-22-production-prompt-quality.md

## 决策与准入

将明确的餐后剩余照片修正请求从新增餐食链路分离，使用原餐照片和原始份量
生成绝对的实际食用内容提案，经用户核对后更新同一记录。

```yaml
RequirementAdmission:
  request: 餐后剩余照片修正已记录午餐，与回答质量优化一并上线
  classification: existing_workflow_repair
  first_user_fit: 减少饮食记录修正负担
  core_loop_step: intake observation and execution verification
  first_class_objects: [HealthTwin, WriteIntent, ExecutionEvent]
  target_surface: Mobile chat and existing inline diet editor
  source_of_truth: authenticated record plus server-owned original photo assets
  safety_level: sensitive health write
  prescription_or_causal_verdict: none
  autonomy_tier: propose_then_confirm
  evidence_provenance: original photo snapshot and current leftover image
  claim_hedging: photo amounts are estimates
  verification_window: same turn proposal and explicit save receipt
  success_metric: original record updated once, no duplicate meal
  added_user_burden: confirm proposed consumed quantities
  burden_justification: visual remainder does not prove exact personal intake
  non_goals: automatic deletion, guessed targets, retrospective production data repair
  smallest_end_to_end_slice: current-day unique named meal with original chat photo snapshot
  stale_surface_to_remove_or_archive: generic meal capture for leftover requests
  spec_required: yes
```

## 用户流程与契约

明确餐次和剩余照片 → 本人今日唯一原记录 → 原餐照片逐项对比剩余比例 →
按原始份量计算实际食用描述 → 现有 record_quality 编辑卡 → 用户核对后
recalculate-nutrition → 原记录同 ID 更新及真实保存结果。

Backend 负责所有权、目标及照片来源，模型只估算逐项剩余比例，不选记录、不写数据。
Mobile 复用已有 proposed_food_items、原 revision、确认按钮与幂等 key。
不新增 schema/API。日期、多目标、原图或原始份量不足时明确澄清；未知不当作 0。
全部未吃不自动删餐。原餐前快照始终作绝对基线，不从已修正的摄入量再次扣减。
确认保留原 revision，等待期间其他编辑导致 409；重试旧卡不能覆盖新记录。

## 验证

测试覆盖真实图片入口、零写入提案、逐项不同剩余比例、原基线重试、取消/他人/
跨日/多目标、缺项/遮挡/全剩、模型错误、同 ID 确认、幂等与 CAS 冲突。
使用合成数据；PostgreSQL 验证持久化语义，真实模型评测需对应授权和固定候选。
发布必须完成独立安全审查、精确 SHA CI、受控发布和线上版本核验。
