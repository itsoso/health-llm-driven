# 推送详情与历史解读

Status: implementing · Owner: notification landing · Updated: 2026-10-18

## 决策与问题

睡眠质量下滑等推送缺少 deep link，历史列表把这些行禁用。增加按通知 ID 的只读详情页，展示已保存原文、时间及局限，并提供小巴解读入口。专属用药、行动、晨报和运动目的地优先保留。

## RequirementAdmission

```yaml
request: 睡眠质量下滑等推送需要有一个landing页面点进去可以分析，现在无法点击。
classification: existing-loop-repair
first_user_fit: 查看本人健康推送并理解其含义
core_loop_step: observe -> interpret -> review
first_class_objects: [HealthTwin, SafetyGuardian]
target_surface: Mobile
source_of_truth: authenticated NotificationLog
safety_level: health-data-read-and-advice
prescription_or_causal_verdict: false
autonomy_tier: manual_request_read_only
evidence_provenance: 已保存的历史推送文字，不是当前原始指标核验
claim_hedging: 历史观点不能充当当前诊断；不推断因果或给个人处方
verification_window: 本轮功能测试、候选 CI、发布后验收
success_metric: 无专属路由的历史和新推送可打开本人详情并发起有范围的解读
added_user_burden: 一次明确的解读请求
burden_justification: 打开通知不自动调用模型或写健康记录
non_goals: 自动完成行动、重新诊断、自动拉取今天数据填充历史缺失
smallest_end_to_end_slice: notification id -> owned detail -> selected notification explanation
stale_surface_to_remove_or_archive: 无链接禁用行
spec_required: yes
```

## 流程与跨端契约

- 服务端为无专属路由的记录提供 `/notification-history?detailId=<positive-id>`，兼容旧 App 已存在的历史页；新版登录后校验 ID、一次性 replace 到 `/notification-detail?id=<positive-id>`。非法或数组参数停留历史页，桥接期间不请求历史列表。新推送在实际发送前保留 pending 日志，携带仅含 ID 的链接，完成后更新同一行；静默延迟回放复用原日志。
- `GET /notification/logs/{id}` 按认证 user_id + id 查询；缺失和他人 ID 均为 404。返回 id、notification_type、title、content、created_at、sent_at、content_source；标题正文优先已保存 full_title/full_content。不返回完整内部 data/完成引用。
- Mobile 详情展示完整存留正文、日期和“历史推送，未重新核验原始数据”；旧日志可能只保留摘要，不捏造完整报告。错误可重试，加载/错误时不提供分析。
- “让小巴解读”返回主对话并预填问题；仅传 `{from: notification/<id>}`，用户发送后执行。服务端重新读取本人记录，丢弃客户端附加内容，范围只含这条通知及公开知识。历史推送不是已核验的个人事实；不补查其他日期/个人域，不授予写权限。紧急症状仍遵守共享健康安全链路。
- 该受限入口绑定页面的标准解读问题。用户改成新问题时丢弃旧通知选择及客户端附加内容，按新问题进入常规健康/急症流程；不让旧推送掩盖当前症状。
- Mobile query key 包含认证用户与通知 ID，账号切换不复用旧页面内容。

## 数据、安全与非目标

复用 NotificationLog，无 schema/迁移。pending 是既有状态，不代表已发送；异常不得变成功。保留现有 dedup、静默、许可、隐私出口。详情阅读不修改已读、依从或用药状态。URL 不放健康内容；新详情不扩大 APNs 原文载荷。现有专属跳转仍负责其显式确认。

解读复用主 Agent 及共享安全处理，不单建医疗模型调用。通知选择器限制所有模型工具为公开 knowledge_search；禁止健康写入和其他个人数据读取。客户端不能以伪造 ID、标题、日期、角色或 flags 扩权。未知历史原文、原始指标和时间必须明确未知。给模型的保存时间不代表采样时间；完整性未知的旧文本不能因本轮未截断而称为完整原文。解读不提供投递/已读状态，也不得推断是否送达。

## 验收与验证

历史无链接睡眠/趋势/提醒可点；专属链接优先；长文本完整阅读；缺失/跨用户/非法 ID 不泄漏；重复打开不写健康记录；账号切换不露旧缓存；预填不自动发送。新推送发送时 ID 已持久化可读，延迟仅一行，失败状态真实。Agent 流式回归覆盖本人历史记录、客户端污染、旧会话隔离、越界工具阻断、缺失记录和紧急症状。

执行后端 pytest（单元与 PostgreSQL）、Mobile Jest/tsc/lint、System Map、LLM change gate、独立安全审查、候选 CI-mode 与精确 SHA CI。模拟器操作如受锁屏阻挡如实保留未验证。发布遵循 no-backup，backend 先于相同 SHA OTA；当前 main 含未推送原生 GPS 候选，不能把 native 变化冒充 OTA。无授权凭据/候选 Gate 时保留具体发布断点。

### 2026-10-27 来源绑定补充

标准历史推送解读采用服务端来源选择契约。模型仅选择本人记录中的完整句子及匹配指标类型，数值、相对时间和否定词逐字保留；含义、局限和核实项由固定释义生成。保存时间不能推算采样日期，差值不能补成未提供的实测读数。解读范围明确为已保存的指标片段，其他结论未核验。来源不完整、选择不合契约或医疗边界失败不作为完整解读；来源失败/单一剂量问题可做一次有截止时间、无工具且只含同一来源的重解读，仍经过全部输出校验。
