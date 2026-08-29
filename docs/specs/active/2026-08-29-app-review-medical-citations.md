# Feature Spec: App Review 医学信息可点击引用

> Status: implemented; awaiting exact release candidate
> Owner: product / backend / mobile release
> Updated: 2026-08-29
> Related PRD/PDD: `docs/prd/2026-08-05-ios-1-3-3-app-store-release.md`
> Related code: `backend/app/services/medical_citation_policy.py`, `backend/app/services/agent_executor.py`, `mobile/components/chat/MedicalCitations.tsx`

## 1. Decision

为小巴对话中的医学计算、范围、风险和健康建议增加由服务端确定的权威来源，并在 Mobile 回答正文下方始终展示可点击的 HTTPS 引用和就医边界。

## 2. Problem

- 影响对象：使用 AI 对话查看 BMI 等健康信息的用户，以及 App Review 审核员。
- 出现场景：Mobile 小巴对话。Apple 在 Build 256 中输入“帮我算我的BMI”，看到公式、数值和正常范围，但没有可发现的来源链接。
- 既有不足：“依据与过程”只说明使用了哪些用户数据；健康证据卡中的来源并非所有回答都有，且部分来源不是可点击链接。
- 不处理的后果：用户无法核对医学信息，App 持续违反 Guideline 1.4.1。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复 App Review 1.4.1，医学信息必须有易发现、可点击的权威来源
  classification: safety_repair
  first_user_fit: 已在小巴中询问健康计算或医学建议的用户
  core_loop_step: Health Twin -> Review/Learn
  first_class_objects: SafetyGuardian, ExecutionEvent
  target_surface: Backend + Mobile chat
  source_of_truth: 服务端医学引用策略；外部权威机构 HTTPS 页面
  safety_level: medical_boundary
  prescription_or_causal_verdict: no
  autonomy_tier: read_only
  evidence_provenance: NHC/CDC/WHO/USDA/NIH/NLM/专业学会及既有受控健康证据
  claim_hedging: 必须声明筛查/健康管理边界和咨询医生
  verification_window: 同一提交候选 Build 的实时回答、历史恢复和外链打开
  success_metric: BMI 审核路径 100% 展示至少一个可点击权威来源，且无不安全 URL
  added_user_burden: 0
  burden_justification: 来源默认展开，无需用户额外操作才能发现
  non_goals: 诊断、治疗、处方、剂量调整、由模型自由生成 URL
  smallest_end_to_end_slice: BMI 提问 -> 服务端引用契约 -> SSE/落库 -> Mobile 可点击来源 -> 真机打开官方页面
  stale_surface_to_remove_or_archive: 无
  spec_required: yes
```

## 4. Non-Goals

- 不宣称任何医学计算等于诊断。
- 不允许模型自行编造来源、URL 或机构名称。
- 不新增健康数据写入、处方、治疗或药物剂量行为。
- 不用 OTA 替代包含本修复的新 App Store 二进制。
- 本次只修改 Mobile 展示；Mac/Web 后续按同一服务端契约接入，不阻塞本次 iOS 拒审修复。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `SafetyGuardian` | 增加医学信息引用与安全边界的终态出口护栏 |
| `ExecutionEvent` | `done` 事件附加 `medical_citations` 与主题 |

## 6. User Flow

```text
用户输入“帮我算我的BMI”
  -> 服务端按受控主题目录给模型注入可用证据范围
  -> 服务端在 complete 终态重新分类最终回答并生成引用
  -> 同一引用写入 assistant message.meta 并通过 SSE 返回
  -> Mobile 正文下方展示“参考来源”
  -> 用户点击官方 HTTPS 链接核对
  -> 真机验收记录可见性与外链打开结果
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 解析、恢复、展示并打开来源 | 只接受完整 HTTPS 来源；完成态正文下方默认可见 |
| Backend | 主题识别、来源选择、提示约束、终态补全和持久化 | 模型不决定 URL；失败回答不声称已有引用；用户隔离查询 assistant 消息 |

## 8. Data Contract

```yaml
apis: POST /agent/stream 的 done data 增加向后兼容字段
events:
  done.medical_citation_required: boolean
  done.medical_citation_topics: string[]
  done.medical_citations: MedicalCitation[]
models:
  AgentMessage.meta: 持久化同名字段
fields:
  MedicalCitation: source_id, title, organization, url, topic, claim_scope
enums: none
backward_compatibility: 新字段均为可选；旧客户端忽略，旧历史无字段时不展示
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- 涉及医学信息展示，但不改变用户健康数据、药物或补剂的写入权限。
- URL 必须是无凭据、非 localhost 的 HTTPS；客户端再次执行同样的 fail-closed 过滤。
- BMI 明确为筛查指标；所有引用面板提示健康信息不替代诊断，医疗决定前咨询医生。
- 服务端查询持久化消息时同时校验 `AgentConversation.user_id`，避免跨用户元数据修改。
- 日志只记录用户 ID、消息 ID 和异常类型，不记录健康原文或 URL 参数。

## 10. AI Behavior

- 模型只能在服务端提供的来源和 claim scope 内表述公式、范围与建议。
- 模型不得创建或格式化最终引用；最终引用由服务端确定性生成。
- 终态会根据最终正文再次分类，覆盖确定性回答和模型绕过场景。
- 无法匹配专门主题但确属健康建议时，降级到 MedlinePlus 健康主题索引；不降级成无引用医学回答。

## 11. Acceptance Criteria

```gherkin
Given 用户输入“帮我算我的BMI”
When 服务端完成回答
Then done 事件和落库 meta 均包含 NHC 与 CDC 的 HTTPS 引用

Given Mobile 收到或恢复含 medical_citations 的完成态回答
When 消息渲染
Then “参考来源”无需展开即可看到，点击可打开对应官方链接

Given 来源使用 HTTP、缺标题或缺机构
When Mobile 解析
Then 该来源不会进入可点击列表

Given 回合 completion_status 为 error 或 interrupted
When 服务端发送终态
Then 不声称该回合已提供医学引用
```

## 12. Verification Plan

```bash
# Backend
backend/venv/bin/python -m pytest \
  backend/tests/test_medical_citation_policy.py \
  backend/tests/test_agent_executor_medical_citations.py -q

# Mobile
cd mobile
npm test -- --runInBand \
  services/__tests__/medicalCitations.test.ts \
  services/__tests__/chatStream.test.ts \
  hooks/__tests__/useChatEngineHistory.test.ts \
  components/chat/__tests__/MedicalCitations.test.tsx \
  components/chat/__tests__/ChatBubbleToolsUsed.test.tsx
npx tsc --noEmit

# Release and repo hygiene
python3 scripts/check_app_store_release_pack.py
./scripts/system-map-check.sh
git diff --check
```

真机：在精确候选 Build 输入“帮我算我的BMI”，确认来源默认可见，并分别打开 NHC/CDC 官方页面。

## 13. Rollout And Rollback

- Backend 随主干部署；Mobile 必须生成 Build 257 或更高的新 production 二进制。
- 审核期间继续冻结 production OTA，确保审核包与验证包一致。
- 回滚 Mobile 可移除可选字段消费；Backend 字段保持向后兼容。若来源目录存在错误，停止重新提交并回滚服务端策略提交。

## 14. Open Questions

- 阻塞项：精确候选 Build、真机引用外链证据和 App Store Connect 人工重新提交尚未完成。
- 非阻塞项：Mac/Web 是否在后续版本复用同一引用面板。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-29 | Initial implementation spec | 修复 App Review Guideline 1.4.1 拒审 |
