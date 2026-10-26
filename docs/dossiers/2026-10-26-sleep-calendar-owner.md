# 睡眠查询日期前置误判本人归属

| 字段 | 值 |
|---|---|
| slug | sleep-calendar-owner |
| 状态 | parked |
| 当前阶段 | 等待主干整合与发布交接，未部署 |
| 反馈环 | backend |

## G1 准入

裁决：PASS。恢复已有本人睡眠查询的正确语序识别；保持账号、日期及写入边界，不新增产品能力。

- 请求：截图“分析上周我的睡眠情况”收到“只能查询当前登录用户本人的记录”。
- 状态：本地修复，发布 BLOCK；未宣称线上生效。
- 准入：既有本人睡眠读取行为的纠错，不新增产品行为、健康写入、数据源、接口或迁移。
- Router：quick_fix + safety overlay；System Map 按需查询未索引该内部模块，已回源码及邻近测试调查，完整 system-map-check 通过。未使用 superpowers。

## 根因与修复

`health_semantics._is_current_user_scope_owner()` 只认可本人在日期前的语序，把“上周我”当作外部归属；截图原句通过 shared owner check 返回 nonself，gateway 拒绝为 health_query_subject_not_current_user。本地基线的该源码与读回生产 SHA `1f14f9c0a73facc511daafa3a7aa8e447ee62fd0` 一致。

提交 `a10f87f9d` 增加完整匹配的有限日历前缀 + 本人所有者。未复用过去/近的任意字符匹配，避免吞掉第三方姓名；具体日期有效性、身份、工具、维度、时区、取消和写授权继续由原有 gate 决定。固定合成时钟 2026-10-26 Asia/Shanghai，截图原句绑定 2026-10-19 至 2026-10-25，非滚动近七天。

## 验证

- RED：截图原句及同类语序原始测试 8 failed / 22 passed（`/tmp/reva-sleep-owner-red.log`）。
- 测试范围校正：初始额外“我本人”成功预期触发现存独立日期范围解析不支持；不为本次修复扩展该语法，保留截图“我”及既有“本人”端到端断言。初轮宽回归的失败证据保留在 `/tmp/reva-sleep-owner-regression.log`，不冒充通过。
- 最终定向 SQLite：34 passed（`/tmp/reva-sleep-owner-final.log`）。
- 独立临时 PostgreSQL：34 passed；测试库已停止（`/tmp/reva-sleep-owner-pg.log`、`/tmp/reva-sleep-owner-pg-result.json`）。
- 实际 Pi / gateway / 查询适配器读取合成 GarminData，仅模型与时钟模拟。覆盖上周首尾日、同日期其他用户、上周前及本周记录；仅返回本人范围内两条记录，数据库指纹不变、无 write_receipts。
- 反例：第三方与并列主体、撤销/条件/引用请求、无效日期、未支持筛选、模型注入 owner/user/tenant、日期/时区/维度扩张、身份不一致、写操作均拒绝。
- System Map：PASS（`/tmp/reva-sleep-owner-system-map.log`）。
- 最终六文件回归：1399 passed / 12 skipped / exit 0，变更模块语句覆盖率 90%（`/tmp/reva-sleep-owner-regression-final.log`、`/tmp/reva-sleep-coverage-final.json`）；跳过项为原有测试。
- 独立 G4：`sleep_owner_safety` 对固定 `a10f87f9d6d3a07185e109fdacc7bead82f4d4f4` 判定 code safety GO；独立重跑 33 项非 DB 测试全部通过，并探测并列/第三方主体、控制字符、batch 根及嵌套 owner ID、引用/取消、无效日期、更窄筛选、窗口/时区及主体不匹配，均未发现放行。PostgreSQL 为 producer 执行并由 reviewer 读证，不冒充独立重跑。发布仍 BLOCK。
- 无真实健康记录读取；无真实模型评测、模拟器/线上用户对话验收；不得把合成 provider 结果称作真实模型完成。

## 发布边界

2026-10-26 只读核对：remote main `cf080ee99e90aba46879c282bec891a10882c2fc`，CI 40264280549 success。其绿色不能代替本修复候选 CI。开工本地有记事本任务三个未推送提交；fetch 后本地与远端分叉，另有大量其他任务 dirty files，均保留。

生产仍为 `1f14f9c0a73facc511daafa3a7aa8e447ee62fd0`，backend / worker / beat active，health HTTP 200。这仅证明旧版健康，不证明本修复生效。

遵守 AGENTS.md §7“分支分叉……停止外部写入并报告”：未 push、merge 或 deploy，未替其他发布者领取操作，未创建备份。记事本 Dossier 亦记录待操作者停止交接。后续需主干整合及交接明确、精确候选完整 CI、CI-mode、安全 GO、原发布锁/回执/授权均满足后经 deploy.sh 上线。本次仅后端解析修复，无独立 Mobile OTA 制品。
