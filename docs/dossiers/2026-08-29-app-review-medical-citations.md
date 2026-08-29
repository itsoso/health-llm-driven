# Dossier: App Review 医学信息可点击引用

| 字段 | 值 |
|---|---|
| slug | `app-review-medical-citations` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | S6 候选构建准备 |
| 状态 | ready_for_release_candidate |
| 负责 | product / backend / mobile release |
| 关联提交 | Apple Submission `85f3224c-3688-4aae-9da1-c7e91f4facaa`，Version 1.3.3 (256) |

## S0 · 用户需求

> 确保我能一次性审核通过

不能保证 Apple 的最终裁决；可交付目标是消除已知 1.4.1 拒审原因，并让代码、审核说明、精确二进制和真机证据形成同一条可复核链。

## S1 · 已确认事实

- App Store Connect 当前状态：1.3.3 (256) 已拒绝，问题未解决。
- Guideline：1.4.1 Safety: Physical Harm。
- Apple 明确指出 AI chat 的医学计算与参考没有来源链接。
- 审核复现：输入“帮我算我的BMI”，回答展示公式、22.9 和正常范围，但无引用。
- Build 256 源提交：`75f61f694c4711a7b349eb63fb7af5e48d9f9012`。

## G1 · 准入

- 分类：已上线健康信息 surface 的安全合规修复。
- first_class_objects：`SafetyGuardian`, `ExecutionEvent`。
- source_of_truth：服务端受控来源目录 + 已准入健康证据 URL。
- 自治等级：只读；不产生诊断、处方、治疗或健康数据写入。
- **裁决：PASS**。

## G2 · 可行性与安全压测

- 后端终态 choke point 覆盖普通、确定性和多模型回答。
- 模型只接收服务端给出的来源范围，不能生成最终 URL。
- Backend/Mobile 双层只接受安全 HTTPS。
- 完成态引用写入 message meta，历史恢复与实时 SSE 保持一致。
- Build 256 不可复用；必须新建 production Store binary。
- **裁决：PASS**。

## S5 · 实现

- [x] 医学主题到权威来源的确定性策略。
- [x] BMI 使用国家卫生健康委员会和 CDC 来源。
- [x] 服务端预生成提示约束与 complete 终态补全。
- [x] assistant meta 持久化，查询带用户所有权过滤。
- [x] Mobile SSE/历史解析、安全 URL 过滤和默认展开引用面板。
- [x] 审核说明加入 Apple 原始 BMI 复现路径。
- [x] 真机模板加入引用可见与官方链接打开检查。
- [x] 系统地图再生成与漂移验证。
- [x] 全量相关回归、lint、release pack 和安全 Gate。
- [ ] commit / push / backend deploy / EAS production build。
- [ ] 精确候选 Build 真机证据。
- [ ] 用户确认后回复 Apple 并重新提交。

## G3 · 测试

- Backend Agent/健康证据/系统知识/完成态/引用/发布包相关回归：293 passed。
- Mobile 引用策略、SSE、历史恢复、组件与 ChatBubble：48 passed。
- TypeScript `tsc --noEmit`：PASS；Expo lint `--quiet`：PASS。
- System Map 生成与漂移：PASS；App Store release pack：PASS；iOS submission preflight：PASS。
- Python 编译与 `git diff --check`：PASS。
- **裁决：PASS**。

## G4 · 安全评审

- 来源准确性：BMI 的 NHC/CDC 来源与 claim scope 对齐；目录内 11 个官方 HTTPS URL 于 2026-08-29 实测 HTTP 200。
- URL 安全：Backend 拒绝 HTTP、带凭据 URL、localhost、`.local` 和非公网 IP；Mobile 再拒绝同类 URL 及 IPv6 literal。
- 用户隔离：持久化查询同时限定 assistant message 与 `AgentConversation.user_id`，跨用户回归通过。
- 失败语义：仅 `completion_status=complete` 附引用；error/interrupted 不声称已经提供来源；外链打不开时明确提示用户重试。
- 医疗边界：只增加只读证据展示，不新增诊断、处方、剂量调整或健康数据写入；模型不能决定最终 URL。
- **裁决：PASS（本变更为只读证据展示；未扩大既有医疗自治或写入权限）**。

## G5 · 部署健康

- pending。需要 Backend 健康证据和 Build 257+ 的 EAS/ASC/IPA 对齐。

## G6 · 上线验证

- pending。精确 Build 必须真机输入“帮我算我的BMI”，看到默认展开来源并能打开 NHC/CDC 官方链接。

## Rollback

- 任一来源、隐私、真机或安全 Gate 失败：停止重新提交并回到 S5。
- 审核期间禁止 production OTA；不得用 OTA 改变待审包行为。
