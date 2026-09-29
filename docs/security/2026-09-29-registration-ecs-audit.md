# 开放注册与 ETH 质押 ECS 安全审计

审计时间：2026-09-29 21:09–21:26，Asia/Shanghai。

**裁定：NO-GO。当前不能确认开放注册后的应用风险与 ETH 质押已隔离，不应将最新自助注册版本直接上线。** 这是基于已证实边界缺口的上线判断，不是“已被入侵或资产已丢失”的结论。

## 范围与基线

- 远端主干：`fc9328b1b824427c6fcf2c18607461410077530c`，已 fetch。共享 checkout 有他人改动，本次在独立 detached worktree 审计与修复。
- 线上 `/opt/health-app` HEAD：`623407d6d41d72b8f130aa2db765b2cbc6fba132`；后端启动时间为当日 20:50:42。它与最新主干不是同一版本。
- 方法：源码及依赖审计、SSH 只读主机检查、systemd 运行属性、进程身份、文件权限检查、少量匿名 HTTP 请求、本地回归。没有注册真实账号、发送短信、压力测试、利用 RCE、读取 keystore 内容或导出任何密钥。仅在主机内判断 validator 定义中是否存在密码及文件路径引用，不输出其值。
- 没有修改线上配置、权限、防火墙或服务；没有 commit/push/deploy。审计结束时 health-backend、validator、beacon、执行客户端服务均为 active；这不等于验证了链上收益/出块/资金状态。
- 未覆盖：完整渗透测试、所有跨租户路由、云安全组和 RAM 权限审计、历史入侵取证、提现凭据位置、所有同机应用代码与系统包 CVE。

## 主要发现

优先级表示本次开放注册前的整改顺序，不代表已经演示了远程利用。

| 编号 | 优先级 | 已验证事实 | 风险与边界 |
| --- | --- | --- | --- |
| H1 | P0 阻断 | 正在监听 `127.0.0.1:30001` 的 Next.js 进程属于 root，工作目录是健康前端，位于 root 登录 session；`health-frontend.service` 的 MainPID 为 0，不能用该 unit 的状态代表实际进程。Lighthouse validator、beacon 和执行客户端也以 root 运行。 | 同机任一 root Web 进程若发生代码执行，会获得质押文件和进程的权限。尚未证明存在可利用的前端 RCE，但其后果隔离明确失败。 |
| H2 | P0 阻断 | `/mnt/data/lighthouse/validators` 下一个 keystore 文件模式为 0644，健康应用 UID 在后端 mount namespace 内可读；该文件未被当前 validator 定义引用。当前被引用的 keystore、validator 定义与 API token 为 root:root 0600，应用 UID 不可读。定义文件存在内联密码。 | 可读文件可能是遗留/备份，未读取内容或证明与活跃密钥相同。它仍应按密钥材料收紧权限；root Web 身份则可突破当前 0600 的用户隔离。没有核验提现私钥，不能把签名密钥风险等同于已能转走全部资金。 |
| H3 | P0 阻断 | 在健康后端实际 mount/net namespace 以 `health-app` 身份发起只读请求，`127.0.0.1:5052/eth/v1/node/version` 和 `100.100.100.200/latest/meta-data/` 均返回 200。 | 健康应用可触及本机 Beacon API 与无 token 元数据端点。SSRF 或进程失陷后的横向访问缺少网络隔离。RAM 角色目录本次返回 404，没有读取云凭据，也不声称已泄漏云凭据。 |
| H4 | P1 高 | 公网直接请求 `:9090/api/v1/status/buildinfo` 返回 200 且内容匹配 Prometheus；`:9100/metrics` 返回 200 且内容匹配 node exporter。UFW 放行这两个端口。 | 未认证监控信息可用于资产探测。HTTP 证据证明这两个端口可访问；不把 TCP 握手成功单独当成开放端口证据。8081 和 5052 的直接公网 HTTP 探测超时，不能列为已验证公网开放。 |
| H5 | P1 高 | 线上 Python 环境有 195 个包；扫描在 6 个包上命中 51 个去重后的 package/advisory-ID 组合。主干 Python 锁文件与前端、Pi runtime 的生产依赖扫描均未命中。 | 部署到旧 venv 的增量安装残留了锁文件之外的包。不能把锁文件通过当成生产环境通过。每个告警仍需结合执行路径判断可利用性。 |
| H6 | P1 高 | 主干自助注册默认 true；线上版本尚无该开关，仍配置 invitation enforcement=true、rollout=true。短信入口是每 IP 每分钟限流与每手机发送冷却，没有发现人机挑战、全局短信费用硬预算或日注册名额。 | 最新主干上线会改变注册准入。手机号验证不证明真人身份或善意，分布式 Bot 可绕过单 IP 配额。必须显式固定准入模式并增加多维限额。 |
| H7 | P1 高 | `main.py` 声明 Redis 默认 `200/minute`，但未挂载 SlowAPI 中间件；auth 等路由另建内存 Limiter。按相同库和接线方式复现，默认 `2/minute` 的未装饰路由连续 4 次均为 200。 | 不能将声明的默认限流视作覆盖全站。已有显式装饰的登录/OTP 路由有限流；内存额度不会跨进程/重启持久共享。没有对生产进行洪泛验证。 |
| H8 | P1 高 | 健康后端与 Celery 的 `MemoryMax`、`CPUQuotaPerSecUSec` 为 infinity；同机还有 root 运行的其他 Web 服务。 | 注册后高成本请求、解析恶意文件或后台任务可能争抢质押节点资源。进程非 root 不能解决资源耗尽。需要实例分离或经测量的 cgroup/队列/并发边界。 |

