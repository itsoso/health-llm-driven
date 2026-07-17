# 小程序快速开始指南（使用已构建版本）

## ⚠️ 重要说明

由于 Taro 4.1.10 在 Intel 版本 Node.js + Apple Silicon Mac 环境下存在 native binding 问题，我们直接使用已经构建好的版本。

## ✅ 当前状态

- **构建产物**：`packages/mini-program/dist/` ✓（已存在）
- **最后构建时间**：2026-01-21
- **订阅模板 ID**：已配置 ✓

## 📱 快速开始（3 步）

### 步骤 1：打开微信开发者工具

1. 启动**微信开发者工具**
2. 选择"小程序"
3. 点击"导入项目"

### 步骤 2：导入项目

**项目配置**：
- **项目目录**：选择 `/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist`
- **AppID**：`wx1234567890abcdef`
- **项目名称**：健康管理小程序

点击"导入"。

### 步骤 3：预览测试

1. **在微信开发者工具中**：
   - 点击工具栏的"预览"按钮
   - 会生成一个二维码

2. **使用手机微信扫码**：
   - 打开微信扫一扫
   - 扫描二维码
   - 小程序会在手机上打开

3. **开启订阅消息**：
   - 在小程序中点击底部"我的"标签
   - 找到"消息提醒"部分
   - 点击"开启消息提醒"按钮
   - 在弹出的授权窗口中勾选要订阅的模板
   - 点击"允许"

## 🔍 验证订阅是否成功

### 方法 1：查看小程序设置页面

在"我的" -> "消息提醒"中应该显示：
- ✅ 消息提醒：已开启
- 已订阅的模板列表

### 方法 2：查看后端数据库

```bash
ssh root@39.98.206.178 "sudo -u postgres psql -d health_db -c \"SELECT user_id, enabled, wechat_enabled, wechat_template_ids FROM user_notification_settings WHERE user_id = 3;\""
```

预期输出：
```
 user_id | enabled | wechat_enabled | wechat_template_ids
---------+---------+----------------+---------------------
       3 | t       | t              | {"reminder": "rit...", ...}
```

### 方法 3：测试推送

```bash
# 获取 token
TOKEN=$(curl -s -X POST 'https://health.westwetlandtech.com/api/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"itsoso@126.com","password":"<redacted-test-password>"}' | jq -r '.access_token')

# 查询订阅设置
curl -X GET 'https://health.westwetlandtech.com/api/wechat/subscribe/settings' \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 🔄 如果需要更新小程序代码

### 方案 A：在服务器上构建（推荐）

如果您有一台 Linux 服务器或 Intel Mac：

```bash
# 在服务器上
cd /path/to/health-llm-driven/packages/mini-program
npm install
npm run build:weapp

# 然后将 dist 目录下载到本地
scp -r user@server:/path/to/dist ./
```

### 方案 B：使用 Docker 构建

```bash
# 在项目根目录创建 Dockerfile
cat > Dockerfile.miniapp << 'EOF'
FROM node:18-alpine
WORKDIR /app
COPY packages/mini-program/package*.json ./
RUN npm install
COPY packages/mini-program/ ./
RUN npm run build:weapp
EOF

# 构建
docker build -f Dockerfile.miniapp -t miniapp-builder .

# 复制产物
docker create --name temp miniapp-builder
docker cp temp:/app/dist ./packages/mini-program/
docker rm temp
```

### 方案 C：安装 ARM 版本 Node.js（长期解决方案）

如果您想在本地构建，建议安装 ARM 原生版本的 Node.js：

```bash
# 1. 卸载当前的 Intel 版本 Node.js
# 2. 从 https://nodejs.org 下载 ARM64 版本
# 3. 安装后验证：
node -p "process.arch"  # 应该显示 "arm64"

# 4. 重新安装依赖并构建
cd packages/mini-program
rm -rf node_modules
npm install
npm run build:weapp
```

## 📊 订阅模板列表

| 模板类型 | 模板 ID | 用途 |
|---------|---------|------|
| 健康提醒 | rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI | 喝水、洗鼻、运动提醒 |
| 早间简报 | A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg | 每天 7:00 的健康简报 |
| 健康预警 | JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg | 心率异常、睡眠不足等预警 |
| 目标进度 | buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE | 每周日的目标完成情况 |
| 周报通知 | sjiGrcujQj4FMN-iQlKEqzuAYknzOBFMNpnz15pwWPo | 每周一的健康总结 |

## 🎯 推送时间表

| 推送类型 | 触发时间 | 说明 |
|---------|---------|------|
| 早间简报 | 每天 7:00 | 包含睡眠总结、今日建议 |
| 喝水提醒 | 9:00, 11:00, 14:00, 16:00, 19:00 | 根据用户画像定制 |
| 洗鼻提醒 | 7:00, 22:00 | 鼻炎患者专属 |
| 运动提醒 | 18:00 | 久坐提醒 |
| 健康预警 | 实时检测 | 异常情况立即推送 |
| 周报通知 | 每周一 8:00 | 上周健康总结 |

## ❓ 常见问题

### Q: 为什么不能直接构建？

**A**: 您的 Mac 是 Apple Silicon (ARM64)，但安装的是 Intel 版本的 Node.js。Taro 4.1.10 的 native binding 在这种环境下有兼容性问题。

### Q: 如何更新小程序代码？

**A**: 
1. 修改源代码后，在服务器或 Docker 中构建
2. 或者安装 ARM 版本的 Node.js
3. 然后在微信开发者工具中重新导入 dist 目录

### Q: 订阅后没有收到推送？

**A**: 检查以下几点：
1. Celery 服务是否运行：`systemctl status celery-worker celery-beat`
2. 查看推送日志：`tail -f /var/log/celery/worker.log | grep -i wechat`
3. 确认订阅设置已保存到数据库

### Q: 如何上传到微信公众平台？

**A**: 
1. 在微信开发者工具中点击"上传"按钮
2. 填写版本号（如 1.0.0）和备注
3. 登录微信公众平台提交审核

## 📞 需要帮助？

如果遇到问题，请提供：
1. 微信开发者工具的控制台日志
2. 错误截图
3. 具体的操作步骤

---

**现在就可以开始使用了！** 🎉

直接用微信开发者工具打开 `packages/mini-program/dist` 目录即可！
