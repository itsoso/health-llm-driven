# Dossier: 小巴健康 · 这一路

| 字段 | 值 |
|---|---|
| slug | `monthly-journey` |
| 创建日期 | 2026-09-22 |
| 当前阶段 | G4 · 本地候选复核，等待统一发布 |
| 状态 | building |
| 负责 | Codex / 用户 |
| 反馈环 | 本地 iOS Simulator；发布暂缓 |

## S0 · 用户需求（逐字）

> 我突然发现，可以加个定位功能，然后每周还是每个月来个 酷炫的啥轨迹总结，对于你们这些商务人士的情绪价值是不是很有满足感

> 做吧

> 1

最后的“1”明确选择完整版，接受更新原生用途说明和后续新安装包。

用户确认的首版 framing：记录时可选地点 + 月度足迹回顾 + 可选择内容的
分享长图；默认不采集全天后台位置，不把足迹点连线冒充真实路线。
服务经常出差、已有照片/饮食/生活记录的人，以低负担回顾行程与自我照顾。
目前用户只能翻阅分散记录。周报、动画视频和后台追踪不是首版承诺。

## S1 · Discovery

- 基线：`ff52113da`，main 干净、领先 origin/main 5 项已完成后端修复提交。
- 开放 PR 已检查；未发现直接覆盖足迹功能的 PR。发布流水线 PR #252
  涉及 release 权限与流程，发布前需重新核对，不修改其范围。
- Router：feature + safety；Product Pipeline controller；System Map 按需。
- `backend/app/api/episodes.py:257` 已有生活事件创建/删除/最近时间线；
  `backend/app/models/episode.py:90` 的 context_snapshot 可承载事件上下文。
  目前返回 title/time/notes，没有结构化地点、照片关联或自然月回顾契约。
  `backend/tests/test_life_events.py:211` 验证读路、用户隔离与时间精度。
- `backend/app/models/daily_health.py:147` 饮食已有独立记录与 photo_assets；
  没有地点字段。不可把地点塞入营养原始结果，或为贴地点重复写饮食记录。
- `mobile/services/location.ts:61` 的 updateGPSLocation 更新当前 profile，
  不可用于历史足迹写入；`reverseGeocodeOnDevice` 可作候选能力，失败必须
  呈现未知/手动填写，不能把天气城市或 IP 估计当作历史到访证据。
- `mobile/app.json:33` 与 `:216` 的定位用途只说明天气、空气质量；
  expo-location 虽已内置，新增保存足迹用途仍需同步原生文案和新安装包。
  当前 Always 与 iOS background location 均关闭，本功能保持关闭。
- 分享可复用 `mobile/components/diet/DietShareComposer.tsx` 的预览/导出/
  临时文件清理模式，`mobile/components/chat/ConversationShareImage.tsx`
  的固定宽度、内容自适应高度与图片加载完成条件。现有组件含饮食/聊天
  语义，不直接整卡复用为足迹图。复用认证图片读取，不能生成公开源图 URL。
- 月度时间线须按明确用户时区和自然月边界，不用最近 30 天冒充月份；
  分页/数量上限须告知，不能静默截断后宣称完整。
- 只读 Mobile discovery 使用现有 Python runtime 修正 PATH 后运行
  `./scripts/system-map-check.sh`，通过；不是新功能测试或发布验证。
- Mobile reader `/root/journey_mobile_discovery` 已完成：
  `mobile/utils/share.ts:270` 提供微信/小红书 shareLongImage；
  `mobile/utils/share.ts:335` 保护源图本地化并清理；邻近 share.test 与
  DietShareComposer / ConversationShareImage 测试可复用失败/取消/乱序基线。
  `mobile/utils/imageUpload.ts:18` 预处理不保留 EXIF 地点/时间，不得伪造。

## G1 · 准入

```yaml
RequirementAdmission:
  request: 可选记录地点及月度足迹回顾与分享
  classification: new_product_behavior
  first_user_fit: 经常出差且已有生活与饮食记录的高强度工作者
  core_loop_step: Capture -> ExecutionEvent 上下文 -> 月度 Review
  first_class_objects: [ExecutionEvent, HealthTwin]
  target_surface: Mobile
  source_of_truth: 后端当前认证用户所属原始记录与显式确认地点
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 用户确认地点、原记录发生时间、用户所选照片
  claim_hedging: 不编造路线、距离、健康改善或心情
  verification_window: 自然月；试用一个月评估回顾价值
  success_metric: 用户能核对更正足迹、选择分享内容并愿意下月继续使用
  added_user_burden: 可选添加地点与分享前预览；不强制每日打卡
  burden_justification: 用户明确希望回看出差和自我照顾片段
  non_goals: [全天追踪, 自动公开, 商旅排名, 后台推送, 视频动画, 周报]
  smallest_end_to_end_slice: 单条记录确认城市 -> 月度足迹 -> 勾选片段 -> 长图预览导出
  stale_surface_to_remove_or_archive: 无；复用记录源，不另建平行日记
  spec_required: yes
```

