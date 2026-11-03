# Feature Spec: 已存化验数值提前展示

> Status: implementation
> Updated: 2026-11-04
> Owner: Agent performance delivery
> Dossier: ../dossiers/2026-11-02-explicit-model-latency.md

## Decision and problem

用户查询化验时，在已授权读取成功后立即复用现有 metric_table 与回答依据展示数值，完整分析继续生成。普通 medical_exam 返回纯文本，不能安全从模型文字抽取数值；因此此前必须等待最终生成才能看到事实。最新脱敏线上样本完整耗时约172秒，但该样本未保存工具参数，不能断言其具体化验查询形状。

## Requirement admission

```yaml
RequirementAdmission:
  request: 继续优化回复和卡片速度
  classification: existing read presentation improvement
  first_user_fit: 已有健康记录的用户
  core_loop_step: observed -> understood
  first_class_objects: HealthTwin evidence
  target_surface: Agent conversation existing metric_table and answer_evidence
  source_of_truth: 本轮已授权 health_query 的同一次 owner-scoped 查询
  safety_level: medical read facts only; safety-gate required
  prescription_or_causal_verdict: none
  autonomy_tier: existing read authority only
  evidence_provenance: stored numeric records; original report not verified
  claim_hedging: 展示实际日期及来源局限，不判定正常或异常、不推断诊断
  verification_window: same turn, persisted reload
  success_metric: 有数值的读取结束后、下一次模型调用前发出事实；对比相同合成请求首卡时间
  added_user_burden: none
  burden_justification: existing surface only
  non_goals: 模型选择、临床推理预算、写入、所选报告及上传列表行为不变
  smallest_end_to_end_slice: canonical numeric projection -> existing stream -> persisted response
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## Flow and surface contract

当前请求 -> Pi / ToolGateway 权限校验 -> medical_exam 原读取 -> 同批数值白名单投影 -> 现有事实表与依据提前流出 -> 原模型与最终医疗门 -> 同一事实保存供历史回看。客户端复用现有卡片协议，不增加入口、权限或原生依赖。

## Data and safety contract

内部工具仍返回字符串。Agent 普通 medical_exam opt-in 接收 `medical-readout.v1` JSON，含原 `summary` 和受限 `readout`；直接 canonical reader 默认保留原文本。查询条件与结构化数据绑定；不新增查询、不扩大原有最少365天的低频化验窗口，表下注明实际窗口和展示子集。只有原查询已选出的有限数值及日期进入卡片，不从 OCR/报告叙述解析数值。未来、无日期、嵌套值、NaN、Infinity、错查询、错误或未知版本均不能生成事实。已选报告与上传列表保持既有路径，本批不支持其新投影。

模型只读取经过 envelope 校验后提取的原 summary，逐字保留临床文本且不额外占用数值投影的 Token；数值写库不降精度。展示复用 number_format 真源。卡片注明原始报告未核验，陈旧项注明较旧，缺数值不推断正常。无 schema migration、缓存、跨用户共享或新外部调用。

## Verification and release

RED/GREEN 覆盖 owner、日期、筛选绑定、非有限值、无数据、原叙述保留、早于下一次模型调用、最终与保存依据一致；既有选定报告隔离及历史纠正回归。同批真实模型合成请求比较首有用输出、完整耗时、模型次数、成本，所有失败保留；两样本不宣称生产P95/P99。数据库语义用 PostgreSQL验证。独立 G4、CI-mode 集成、精确main CI及既有 backend / OTA发布闸均保留。

停止条件：数据串用户、日期/来源失真、遗漏临床文本、最终回复退化、错误或成本长尾明显变坏时不发布，回到实现；不恢复旧配置、不备份。App实际绘制、生产长尾及设备接收须另有证据。
