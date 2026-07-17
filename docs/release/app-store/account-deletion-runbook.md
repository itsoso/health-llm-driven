# 账号与数据删除处理清单

本清单用于处理 App 内 `删除账号与数据` 请求。请求默认须在提交后 7 天内完成。任何步骤失败都必须保持 `processing`，不得把请求标记为 `completed`。

## 1. 领取请求

1. 管理员查询 `GET /api/v1/admin/account-deletion-requests?status=requested`。
2. 将目标请求更新为 `processing`，在 `note` 中记录工单号和处理人。
3. 核对请求中的 `user_id`、`request_id` 和 `audit_id`，禁止仅按姓名或邮箱操作。

## 2. 停止新增数据

1. 撤销或删除 Garmin、Apple Health 之外的服务端设备凭证和第三方连接。
2. 停止该用户的同步、提醒、后台任务和推送 Token。
3. 记录操作开始时间；处理期间不得重新启用连接。

## 3. 清除用户数据

在执行第 5 步前，管理员必须调用
`GET /api/v1/admin/account-deletion-requests/{request_id}/verification-report`。
该接口只返回表名、行数、缓存数量、私有文件数量和 `scope_digest`，不返回健康正文。
报告中的 `can_finalize` 必须为 `true`；否则后台完成接口会拒绝请求。

在生产 PostgreSQL 的受控维护窗口内执行经评审的用户删除脚本或 SQL。清除范围至少包括：

- 账号凭证、登录会话、API Key 和设备凭证。
- 健康记录、HealthKit/Garmin 同步数据、体检、基因、用药、补剂、饮食、图片和文档。
- Agent 对话、消息、记忆、草稿、行动卡、提醒、计划和生成的报告。
- 对象存储中的原始图片、报告和导出文件，以及缓存和搜索索引。
- 家庭共享、公开分享和第三方连接中的可访问副本。

不得直接复用旧的 `DELETE /api/v1/admin/users/{user_id}` 作为完成依据；该端点不能证明覆盖全部健康表、对象存储和缓存。

## 4. 验证

1. 用只读查询确认所有以 `user_id`、账号标识或对象存储前缀关联的业务数据均为 0。
2. 确认登录失败、推送停止、分享链接失效、图片和报告 URL 不再可访问。
3. 保留不含健康正文的最小审计记录：请求编号、处理人、完成时间、验证查询摘要和工单引用。
4. 将验证证据写入受控工单，生成唯一 `verification_reference`。

## 5. 完成请求

只有第 4 节全部通过后，才可调用：

```json
{
  "status": "completed",
  "note": "已按账号删除清单核验",
  "data_deletion_verified": true,
  "verification_reference": "受控工单或变更记录编号"
}
```

后台会拒绝缺少清除核验或验证引用的完成请求。无法在 7 天内完成时，保持 `processing` 并联系用户说明进度；只有法律义务或身份核验失败时才可 `rejected`，且必须写明原因。
