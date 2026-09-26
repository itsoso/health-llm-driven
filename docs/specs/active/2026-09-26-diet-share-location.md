# 饮食分享：可选地点

> Status: implemented; locally tested and safety-reviewed; visual acceptance and release pending
> Updated: 2026-09-26
> Related: 2026-09-22-monthly-journey.md

## Decision / Problem

用户反馈“分享页面没有地址 没有地理位置的编写选项”。现有饮食分享预览、海报和文字均没有地点字段；足迹模块不能替代本次分享的地点编辑。

## Requirement Admission

```yaml
RequirementAdmission:
  request: 分享页面没有地址 没有地理位置的编写选项
  classification: existing-surface-completion
  first_user_fit: 拍照记录饮食后分享生活场景
  core_loop_step: 执行记录与回顾
  first_class_objects: [ExecutionEvent]
  target_surface: Mobile 饮食分享预览
  source_of_truth: 用户本次明确填写并确认的地点
  safety_level: sensitive-location-export
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 用户输入，不推断定位
  claim_hedging: 不声称设备定位或已保存到足迹
  verification_window: 本次编辑及导出
  success_metric: 新增、修改、取消、移除地点后图文一致且无旧图导出
  added_user_burden: 可选输入与一次确认
  burden_justification: 公开地理位置必须主动确认
  non_goals: GPS、后台轨迹、地址检索、服务端保存、自动读取已有位置
  smallest_end_to_end_slice: 两个分享入口共用编辑器，确认后重生成海报并同步分享文字
  stale_surface_to_remove_or_archive: 无
  spec_required: yes
```

## User Flow / Surface Contract

Mobile 分享预览 → 添加地点 → 手填城市/餐厅/公共地点 → 确认展示 → 重生成图片 → 分享图片或文字。编辑中不允许导出旧图；取消保留原确认结果。清除并确认即移除图文地点。默认不显示，关闭/换记录/换账户清除。

## Data / Privacy / AI

`DietShareComposer` 使用会话内 `locationLabel`，由共享格式化函数限制长度、移除不可见控制字符。传给海报及文字回调的值一致；不增加 DietRecord/API/数据库字段，不调用 LLM/GPS，不写服务器、日志或埋点。提示不要填写住址/房号。明确仅本次分享、不改饮食记录或足迹。现有裁剪/隐私遮挡保持不变。

## Acceptance / Verification

- 首次不含地点，两个入口均能手填、修改、清除；取消不改变原海报。
- 确认后旧截图被释放；新图失败时不回退到旧地点截图，允许重试。
- 新记录、关闭重开、身份失效不继承位置；异步截图不可污染下一会话。
- 长输入、空白、控制符归一；分享文字与海报同一显式位置，旧调用兼容。
- Jest（composer/card/presentation/chat/diet page）、TypeScript、相关 ESLint、diff/map 检查；独立安全评审。
- 模拟器验收和发布分别记录；不以测试替代实际截图验收。

## Rollout / Rollback / Non-Goals

仅 JS/TS/UI，无原生或迁移变化。用户本轮未要求发布，不运行 OTA/商店发布。未来按发布门禁发版，回滚该客户端提交即可；无持久数据需回退。永久保存地点和 GPS 后续另定，不阻塞手填入口。