- 产品准入建议 PASS：以记录事件的地点上下文支持月度 Review，而非社交
  排名或里程竞赛；只做情绪化里程图不足以替代健康复盘目标。
- 隐私默认：不存连续精确轨迹；分享只含用户选择的城市和照片；默认不带
  原始自由文本、住址、酒店、精确时间和健康指标，照片自身隐私须预览提示。
- 用户已确认首版 framing；**新增明确分叉**：一次定位 + 手动城市需要更新
  原生用途说明并安装新版，或先做手动城市版保留 OTA 能力。尚未替用户选。
- **裁决：PASS。** 用户选择 1，关闭原生安装包 vs 手动先行分叉，进入定义环。

## S2 / S3 · 定义产物

- PRD：`docs/prd/2026-09-22-monthly-journey.md`
- 行为/API/安全真源：`docs/specs/active/2026-09-22-monthly-journey.md`
- 实施：`docs/plans/2026-09-22-monthly-journey.md`
- 数据方案为三种源记录的地点注释，不复制健康事实；新增表需迁移。
- Router 增加 `database` overlay（canonical skill add-managed-migration），
  严格加密城市、源/账号删除、版本并发必须 PostgreSQL 验证。

## G2 · 可行性与安全

- 独立只读 `/root/journey_g2_review` 正在检查方案与既有源契约；未进 S5。
- 用户已确认核心边界；仅在出现新的实质范围/风险分叉时再请求决定。
- 首轮 **NO-GO**：旧 URL refresh 不提供归属校验；导出仅 ID 不能防预览后
  内容/照片变动。已回 S2/S3 修订：明确 agent_messages、规范私有图片白名单、
  不可证明图片显式 unavailable；export-preview 绑定版本与稳定选图 key，
  服务端白名单投影，客户端实际保存/分享前再次预检；待独立复核。
- 修订后同一独立 reviewer **裁决：GO。** 已关闭两项阻断，无新产品分叉。
  图片按既有不可变私有上传路径识别，原位替换假设须测试，不是上线证明。
- 确定性 G2 出口：全仓 141 Dossier 自洽；System Map 全闸通过。

## S4 / S5 · 任务与委托

- Fetch 到 `d31ab9cef`，远端未新增；开放 PR 已复查无同域覆盖。
- 契约：`_workspace/monthly-journey-contract.md` 引用 feature spec §§5–7。
- Ledger：`docs/_generated/harness-runs/c360e5703680.jsonl`（本地，不提交）。
- Product Pipeline 委托同一 run 的 Health Harness；外部 karpathy/TDD/verification
  技能未安装，遵循 AGENTS 的最小变更、RED/GREEN 与新鲜验证，不启用 superpowers。
- T1 Backend agent：三源注释、版本/加密/迁移/CRUD/export projection/tests。
- T2 Mobile agent：月度入口、地点编辑、图片选择、分享/清理/tests。
- T3 Main：native 权限测试与文案、生成类型、集成/PG/模拟器可用性与 G4。
- 保持 shared main，文件职责互斥，delegate 不 commit/push/deploy。
- Native RED：原文案/runtime 缺口 3 failed/15 passed；城市隐私清单补充 RED
  1 failed/17 passed。更新权限用途、生活照片/足迹成品文案；候选版本 1.3.4
  维持 appVersion runtime，隔离旧 1.3.3 原生用途与本轮 JS。
- 补充非精确位置隐私清单，字段核对 Apple 官方
  https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacycollecteddatatypes/nsprivacycollecteddatatype
  ；仅声明功能用途且不 tracking。商店隐私标签须发布前同步，本轮未改线上元数据。
- Mobile 与 Web 隐私政策同步用途/控制方式（Web 无新业务面）。
- 独立 PG：`/tmp/reva-journey-pg.B4WF3N`、127.0.0.1:55493，合成测试库，
  不连接生产。主代理提供给 T1；避免多个测试进程并发重建同一库。

## G3 / G4

- 初期全仓 `check_dossier_consistency.py` exit 1：此前
  `2026-09-22-background-ai-identity.md` 缺可解析阶段/状态与 G1 段。
  报错未指向本档案；不能宣称全仓一致性通过，进入交付前需处理该既存文档闸。
