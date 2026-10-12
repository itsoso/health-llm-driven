# Garmin 同步状态不能把未完成显示为成功

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 本地验证与 G4 文件预审 |

primary controller: health-harness-orchestrator；overlay: safety-gate、add-managed-migration。

## G1 准入
裁决：PASS。用户提供设置页 Garmin “刚刚同步”截图，指出实际未同步好。本任务修复状态真实性，不据截图断言其个人数据已成功同步。
- 目标：同步异常或时间异常不得显示绿色成功；历史成功时间不能掩盖最新运动导入失败。
- 边界：不修改认证授权、不触发真实账号同步、不新增健康数据读取或删除数据，不绕过统一发布 owner。

## G2 调查与方案
裁决：PASS。
- credential-status 在 error_count 尚未达到三次且 recent last_sync_at 存在时，即使 last_error 非空也可能返回 healthy。
- 未来同步时间被压成零分钟；Mobile 再把负分钟压成零并显示“刚刚同步”。旧测试明确把八小时未来时间当作 healthy，此行为错误。
- Celery 运动导入返回部分失败已有持久标记，但抛异常路径只 retry，未保存未完成标记。上次成功时间仍会驱动绿色 UI。
- 修复：最近错误优先 stale；超过一分钟的未来时间返回 stale、未知分钟和脱敏说明；Celery workout 异常 rollback 后保存既有 activity partial 标记再保持原重试；设置页防御旧版 healthy+last_error 和负时间，优先异常文案及警示色。
- 无新增 API 字段/schema。last_sync_at 仍保留历史值，不冒充本轮成功；明确同步完成后才恢复既有状态。

## G3 验证
- 新后端三行为和 Mobile 三情形先失败。初轮后端从仓库根运行另有源码相对路径错误；改用 backend 工作目录后验证。
- SQLite：credential-status、Celery、scheduler/safety 相邻 36 passed。
- PostgreSQL、Mobile 两套、TypeScript 与独立文件预审进行中。
- System Map 检查通过；无结构生成变化。未修改他人发布工具或收据。

## 发布边界
代码未提交未部署。统一 owner 仍为线程 01a120c7-1ba0-75c3-9487-447bd5bfa28f；本线程不暂存、commit、push、deploy 或 OTA。
尚未核验截图对应账号线上请求/任务日志，不能声称本次个人运动数据已补齐。上线前仍需固定 SHA G4、所需完整 CI、后端与 OTA 分别成功及用户路径验证。
- 第一轮真实 PostgreSQL 36 passed（42.94s）；Mobile 设置与 Garmin 连接页 57 passed，tsc --noEmit exit0。
- 独立六文件预审 GO，非固定 SHA G4；reviewer 独立设置页49通过，自己的后端环境因默认5432无PG未启动，不将其算测试证据。
- 按审查建议增加实际SQL异常使PostgreSQL事务进入失败态的测试，验证rollback后marker确实持久且API stale；最终37项PG运行中。根目录初次运行的源码相对路径失败与错误工作目录重试均未计通过。
- 最终真实 PostgreSQL 37 passed（50.73s，/tmp/reva-garmin-status-final-pg.log），包含实际失败事务回滚恢复与状态持久化验证；测试服务器正在正常停止。没有触发生产同步或改变发布候选。

## 2026-10-12 新截图：时间异常与同步等待状态

用户 10:17 截图显示“同步时间异常”且按钮为“同步中…”。截图本身不能证明请求卡死，也不能确定未来时间来源；尚未核实该用户数据是否补齐。已请统一 owner 仅核对线上列类型、连接时区与 UTC 时钟元数据，不请求凭证或用户健康正文、不触发生产同步。

本地源码与 RED 证据确认：
- 连接页在同步 POST 完成后仍等待其他健康查询刷新，继续显示同步中；刷新失败走同步错误提示。新增只读“刷新连接状态”入口，sync 期间可读状态但不重放 POST；区分“正在刷新同步结果”，刷新失败单独说明请求已完成、需核实结果。
- 页面遇到 healthy 与 last_error/负分钟矛盾时不报绿；保持现有未来时间异常告警，不修改历史值。
- Celery 定时派发将未来时间当作近期同步而跳过；naive UTC 又被赋予中国时区。统一 naive UTC，仅 −1 分钟至 90 分钟内跳过，未来异常重新进入原受控派发路径。未改筛选、授权、任务锁、写入字段或 schema。

验证：页面先 3 RED，后增加只读 refetch isError 反例；Mobile 连接页/设置/service 共 67 PASS，tsc PASS。后台新 6 参数真实 task 分支先 2 RED/4 PASS，随后 sync/credential-status/safety 共 SQLite 43 PASS、独立临时 PostgreSQL 43 PASS（/tmp/reva-garmin-recovery-pg.log）；前两次测试环境缺 pytest/sqlalchemy 的启动失败不计 RED。System Map 官方检查与 diff-check PASS。独立 reviewer garmin_recovery_review 文件预审 GO，独立页面 12 PASS，后台未独立重跑；非固定 SHA G4。

仍未提交、完整候选 CI、部署或 OTA；未做本次模拟器与真实 Garmin 账号验收。此增量修复可复现的恢复/显示问题，不将其称为截图时间来源已查清。测试 PG 已正常停止（server stopped），pytest 退出码 0。

## 统一发布 owner：生产元数据与受控迁移

2026-10-12 只读核对生产元数据：`garmin_credentials.last_sync_at` 实际为 `timestamp without time zone`，应用配置连接时区为 `Asia/Shanghai`；数据库与主机 UTC 时钟一致。未读取用户记录或凭证，未触发生产同步。该组合的隐式转换机制可在 PostgreSQL 复现，但不能据元数据推断截图账号某条历史记录的原始写入来源。

新增 managed 迁移 `20261012_110000_garmin_sync_timestamp_timezone`，将列恢复为 ORM 已声明的 `TIMESTAMPTZ`。转换显式使用 UTC，保留现有 API 对旧 naive 值的解释，不猜测并减去历史八小时偏移；成功的后续自然同步会写入正确的 aware instant。已正确列无操作；缺失或不支持的列类型失败关闭。DDL 锁等待最多 5 秒、语句最多 30 秒，不能带迁移失败继续部署。

SQLite 镜像仅保留兼容性；生产时区语义由 PostgreSQL 验证。接口字段和客户端类型不增加，`last_sync_at` 的 ISO 字符串由无偏移变为带偏移，表示的旧 UTC instant 保持一致；不宣称字符串逐字不变。连接页展示依据服务端分钟字段。

回滚优先回滚应用并保留兼容的 aware 列。手工 down 文件将 aware instant 显式转换为 naive UTC；必须保留原迁移 ledger，后续再次 forward 需新审查的迁移 ID，不能删除生产 ledger 重放。

RED：旧列的真实 PostgreSQL 八小时偏移已复现；两方言新迁移行为测试在实现前失败。GREEN：最终临时 PostgreSQL 47 PASS，涵盖旧值/空值、重复应用、已正确列、UTC/上海两种连接时区、真实 credential-status 接口读数、新 aware 写入与 down/forward 往返；临时服务器正常停止。Mobile 连接页/service 17 PASS、设置页 50 PASS，TypeScript exit 0、System Map 官方检查 PASS。未运行真实模型评测。

本节替代此前“无 schema 变化”的本次增量说明；未提交、固定 SHA G4、完整 CI、后端迁移与新移动包发布仍待完成。已发布 1.3.5（278）只包含此前模型权限等改动，不能作为本次 Garmin 交付证据。模拟器未登录真实 Garmin，个人数据补齐和实际设备安装仍未验证。
