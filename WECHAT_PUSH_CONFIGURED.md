# ✅ 微信推送配置完成

> 2026-01-22 - 服务器和小程序推送配置

---

## 🎯 配置状态

### ✅ 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| 服务器后端配置 | ✅ 完成 | 环境变量已配置 |
| 后端服务重启 | ✅ 完成 | 服务正常运行 |
| 小程序代码配置 | ✅ 完成 | 模板ID已更新 |

### ⏳ 待完成

| 项目 | 状态 | 说明 |
|------|------|------|
| 小程序编译 | ⏳ 待执行 | 需要手动编译 |
| 小程序上传 | ⏳ 待执行 | 需要使用微信开发者工具 |

---

## 📋 配置详情

### 1. 服务器后端配置

**配置文件**: `/opt/health-app/backend/.env`

```bash
# 微信小程序基础配置
WECHAT_APPID=wx1234567890abcdef
WECHAT_SECRET=abcdef1234567890abcdef12

# 兼容配置
WECHAT_MINI_APP_ID=wx1234567890abcdef
WECHAT_MINI_APP_SECRET=abcdef1234567890abcdef12

# 订阅消息模板ID
WECHAT_TEMPLATE_REMINDER=rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI
WECHAT_TEMPLATE_BRIEFING=A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg
WECHAT_TEMPLATE_ALERT=JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg
WECHAT_TEMPLATE_GOAL=buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE
WECHAT_TEMPLATE_WEEKLY=sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo
```

**服务状态**: ✅ 已重启并运行正常

```bash
systemctl status health-backend
# Active: active (running)
```

### 2. 小程序代码配置

**配置文件**: `packages/mini-program/src/services/subscribe.ts`

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo',
};
```

**状态**: ✅ 代码已更新

---

## 🚀 后续步骤

### 步骤 1: 编译小程序

由于本地环境依赖问题，需要手动编译：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program

# 方式 1: 使用 npm
npm run build:weapp

# 方式 2: 如果遇到依赖问题，尝试清理后重新安装
rm -rf node_modules
pnpm install
npm run build:weapp
```

**编译输出目录**: `packages/mini-program/dist/`

### 步骤 2: 上传小程序

#### 使用微信开发者工具

1. **打开微信开发者工具**
2. **导入项目**
   - 项目目录: `/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist`
   - AppID: `wx1234567890abcdef`
   - 项目名称: 健康管理小程序
3. **预览测试**
   - 点击 **预览** 按钮
   - 扫码在手机上测试
   - 测试订阅消息功能
4. **上传代码**
   - 点击 **上传** 按钮
   - 填写版本号: `1.1.0`
   - 填写备注: `配置微信推送功能`
5. **提交审核**
   - 登录微信公众平台
   - 进入 **版本管理**
   - 选择刚上传的版本
   - 点击 **提交审核**

#### 使用命令行工具（可选）

```bash
# 安装 miniprogram-ci
npm install -g miniprogram-ci

# 上传代码
miniprogram-ci upload \
  --pp ./packages/mini-program/dist \
  --pkp ./packages/mini-program/private.key \
  --appid wx1234567890abcdef \
  --uv 1.1.0 \
  --ud "配置微信推送功能"
```

---

## 🧪 测试验证

### 1. 测试后端配置

```bash
# 检查环境变量是否加载
ssh root@39.98.206.178 "cd /opt/health-app/backend && grep WECHAT .env"

# 查看服务日志
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"
```

### 2. 测试小程序订阅

在小程序中测试订阅功能：

1. 打开小程序
2. 进入 **设置** 页面
3. 找到 **消息提醒** 设置
4. 点击 **开启提醒**
5. 授权订阅消息
6. 查看是否成功订阅

### 3. 测试推送发送

```bash
# 使用 API 测试推送
curl -X POST https://health.westwetlandtech.com/api/v1/notification/test-push \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试推送",
    "content": "这是一条测试消息",
    "channel": "wechat"
  }'
```

### 4. 查看推送日志

