# Executor.Life 域名迁移文档

## 📋 迁移概述

**目标**: 将健康管理系统从 `health.westwetlandtech.com` 迁移到 `health.executor.life`  
**策略**: 双域名并存，新功能使用新域名，保留旧域名兼容性  
**时间**: 2026-01-24

---

## 🌐 域名配置

### 新域名
- **主域名**: `health.executor.life`
- **用途**: 健康管理系统主站
- **SSL 证书**: `/etc/letsencrypt/live/executor.life/` (通配符证书)

### 旧域名（保留）
- **主域名**: `health.westwetlandtech.com`
- **状态**: 继续可用，不做变更
- **SSL 证书**: `/etc/letsencrypt/live/westwetlandtech.com/`

---

## 🔧 服务器配置

### 1. Nginx 配置

#### 新增配置文件
**文件**: `/etc/nginx/conf.d/health.executor.life.conf`

```nginx
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name health.executor.life;
    
    location /.well-known/acme-challenge/ {
        root /var/www/executor.life;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 主配置
server {
    listen 443 ssl http2;
    server_name health.executor.life;
    
    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/executor.life/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/executor.life/privkey.pem;
    
    # SSL 优化配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 上传文件直接访问
    location /api/v1/upload/files/ {
        proxy_pass http://127.0.0.1:8000/api/v1/upload/files/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端API - /api/v1/ 直接代理
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

    # Next.js 静态资源 - 禁用缓存
    location /_next/static/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
        expires off;
    }

    # 前端应用
    location / {
        proxy_pass http://127.0.0.1:3000;
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

#### 旧配置文件（保留）
**文件**: `/etc/nginx/conf.d/health.westwetlandtech.com.conf`  
**状态**: 保持不变，继续提供服务

---

## 💻 代码修改

### 1. 前端 Web (Next.js)

#### `/frontend/src/services/api.ts`
```typescript
// 修改前
const API_BASE_URL = isNativeApp 
  ? 'https://health.westwetlandtech.com/api'
  : (process.env.NEXT_PUBLIC_API_BASE_URL || '/api');

// 修改后
const API_BASE_URL = isNativeApp 
  ? 'https://health.executor.life/api'  // 新域名
  : (process.env.NEXT_PUBLIC_API_BASE_URL || '/api');
```

### 2. 小程序

#### `/packages/mini-program/src/services/request.ts`
```typescript
// 修改前
const BASE_URL = 'https://health.westwetlandtech.com/api';

// 修改后
const BASE_URL = 'https://health.executor.life/api';
```

#### `/packages/mini-program/src/pages/privacy/index.tsx`
```tsx
// 修改前
<Text className="contact-item">🌐 网站：https://health.westwetlandtech.com</Text>

// 修改后
<Text className="contact-item">🌐 网站：https://health.executor.life</Text>
```

#### `/packages/mini-program/src/pages/diet/index.tsx`
```typescript
// 修改前
const fullImageUrl = meal.image_url 
  ? (meal.image_url.startsWith('http') 
      ? meal.image_url 
      : `https://health.westwetlandtech.com${meal.image_url}`)
  : null;

// 修改后
const fullImageUrl = meal.image_url 
  ? (meal.image_url.startsWith('http') 
      ? meal.image_url 
      : `https://health.executor.life${meal.image_url}`)
  : null;
```

#### `/packages/mini-program/src/pages/huawei/index.tsx`
```typescript
// 修改前
const result = await get<{ auth_url: string; state: string }>('/devices/huawei/oauth/authorize', {
  redirect_uri: 'https://health.westwetlandtech.com/api/devices/huawei/oauth/callback'
});

// 修改后
const result = await get<{ auth_url: string; state: string }>('/devices/huawei/oauth/authorize', {
  redirect_uri: 'https://health.executor.life/api/devices/huawei/oauth/callback'
});
```

---

## 📦 部署步骤

### 1. 服务器端配置

```bash
# 1. 连接服务器
ssh root@health.westwetlandtech.com

# 2. 创建 Nginx 配置
vim /etc/nginx/conf.d/health.executor.life.conf
# (粘贴上面的配置内容)

# 3. 测试 Nginx 配置
nginx -t

# 4. 重新加载 Nginx
systemctl reload nginx

# 5. 验证配置生效
curl -I https://health.executor.life/
```

### 2. DNS 配置

**需要在域名服务商添加 DNS 记录**:

```
类型: A
主机记录: health
记录值: 39.98.206.178
TTL: 600
```

### 3. SSL 证书申请（可选）

如果需要独立证书（当前使用通配符证书）:

```bash
certbot certonly --webroot \
  -w /var/www/executor.life \
  -d health.executor.life \
  --non-interactive \
  --agree-tos \
  --email liqiuhua@gmail.com
```

### 4. 代码部署

```bash
# 1. 提交代码
git add -A
git commit -m "feat: 迁移到 executor.life 域名"
git push

# 2. 服务器部署
ssh root@health.westwetlandtech.com
cd /opt/health-app

# 3. 拉取最新代码
git pull

# 4. 部署前端
cd frontend
npm run build
pm2 restart health-frontend

# 5. 部署小程序（本地编译上传）
# 在本地执行：
cd packages/mini-program
npm run build:weapp
# 然后通过微信开发者工具上传
```

---

## ✅ 验证清单

### 服务器验证

```bash
# 1. 检查 Nginx 配置
nginx -t

# 2. 检查配置文件
ls -lh /etc/nginx/conf.d/health.*.conf

