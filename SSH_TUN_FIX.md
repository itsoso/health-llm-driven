# SSH 绕过 TUN 代理配置指南

当使用 TUN 模式的代理时，SSH 连接可能会被代理拦截导致连接失败。以下是几种解决方案。

## 方案 1: 在 SSH 配置中设置直连（推荐）

编辑 `~/.ssh/config` 文件，为特定服务器添加直连配置：

```bash
# 编辑 SSH 配置
vim ~/.ssh/config
```

添加以下配置：

```ssh-config
# 阿里云服务器 - 绕过代理直连
Host health.westwetlandtech.com
    ProxyCommand none
    ProxyJump none
    # 如果需要指定端口
    # Port 22
    # 如果需要指定用户
    # User root
    # 如果需要指定密钥
    # IdentityFile ~/.ssh/your_key

# 或者为所有服务器设置（不推荐，可能影响其他连接）
Host *
    ProxyCommand none
    ProxyJump none
```

## 方案 2: 使用环境变量排除 SSH

在 SSH 命令前设置环境变量，让 SSH 不经过代理：

```bash
# 临时设置，仅对当前命令有效
NO_PROXY="*" HTTP_PROXY="" HTTPS_PROXY="" http_proxy="" https_proxy="" ssh root@health.westwetlandtech.com

# 或者在 ~/.zshrc 或 ~/.bashrc 中添加
export NO_PROXY="localhost,127.0.0.1,health.westwetlandtech.com"
```

## 方案 3: 使用 SSH 命令行参数

直接在 SSH 命令中添加参数绕过代理：

```bash
ssh -o ProxyCommand=none \
    -o ProxyJump=none \
    root@health.westwetlandtech.com
```

## 方案 4: 配置代理软件的绕过规则

如果使用 Clash、V2Ray 等代理软件，可以在配置中添加绕过规则：

### Clash 配置示例

```yaml
rules:
  - DOMAIN-SUFFIX,westwetlandtech.com,DIRECT
  - DOMAIN-SUFFIX,aliyun.com,DIRECT
  - IP-CIDR,47.0.0.0/8,DIRECT  # 阿里云 IP 段
  - IP-CIDR,120.0.0.0/8,DIRECT  # 阿里云 IP 段
```

### V2Ray 配置示例

在路由规则中添加：

```json
{
  "domain": [
    "westwetlandtech.com",
    "aliyun.com"
  ],
  "outboundTag": "direct"
}
```

## 方案 5: 使用 nc (netcat) 作为 ProxyCommand

如果方案 1 不工作，可以尝试使用 netcat：

```ssh-config
Host health.westwetlandtech.com
    ProxyCommand nc %h %p
```

## 验证配置

配置完成后，测试 SSH 连接：

```bash
# 测试连接（不执行命令）
ssh -o ProxyCommand=none root@health.westwetlandtech.com echo "连接成功"

# 或者使用详细模式查看连接过程
ssh -v -o ProxyCommand=none root@health.westwetlandtech.com
```

## 部署脚本已更新

`deploy-remote.sh` 脚本已经更新，自动添加了绕过代理的参数：

```bash
ssh -o ProxyCommand=none \
    -o ProxyJump=none \
    root@health.westwetlandtech.com
```

## 常见问题

### Q: ProxyCommand=none 不工作怎么办？

尝试使用 `nc` (netcat)：

```bash
# 安装 netcat（如果未安装）
# macOS: brew install netcat
# Ubuntu: apt install netcat

# 在 SSH 配置中使用
Host health.westwetlandtech.com
    ProxyCommand nc -X none %h %p
```

### Q: 如何检查是否绕过了代理？

使用 `-v` 参数查看详细连接信息：

```bash
ssh -v -o ProxyCommand=none root@health.westwetlandtech.com
```

查看输出中是否有代理相关的信息。

### Q: 如何临时禁用 TUN 模式？

如果以上方案都不行，可以临时关闭 TUN 模式，执行部署后再开启。

## 推荐配置

**最佳实践：** 在 `~/.ssh/config` 中为服务器添加专用配置：

```ssh-config
Host health.westwetlandtech.com
    HostName health.westwetlandtech.com
    User root
    ProxyCommand none
    ProxyJump none
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

这样配置后，直接使用 `ssh health.westwetlandtech.com` 即可，无需每次添加参数。
