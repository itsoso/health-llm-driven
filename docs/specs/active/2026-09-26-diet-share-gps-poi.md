# 饮食分享 GPS / 高德 API 地点选择

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

> Status: implementing
> Updated: 2026-09-26
> Related: 2026-09-26-diet-share-location.md；全局 PRD R5/R10

## Decision / Problem

在已有可选分享地点中增加 GPS 和高德候选，减少手填；修复输入框过窄。用户已确认 API 方案，不引入原生 SDK。

## Requirement Admission

```yaml
RequirementAdmission:
  request: 默认 GPS 地点，精确到附近餐厅，使用高德 API
  classification: product_change
  first_user_fit: 出差饮食记录的低摩擦回顾与分享
  core_loop_step: 执行记录与回顾
  first_class_objects: [ExecutionEvent]
  target_surface: Mobile 饮食分享
  source_of_truth: 用户确认后的本次分享地点
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 当次设备定位与高德 POI，候选并非到店证明
  claim_hedging: hedged
  verification_window: 同一分享会话
  success_metric: 地点候选可确认或更正，图文一致且无跨会话污染
  added_user_burden: 单次第三方同意与公开确认
  burden_justification: 精确位置对外传输和公开必须分开确认
  non_goals: 后台定位、地图导航、记录或足迹写入、原生 SDK、LLM
  smallest_end_to_end_slice: 当前 GPS 到认证代理到候选到确认导出
  stale_surface_to_remove_or_archive: 替换旧窄输入编辑器，保留手填
  spec_required: yes
```

## User Flow / Surface Contract

添加地点 → 展示高德接收方、坐标/搜索词用途 → 同意本次查询 → 前台 GPS → 高德候选；当日记录优先定位，历史/无日期须明确选择当前位置，不声称是就餐位置。精度差提示手选；近距离餐厅推荐只填草稿，不自动公开。搜索/手填始终可用。清除/手填取消排队定位结果；关闭、换记录、身份失效、App 后台时停止应用旧结果。
地点编辑器全宽输入，候选显示名称和详细地址，默认公开名称；用户可手填完整地址但提示避开住址/房号。取消保留原已确认地点；确认后重生成图片，图文统一。

## Data Contract

- `POST /share-location/nearby`: `latitude`, `longitude` (WGS84), `accuracy_m`, `captured_at` (UTC ISO), `consent: "amap-share-location-v1"`。
- `POST /share-location/search`: `keyword` (1–80), `city` (可选，≤40), 同一 consent。
- 两者返回 `{items: [{id, name, address, label, distance_m: number|null}], suggested_id: string|null}`；最多 10 项，label ≤40 个 Unicode 字符。搜索不建议自动选择。
- 后端持有 `AMAP_WEB_SERVICE_KEY`；空值返回明确 503。固定 HTTPS 高德上游，不接任意 URL；GPS 显式转换为高德坐标；按用户限流、超时、结果边界。
- 请求走 JSON body；不保存坐标/搜索词/结果，不写 profile、DietRecord 或 Journey。认证用户 ID 只用于限流与脱敏审计，不发高德。失败不回传上游错误/URL/Key。
- 推荐仅供确认：accuracy ≤50m 且餐厅 ≤100m 才候选预填；定位过期（>2分钟）、缺精度、低精度（>200m）拒绝附近查询。近店不等于到店。

## Privacy / AI

无 AI。每次打开编辑器单独同意本次高德查询；拒绝可手填，无后台请求。前后台、会话、身份、草稿代次检查贯穿每个 await；网络 abort 与结果丢弃并用。前端不打印 Axios 错误对象；后端上游日志需屏蔽带 Key/坐标 URL。审计仅事件/状态/认证身份，不含内容。更新应用及公开隐私政策，发布前评估商店披露。无原生权限新增或迁移，但已有 iOS 权限用途文案只涵盖天气/城市足迹，须补充高德餐厅查询，因此有原生配置变更。

## Acceptance / Verification

先 RED 再 GREEN：未同意/拒权/过期/粗略定位/后台/超时/关闭与切账户/手改草稿/清空均不得迟到写回；历史餐食不自动定位；确认前不公开。服务端无认证/无同意/越界字段不发上游；GPS 转换、候选排序、错误脱敏、限流、无 Key 均测试。Composer 保留旧图回调防护。相关 pytest、Jest、tsc、lint、System Map、diff/秘密检查；真实高德联调需已配置 Key，模拟器视觉单列，mock 不冒充真机或联调。

## Rollout / Rollback / Open Questions

后端代理先配置并验证再开放客户端；无 Key fail closed，手填可用。本轮不自动发布。无需数据库迁移，回退到纯手填。待配置 Web 服务 Key、核对配额和商业许可，以及真实定位/隐私发布验收。更新的系统权限文案须新原生安装包，不可仅 OTA；API 方案不代表免除原生配置/隐私审核。

## Sources

- https://developer.amap.com/api/webservice/guide/api/convert
- https://developer.amap.com/api/webservice/guide/api/georegeo
- https://developer.amap.com/api/webservice/guide/api-advanced/search

## Changelog

2026-09-26：用户确认 API 接入；定义会话同意、候选与公开分离。
