# 📱 小程序推送配置总结

> 微信小程序订阅消息推送配置完整方案

---

## 📋 配置概览

### 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 后端推送服务 | ✅ 已实现 | `WeChatPushService` 完整实现 |
| 小程序订阅服务 | ✅ 已实现 | `subscribe.ts` 完整实现 |
| API 端点 | ✅ 已实现 | 订阅设置保存/获取接口 |
| 数据库模型 | ✅ 已实现 | `UserNotificationSetting` 表 |
| 配置脚本 | ✅ 已创建 | `setup_wechat_push.sh` |
| 文档 | ✅ 已完成 | 完整配置指南 |

### 待配置项

| 配置项 | 位置 | 状态 |
|--------|------|------|
| 微信模板申请 | 微信公众平台 | ⏳ 待申请 |
| AppID/Secret | 后端 `.env` | ⏳ 待配置 |
| 模板ID | 后端 `.env` + 小程序 | ⏳ 待配置 |
| 小程序重新编译 | 本地 | ⏳ 待执行 |
| 小程序上传 | 微信开发者工具 | ⏳ 待执行 |

---

## 🎯 推送类型

### 1. 健康提醒 (HEALTH_REMINDER)

**用途**: 定时提醒用户进行健康活动

**触发场景**:
- 💧 喝水提醒（每 2 小时）
- 👃 洗鼻提醒（早晚各一次）
- 🏃 运动提醒（根据用户设定）
- 💊 补剂提醒（根据补剂计划）

**后端实现**: `backend/app/services/notification/push_scheduler.py`

**Celery 任务**: `app.tasks.notifications.send_exercise_reminder`

### 2. 早间简报 (MORNING_BRIEFING)

**用途**: 每日健康数据摘要和建议

**触发时间**: 每天 7:30

**内容包含**:
- 昨日睡眠质量
- 昨日运动数据
- 今日健康建议
- 今日天气和环境

**后端实现**: `backend/app/services/ai_scheduler.py`

**Celery 任务**: `app.tasks.notifications.send_morning_briefing`

### 3. 健康预警 (HEALTH_ALERT)

**用途**: 异常健康指标提醒

**触发场景**:
- 心率异常
- 血压异常
- 睡眠质量差
- 压力过大
- 体重变化异常

**后端实现**: `backend/app/services/health_analysis.py`

### 4. 目标进度 (GOAL_PROGRESS)

**用途**: 健康目标完成度通知

**触发时间**: 每周一次

**内容包含**:
- 目标完成百分比
- 本周进展
- 剩余天数
- 鼓励语

**后端实现**: `backend/app/services/goal_service.py`

### 5. 周报通知 (WEEKLY_REPORT)

**用途**: 每周健康数据总结

**触发时间**: 每周一 9:00

**内容包含**:
- 本周运动总结
- 本周睡眠分析
- 本周健康趋势
- 下周建议

**后端实现**: `backend/app/services/review_service.py`

**Celery 任务**: `app.tasks.health_analysis.generate_weekly_reports`

---

## 🏗️ 架构设计

### 推送流程

```
用户订阅授权
    ↓
小程序调用 wx.requestSubscribeMessage
    ↓
获取用户授权结果
    ↓
调用后端 API 保存模板ID
    ↓
存储到 user_notification_settings 表
    ↓
Celery 定时任务触发
    ↓
检查用户订阅设置
    ↓
调用 WeChatPushService 发送推送
    ↓
调用微信 API 发送订阅消息
    ↓
记录推送日志到 notification_logs 表
```

### 核心组件

#### 1. 小程序端 (`packages/mini-program/src/services/subscribe.ts`)

**功能**:
- 请求用户订阅授权
- 管理模板ID配置
- 保存订阅设置到后端
- 显示订阅引导

**核心方法**:
```typescript
requestSubscribe(templateKeys: string[])      // 请求订阅
requestAllSubscriptions()                     // 一键订阅所有
saveSubscribeSettings(acceptedTemplateKeys)   // 保存到后端
showSubscribeGuide()                          // 显示引导
```