```sql
-- 连接数据库
ssh root@39.98.206.178 "sudo -u postgres psql health_db"

-- 查看推送记录
SELECT 
    id,
    user_id,
    notification_type,
    channel,
    status,
    created_at,
    sent_at
FROM notification_logs
ORDER BY created_at DESC
LIMIT 10;

-- 查看用户订阅设置
SELECT 
    u.id,
    u.username,
    u.wechat_openid,
    uns.wechat_enabled,
    uns.wechat_template_ids
FROM users u
LEFT JOIN user_notification_settings uns ON u.id = uns.user_id
WHERE u.wechat_openid IS NOT NULL;
```

---

## 📊 推送类型说明

| 推送类型 | 模板ID | 触发时机 | 用途 |
|---------|--------|---------|------|
| 健康提醒 | `rit2hR...` | 定时触发 | 喝水、洗鼻、运动提醒 |
| 早间简报 | `A-R8QF...` | 每天 7:30 | 健康数据摘要和建议 |
| 健康预警 | `JCSm2j...` | 数据异常时 | 异常指标提醒 |
| 目标进度 | `buawjD...` | 每周一次 | 健康目标完成度 |
| 周报通知 | `sjiGrc...` | 每周一 9:00 | 每周健康报告 |

---

## 🔧 故障排查

### 问题 1: 推送发送失败

**检查清单**:
- [ ] 后端环境变量是否正确配置
- [ ] 后端服务是否重启
- [ ] 用户是否已订阅消息
- [ ] 模板ID是否正确
- [ ] AppID 和 AppSecret 是否正确

**查看日志**:
```bash
ssh root@39.98.206.178 "tail -f /var/log/health-backend/app.log | grep '微信订阅'"
```

### 问题 2: 小程序编译失败

**解决方法**:
```bash
# 清理依赖
cd packages/mini-program
rm -rf node_modules
rm pnpm-lock.yaml

# 重新安装
pnpm install

# 重新编译
npm run build:weapp
```

### 问题 3: 用户收不到推送

**排查步骤**:
1. 检查用户是否已授权订阅
2. 检查用户的 wechat_openid 是否正确
3. 检查推送日志中的错误信息
4. 检查模板参数是否符合微信要求

---

## 📝 配置备份

### 备份文件

- 原配置备份: `/opt/health-app/backend/.env.backup.YYYYMMDD_HHMMSS`
- 小程序代码: `packages/mini-program/src/services/subscribe.ts`

### 恢复配置

```bash
# 如需恢复原配置
ssh root@39.98.206.178 "cd /opt/health-app/backend && cp .env.backup.YYYYMMDD_HHMMSS .env && systemctl restart health-backend"
```

---

## 📞 技术支持

### 相关文档

- 📖 **完整配置指南**: `MINI_PROGRAM_PUSH_SETUP_GUIDE.md`
- 📋 **快速参考**: `MINI_PROGRAM_PUSH_QUICK_REF.md`
- 📊 **配置总结**: `PUSH_CONFIGURATION_SUMMARY.md`

### 联系方式

如遇到问题，请提供：
1. 错误日志
2. 配置信息（脱敏）
3. 测试结果
4. 用户ID

---

## ✅ 配置检查清单

### 服务器端

- [x] 配置 WECHAT_APPID
- [x] 配置 WECHAT_SECRET
- [x] 配置所有模板ID
- [x] 重启后端服务
- [x] 验证服务运行正常

### 小程序端

- [x] 更新 subscribe.ts 中的模板ID
- [ ] 编译小程序 (`npm run build:weapp`)
- [ ] 上传到微信公众平台
- [ ] 提交审核（如需要）
- [ ] 发布上线（如需要）

### 测试验证

- [ ] 测试订阅授权
- [ ] 测试推送发送
- [ ] 查看推送日志
- [ ] 验证用户收到推送

---

**配置时间**: 2026-01-22 12:54  
**配置人员**: AI Assistant  
**服务器**: 39.98.206.178  
**状态**: ✅ 后端配置完成，⏳ 小程序待编译上传
