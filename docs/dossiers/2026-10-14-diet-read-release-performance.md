# 饮食读取与 OTA 发布性能优化

- 日期：2026-10-14
- Controller：Health Harness；overlay：safety-gate。
- 前序修复：`9e600c269721d83c9ede255113dce237a2ffdfb8` 已完成后端及 OTA 发布。
- 用户授权：完成后继续优化性能，自动部署及 OTA；不备份、不做真实模型评测。
- 状态：G3 验证中，尚未发布本轮候选。

## 范围与验收

1. 饮食列表及日汇总的四条认证读取路径统一预载照片关系，消除每餐一次的隐式读取。保持用户隔离、照片顺序、签名 URL、空值及响应契约。
2. OTA 凭据步骤与 publisher 准入之间删除相邻重复的完整 CI 查询；保留首次准入、publisher 准入及导出后的重新验证。不降低额度阈值，不缓存跨操作证明，不改变单次发布约束。
3. 不改模型、提示词、原生配置和营养估算算法；不把数据库优化宣称为模型推理加速。

## 基线与验证计划

- 在隔离 PostgreSQL 上对同一组合成数据、同一真实 HTTP 端点重复请求，比较修复前后 SQL 数量及 HTTP/SQL 分段 P50/P95/P99。它证明读取路径收益，不代表真实用户或生产长尾。
- SQL 预算测试先失败后修复；覆盖四条读取路径、外部用户隔离、多照片顺序与空列表。
- OTA 调用预算和 SHA/main/CI attempt 漂移测试必须通过；候选独立 G4 后才推送。
- 运行项目 CI-mode 集成闸与目标 main 精确 SHA 完整 CI；同 SHA 后端部署后执行 trusted OTA validate、publish 并核对终态回执及健康状态。
- 任一契约、隔离、CI 或发布证据失败即停止对应发布步骤并修复；不跳过检查或重复领取未知状态的操作。

## 所有权与证据

- `diet_edit_fresh_review`：`backend/app/api/diet.py`、`backend/tests/test_diet_photo_query_budget.py`。
- `closure_fresh_safety`：`.github/workflows/trusted-ota.yml` 及相邻发布测试。
- 主会话：本 Dossier、整体验证、提交、安全复核和发布收口。其他会话 WIP 保留。
- Trace：`c21c37b7264e`。
- System Map baseline：`/tmp/reva-performance-map-baseline.log`，检查通过。
- 发布历史只读性能诊断发现重复源码/状态校验；本批不引入跨文件历史缓存，另行设计身份与结束复核后再评估。

## G3 增量证据

- OTA 预算：RED 2 失败、12 通过；修复后相关套件 413 通过、1 项既有 Linux ACL 环境跳过。每次 validate/publish 的 runner 完整 CI GET 从 20 减为 15，两轮合计 40 减为 30。服务端配额闸不变；真实验证器注入 main、SHA、attempt 漂移，claim/vendor 前拒绝。
- 饮食初测：SQLite 相邻 191 通过，独立 PostgreSQL 10 通过且停库成功。四端点各 20 次、3 餐 6 照的冷 Session HTTP 请求，饮食/照片 SELECT 均从 4 减为 2；空列表 1、跨用户拒绝 0。SQL 段 P50 下降，但 HTTP P50 未下降，不据此宣称整页或照片识别延迟改善。追加历史列表样本验证中。
- LLM change gate：`live_llm_required=false`、`confirmed=false`、`waived=false`。本轮无真实模型调用及评测。
- System Map、tracked-file 高置信秘密检查、diff 检查通过；新增文件在提交前再次扫描。
- 发布使用 backend-deploy adapter 和当前部署规范；adapter 中旧备份条款由用户不备份要求及现行规范覆盖。
- 追加历史列表：同一合成 30 餐/60 照、20 次冷 Session HTTP 请求，`user-list`/`me-list` SELECT 从 31 降为 2。两端点 HTTP P50 分别 9.51→5.66ms、9.65→5.69ms，P95 分别 10.14→6.64ms、9.93→6.82ms；数据库段 P50 1.85→0.32ms、2.01→0.34ms。仅为本地 PostgreSQL 样本，不代表生产网络或模型耗时。
- 追加基线先 8 个预算 RED、8 个隔离/空列表 PASS；原函数由固定 Git blob 摘要绑定、仅在隔离测试进程替换四个只读 GET 函数体，共享 API 源码未往返修改。最初测试适配器未命中新版路由的环境错误保留，不算功能 RED。
- 正常授权轮换沿用已受审成功路径，固定旧模板哈希，保留 launcher/build 双锁和 OTA 历史验证。清理步骤不重复联网 CI；rotate 由 canonical 实现执行完整精确 CI，去掉外层重复调用。最终执行字节另行独立复核。