### 线上依赖命中

| 包 | 线上版本 | 按 advisory ID 去重 |
| --- | --- | --- |
| pypdf | 3.17.0 | 41 |
| pip | 25.3 | 5 |
| ecdsa | 0.19.1 | 2 |
| paramiko | 4.0.0 | 1 |
| pytest | 7.4.3 | 1 |
| setuptools | 80.10.1 | 1 |

原始扫描输出为 97 条，含重复 advisory ID，故没有将其描述为 97 个独立漏洞。`pypdf` 存在系统知识 PDF 导入 fallback 调用；尚未证明普通注册用户能触达该管理/导入路径。pip/setuptools/pytest 多属安装、构建或测试面，不能直接等同于公网 RCE。整改应重建精确生产环境并处理实际需要的依赖，不在运行环境盲目卸载或批量升级。

## 已有效的部分防护

- health-backend/Celery 以 `health-app` 运行，后端有效 capabilities 为 0，NoNewPrivileges=true、ProtectSystem=strict、ProtectHome=true；health-app 无 sudo 权限，不能读当前 validator 定义或访问 Docker socket。
- PostgreSQL、Redis、健康后端监听回环；所检查的 health 数据库角色无 superuser/createrole/createdb/bypassrls 权限。这不是对所有 RLS/跨用户查询的完整验证。
- SSH 禁用密码登录，root 仅允许密钥方式。
- 匿名访问健康 `/auth/me`、ETH 公网 `/openclaw/health` 与 `/openclaw/api/eth/v1/node/version` 均为 401。公网 ETH 代理已有鉴权，但本机直连仍可访问部分接口。
- OTP 有短有效期、错误次数限制、成功消费与 `FOR UPDATE`；本轮没有变更数据库逻辑或重新声称 PostgreSQL 并发已通过。
- LLM 已有每用户与全局调用/Token/Credit 额度代码，不能说“没有成本控制”。这些不是短信防刷、人机识别、CPU/内存隔离的替代。

## 本次已完成的本地修复

1. `backend/app/config.py`：生产环境拒绝 `AUTH_PHONE_CODE_DEV_ECHO=true`。
2. `backend/app/services/phone_auth.py`：生产环境无论 debug/echo 开关如何组合，都不进入验证码开发回显；日志投递也统一去空格、忽略大小写识别 production。
3. `backend/app/services/caldav_sync.py`：拒绝非全球可路由 IP，补上 CGNAT（包括阿里云 `100.100.100.200`）；统一检查 IPv4-mapped IPv6；空 DNS 答复失败关闭。

生产当前未开启验证码回显，故这是防误配置缺口，不是已确认线上 OTP 泄漏。元数据端点本次用 HTTP 检查，而日历输入只接受 HTTPS：对 CGNAT 校验遗漏的修复不能被描述为已经演示了该日历接口窃取元数据。DNS 预检后再次解析、CalDAV 的后续发现 URL/跳转仍有残留边界，局部修复不代表 SSRF 已全面封堵。

验证结果：

- 新增回归先跑原实现：11 failed、2 passed，确认捕获真实行为缺口。
- 修改后：126 passed，覆盖配置、CalDAV、OTP 投递隐私、登录策略、自助/邀请注册和 Web session；使用隔离测试配置及 SQLite 单元夹具。没有生产测试写入。
- `git diff --check` 通过；System Map 检查通过（本补丁不改变地图覆盖的结构）。
- 独立 safety reviewer 对固定范围代码给出局部 GO，同时明确不能据此放行开放注册或生产部署。
- 未运行完整 CI-mode 或 PostgreSQL 发布闸，本结果不是发布许可。

