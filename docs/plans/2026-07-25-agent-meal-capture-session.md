# Agent 多图餐食采集事务实施计划

> 按 P0 -> P1 -> P2 顺序执行。每个阶段先写失败测试，再实现并运行相关回归。

## P0 · 正确性

### 1. 服务端聚合事务

- 在上下文餐食捕获服务中增加批量输入，按 `source_message_id` 聚合同轮图片。
- 所有图片先成为 `DietPhotoAsset`，共享同一决策和记录归属。
- 自动记录只创建一次 `DietRecord`；确认路径只创建一个 `DietPhotoDraft`。
- 数据库幂等仍以 owner + source message 为边界，图片用 ordinal 区分。

### 2. 稳定投影

- 动态卡以 `diet-capture:<capture_session_id>` 作为稳定 `card_id`；草稿确认、自动写入、实时重连和历史恢复只更新业务投影，不更换卡片身份。
- 数据增加 `photo_asset_ids/photo_urls`，保留旧单图字段兼容。
- 持久化去除所有 `photo_urls`；历史读取 owner-scoped 批量重新签名。
- 客户端按 `card_id` 去重，实时、重连和历史恢复更新同一卡片。

### 3. 媒体状态与恢复

- 资产 lifecycle 覆盖 pending/attached/deleted；卡片暴露非敏感阶段状态。
- uncertain 写入先按 source message reconcile，禁止直接补写。
- 对话重试复用相同 client turn/source message。

## P1 · Mobile 体验

- `DietDraftCard` 读取多图，首图封面显示数量，点击进入横向全屏浏览。
- 图片加载失败保留营养卡并显示局部重试，不把整轮标为失败。
- 同记录调整动作携带 `record_id`，服务端更新原记录并保留 revision 证据。
- 本地预览只用于上传等待态，服务端资产可用后替换；App 生命周期变化后可恢复。
- 错误按 upload / recognition / persist / attach / render 分类。

## P2 · 观测、完整性、性能

- 统一记录 `client_turn_id/run_id/source_message_id/photo_asset_id/diet_record_id/card_id`。
- 增加完整性巡检：过期 pending、无记录 attached、记录缺文件、卡片缺资产、同轮重复哈希。
- 复用现有客户端压缩；相同内容哈希避免重复资产和重复视觉调用。
- 对话历史增加游标/窗口能力；只为返回消息重新签名图片。

## 测试与验收

### Backend

- 同一消息两张图 -> 一条记录、两资产、一个回执。
- 低置信两张图 -> 一个草稿、两资产、一个确认卡。
- 重试相同消息 -> 不新增记录/草稿/资产。
- 历史恢复 -> 两个新签名 URL，DB meta 不含 URL。
- 外部用户资产 -> 不返回。
- 删除/修正 -> 全部资产保持正确归属。

### Mobile

- 多图数量、封面和全屏浏览。
- 单图旧卡兼容。
- card_id 去重。
- 图片局部失败不遮断正文和操作。
- App 重开后历史卡恢复。

### 发布 Gate

- Backend focused + relevant integration pytest。
- Mobile Jest + TypeScript。
- API 类型生成和 drift 检查。
- 模拟器截图与交互验证。
- 独立隐私/并发/幂等复审。
- 干净 main 部署、健康分、生产路由 smoke；Mobile 纯 JS/TS 走 production OTA。
