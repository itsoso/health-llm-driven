# 到家事件记录误拦修复

| 字段 | 值 |
|---|---|
| 创建日期 | 2026-10-17 |
| 当前阶段 | S7 后端发布与只读回查完成 |
| 状态 | shipped |
| 范围 | 本轮明确要求记录的本人到家事件 |

## G1 · 修复准入

- **裁决**：PASS。恢复既有生活事件记录，不新增产品对象、数据库结构或客户端契约。
- Router：quick_fix + safety overlay；局部 System Map 未索引，回查源码和邻近测试，完整地图检查通过。遵守用户禁用 superpowers 的要求。
- 只处理完整的“本人到家陈述 + 明确记录命令”，命令可以前置或后置。额外日期、医疗内容、读请求、否定、引用、转述、他人主体和未知附言不进入新授权路径。

## 根因与修复

- 原有当前行程投影只支持以“记录行程”等命令开头的有界地点报告，无法为“到家了。记录下来。”产生事件载荷；工具目标绑定拒绝后，通用提示误要求药物名称、剂量和单位。
- 新增共享的完整消息解析，分类为 event/create，并通过既有服务器授权投影、工具网关、认证 API、幂等身份和写回执完成记录。标题和备注来自当前用户陈述，丢弃模型生成的地点、时刻、用户 ID 与附言。
- 没有明确时刻时使用既有生活事件 API 的当前请求时间默认值，不从前文航班时刻推导；不把“到家”转换为家庭地址。
- 已识别行程的目标不匹配提示改为事件内容未对应，不再要求药物剂量；药物/补剂原有校验不放宽。
- 登机口＋航班时刻已有独立修复，本次原句无持久化解析检查通过；既有发布证据见 `2026-10-17-gate-time-context.md`，不将源码探针当设备会话验收。

## 验证进展

- RED：新增测试 7 failed / 43 passed，复现事实投影、前置命令分类、真实流式写入及错误提示。
- 首轮 GREEN：50 passed。追加实际 API 读取隔离、重复 client_turn_id、历史失败会话、持久化回执与无借用时刻断言；修正新增测试对既有时间默认值和认证 fixture 的误用后，5 个流式场景通过。
- PostgreSQL 扩展回归、相邻分类/授权/执行器回归、真实模型 gate 和独立安全审查进行中，未宣称发布完成。
- System Map 与 tracked-secret 扫描通过；生产账户未回填事件，未操作真机。

## 固定候选验证

- 候选 `2d17fba5544ea3aadcb4604ac95a6907a5d2662f`；独立代码安全审查 **GO**，独立 SQLite 50 passed。额外探针确认同一到家指令无法授权 medication、supplement、illness、symptom、diet、reminder、sleep，仅 event 派发。
- PostgreSQL 首轮扩展 237 项中 232 passed / 5 failed，失败均来自新增测试误把既有 API 默认精度断言为 inferred。修正时间断言和测试 token fixture 后，本任务两文件完整 **50 passed**，覆盖真实 stream→gateway→API→PostgreSQL→回执、跨账号读取和 client_turn_id 重放去重。另 187 项相邻 PostgreSQL 测试在首轮已通过。
- 相邻分类、授权、fast routing、补剂澄清和 completion 回归：3,786 passed / 11 skipped / 1 failed。失败是既有饮食 `<1.5s` 性能断言；未修改基线 `ebe376c13` 在同机 Node 22 也复现（1.90s）。当前候选串行复验仍超阈值，未改测试或放宽阈值。新增非到家解析 10,000 次探针 P50 0.92µs / P95 1.00µs；不能将此探针冒充完整性能通过。随后同候选完整 Linux CI 通过，该测试 JUnit 为 0.631 秒，0 failures/errors/skipped。保留本机失败结果，不修改断言。
- 真实模型评测：invariants 12/12、health_agent_core 50/50、orchestrator **5/5，平均 0.98**、trajectory 12/12、goldens 9/9。首次缺模型配置失败后，仅在进程内加载现有模型连接参数，强制内存测试库及真实合成同意主体，不改变生产数据或披露边界。
- PostgreSQL 停止命令等待超时，保留原关闭操作；原进程完成检查点后正常退出，无重启或强杀。
- 发布 transport 首轮 NO-GO：包装器没有显式要求候选等于当前 main。四阶段补 `--observed-main SHA` 后重审 **GO**；保留 canonical 完整 gate、原锁、回执、撤权与 no-backup 轮换。四个批准版本随后各执行一次，均 exit 0，未重放或重试。

## 交付边界

- 开工前工作树已有食物识别 benchmark、多个 Dossier 和发布回执改动，均保留，仅暂存本任务文件。
- 仅后端改动，无 Mobile 运行时代码变化，不需要空 OTA。精确 CI、生产部署和源码只读检查已完成；设备 UI 与真实账号完整会话未验证。


## 最终发布与验收

- [完整 CI 39043236856](https://github.com/itsoso/health-llm-driven/actions/runs/39043236856)：精确候选 SHA，32 jobs success。该候选包含的到家测试与饮食性能测试所在分片均成功。
- 干净候选的本机 CI-mode：3,953 passed、84 subtests passed、23 平台/环境限定 skips；JUnit 4,060 项无失败或错误，Dossier 检查及测试均 exit 0。Mac 结果不代替 Linux 隔离校验，Linux 对应完整 CI 已通过。
- [后端发布 39044651127](https://github.com/itsoso/health-llm-driven/actions/runs/39044651127)：success。服务器 `SUCCEEDED`、runtime `COMMITTED`、干净生产 SHA 与候选一致，业务 lease 已释放；backend/worker/beat 均 active/running、NRestarts=0。
- 公开健康接口 HTTP 200，API/database/Redis/Celery 健康。已部署源码 13 项解析、意图和拒绝误写探针通过；仅加载部署代码执行纯函数，不连接生产数据库，不回填用户事件，也不冒充生产账户会话或设备验收。
- 仅后端变化，保留现有 OTA，无需安装新 App；本次未发布空 OTA、未创建备份或执行恢复演练。
- 结构化证据：`docs/reviews/2026-10-17-home-arrival-release-receipt.json`。后续证据提交仅修改文档和回执，不改变已部署运行代码。
