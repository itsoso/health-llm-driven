# Dossier: 主动开启的每日 GPS 行程

| 字段 | 值 |
|---|---|
| slug | daily-gps-journey |
| 创建日期 | 2026-10-18 |
| 当前阶段 | S5 实现 |
| 状态 | building |
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
- 裁决 PASS；用户“按你说的来”授权所述范围，GPS 不推断医疗结果。

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
