# Plan: 隔离发布执行器

关联需求：`docs/prd/2026-09-07-trusted-release-executor.md`。

## T1 · 守门

先补错误提交/CI/仓库/分页结果负例，再实现 stdlib 只读 gate。固定 API origin/repository/workflow；提交必须是 40 位十六进制并等于 workflow SHA 和 main；该 SHA 的所有匹配 CI run 的当前 attempt 均须成功终结，不能用更大的 run ID 掩盖旧 run 的新一轮失败重跑。请求超时与响应畸形失败，不静默回退旧成功。

## T2 · 执行

GitHub dispatch → 新托管 VM → 固定来源 fresh Git → env-i、Python -I 无凭据 gate → validate 终态或受保护生产 job → 再核 main/CI → 固定 target。

每个生产 job 使用独立新 VM；源、工具、私有运行目录分离，无外部可覆写命令参数，不复用缓存。后端增加精确 SHA verify-only 模式，保留现有 main/clean/远端 revision 检查，禁止隐式 push。输入凭据不从源码树读取；SSH 主机密钥固定，不用 ssh-keyscan 即信任、不关闭 StrictHostKeyChecking。

云端只持有八小时内到期、forced-command 且绑定 SHA 的专用 SSH 身份；服务端从 canonical GitHub fresh clone，调用原 deploy.sh。仅服务器持有独立的 127.0.0.1 限定 loopback 身份。安装器只能在固定 root staging 的受审源码路径执行，不上传本机脚本。后端启动和 TestFlight claim 均先持久化、再操作；未知结果保留证据，不自动重试构建或清除 lease。后端 STARTED/NEEDS_OPERATOR 不允许自动撤销其恢复所需 loopback 身份。成功后移除本次授权及云端 secret、撤销新建 Expo robot token，不影响个人密钥。

## T3 · 验证

本地 RED/GREEN、现有 release 合同、Dossier/System Map/秘密检查；独立 reviewer 读固定 commit。精确 CI 绿色后先触发 validate，保留执行来源和 CI run identity。没有可用受审最小权限发布凭据则记录 BLOCK，不把本地凭据扩散到云端。

## T4 · 条件发布

发布链 G4 和凭据准入均通过才能进入后端 deploy.sh -b。仍执行备份、恢复演练、站外加密、精确迁移/runtime/健康/回滚。后端终态确认后 EAS production + auto-submit，固定 CLI，核验版本、source SHA、EAS ID 与 Apple 处理状态。禁止 App Review 提交。

## T5 · 无手机 QA

仅 exact available Simulator UDID、同源 simulator 构建、本机合成测试图；验证冷启动、登录态/失败、附件/历史关闭、返回、饮食订单数量与分享复盘回跳。测试账号与日志脱敏，不删除原数据、不把账号密码写入 UI 测试产物。若发布被上游阻断，模拟器结果只能记本地开发验收，不记发布后验收。
