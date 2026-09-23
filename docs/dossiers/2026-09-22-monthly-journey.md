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
- 2026-09-23 用户明确要求部署，并确认合并远端更新。以非改写历史的 merge
  `ac3eae1918012fdb3616951c0aa4361be01e03fb` 合入远端 `deb057795`；无冲突，
  本地足迹/后台 AI 源码保留，远端两个补剂版本名修复完整保留。
- 合并候选独立 `/root/merge_release_safety` G4 **GO**；独立 CI-mode
  342 passed / 5 PostgreSQL-only skipped。此裁决不是生产发布证明。
- 合并后主代理 CI-mode 505 passed / 17 skipped（`/tmp/reva-merge-release-ci.log`）；
  独占合成 PostgreSQL 215 passed / 0 skipped（`/tmp/reva-merge-postgres.log`），
  含足迹迁移/约束/并发、后台身份与补剂实际 Web 写入边界。
- Mobile 足迹/分享69、聊天62、原生配置18项通过；Mobile/Web tsc、API 类型
  一致性、System Map、141份 Dossier 一致性、秘密扫描及 diff 检查通过。
- 真实模型评测最初因本机默认配置文件不存在而失败；只从既有 `.env-online`
  向评测进程内存加载模型配置后，合成内存库重跑通过：离线62/62、真实模型5/5、
  轨迹21/21（`/tmp/reva-merge-live-configured.log`）。usage表缺失的测试旁路警告
  不代表生产计费验证；未加载生产数据库配置或输出凭据。
- 只读核对生产仍为 `deb057795`，backend/worker/beat 均 active，未发现业务
  release lease。服务器短期发布授权已过期且绑定旧 SHA，按部署治理暂停部署，
  已向用户请求单独授权轮换；未改权限、未触发生产发布或原生上传。
- 精确最终候选的远端 CI、发布预检及 G5/G6 仍待完成，不能用以上本地证据替代。
- 合并及验证记录已推送为 `ef79580f1`；真实 CI run `35807968268` **失败**。
  `release-invariants` 发现 async_helpers 新测试未进 shard catalog；两个后端
  分片发现 Coarse Location 未同步发布草稿及原生验收模板仍为1.3.3。
  依照发布硬闸暂停外部发布，不将此前本地绿灯当作全仓 CI 通过。
- 本地发布补全：新增 async 测试分片覆盖，补粗略位置类型映射及隐私草稿
  （关联用户、仅功能、不追踪），模板版号同步1.3.4，所有验收勾选保持 false。
  未修改 App Store Connect、未声称真机或新包验收完成。
- 增量 RED：6 failed / 76 passed；中间草稿重复 Location 类别被旧校验拒绝，
  合并为单类别并逐类型声明用途后，CI-mode **82 passed**，
  `/tmp/reva-release-repair-green-v2.log`。测试继续拒绝粗略位置追踪、用途及归属漂移；
  没有放宽原分片覆盖、隐私或发布闸。固定候选独立评审与远端重跑待完成。
- 固定补丁 `2fa78a545` 独立 `/root/release_metadata_safety` **GO**：
  69项 App Store CI-mode + 13项发布分片契约全部通过；未放宽闸门，未伪造验收。
  仅本地保存，远端 CI 仍是失败状态，已请求用户授权推送修复及更新短期发布授权。
- 用户追加要求“发布部署后解决”早餐估算失败，按顺序未抢先改饮食行为。
  只读排查：截图时间窗的一条脱敏 validator 日志缺少全部5项营养字段，
  与用户提示的拒绝原因一致，但尚未按 trace 绑定截图请求或证明上游根因。
  不导出原始饮食/聊天内容，不补录、不重放历史请求。后续应修估算输出/恢复链，
  保留不写空营养、不伪报成功的保护。
- 用户确认推送 CI 修复和轮换本次短期发布授权，`1e221b74e` 已推送。
  CI run `35818069994` 的 balanced-06 揭示另一处分片清单断言仍是旧值；
  本地先复现 1 failed / 20 passed，再同步 async 分片的精确断言。
  CI-mode 分片 runner、async context、发布与隐私契约合跑 **107 passed**
  （`/tmp/reva-shard-contract-green.log`），未删除覆盖或放宽判定。
  生产部署继续等待修正后精确 SHA 的真实 CI；尚未轮换授权或触发部署。
- 固定候选 `a1e39bbfab675ac7f52227b33d4673f7bc3ccf87` 独立
  `/root/release_assertion_review` 增量 **GO**，独立 CI-mode 107 passed。
  GitHub CI `35818623647` 全绿；Trusted release `35819557569`
  `target=validate` 成功，仅证明源码/CI 预检，不是部署回执。
