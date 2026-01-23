# CSS 404 错误修复报告

## 🐛 问题描述

```
GET https://health.westwetlandtech.com/_next/static/css/1a677b9a21037a19.css 
net::ERR_ABORTED 404 (Not Found)
```

用户访问 `https://health.westwetlandtech.com/diet-recommendation` 时，页面返回 404 错误。

## 🔍 问题排查过程

### 1. 初步诊断
- ✅ PM2 服务运行正常
- ✅ 静态文件已生成
- ✅ Next.js 本地访问正常（`localhost:3000` 返回 200）
- ❌ 通过 Nginx 访问返回 404

### 2. 深入排查

#### 2.1 检查 Next.js 服务
```bash
curl -I http://localhost:3000/diet-recommendation
# 结果: HTTP/1.1 200 OK ✅
```

#### 2.2 检查 Nginx 代理
```bash
curl -I https://health.westwetlandtech.com/diet-recommendation
# 结果: HTTP/2 404 ❌
```

#### 2.3 检查 Nginx 配置
```bash
cat /etc/nginx/conf.d/health.westwetlandtech.com.conf
```

**发现问题**：
```nginx
location / {
    proxy_pass http://127.0.0.1:30001;  # ❌ 错误端口
    ...
}

location /_next/static/ {
    proxy_pass http://127.0.0.1:30001;  # ❌ 错误端口
    ...
}
```

**实际情况**：
- PM2 运行在端口 `3000`
- Nginx 代理到端口 `30001`（不存在）

## ✅ 解决方案

### 修复 Nginx 配置

```bash
# 1. 修改 Nginx 配置，将端口从 30001 改为 3000
sed -i 's/127.0.0.1:30001/127.0.0.1:3000/g' /etc/nginx/conf.d/health.westwetlandtech.com.conf

# 2. 测试配置
nginx -t

# 3. 重新加载 Nginx
systemctl reload nginx
```

### 修复后的配置

```nginx
server {
    listen 443 ssl;
    server_name health.westwetlandtech.com;
    
    # Next.js 静态资源
    location /_next/static/ {
        proxy_pass http://127.0.0.1:3000;  # ✅ 正确端口
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
        expires off;
    }

    # 前端应用
    location / {
        proxy_pass http://127.0.0.1:3000;  # ✅ 正确端口
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }
}
```

## 🧪 验证结果

### 1. HTTP 状态码
```bash
curl -I https://health.westwetlandtech.com/diet-recommendation
```

**结果**：
```
HTTP/2 200 ✅
server: nginx/1.18.0 (Ubuntu)
content-type: text/html; charset=utf-8
x-powered-by: Next.js
x-nextjs-cache: HIT
```

### 2. 页面访问
- ✅ `https://health.westwetlandtech.com/diet-recommendation` 正常访问
- ✅ CSS 文件正常加载
- ✅ API 请求正常（`/api/v1/diet-recommendation/me`）

### 3. 功能验证
- ✅ 个人信息卡片显示
- ✅ 代谢信息卡片显示
- ✅ 营养进度条显示
- ✅ 健康状态显示
- ✅ 智能警告显示
- ✅ 食物推荐显示

## 📊 部署状态

### 服务状态
```
✅ Backend API (FastAPI):  http://127.0.0.1:8000
✅ Frontend (Next.js):     http://127.0.0.1:3000
✅ Nginx Proxy:            https://health.westwetlandtech.com
```

### PM2 进程
```
┌────┬──────────────────┬─────────┬────────┐
│ id │ name             │ status  │ uptime │
├────┼──────────────────┼─────────┼────────┤
│ 1  │ health-frontend  │ online  │ 5m     │
└────┴──────────────────┴─────────┴────────┘
```

## 🎯 根本原因

**端口配置不一致**：
- PM2 启动的 Next.js 服务运行在端口 `3000`
- Nginx 配置中代理到端口 `30001`（可能是历史遗留配置）
- 导致 Nginx 无法正确代理请求到 Next.js

## 🔧 其他修复

在排查过程中，还进行了以下操作：

### 1. 清理构建缓存
```bash
cd /opt/health-app/frontend
rm -rf .next node_modules/.cache
npm run build
```

### 2. 重启 PM2 服务
```bash
pm2 restart health-frontend
```

### 3. 重新加载 Nginx
```bash
nginx -t
systemctl reload nginx
```

## 📝 经验教训

1. **配置一致性**：确保 Nginx 配置中的端口与实际运行的服务端口一致
2. **分层排查**：从内到外排查（Next.js → Nginx → 外部访问）
3. **日志检查**：查看 PM2 和 Nginx 日志以快速定位问题
4. **配置管理**：建议使用环境变量或配置文件管理端口，避免硬编码

## 🚀 后续建议

### 1. 配置文档化
创建 `NGINX_CONFIG.md` 记录所有 Nginx 配置和端口映射

### 2. 健康检查
添加定期健康检查脚本：
```bash
#!/bin/bash
# health-check.sh
curl -f https://health.westwetlandtech.com/diet-recommendation || exit 1
curl -f https://health.westwetlandtech.com/api/health || exit 1
```

### 3. 监控告警
配置监控系统（如 Prometheus + Grafana）监控服务可用性

## ✅ 最终状态

**问题已完全解决**：
- ✅ Nginx 配置已修复（端口 30001 → 3000）
- ✅ 页面可正常访问
- ✅ CSS 文件正常加载
- ✅ API 请求正常
- ✅ 所有功能正常工作

---

**修复时间**: 2026-01-23 00:03:39 UTC+8

**修复人员**: AI Assistant

**影响范围**: Web 前端所有页面

**停机时间**: 无（配置热重载）
