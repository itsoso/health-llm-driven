# 生产发布的 GitHub 代理

last-reviewed: 2026-10-01

适用服务器：Reva 生产 `39.98.206.178`。此处记录已安装并验证的线路；接手时先检查
现场，不假定历史状态仍有效。发布授权与流程以 [部署规范](../governance/deploy.md) 为准。

## Agent 如何使用

继续使用 canonical origin `https://github.com/itsoso/health-llm-driven.git`。
在生产服务器执行的 GitHub HTTPS 请求会自动经过代理，不需要额外的 `--proxy`、
`HTTP_PROXY`、`HTTPS_PROXY` 或 Git 全局配置。隔离发布器会清理环境并忽略全局 Git
配置，因此在普通 shell 中设置代理变量不能证明发布器可用。

此代理只覆盖生产服务器的 `github.com:443`，不覆盖 GitHub SSH、api.github.com、
codeload 或其他下载域名。不要把下面的 hosts 映射复制到开发电脑、CI runner 或其他主机。
网络修复不授予任何发布权限，也不改变 exact-SHA、CI、消费记录和锁的规则。
专用发布密钥虽已取消自动到期，新 main SHA 仍须通过 canonical bootstrap 轮换授权；
代理正常不能解决版本未授权，也不能替代这一步。不要手改 authorized-release.json。

## 已安装的路径

```text
生产服务器 Git/HTTPS → [::1]:443 → SSH 加密隧道
  → base.executor.life (47.237.191.17:22222) → github.com:443
```

TLS 仍由客户端与 GitHub 端到端握手，校验 GitHub 证书；base 不终止 TLS。
生产 nginx 继续监听 IPv4 443，隧道只监听 IPv6 loopback，不提供公网代理。

| 主机 | 配置与职责 |
| --- | --- |
| 生产 | `/etc/systemd/system/reva-github-relay.service`，专用非 root 用户运行 SSH；已启用开机启动、保活及失败重连 |
| 生产 | `/etc/hosts` 中唯一 `github.com` 项为 `::1 github.com`；nscd 缓存也须保持一致 |
| 生产 | `/etc/reva-github-relay/identity` 和 `known_hosts`：专用隧道私钥和固定 base 主机密钥；权限 `0600`，不打印、不上传、不提交 |
| base | `/etc/ssh/reva-github-relay/authorized_keys`：root 管理，仅本次专用公钥，来源限制为生产 IP，目标限制为 `github.com:443` |
| base | `/etc/ssh/sshd_config.d/90-reva-github-relay.conf`：仅 publickey、仅 local TCP forwarding、`PermitOpen github.com:443`、`MaxSessions 0`；拒绝 shell、远程/其他目标转发 |

隧道身份与 GitHub Environment Secret `REVA_RELEASE_SSH_KEY` 是两套不同密钥。
不要用管理员密钥或发布私钥替换隧道私钥。base 的 SSH 端口是 **22222**；使用该
IP:port 对应的已验证 known_hosts，不能为消除主机密钥不匹配而关闭严格检查。

## 发布前只读检查

由有管理权限的操作者通过已验证 SSH 连接进入生产服务器，在服务器上运行：

```bash
systemctl is-enabled reva-github-relay
systemctl is-active reva-github-relay
ss -lntp 'sport = :443'
python3 -I -B - <<'PY'
import socket
addresses = socket.getaddrinfo(
    'github.com', 443, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_ADDRCONFIG
)
assert {item[4][0] for item in addresses} == {'::1'}, addresses
print('GitHub resolver uses local relay')
PY
timeout 60 /usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git -c core.hooksPath=/dev/null -c http.followRedirects=false \
  -c http.version=HTTP/1.1 -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 \
  ls-remote https://github.com/itsoso/health-llm-driven.git refs/heads/main
```

