# Dossier: 主动开启的每日 GPS 行程

| 字段 | 值 |
|---|---|
| slug | daily-gps-journey |
| 创建日期 | 2026-10-18 |
| 当前阶段 | S6 验证 / G4 复核 |
| 状态 | validating |
| 负责 | Codex / 用户 |
| 反馈环 | PostgreSQL / Mobile tests / iOS 模拟器 / 原生扫码包 / backend |

## S0 用户需求
> 能否实时获取我的gps信息 记录和分析我一天的行程？
> 按你说的来

- 本人自动记录与复盘全天出行，减少手动地点输入；现仅单次定位/城市标注，无法连续复盘。
- 用户批准前轮明确方案（主动开启、暂停/删除、路线/停留/每日复盘、缺口展示、新原生包），无需重复要求实现授权；真实位置收集在 App 内单独主动开启。

## S1 现状
- mobile/services/location.ts：单次定位；services/backgroundLocationTask.ts：尽力城市刷新。
- services/journey.ts 与 backend/app/models/journey_place.py：确认后的城市标注，不保存精确历史。
- liveRun/backgroundLocation.ts：已有任务但仅内存事件，权限返回值不可靠，不复用为全天采集基础。
- app.config.ts 与 plugins/withIosSupportedOrientations.js 双重剥离后台权限，需要原生变更；旧二进制不允许靠 OTA 开启。
- System Map 局部未索引，已读源码/邻近测试；上一分析阶段完整地图闸通过。

## G1 准入
- first_class_objects: ExecutionEvent / HealthTwin evidence；core_loop_step: execution -> review。
- target_surface: Mobile；safety_level: privacy_sensitive；autonomy_tier: manual_confirm（每次有截止时间的 session）。
- 最小切片：开启 -> GPS -> 结束 -> 只读复盘 -> 删除；保留既有城市标注。
- 裁决: PASS；用户“按你说的来”授权所述范围，GPS 不推断医疗结果。

## S2/S3
- PRD: ../prd/2026-10-18-daily-gps-journey.md
- Spec: ../specs/2026-10-18-daily-gps-journey.md
- Plan: ../plans/2026-10-18-daily-gps-journey.md
- 工作流 trace: ../_generated/harness-runs/5766363127c5.jsonl

## G2
- 独立只读 feasibility reviewer 裁决可行性 GO（不是上线安全 GO）。原生权限、账号切换、离线加密、日界线、后台不保证、删除不复活已纳入合同。
- 待拍板：无新增范围分叉；默认 7 天，可选 1 天；不自动每天重启。

## S4/S5
- Backend / Mobile capture / UI-native 独立分解；父流程负责共享接线和最终状态。
- main 工作；开工前已检查 dirty tree 和开放 PR，保护既有 benchmark、Dossier、release receipt 改动。

## G3/G4/G5/G6
- 均待验证，未部署、未安装、未读取用户 GPS；不宣称 shipped。

- G2 约束补充：系统休眠时无法保证午夜即时关闭硬件，数据截止由服务端/客户端时间闸保证，任务在下一次回调或前台停止。SecureStore 必须支持锁屏、分块有界、安装身份验证；标准原生审核闸拒绝后台权限，需保留禁项并按实际候选能力绑定受审例外。G2 PASS，所有约束进入实现验收。

## S5 增量证据（待固定候选复核）
- 后端 UTF8 PostgreSQL：40 passed；验证迁移重放、状态/上传/删除并发、账号级联、严格加密、损坏密文仍可删除、到期清理、分段复盘与保守交通方式估计。
- Mobile 全量首轮：367 suites passed；采集服务两项当时新增 RED 已在后续切片修复。采集/存储 42 tests passed，原生配置 70 tests passed；最终稳定候选仍须复验。
- 早期独立审查曾裁决 NO-GO：本机索引先删导致孤立密文、午夜覆盖待删除、旧队列被新开启覆盖、延迟午夜批次丢失。修复含持久清理标记、删除优先、未同步队列保护及严格采样时间过滤，尚待固定 SHA 的 G4。
- 补齐后端和 Mobile 精确位置遥测出口屏蔽。后台凭据权限仅在显式开启后扩大；恢复标记不包含 Token，记录缺失时可恢复前台访问等级。账号删除申请停止采集的集成正在验证。
- 发布实际阻断：现有 no-backup code-only 发布拒绝新增模型/managed migration。正在实现仅绑定本次新增表的受审迁移分支，不能绕过检查，也未恢复备份。
- 未部署、未分发原生包、未读取用户 GPS；硬件锁屏连续性与电量未验证。

