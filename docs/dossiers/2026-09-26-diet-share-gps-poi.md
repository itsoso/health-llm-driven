# 饮食分享 GPS 与高德地点候选

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

| 字段 | 值 |
|---|---|
| 状态 | implementing |
| 当前阶段 | S5 · 实现及本地验证完成，待配置联调与正式发布门禁 |
| Controller | product-pipeline，S5 delegate health-harness-orchestrator |
| Overlay | safety-gate |

Run: `docs/_generated/harness-runs/3470cb8e1ad1.jsonl`。外部 TDD/verification capability 未安装，遵循仓库 RED/GREEN 与新鲜验证规则；不启用已禁用的 superpowers。

## S0 · 需求与边界

用户原话：「默认选择gps定位的地址 要尽可能定位到精确地址 比如餐厅 引入高德api sdk」；方案确认：「api方案」。
目标：已有饮食分享减少手填地点；用户确认候选后才公开。成功：有同意和当日记录才查询当前 GPS，能选餐厅、搜索或手填，图文一致；失败可见。不做轨迹/常住地址/餐食数据写入，不新增原生 SDK。
基线 main `895f75426`。保留已有非本任务 `2026-09-23-frontend-publisher-recovery.md` 改动。

## S1 · 现状

- `mobile/components/diet/DietShareComposer.tsx`：已有确认/清除/重生成/会话隔离；输入框位于居中容器但未指定宽度，导致缩成文字宽度。
- `mobile/services/journey.ts`：Expo 前台定位可复用思路，但仅解析城市；不可复用写 profile/足迹的 API。
- `backend/app/services/location_resolver.py`：现有 profile 位置不是本次拍照地点，不复用其旧缓存。
- System Map 未索引精确路径，已回源码/测试，`system-map-check.sh` PASS。
- 无现有高德集成。官方 Web API 支持 GPS 坐标转换、逆编码、周边与关键字 POI 查询；来源见 spec。

## G1 · 准入

裁决：PASS。补齐 R5/R10 的饮食记录分享维护行为，对象 ExecutionEvent；仅会话内地点候选，不新增健康决策。

## G2 · 方案与安全压测

裁决：PASS（实现范围）。用户已选择 API。坐标仅在单次显式同意后经认证后端交给高德；不入库、不进入日志/错误/遥测。OS 权限不替代第三方同意。历史或未知日期不自动定位；只明确选择当前位置才允许。GPS 不能确定具体店铺，推荐必须标待确认，精度差/候选远不自动填入。Key 未配置可完成代码但不得声称真实联调/上线通过。

## 产出与 S4 任务

- [Spec](../specs/active/2026-09-26-diet-share-gps-poi.md)
- [PRD](../prd/2026-09-26-diet-share-gps-poi.md)
- [Plan](../plans/2026-09-26-diet-share-gps-poi.md)
- T1 后端认证代理/校验/限流/脱敏/测试；T2 Mobile service 与独立地点编辑器/生命周期测试；T3 Composer 接入与隐私文案/回归；T4 验证与安全审查。一个文件集一个 writer。

## G3 · 本地验证证据

- Mobile RED：先添加 service/editor 测试，因缺模块失败；撤回入口先失败再实现。零精度先证明被错误接受，再改为 `accuracy <= 0`；排队旧确认回调先证明导出旧地点，再加最新草稿校验。
- Backend RED：先添加代理测试，缺模块失败；对原始距离做推荐判断，避免 `100.004m` 展示取整后误推荐。
- 最终 `CI=1 scripts/run-all-tests.sh --mobile`：**316 suites / 3082 passed / 1 skipped**，TypeScript PASS。相关改动 ESLint PASS。
- 最终后端 CI-mode pytest：`tests/test_share_location.py tests/test_safe_access_log.py tests/test_sentry_status.py`，**51 passed / scoped coverage 96%**。环境 `DATABASE_URL=sqlite:///:memory:`、`TZ=Asia/Shanghai`；仅单元/无持久化代理验证，无新 DB 语义，未声称 PostgreSQL 验证。
- Mobile coverage 专项 3 suites / 51 tests PASS：新增编辑器行覆盖 95.83%，service 行覆盖 97.91%；含 Composer 原有导出代次防护。
- Frontend 隐私页 `tsc --noEmit -p .` 与 ESLint PASS。
- `system-map-check.sh`、治理检查、`git diff --check`、tracked/new-file 秘密扫描 PASS；代码派生 System Map 已同步。iOS/Expo 定位用途文案一致、后台定位仍关闭的静态检查 PASS。
- 后端 venv 无 ruff，未将其标通过。依赖、SDK 未新增。

## G4 · 预审与正式 Gate 边界

独立 `amap_privacy_review` 对工作树作只读预审，无确认的隐私阻断。指出零精度两端不一致与距离先取整问题，均补回归修复。检查了当前 pinned Sentry 的 POST body/交互标签行为；后端用内存 transport 测真实 HttpxIntegration，避免 Key/坐标进入 exporter 或 trace header。
稳定代码复查再次无预提交阻断；独立重跑 service/editor 2 suites / 25 tests PASS，同时核对权限用途与三处隐私声明一致。
**预审不是固定 commit 的正式 G4**。本轮未 commit/push/deploy；正式发布须固定候选提交后独立裁决，核对 exact-main CI，不得用工作树预审替代。

## G5 / G6 · 未发布与剩余项

1. 安全配置后端 `AMAP_WEB_SERVICE_KEY`（高德 Web 服务类型），同时确认 Redis 可用。Key 不放客户端、不放 `EXPO_PUBLIC_*`、不贴聊天、不提交 `.env`；只有 `.env.example` 新空项。
2. 真实高德 Key/配额/许可及真实 Redis Lua 未联调；当前 provider/Redis 结果为测试替身，不冒充生产验证。无 Key 或限流设施不可用时明确 503，手填仍可使用。
3. GPS 室内/商场多楼层的真实餐厅命中率、模拟器当前源码视觉/键盘尚未验收；未操作用户手机。
4. 现有 `NSLocationWhenInUseUsageDescription` 只含天气/城市足迹，已在 app.json 两处同步补充高德餐厅用途，ignored 本地 Info.plist 同步。**因此需新原生安装包，不能仅 OTA**；没有原生 SDK/权限新增。
5. App 与公开隐私页源码、商店披露草稿已同步，但网页尚未部署、ASC 未修改。上线前须核对真实披露/权限文案/安装包版本，后端先联调再开放客户端。
6. 本轮授权为实现 API 方案；未使用历史发布授权跳过上述门禁。未将本功能标 shipped。