要求 service 为 enabled/active、SSH 只监听 `[::1]:443`、解析断言通过，并且 Git
命令退出 0、返回当前 main SHA。与本次发布候选核对后，再通过既有 `check <sha>`
RPC / 工作流 readiness 检查。只读 `check` 不消费授权；`run` 不是网络探测命令。
不要把历史成功 SHA 复制成当前发布候选。

## 故障定位与恢复

先运行 `systemctl status reva-github-relay --no-pager` 和
`journalctl -u reva-github-relay -n 30 --no-pager`。只记录错误、时间与指纹，不输出私钥。

- **连接 base 失败**：检查生产至 `47.237.191.17:22222` 的 TCP 连通性、base SSH 服务
  和固定 host key。主机密钥改变必须核对身份；不能使用 `StrictHostKeyChecking=no`。
- **账号过期 / publickey 拒绝**：检查 base 专用账号的 `chage -l reva-github-relay`、
  当前公钥、来源限制及实际生效配置。历史同名账号曾被停用，不恢复其退休密钥。
  凭据/账号变更走已授权的运维修复与安全复核，不盲目重建密钥。
- **service active 但 Git 失败**：检查 `[::1]:443` 监听、hosts 精确项和 nscd。
  配置已确认正确但缓存陈旧时，运行 `nscd -i hosts`，再执行上面的隔离 Git 检查。
- **需要重启隧道**：确认没有会被中断的发布或其他 Git 传输后，按已授权的运维范围
  执行 `systemctl restart reva-github-relay`，随后重新完成只读检查。无需重启应用或 nginx。

可用下面的只读请求区分本地转发、TLS 与 Git HTTP：

```bash
curl -q --http1.1 --resolve 'github.com:443:[::1]' \
  --connect-timeout 5 --max-time 15 --silent --show-error --output /dev/null \
  --write-out 'HTTP=%{http_code} TLS=%{ssl_verify_result}\n' \
  'https://github.com/itsoso/health-llm-driven.git/info/refs?service=git-upload-pack'
```

预期 HTTP=200、TLS=0。不使用 `-k`、自定义 CA、URL 重写或延长低速超时来放行。
如果需要修改 base SSH 配置，先 `sshd -t`，再以
`sshd -T -C user=reva-github-relay,addr=39.98.206.178,host=health` 核验有效限制，
通过后才 reload。新安装/变更后还需实测：允许 GitHub 443，拒绝 shell、远程转发、
其他主机与端口；只在无发布时测试断线恢复，不能中断正在运行的发布来重复验收。

## 回滚与验证记录

生产原 hosts 保存在 root-only
`/var/backups/reva-github-relay-20261001/hosts.before`。回滚前比较差异，保留后续合法
修改，只撤销本次 GitHub 映射，清理 nscd 缓存，再停止/禁用隧道。不要先停隧道却
留下 loopback 映射。base 的原账号状态位于
`/etc/ssh/reva-github-relay/account-aging.before.txt`；本次原到期日为 `1970-01-02`。
撤销本次新增的公钥/sshd 配置、语法验证并 reload 后，可按原记录恢复到期状态。
历史退休文件与审计记录保留。回滚会恢复已知不稳定的直连路径，不等于网络已修好。