#### 2. 后端推送服务 (`backend/app/services/notification/wechat_push.py`)

**功能**:
- 获取微信 access_token
- 发送订阅消息
- 构建消息模板
- 错误处理

**核心方法**:
```python
get_access_token()                            # 获取 token
send_subscription_message(...)                # 发送消息
send_health_reminder(...)                     # 发送健康提醒
send_morning_briefing(...)                    # 发送早间简报
```

#### 3. 推送调度服务 (`backend/app/services/notification/push_scheduler.py`)

**功能**:
- 检查用户订阅设置
- 判断是否在免打扰时间
- 调用推送服务
- 记录推送日志

**核心方法**:
```python
send_morning_briefing(user_id)                # 发送早间简报
send_health_reminder(user_id, reminder_type)  # 发送健康提醒
```

#### 4. API 端点 (`backend/app/api/wechat.py`)

**端点**:
- `POST /api/v1/wechat/subscribe/settings` - 保存订阅设置
- `GET /api/v1/wechat/subscribe/settings` - 获取订阅设置
- `PUT /api/v1/wechat/subscribe/settings` - 更新通知设置

---

## 📂 文件清单

### 配置文件

| 文件 | 用途 | 位置 |
|------|------|------|
| `.env` | 后端环境变量 | `/opt/health-app/backend/.env` |
| `subscribe.ts` | 小程序模板配置 | `packages/mini-program/src/services/subscribe.ts` |

### 代码文件

| 文件 | 功能 | 路径 |
|------|------|------|
| `wechat_push.py` | 微信推送服务 | `backend/app/services/notification/wechat_push.py` |
| `push_scheduler.py` | 推送调度服务 | `backend/app/services/notification/push_scheduler.py` |
| `push_service.py` | 统一推送服务 | `backend/app/services/notification/push_service.py` |
| `subscribe.ts` | 小程序订阅服务 | `packages/mini-program/src/services/subscribe.ts` |
| `wechat.py` | 微信 API 端点 | `backend/app/api/wechat.py` |
| `notification.py` | 通知数据模型 | `backend/app/models/notification.py` |

### 文档文件

| 文件 | 内容 | 路径 |
|------|------|------|
| `MINI_PROGRAM_PUSH_SETUP_GUIDE.md` | 完整配置指南 | 项目根目录 |
| `MINI_PROGRAM_PUSH_QUICK_REF.md` | 快速参考卡片 | 项目根目录 |
| `PUSH_CONFIGURATION_SUMMARY.md` | 配置总结（本文档） | 项目根目录 |

### 脚本文件

| 文件 | 功能 | 路径 |
|------|------|------|
| `setup_wechat_push.sh` | 配置向导脚本 | `scripts/setup_wechat_push.sh` |

---

## 🔧 配置步骤

### 快速配置（推荐）

```bash
# 1. 在服务器上运行配置脚本
ssh root@39.98.206.178
cd /opt/health-app
bash scripts/setup_wechat_push.sh

# 2. 更新小程序配置
# 编辑 packages/mini-program/src/services/subscribe.ts
# 填入模板ID

# 3. 编译小程序
cd packages/mini-program
npm run build:weapp

# 4. 上传小程序
# 使用微信开发者工具上传 dist 目录
```

### 详细配置

参考 `MINI_PROGRAM_PUSH_SETUP_GUIDE.md`

---

## 🧪 测试验证

### 1. 测试订阅授权

```typescript
// 在小程序中
import { requestAllSubscriptions } from '@/services/subscribe';

const result = await requestAllSubscriptions();
if (result.success) {
  console.log('订阅成功:', result.acceptedTemplates);
}
```

### 2. 测试推送发送

```bash
# 后端测试
curl -X POST https://health.westwetlandtech.com/api/v1/notification/test-push \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试推送",
    "content": "这是一条测试消息",
    "channel": "wechat"
  }'
```

### 3. 查看推送日志

