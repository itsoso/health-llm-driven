# 故障排查指南

> 记录项目运行中遇到的问题及解决方案，遇到类似问题时先搜索本文档

---

## 目录

- [前端部署问题](#前端部署问题)
- [后端问题](#后端问题)
- [小程序问题](#小程序问题)

---

## 前端部署问题

### 1. CSS/JS 文件 400 Bad Request 错误

**问题现象**：
```
GET https://health.westwetlandtech.com/_next/static/css/xxx.css net::ERR_ABORTED 400 (Bad Request)
GET https://health.westwetlandtech.com/_next/static/chunks/app/layout-xxx.js net::ERR_ABORTED 400 (Bad Request)
```

**原因分析**：
1. 前端重新构建后，CSS/JS 文件的 hash 值会改变
2. 旧的 HTML 页面（被缓存）仍然引用旧的文件 hash
3. 旧文件已不存在，服务器返回 400 错误

**可能的缓存层**：
- 浏览器缓存
- Nginx 缓存（`proxy_cache_valid` 配置）
- CDN 缓存
- Next.js 服务缓存（未完全重启）

**解决步骤**：

#### 步骤 1：确认服务器代码是最新版本
```bash
ssh root@39.98.206.178 "cd /opt/health-app && git log --oneline -2"
```

如果代码不是最新，强制更新：
```bash
ssh root@39.98.206.178 "cd /opt/health-app && git fetch origin && git reset --hard origin/main"
```

#### 步骤 2：验证前端服务返回的 CSS hash
```bash
# 查看服务返回的 HTML 中引用的 CSS 文件
ssh root@39.98.206.178 "curl -s http://localhost:3000/admin | grep -o '[a-f0-9]\{16\}\.css' | head -1"

# 查看实际存在的 CSS 文件
ssh root@39.98.206.178 "ls /opt/health-app/frontend/.next/static/css/"
```

如果两者不匹配，说明前端服务没有正确重启。

#### 步骤 3：完全重启前端服务
```bash
ssh root@39.98.206.178 "
# 停止服务
systemctl stop health-frontend

# 杀掉残留进程
pkill -f 'next' || true

# 清理构建缓存
cd /opt/health-app/frontend
rm -rf .next

# 重新构建
npm run build

# 启动服务
systemctl start health-frontend
"
```

#### 步骤 4：清理 Nginx 缓存
```bash
ssh root@39.98.206.178 "
# 清理缓存目录
rm -rf /var/cache/nginx/*

# 重启 Nginx
systemctl restart nginx
"
```

#### 步骤 5：检查 Nginx 配置中的缓存设置
```bash
ssh root@39.98.206.178 "cat /etc/nginx/conf.d/health.westwetlandtech.com.conf | grep -A5 '_next'"
```

如果有 `proxy_cache_valid` 配置，考虑禁用或减少缓存时间：
```bash
# 禁用静态资源缓存
sed -i 's/proxy_cache_valid 200 60m;/# proxy_cache_valid 200 60m;/g' /etc/nginx/conf.d/health.westwetlandtech.com.conf
nginx -t && systemctl restart nginx
```

#### 步骤 6：客户端清除缓存
- **无痕模式**：`Cmd+Shift+N` (Mac) / `Ctrl+Shift+N` (Windows)
- **强制刷新**：`Cmd+Shift+R` (Mac) / `Ctrl+Shift+R` (Windows)
- **清除浏览器缓存**：浏览器设置 → 清除缓存

---

### 2. Git Pull 没有更新到最新代码

**问题现象**：
```bash
git pull
# 显示 Already up to date，但代码不是最新
```

**原因**：本地有未提交的更改或分支冲突

**解决方案**：
```bash
# 强制重置到远程最新
git fetch origin
git reset --hard origin/main
```

---

### 3. 部署后页面没有变化

**排查清单**：

1. **确认代码已推送到 GitHub**
   ```bash
   git log --oneline -1  # 本地
   ssh root@39.98.206.178 "cd /opt/health-app && git log --oneline -1"  # 服务器
   ```

2. **确认前端已重新构建**
   ```bash
   ssh root@39.98.206.178 "ls -la /opt/health-app/frontend/.next/static/css/"
   ```

3. **确认服务已重启**
   ```bash
   ssh root@39.98.206.178 "systemctl status health-frontend | head -5"
   ```

4. **测试本地服务响应**
   ```bash
   ssh root@39.98.206.178 "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/"
   ```

---

## 后端问题

### 1. API 返回 500 错误

**排查步骤**：
```bash
# 查看后端日志
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"

# 检查服务状态
ssh root@39.98.206.178 "systemctl status health-backend"
```

### 2. 数据库表不存在

**解决方案**：
```bash
ssh root@39.98.206.178 "
cd /opt/health-app/backend
source venv/bin/activate
python -c 'from app.database import engine, Base; from app.models import *; Base.metadata.create_all(bind=engine)'
"
```

---

## 小程序问题

### 1. WXSS 编译错误：unexpected token `*`

**问题现象**：
```
[ WXSS 文件编译错误] 
./app.wxss(1:124): unexpected token `*`
```

**原因**：微信小程序 WXSS 不支持 `*` 通配符选择器

**解决方案**：移除 SCSS 中的 `*` 选择器
```scss
// ❌ 错误
* {
  outline: none;
}

// ✅ 正确 - 明确指定元素
view, text, button {
  outline: none;
}
```

### 2. TabBar 页面无法用 navigateTo 跳转

**问题现象**：使用 `Taro.navigateTo` 跳转到 TabBar 页面无效

**原因**：TabBar 页面只能用 `switchTab` 跳转

**解决方案**：
```typescript
// ❌ 错误
Taro.navigateTo({ url: '/pages/ai-assistant/index' })

// ✅ 正确
Taro.switchTab({ url: '/pages/ai-assistant/index' })
```

---

## 常用运维命令

### 一键部署
```bash
./deploy.sh           # 部署全部
./deploy.sh -f        # 仅部署前端
./deploy.sh -b        # 仅部署后端
./deploy.sh -s        # 查看服务状态
```

### 服务管理
```bash
# 重启服务
ssh root@39.98.206.178 "systemctl restart health-frontend health-backend"

# 查看状态
ssh root@39.98.206.178 "systemctl status health-frontend health-backend"

# 查看日志
ssh root@39.98.206.178 "journalctl -u health-backend -f"
```

### 清理缓存
```bash
# Nginx 缓存
ssh root@39.98.206.178 "rm -rf /var/cache/nginx/* && systemctl restart nginx"

# Next.js 构建缓存
ssh root@39.98.206.178 "cd /opt/health-app/frontend && rm -rf .next && npm run build"
```

---

## 更新日志

| 日期 | 问题 | 解决方案 |
|------|------|---------|
| 2026-01-18 | CSS 文件 400 错误 | 完全重启前端服务 + 清理 Nginx 缓存 |
| 2026-01-18 | Git pull 未更新 | 使用 `git reset --hard origin/main` |
| 2026-01-18 | WXSS `*` 选择器错误 | 移除通配符选择器 |
