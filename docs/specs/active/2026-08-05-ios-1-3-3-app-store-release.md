# Feature Spec: iOS 1.3.3 App Store Release Safety Boundary

> Status: blocked (production/App Store writers frozen)
> Owner: product / mobile release
> Updated: 2026-08-12
> Related PRD: `docs/prd/2026-08-05-ios-1-3-3-app-store-release.md`
> Related code: `mobile/components/dashboard/RhinitisCard.tsx`, `mobile/app/(tabs)/record.tsx`, `mobile/components/chat/cards/AIGCMediaConfirmationCard.tsx`, `frontend/src/components/assistant/inlineCards/cards.tsx`, `backend/app/api/aigc_media.py`, `backend/app/services/aigc_media_job_service.py`, `mobile/app.json`

## 1. Decision

产品与医疗安全范围保持批准，但发布执行当前 **BLOCK**。在新的可信 production launcher
通过独立 G4 前，不创建/上传 Store Build，不选择 TestFlight build，不修改 ASC，不重置
审核账号，也不提交 App Review。不得自动 archive/export/signing/provisioning、调用
`mobile-local-device.sh` 或使用 `-allowProvisioningUpdates`。existing-IPA 唯一例外是
`mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 只读现成 IPA 并生成离线检视
metadata/report；不得生成 install manifest、安装二维码或可安装承诺。
本地 Mobile 验证只走 Metro/tests 或 `npm run ios` 的 Simulator wrapper；调用方不得向
npm/Expo 追加 `--device`，wrapper 必须从 available inventory 锁定 exact Simulator UDID。
物理 iOS repo CLI 与仓库内真机验收冻结。

冻结根因是 same-UID writable repo bootstrap trust 无法闭合：Git replace、shared info
attributes+filter、隐藏 untracked import shadow、`BASH_ENV` 与
`PYTHONPATH`/`sitecustomize` 均可在 repo 内 guard 前改变执行语义。

## 2. Problem

记录页当前对所有用户展示莫米松和异丙托溴铵，并在用户点击时以硬编码剂量自动创建处方药和服药记录。用户未先录入该药物，也没有确认该剂量来自其医生或处方。失败还被空 `catch` 静默吞掉。

如果不处理：

- 用户可能把快捷按钮理解为产品建议的药物和剂量；
- 健康写入可能在用户不知情时失败；
- App Review 可能将产品判断为提供处方或治疗决策；
- 送审说明中的“不会开药或改剂量”与真实行为冲突。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 本周发布 iOS 1.3.3 正式版本并通过 App Store 审核
  classification: product_change | medical_safety | release
  first_user_fit: 需要可靠记录既有健康事实、但不希望应用替代医生决策的移动端用户
  core_loop_step: Data In -> Health Twin -> Daily Plan -> Execution -> Review/Learn
  first_class_objects: [WriteIntent, ExecutionEvent, SafetyGuardian, HealthTwin]
  target_surface: Mobile iPhone + App Store listing + Backend review environment
  source_of_truth: Backend for health/account facts; App Store Connect for submission metadata
  safety_level: medical_boundary | privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: user-entered medication facts and deterministic release evidence only
  claim_hedging: absolute_disallowed
  verification_window: exact Store Build before submission and production after approval
  success_metric: final gate passes, build enters review, no unresolved medical/privacy blocker
  added_user_burden: one navigation step when recording an existing medication from the rhinitis area
  burden_justification: prevents app-authored prescription and dose creation
  non_goals: new features, payment, diagnosis, treatment, dose changes, broad refactor
  smallest_end_to_end_slice: remove hard-coded drugs -> surface failures -> exact-build acceptance -> submit
  stale_surface_to_remove_or_archive: hard-coded rhinitis drug chips and stale Build 237 release copy
  spec_required: yes
```

## 4. Non-Goals

- 不改变后端用药数据模型或 API。
- 不移除用户主动维护用药清单和记录既有服药事实的能力。
- 不新增 AI 医疗能力、处方识别能力或剂量建议。
- 不将高级实验入口提升到 production。
- 不把 App Store 截图或审核账号作为真实用户数据来源。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | 鼻炎卡不再构造应用自带的处方药写入意图 |
| `ExecutionEvent` | 用药事件只能来自用户已维护的药物与明确确认路径 |
| `SafetyGuardian` | 处方与剂量决定继续降级到医生；审核增加对抗提示验证 |
| `HealthTwin` | 只接收真实用户确认的健康记录，不接收产品硬编码药物 |

## 6. User Flow

```text
用户打开“记录”页
  -> 鼻炎卡只记录洗鼻/喷嚏等用户事实
  -> 用户需要记录用药时进入“用药管理”
  -> 选择自己已录入的药物并确认
  -> 后端写入 ExecutionEvent
  -> UI 明确显示成功或失败
```

审核流程：

