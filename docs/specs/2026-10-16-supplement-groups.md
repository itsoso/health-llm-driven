# Feature Spec: 我的补剂组合与整组确认

Status: approved for implementation

## Decision / Problem
用户同意先实现“我的补剂组合＋整组确认”，减少每日重复勾选，为后续配盒保留组合与执行事件。智能硬件、每周装盒和自动服用推定不在本次范围。

## Requirement Admission
分类 new_product_behavior；first_user_fit 为本人已保存补剂的重复打卡；核心循环为执行与核对；对象 HealthProtocol / ExecutionEvent；目标为聊天补剂弹窗；真源服务器本人组合与独立事件快照；safety_level medical_boundary；autonomy_tier manual_confirm；不提供处方/剂量建议；证据为用户明确确认；spec_required yes。G1 PASS，用户“可以”及持续发布授权覆盖本切片。

## Flow
聊天＋补剂打卡 → 我的组合 → 新建/编辑名称和已有补剂 → 保存（不打卡） → 选择组合核对当前成员 → 明确整组已服 → 原子保存记录及当时组合快照 → 显示回执。原逐项勾选继续保留。

## Contract / Storage
复用 HealthProtocol domain=supplement/source_model=supplement_group 与 versioned implied_quantity；HealthProtocolEvent.value 保存服务端生成的首次确认快照。无 ORM/schema 变化。专用 /supplements/groups：GET 列表、POST 保存新组、PUT /{id} 更新、DELETE /{id} 归档、POST /{id}/confirm 确认；读取返回账户当天日期、revision、成员及今日历史。创建/修改仅名称及 supplement_ids，修改携带 revision；确认携带 revision、record_date、confirmed=true。均不接受 user_id 或实际剂量。契约具体类型由 backend schema 导出，mobile同步。

## Invariants
所有成员本人且启用；组合最多20个、成员1–30个，名称1–60字。确认前 fresh revision 和账户日期匹配；定义/成员变化拒绝。首次事件快照保留当时名称、成员ID、参考用量、记录关联、来源manual_group；不把参考用量写入actual_dosage。已服成员保留原实际剂量。相同组当天重复返回原快照，修改组后也不追加新成员到旧事件。所有通用协议创建、完成、自动观测、跳过、稍后、恢复及调整入口不能伪造/改写组合事件；组合不进入通用自动执行/议程。专用事务锁定本人和组合，唯一冲突整批回滚；不宣称锁覆盖其他旧写入口。移动端未知结果仅查回，无自动POST重试；切账号/跨日/内容变更废弃旧确认。

## Validation / Release
先 RED 再实现；后端 ownership、原子回滚、重放不可变、通用入口阻断、跨日/revision；PostgreSQL 并发及JSON语义；移动端建立/编辑/保存无打卡/整组核对/失败状态/账号切换；类型同步、System Map、独立 G4、完整 CI及 CI-mode。部署当前 main 精确SHA，再trusted OTA validate/publish。无备份、无真实模型评测、无真实健康数据读取。设备拉取独立报告。

## G2
独立 cold_recovery_safety 条件 GO：完成上述全部通用入口防护及 PG 并发回滚证据；不得绕过发布 schema gate。无待用户决策分叉。
