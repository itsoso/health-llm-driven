# Nginx API /v1/ 路径重复问题修复

**问题时间**: 2026-01-23  
**错误**: 404 Not Found  
**请求路径**: `/api/v1/diet-recommendation/me`

## 🐛 问题描述

前端请求 `https://health.westwetlandtech.com/api/v1/diet-recommendation/me` 时返回 404 错误。

## 🔍 问题根源

### Nginx 配置问题

**原配置**:
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/v1/;
}
```

### 问题分析

当请求 `/api/v1/diet-recommendation/me` 时：

1. **匹配规则**: `/api/` 
2. **去掉前缀**: 去掉 `/api/`，剩下 `v1/diet-recommendation/me`
3. **添加到目标**: `http://127.0.0.1:8000/api/v1/` + `v1/diet-recommendation/me`
4. **最终路径**: `http://127.0.0.1:8000/api/v1/v1/diet-recommendation/me` ❌

**结果**: 路径中 `v1` 重复了，导致 404！

### 正确的路径应该是

```
http://127.0.0.1:8000/api/v1/diet-recommendation/me
```

## ✅ 解决方案

### 修改 Nginx 配置

添加一个更具体的 `/api/v1/` 规则，优先级高于 `/api/`：

```nginx
# 后端API - /api/v1/ 直接代理（新增，优先级高）
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

# 后端API - /api/ 映射到 /api/v1/ （兼容旧版）
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
```

### 工作原理

#### 请求 `/api/v1/diet-recommendation/me`

1. **匹配规则**: `/api/v1/` （更具体，优先匹配）
2. **去掉前缀**: 去掉 `/api/v1/`，剩下 `diet-recommendation/me`
3. **添加到目标**: `http://127.0.0.1:8000/api/v1/` + `diet-recommendation/me`
4. **最终路径**: `http://127.0.0.1:8000/api/v1/diet-recommendation/me` ✅

#### 请求 `/api/diet-recommendation/me` (旧版)

1. **匹配规则**: `/api/` （兼容旧版）
2. **去掉前缀**: 去掉 `/api/`，剩下 `diet-recommendation/me`
3. **添加到目标**: `http://127.0.0.1:8000/api/v1/` + `diet-recommendation/me`
4. **最终路径**: `http://127.0.0.1:8000/api/v1/diet-recommendation/me` ✅

## 📝 修复步骤

### 1. 更新 Nginx 配置

```bash
# 编辑配置文件
vim /etc/nginx/conf.d/health.westwetlandtech.com.conf

# 在 location /api/ 之前添加 location /api/v1/ 规则
```

### 2. 测试配置

```bash
nginx -t
```

**预期输出**:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 3. 重新加载 Nginx

```bash
systemctl reload nginx
```

### 4. 验证修复

```bash
# 测试 API 访问
curl -I https://health.westwetlandtech.com/api/v1/diet-recommendation/me

# 预期: HTTP/2 401 (需要认证，说明路由可访问)
```

## 📊 验证结果

### 修复前

```bash
$ curl -s -o /dev/null -w '%{http_code}' \
  https://health.westwetlandtech.com/api/v1/diet-recommendation/me

404  # ❌ Not Found
```

### 修复后

```bash
$ curl -s -o /dev/null -w '%{http_code}' \
  https://health.westwetlandtech.com/api/v1/diet-recommendation/me

401  # ✅ Unauthorized (路由可访问，需要 token)
```

## 🎯 Nginx Location 匹配规则

### 优先级（从高到低）

1. **精确匹配**: `location = /path`
2. **前缀匹配（优先）**: `location ^~ /path`
3. **正则匹配**: `location ~ /path` 或 `location ~* /path`
4. **前缀匹配**: `location /path`

### 本次修复

```nginx
location /api/v1/  { ... }  # 更长的前缀，优先匹配
location /api/     { ... }  # 较短的前缀，次级匹配
```

**规则**: 当多个前缀匹配时，Nginx 选择**最长匹配**的规则。

## 🔧 完整的 Nginx 配置

```nginx
server {
    listen 443 ssl;
    server_name health.westwetlandtech.com;
    
    # 上传文件（最具体）
    location /api/v1/upload/files/ {
        proxy_pass http://127.0.0.1:8000/api/v1/upload/files/;
        ...
    }

    # API v1（新增，优先级高）
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        ...
    }

    # API 通用（兼容旧版）
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        ...
    }

    # Next.js 静态资源
    location /_next/static/ {
        proxy_pass http://127.0.0.1:3000;
        ...
    }

    # 前端应用
    location / {
        proxy_pass http://127.0.0.1:3000;
        ...
    }
}
```

## 💡 经验教训

### 1. Nginx 路径重写要小心

当使用 `proxy_pass` 时，如果目标 URL 包含路径，Nginx 会进行路径替换：

```nginx
# ❌ 错误示例
location /api/ {
    proxy_pass http://backend/api/v1/;
}
# /api/v1/xxx → /api/v1/v1/xxx

# ✅ 正确示例 1: 添加更具体的规则
location /api/v1/ {
    proxy_pass http://backend/api/v1/;
}

# ✅ 正确示例 2: 不在 proxy_pass 中重复路径
location /api/v1/ {
    proxy_pass http://backend;  # 不添加路径
}
```

### 2. 测试要全面

修改 Nginx 配置后，要测试：
- ✅ 新路径 (`/api/v1/xxx`)
- ✅ 旧路径 (`/api/xxx`)
- ✅ 特殊路径 (`/api/v1/upload/files/`)

### 3. 使用 curl 调试

```bash
# 查看完整的请求和响应
curl -v https://example.com/api/v1/xxx

# 只看状态码
curl -s -o /dev/null -w '%{http_code}' https://example.com/api/v1/xxx

# 查看响应头
curl -I https://example.com/api/v1/xxx
```

## 📄 相关文档

- `DIET_RECOMMENDATION_404_FIX.md` - 饮食推荐 404 修复
- `/etc/nginx/conf.d/health.westwetlandtech.com.conf` - Nginx 配置文件

## ✅ 修复完成

- ✅ Nginx 配置已更新
- ✅ 配置语法检查通过
- ✅ Nginx 已重新加载
- ✅ API 路由可访问 (401)
- ✅ 前端可以正常请求

---

**修复完成时间**: 2026-01-23 09:51  
**Nginx 状态**: ✅ Running  
**API 状态**: ✅ Accessible (401 需要 token)
