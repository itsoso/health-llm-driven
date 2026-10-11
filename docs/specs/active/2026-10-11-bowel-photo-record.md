# Feature Spec: 排便记录与私有照片

> Status: implementing
> Updated: 2026-10-11
> Owner: root

## Decision and problem
手机端新增排便记录弹窗，复用 excretion API；可手填时间、Bristol 类型、颜色、疼痛、是否见血、备注，并选一张照片，确认保存后查看自己的历史。已有后端记录缺少手机入口和照片关联。

## RequirementAdmission
- request: 我发现还要加一个排便的记录和拍照
- classification: existing health observation capture extension
- first_user_fit: 日常消化道观察和个人记录复核
- core_loop_step: observation -> HealthTwin evidence -> outcome review
- first_class_objects: HealthTwin, ExecutionEvent
- target_surface: Mobile 记录页、聊天附件菜单与排便记录弹窗
- source_of_truth: authenticated owner's excretion_records
- safety_level: sensitive health data and private medical photo
- prescription_or_causal_verdict: none
- autonomy_tier: manual_confirm
- evidence_provenance: user-entered observation; optional user photo
- claim_hedging: 不根据照片诊断；未选择状态保持未知
- verification_window: 保存后立即刷新，历史重新打开可查看
- success_metric: one confirmed form -> one owned durable record with optional photo
- added_user_burden: 明确点击保存，照片可选
- burden_justification: 防止错误或重复健康写入
- non_goals: 自动识别、诊断、分享、通知、LLM 提交照片
- smallest_end_to_end_slice: 记录页入口 -> 表单/拍照 -> 私有上传 -> 确认保存 -> 历史查看
- stale_surface_to_remove_or_archive: none
- spec_required: yes

## Contract and invariants
复用 POST /excretion/records 与 GET /excretion/records/me?type=bowel。新增可选 photo_key（medical/<authenticated_user_id>/<filename>）和 client_request_id（UUID）；客户端每个表单一个固定 UUID。另存 immutable client_request_hash，避免原记录修改后重放误判。数据库同一用户 UUID 唯一，相同提交重放返回原记录，不同载荷冲突。服务器校验路径、文件存在、owner 与无 symlink；响应 photo_url 为新签名 5 分钟私有 URL，不持久化 capability URL。历史图片失效返回 photo_unavailable=true，不把图片错误伪装成功，也不丢失已有观察记录。
照片在点击保存后上传，上传成功后同一表单复用 key；失败保留表单，跨账号异步结果不得展示或提交到新账号。退出/切换账号清空敏感状态。照片本机重新编码为 JPEG 移除原图元数据，查看时关闭图片磁盘缓存。现有相机与相册权限复用，不增加原生权限。只有用户明确保存才写记录，不发模型或社交分享。

## Acceptance
相机/相册取消与拒绝不写入；可无图保存；照片可移除；重复点击与同 UUID 重试不重复写；保存失败保留表单；跨账号不可读/关联他人照片；读取重新签名；历史照片默认隐藏，点击查看。日期/时间为用户本地日历输入，不推断未知的 Bristol 或见血状态。

## Validation and release
SQLite 快速回归 + PostgreSQL 数据/唯一性/迁移语义；Mobile interaction Jest + tsc；独立安全审核；生成 System Map 与客户端类型。相机实拍硬件验收未验证，模拟器可用相册合成图片测试。
部署与 OTA 必须在 CI、G4 通过后按现有可信工作流；上次 OTA 失败不重跑、不换 SHA 绕过。

## Rollback
先回滚应用以停止新照片写入；新增列 nullable，旧客户端兼容。迁移反向删除 photo_key/client_request_id/client_request_hash 与唯一索引会丢失新增关联，只能按正式回滚评审执行，保留原始图片与记录。
