# Feature Spec: 我的进度信息层级与观察边界

> Status: implementing
> Updated: 2026-11-01
> Related code: mobile/app/my-progress.tsx

## Decision and problem

将现有进度页整理为本期行动、身体变化、建议进展和建议详情。原界面在零行动时
显示 0/0 与 0% 完成率，且将 independently graded 建议除以 completed 产生 2/0。
去掉重复的大比例卡和“AI 让你变好”的归因文案，保留已有数据与详情路径。

## Requirement Admission

- request: 优化截图中的我的进度页面。
- classification: product_change + bugfix。
- first_user_fit/core_loop_step: 帮助已有用户回顾执行与观察结果。
- first_class_objects: ExecutionEvent、HealthTwin、InterventionCycle。
- target_surface/source_of_truth: Mobile /my-progress；本人 progress 和 daily-plan/review API。
- safety_level: privacy_sensitive；prescription_or_causal_verdict: none。
- autonomy_tier: none；evidence_provenance: 已有本人记录与服务端评估。
- claim_hedging: absolute_disallowed；verification_window: 7/30/90 天。
- success_metric: 无零分母或跨集合比例；空行动不展示失败分数；变化不预设临床优劣；详情可访问。
- added_user_burden: 无；burden_justification: 复盘依据按需展开。
- non_goals: 不改变建议生成、健康写入、评估算法、原生能力或 week 导航模式。
- smallest_end_to_end_slice: 同一页重排、计数与空态修复、分区刷新/失败重试、本人会话隔离。
- stale_surface_to_remove_or_archive: 旧 2x2 百分比卡、重复改善叙事与技术术语说明。
- spec_required: yes。

## Behavior and acceptance

1. 7/30/90 天筛选具有选中状态与可访问标签；两个数据源同步切换和刷新。
2. 零行动明确“本期还没有行动记录”；只有分母有效且计数一致时显示行动完成比例。
3. 身体变化使用中性颜色、中文指标名、单位、最多两位小数；不把上升/下降预设为改善。
4. 建议采用独立计数，不将 graded/completed 当成递进集合；未知结果明确待分类，不伪造改善。
5. 评估列表保留零值、本人卡片详情导航与证据标签；不把 effect_size 自动当成百分比疗效。
6. 预测/观察依据按需展开，观察性非因果说明始终可见；不新增健康建议或写行为。
7. 两部分独立呈现加载、失败和重试；不显示原始异常，不用失败伪装零数据。
8. 查询及响应绑定 owner/会话 revision；退出、账号切换和 consent 变化清除旧展示，禁止持久缓存。
9. 组件、服务与隐私回归、类型/设计检查、独立 G4；发布保持完整 CI、后端和 OTA 独立回执。

## Rollout and boundaries

复用已授权隔离目录；不覆盖共享工作区。无 API/schema/native 变化。
默认模拟器验收；真实相机与个人设备 OTA 接收不由组件测试证明。
