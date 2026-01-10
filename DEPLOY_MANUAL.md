# 手动部署指南

如果自动部署脚本无法使用，可以按照以下步骤手动在阿里云服务器上部署。

## 部署步骤

### 1. SSH 连接到服务器

```bash
ssh root@health.westwetlandtech.com
# 或者使用你的 SSH 密钥
ssh -i ~/.ssh/your_key root@health.westwetlandtech.com
```

### 2. 进入应用目录

```bash
cd /opt/health-app
```

### 3. 拉取最新代码

```bash
git pull origin main
```

### 4. 更新后端依赖（如果需要）

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 5. 更新前端依赖并构建

```bash
cd frontend
npm install
npm run build
cd ..
```

### 6. 重启服务

```bash
systemctl restart health-backend.service
systemctl restart health-frontend.service
```

### 7. 检查服务状态

```bash
systemctl status health-backend.service
systemctl status health-frontend.service
```

### 8. 查看日志（如果需要）

```bash
# 后端日志
journalctl -u health-backend.service -f

# 前端日志
journalctl -u health-frontend.service -f
```

## 一键部署命令

如果服务器上已经有 `deploy.sh` 脚本，可以直接执行：

```bash
cd /opt/health-app
./deploy.sh
```

或者使用 `--no-logs` 参数不显示日志：

```bash
./deploy.sh --no-logs
```

## 验证部署

部署完成后，访问以下地址验证：

- 前端：https://health.westwetlandtech.com
- 后端健康检查：https://health.westwetlandtech.com/health
- API：https://health.westwetlandtech.com/api/v1/

## 常见问题

### 问题1: git pull 失败

如果 git pull 需要认证，可以：

```bash
# 使用 HTTPS 方式（需要输入用户名密码）
git remote set-url origin https://github.com/itsoso/health-llm-driven.git
git pull origin main

# 或者配置 SSH 密钥
```

### 问题2: npm install 失败

```bash
# 清除缓存
npm cache clean --force

# 使用国内镜像
npm config set registry https://registry.npmmirror.com
npm install
```

### 问题3: 服务启动失败

```bash
# 查看详细错误
journalctl -u health-backend.service -n 50
journalctl -u health-frontend.service -n 50

# 检查端口占用
netstat -tlnp | grep -E "8000|3000"
```

### 问题4: 前端构建失败

```bash
# 检查 Node.js 版本
node -v  # 需要 >= 18

# 清除 node_modules 重新安装
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

## 回滚

如果需要回滚到之前的版本：

```bash
cd /opt/health-app

# 查看提交历史
git log --oneline -10

# 回滚到指定版本
git reset --hard <commit-hash>

# 重新构建和重启
cd frontend && npm run build && cd ..
systemctl restart health-backend health-frontend
```
