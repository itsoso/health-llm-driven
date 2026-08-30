# 1.4 Knowledge-to-Action：第三方知识到健康行动设计

状态：已完成定义环审批，待进入实现规划

日期：2026-08-16

## 1. 决策摘要

下一版将 KBase 定位为第三方知识供应链，而不是 Health 运行时的原文 RAG。

第三方内容先在 KBase 隔离采集、做权利判断、生成带来源的候选 Claim，再以不可变 Knowledge Release 交付给 Health。Health 导入后固定进入 `draft/held`，经过逐 Claim 的健康域审核和独立发布后，才允许进入 reviewed System KB 和运行时检索。

用户端采用“行动优先”：小巴在相关对话或今日计划中展示已审核的短 Claim、来源和适用边界，用户明确确认后才能加入议程或习惯候选。

## 2. 背景与问题

用户希望把得到、微信公众号等第三方知识通过 KBase 与小巴结合。当前系统已有 KBase Release 消费、System KB V2、逐 Claim 审核和 reviewed-only serving 能力，但第三方采集面仍可能带来以下风险：

- 公开可见、认证或原创并不等于获得复制、传播、embedding 或模型训练授权。
- 文章可能更新、删除、撤回，或授权范围到期；静默保留旧 Claim 会造成版权和医学风险。
- 公众号正文、课程正文和用户健康资料不应混入同一个运行时检索面。
- 第三方文章的医学主张不能自动成为诊断、处方、剂量或急症判断依据。
- 现有旧版整包导出与新 Release/Agent Package 契约并存，容易造成来源、版本和审核规则漂移。

## 3. 产品目标

### 3.1 目标

1. 在版权、隐私和医学安全边界内，将第三方知识转化为可追溯的健康 Claim。
2. 让小巴能解释“依据什么、为什么适合我、有什么限制”。
3. 让用户明确选择是否把建议加入今日行动，而不是自动执行。
4. 让来源修订、撤回和授权失效能够停止后续服务。
5. 保留 KBase 与 Health 各自的职责边界：KBase 管来源和发布，Health 管健康审核和服务。

### 3.2 非目标

- 不将任意公众号或得到内容批量全文导入生产 RAG。
- 不绕过登录、付费、订阅、反爬或其他访问控制。
- 不让模型自动批准或发布医学 Claim。
- 不让第三方内容直接生成诊断、处方、药物剂量、急症排除或安全规则。
- 不把 KBase、Obsidian 或第三方原文库暴露为小巴的在线工具。
- 不向 KBase 回传用户问题、回答、自由文本反馈或个人健康数据。
- 不在本版本重写旧版 legacy export；旧链路仅保留兼容和迁移用途。

## 4. 来源策略

每篇第三方内容先按权利状态分流：

| 权利状态 | KBase 可保存 | 可进入 Health | 运行时行为 |
| --- | --- | --- | --- |
| 自有或有书面授权 | 按授权范围保存隔离原文和版本 | 可生成候选 Claim | 仅审核通过的 Claim |
| 明确允许相应用途 | 元数据、必要短引文、转化 Claim | 需逐条审核 | 展示短 Claim 和链接 |
| 权利不明、禁止转载、付费或订阅 | 标题、作者、URL、时间、哈希、主题 | 不保存正文、不做 embedding | 仅作为发现链接，不进入知识检索 |

“公开可访问”“认证账号”“原创声明”都不能单独作为再利用授权。采集器不得使用管理员 Cookie/Token 批量抓取任意账号并直接写入生产知识库；不得绕过访问控制。Cookie、Token 和授权证明不能明文进入日志、Health 数据库或用户面。

## 5. 端到端流程

```text
第三方来源
  -> KBase 隔离采集与权利判断
  -> 候选 Claim 与引用
  -> 不可变 Agent Package v2 / Evidence Release
  -> Health 私有拉取与完整性校验
  -> 草稿工作区（held, serving_allowed=false）
  -> 逐 Claim 健康审核
  -> Reviewed System KB V2
  -> 小巴引用卡片
  -> 用户确认后加入今日议程
```

