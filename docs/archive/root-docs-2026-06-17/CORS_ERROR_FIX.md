# CORS 错误修复

## 🐛 问题描述

**错误信息**:
```
Access to fetch at 'https://health.westwetlandtech.com/api/review/stats/streak' 
from origin 'https://health.executor.life' has been blocked by CORS policy: 
Response to preflight request doesn't pass access control check: 
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

**发生场景**:
- 用户访问 `https://health.executor.life/review`
- 前端尝试请求 `https://health.westwetlandtech.com/api/review/stats/streak`
- 浏览器阻止跨域请求

---

## 🔍 根本原因

### 问题分析

在 `frontend/src/app/review/page.tsx` 中硬编码了旧域名：

```typescript
// ❌ 错误的代码
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://health.westwetlandtech.com/api';
```

**导致的问题**:
1. 用户访问 `health.executor.life`
2. 前端请求发送到 `health.westwetlandtech.com`
3. 浏览器检测到跨域请求
4. 服务器没有配置 CORS 头允许跨域
5. 请求被阻止

### 为什么会跨域？

```
前端域名: https://health.executor.life
API 域名:  https://health.westwetlandtech.com
          ↑ 不同的域名 → 触发 CORS 检查
```

---

## ✅ 解决方案

### 修复代码

**修改前**:
```typescript
// Nginx 配置 /api/ → /api/v1/，所以这里不需要 /v1
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://health.westwetlandtech.com/api';
```

**修改后**:
```typescript
// 使用相对路径，依赖 Nginx 反向代理
const API_BASE = '/api';
```

### 为什么这样可以解决？

#### 1. 使用相对路径
```typescript
const API_BASE = '/api';  // 相对路径
```

#### 2. 请求流程
```
用户访问: https://health.executor.life/review
前端请求: /api/review/stats/streak
         ↓
浏览器解析为: https://health.executor.life/api/review/stats/streak
         ↓ (同域名，无 CORS 问题)
Nginx 接收: https://health.executor.life/api/review/stats/streak
         ↓
Nginx 代理: http://127.0.0.1:8000/api/v1/review/stats/streak
         ↓
FastAPI 处理并返回
```

#### 3. 关键点
- ✅ **同域名**: 前端和 API 都是 `health.executor.life`
- ✅ **无跨域**: 浏览器不会触发 CORS 检查
- ✅ **Nginx 代理**: 服务器内部转发到后端

---

## 🔧 Nginx 配置

### 反向代理配置

**文件**: `/etc/nginx/conf.d/health.executor.life.conf`

```nginx
server {
    listen 443 ssl http2;
    server_name health.executor.life;
    
    # 后端 API - /api/v1/ 直接代理
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

    # 后端 API - /api/ 映射到 /api/v1/ （兼容旧版）
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
    
    # 前端应用
    location / {
        proxy_pass http://127.0.0.1:3000;
        # ...
    }
}
```

---

## 📝 其他文件检查

### 已正确配置的文件

#### 1. `frontend/src/services/api.ts`
```typescript
// ✅ 正确的配置
const API_BASE_URL = isNativeApp 
  ? 'https://health.executor.life/api'  // 原生App使用完整URL
  : (process.env.NEXT_PUBLIC_API_BASE_URL || '/api');  // Web使用相对路径
```

#### 2. `frontend/src/app/admin/performance/page.tsx`
```typescript
// ✅ 正确的配置
const response = await fetch(`/api/v1/performance/overview?${params}`, {
  headers: { Authorization: `Bearer ${token}` }
});
```

### 需要注意的模式

#### ✅ 正确的做法
```typescript
// Web 端 - 使用相对路径
const API_BASE = '/api';

// 原生 App - 使用完整 URL
const API_BASE = 'https://health.executor.life/api';
```

#### ❌ 错误的做法
```typescript
// 硬编码域名 - 会导致 CORS 问题
const API_BASE = 'https://health.westwetlandtech.com/api';
```

---

## 🚀 部署记录

