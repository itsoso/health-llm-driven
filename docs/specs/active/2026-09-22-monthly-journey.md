# Feature Spec: 小巴健康 · 这一路

> Status: implementing — G1 accepted; G2 GO after review
> Owner: Codex / 用户
> Updated: 2026-09-22
> Related PRD: docs/prd/2026-09-22-monthly-journey.md

## 1. Decision / Problem

用户确认完整版：为已保存的饮食、生活事件、本人聊天照片可选附上城市，
按自然月回看足迹与生活片段，生成可选择内容的品牌长图。更新前台定位用途
并通过新安装包发布；不申请 Always，不开全天后台追踪。
不新建平行日记，不自动重放/重新识别或重复写入原健康记录。

## 2. Requirement Admission

完整卡见 `docs/dossiers/2026-09-22-monthly-journey.md` G1。
映射 ExecutionEvent 的地点上下文及 Review；城市变化帮助用户回看记录发生
情境，不形成 HealthTwin 医学推断。首月验证是否易核对、更正和回顾。
只做个人纪念/自我照顾片段，不按里程评成绩，不编心情、因果或健康改善。

## 3. Non-Goals

- 周报、自动推送、后台轨迹、实时共享、地图导航、真实行驶距离、视频动画。
- 新增药物/补剂/健康建议、LLM 生成总结或把坐标发给模型。
- EXIF 自动推断、从旧聊天猜地址、读取整个相册、修改当前天气城市。
- Web/Mac/Watch 新展示面；本轮不自动部署、发 OTA 或上传商店。

## 4. User Flow / Surface

```text
小巴聊天更多 -> 这一路 -> 选择月份 -> 添加地点
  -> 从饮食 / 生活事件 / 聊天照片选择本人记录
  -> 核对发生日期 -> 手动城市 或 明示用途后单次定位 -> 确认保存
  -> 月度城市节点及片段 -> 勾选分享片段/照片 -> 长图预览 -> 保存/系统分享
```

Mobile 是唯一编辑/分享面；Backend 是归属、日期、城市与源记录的真源。
“足迹连线”按记录顺序展示示意节点，不采用虚构地理坐标，醒目标注非实际路线。
空月显示添加引导；单城可回顾；不为了好看伪造统计。分页明确剩余记录，
不能把已加载页当完整月份。原记录删除时相关地点失效/随源删除。

## 5. Data Contract

新增 `JourneyPlace` 注释表：owner FK；diet_record_id / life_event_id /
chat_message_id 三个可空 FK（CASCADE），恰好一个非空；每种源每用户唯一。
chat_message_id 明确指向 agent_messages.id，经 AgentConversation.user_id
验证 owner；不是已废弃 chat_messages。life_event_id 指向 health_episodes.id。
city 用 StrictEncryptedString 加密，禁止明文 fallback；不存纬经度、
精确地址、酒店、健康读数、原图 URL 或聊天全文。字段还包括 local_date、
timezone、location_source(manual/device)、version、created_at/updated_at。
按 owner/local_date/id 索引分页；不从加密城市建可还原索引。

所有读写基于当前认证用户，写入还必须检查源记录归属；life_event 类型限定；
chat_photo 限本人 user 消息且有合法本人私有照片。拒绝任意 URL 注入。
原记录通过 FK 关联，不复制事实；source deletion/account deletion 必须验证。

API（统一 `/api/v1/journey` 前缀）：

- GET `/sources?kind=diet|life_event|chat_photo&month=YYYY-MM&timezone=IANA&offset=0&limit=30`
  -> `{items: JourneySource[], total, offset, limit}`。
- PUT `/places/{kind}/{source_id}` body
  `{city, local_date:YYYY-MM-DD, timezone, location_source:manual|device,
  expected_version:0|positive, confirmed:true}` -> JourneyPlace。
  expected_version=0 仅创建；已有行及并发冲突 409，重新读取后显式编辑。
- GET `/month?month=YYYY-MM&offset=0&limit=30`
  -> `{month, items:JourneyPlace[], total, offset, limit}`。
- DELETE `/places/{id}?expected_version=N` -> 204；只删地点，不删源记录。
- POST `/export-preview` body
  `{items:[{place_id,version,image_keys:string[]}]}`
  -> `{month,items:JourneyExportItem[]}`。上限 30，拒绝重复项/跨月。
  校验归属、当前源仍在、版本一致、所选图仍属该源；版本/图变更 409，
  源消失/不属于当前账号 404。成功前写审计（仅操作和数量/内部 IDs），
  失败不伪装成功，不记录城市、图片地址、原文。不声称回执等于分享成功。

JourneySource:
`{kind, source_id, title, suggested_date, date_basis:record|message,
images:JourneyImage[], image_status:ready|unavailable|none, place:JourneyPlaceBase|null}`。
JourneyPlaceBase:
`{id, kind, source_id, city, local_date, timezone, location_source, version}`。
JourneyPlace = Base + `{title, images:JourneyImage[], image_status:ready|unavailable|none}`。
JourneyImage = `{key:string,url:string}`，key 为 owner/source/规范私有路径绑定
的稳定摘要，不使用签名 URL，不向客户端暴露绝对文件路径。
JourneyExportItem = `{city,local_date,kind,images:JourneyImage[]}`，无 title。