KBase 的 `published` 只代表上游来源、质量和发布门通过，不代表 Health 可以服务。Health 的 review manifest 和 serving allowlist 是最终服务裁决。

## 6. 数据契约

### 6.1 SourceSnapshot

表示一次来源内容的可验证快照：

- 平台、账号主体、文章或内容 ID、规范 URL。
- 作者、发布时间、来源更新时间、抓取时间和最后检查时间。
- 内容哈希、版本关系和 supersedes/withdraws 关系。
- 权利依据、证明引用、授权范围、期限和撤回联系人。
- `allow_summary`、`allow_quote`、`allow_embedding`、`allow_training` 等用途布尔值；未明确项一律为 `false`。
- 生命周期：`discovered`、`rights_cleared`、`withdrawn`、`expired`。

权利不明的 SourceSnapshot 只能进入 metadata-only 路径。

### 6.2 CandidateClaim

表示从来源中转化出的原子主张：

- Claim 文本、主题、适用人群、适用场景和排除条件。
- 风险等级、时效、新鲜度和复核日期。
- 来源 `source_id`、内容哈希、引用位置和外部佐证。
- 允许的结论范围和禁止推导范围。
- `evidence_only=true`，不携带可替代付费或受限原文的长篇正文。

高风险健康主张必须有指南、监管资料、原始研究或其他独立高质量依据。第三方账号不能作为高风险主张的唯一证据。

### 6.3 KnowledgeRelease / Agent Package v2

Release 是不可变发布单元，至少包含：

- `release_id`、`content_hash`、发布者、发布时间和生命周期。
- Claim 清单、citation 清单、引用范围和来源版本。
- `evidence_policy`：主来源、辅助来源、独立来源数、风险边界、允许结论和 Claim 数量上限。
- 评测结果、完整性证明和撤回/tombstone 信息。

Health 消费端必须从 KBase 的受控接口拉取 release 列表和 evidence detail，并校验列表/detail 的 `release_id`、哈希、Claim 唯一性、引用可解析性、`published`、`evidence_only` 和策略快照。校验失败必须 fail closed。

### 6.4 HealthAdjudication

Health 导入后建立审阅记录：

- 工作区 fingerprint、release lineage 和 policy snapshot。
- 每个 Claim 的 `approve`、`needs_evidence`、`background_only` 或 `reject`。
- 审核人、审核时间、适用边界、风险说明和复核日期。
- 独立发布状态与 serving allowlist。

导入、审核、finalize、publish 必须分离；同步动作不得自动改变 serving 状态。

### 6.5 ActionBinding 与反馈

用户采用行动后只绑定：

- `claim_id`、`release_id`、行动类型、时间和规则版本。
- 必要的本地适用性结果，不写回 KBase。

反馈只允许使用不含用户内容的枚举，例如 `helpful`、`not_applicable`、`source_outdated`、`fact_incorrect`、`evidence_conflict`，并携带匿名事件 ID、`claim_id` 和 `release_id`。个人“不适合我”不能直接使全局 Claim 失效。

## 7. 生命周期与撤回

```text
discovered
  -> rights_cleared
  -> candidate
  -> medical_review
  -> reviewed
  -> serving_allowed
  -> stale / withdrawn / rejected
```

来源修订、删除、撤回或授权失效时：

1. KBase 发布新的版本或 tombstone。
2. Health 停止接受旧版本的新导入和新服务。
3. 相关 Claim、embedding、索引和依赖引用退出运行时 allowlist。
4. 已完成的用户记录保留审计链，但标记“依据已更新/失效”。
5. 网络短暂失败不能直接判定来源撤回；权利人正式撤回必须立即处理。

## 8. 用户端体验

第一版不增加独立资讯首页。小巴只在相关对话或今日计划中展示已审核内容：

- 核心 Claim 的短转述。
- “为什么可能适合你”。
- 来源平台、作者、发布日期、复核状态和原文链接。
- 适用条件、限制和“仅供健康管理参考”提示。

用户动作只有：

