# Dossier: 上下文餐食照片采集

| 字段 | 值 |
|---|---|
| slug | `contextual-meal-photo-capture` |
| 创建日期 | 2026-07-19 |
| 当前阶段 | G4 安全复审 |
| 状态 | reviewing |
| 负责 | Codex |
| 反馈环 | 后端 pytest / Mobile Jest + TypeScript / Web build / Mac build / backend deploy + Mobile OTA |

## S0 · 用户需求(逐字)

> 还是不够智能，无法根据图片自动保存食物，当然我没有给出明确指令，但也没给出一些提示，比如要我确认并保存饮食，默认食物的照片应该在特定场景，比如按照用户所在时区，到了早中晚三餐的时候，自动保存，另外保存之后，不能列出饮食对应的图片，是不是系统里边没有保存图片路径？给出DB的设计和实现。

- 谁用 / 解决什么 / 现在怎么绕过：在小巴对话中拍餐食的用户；目前必须明确说“记录”才可能触发写入，而写入不会接住聊天图片，导致没有可验证回执和图片化历史。
- 锚点用户相关性：把高频、低负担的餐食采集接回 `DietRecord -> HealthTwin -> 今日行动` 主循环。

## S1 · Discovery(现状勘察)

- 已有可复用：
  - `DietRecord.image_url` 已存在，`DietPhotoDraft` 已能在直接饮食页识别时保存 owner-scoped 图片并在确认后转入记录。
  - `backend/app/api/diet.py` 已有私有图片持久化、幂等写入和照片草稿生命周期。
  - `backend/app/services/agent_executor.py` 已在聊天图片上调用结构化食物识别，且已有用户时区的系统时间上下文。
  - `mobile/components/chat/cards/DietDraftCard.tsx` 已能承接 `diet_record.create` 的确认动作和写入回执。
- 缺口：聊天图片只以 `chat` 私有媒体留在聊天消息上；结构化识别输出没有携带可被饮食写入消费的照片资产；当前图片语境/记录判断含关键词启发式，且没有本地餐时的显式策略；饮食 API 只返回单一 `image_url`，列表未把多图资产作为一等数据渲染。
- 硬约束：食物识别和营养估算仍是不确定候选事实；图片属于敏感健康数据；所有写入必须 owner-scoped、可幂等、具可验证 receipt；签名 URL 不是 DB 真值，不能持久化。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `WriteIntent`、`ExecutionEvent`、`HealthTwin`。
- core_loop_step: 食物照片采集 -> 可验证饮食事实 -> 今日饮食/下一餐行动。
- target_surface / safety_level / autonomy_tier: Backend + Mobile 首发，Web/Mac 读取同一 API；privacy-sensitive；仅受限高置信餐时走 `auto`，其他图保持 `manual_confirm`。
- spec_required(§8.1): 是。它新增用户可见行为、新写入路径、跨端 API 和长期媒体数据模型。
- smallest_end_to_end_slice: 小巴上传一张高置信午餐图 -> owner-scoped 饮食图片资产 -> 受控自动记录或当前页确认卡 -> 带图的饮食记录读取。
- stale_surface_to_remove: 聊天图片仅供模型识别、没有饮食媒体归属的隐式路径。
- **裁决**: PASS — 用户已明确要求实现受情境约束的自动保存，并要求 DB 设计。
- 用户确认: 已在本需求中明确授权此范围。

## S2 · PRD

- 链接: `docs/prd/2026-07-19-contextual-meal-photo-capture.md`
- 继承: `docs/specs/active/2026-07-11-diet-capture-excellence.md` 的隐私、识别清洗、营养不确定性、所有权与幂等要求。

## S3 · 规划

- 链接: `docs/plans/2026-07-19-contextual-meal-photo-capture.md`
- 后端先发布媒体/写入契约与迁移，再更新 Mobile，再刷新 Web/Mac 读取类型；Mobile JS/TS 改动走 OTA。

## G2 · 可行性 + 安全压测

