# 发布授权历史校验的 I/O 优化

更新：2026-10-10。本文描述当前候选实现及其边界；尚无新版生产封存、线上性能对照或新部署/OTA 成功回执。

## 操作与基线

`bootstrap_trusted_release.py rotate` 在部署前为新源码 revision 轮换受限发布授权。它核验旧操作终态、授权撤销、原锁、历史 Web/OTA 回执及备份制品；检查失败仍阻断轮换。这不是后端部署已完成的证据。

原始会话进程 90431 的 08:00 采样：`rchar=6680793629`、`read_bytes=8016338944`。前者是进程读取字节计数，后者是内核记录的存储层读取，不能等同于唯一数据集大小。

2026-10-10 对生产 `frontend-publications` 仅做元数据清点：四组保留构建/依赖备份合计 2,727,305,688 字节、210,290 个目录项，耗时 16.82 秒。没有读取或输出文件正文。旧流程在写退休 intent 前和真正退休前各执行一次历史制品全文哈希；未变化备份两轮约读取 5.45 GB。其他历史和 Git 检查也有 I/O，不能断言 8 GB 全部来自这一项。

## 当前实现：封存审计，保留一个活动回滚集合

实现真源为 [trusted_release_server.py](../../scripts/trusted_release_server.py) 与 [bootstrap_trusted_release.py](../../scripts/bootstrap_trusted_release.py)。没有封存索引时，既有完整历史校验继续执行。首次封存必须完整读取并核验所有历史备份，不能通过先生成索引省略迁移校验。

封存绑定当前 live 前端制品与其原 publication operation；该 operation 的 `previous-next`、`previous-node-modules` 是日常必须完整核验的回滚集合。live 内容也必须完整核验。其他已封存历史备份退出日常正文哈希和内部目录遍历，但原备份、锁、消费记录、撤权和审计文件继续保留，不执行物理回收。

每次日常检查仍枚举所有 publication 操作的顶层库存，重读并校验全部小审计文件、日志摘要、原始回执和终态，核对封存覆盖集合及备份根目录安全边界。只有这些证据与封存记录一致的 archived operation，才跳过其备份内部遍历和 blob 内容读取。新增未知/未完成操作、审计改变或消失、撤销异常、签名错误、部分索引更新继续阻断。已完成的新 publication 在经过校验、live 绑定及锁/进程复证后，可于退休 intent 之前更新封存代次；不会把未知现场自动纳入可信记录。

索引位于私有 `frontend-history-seal`，使用独立生成的密钥，以带用途隔离的 HMAC 保护 checkpoint、代次链、anchor 和更新 intent；目录/文件要求受保护的 root 身份与权限。更新按原 launcher/build 锁执行，持久化、原子替换并 fsync。普通可写 JSON 或文件存在本身不能作为信任证明。密钥与全部状态一起被 root 回退不在该保护的威胁覆盖内；索引不是独立外部防回滚凭证。

封存证明历史证据在封存时已经验证，不证明 archived blob 此刻仍完整。旧备份恢复或重新选为回滚候选前，必须重新全量读取、遍历并与原摘要比较；不符则拒绝恢复，不能以封存状态豁免。

## 独立 bootstrap 入口与中断收尾

首次封存不依赖一次成功的 `rotate` 才能启动。必须从受审、精确 CI 通过的 canonical staging 加载 bootstrap；不得上传本机脚本替换线上工具。入口是同一个子命令，三个互斥使用阶段如下：

```bash
# 首次封存/显式更新；live 绑定不唯一时须给出原 operation ID
python3.12 -I -S -B scripts/bootstrap_trusted_release.py seal-frontend-history --sha <reviewed-sha>

# 只读检查原部分更新，不创建新 checkpoint
python3.12 -I -S -B scripts/bootstrap_trusted_release.py seal-frontend-history --sha <reviewed-sha> --inspect

# 仅完成检查已确认的原 checkpoint，不重新创建或更换 ID
python3.12 -I -S -B scripts/bootstrap_trusted_release.py seal-frontend-history --sha <reviewed-sha> --checkpoint-sha256 <original-checkpoint-digest>
```