- G5 阻断：服务器 canonical staging 的三次有界 HTTPS fetch 均以128退出
  （连接空响应/低速超时），独立只读 HTTPS 探测连接超时。保留
  `/var/lib/reva-release/bootstrap/a1e39bbfab675ac7f52227b33d4673f7bc3ccf87/source`
  的未完成 Git 现场；没有运行其中脚本，没有发布消费记录。
  未生成新私钥、未轮换授权、未设置 GitHub 发布 secret、未 dispatch backend。
  应先恢复服务器到 canonical GitHub 的连接，再核验 main/CI/干净源码并继续；
  不上传本机脚本、不使用镜像替代受审来源，不删除锁或旧发布证据。
- 早餐只读复现进一步确认：`记录早餐，喝了一碗小米粥。` 被拆成两个授权
  子句，合成完整营养参数仍遭 `health_record_authorization_target_unresolved`；
  去掉逗号或改成“吃了”则允许。截图时间窗内日志也显示营养补全后首轮
  被该授权拒绝，后轮才出现营养缺失；日志未独立按 trace 绑定，不能把时间
  相关性当成完整追踪证据。待发布后修复分句/后续错误呈现，未修改饮食行为。
- 用户要求继续部署后，服务器到 canonical GitHub/API 的 TLS 连通性恢复，
  在原 staging 成功 fetch 精确候选并核对三个发布脚本 SHA-256；未改 DNS、
  hosts、代理或 TLS 校验。独立服务器 CI gate 再次确认 run `35818623647`；
  本机 CI-mode 相关107项复跑通过（`/tmp/reva-resume-release-ci.log`）。
- 已按用户授权正常 rotate 旧 `42ba9fcc7` 至 `a1e39bbfa`，保留旧审计和锁，
  未使用事故恢复或历史消费重试。Trusted release **`35822757961` 成功**，
  仅 `target=backend`，服务端终态 `SUCCEEDED`，实际生产精确 SHA 为
  `a1e39bbfab675ac7f52227b33d4673f7bc3ccf87`。
- 后端验收：足迹 managed migration 已执行；三次健康度 **60/60**，三次
  runtime-only KB contract 通过，Skills manifest 同步通过；backend/worker/beat
  跨稳定窗口 PID 不变、NRestarts=0，业务 lease 已释放。真实公网
  `https://health.executor.life/api/v1/health` 返回200，足迹 `/api/v1/journey/month`
  未登录返回401。最初按旧 Skill 地址探测 `health-api.executor.life` 失败，
  后以 Mobile `services/api.ts` 的实际域名验证；不将旧地址失败误报为线上故障。
- 发布完成后精确撤销本次双发布授权、删除服务器 loopback 私钥和本机临时
  私钥，移除本次 GitHub `REVA_RELEASE_SSH_KEY`；保留既有 Expo token、
  known-hosts、旧发布审计和所有消费记录。未清锁、未重置审核账号。
- 此次仅后端 G5/G6 完成，不代表全部客户端发布：原生1.3.4扫码安装包、
  前端隐私页面发布与早餐业务修复仍未完成，未进行 OTA/TestFlight/商店上传。

### 2026-09-23 原生扫码包发布续办

- 用户要求继续发布；范围保持原生1.3.4扫码安装与隐私页，不擅自提交
  TestFlight 或 App Store。独立 `/root/native_qr_release_safety` 允许从
  canonical 干净 staging 进行 production profile 的私有本地构建；
  公网发布仍须 IPA 签名、权限、runtime/channel、摘要与公开文件白名单验收。
- 查明 local QR 脚本原来只读取 profile.env，漏掉 profile.channel，导致
  本地新包缺少生产 OTA 通道。修复为读取含继承的显式 channel，通过
  `REVA_LOCAL_UPDATES_CHANNEL` 写入 Expo requestHeaders，并在 app config
  拒绝与 variant/Rokid 能力不匹配的通道；不改变 EAS 自身的通道注入。
  profile 解析失败先阻断，不再由 eval 吞掉失败状态。
- RED：Mobile 通道测试6项失败，脚本通道测试1项失败，均命中原问题。
  GREEN：Mobile 足迹/分享/原生配置96项、脚本7项、Mobile TypeScript、
  System Map、秘密扫描通过；CI-mode 集成与发布契约已通过，精确远端
  revision CI 与固定增量安全复审仍须在公开发布前完成。
- 发布操作约束：不用原工作区的 `ios` 做 clean prebuild；不上传 archive、
  构建日志或环境文件；另用唯一 publish ID 装配已验证 IPA 和安装页面。
  development fallback 或 get-task-allow=true 一律阻断公开发布。
  真实设备安装、GPS、第三方接收仍未验证，不以既有模拟器证据冒充。
