# Nginx 静态资源缓存问题修复

## 问题描述

前端更新后，用户浏览器出现 400 错误，无法加载静态资源：
```
GET https://health.westwetlandtech.com/_next/static/css/a86b4103c59047a9.css net::ERR_ABORTED 400 (Bad Request)
```

## 根本原因

1. **端口配置错误**：Nginx 配置指向端口 30001（旧服务），但 PM2 管理的新前端服务运行在端口 3000
2. **浏览器缓存**：浏览器缓存了旧的 HTML，但请求的静态文件（CSS/JS）已经在新构建中更新，导致文件名不匹配
3. **Next.js 构建哈希**：每次构建 Next.js 都会生成新的文件哈希值，旧的文件名在新构建中不存在

## 解决方案

### 1. 更新 Nginx 配置

**文件**：`/etc/nginx/conf.d/health.westwetlandtech.com.conf`

**关键修改**：

```nginx
# 前端应用 - 更新为端口 3000
location / {
    proxy_pass http://127.0.0.1:3000;  # 从 30001 改为 3000
    # ...
    # HTML 页面不缓存
    add_header Cache-Control "no-store, no-cache, must-revalidate";
}

# Next.js 静态资源 - 禁用缓存
location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;
    # ...
    # 禁用缓存，确保总是获取最新文件
    add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    expires off;
}
```

### 2. 清理旧进程

```bash
# 杀掉端口 30001 的旧进程
kill -9 <PID>

# 确保只有 PM2 管理的前端服务在运行
pm2 status
```

### 3. 重载 Nginx

```bash
nginx -t
systemctl reload nginx
```

## 验证步骤

1. **检查端口**：
   ```bash
   netstat -tlnp | grep 3000
   # 应该只看到一个 next-server 进程
   ```

2. **强制刷新浏览器**：
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`
   - 或使用无痕模式

3. **检查响应头**：
   ```bash
   curl -I https://health.westwetlandtech.com/_next/static/chunks/...
   # 应该看到 Cache-Control: no-store, no-cache
   ```

## 预防措施

### 1. 统一部署流程

**推荐的前端部署脚本**：

```bash
#!/bin/bash
# deploy_frontend.sh

cd /opt/health-app/frontend

# 停止服务
pm2 stop health-frontend

# 清理旧构建
rm -rf .next
rm -rf node_modules/.cache

# 拉取最新代码
git pull origin main

# 重新构建
npm run build

# 重启服务
pm2 restart health-frontend

# 验证
pm2 status
curl -I http://localhost:3000
```

### 2. 使用 BUILD_ID 验证

```bash
# 检查当前 BUILD_ID
cat /opt/health-app/frontend/.next/BUILD_ID

# 验证静态文件是否生成
ls -lh /opt/health-app/frontend/.next/static/chunks/app/overview/
```

### 3. Nginx 缓存策略

- **HTML 页面**：不缓存（`no-store, no-cache`）
- **静态资源**：短期缓存或不缓存（开发阶段建议不缓存）
- **图片/字体**：长期缓存（生产环境可启用）

## 相关文件

- Nginx 配置：`/etc/nginx/conf.d/health.westwetlandtech.com.conf`
- 前端目录：`/opt/health-app/frontend`
- PM2 配置：`pm2 info health-frontend`

## 时间线

- **2026-01-22 14:00**：用户报告静态资源 400 错误
- **2026-01-22 14:30**：发现端口配置错误（30001 vs 3000）
- **2026-01-22 15:00**：更新 Nginx 配置，禁用缓存
- **2026-01-22 15:10**：问题解决，服务恢复正常

## 经验教训

1. **服务器端构建**：始终在服务器上构建 Next.js 应用，避免本地构建后上传导致的版本不一致
2. **端口管理**：使用 PM2 统一管理服务，避免多个进程占用不同端口
3. **缓存策略**：开发/测试阶段禁用静态资源缓存，生产环境根据需要启用
4. **版本验证**：部署后验证 BUILD_ID 和静态文件是否正确生成

---

**修复完成！** 🎉

用户现在可以正常访问：https://health.westwetlandtech.com
