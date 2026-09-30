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