这些命令仍要求 canonical 来源、完整 CI、原授权策略、原 launcher/build 锁、无活动业务租约/发布进程及 OTA 历史闭合。seal/finish 还要全量核验 live 内容和活动回滚备份；`--active-operation` 只能消除已验证 live 绑定的歧义。inspect 只读取已经形成且可验证的部分 checkpoint，不豁免鉴权或锁。

未完成的 anchor/update intent 会阻断普通轮换。finish 只能收尾精确匹配的原 checkpoint、live 摘要与原审计集合，不删除现场，不生成新授权，不消费业务发布 claim。无法验证的早期残缺、未知文件或证据漂移继续交给 operator 调查，禁止删索引、自动降级全量放行或重跑原发布。

## 进程内 memo 与性能证据

同一次持锁轮换仍可共享局部 `backup_memo`。对于本次确需完整核验的制品，首轮完整哈希并匹配原回执，记录前后库存指纹；次轮只在路径、类型、设备/inode、owner/group/mode、链接数、大小、纳秒 mtime/ctime 和链接目标全部一致时复用摘要。次轮仍校验权限、链接边界和两次库存指纹。此 memo 不落盘、不跨命令，不用于 live 制品；它与历史封存不同，不能替代封存的覆盖与签名检查。

历史检查输出脱敏的阶段、耗时、archived/实际核验数量和可用的进程 I/O 差值；`/proc` 计数不可用时保留缺失，不伪造零。bootstrap 的阶段诊断与原 stdout 回执协议分开。计时或内容读取减少不表示发布成功。

此前本地同盘合成对照使用 2,048 个文件、512 MiB，验证 memo 将两轮内容读取从 1 GiB 降至 512 MiB，摘要相同；暖文件系统实测 1.17 秒与 0.60 秒。该结果仅证明旧过渡优化的重复内容读取减少，不能折算新版生产收益。新版要在相同 current/rollback 集合下增加大体积 archived 备份，验证日常 archived 正文读取和内部遍历为零，并将首次全量封存耗时单独报告。

## Runner 前置预检与 Pi 计时

`trusted-release.yml` 在精确 source/CI gate 后、生产凭据之前运行 [trusted_runner_transport.py](../../scripts/trusted_runner_transport.py)。固定 `39.98.206.178:22`，TCP 建连和 SSH 标识读取共用五秒预算，只读有限长度标识，不发送认证数据、不读凭据、不领取 claim。`target=transport` 仅执行 preflight，可在授权轮换之前测试 runner 线路；仍须满足精确 source/CI gate。

脱敏 JSON 包含阶段、耗时以及 `authenticated=false`、`host_identity_verified=false`。成功只表示固定 endpoint 可连接并返回 SSH 标识；不能证明鉴权、主机身份、服务就绪或部署成功。真实发布继续执行后续 SSH host key 校验、只读 readiness、执行前 CI 复证及一次性 claim。网络失败不自动重发已消费操作。

`deploy.sh` 为 Pi 安装增加独立的 `remote_pi_install_started` / `remote_pi_install_completed` 计时，保留安装失败退出码。Python 锁文件缓存不证明 Pi runtime 就绪，Pi 安装仍实际执行。此处只是测量，不是 Pi 缓存、跨 runner 工具镜像或构建复用；这些优化须先取得分段基线再决定。

## 验证与发布边界

相关证据覆盖 [历史封存测试](../../scripts/test_trusted_frontend_history_seal.py)、[runner 预检测试](../../scripts/test_trusted_runner_transport.py) 与 [发布计时测试](../../scripts/test_release_timing.py)。本地合成测试不替代 Linux 生产语义、精确 SHA CI、独立安全审查和线上验收。

生产启用仍须新 canonical SHA 受审且 CI 通过，先取得 runner 线路证据，再执行独立封存与必要授权操作，分别记录部署、OTA 和业务验收回执。当前实现不能将原网络阻断或未完成发布自动改为成功。