```text
审核员使用专用账号密码登录
  -> 不授权可选权限也能使用文字对话和演示数据
  -> 可查看隐私政策与账号删除入口
  -> 医疗问题只得到解释、记录或就医建议
  -> 不出现产品自带处方、治疗方案或剂量修改
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 展示和确认用户健康事实 | 不创建产品自带处方；权限拒绝后保留文字路径 |
| Backend | 健康记录、账号和删除请求事实源 | 强制用户隔离；失败明确返回；审核环境保持在线 |
| App Store Connect | 审核与产品页事实源 | 元数据、隐私、年龄分级和精确 Build 一致 |

## 8. Data Contract

```yaml
apis: AIGC confirmation owner GET returns an exact outbound_prompt plus short-lived review_token; confirm POST requires that token
events: existing medication execution events only
models: unchanged
fields: [outbound_prompt, review_token, review_expires_at]
enums: unchanged
backward_compatibility: existing user medication records remain readable and writable; old AIGC clients fail closed until updated
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- 应用不得建议用户开始、停止、更换处方药或改变剂量。
- 快捷记录只能记录用户已有事实，不能把缺失药物自动补成产品默认值。
- 所有写入失败必须提示，不得空 `catch`。
- 审核账号只含虚构、可复位的数据；不得复制真实用户数据。
- 审核账号 live gate 只向 HTTPS 地址发送凭证，禁止跟随任何重定向；验证内容必须包含仓库 fixture 的精确合成会话，不得仅以“非空”代替。
- AIGC provider 外发前必须由 owner-scoped no-store GET 展示将实际发送的完整提示词；确认 POST 只接受短时、owner/confirmation/provider/model/prompt-version 绑定的 runtime token，任何缺失、篡改、过期或版本变化必须在调用 provider 前失败。
- HealthKit 数据不得用于广告、营销画像、出售或无关数据挖掘。
- 用户可在应用内发起完整账号删除请求并查看处理状态。
- App Store 截图不得泄露姓名、电话、药名、报告或设备标识。

## 10. AI Behavior

AI 可以解释用户记录、整理就医问题、生成需用户确认的记录草稿和提供生活方式建议。

AI 不得：

- 给出确定诊断；
- 开处方或选择具体药物；
- 指示停药、加量、减量或替换剂量；
- 把不确定关联写成因果；
- 在红旗症状下只给居家观察而不提示及时就医或急救。

## 11. Acceptance Criteria

```gherkin
Given 用户从未录入莫米松或异丙托溴铵
When 用户打开记录页
Then 页面不显示这两种具体药名或固定剂量，也不会调用创建药物 API

Given 用户点击洗鼻或喷嚏记录
When 后端写入失败
Then 应用显示可重试错误，而不是静默保持旧状态

Given 审核员拒绝通知、位置、麦克风、相册、相机和 HealthKit 权限
When 审核员进入 Agent
Then 仍可用文字完成对话和手工记录

Given 审核员询问诊断、开药、停药或剂量调整
When Agent 回复
Then 回复不产生处方决定，并在需要时引导医生或急救服务

Given App Store 审核开始
When 任一 OTA channel 被检查
Then 所有 OTA/rollback writer 均保持 exit 78，不依赖可漂移或共用的 channel→branch 映射

Given 发布机运行审核账号 live gate
When API 基址为 HTTP、包含 URL 凭证/查询/片段或服务返回重定向
Then 在泄露密码或 Bearer token 前 fail closed

Given 审核账号成功登录
When live gate 验证审核可见数据
Then 当前用户的固定简报会话包含仓库 fixture 的精确连续消息对

Given 用户准备把图片或提示词发送给外部 AIGC provider
When Mobile 或 Web 尚未成功加载完整外发描述和 owner-bound review token
Then 确认按钮保持禁用，通用卡片 action 也不能直接发起 confirm POST

Given 完整外发描述已显示且用户点击确认
When confirm POST 到达服务端
Then token 必须与当前 owner、confirmation、provider、model 和 prompt 版本匹配，实际 provider prompt 与用户所见内容逐字节一致
```

## 12. Verification Plan

```bash
cd mobile
pnpm test --runInBand
pnpm exec tsc --noEmit
pnpm lint

cd ..
python3 scripts/check_app_store_release_pack.py
python3 scripts/check_ios_app_store_submission.py
python3 backend/scripts/check_dossier_consistency.py
git diff --check
```

冻结期 `--final-submit` 会登录 production reviewer 并取得可写 bearer token，必须在登录/
凭证读取前冻结，不能作为只读 gap report。解冻后，
未来获权提交还必须绑定 App Store Connect 凭据、截图目录、精确 Build 和仓库外人工生成
的同包真机证据；仓库内 Simulator harness 不满足该 Gate。

## 13. Rollout And Rollback

- 发布路径：当前不查询、选择、分发或提交 existing candidate；只允许用 already-downloaded
  IPA/已导出本地 metadata 做 exact source/native identity 对账。所有 native/EAS/ASC/App
  Review writer/observation 均 BLOCK。
- 审核期间：冻结所有 OTA/rollback channel 和审核账号；preview/development 也无例外。
- 审核拒绝：不公开发布；修复后提交新 Build。
- 当前不存在“手动发布”兜底；raw CLI/ASC/SSH/helper 都不能绕过冻结。
- 解冻必须另立 dossier，落地 repo-external root-owned launcher、fixed interpreter、
  `env -i` allowlist、canonical archive/tree 仓库外 materialization，并通过新的独立 G4。
- 此前 G5/G6/App Store submission 均 BLOCK，不得写 shipped/complete。

## 14. Open Questions

可信 bootstrap launcher 是首要阻断项。existing candidate（若有）只可从已有本地材料
对账，且不能
解除 Build/TestFlight/App Review Gate；不能假设 remote auto-increment 或人工 ASC 操作
会创建/选择新候选。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-05 | Initial approved spec | 用户批准审核优先、功能冻结的 1.3.3 发布方案 |
| 2026-08-06 | Added exact AIGC external-provider review boundary | 外发前必须展示实际完整 prompt 并取得 owner/provider/model/version 绑定短时 token；客户端与 capability gateway 均 fail closed，最终独立 G4 GO。 |
| 2026-08-12 | Historical partial freeze (superseded below) | 当时仅冻结自动 writer 并曾允许选择已对账 existing candidate；后续同日发现 bootstrap 绕过面后，该授权已撤销。 |
| 2026-08-12 | Blocked all production and App Store writers/observation | same-UID repo bootstrap 可被 Git/env/import shadow 绕过；existing candidate 仅能从已有本地材料对账，不得联网查询/选择/提交。 |
