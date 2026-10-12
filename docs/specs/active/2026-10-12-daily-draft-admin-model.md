# Feature Spec: 日常安排草稿与管理员模型控制

> Status: implemented and released; device acceptance pending
> Owner: root
> Updated: 2026-10-12

## Decision / Problem

“规划今天饮食运动和睡眠”属于安排草稿，却被当作未完成的个人查询。普通用户也能看到供应商通道及模型切换。修复前者的全句意图边界，后者只对认证管理员开放。

## Requirement Admission

- classification: existing behavior repair and access restriction
- first_user_fit / core_loop_step: 减少安排下一步时的等待和误报
- first_class_objects: 草稿；不创建 HealthProgram、ExecutionEvent 或 WriteIntent
- target_surface: Mobile、Web、Backend
- source_of_truth: 完整当前输入和数据库 User.is_admin
- safety_level: 个人数据与健康建议边界；不授权读取或写入
- prescription_or_causal_verdict: no
- autonomy_tier: reply only
- evidence_provenance: 当前输入；明确个人资料未核验
- verification_window: 本轮离线真实stream、PostgreSQL权限查询、固定候选CI和部署
- success_metric: 截图原话无个人工具、单轮完成、无查询日期误报；成员无模型入口且不能持久化/执行旧偏好
- added_user_burden: none
- non_goals: 不为未知句式扩权、不改用药、不降健康建议模型质量、不运行真实模型评测

## Flow / Surface Contract

闭合的饮食/运动/睡眠安排句 → 当前输入建议scope → 只开放通用知识 → 有条件草稿、未读取个人记录、未保存。带他人、病史依据、查询、保存、取消或未知尾句均保留现有严格策略。

Mobile/Web从认证用户对象显示管理员入口；普通用户只显示“小巴”。模型列表保留公开模型名，隐藏供应商通道。Backend成员GET返回空options和null选择，PUT/selftest在任何变更或模型调用前403；运行时查询当前管理员身份，降权后旧偏好和extra_context不能继续指定模型。

## Data / Verification / Rollback

沿用既有API与User.is_admin，不迁移schema、不删除历史偏好。覆盖正反句式、真实Pi/panel保存回复、管理员/成员、降权和每个偏好consumer。权限join使用PostgreSQL复核。风险：新句式以外仍走原有scope，实际模型总延时不能用本地单轮测试证明；公开模型名不等于供应商通道名。回退应用修复不会丢失记录或偏好，但会恢复旧入口权限，应单独审查。