- 已仅补先前后台身份档案的表头/G1 机器可解析格式，历史验证/发布结论不变。
- Backend runnable RED 13；软删除照片旧封面回退及图片 URL 跨端契约另有
  独立 RED 后修复。图片返回 canonical owner path，由 Bearer 鉴权读取，
  不再给此功能生成 capability URL；真实图片 endpoint 本人/匿名/他人测试通过。
- G3 当前：CI-mode 集成 `/tmp/reva-journey-ci-final.log`，163 passed、
  10 PG-only skipped、exit 0；初次命令引用了不存在的测试路径，collection
  exit 4，纠正路径后完整重跑，不将初次当功能 RED。
- 独立 PostgreSQL `/tmp/reva-journey-backend-postgres-current.log`：61 passed，
  零 skip；包括并发 CAS、重复创建、约束、加密、源/owner cascade、迁移回放。
  迁移测试账本残留曾失败，已限定本测试 migration ID 清理后完整重跑。
- Mobile `/tmp/reva-journey-mobile-tests-final.log`：54 passed；
  `/tmp/reva-journey-chat-regression-final.log`：62 passed；native config 18 passed。
  Mobile/Web tsc 通过；变更文件 lint 零 error（Mobile 测试 import 等 21 warnings）。
- 两端 API 类型已生成；System Map/mobile-nav/doc-drift 校验通过。
- iOS 1.3.4 preview 原生模拟器包编译成功；权限用途已核对实际 Info.plist。
  模拟器视觉验收仍在进行，未以组件 mock 冒充真实端到端通过。
- 按 safety-gate 固定本地候选后独立 G4；未推送或部署。
- 固定候选 `626487c94` 独立 `/root/journey_safety_review` **GO**：重跑
  Mobile 54、SQLite 51 passed/10 PG-only skipped，核对 PG61 证据。
  不是上线裁决；真实 GPS/第三方接收/旧账号完整删除流程不由本轮证明。
- 主代理 iPhone 17 Pro Simulator 使用独立 preview bundle + 本机 PostgreSQL
  合成账号，真实登录、月度读取、三片段白名单长图预览及饮食源手动城市
  保存通过；没有连接生产个人记录。未签名包最初缺 Keychain entitlement，
  已重新用 simulator ad-hoc signing 构建成功，真实登录和重启恢复通过。
- 视觉验收捕获主页面顶部安全区缺失（月份进入状态栏），补显式顶部
  safe area 和返回栏，先2 RED后 Mobile56 GREEN。编辑/导出 Modal 各自增加
  SafeAreaProvider，先2 RED后58 GREEN；真实编辑页复验标题不再遮挡，历史
  日期禁用“当前位置”，取消返回正常。
- 实际 PNG 揭示 view-shot iOS 单宽度会忽略缩放、按屏幕倍率输出；基于
  当前 iOS/Android native 源码增加两尺寸等比换算与真实像素高度上限。
  iOS 除 PixelRatio，Android 原生取像素；2x/3x/非法密度/边界先 RED 后 GREEN。
  导出按钮移到说明后，避免长图必须滚到底；最终相关 **69 passed**，
  `/tmp/reva-journey-exportactions-green.log`，Mobile tsc exit 0。
- 最终原生模拟器导出：`/tmp/reva-journey-ui.ZidkUU/journey-export-720-final.png`，
  sips 及目检 **720×1524**、无文字拉伸/额外顶部空白，城市/日期/类型齐全，
  不含私有记录标题；系统分享面板收到 PNG（113 KB）。已取消，未发往第三方。
  关闭系统分享后 app tmpfile 消失，保留的合成证据副本在本机 /tmp。
- 已验证边界：真实本机 API + PG + 独立 preview 登录/恢复/读取/手动确认/
  预览/原生截图/系统交接；未验证真实 GPS、HTTPS 照片原生下载与有图成品、
  Android 设备、相册保存、微信/小红书接收端。API 图片鉴权与组件加载/失败
  测试不能冒充这些真实环境通过；统一发布前另行补齐或按治理记录风险接受。
- 最终固定修正 `a96de8b6e` 相对 `626487c94` 独立增量 G4 **GO**，
  reviewer 重跑27项通过，并目检最终 PNG；原安全裁决持续有效。
  最终 System Map、diff、两端 API 类型一致性、Dossier 与秘密扫描通过。
- 已停止本次独立 preview 进程、Metro、本机合成 API 和 PostgreSQL；
  `pg_ctl status` 确认 no server running，测试库/合成截图只保留在本机 /tmp。

## G5 / G6 · 发布与验证

- 未发布。遵循用户“全部解决之后再部署和发布”，本功能不单独绕过发布条件。
