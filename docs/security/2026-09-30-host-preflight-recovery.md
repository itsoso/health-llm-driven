# 已发布版本的主机加固前置失败恢复

生产应用版本 `051ee281f8247d162bcdef7b3f93fdf51930c94c` 已有后端和 Web 成功回执。
原主机加固在完成配置与防火墙备份后，因受限 PATH 无法解析 `useradd` 中止；未创建
`health-web` 账户/组。原失败记录不变，不能重新运行原 apply 或删除租约。

修复固定使用 `/usr/sbin/useradd` 和 `/usr/sbin/ufw`，普通加固在创建审计/租约前
检查命令及 UFW。恢复仅支持上述固定生产版本，新发布器必须为独立 G4 GO、当前
main、精确 CI 绿色的 canonical root staging。完整 Git tree 差异仅可涉及恢复器、
对应测试和本文档。并发合入的 OTA bootstrap、对应测试及 share dossier 仅允许
`4ee35ac33f5554153575f7605cb62ddfa504311d` 中已独立审查的精确 mode/type/blob，
不是路径级豁免；任何字节/模式变动或未知文件删除均拒绝。持久网络策略函数和端口常量必须相同，不 checkout 生产应用。

入口为该新 staging 的 `deploy.sh --security-hardening --sha <生产版本>
--resume-preflight --publisher-sha <新发布器> --lease-token-stdin`。原租约 token
仅通过服务器内受保护 stdin 提供。默认只读取证；同一 `--evidence-sha256` 才执行。

必须证明账户和组均不存在、固定九项配置写集与原 tar/manifest 字节和权限一致、
原本缺失配置仍缺失、没有新 unit/临时文件、缓存仍 root 所有、密钥元数据库存不变、
PM2 及后端/ETH 进程身份早于原尝试且稳定。只忽略防火墙快照的生成时间注释和
内建链包/字节计数，所有链、策略、顺序与规则保持精确一致。现有后端沙箱、实际
注册策略与原前端制品回执也要通过。密钥内容不读取、不复制，不重启 ETH 服务。

持有原 launcher/build 锁与原 business lease，独立
`host-hardening-recoveries/<生产版本>/intent.json` 持久化后，再完整复证才执行
原加固的备份后阶段；该阶段输出到新 `apply/`，不污染原备份/失败审计。
前端由 root PM2 切到 `health-web` systemd，安装账户级 IPv4/IPv6 隔离、关闭公网
监控端口，并将已盘点 keystore 权限收紧。失败保留 intent，禁止重跑。

完成前核验实际前端 UID、后端/ETH 进程身份及原审计/备份/lease 不变；四个原租约
文件持久归档后，以同文件系统 no-clobber 移动原目录，核验原 inode 并 fsync。
独立 `RECOVERED_LOCAL_VERIFIED` 不覆盖原失败记录；未来发布必须重新验证完整
恢复历史和内层证据。外网回读及实际服务命名空间的隔离验证仍为独立验收要求。

这不开放自主注册，不构成共享内核上的质押资产绝对安全证明。开放公众注册前仍须
完成应用与质押独立主机隔离，以及注册风险策略的独立验收。

## 登录事故优先恢复

生产 PyJWT 2.14.0 的目录/文件受安装 umask 077 影响，实际 health-app 用户只能
导入空 namespace，带 Bearer 的认证触发 AttributeError 返回 500。包版本和 RECORD
字节正确并不能证明运行账户可用。独立 `--repair-runtime-permissions` 与主机恢复
互斥，仍通过同一 canonical 新 main、独立 G4、完整 CI、原锁及 digest 校验。

源码范围同时纳入本事故的 deploy/rollback 安装权限修复、锁定依赖运行身份验证及
对应回归文件，均须同一固定提交审查；不允许应用业务代码或网络策略变化。

该入口仅允许固定 051 上的 PyJWT 2.14.0：校验 wheel 源码 SHA256、完整原 RECORD、
确切目录/文件库存、root 元数据及 inode。先保存权限前镜像 intent，再只将已验证
源码和包元数据设为只读可访问；root 归属和全部文件字节不变，生成的字节码缓存
保持 0700/0600。以清空补充组后的真实 health-app 身份验证来源、版本、合成 JWT
正常签验、错误签名与过期拒绝，不读取生产密钥。

正常发布与回滚的运行身份检查读取 RECORD 中运行必需的成员；仅豁免当前解释器
标准命名、无 hash/size、且同一 RECORD 有对应可读源码的生成缓存。缺失/不可读
源码、独立 pyc、未知缓存名和路径越界仍失败；真实 JWT 签验仍必须通过。

只重启 health-backend、celery-worker、celery-beat，等待覆盖服务停止/启动时间，
核验新进程 UID/cgroup/命令身份连续、稳定运行及 health 中 DB/Redis/Celery 连接。
无效 Bearer 的 /auth/me 必须返回 401，重定向不作为成功。ETH 进程身份逐项不变，
原主机加固 audit/backup/lease 保留。独立完成凭据才允许后续主机恢复使用这三个
新业务 PID；质押仍要求原进程。失败保留 intent 且禁止重跑，不伪造历史成功。

## 监控入口的独立验收修复

原主机加固已返回本地成功，但外部验收发现 9090 仍可访问：UFW 命令退出成功
没有证明实际 INPUT 的规则顺序。旧回执保留，不能当成外部封禁成功。

新 canonical `--repair-monitor-ingress --sha <051> --publisher-sha <新 main>`
默认只读取证，绑定完整 CI/G4、56eec9 主机恢复历史、服务身份和双栈完整规则。
指定同一 `--evidence-sha256` 后才创建独立 intent 与新 business lease。
固定变更仅涉及 `/etc/ufw/before.rules`、`before6.rules` 中相应 before-input
链的第一条非 loopback TCP 9090/9100 DROP，以及两个对应实时插入规则。
该位置早于 ESTABLISHED，保持 loopback 本机监控可用；不重载 UFW、不重启服务。

原配置完整字节和权限、双栈规则保存在私有 intent；变更后必须证明精确两条
新增规则、其他规则投影不变、持久化字节等于固定插入、原历史和全部服务进程不变。
失败保留 intent 与 lease，不重放、不覆盖旧成功。完成后独立回执与租约归档，
未来 bootstrap 必须验证此完整历史。外部新连接验收仍为最后一道闸。