- 压测结论：不把任何上传图片或任何高置信模型结果直接当饮食事实。自动写入只在用户主动发起聊天图片、视觉识别为食物、用户本地早餐/午餐/晚餐窗口匹配、置信度达阈值、无重复写入时允许；每次均生成 `record_id` 的可验证回执。删除仍复用既有 owner-scoped 饮食历史流程，避免新增未定义恢复语义的乐观撤销路径。
- 硬阻断(已焊进规划)：不持久化签名 URL；不复用聊天图片路径作饮食资产；不使用正则表达式推断图片写入意图；不对截图/非食物/低置信/夜间零食自动写入；写入失败不得显示“已记录”。
- **裁决**: PASS — 以“受限自动化 + 可验证回执 + 其他情况当前页确认”的方案进入研发。

## S4 · 研发任务分解

- [x] T1: 新建多图饮食照片资产模型、成对迁移、owner-scoped 存储与签名读取。
- [x] T2: 增加上下文聊天照片专用服务；API 仍作为草稿确认的唯一写入消费端，保留幂等、receipt 和资产挂载。
- [x] T3: 实现时区餐时与语义视觉策略，输出 `auto_record`、`confirm` 或 `analyze_only`。
- [x] T4: 接入小巴聊天图片，自动保存或生成同页动态确认卡；自动保存只在服务端 receipt 后展示，删除复用既有 owner-scoped 历史流程。
- [x] T5: 更新 Mobile 饮食列表、聊天卡片和 API 类型，展示照片缩略图及多图浏览。
- [x] T6: 更新 Web/Mac 读取契约与带图展示，保证相同记录事实。
- [x] T7: 覆盖迁移、并发幂等、时区、隐私、自动化边界和三端渲染；等待独立安全复审结论后关闭 G4。

## S5 · 实现

- 已落地 `diet_photo_assets`：canonical `storage_key`、source-message/image-ordinal 幂等键、记录/草稿归属、识别快照与生命周期；PostgreSQL/SQLite 成对迁移。
- 小巴聊天图片在结构化视觉识别后进入纯类型化的餐时策略：仅聊天来源、高置信、用户本地正常餐时、语义捕获、无重复时自动创建 `DietRecord`；低置信或非餐时生成当前页 `diet_draft`；分析请求/非食物不写入。
- 所有新饮食图片入口（聊天、直接 `image_base64`、识别草稿）都写入 canonical `DietPhotoAsset`；自动保存产生 `diet_record` verified receipt，并投影与普通饮食记录相同的餐后行动协议（失败只记录告警，不篡改 receipt）。
- 确认卡的图片 URL 只存在当前 SSE 视图，服务端会话元数据和 Mac 本地缓存都会删除该短期 capability。
- Mobile、Web 的饮食历史消费 `photo_assets`（兼容 legacy `image_url`）并展示有序缩略图；Mac 在当前确认卡中消费同一 owner-scoped 照片，且确认动作只可使用已渲染卡片内、带 capability policy 的服务端草稿 token。

## G3 · 测试闸

- PASS（本地）：后端 99 项 focused pytest；Mobile TypeScript + 117 项 Jest；Web TypeScript、31 项 Vitest 与 production build；Mac 57 项 Swift 测试均通过。
- 迁移回归覆盖了 `DietPhotoAsset` 建表、旧 signed URL 规范化、未来 signed URL 拒绝，以及 SQLite trigger block 的受管执行器解析。
- 备注：Web build 仍有既存 lint warning；未新增 blocking error。Python ruff 不在当前开发虚拟环境中，未将“找不到命令”伪报为通过。

## G4 · 安全闸

- 触发：图片健康数据、自动写入、owner-scoped 私有媒体和新读取契约。
- 独立安全/隐私复审的整改已完成：Web 对话确认 action 现保留并受白名单/显式确认约束；过期草稿立即删除媒体资产；legacy `image_url` 增加 canonical 约束；SQLite 触发器迁移已被受管执行器正确原子执行。
- 最终提交后的独立复审待执行；重点复核 owner isolation、签名 URL、重复写入、草稿清理和跨端确认动作。

## G5 · 部署健康闸

- 未部署：本次工作仍在功能分支，等待 G4 和最终差异检查。

## G6 · 验证闸(人在环)

- 待真机验证：午餐时仅发食物照片、低置信图、非餐时食物图、断网重试、带图列表读取与删除。