# 3. 检查 SSL 证书
certbot certificates | grep executor.life

# 4. 测试 HTTPS 访问
curl -I https://health.executor.life/

# 5. 测试 API 访问
curl -I https://health.executor.life/api/v1/health
```

### 功能验证

- [ ] Web 端首页访问正常
- [ ] Web 端登录功能正常
- [ ] Web 端 API 调用正常
- [ ] 小程序 API 调用正常
- [ ] 小程序图片显示正常
- [ ] 华为设备授权回调正常
- [ ] 性能监控数据上报正常

---

## 🔄 回滚方案

如果新域名出现问题，可以快速回滚：

### 1. 代码回滚

```bash
# 1. 回滚前端代码
cd /Users/liqiuhua/work/personal/health-llm-driven
git revert HEAD
git push

# 2. 服务器重新部署
ssh root@health.westwetlandtech.com
cd /opt/health-app
git pull
cd frontend
npm run build
pm2 restart health-frontend
```

### 2. Nginx 回滚

```bash
# 禁用新域名配置
mv /etc/nginx/conf.d/health.executor.life.conf \
   /etc/nginx/conf.d/health.executor.life.conf.disabled

# 重新加载 Nginx
systemctl reload nginx
```

---

## 📊 域名对比

| 项目 | 旧域名 | 新域名 |
|------|--------|--------|
| **Web 主站** | health.westwetlandtech.com | health.executor.life |
| **API 端点** | health.westwetlandtech.com/api | health.executor.life/api |
| **SSL 证书** | westwetlandtech.com | executor.life |
| **证书类型** | 单域名 | 通配符 |
| **状态** | 保留可用 | 新主域名 |

---

## 🔐 SSL 证书信息

### Executor.Life 证书

```
Certificate Name: executor.life
Serial Number: 58b6598186ee1ec5c83cdfed5475566868d
Key Type: RSA
Domains: executor.life
Expiry Date: 2026-04-21 06:04:37+00:00 (VALID: 87 days)
Certificate Path: /etc/letsencrypt/live/executor.life/fullchain.pem
Private Key Path: /etc/letsencrypt/live/executor.life/privkey.pem
```

### WestWetlandTech 证书（保留）

```
Certificate Name: health.westwetlandtech.com
Serial Number: 617885922285592009da58a5589de76005f
Key Type: RSA
Domains: health.westwetlandtech.com
Expiry Date: 2026-04-05 05:38:32+00:00 (VALID: 71 days)
```

---

## 📝 注意事项

### 1. DNS 传播时间
- DNS 记录修改后，全球生效需要 **0-48 小时**
- 建议在低峰期进行域名切换
- 可以使用 `dig health.executor.life` 检查 DNS 解析

### 2. 微信小程序域名配置
需要在微信公众平台添加新域名到服务器域名白名单：
- **request 合法域名**: `https://health.executor.life`
- **uploadFile 合法域名**: `https://health.executor.life`
- **downloadFile 合法域名**: `https://health.executor.life`

### 3. 第三方服务回调
以下服务需要更新回调 URL：
- ✅ 华为健康 OAuth 回调
- ⚠️ Garmin Connect（如果有配置）
- ⚠️ 其他第三方集成

### 4. 缓存清理
域名切换后，建议清理：
- 浏览器缓存
- CDN 缓存（如果使用）
- 小程序缓存（重新编译上传）

---

## 🎯 后续优化

### 1. 域名重定向
可以考虑将旧域名重定向到新域名：

```nginx
# 在 health.westwetlandtech.com.conf 中添加
server {
    listen 443 ssl;
    server_name health.westwetlandtech.com;
    
    # ... SSL 配置 ...
    
    # 301 永久重定向到新域名
    return 301 https://health.executor.life$request_uri;
}
```

### 2. HSTS 配置
增强安全性：

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### 3. 监控告警
配置域名监控：
- SSL 证书过期提醒
- 域名解析监控
- 服务可用性监控

---

## 📅 迁移时间线

| 时间 | 操作 | 状态 |
|------|------|------|
| 2026-01-24 12:00 | 创建 Nginx 配置 | ✅ 完成 |
| 2026-01-24 12:10 | 修改前端代码 | ✅ 完成 |
| 2026-01-24 12:15 | 修改小程序代码 | ✅ 完成 |
| 待定 | 配置 DNS 记录 | ⏳ 待用户操作 |
| 待定 | 部署到生产环境 | ⏳ 待 DNS 生效 |
| 待定 | 微信小程序域名配置 | ⏳ 待部署完成 |
| 待定 | 功能验证 | ⏳ 待部署完成 |

---

## 🆘 问题排查

### 问题 1: 域名无法访问
```bash
# 检查 DNS 解析
dig health.executor.life

# 检查 Nginx 配置
nginx -t
systemctl status nginx

# 检查端口监听
netstat -tlnp | grep :443
```

### 问题 2: SSL 证书错误
```bash
# 检查证书有效期
certbot certificates

# 重新申请证书
certbot certonly --webroot -w /var/www/executor.life -d health.executor.life
```

### 问题 3: API 调用失败
```bash
# 检查后端服务
pm2 status
pm2 logs health-backend

# 测试 API 端点
curl -I https://health.executor.life/api/v1/health
```

---

**迁移状态**: 🟡 配置完成，等待 DNS 配置  
**文档版本**: 1.0  
**更新时间**: 2026-01-24 12:30 (北京时间)
