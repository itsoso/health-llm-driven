# Dossier: App Store iPhone First Release

| 字段 | 值 |
|---|---|
| slug | `app-store-iphone-first-release` |
| 创建日期 | 2026-07-14 |
| 当前阶段 | S6 测试与部署 |
| 状态 | testflight_pending_physical_acceptance |
| 负责 | Codex |
| 目标版本 | iPhone App Store RC |

## S0 · 用户需求

> 思考我要提交到appstore ，产品上还有哪些需要改进，做出规划
>
> 按照你的规划执行

- 使用者:第一次从 App Store 安装小巴的 iPhone 用户。
- 核心问题:当前包同时暴露未完成的平台能力、启动即索取权限、隐私材料与实际二进制不完全一致，不能把历史 TestFlight 当成正式 RC。
- 核心闭环:`打开小巴 -> 文字/语音/拍照 -> 可编辑草稿 -> 用户确认 -> 数据写入 -> 今日状态刷新 -> 可撤销或修正`。

## S1 · Discovery

- 生产配置当前仍声明 iPad、多方向、Watch extension、Rokid、Siri、后台定位/音频/蓝牙。
- 通知在登录后自动请求系统权限；定位在第一次进入主界面约 1 秒后主动弹窗。
- App Store 截图是 2026-06-30 的旧 UI；最新 Store build 225 早于当前 `main`。
- `PrivacyInfo.xcprivacy` 尚未声明 App 自身收集的数据；账号删除只写审计日志，缺持久状态与运营闭环。
- 当前工作树另有“今日行动渐进式计划”WIP；本次不回退，纳入 Agent 核心链路回归。

## G1 · 准入

```yaml
RequirementAdmission:
  request: 把当前产品收敛为可提交 App Store 的可信 iPhone 首发版
  classification: release_trust_and_scope
  first_user_fit: yes
  core_loop_step: intake -> agent draft -> manual confirm -> persistence -> review
  first_class_objects: [WriteIntent, ExecutionEvent, ConsentGrant, ProvenanceRecord]
  target_surface: [Mobile, Backend, Privacy Web, Release Tooling]
  source_of_truth: [PostgreSQL, App Store release pack, iOS production config]
  safety_level: privacy_sensitive_and_medical_boundary
  prescription_or_causal_verdict: forbidden
  autonomy_tier: manual_confirm
  evidence_provenance: required_for_health_actions
  success_metric: core acceptance cases pass with no raw JSON, duplicate write, lost image, or permission-at-launch
  added_user_burden: permission prompts move to explicit feature actions
  burden_justification: contextual consent improves comprehension and review compliance
  non_goals: [iPad launch, Watch launch, Rokid launch, autonomous medical decisions]
  smallest_end_to_end_slice: iPhone portrait core Agent loop plus privacy and deletion controls
  stale_surface_to_remove_or_archive: [production Watch, production Rokid, production Siri, startup permission prompts]
  spec_required: yes
```

裁决: **PASS**。用户已确认采用 iPhone-first 规划。

## S2/S3 · PRD 与规划

- 产品依据:`docs/prd/reva-personal-health-os-prd.md`。
- 实施计划:`docs/plans/2026-07-14-app-store-iphone-first-release-plan.md`。
- 首发承诺:Agent Native、Mobile First、iPhone portrait；用户可在不授予通知、定位、麦克风、照片或 HealthKit 权限时使用文字对话。

## G2 · 可行性与安全压测

- iPad/Watch/Rokid/Siri 从标准 production 包移除，但保留显式独立 profile 供后续验证。
- HealthKit、相机、照片、麦克风、语音识别保留，因为属于核心记录入口；均只能由用户动作触发授权。
- 所有健康写入保持 `manual_confirm`；无法取得可验证回执时不得显示成功。
- 医疗输出继续限制为记录、解释和生活方式建议，不诊断、不处方、不调整剂量。
- 原生配置变化必须走新 EAS production build；旧 build 225 不可作为 RC。

裁决: **PASS**。无待拍板项。

## S4 · 研发任务

- [x] R1 iPhone-only production scope 与配置回归测试。
- [x] R2 通知/定位改为场景触发授权。
- [x] R3 隐私清单、隐私政策、账号删除处理闭环。
- [ ] R4 Agent 核心写入、语音、拍照、分享和渲染回归（自动化与模拟器已过；真机待测）。
- [x] R5 安全、依赖、可访问性和审核材料 Gate。
- [ ] R6 commit/push、新 EAS build、TestFlight 与真机 G6。

## Gate Ledger

| Gate | 状态 | 依据 |
|---|---|---|
| G1 准入 | PASS | iPhone-first 核心闭环与一等对象映射明确 |
| G2 可行性/安全 | PASS | 已冻结范围与医疗/隐私边界 |
| G3 测试 | PASS | 合并后后端联合回归 381 项、Mobile 全量 1717 项、TypeScript、Lint、iOS 原生模拟器构建与启动通过；全量回归见发布记录 |
| G4 安全 | PASS | 生产包无后台录音/持续定位；账号删除、隐私清单、写入回执 fail-closed 已复核 |
| G5 部署健康 | PENDING | 等待新 production build |
| G6 真机验证 | BLOCKED | 必须在同一 TestFlight build 完成真实 iPhone 语音/拍照/微信与小红书分享/写入/删除状态证据 |

## Correction Block

- 旧基线:2026-06-29 dossier 记录“final-submit preflight passed”，且 Store build 225 已上传。
- 新证据:build 225 早于当前 `main`，截图和原生能力也已漂移。
- 新基线:只有从本 dossier 对应提交构建的新 production 包，完成 G3-G6 后才可提交审核。

## 2026-07-14 Verification Notes

- iOS production prebuild: iPhone-only (`TARGETED_DEVICE_FAMILY=1`)、portrait-only、deployment target 16.0。
- 最终 `Info.plist` 不含 `UIBackgroundModes`、`NSLocationAlwaysUsageDescription` 或 `NSLocationAlwaysAndWhenInUseUsageDescription`。
- 修复 Mobile 草稿恢复:SecureStore key 改为平台允许的字符集，避免应用重启或前后台切换时丢失输入草稿。
- 修复低质量主动开场:过滤“已记录/记录成功”类回执标题，不再生成“今天就是已记录的检验日，做到了吗”。
- 修复 Mac/Web 连续提醒链路:生产日志证明上下文历史已保留；失败来自 SmartReminder 的 `pending` 被误判为未写入，而非记忆缺失。
- 新增时间窗原子提醒:支持 `start_time + end_time + interval_minutes`，09:00–20:00 每 90 分钟确定性生成 8 个时点；同一用户重复提交幂等复用已有记录。
- 对“9点到20点”这类补充回答增加确定性上下文恢复：仅在当前消息明确给出时间范围时继承最近一轮已确认的频率，避免模型把整段计划收缩成单个 09:00 提醒。
