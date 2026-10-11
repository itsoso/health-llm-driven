# Plan: 排便记录与私有照片

需求与不变量见 docs/specs/active/2026-10-11-bowel-photo-record.md；产品目标见 docs/prd/2026-10-11-bowel-photo-record.md。

1. Backend: 扩展现有模型和双方 API 契约；nullable photo_key/client_request_id 成对 managed migrations；owner-scoped 私有图片校验与签名响应；用户+UUID 幂等；RED/GREEN、PostgreSQL 与迁移验证。
2. Mobile: service 类型、上传与读取；记录页入口、modal route；可选状态、日期时间、相机/相册/移除、明确保存、历史照片按需查看。会话 owner 绑定、同步点击锁、固定提交 UUID、失败保留。
3. Integration: 类型生成/地图、Jest/tsc/后端测试、G4 独立隐私写路径审查；只提交本任务文件，保留饮食入口和性能任务 WIP。
4. Delivery: 本次代码实现与本地验收。后续干净候选完整 CI 与后端迁移部署、OTA 各自独立 Gate，原失败 OTA 不消费新 claim 绕过。

数据流: Mobile confirm -> private medical upload -> excretion create(owner + UUID + photo key) -> PostgreSQL -> fresh signed response -> private history.
一个 writer 修改 backend，root 修改 Mobile 与文档，reviewer 只读。回退见 feature spec。