- 加入今日议程。
- 保存为习惯候选。
- 暂不采用/不适合我。

高风险内容只能提供教育性说明和就医提示，不出现自动处方或诊断动作。来源撤回后，不再生成新建议，并在已保存的行动上显示依据变更。

## 9. 1.4 试点范围

### 9.1 正式试点

- 1 个已取得书面授权的第三方来源。
- 睡眠、一般运动或膳食习惯等低风险主题。
- 约 10–20 条 Claim。
- 先完成一条 Agent Package v2 到 Health 草稿桥接链路。
- 人工审核至少 1 条 Claim，并验证引用卡片和加入今日议程。
- 完成一次内容修订和一次授权撤回演练。

### 9.2 延后范围

- 多来源冲突合并。
- 权利不明来源的正文保存。
- 付费得到内容导入。
- 自动医学审核、自动排程和自动发布。
- 用户自由文本反馈回传 KBase。
- Agent Package 中模型、提示词、工具和 UI 策略接管 Health runtime。

## 10. 验收标准

### 功能

- Release 列表与 detail 的 ID、哈希、引用和策略校验可重放、可幂等。
- 导入结果固定为 `held/draft`，同步不会产生 serving 变化。
- 审核通过的 Claim 可被受控 Health Evidence Runtime 检索。
- held、rejected、background_only、generic 或 withdrawn Claim 不可被运行时引用。
- 用户能看到来源、适用条件、复核时间，并能将建议加入今日议程。

### 安全与版权

- Health serving 面不存在第三方 raw/full body、付费正文、Cookie、Token、Prompt 或个人健康资料。
- 权利不明内容不会生成 embedding、训练样本或可替代原文的摘要。
- 撤回演练后，旧 Claim 从检索和引用链中退出。
- KBase 收不到用户问题、回答、健康记录或自由文本反馈。

### 质量

- 每条上线 Claim 都能追溯到 source、release、hash、citation 和审核回执。
- 高风险 Claim 无独立依据时不能进入 serving allowlist。
- 采集、导入、审核、撤回和反馈都有幂等 receipt 与审计记录。

## 11. 发布闸门

- G1 准入：来源授权、主题风险、试点范围和数据保留期限明确。
- G2 风险：版权、访问控制绕过、提示注入、撤回和误用场景完成压测。
- G3 测试：schema、hash、引用解析、权限、撤回、幂等和 serving allowlist 测试通过。
- G4 评审：产品、工程、安全和健康域审核完成；模型不能代替人工健康裁决。
- G5 部署：先部署桥接和审阅面，默认 `serving_allowed=false`，验证健康和 receipt。
- G6 上线：用授权来源的低风险 Claim 完成从导入、审核、引用、行动到撤回的完整演练。

任何 Gate 失败都回到上游，不带红进入下一阶段。

## 12. 参考与边界

- [得到/KBase 供应链设计](../architecture/dedao-kbase-reva-sync.md)
- [KBase Release 消费计划](2026-07-12-kbase-knowledge-release-consumer.md)
- [KBase Claim 审核设计](2026-07-13-kbase-claim-adjudication-design.md)
- [KBase 反馈 Outbox 设计](2026-07-13-kbase-feedback-outbox-design.md)
- [KBase Verification Packet 设计](2026-07-13-kbase-verification-packets-design.md)
- [《中华人民共和国著作权法》](https://www.npc.gov.cn/c2/c30834/202011/t20201119_308796.html)
- [信息网络传播权保护条例](https://xzfg.moj.gov.cn/front/law/detail?LawID=167&Query=%E4%BF%A1%E6%81%AF%E5%8F%8A)
- [腾讯知识产权保护平台：原创声明](https://ipr.tencent.com/policy/content/3)
- [国家网信办公众账号信息服务管理规定](https://www.cac.gov.cn/2021-01/22/c_1612887880656609.htm)

上述内容是产品和工程设计，不构成针对具体来源或合同的法律意见。正式采集前仍需由权利人授权和法务确认具体用途、地域、期限与撤回机制。
