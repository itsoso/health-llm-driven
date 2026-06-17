# Nginx 端口配置错误修复

**修复时间**: 2026-01-23 15:07  
**问题**: 前端静态资源加载失败，返回 400 错误

## 🐛 问题描述

浏览器控制台出现以下错误：

```
Failed to load resource: the server responded with a status of 400 ()
webpack-ad4e51dbf9db1be9.js:1  Failed to load resource: the server responded with a status of 400 ()
page-5c1820fd5561b181.js:1  Failed to load resource: the server responded with a status of 400 ()
```

**影响**:
- 所有 `_next/static` 路径的资源加载失败
- 页面 JavaScript 无法正常加载
- 页面功能异常

## 🔍 问题分析

### Nginx 访问日志

```
223.104.40.154 - - [23/Jan/2026:15:06:53 +0800] "GET /_next/static/chunks/webpack-ad4e51dbf9db1be9.js HTTP/2.0" 400 928
223.104.40.154 - - [23/Jan/2026:15:06:53 +0800] "GET /_next/static/chunks/app/page-5c1820fd5561b181.js HTTP/2.0" 400 928
223.104.40.154 - - [23/Jan/2026:15:06:53 +0800] "GET /_next/static/chunks/app/layout-5fb8a0cf9f6b5902.js HTTP/2.0" 400 928
```

**特征**:
- 所有请求返回 400 错误
- 响应大小都是 928 字节
- 请求的都是 `_next/static` 路径

### 根本原因

**Nginx 配置**（错误）:
```nginx
# Next.js 静态资源
location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;  # ❌ 端口错误
    ...
}

# 前端应用
location / {
    proxy_pass http://127.0.0.1:3000;  # ❌ 端口错误
    ...
}
```

**实际服务端口**:
```bash
$ systemctl status health-frontend
...
Jan 23 15:05:31 ETH2 npm[1658370]:    - Local:        http://localhost:30001
Jan 23 15:05:31 ETH2 npm[1658370]:    - Network:      http://0.0.0.0:30001
```

**问题**: Next.js 服务运行在端口 **30001**，但 nginx 配置代理到端口 **3000**，导致连接失败返回 400 错误。

## ✅ 解决方案

### 修复 Nginx 配置

**修改前**:
```nginx
location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;  # ❌
    ...
}

location / {
    proxy_pass http://127.0.0.1:3000;  # ❌
    ...
}
```

**修改后**:
```nginx
location /_next/static/ {
    proxy_pass http://127.0.0.1:30001;  # ✅
    ...
}

location / {
    proxy_pass http://127.0.0.1:30001;  # ✅
    ...
}
```

### 执行的操作

```bash
# 1. 备份配置
cp /etc/nginx/conf.d/health.westwetlandtech.com.conf \
   /etc/nginx/conf.d/health.westwetlandtech.com.conf.backup-20260123-150746

# 2. 修改端口
sed -i 's/proxy_pass http:\/\/127.0.0.1:3000/proxy_pass http:\/\/127.0.0.1:30001/g' \
    /etc/nginx/conf.d/health.westwetlandtech.com.conf

# 3. 测试配置
nginx -t

# 4. 重新加载 nginx
systemctl reload nginx
```

## 📊 修复前后对比

### 修复前

| 请求 | 状态码 | 响应大小 | 结果 |
|------|--------|---------|------|
| `/_next/static/chunks/webpack-*.js` | 400 | 928 字节 | ❌ 失败 |
| `/_next/static/chunks/app/page-*.js` | 400 | 928 字节 | ❌ 失败 |
| `/_next/static/css/*.css` | 400 | 928 字节 | ❌ 失败 |

**问题**: 端口不匹配，nginx 无法连接到 Next.js 服务

### 修复后

| 请求 | 状态码 | 响应大小 | 结果 |
|------|--------|---------|------|
| `/_next/static/chunks/webpack-*.js` | 200/404 | 正常 | ✅ 正常 |
| `/_next/static/chunks/app/page-*.js` | 200/404 | 正常 | ✅ 正常 |
| `/_next/static/css/*.css` | 200/404 | 正常 | ✅ 正常 |

**说明**: 
- 200: 文件存在，正常返回
- 404: 文件不存在（可能是旧版本的文件，正常现象）

## 🔧 完整的 Nginx 配置

```nginx
server {
    listen 443 ssl;
    server_name health.westwetlandtech.com;
    ssl_certificate /etc/letsencrypt/live/westwetlandtech.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/westwetlandtech.com/privkey.pem;

    # 上传文件直接访问
    location /api/v1/upload/files/ {
        proxy_pass http://127.0.0.1:8000/api/v1/upload/files/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端API - /api/v1/
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # 后端API - /api/ (兼容旧版)
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Next.js 静态资源 - ✅ 端口 30001
    location /_next/static/ {
        proxy_pass http://127.0.0.1:30001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        
        # 禁用缓存，确保总是获取最新文件
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
        expires off;
    }

    # 前端应用 - ✅ 端口 30001
    location / {
        proxy_pass http://127.0.0.1:30001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # HTML 页面不缓存
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }
}
```

## 📝 服务端口配置

### 前端服务

**服务名**: `health-frontend.service`  
**运行端口**: `30001`  
**启动命令**: `next start -H 0.0.0.0 -p 30001`

**配置文件**: `/etc/systemd/system/health-frontend.service`
```ini
[Service]
ExecStart=/usr/bin/npm run start -- -H 0.0.0.0 -p 30001
WorkingDirectory=/opt/health-app/frontend
```

### 后端服务

**服务名**: `health-backend.service`  
**运行端口**: `8000`  
**启动命令**: `uvicorn main:app --host 127.0.0.1 --port 8000`

## 🔍 如何诊断类似问题

### 1. 检查服务实际运行端口

```bash
# 查看服务状态
systemctl status health-frontend

# 查看监听端口
ss -tulpn | grep node
```

### 2. 检查 Nginx 配置

```bash
# 查看配置文件
cat /etc/nginx/conf.d/health.westwetlandtech.com.conf

# 查找 proxy_pass 配置
grep -n 'proxy_pass' /etc/nginx/conf.d/health.westwetlandtech.com.conf
```

### 3. 检查访问日志

```bash
# 查看最近的 400 错误
tail -100 /var/log/nginx/access.log | grep ' 400 '

# 查看特定路径的请求
tail -100 /var/log/nginx/access.log | grep '_next/static'
```

### 4. 测试端口连接

```bash
# 测试端口是否可访问
curl http://127.0.0.1:30001/
curl http://127.0.0.1:3000/  # 应该失败
```

## 📌 注意事项

### 1. 端口一致性

- ✅ Nginx `proxy_pass` 端口必须与服务实际运行端口一致
- ✅ 检查 systemd 服务配置中的端口参数
- ✅ 检查应用启动命令中的端口参数

### 2. 配置修改后的操作

```bash
# 1. 测试配置
nginx -t

# 2. 重新加载（不中断服务）
systemctl reload nginx

# 3. 重启（完全重启）
systemctl restart nginx
```

### 3. 备份配置

- 修改前总是备份配置文件
- 使用时间戳命名备份文件
- 保留多个版本的备份

## 🎉 完成状态

- ✅ 定位问题：Nginx 端口配置错误
- ✅ 修复配置：端口从 3000 改为 30001
- ✅ 测试验证：主页正常访问
- ✅ 重新加载：Nginx 配置已生效

---

**修复完成！**

现在访问 https://health.westwetlandtech.com/ 应该不会再出现 400 错误，所有静态资源都能正常加载。
