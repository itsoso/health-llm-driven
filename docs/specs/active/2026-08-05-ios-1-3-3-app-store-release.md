# Feature Spec: iOS 1.3.3 App Store Release Safety Boundary

> Status: approved
> Owner: product / mobile release
> Updated: 2026-08-05
> Related PRD: `docs/prd/2026-08-05-ios-1-3-3-app-store-release.md`
> Related code: `mobile/components/dashboard/RhinitisCard.tsx`, `mobile/app/(tabs)/record.tsx`, `mobile/app.json`

## 1. Decision

发布新的 iOS 1.3.3 Store Build，并在发布前移除记录页内置的具体处方药、固定剂量和自动建药行为；审核路径只演示健康记录、趋势解释、生活方式建议和用户确认后的写入。

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
apis: unchanged
events: existing medication execution events only
models: unchanged
fields: unchanged
enums: unchanged
backward_compatibility: existing user medication records remain readable and writable
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- 应用不得建议用户开始、停止、更换处方药或改变剂量。
- 快捷记录只能记录用户已有事实，不能把缺失药物自动补成产品默认值。
- 所有写入失败必须提示，不得空 `catch`。
- 审核账号只含虚构、可复位的数据；不得复制真实用户数据。
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
When production OTA 渠道被检查
Then 审核期间没有发布改变 1.3.3 首次启动行为的新更新
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

最终提交还必须运行带 App Store Connect 凭据、截图目录、精确 Build 和外部真机证据的 `--final-submit` 闸门。

## 13. Rollout And Rollback

- 发布路径：新 EAS production Store Build，不以 OTA 替代嵌入代码。
- 审核期间：冻结 production OTA 和审核账号。
- 审核拒绝：不公开发布；修复后提交新 Build。
- 批准后：手动发布；生产 smoke 失败则暂停公开动作，必要时通过远程配置关闭问题入口并准备新 Build。
- 上线验证完成后才解除 OTA 冻结。

## 14. Open Questions

无阻塞性未决问题。具体构建号由 EAS remote auto-increment 决定，但必须不低于 241。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-05 | Initial approved spec | 用户批准审核优先、功能冻结的 1.3.3 发布方案 |
