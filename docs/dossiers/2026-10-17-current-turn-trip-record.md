# 本轮本人行程记录误拦修复

## 范围与状态

- 现有生活事件记录能力的局部修复；不增加产品对象、API、表结构或移动端行为。
- Router: `quick_fix` + `safety` overlay；发布阶段 `release/backend`。遵守用户禁用 superpowers 的要求，不加载其能力。
- 当前状态：本地实现和 PostgreSQL 验证通过；安全重审待完成；配置修正后真实模型闸已通过，最终候选需重新绑定验证，尚未推送或部署。
- 不回填截图中的真实行程；测试使用合成地点和隔离测试账号。

## 根因与改动

`记录我的行程` 被后置所有权语法当作非当前用户资料，导致分类为 unknown、无写入授权。原有简短 `记录行程` 仅支持前一条助手提议中的事件内容，无法把本轮明确提供的位置、计划目的地与路线绑定到工具载荷。

共享命令语法增加显式第一人称所有者。仅在完整授权检查通过且消息结构为“记录命令 + 我目前所在地点 + 可选计划/路线”时，从用户本轮文本生成标题和备注。保留计划措辞；模型自行添加的到达状态、时间、用户标识和备注不进入载荷。未知附加句不被静默丢弃。复用原有工具网关、回执和幂等身份投影。

## 证据

- RED：新增测试在修复前 3 failed / 14 passed，包含本人命令及真实工具网关不派发复现。
- GREEN：分类、共享写授权、工具网关、文本工具恢复四个测试文件，4,757 passed。
- PostgreSQL：独立临时测试数据库；`test_agent_trip_record.py` 11 passed。包含真实 `run_stream` → 工具网关 → HTTP 测试客户端 → 生活事件 API → PostgreSQL → assistant write_receipts；仅模型传输和 HTTP 网络传输使用测试替身，策略和持久化代码均未替换。
- 安全负例：否定、撤回、转述、假设、引用、其他所有者和问句均不派发；模型提供的其他用户 ID 被丢弃，落库归属认证用户。
- 截图原句本地无持久化探针通过；不把私人地点写入仓库。
- `PATH="$PWD/.venv/bin:$PATH" ./scripts/system-map-check.sh` 通过；该局部实现未改变生成图结构。
- `git diff --check` 通过。

## 独立安全审查与修复

- 首轮固定候选 `a790be24e`：独立 reviewer 裁定 NO-GO。宽地点字符集吞入括号示例/假设或句尾授权否认；授权规范化还会损失英文地点大小写及空格。
- 补充真实网关负例和保真测试，修复前 5 failed / 9 passed。修复后拒绝元语言限定词和括号，授权检查与原始事实投影分离；PostgreSQL 新文件 18 passed。待固定新提交重新独立审查。
- 完整 executor completion 状态回归 178 passed。
- 第二轮 `519de2e98` 仍 NO-GO：地点后的未知假定、转述、撤回附言可被吞入。新增 6 个失败网关用例后，改用正向有界实体终结词，匹配首次地理实体结尾，任何剩余附言均拒绝授权。支持口岸等设施、行政区/港岛目的地和桥路等路线；未覆盖的地名表达不自动授权。PostgreSQL 新文件 24 passed；截图原句无持久化探针仍通过。旧候选完整相关回归为 4,775 passed。

## 发布断点

`APP_ENV=test DATABASE_URL=sqlite:///:memory: python scripts/harness_llm_regression_gate.py --include-live-llm` 返回失败：离线 invariants 12/12、health_agent_core 50/50、trajectory contract 12/12、goldens 9/9 通过；真实 orchestrator 0/5。默认 provider 报 ValueError，OpenAI 备用路径被 `recipient_not_disclosed` 拦截。没有修改披露/同意配置，没有设置 confirmed 或 waiver 冒充通过。

已定位本地现有发布配置内的模型连接参数。只在进程内加载限定的模型参数用于合成评测，数据库强制保持隔离内存测试库，不输出凭据、不变更生产配置或披露规则。真实 orchestrator 5/5、平均 0.96，其余离线/trajectory 闸均通过；最终候选重新验证后再绑定确认。

需要完成真实模型闸，再绑定精确提交确认、推送并等待完整 CI；之后按受控后端发布流程执行。此变更没有 Mobile JS/原生差异，无需单独 OTA。生产路径与模拟器复验尚未完成。保留开工前全部其他任务的工作区改动。
