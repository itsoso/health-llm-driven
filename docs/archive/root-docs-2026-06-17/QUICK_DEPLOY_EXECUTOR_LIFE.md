# 快速部署指南 - Executor.Life 域名

## 🎯 当前状态

✅ **已完成**:
- Nginx 配置已创建并部署
- 前端代码已更新
- 小程序代码已更新
- 代码已提交到 Git

⏳ **待完成**:
- DNS 记录配置
- 前端重新构建部署
- 小程序重新编译上传
- 微信小程序域名白名单配置

---

## 📋 部署步骤

### 步骤 1: 配置 DNS 记录

在域名服务商（阿里云/腾讯云等）添加 DNS 记录：

```
类型: A
主机记录: health
记录值: 39.98.206.178
TTL: 600
```

**验证 DNS 生效**:
```bash
dig health.executor.life
# 或
nslookup health.executor.life
```

---

### 步骤 2: 部署前端

```bash
# 连接服务器
ssh root@health.westwetlandtech.com

# 进入项目目录
cd /opt/health-app

# 拉取最新代码
git pull

# 构建并重启前端
cd frontend
npm run build
pm2 restart health-frontend

# 验证前端服务
pm2 status
```

**验证访问**:
- 旧域名: https://health.westwetlandtech.com ✅ 应该正常
- 新域名: https://health.executor.life ✅ 应该正常

---

### 步骤 3: 编译小程序

```bash
# 在本地执行
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program

# 拉取最新代码（如果还没有）
git pull

# 安装依赖（如果需要）
npm install

# 编译小程序
npm run build:weapp
```

**上传小程序**:
1. 打开微信开发者工具
2. 导入项目：`packages/mini-program/dist`
3. 点击"上传"按钮
4. 填写版本号和备注
5. 提交审核

---

### 步骤 4: 配置微信小程序域名白名单

登录 [微信公众平台](https://mp.weixin.qq.com/)：

1. 进入"开发" → "开发管理" → "开发设置"
2. 找到"服务器域名"
3. 添加以下域名：

**request 合法域名**:
```
https://health.executor.life
```

**uploadFile 合法域名**:
```
https://health.executor.life
```

**downloadFile 合法域名**:
```
https://health.executor.life
```

**注意**: 
- 保留 `https://health.westwetlandtech.com` 以确保兼容性
- 每月只能修改 5 次，请谨慎操作

---

## ✅ 验证清单

### Web 端验证

```bash
# 1. 测试首页
curl -I https://health.executor.life/

# 2. 测试 API
curl -I https://health.executor.life/api/v1/health

# 3. 测试静态资源
curl -I https://health.executor.life/_next/static/...
```

**浏览器验证**:
- [ ] https://health.executor.life 可以访问
- [ ] 登录功能正常
- [ ] API 调用正常
- [ ] 图片加载正常

### 小程序验证

**真机测试**:
- [ ] 小程序可以正常启动
- [ ] 登录功能正常
- [ ] 数据加载正常
- [ ] 图片显示正常
- [ ] 华为设备授权正常（如果使用）

---

## 🔧 快速命令

### 一键部署前端

```bash
ssh root@health.westwetlandtech.com "cd /opt/health-app && git pull && cd frontend && npm run build && pm2 restart health-frontend && pm2 status"
```

### 检查服务状态

```bash
ssh root@health.westwetlandtech.com "
echo '=== Nginx 状态 ==='
systemctl status nginx | head -5
echo ''
echo '=== PM2 状态 ==='
pm2 status
echo ''
echo '=== 域名测试 ==='
curl -I https://health.executor.life/ 2>&1 | head -5
"
```

### 查看日志

```bash
# 前端日志
ssh root@health.westwetlandtech.com "pm2 logs health-frontend --lines 50"

# 后端日志
ssh root@health.westwetlandtech.com "pm2 logs health-backend --lines 50"

# Nginx 错误日志
ssh root@health.westwetlandtech.com "tail -50 /var/log/nginx/error.log"
```

---

## 🚨 故障排查

### 问题 1: DNS 未生效

**症状**: `dig health.executor.life` 没有返回 IP

**解决**:
```bash
# 等待 DNS 传播（最多 48 小时）
# 或者修改本地 hosts 文件测试：
sudo vim /etc/hosts
# 添加：39.98.206.178 health.executor.life
```

### 问题 2: SSL 证书错误

**症状**: 浏览器提示证书无效

**解决**:
```bash
ssh root@health.westwetlandtech.com

# 检查证书
certbot certificates | grep executor.life

# 如果需要，申请新证书
certbot certonly --webroot -w /var/www/executor.life -d health.executor.life
```

### 问题 3: 小程序无法连接

**症状**: 小程序提示"不在以下 request 合法域名列表中"

**解决**:
1. 检查微信公众平台域名配置
2. 确保添加了 `https://health.executor.life`
3. 重新编译上传小程序

### 问题 4: API 调用 404

**症状**: 前端或小程序 API 调用返回 404

**解决**:
```bash
# 检查 Nginx 配置
ssh root@health.westwetlandtech.com "nginx -t"

# 检查后端服务
ssh root@health.westwetlandtech.com "pm2 status"

# 测试 API
curl -I https://health.executor.life/api/v1/health
```

---

## 📞 联系方式

如果遇到问题，请检查：
1. 📄 完整文档: `EXECUTOR_LIFE_DOMAIN_MIGRATION.md`
2. 🔧 Nginx 配置: `/etc/nginx/conf.d/health.executor.life.conf`
3. 📊 服务状态: `pm2 status`
4. 📝 日志文件: `pm2 logs`

---

## 🎉 部署完成检查

部署完成后，确认以下所有项目：

- [ ] DNS 记录已配置并生效
- [ ] https://health.executor.life 可以访问
- [ ] https://health.executor.life/api/v1/health 返回 200
- [ ] Web 端登录功能正常
- [ ] Web 端数据加载正常
- [ ] 小程序已重新编译上传
- [ ] 小程序域名白名单已配置
- [ ] 小程序真机测试通过
- [ ] 旧域名 health.westwetlandtech.com 仍然可用

---

**部署时间**: 待定  
**预计耗时**: 30-60 分钟（不含 DNS 传播时间）  
**文档版本**: 1.0  
**更新时间**: 2026-01-24 12:35
