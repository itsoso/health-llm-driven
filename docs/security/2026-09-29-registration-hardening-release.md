# 注册与质押宿主机隔离修复发布

本次发布保留邀请制：`AUTH_PHONE_SELF_REGISTRATION_ENABLED=false`、
`REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=true`、
`REGISTRATION_INVITATION_ROLLOUT_ENABLED=true`。这是现有 ECS 的风险收敛，
不是开放自主注册的许可，也不声称任何防护能保证没有机器人。

## 实现与发布边界

- OTP 开发回显在生产配置层和投递层均拒绝；CalDAV URL 拒绝非全球地址、
  IPv4-mapped 私网、CGNAT 与空 DNS 结果。DNS 重绑定等应用层残余风险由本机
  UID 出站边界补充约束，不宣称所有公网重定向风险已消除。
- API 使用同一个 limiter，生产 Redis 共享计数，存储异常失败关闭；付费
  短信调用前以 Redis Lua 原子预留全局、手机号、IP、重发冷却配额。手机号
  和 IP 用 HMAC 派生 key，失败的供应商调用也消耗预算。默认滚动 24 小时
  全局 500、每手机号 5，IP 每小时 20；不是人机挑战替代品。
- 生产 installer 进入 hash lock，精确移除不在 lock 的残留分发包；PDF
  导入回退复用已锁定 PyMuPDF。先安装完整 lock，再清理，再验证 lock 与
  `pip check`；任何一步失败不得写成功 marker 或重启为新版本。
- backend/worker/beat 隐藏质押数据路径、拒绝元数据网段并限制 CPU、内存。
  前端先以备用端口验证 dedicated `health-web` systemd，再从准确匹配的
  PM2 进程切换；只读制品、专用缓存、无 capabilities。失败保留锁和审计。
- 固定 UID 的 IPv4/IPv6 OUTPUT 规则拒绝非必要本机端口和内网；允许服务
  对已建立入站连接的 REPLY，不允许既有任意出站连接借此绕过。检查完整
  规则序列及 OUTPUT 首部，不 flush、盲改或重新排序未知链。
- 只对已盘点 keystore 改 0600，不读取、归档或移动密钥；不启动或重启
  validator/beacon/执行客户端。仅关闭公网 9090/9100，保留 ETH P2P。

## 执行顺序

1. 最终 main 精确 SHA CI 全绿，独立固定提交 safety-gate GO。
2. 通过可信发布 workflow 的 backend target 执行 canonical `deploy.sh -b`；
   publisher 生成显式邀请制候选 env。确认 backend SUCCEEDED 与实际进程。
3. 在 root canonical staging 使用现有 `--rebuild-deployed-frontend`，
   publisher/production 都绑定最终 SHA。后端已经更新整仓，因此其同树门
   仍保持成立；隔离构建新前端并完成页面验证、双制品替换与独立成功回执。
4. 同一 canonical staging 执行 `deploy.sh --security-hardening --sha <SHA>`。
   入口在环境加载之前固定调用系统 Python `-I -S -B`；复用 canonical
   source、fresh CI、backend 成功回执与 revision 证明，持有 launcher flock
   和 business lease。前端成功/安装/verified 回执以及实盘组合 digest 必须
   匹配最终 SHA；未知历史、缓存代码、漂移或已有 lease 一律阻断。
5. 完整配置写集先压缩备份，记录不存在的对象，逐文件 SHA 回读并 fsync；
   原密钥只保存路径/权限元数据。确认实际 sandbox 和进程环境后记独立
   `LOCAL_VERIFIED`，不覆盖 backend 成功回执。公网闭口检查仍需从外部执行。
6. 联合验收服务、老用户入口、邀请策略、实际 UID 到质押/metadata 的隔离、
   密钥不可读、9090/9100 外部拒绝、真实生产包扫描、ETH 进程持续运行。
   Mobile OTA 由协调任务另行执行并验收，不以 backend 成功替代。

已加固后的普通前端构建/重启不得自动退回 root PM2；无法确认运行身份时
必须失败。未知执行结果保留所有 lease、回执与备份，禁止删除锁、换 SHA
重放或伪造终态。

## 验证记录

- 实际 Redis 并发配额、手机号/IP 轮换、冷却、存储失败和付费供应商前拒绝
  测试已执行；最终整合集计随固定提交评审记录更新。
- 在 ECS 上新建独立 network namespace 验证 IPv4/IPv6 请求回复、数据库
  访问、质押端口拒绝、合成 metadata 地址拒绝以及规则前置绕过拒绝：
  `NATIVE_IPV4_IPV6_REPLY_DENY_ORDER_PASS`。未改生产网络。
- 最终 hash lock 的在线 pip-audit：无已知漏洞。上线后必须对实际已安装
  环境再扫描，不能从锁文件结果推断生产已清理。
- 本文编写时尚未完成生产切换，不把本地验证当成线上结果。

## 开放注册剩余边界

ECS 仍有其他 root Web 服务，未审计它们的全部代码；共享内核也没有物理
隔离。应把公网应用迁往独立实例，保留现有 validator 单实例，不复制验证
密钥启动第二个实例。新 ECS 尚无目标信息；本次不创建收费资源。
自主注册继续关闭，未来开放需补服务端人机挑战、实际隔离和滥用处置验收。
