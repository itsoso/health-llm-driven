# 快速修复 CSS 404 错误

## 🐛 问题
```
GET https://health.westwetlandtech.com/_next/static/css/1a677b9a21037a19.css 
net::ERR_ABORTED 404 (Not Found)
```

## 📋 原因
Next.js 在每次构建时会生成新的静态文件名（带 hash），但浏览器缓存了旧的 HTML，导致请求的 CSS 文件名不存在。

## ✅ 解决方案

### 方案 1: 清除浏览器缓存（推荐）

#### Chrome/Edge
1. 按 `Ctrl + Shift + Delete` (Windows) 或 `Cmd + Shift + Delete` (Mac)
2. 选择「缓存的图片和文件」
3. 点击「清除数据」
4. 刷新页面

#### 或者使用硬刷新
- Windows: `Ctrl + Shift + R` 或 `Ctrl + F5`
- Mac: `Cmd + Shift + R`

### 方案 2: 无痕模式测试
1. 打开无痕/隐私窗口
2. 访问 https://health.westwetlandtech.com/diet-recommendation
3. 应该可以正常加载

### 方案 3: 重启 PM2 服务（服务器端）
```bash
ssh root@39.98.206.178 "pm2 restart health-frontend"
```

## 🔍 验证修复

### 1. 检查 Network 标签
打开浏览器开发者工具（F12）→ Network 标签

**应该看到**:
```
✅ 200 /diet-recommendation
✅ 200 /_next/static/css/741d2ff999d88a97.css
✅ 200 /_next/static/css/fc1c9daac70c093b.css
✅ 200 /api/v1/diet-recommendation/me
```

### 2. 检查页面显示
应该看到：
- ✅ 个人信息卡片
- ✅ 代谢信息卡片
- ✅ 营养进度条
- ✅ 健康状态
- ✅ 食物推荐

## 📊 当前服务器状态

### 前端服务
- **状态**: ✅ 运行中
- **端口**: 3000
- **进程**: PM2 (health-frontend)

### 静态文件
- **路径**: `/opt/health-app/frontend/.next/static/`
- **CSS 文件**: 
  - ✅ 741d2ff999d88a97.css (79KB)
  - ✅ fc1c9daac70c093b.css (10KB)

### Nginx 配置
- **代理**: / → http://127.0.0.1:3000
- **状态**: ✅ 正常

## 🎯 如果问题仍然存在

### 检查 PM2 日志
```bash
ssh root@39.98.206.178 "pm2 logs health-frontend --lines 50"
```

### 检查 Nginx 日志
```bash
ssh root@39.98.206.178 "tail -50 /var/log/nginx/error.log"
```

### 完全重启服务
```bash
ssh root@39.98.206.178 "
  cd /opt/health-app/frontend && 
  pm2 stop health-frontend && 
  pm2 delete health-frontend && 
  pm2 start npm --name health-frontend -- start && 
  pm2 save
"
```

## 💡 预防措施

### 1. 禁用缓存（开发环境）
在浏览器开发者工具中：
- Network 标签
- 勾选「Disable cache」
- 保持开发者工具打开

### 2. 使用版本号
在 URL 后添加时间戳：
```
https://health.westwetlandtech.com/diet-recommendation?v=20260122
```

### 3. 配置 Nginx 缓存策略
```nginx
location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;
    proxy_cache_valid 200 365d;
    add_header Cache-Control "public, immutable, max-age=31536000";
}
```

## ✅ 总结

**最快的解决方法**：
1. 按 `Ctrl + Shift + R` (或 `Cmd + Shift + R`) 硬刷新
2. 如果不行，清除浏览器缓存
3. 如果还不行，使用无痕模式测试

**根本原因**：浏览器缓存了旧的 HTML

**是否需要重新部署**：❌ 不需要，服务器端已经是最新的

---

**更新时间**: 2026-01-22 23:56

**状态**: ✅ 服务器端正常，只需清除浏览器缓存
