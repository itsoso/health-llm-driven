# Feature Spec: 饮食记录详情与后续交互

> Status: implementation
> Updated: 2026-10-31
> Related PRD: reva-personal-health-os-prd.md
> Related code: mobile/app/diet.tsx

## Decision and problem

点击饮食列表中的记录打开详情，可查看完整描述、全部照片、营养与备注，并继续修改、
分享、删除或复盘当天饮食。当前卡片不可点击，描述截断且编辑隐藏在左滑操作中。

## Requirement Admission

```yaml
RequirementAdmission:
  request: 饮食记录要支持点击查看详情 以及进一步交互
  classification: product_change
  first_user_fit: 减少日常饮食核对与纠错成本
  core_loop_step: execution -> verification -> review
  first_class_objects: [ExecutionEvent, HealthTwin, WriteIntent]
  target_surface: Mobile diet
  source_of_truth: 认证用户的后端 DietRecord
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 已有 owner-scoped daily diet query
  claim_hedging: hedged
  verification_window: 当前会话
  success_metric: 记录可打开并在同一记录上执行既有操作
  added_user_burden: 一次点击
  burden_justification: 可看完整内容并发现操作
  non_goals: 新识别模型、新数据库、单餐 AI 授权协议
  smallest_end_to_end_slice: 列表点击 -> 详情 -> 既有编辑或日复盘
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## User flow and surface contract

Mobile 从当前本人日期列表按 ID 选择记录，使用原列表最新对象派生详情，不复制持久化快照。
详情展示日期、餐次、完整食物/份量、全部照片、热量、蛋白质、碳水、脂肪、纤维及备注。
缺失营养显示未记录，零与缺失区分；照片估算不作为精确检测值。数字复用
`formatDisplayNumber`（Mobile 展示适配器），最多两位小数，不改存储值。

修改沿用 MealForm 和原子重算；删除沿用确认对话框；分享沿用现有分享面。
“复盘当天饮食”沿用 post_confirm 的原 prompt 和本人记录 ID 验证，日期徽标来自目标记录，
不冒充新增的单餐分析能力。打开/关闭详情不写健康记录、不自动调用 AI。

## Data, privacy and AI boundary

无 API、模型、字段、迁移变化。详情绑定 owner、token、consent revision 和日期；登出、
切换用户/日期、撤销同意、记录消失即关闭，不向新会话展示旧详情。照片使用现有私有图片
来源构建器，不向外站发送认证头。详情操作必须来自仍存在的当前本人记录。
客户端上下文只作 lookup hint，后端 `_resolve_post_confirm_diet_review` 以认证用户及
记录 ID 查库并取得日期。新入口不新增 LLM 指令或绕过安全规则。

## Acceptance and verification

- 点记录正文/照片可打开详情；分享与重试按钮不同时打开详情。
- 完整长描述、全部照片、缺失值与零值、两位展示精度有组件测试。
- 修改绑定所选记录；删除必须确认，取消不写；复盘绑定记录 ID 和原日期。
- 原记录刷新后详情同步；账号/日期/同意变化或记录删除不留下旧详情。
- 既有拍照确认、原子编辑和分享回归通过；tsc、定向 ESLint、地图检查通过。
- 本地组件验证不代替模拟器和生产验证。

## Delivery

纯 JS/TS UI 可走 trusted OTA，但当前主干分叉和并行工作区先阻断外部写入。
无备份/回退副本。发布需干净目标 SHA、集成闸、独立安全审查、精确绿色 CI、
同 SHA 后端及 OTA validate/publish 回执。尚无需要用户拍板的产品分叉。
