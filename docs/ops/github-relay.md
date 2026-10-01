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