私有 title 只供用户挑选，分享模型不含 title；健康/症状等敏感原文不得
进入分享图。图片只从源记录重新校验、签名或鉴权访问：仅允许已证明本人
所有的规范 chat/diet 私有路径；拒绝其他 origin/owner、异常 JSON/路径及
无法证明归属的 legacy 图片。既有 refresh helper 不是授权校验器。
任一源图非法时图集置空并标 unavailable，不能静默假装完整；chat_photo
此时不能添加地点，diet/life_event 可以无图继续。life_event 首版无独立图集。
图片加载失败显式提示并阻止导出，用户可取消选图继续。

## 6. Location / Date

- 明示“将这条记录的城市保存为足迹”，用户点击才请求 foreground 一次定位。
- 端上 reverse geocode 只取 city/subregion；不向本后端发送坐标，失败允许手填。
  系统地理编码可能需要系统地图服务，不承诺完全离线。
- 城市可编辑；说明仅填城市，不填地址；分享时再次确认城市及照片内隐私。
  自由文本不能技术保证是城市，不能宣称用户输入已自动脱敏。
- old/imported photo 的上传日期仅为建议（date_basis=message），必须提示非拍摄时间。
- 发生日期由用户确认；单次定位仅允许今天，历史日期只手动选城市，不能拿当前
  位置追溯历史。客户端日期改变后清除 device 结果；服务端校验 device 日期
  等于提交 timezone 下 today，timezone 必须合法。
- life_event aware 时间按请求 timezone 转日；旧 SQLite naive life_event 按
  既有北京时间语义兼容；chat naive 时间按 UTC；diet record_date 不改变。
- 月度按用户确认 local_date 归月，跨时区旅行不事后移动已确认记录的月份。

## 7. Privacy / Share

- 分享选项初始全不选，用户最多选 30 条；照片也需显式选择（默认不附图）。
- DTO 白名单只允许城市、月、日级日期、泛化片段类型及选中照片；不传原文、
  健康指标、时分、坐标。渲染前统一白名单投影，不靠 UI 隐藏私有字段。
- 固定宽度、自然高度、等比截图，避免文字拉伸；照片未就绪不截，错误可重试。
- 预览和导出限明确高度/条数；过多需减少选择，不静默裁掉尾部。
- 分享渲染只使用 export-preview 返回的白名单 DTO；保存/分享前再次提交同一
  版本和选图预检，失败销毁旧图，不打开分享面板。检查是导出时点检查，
  不承诺撤回已交给外部 App 或已由用户主动存入相册的图。
- 修改选择即作废旧图；重复点击互斥；关闭、退出登录/换账号、页面离开时清理
  本地临时图/下载文件并取消迟到结果；导出前校验当前认证用户仍与加载时相同。
  不删除用户主动保存到相册的成品。
- 分享调用系统面板（微信/小红书可用时），不承诺第三方已收到或成功发布。
  不创建公开分享网页或可复用公开原图链接。
- 撤回定位权限不自动删除已确认足迹；界面提供逐条删除。删除账号时全部删除。

## 8. Acceptance / Verification

1. RED/GREEN：无权限仍手填、历史日期禁止 device、定位失败不伪装保存成功。
2. 同用户 CRUD/version/idempotence；他人源与 annotation 均 404；非生活事件
   与 assistant 消息不能注释；SQL/HTML/控制字符/超长/未知字段边界。
3. PostgreSQL 恰一 FK、唯一、并发版本、源/账号 cascade、加密 at rest、
   时区月边界和 owner/date 查询索引证据；受管迁移镜像兼容与回放。
4. Mobile tsc/Jest：入口、各 source 标签、分页、月切换/乱序/账号切换，
   保存错误留草稿、409 提示重读、删除、分享白名单和默认空选择。
5. Simulator：实际可点击路径、空态/错误/长城市名、多照片长图、无顶部空白、
   字体不变形；模拟坐标仅证明流程，不冒充真实 GPS 或第三方 App 交接验证。
6. native app.json/plugin 两处用途一致；Always/background 不增加。
7. 集成闸、System Map、文档一致性、秘密扫描、固定提交独立安全 GO。

## 9. Rollout / Rollback

先后端受管迁移/代码（旧 App 不受影响），再新原生安装包，不能仅 OTA。
本轮发布仍受用户“全部完成后统一发布”和真实目标 main CI 限制。
代码回滚时保留新增注释表，停止新入口；不自动删除用户确认的足迹。
不可逆迁移前保留备份，灾难恢复/密钥轮换沿用项目政策。

## 10. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-09-22 | 首版完整功能定义 | 用户选择单次定位＋手动城市＋新安装包 |
