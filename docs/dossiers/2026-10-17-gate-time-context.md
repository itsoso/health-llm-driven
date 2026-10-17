# 登机口和航班时间续聊误入健康查询修复

| 字段 | 值 |
|---|---|
| 创建日期 | 2026-10-17 |
| 当前阶段 | S7 后端发布与回读完成 |
| 状态 | shipped |
| 范围 | 普通行程进展的非写入上下文承接 |

## G1 · 修复准入

- **裁决**: PASS。恢复既有行程背景能力，不新增健康对象、数据库结构、写权限或航班查询服务。
- 本轮为 quick_fix + safety overlay；System Map 局部文件未索引，回到源码与邻近测试，完整地图检查通过。禁用的 superpowers 技能未加载。

## 根因与修复

- 旧上下文解析只允许城市及固定设施词，遗漏带数字的登机口和时间；这类纯陈述进入模型路径，无关健康读取被拒绝后展示查询失败文案。
- 增加完整匹配的登机口与可选航班时刻语法，只接受有效 24 小时时钟和降落/落地/起飞事件；时间只是用户陈述，不推断已降落、日期、时区或航班实际状态。
- 连续对话校验将登机口回复绑定认证用户此前解析出的完整陈述，不用任意助手前缀放行。现有医疗续问、待确认动作、附件、重试、账号隔离仍优先。
- 普通陈述只保存到当前对话，不新增健康事件，不声称已记录行程；明确记录请求继续走既有写入路径。

## 验证进展

- RED：修正测试导入后，8 failed / 21 passed，复现登机口解析和连续对话失败。
- GREEN：首轮相关回归 197 passed；后续增加不推断航班状态、重试去重和跨用户拒绝覆盖。
- 本机 System Map 入口初次因 PATH 没有 python3.12 失败，使用仓库 .venv PATH 后完整检查通过。
- PostgreSQL、独立安全 review、精确 SHA 完整 CI 与发布验证已完成，证据见下。
- 后端运行代码变化，无 Mobile 运行代码改动，不发布空 OTA；未写入用户生产行程或操作真实设备。

## 发布与验收

- 发布 SHA `e75b182637ea6ca658a18e35368774ccb83c9322`；独立安全审查 **GO**，139 项独立回归和 3 条合法/14 条拒绝探针通过。截图原句在部署源码解析探针中通过，不将其等同于真实账号或设备会话验收。
- PostgreSQL 相关完整回归 **199 passed**：实际对话保存与连续承接、重试去重、账号隔离、健康事件不新增及原有写路径均通过。测试库停止时 pg_ctl 等待超时，原关闭操作随后完成检查点并正常退出；没有重启或强杀数据库。
- 本机 CI-mode **3,953 passed、84 subtests passed、23 环境/平台限定 skips**；JUnit 4,060 项无失败/错误，干净候选 checkout；Dossier 一致性与测试均退出 0。本机结果不冒充 Linux 隔离验收，对应云端完整检查通过。
- [完整 CI 39038027218](https://github.com/itsoso/health-llm-driven/actions/runs/39038027218)：精确 SHA，32 jobs success。机器判定 live_llm_required=false，未使用确认变量或豁免；本次正常路径是确定性回复，测试禁止模型和工具调用。
- 固定四份 transport 脚本经独立 **GO** 后单次执行。rotate 的 SSH 连接退出 255，保留原失败传输结果；服务器原日志 `INSTALLED` 与退休 `RETIRED` 已完成。另经独立审查的纯只读脚本绑定原锁 fd/inode、候选与旧密钥退役回执、受限双身份、源码/执行器及生产状态，exit 0 后确认 `AUTHORIZED_NEW_SHA_READBACK`，未重放 rotate 或任何 mutation。
- [后端发布 39040820061](https://github.com/itsoso/health-llm-driven/actions/runs/39040820061)：success；服务器 `SUCCEEDED`，runtime `COMMITTED`，生产干净 SHA 一致，租约释放，backend/worker/beat active/running 且 NRestarts=0。
- 公开健康接口 HTTP 200，API/database/Redis/Celery 健康；已部署源码 7 项解析、非写入意图、用户原句回复与医疗/提醒/非法时间拒绝检查通过，不写用户生产记录。
- 仅后端变化，保留已有 `8711e424` OTA，无需安装新 App。未声称通过设备 UI 或生产账户完整会话验收。
- 结构化回执：`docs/reviews/2026-10-17-gate-time-context-release-receipt.json`。
