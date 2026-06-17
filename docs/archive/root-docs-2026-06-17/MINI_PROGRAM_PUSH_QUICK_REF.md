# 📱 小程序推送配置快速参考

> 一页纸快速配置指南

---

## 🎯 配置清单

### 1️⃣ 微信公众平台 (5分钟)

**登录**: https://mp.weixin.qq.com/

**申请模板**: 功能 → 订阅消息 → 选用模板

| 模板类型 | 搜索关键词 | 用途 |
|---------|-----------|------|
| 健康提醒 | 事项提醒、健康提醒 | 喝水、洗鼻、运动提醒 |
| 早间简报 | 数据统计、日报 | 每日健康摘要 |
| 健康预警 | 异常提醒、预警 | 指标异常通知 |
| 目标进度 | 进度提醒、任务 | 健康目标进度 |
| 周报 | 周报、数据报告 | 每周健康报告 |

**获取 AppID/Secret**: 开发 → 开发管理 → 开发设置

---

### 2️⃣ 后端配置 (2分钟)

**方式 1: 使用配置脚本（推荐）**

```bash
# 在服务器上运行
ssh root@39.98.206.178
cd /opt/health-app
bash scripts/setup_wechat_push.sh
```

**方式 2: 手动配置**

编辑 `/opt/health-app/backend/.env`:

```bash
# 基础配置
WECHAT_APPID=wx1234567890abcdef
WECHAT_SECRET=abcdef1234567890abcdef12

# 模板ID
WECHAT_TEMPLATE_REMINDER=模板ID1
WECHAT_TEMPLATE_BRIEFING=模板ID2
WECHAT_TEMPLATE_ALERT=模板ID3
WECHAT_TEMPLATE_GOAL=模板ID4
WECHAT_TEMPLATE_WEEKLY=模板ID5
```

**重启服务**:

```bash
systemctl restart health-backend
```

---

### 3️⃣ 小程序配置 (3分钟)

**编辑文件**: `packages/mini-program/src/services/subscribe.ts`

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: '模板ID1',
  MORNING_BRIEFING: '模板ID2',
  HEALTH_ALERT: '模板ID3',
  GOAL_PROGRESS: '模板ID4',
  WEEKLY_REPORT: '模板ID5',
};
```

**编译上传**:

```bash
cd packages/mini-program
npm run build:weapp
# 使用微信开发者工具上传 dist 目录
```

---

## 🧪 快速测试

### 测试订阅授权

在小程序中调用：

```typescript
import { requestAllSubscriptions } from '@/services/subscribe';

const result = await requestAllSubscriptions();
console.log('订阅结果:', result);
```

### 测试推送发送

```bash
# 后端测试
curl -X POST https://health.westwetlandtech.com/api/v1/notification/test-push \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"测试","content":"测试消息","channel":"wechat"}'
```

### 查看日志

```bash
# 后端日志
tail -f /var/log/health-backend/app.log | grep "微信订阅"

# Celery 日志
tail -f /var/log/celery/worker.log | grep "推送"
```

---

## 🐛 常见错误速查

| 错误码 | 含义 | 解决方法 |
|--------|------|---------|
| 43101 | 用户未订阅 | 引导用户重新订阅 |
| 47003 | 模板参数错误 | 检查参数格式和长度 |
| 40001 | access_token 无效 | 检查 AppID/Secret |
| 40037 | 模板ID不存在 | 确认模板ID正确 |

---

## 📊 数据库检查

```sql
-- 查看订阅用户
SELECT COUNT(*) FROM user_notification_settings WHERE wechat_enabled = true;

-- 查看推送记录
SELECT * FROM notification_logs ORDER BY created_at DESC LIMIT 10;

-- 查看推送成功率
SELECT 
    notification_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as success
FROM notification_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY notification_type;
```

---

## 🔗 相关文档

- 📖 **完整配置指南**: `MINI_PROGRAM_PUSH_SETUP_GUIDE.md`
- 🔧 **配置脚本**: `scripts/setup_wechat_push.sh`
- 📱 **小程序订阅服务**: `packages/mini-program/src/services/subscribe.ts`
- 🔙 **后端推送服务**: `backend/app/services/notification/wechat_push.py`

---

## ⚡ 一键命令

```bash
# 完整配置流程（在本地执行）
cd /Users/liqiuhua/work/personal/health-llm-driven

# 1. 更新小程序模板ID
vim packages/mini-program/src/services/subscribe.ts

# 2. 编译小程序
cd packages/mini-program && npm run build:weapp

# 3. 配置后端（在服务器上）
ssh root@39.98.206.178 "cd /opt/health-app && bash scripts/setup_wechat_push.sh"

# 4. 上传小程序代码到微信公众平台
# 使用微信开发者工具上传
```

---

**配置时间**: 约 10 分钟  
**难度**: ⭐⭐☆☆☆  
**更新日期**: 2026-01-22