```sql
-- 查看最近的推送记录
SELECT * FROM notification_logs 
ORDER BY created_at DESC 
LIMIT 20;

-- 查看推送成功率
SELECT 
    notification_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as success,
    ROUND(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as success_rate
FROM notification_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY notification_type;
```

---

## 📊 数据库表

### user_notification_settings

用户推送设置表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| user_id | Integer | 用户ID |
| enabled | Boolean | 总开关 |
| wechat_enabled | Boolean | 微信推送开关 |
| wechat_openid | String | 微信 OpenID |
| wechat_template_ids | JSON | 订阅的模板ID |
| morning_briefing_enabled | Boolean | 早间简报开关 |
| reminder_enabled | Boolean | 提醒开关 |
| health_alert_enabled | Boolean | 健康预警开关 |
| morning_briefing_time | String | 早间简报时间 |
| quiet_hours_start | String | 免打扰开始 |
| quiet_hours_end | String | 免打扰结束 |

### notification_logs

推送日志表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| user_id | Integer | 用户ID |
| notification_type | String | 推送类型 |
| channel | String | 推送渠道 |
| title | String | 标题 |
| content | Text | 内容 |
| status | String | 状态 |
| error_message | Text | 错误信息 |
| created_at | DateTime | 创建时间 |
| sent_at | DateTime | 发送时间 |

---

## 🚀 部署检查清单

### 微信公众平台

- [ ] 已登录微信公众平台
- [ ] 已申请健康提醒模板
- [ ] 已申请早间简报模板
- [ ] 已申请健康预警模板
- [ ] 已申请目标进度模板
- [ ] 已申请周报模板
- [ ] 已记录所有模板ID
- [ ] 已获取 AppID
- [ ] 已获取 AppSecret

### 后端配置

- [ ] 已配置 `WECHAT_APPID`
- [ ] 已配置 `WECHAT_SECRET`
- [ ] 已配置 `WECHAT_TEMPLATE_REMINDER`
- [ ] 已配置 `WECHAT_TEMPLATE_BRIEFING`
- [ ] 已配置 `WECHAT_TEMPLATE_ALERT`
- [ ] 已配置 `WECHAT_TEMPLATE_GOAL`
- [ ] 已配置 `WECHAT_TEMPLATE_WEEKLY`
- [ ] 已重启后端服务
- [ ] 服务运行正常

### 小程序配置

- [ ] 已更新 `subscribe.ts` 中的模板ID
- [ ] 已重新编译小程序 (`npm run build:weapp`)
- [ ] 已上传到微信公众平台
- [ ] 已提交审核（如需要）
- [ ] 已发布上线（如需要）

### 测试验证

- [ ] 已测试订阅授权流程
- [ ] 已测试推送发送功能
- [ ] 已查看推送日志
- [ ] 已验证推送到达
- [ ] 已测试各种推送类型

---

## 📞 技术支持

### 常见问题

参考 `MINI_PROGRAM_PUSH_SETUP_GUIDE.md` 中的"常见问题"章节

### 日志查看

```bash
# 后端日志
tail -f /var/log/health-backend/app.log | grep "微信订阅"

# Celery 日志
tail -f /var/log/celery/worker.log | grep "推送"

# 系统日志
journalctl -u health-backend -f
```

### 联系方式

如遇到问题，请提供：
1. 错误日志
2. 配置信息（脱敏）
3. 测试结果
4. 用户ID
5. 推送类型

---

## 📈 后续优化

### 1. 推送效果分析

- 统计推送打开率
- 分析最佳推送时间
- 优化推送内容

### 2. 个性化推送

- 根据用户习惯调整推送时间
- 根据用户偏好定制推送内容
- 智能免打扰时间

### 3. 推送模板优化

- A/B 测试不同模板
- 优化模板文案
- 增加交互元素

---

**创建日期**: 2026-01-22  
**文档版本**: v1.0  
**维护者**: Health LLM Team  
**状态**: ✅ 完成
