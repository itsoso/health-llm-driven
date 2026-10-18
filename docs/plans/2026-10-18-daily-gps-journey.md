# 每日 GPS 行程实施计划

唯一状态记录：../dossiers/2026-10-18-daily-gps-journey.md；合同：../specs/2026-10-18-daily-gps-journey.md。

1. Backend：独立 Session/Point 模型、严格加密、成对 managed migration、所有者认证 API、状态 CAS/幂等、到期清理与确定性复盘；先 RED，再实现，真实 PostgreSQL 验证。
2. Mobile 采集：独立 task 与安全离线队列、session owner/credential generation 固定、每次显式开始、权限/注册失败不得假成功、暂停/结束/登出/过期停止；先测试。
3. Mobile 页面及原生：现有 journey 入口、状态控制、私有路线分段和停止点、记录列表/修正/删除；原生 Always/location mode 配置只绑定新构建，旧包拒绝开始；新 runtime，原生配置测试与生成 plist 检验。
4. 集成：契约生成、系统地图、全相关测试、PG 迁移与并发；固定本地提交后独立 G4；NO-GO 回到实现，不 push。
5. Release：精确 main 全绿、无备份发布授权、后端健康/迁移、原生扫码安装包。此前未下发的返回按钮包含在新包，不将旧 OTA 准备当发布。模拟器界面验收；硬件/电量/全天连续性单列未验证。

共享文件（main.py、models/__init__、Celery、app.config、auth、generated types/map）由父流程串行集成；子任务不提交/推送/发布。直接 main 工作服从 AGENTS，不创建未要求分支或 worktree。