## G3 稳定功能候选
- 本地提交：`d1780551d17f3314cf401b91c4846c826fe07c5d`；未 push。
- Mobile：368 suites passed，3847 tests passed，1 skipped；TypeScript 无错误。
- 后端 CI=true 集成切片：41 passed；新增 API / service 覆盖率 94.53%。首次覆盖命令继承全仓 `--cov=app` 导致 19.84% 阈值失败；随后明确目标模块重新运行并通过，不将切片覆盖率称作全仓覆盖。
- PostgreSQL 40 passed；API 两端生成校验、System Map、秘密扫描通过。真实 LLM 闸裁定本次无需真实模型评测（不把 GPS 送模型）。
- 固定候选独立 G4 已发起；发布 helper 和隐私说明补充将形成后续候选，需再验证。
- CUA 明确因 Mac 锁屏拒绝模拟器操作；未用替代 UI 通道绕过，无视觉通过结论。已请求用户解锁 Mac，其他工作继续。

## G4 首轮固定候选裁决与补充
- `d1780551d17f3314cf401b91c4846c826fe07c5d` 独立裁决 NO-GO：首次开启请求超时后重试沿用原 intent，用户更改 7→1 天时仍可能确认 7 天；正在补双向参数变化回归并保留原幂等保护。固定候选中的两端旧隐私政策还否认后台采集，也构成阻断。
- 隐私声明修正提交 `8253fc89b`：Mobile/Web 页面与隐私标签草稿区分城市足迹和每日 GPS，明确保留与删除边界；两端新增 4 项渲染回归、现有 3 项隐私对齐检查通过。没有更新 App Store Connect。
- 受控无备份新增表发布支持提交 `6a345e6ec`，仅准入本次固定模型/SQL 摘要；专用单测及真实 PostgreSQL 56 passed，既有部署回归 231 passed。已提交另一位未参与实现的 reviewer 独立检查，未执行生产迁移。
- CI 显式 PostgreSQL 分片已加入新 API/数据库测试，release-invariants 及独立 PostgreSQL step 已覆盖迁移 helper；这些配置仍待最终候选真实 CI。
- 生产 GitHub relay 只读检查 enabled/active、IPv6 loopback、canonical TLS Git 查询通过；远端 main 仍为 `25b85536e3722dc111c528b8a915062a3f971397`。未推送、未发布新能力。

## G4 修复后裁决
- 功能与隐私候选 `bf89865ed174ab2882bfbc9819f4dbae063eb58f` 独立复核 GO：原期限与幂等键绑定，改变期限在权限和凭据调整前明确拒绝；原期限恢复、删除后新期限开启、冷启动及 UI 恢复通过。独立 Mobile 64 passed、Web 2 passed；实现者相关切片 62 passed，TypeScript 通过。
- 发布 adapter `6a345e6ec29057c43dbf22a0683c1bcbd9591e43` 独立复核 GO：新鲜 helper/真实 PostgreSQL/runner 63 passed、3 skipped（跳过为 runner 额外 Redis 环境项，GPS PG 6 项均运行）；既有部署回归 215 passed。不是生产迁移成功证明。
- 最终功能候选两端 TypeScript、秘密扫描通过；新增隐私测试带来的生成地图变化已重新生成并通过完整 System Map 校验。最终 Mobile 全量测试与精确主干 CI 待完成；G5/G6 仍未通过。
- 原生扫码构建计划为 1.3.6 (289)：本地回执与公开 manifest 可证前一个 QR build 为 288。已安装 ad-hoc profile 有效，公开 latest 是旧实体目录，因此只发布唯一版本目录并使用 `--no-latest`；不替换旧目录。未预留或上传 Apple 构建。

## 2026-10-29 Store capability containment

App Review rejected unrelated Store build 283 under Guideline 2.5.4 because it
declared persistent background location while this feature was still validating
and had no physical-device background acceptance. The standard production
binary now fails closed with daily journey disabled, even if an internal flag is
present. Only a separately requested non-Store development or preview iOS build
carrying `REVA_DAILY_JOURNEY_ENABLED=1` may restore the native mode;
that build still requires this Dossier's remaining G4-G6, privacy and real-device
evidence before Store submission. This containment does not delete the feature
implementation or promote it to shipped.
