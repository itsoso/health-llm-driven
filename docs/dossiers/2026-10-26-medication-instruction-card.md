# 用药查询指令误生成记录卡修复

| 字段 | 值 |
|---|---|
| 状态 | shipped |
| 当前阶段 | G6 后端/OTA 回执核验；设备更新应用未观察 |

## G1 需求准入

裁决: PASS。用户 22:57 截图中，查询指令被当作药名，以 90% 置信度展示用药草稿并提供记录入口；“问小巴”进一步把该指令嵌入无日期的查询，形成错误循环。

- 分类：既有通知/用药记录链路缺陷修复；不新增用药行为或读取授权。
- 本轮事实：查询说明不是药品，不是服药事实；明确“不要记录”不可作为 intake。
- 最小范围：共享摄入分类器拒绝查询指令；历史投影及移动端缓存不展示指令药名草稿或其操作；保留正常药名/剂量/明确摄入。
- 非目标：推断查询日期、放宽 owner/时间范围、删除历史消息或用药数据、批量服药、修改药物方案。
- 成功条件：截图原文及衍生查询不生成草稿；旧卡片无可执行入口；本人/精确日期读取和显式写入确认守卫不变。

## G2 实现边界

沿用当前只读提醒详情及查询范围契约。分类器的 subject 分类仍识别药物主题，避免错误转入饮食记录；record 分类及 quick-record 正则回退必须拒绝非摄入指令。历史处理仅 deepcopy 后投影，绝不更新/清理原始数据库记录。

## 验证证据

- RED：后端 6 failed / 212 passed；移动端缓存卡片 2 failed。覆盖完整提醒查询、截图卡片标题、衍生问句、禁止记录和历史卡片。
- 初轮 GREEN：后端 320 passed；移动端 113 passed。包含真实用药正例、只读精确范围、账号隔离、卡片持久化/历史投影及现有用药页面。
- System Map selector 未索引；已检查源码及邻近测试，`system-map-check.sh` passed。
- 当前无 schema/DB 行为更改，无真实健康数据读写或模型调用；新增投影测试为纯内存，不能声称生产数据库或设备验收。
- 本节为发布前历史验证记录；最终状态见下方 G4–G6。

## G4 第一轮审查修正

独立审查 NO-GO：`查一下`、药名本身作为查询对象的语句仍生成草稿，且句首“检查结果正常”可能压掉后续真实摄入。新增测试先得到 5 failed，再将读指令限定为首分句、复用药物词汇识别查询对象；补齐历史/缓存投影同类回归。读写授权保持原样。

## G4 最终独立安全审查

裁决: GO。固定候选 `3dd357f9067ad57a938973e3cdb80c6ade503ede`，累计 diff 从 `9e3cf5def` 起。独立 backend 228 passed，mobile registry 109 passed，额外 10 项合成探针通过；没有新增 owner/date 授权，历史只读投影不改变存储记录。

本轮相关后端回归 506 passed，最终新增历史变体的定向回归 228 passed；移动端 117 passed，TypeScript、ESLint、System Map、档案一致性检查通过。路径敏感 live-model gate 判定无需真实模型，不将合成测试冒充真实模型验收。

## G5 发布

裁决: PASS。

- 精确候选完整 [CI 40346287287](https://github.com/itsoso/health-llm-driven/actions/runs/40346287287) 成功，含 PostgreSQL、Mobile 和类型漂移检查；Linux CI-mode 发布集成 4710 passed / 47 skipped / 127 subtests passed。
- [后端 validate 40349263970](https://github.com/itsoso/health-llm-driven/actions/runs/40349263970)、[后端发布 40349448930](https://github.com/itsoso/health-llm-driven/actions/runs/40349448930) 成功。
- [OTA validate 40350611247](https://github.com/itsoso/health-llm-driven/actions/runs/40350611247)、[OTA publish 40351152172](https://github.com/itsoso/health-llm-driven/actions/runs/40351152172) 成功。group `afd20f4f-6bea-43b0-9a37-561df8116e7c`，update `01a178e0-cfb1-7969-be62-08cd3ed4e433`。
- 沿用既有权限续期只读 GitHub App 凭据并经独立审查，canonical 发布授权轮换后单次执行；无备份、回退副本或恢复演练。

## G6 发布后核验

裁决: PASS。2026-10-26 23:43 Asia/Shanghai 只读核验生产 SHA 为上述候选，backend SUCCEEDED、runtime COMMITTED/finalized/code-only-no-backup、OTA SUCCEEDED；三个后端服务 active，业务租约已释放。公网 health 200，未登录用药提醒 GET 401。

完整证据见 [发布回执](../reviews/2026-10-26-medication-instruction-release-receipt.json)。没有读取真实健康数据、修改历史记录或执行真实服药写入。用户设备下载/应用 OTA 和原生通知实际点击未观察；新行为由分类、持久化投影、缓存组件及范围约束回归证明，不宣称设备已更新。重新打开历史会话可获取服务器过滤结果；本地缓存防护须应用本次 OTA。