2026-10-01 验收：严格 Git 查询连续通过，停止隧道时失败、恢复后通过；限制负测通过。
[Trusted release 36861632116](https://github.com/itsoso/health-llm-driven/actions/runs/36861632116)
随后完成实际环境密钥认证、服务器 readiness 和后端部署。此记录证明当时可用，
后续发布仍须重新检查当前线路、候选版本和 CI。


## 2026-10-15 GitHub API 限流诊断与备用方案

状态：调查与方案完成，以下改造尚未实施；不改变生产授权或既有 no-backup 要求。
这里 backup 指发布链路的备用处理方案，不是数据库、配置或制品备份。

### 已核实原因

- 生产匿名 `GET /rate_limit` 于 2026-10-15 04:57:48 UTC 返回 core limit=60、used=53、remaining=7。该快照不是全部请求的归因账本，不能认定53次均由本会话产生。
- `scripts/trusted_release_gate.py::_get_json` 支持 GH_TOKEN；但主要 Actions preflight 使用 `sudo env -i`，未显式传入该变量；bootstrap 的固定 ENV 和 server 的 clean_environment 同样隔离普通登录环境。开发机 gh 登录不代表这些进程已认证。隔离本身应保留，问题是缺少专门设计的只读认证通道。
- 对既有测试夹具执行真实 verify_release、用合成 HTTP 响应计数：当前 main 等于候选时，full gate 共5次 API GET（main两次、CI列表两次、run详情一次）。这是离线调用计数，不是线上耗时/P95。重复读取用于防止主干和CI重跑状态在校验期间改变，不能直接删除。backend-v1 源码路径为5+4N次（N为该SHA的CI run数），切换backend-v1并非节流方案。
- 多阶段重新校验及多个发布者共享匿名出口会消耗同一IP额度；并发发布身份已有审计证据，但尚不能逐次归因。缺少按operation/phase记录请求量的审计，是观测缺口。
- 本次 rotate 本地包装器报 insufficient_fresh_attestation_budget，是剩余额度低于预留35次的主动拒绝，不等于该调用收到GitHub限流响应。另一个 workflow preflight 有独立限流失败，必须区分记录。
- 当前 relay 仅覆盖 github.com:443，API请求仍直连api.github.com。Git SSH断连、Git HTTPS传输故障、API配额耗尽必须分别诊断；重启relay无法增加API额度。
- 403限流已经立即失败；429没有Retry-After时现实现会以1秒间隔在10秒截止内重试。应改为至少60秒后的调度重试，避免扩大二级限流；不在特权进程中长时间占锁睡眠。

### 主方案与备用路径

| 优先级 | 方案 | 触发与执行边界 |
| --- | --- | --- |
| P0 | 单发布owner、阶段请求计数、共享冷却状态 | 按repo/认证身份资源桶协调；记录operation、phase、状态码、remaining/reset/Retry-After、请求数，不记Token、响应正文或原始健康数据。一次预算不足只排一个唤醒，避免各会话重复尝试。 |
| P1 | Actions使用本仓库只读GITHUB_TOKEN | 显式actions:read、contents:read；只交给受审gate进程，不恢复整个环境、不放入命令参数、日志或Git配置。先测试env清理及凭据泄露边界。 |
| P1 | 生产使用仓库限定GitHub App安装令牌 | 通过受控凭据提供器交给只读校验器；短期Token，固定仓库/URL/TLS、拒绝重定向，权限仅actions/contents/metadata读取。bootstrap和installed executor同批适配；尚未配置，不能靠临时注入管理员PAT绕过。 |
| P2 | 无可用认证额度时延后原候选 | 按Retry-After和reset较晚时间加小幅抖动排队；恢复后重新验证current main、CI attempt、owner、原回执及锁。只有明确未消费的读取校验可重试；已开始或未知发布必须恢复原操作。现有匿名路径可作为受预算约束的只读备用，不自动降级失败的认证请求。 |
| P2 | 监控与发布校验分离 | UI进度用短TTL缓存/条件请求或webhook，按repo/SHA/run/attempt/凭据身份隔离。最终特权阶段仍实时校验；不得复用缓存绿灯，不能用旧CI回执离线上线。 |
| P3 | Git传输故障单独恢复 | 按本文既有relay/TLS检查恢复同一canonical线路。API全局不可用时保留当前健康版本、继续本地测试和构建、等待恢复；不切镜像、不轮换IP逃避限流、不关闭证书校验。 |

GitHub官方当前额度：匿名60次/小时/IP；Actions GITHUB_TOKEN通常1000次/小时/仓库；GitHub App安装令牌最低5000次/小时。并不保证免受二级限流。GET /rate_limit不消耗主额度，但可能计入二级限流，不能高频轮询。额度以实际API响应头为准。

### 实施与验收

1. 先补观测和限流分类RED测试：403主额度归零、403/429二级限流、Retry-After、reset、401/非限流403、网络故障分别输出结构化脱敏原因；没有等待期内请求风暴。
2. 配置受审最小权限认证路径，验证普通环境Token不能改变生产授权、固定端点拒绝重定向、秘密不出现在日志/argv、凭据过期明确失败。不要测试真实健康数据或真实模型。
3. 测试main变化、CI重跑/失败、缓存过期、身份切换仍拒绝；冷却结束不重放已消费release/OTA；不同owner不能同时发布。
4. 在同一候选/相同阶段记录改造前后GET数量、认证桶、剩余额度、校验耗时。目标：主要校验链路不再匿名运行；二级限流不快速重试；每桶仅一个恢复调度；最终授权边界不放宽。不凭当前快照承诺生产P95或整次发布耗时。
5. 精确SHA完整CI、独立安全审查通过后才安装新发布器；未完成发布交接前不改生产鉴权。失败时停用新候选并保留当前健康版本及原审计，不新建回退副本。

依据：[GitHub限流规则](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)、[REST最佳实践](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)。本次未修改生产配置，未部署上述备用机制。


### 认证与退避实现候选（2026-10-15，尚未上线）

已实现的候选覆盖 trusted-release 全部直接gate及 trusted-ota 初始/内部gate：内置 `github.token` 保持既有 `contents: read`、`actions: read`，由 shell builtin printf 经stdin交给隔离进程。先完成不带Token的Git物化，再独立校验；不把API Token放入argv、Git配置、Expo环境或输出日志。显式stdin为空/超长/非法即失败，不回退其他来源。现有两条workflow已经共用 `reva-production-release` concurrency group 且不取消运行中的发布，本次保留，未新增第二套锁；外部SSH操作者仍须交接。

生产候选gate增加固定可选入口 `/etc/reva-github-api/credential.json`，与发布授权目录分离；不修改 authorized-release.json。仅root读取，祖先root所有且不可组/其他写，文件0600、单硬链、禁止软链、有界读取和读取前后身份校验。严格字段为 `repository`（必须itsoso/health-llm-driven）、`token`、`expires_at`（未来UTC Unix秒）。由运维凭据提供器写入本仓库只读GitHub App installation token及实际过期时间，私钥留在凭据提供器，不提交到仓库或聊天。到期前安全刷新；API仍验证Token有效性和实际权限。此字段绑定只防配置误用，不声称能从Token字符串证明GitHub侧权限。

配置缺失保持原匿名/legacy兼容路径；配置存在但不安全、过期或非法则明确失败，绝不降级。显式Actions stdin不读取服务器配置。没有可用安装凭据时不能宣称生产已提额，本次未创建或安装凭据。安全部署新gate并完成真实只读GitHub元数据验收后，才记录认证已启用。

403/429现在立即失败，不在进程内快速重试；脱敏错误给出 `code`、`not_before`、`retry_after_seconds`，按Retry-After、reset及至少60秒计算。未知403保留“权限拒绝或二级限流”的不确定性。调度者须遵守not_before，且只能恢复明确未消费的只读校验；这些字段不构成发布授权。共享持久冷却调度、App自动刷新服务尚未实现，不能把错误提示当作自动恢复完成。

付费结论：官方价格页没有单列API请求量流量包；Enterprise起价21美元/用户/月（页面为首12个月价格，实际合同另核），适用的Enterprise Cloud安装令牌和Actions资源可有15000次/小时额度。普通匿名请求依旧60次，二级限流依旧存在。当前先用无需升级的认证额度，未购买或变更套餐。依据：[官方价格](https://github.com/pricing)、[Enterprise Cloud额度](https://docs.github.com/en/enterprise-cloud%40latest/rest/using-the-rest-api/rate-limits-for-the-rest-api)。
