# 安静时段后的提醒汇总

Status: implementing
Updated: 2026-10-20
Related PRD: `docs/prd/reva-personal-health-os-prd.md`

## 决策与准入

截图故障修复：保留 09:00 晨间地板与用户安静时段，将同一批次内、同一用户/原计划日期/时区/延后投递时刻的例行用药提醒合为一次投递；家庭日报按事项与成员计数，不逐条重复隐去项目名后的相同句子。
classification: bugfix；first_class_objects: ExecutionEvent；target_surface: Mobile 锁屏/已有通知详情、Backend；source_of_truth: Backend；safety_level: medication/privacy-sensitive；prescription_or_causal_verdict: none；autonomy_tier: unchanged；spec_required: yes。
不改变原用药计划、服药记录、剂量或服药建议。延后的提醒不等于漏服，不引导直接补服；打开只查看详情。

## 流程与合同

- 仅合并可验证的服务器例行用药 slot；不同用户/日期/时区、紧急健康告警、其他提醒和无法验证的旧载荷保留原路径。当前准时提醒不延迟等待汇总。
- 原队列保留，整组通过一次条件更新认领；若仅认领部分则回滚，不投递。进程中断保留 pending，不自动重发。
- 一条通知详情保存全部原计划时段；各原日志保存汇总关联及同一次投递结果，不伪造独立发送。失败保留失败；再次落入安静时段时还原每条原载荷并统一顺延。
- 批次沿用有界队列，跨批次可产生多个汇总，不通过无界加载承诺全队列一条。发送仍经过用户开关、隐私、严重度、现有去重及渠道入口。
- 汇总使用已有 `/notification-history?detailId=`，由登录账户读取已保存详情；原始完整文本及汇总内部关联不进入渠道载荷，无移动端类型/schema/迁移变化。
- 家庭详细数据留在现有授权查询中，锁屏只给计数并指向 `/family`；不将全量家庭报告持久化到通知中绕过授权撤销。

## 验收与发布

先 RED 后 GREEN：单次投递保留所有时段、失败/重复 flush、跨账户/日期、安静时段顺延、紧急提醒不合并、旧载荷兼容、真实 PostgreSQL 并发认领、同名复查汇总及家庭撤权。
独立 safety-gate 审查固定提交；完整 CI/CI-mode、发布锁/回执及健康检查独立验证。未使用真实健康记录或真实模型；APNs 真机展示未验证。按持续授权推进适用发布，不备份、不重放不明操作。