### 1. 代码修改
```bash
git add frontend/src/app/review/page.tsx
git commit -m "fix: 修复 review 页面 CORS 错误"
git push
```

**Commit**: `2fa6a99`

### 2. 服务器部署
```bash
ssh root@health.westwetlandtech.com
cd /opt/health-app
git pull
cd frontend
npm run build
pm2 restart health-frontend
```

**部署时间**: 2026-01-24 12:45  
**构建状态**: ✅ 成功  
**服务状态**: ✅ 在线

---

## ✅ 验证结果

### 测试步骤

1. 访问 `https://health.executor.life/review`
2. 打开浏览器开发者工具 (F12)
3. 切换到 Network 标签
4. 刷新页面
5. 查看 API 请求

### 预期结果

**修复前**:
```
❌ Request URL: https://health.westwetlandtech.com/api/review/stats/streak
❌ Status: (failed) net::ERR_FAILED
❌ CORS error
```

**修复后**:
```
✅ Request URL: https://health.executor.life/api/review/stats/streak
✅ Status: 200 OK
✅ No CORS error
```

---

## 🎓 CORS 知识点

### 什么是 CORS？

**CORS** (Cross-Origin Resource Sharing) - 跨域资源共享

浏览器的安全机制，限制从一个域名的网页访问另一个域名的资源。

### 何时触发 CORS？

当以下任一项不同时：
- **协议**: `http` vs `https`
- **域名**: `executor.life` vs `westwetlandtech.com`
- **端口**: `:80` vs `:443`

### 如何解决 CORS？

#### 方案 1: 服务器配置 CORS 头（不推荐）
```python
# FastAPI
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://health.executor.life"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**缺点**: 需要维护允许的域名列表

#### 方案 2: 使用相对路径 + Nginx 代理（推荐）✅
```typescript
// 前端使用相对路径
const API_BASE = '/api';
```

```nginx
# Nginx 反向代理
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/v1/;
}
```

**优点**:
- ✅ 无 CORS 问题
- ✅ 无需配置 CORS 头
- ✅ 更安全
- ✅ 更简单

---

## 📊 影响范围

### 修复的页面
- ✅ `/review` - 每日复盘页面

### 不受影响的页面
- ✅ 其他页面已使用相对路径或正确配置

---

## 🔍 排查方法

### 1. 检查 Network 请求
```
F12 → Network → 查看请求 URL
```

### 2. 搜索硬编码域名
```bash
grep -r "health.westwetlandtech.com" frontend/src/
grep -r "health.executor.life" frontend/src/
```

### 3. 检查 API 配置
```typescript
// 查找 API_BASE 或 baseURL 配置
const API_BASE = ...
const baseURL = ...
```

---

## 📚 相关文档

- `EXECUTOR_LIFE_DOMAIN_MIGRATION.md` - 域名迁移文档
- `PERFORMANCE_API_PATH_FIX.md` - 性能监控 API 修复
- `frontend/src/services/api.ts` - API 配置文件

---

## 🎯 最佳实践

### 前端 API 配置

```typescript
// ✅ 推荐：使用相对路径
const API_BASE = '/api';

// ✅ 推荐：根据环境判断
const API_BASE = isNativeApp 
  ? 'https://health.executor.life/api'  // 原生App
  : '/api';  // Web端

// ❌ 避免：硬编码域名
const API_BASE = 'https://health.westwetlandtech.com/api';
```

### Nginx 配置

```nginx
# ✅ 配置反向代理
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/v1/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 🆘 故障排查清单

遇到 CORS 错误时：

- [ ] 检查前端是否使用相对路径
- [ ] 检查是否硬编码了域名
- [ ] 检查 Nginx 反向代理配置
- [ ] 检查后端服务是否运行
- [ ] 检查浏览器 Network 标签的请求 URL
- [ ] 清除浏览器缓存重试

---

**修复状态**: ✅ 完成  
**部署状态**: ✅ 已上线  
**验证状态**: ⏳ 待用户测试  
**文档时间**: 2026-01-24 12:50