## 具体整改顺序与验收条件

### 先固定注册准入，保留现有用户登录

在下一次发布的环境配置中显式设置：

```dotenv
AUTH_PHONE_SELF_REGISTRATION_ENABLED=false
REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=true
REGISTRATION_INVITATION_ROLLOUT_ENABLED=true
```

这是“保留邀请注册”。如需要暂停所有新邀请注册，将 rollout 设为 false；已有用户仍走既有登录分支。仅关闭 rollout 不会关闭最新代码中优先执行的自助注册分支，必须同时关闭 self-registration。验收需分别验证未邀请号码拒绝、邀请号码按选定策略处理、老用户正常登录，不能只看 env 文件。

### 收紧同机暴露与权限

- 公网关闭 9090/9100；监控通过 SSH/VPN 或受认证代理访问，先确认现有监控采集来源并留回滚。云安全组与 UFW 同步核对；保留必要的 ETH P2P 端口，不能一刀切封 9000/9001/30303。
- 对已定位的 0644 keystore 文件改为仅受信任质押用户可读，并检查目录、备份及当前密钥权限。只改已盘点对象，不递归盲改、不移动或复制验证器密钥。用 `health-app` 和前端新身份的实际 namespace 再验不可读。
- 将实际 root Next.js 进程迁移到受 systemd 管理的专用非 root 用户；先准备只读构建产物和必要缓存目录，使用备用回环端口完成健康验证，再切 Nginx。只修改停用的 `health-frontend.service` 无法解决实际 root 进程。
- 全部公网 Web 服务与质押应拆分 ECS。优先迁走 Web 应用，保持现有验证器单实例；切勿为迁移并行启动同一验证密钥的第二实例。
- 同机过渡期，为应用阻断质押管理/RPC、元数据与非必需本机服务访问，保留数据库、Redis 和明确业务依赖；通过网络 namespace/出口代理或按身份的规则实现。启用 ECS 元数据 token 必需模式前检查云监控等现有依赖。

### 重建运行环境并补齐防滥用

- 用锁文件重建干净 venv，必要未锁定依赖单独评审；对实际新环境再次扫描，并验证 PDF 导入和正常服务行为。发布从已验证 revision 执行，保留旧环境可回滚。
- 将限流统一到共享存储并确认全局中间件/路由接线；登录、验证码按 IP+手机号/账号限额，短信再加日预算和全局熔断。故障策略要显式失败，不能存储故障时悄悄无配额放行。
- 在发短信前加入服务端验证的人机挑战/风险判定；客户端令牌必须有有效期、防重放、场景绑定。配额与挑战必须一起验证，不能只在 UI 显示验证码控件。
- 新账号分级限额：注册日名额、AI 调用、上传大小、解析任务数和后台并发；按真实基线设 CPU/内存/队列上限，给验证器留出资源。禁止在质押宿主机直接做压测。

**开放注册最终验收**：不存在 root Web 运行进程；所有应用身份不能访问质押密钥/管理面；匿名监控访问被拒；元数据普通访问被拒；实际部署环境依赖告警已按路径处理；多维限流、预算熔断和封禁/关闭注册演练通过；相关测试、完整 CI 与发布安全门通过。每项都要有运行证据。

## 证据附件与外部依据

本地附件目录：`/Users/liqiuhua/.codex/visualizations/2026/09/29/01a0ed4b-e586-7be1-821a-d33a02e0d24e/security-audit/`。

- `reva-security-red.log`、`reva-security-green.log`：修改前后测试。
- `reva-security-system-map-check.log`：地图与漂移检查。
- `reva-frontend-audit-20260929.json`、`reva-pi-audit-20260929.json`：npm 生产依赖扫描。
- `reva-python-audit-20260929.json`：主干 Python 锁文件扫描。
- `reva-security-production-packages.json`、`reva-production-python-audit-20260929.json`、`production-dependency-findings-deduplicated.json`：线上包清单、扫描与去重。
- 主机观察来自本次只读 SSH/HTTP 输出；未保存可能包含凭据的完整 nginx 配置、环境变量或 validator 文件。

[OWASP 防自动化指导](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html)支持将人机挑战与多维限流、身份配额组合使用。[阿里云元数据文档](https://www.alibabacloud.com/help/zh/ecs/user-guide/view-instance-metadata/)建议强制加固 token 模式以降低 SSRF 元数据泄漏风险。[Lighthouse FAQ](https://lighthouse-book.sigmaprime.io/faq.html)明确警告不要并行运行重复的验证密钥/validator；[Slashing Protection](https://lighthouse-book.sigmaprime.io/validator_slashing_protection.html)说明验证器签名与惩罚保护边界。
