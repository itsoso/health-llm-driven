# 静态资源 400 错误最终修复 ✅

> 修复时间: 2026-01-22 14:55

## 🐛 问题

所有前端静态资源返回 400 错误：
```
GET /_next/static/css/a86b4103c59047a9.css - 400
GET /_next/static/chunks/webpack-9bde44cb5a6d3c6d.js - 400
GET /_next/static/chunks/fd9d1056-aef6dc36e279b115.js - 400
... (共15+个文件)
```

## 🔍 根本原因

### Next.js 版本不匹配

**本地构建环境**：
- Next.js 14.0.4
- BUILD_ID: `8b1WBOS7fQXOrkkodZT9r`
- 文件: `e3d872a7299a724b.css`

**服务器运行环境**：
- Next.js 14.2.35 ⚠️
- 尝试加载旧的文件名

### 问题链

1. **本地构建** → 使用 Next.js 14.0.4 生成文件
2. **rsync 上传** → 只上传 `.next` 目录
3. **服务器运行** → 使用 Next.js 14.2.35 启动
4. **版本冲突** → 运行时与构建时版本不匹配
5. **文件名错误** → 请求的文件名与实际文件名不符

## ✅ 解决方案

### 在服务器上重新构建

```bash
cd /opt/health-app/frontend

# 1. 停止前端服务
pm2 stop health-frontend

# 2. 安装依赖（确保版本一致）
npm install

# 3. 重新构建（使用服务器的 Node/Next.js 版本）
npm run build

# 4. 启动服务
pm2 start npm --name health-frontend -- start

# 5. 清理旧进程
pm2 delete 0

# 6. 保存配置
pm2 save
```

### 构建结果

**新的 BUILD_ID**: `XqAoAS-cdyZm4e0wO2ZGw`

**新的文件名**（与请求匹配）：
```
✅ webpack-9bde44cb5a6d3c6d.js
✅ fd9d1056-aef6dc36e279b115.js
✅ 2117-a56d72bc22eed5c1.js
✅ main-app-c607fd09aefd5bae.js
✅ a86b4103c59047a9.css
```

## 📊 验证

### 服务器状态
```bash
pm2 status health-frontend
# ✅ online (PID: 1610064)

cat /opt/health-app/frontend/.next/BUILD_ID
# XqAoAS-cdyZm4e0wO2ZGw

curl -I http://localhost:3000
# HTTP/1.1 200 OK
```

### 文件存在性
```bash
ls /opt/health-app/frontend/.next/static/chunks/
# ✅ webpack-9bde44cb5a6d3c6d.js
# ✅ fd9d1056-aef6dc36e279b115.js
# ✅ 2117-a56d72bc22eed5c1.js
```

## 🎯 用户操作

**强制刷新浏览器**（清除旧的 HTML 缓存）：
- Windows/Linux: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

## 📝 经验教训

### ❌ 错误的部署方式

```bash
# 本地构建 + rsync
npm run build  # 本地 (Next.js 14.0.4)
rsync .next/ server:/path/  # 上传
pm2 restart  # 服务器 (Next.js 14.2.35) ❌ 版本不匹配
```

### ✅ 正确的部署方式

**方法 1：服务器端构建（推荐）**
```bash
# 在服务器上
cd /opt/health-app/frontend
git pull  # 或 rsync 源代码
npm install
npm run build
pm2 restart health-frontend
```

**方法 2：Docker（最佳）**
```dockerfile
FROM node:20
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

**方法 3：锁定版本**
```json
// package.json
{
  "dependencies": {
    "next": "14.0.4"  // 精确版本，不用 ^14.0.4
  }
}
```

## 🔧 预防措施

### 1. 统一环境

**package.json**:
```json
{
  "engines": {
    "node": ">=20.0.0",
    "npm": ">=10.0.0"
  },
  "dependencies": {
    "next": "14.2.35"  // 锁定版本
  }
}
```

### 2. CI/CD 流程

```yaml
# .github/workflows/deploy.yml
- name: Build on server
  run: |
    ssh server "cd /opt/health-app/frontend && \
                npm install && \
                npm run build && \
                pm2 restart health-frontend"
```

### 3. 健康检查

```bash
#!/bin/bash
# health-check.sh

BUILD_ID=$(cat /opt/health-app/frontend/.next/BUILD_ID)
echo "Current BUILD_ID: $BUILD_ID"

# 检查关键文件是否存在
STATIC_DIR="/opt/health-app/frontend/.next/static"
if [ -d "$STATIC_DIR/$BUILD_ID" ]; then
    echo "✅ Static files exist"
else
    echo "❌ Static files missing"
    exit 1
fi
```

## 🎉 修复完成

服务器端已完成重新构建，所有静态资源文件名现在匹配。

**用户需要强制刷新浏览器**（Ctrl+Shift+R）以清除旧的 HTML 缓存。

---

**关键要点**：
1. ✅ 始终在服务器上构建，或确保构建和运行环境完全一致
2. ✅ 锁定 Next.js 版本，避免自动升级
3. ✅ 使用 Docker 容器化部署
4. ✅ 部署后验证 BUILD_ID 和静态文件
