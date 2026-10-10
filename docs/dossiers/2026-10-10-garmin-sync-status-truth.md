# Garmin 同步状态不能把未完成显示为成功

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 本地验证与 G4 文件预审 |

primary controller: health-harness-orchestrator；overlay: safety-gate。

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
