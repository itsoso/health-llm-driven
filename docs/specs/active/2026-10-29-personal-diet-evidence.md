# 个人饮食建议的依据查询修复

> Status: local candidate; not deployed
> Updated: 2026-10-29
> Baseline: e6f26f6230e429a29113e4322ff5d7be22764787

## 决定与问题

修复明确要求使用本人基因、年龄、体重给饮食建议时，被当作他人资料请求拒绝的问题。原文中的系统位置描述没有被现有主体解析接受，随后权限终止策略直接结束对话。化验卡片本身不证明所需资料已查询或饮食分析已完成；未取得这次线上运行的完整日志，不能推断卡片来源。

## 需求准入

```yaml
RequirementAdmission:
  classification: engineering-maintenance
  first_user_fit: 基于已有个人资料获得有条件的饮食选择
  core_loop_step: 观察依据到建议
  first_class_objects: [HealthTwin, LeverageAction]
  target_surface: existing agent chat
  source_of_truth: authenticated account and owned records
  safety_level: sensitive read and health advice
  prescription_or_causal_verdict: none
  autonomy_tier: read-only
  evidence_provenance: actual tool results in this turn
  claim_hedging: missing records are unknown; genetic data is not diagnosis
  verification_window: current turn
  success_metric: requested reads plus substantive dietary answer, no foreign data
  added_user_burden: none
  non_goals: saving plans, medication changes, new UI, unrestricted personal reads
  smallest_end_to_end_slice: typed self basis → bounded reads → dietary synthesis
  spec_required: yes
```

## 用户流程与数据契约

完整消费“基于/结合/根据 + 本人 + 依据列表 + 饮食建议”请求；允许明确的 health/健康系统位置描述。只有明确列出的基因、年龄、体重可形成查询目标。季节是输出背景，不授权定位、天气、病史或额外资料。未知条件、他人主体、引用、否定、日期过滤和追加写入不从这个适配器获得权限。

复用既有建议依据流程：模型省略读取时，服务端经同一工具网关补齐未执行目标；模型参数不得指定用户、档案、额外维度或时间窗。基因沿用当前账号活动档案，体重沿用最多最近十条记录。年龄新增最小投影 `health_query(age)`，只在该任务明确要求年龄时开放，按账号时区的当前日期计算周岁，仅返回 `age_years`、`as_of`、`source`；不返回生日、姓名或联系方式，生日缺失/未来日期返回未知。

单模型与多模型共享查询完成检查、提示和回答目标。读取成功与回答完成分别判定；空数据不伪装有证据，失败不伪装完成。模型没有给饮食建议时，最多补一次无工具合成，仍缺失则保留未完成状态。补合成仍通过原有医学与输出检查。

## 边界与验证

建议须说明事实、未知条件和适用前提；不凭未知基因推断风险，不开方或调药，不持久化方案。个人数据读权限只来自完整请求及一致的认证主体，不能靠模型输出、上下文或重试扩权。

验证覆盖：原话及同义表述、混入其他主体、模型参数扩权、shadow 拒绝、只查列出的依据、流式和多模型真实 Pi 循环、跳过/失败查询、仅数据无建议、年龄最小投影、PostgreSQL 用户隔离、既有运动计划回归与 System Map 漂移。测试使用合成账号，模型响应受控；不等于生产模型实际回答已验证。

## 本地验证回执

- 原话权限测试先红；仅有查询结果的回答先被复现为错误完成；邀请/未来承诺回复亦先补红测试，再修复。
- 权限与语义基础回归：3424 passed（补充回答检查之前的候选）。
- 最终候选针对性回归：164 passed，覆盖本修复、运动建议及批查询；新增适配器/读取/共享层覆盖率合计 94%。
- 独立 PostgreSQL 合成测试：2 passed，核验年龄投影及基因用户/活动档案隔离。
- `ruff --select F821,F822,E9`、`git diff --check`、`./scripts/system-map-check.sh` 通过。
- safety-gate 独立 reviewer 在补齐“仅数据”“邀请”“未来承诺”完成语义之后给出 GO。
- 未 commit、push、merge 或 deploy；未做生产模型实际回复验证。上述 GO 不是发布验收。
