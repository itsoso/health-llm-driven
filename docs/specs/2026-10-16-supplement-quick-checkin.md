# 补剂快速勾选弹窗

Status: accepted for implementation

## 决策与范围

用户要求「是否可以做一个快速补剂弹出UI 让我check选中」。聊天加号菜单增加“补剂打卡”，打开底部弹窗，以本人启用补剂列表选择本次已服项目，统一人工确认。复用已有数据模型和批量打卡，不调用 LLM。

## RequirementAdmission

- classification: new_product_behavior
- first_user_fit: 减少逐次输入名称和重试成本
- core_loop_step: 执行 -> 记录 -> 核对
- first_class_objects: ExecutionEvent / HealthProtocol
- target_surface: mobile chat
- source_of_truth: 认证用户的 supplement definitions 与当日 records
- safety_level: medical_boundary
- prescription_or_causal_verdict: none
- autonomy_tier: manual_confirm
- evidence_provenance: 用户主动勾选已服事实
- claim_hedging: n/a
- verification_window: 当前账户当地日
- success_metric: 选中项一次确认有匹配回执；未选项不写
- added_user_burden: 勾选及一次确认
- burden_justification: 防止猜测已服项目
- non_goals: 剂量建议、自动识别名称、修改方案、自动补服、跨设备严格一次提交
- smallest_end_to_end_slice: 加号 -> 弹窗 -> 已有清单 -> 勾选 -> batch -> 回执/读回
- stale_surface_to_remove_or_archive: 无
- spec_required: yes

## 交互及安全契约

默认全不选。名称及常规用量可展示，明确不是本次实际用量；本次仅记录已服状态，不传 actual_dosage/user_id。已服项禁选。空态引导返回对话添加补剂清单；查看补剂记录入口打开现有记录页（该页不提供新增清单能力）；加载失败可重试。提交按钮显示选中数，提交期间禁止二次点击和关闭。关闭未提交弹窗不写入。

GET /supplements/me/date/{date}，POST /supplements/records/batch。日期必须来自有效账户时区；账户/时区/日期改变须重新加载，不把旧选择送入新上下文。认证变更废弃请求结果。提交前刷新当前状态剔除已服项，核对回执 ID、日期、taken、record_id；失败/超时不自动重发，先读回核对并提示不确定性。严格跨设备条件写不在现有接口能力内，不宣称该能力。

## 验证与发布

先 RED 后实现：默认不写/不选、空态、加载错误、选择提交、已服禁选、快速双击、取消、异常回执、超时核对、换账户和跨日。客户端类型检查及聊天菜单回归。独立 G4；完整精确 SHA CI；既有部署/OTA gates。仅用合成数据，不读真实健康记录、不真实模型评测、不备份。
