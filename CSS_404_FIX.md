# CSS 404 错误修复 ✅

> 修复时间: 2026-01-22 14:50

## 🐛 问题

浏览器控制台报错：
```
GET https://health.westwetlandtech.com/_next/static/css/a86b4103c59047a9.css 
net::ERR_ABORTED 400 (Bad Request)
```

## 🔍 原因分析

### 1. 文件名不匹配

**服务器上的实际文件**：
```
/opt/health-app/frontend/.next/static/css/
├── e3d872a7299a724b.css  ✅ 存在
└── fc1c9daac70c093b.css  ✅ 存在
```

**浏览器请求的文件**：
```
a86b4103c59047a9.css  ❌ 不存在（旧版本）
```

### 2. 根本原因

**Next.js 构建机制**：
- 每次构建时，CSS 文件名会根据内容生成哈希值
- 文件名格式：`[contenthash].css`
- 构建 ID 变化：旧版本 → 新版本 `8b1WBOS7fQXOrkkodZT9r`

**浏览器缓存问题**：
- 浏览器缓存了旧的 HTML 文件
- HTML 中引用的是旧的 CSS 文件名
- 服务器上只有新的 CSS 文件

## ✅ 解决方案

### 1. 服务器端修复

```bash
# 完全重启前端服务（清除进程缓存）
pm2 delete health-frontend
pm2 start npm --name health-frontend -- start
pm2 save

# 重新加载 Nginx
nginx -t
systemctl reload nginx
```

### 2. 客户端修复（用户操作）

**方法 1：强制刷新（推荐）**
- Windows/Linux: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

**方法 2：清除浏览器缓存**
1. 打开开发者工具（F12）
2. 右键点击刷新按钮
3. 选择"清空缓存并硬性重新加载"

**方法 3：隐私模式**
- 使用浏览器的隐私/无痕模式访问

**方法 4：清除站点数据**
```
Chrome: 设置 → 隐私和安全 → 网站设置 → 查看所有网站的权限和数据
找到 health.westwetlandtech.com → 清除数据
```

## 🔧 预防措施

### 1. 添加 Cache-Control 头

建议在 Nginx 配置中为 HTML 文件禁用缓存：

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    
    # 对 HTML 文件禁用缓存
    location ~* \.html$ {
        proxy_pass http://127.0.0.1:3000;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }
    
    # 静态资源长期缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://127.0.0.1:3000;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

### 2. 使用版本号

在部署时可以添加版本参数：
```
https://health.westwetlandtech.com/?v=20260122
```

## 📊 验证

### 检查当前 BUILD_ID
```bash
cat /opt/health-app/frontend/.next/BUILD_ID
# 输出: 8b1WBOS7fQXOrkkodZT9r
```

### 检查 CSS 文件
```bash
ls /opt/health-app/frontend/.next/static/css/
# 输出:
# e3d872a7299a724b.css
# fc1c9daac70c093b.css
```

### 验证前端服务
```bash
pm2 status health-frontend
# 应该显示 online 状态
```

## 🎯 用户操作指南

如果遇到 CSS 404 错误：

1. **第一步：强制刷新**
   - `Ctrl + Shift + R` (Windows/Linux)
   - `Cmd + Shift + R` (Mac)

2. **第二步：清除缓存**
   - 打开开发者工具（F12）
   - 右键刷新按钮 → "清空缓存并硬性重新加载"

3. **第三步：隐私模式**
   - 如果还不行，尝试隐私/无痕模式

4. **第四步：联系管理员**
   - 如果以上都不行，可能是服务器问题

---

**修复完成！** 🎉

服务器端已重启，用户需要**强制刷新浏览器**（Ctrl+Shift+R）即可解决。
