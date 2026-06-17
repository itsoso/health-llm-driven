# Nginx 端口配置修复记录

**修复时间**: 2026-01-22 16:20

## 问题描述

### 错误信息
```
ChunkLoadError: Loading chunk 3185 failed.
(error: https://health.westwetlandtech.com/_next/static/chunks/app/layout-77bf1437145a86ba.js)
```

### 根本原因
Nginx 配置文件中前端应用的代理端口配置错误：
- **配置的端口**: 3000
- **实际运行端口**: 30001

导致 Nginx 无法正确代理到前端服务，静态资源加载失败。

## 问题排查过程

### 1. 检查前端服务状态
```bash
systemctl status health-frontend
```
✅ 服务正常运行在端口 30001

### 2. 检查静态文件
```bash
ls -lh /opt/health-app/frontend/.next/static/chunks/app/
```
✅ 文件存在且正确生成

### 3. 检查 Nginx 配置
```bash
cat /etc/nginx/conf.d/health.westwetlandtech.com.conf
```
❌ 发现端口配置错误：
```nginx
# 错误配置
location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;  # ← 错误端口
}

location / {
    proxy_pass http://127.0.0.1:3000;  # ← 错误端口
}
```

## 修复方案

### 修复命令
```bash
ssh root@39.98.206.178 "
  sed -i 's/proxy_pass http:\/\/127.0.0.1:3000/proxy_pass http:\/\/127.0.0.1:30001/g' \
    /etc/nginx/conf.d/health.westwetlandtech.com.conf && \
  nginx -t && \
  systemctl reload nginx
"
```

### 修复后的配置
```nginx
# 正确配置
location /_next/static/ {
    proxy_pass http://127.0.0.1:30001;  # ✅ 正确端口
}

location / {
    proxy_pass http://127.0.0.1:30001;  # ✅ 正确端口
}
```

## 验证结果

✅ **Nginx 配置测试通过**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

✅ **Nginx 重新加载成功**

✅ **前端资源可以正常访问**

## 完整的 Nginx 配置

```nginx
server {
    if ($host = health.westwetlandtech.com) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    server_name health.westwetlandtech.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/westwetlandtech;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name health.westwetlandtech.com;
    ssl_certificate /etc/letsencrypt/live/westwetlandtech.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/westwetlandtech.com/privkey.pem;

    # 后端API - /api/ 映射到 /api/v1/
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
        proxy_pass http://127.0.0.1:30001;  # ✅ 修复后
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        
        # 禁用缓存，确保总是获取最新文件
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
        expires off;
    }

    # 前端应用
    location / {
        proxy_pass http://127.0.0.1:30001;  # ✅ 修复后
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

## 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 (Next.js) | 30001 | 健康应用前端服务 |
| 后端 (FastAPI) | 8000 | 健康应用后端 API |
| Nginx | 80/443 | 反向代理和 SSL 终止 |

## 用户操作建议

如果用户仍然遇到加载错误，建议：

### 1. 强制刷新浏览器
- **Chrome/Edge**: `Ctrl + Shift + R` (Windows) 或 `Cmd + Shift + R` (Mac)
- **Firefox**: `Ctrl + F5` (Windows) 或 `Cmd + Shift + R` (Mac)
- **Safari**: `Cmd + Option + R` (Mac)

### 2. 清除浏览器缓存
1. 打开浏览器设置
2. 找到"清除浏览数据"或"清除缓存"
3. 选择"缓存的图片和文件"
4. 清除最近 1 小时或全部时间的数据

### 3. 无痕模式测试
打开浏览器的无痕/隐私模式访问网站，验证问题是否解决

## 预防措施

### 1. 配置管理
将 Nginx 配置纳入版本控制：
```bash
# 备份配置
cp /etc/nginx/conf.d/health.westwetlandtech.com.conf \
   /opt/health-app/nginx/health.westwetlandtech.com.conf

# 添加到 Git
cd /opt/health-app
git add nginx/health.westwetlandtech.com.conf
git commit -m "docs: 添加 Nginx 配置到版本控制"
```

### 2. 部署检查清单
在每次部署后检查：
- [ ] 前端服务运行在正确端口
- [ ] Nginx 配置指向正确端口
- [ ] 静态资源可以正常访问
- [ ] API 接口正常工作

### 3. 监控告警
设置监控检查：
```bash
# 检查前端服务
curl -f http://127.0.0.1:30001 || echo "前端服务异常"

# 检查 Nginx 代理
curl -f https://health.westwetlandtech.com || echo "Nginx 代理异常"
```

## 相关文档

- [NAVIGATION_UPDATE_20260122.md](NAVIGATION_UPDATE_20260122.md) - 首次导航栏优化
- [NAVIGATION_RESTRUCTURE_20260122.md](NAVIGATION_RESTRUCTURE_20260122.md) - 导航栏重组

## 经验教训

1. **配置一致性**: 确保 Nginx 配置与实际服务端口一致
2. **配置版本控制**: 将关键配置文件纳入 Git 管理
3. **部署验证**: 部署后立即验证服务是否正常
4. **错误排查**: 遇到前端加载错误，优先检查：
   - 服务是否运行
   - 端口是否正确
   - Nginx 配置是否正确

---

**修复人员**: AI Assistant  
**修复状态**: ✅ 已完成  
**文档版本**: 1.0
