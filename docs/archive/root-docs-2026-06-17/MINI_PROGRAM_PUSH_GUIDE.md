# 小程序订阅推送完整指南

## 📋 目录

1. [配置状态确认](#配置状态确认)
2. [小程序端操作步骤](#小程序端操作步骤)
3. [验证方法](#验证方法)
4. [测试推送](#测试推送)
5. [常见问题](#常见问题)

---

## ✅ 配置状态确认

### 1. 后端配置（已完成 ✓）

**环境变量**（`/opt/health-app/backend/.env`）：
```bash
WECHAT_APPID=wx1234567890abcdef
WECHAT_SECRET=abcdef1234567890abcdef12
WECHAT_TEMPLATE_REMINDER=rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI
WECHAT_TEMPLATE_BRIEFING=A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg
WECHAT_TEMPLATE_ALERT=JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg
WECHAT_TEMPLATE_GOAL=buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE
WECHAT_TEMPLATE_WEEKLY=sjiGrcujQj4FMN-iQlKEqzuAYknzOBFMNpnz15pwWPo
```

### 2. 小程序端配置（已完成 ✓）

**文件**：`packages/mini-program/src/services/subscribe.ts`

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBFMNpnz15pwWPo',
};
```

---

## 📱 小程序端操作步骤

### 步骤 1：编译并上传小程序

```bash
# 1. 进入小程序目录
cd packages/mini-program

# 2. 安装依赖（如果还没安装）
npm install

# 3. 编译小程序
npm run build:weapp

# 4. 使用微信开发者工具打开 dist 目录
# 路径：packages/mini-program/dist
```

### 步骤 2：在微信开发者工具中操作

1. **打开项目**
   - 启动微信开发者工具
   - 选择"小程序"
   - 导入项目，选择 `packages/mini-program/dist` 目录
   - AppID 填写：`wx1234567890abcdef`

2. **预览测试**
   - 点击工具栏的"预览"按钮
   - 使用手机微信扫码
   - 在手机上打开小程序

3. **上传代码**（可选，用于正式发布）
   - 点击工具栏的"上传"按钮
   - 填写版本号和备注
   - 上传成功后，在微信公众平台提交审核

### 步骤 3：在小程序中开启订阅

**方法 A：通过设置页面（推荐）**

1. 打开小程序
2. 点击底部导航栏的"我的"（设置页面）
3. 找到"消息提醒"部分
4. 点击"开启消息提醒"按钮
5. 在弹出的授权窗口中，勾选要订阅的模板
6. 点击"允许"

**方法 B：首次使用引导**

首次登录小程序时，会自动弹出订阅引导：
1. 点击"立即开启"
2. 在授权窗口中选择要订阅的模板
3. 点击"允许"

---

## 🔍 验证方法

### 1. 前端验证（小程序端）

**在设置页面查看订阅状态**：

```
我的 -> 消息提醒
```

应该显示：
- ✅ 消息提醒：已开启
- 已订阅的模板列表：
  - 健康提醒
  - 早间简报
  - 健康预警
  - 目标进度
  - 周报通知

**查看小程序控制台日志**：

在微信开发者工具的"控制台"中，应该看到：
```
[订阅] 授权结果: { acceptedTemplates: [...], rejectedTemplates: [] }
[订阅] 设置已保存到后端
```

### 2. 后端验证

**方法 A：查看数据库**

```bash
ssh root@39.98.206.178

# 查询用户的订阅设置
sudo -u postgres psql -d health_db -c "
SELECT 
    user_id,
    enabled,
    wechat_enabled,
    wechat_template_ids,
    morning_briefing_enabled,
    reminder_enabled,
    health_alert_enabled,
    created_at,
    updated_at
FROM user_notification_settings 
WHERE user_id = 3;
"
```

预期结果：
```
 user_id | enabled | wechat_enabled | wechat_template_ids | morning_briefing_enabled | ...
---------+---------+----------------+---------------------+--------------------------+-----
       3 | t       | t              | {"reminder": "rit...", "morning_briefing": "A-R..."} | t | ...
```

**方法 B：调用后端 API**

```bash
# 获取 token
TOKEN=$(curl -s -X POST 'https://health.westwetlandtech.com/api/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"itsoso@126.com","password":"<redacted-test-password>"}' | jq -r '.access_token')

# 查询订阅设置
curl -X GET 'https://health.westwetlandtech.com/api/wechat/subscribe/settings' \
  -H "Authorization: Bearer $TOKEN" | jq
```

预期响应：
```json
{
  "enabled": true,
  "wechat_enabled": true,
  "template_ids": {
    "reminder": "rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI",
    "morning_briefing": "A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg",
    "health_alert": "JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg",
    "goal_progress": "buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE",
    "weekly_report": "sjiGrcujQj4FMN-iQlKEqzuAYknzOBFMNpnz15pwWPo"
  },
  "morning_briefing_enabled": true,
  "reminder_enabled": true,
  "health_alert_enabled": true
}
```

### 3. 微信公众平台验证

1. 登录 [微信公众平台](https://mp.weixin.qq.com/)
2. 进入"功能" -> "订阅消息"
3. 查看"我的模板"
4. 确认以下模板已添加：
   - 健康提醒（ID: rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI）
   - 早间简报（ID: A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg）
   - 健康预警（ID: JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg）
   - 目标进度（ID: buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE）
   - 周报通知（ID: sjiGrcujQj4FMN-iQlKEqzuAYknzOBFMNpnz15pwWPo）

---

## 🧪 测试推送

### 方法 1：通过后端 API 手动测试

**创建测试脚本**：

```bash
# 保存为 test_push.sh
#!/bin/bash

# 获取 token
TOKEN=$(curl -s -X POST 'https://health.westwetlandtech.com/api/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"itsoso@126.com","password":"<redacted-test-password>"}' | jq -r '.access_token')

# 测试发送早间简报
curl -X POST 'https://health.westwetlandtech.com/api/wechat/push/test' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "message_type": "morning_briefing",
    "data": {
      "greeting": "早安！",
      "sleep_score": "85分",
      "sleep_quality": "良好",
      "today_suggestion": "今天适合进行中等强度运动",
      "weather": "晴天 15-25℃"
    }
  }'
```

### 方法 2：等待定时任务触发

**早间简报**（每天 7:00）：
```bash
# 查看 Celery Beat 日志
ssh root@39.98.206.178
tail -f /var/log/celery/beat.log | grep morning_briefing
```

**健康提醒**（根据用户画像触发）：
```bash
# 查看 Celery Worker 日志
tail -f /var/log/celery/worker.log | grep reminder
```

### 方法 3：通过小程序触发

**完成打卡后触发提醒**：

1. 在小程序中完成一次健康打卡（如喝水、洗鼻）
2. 系统会自动请求下次提醒的订阅授权
3. 到达提醒时间时，会收到推送

---

## ❓ 常见问题

### Q1: 点击"开启消息提醒"后没有反应？

**可能原因**：
1. 小程序未正确编译和上传
2. AppID 配置错误
3. 模板 ID 未在微信公众平台配置

**解决方法**：
```bash
# 1. 检查小程序编译
cd packages/mini-program
npm run build:weapp

# 2. 检查微信开发者工具控制台是否有错误
# 3. 确认 AppID 是否正确：wx1234567890abcdef
# 4. 在微信公众平台确认模板是否已添加
```

### Q2: 授权成功但没有收到推送？

**检查清单**：

1. **确认订阅状态**：
   ```bash
   # 查询数据库
   sudo -u postgres psql -d health_db -c "
   SELECT enabled, wechat_enabled, wechat_template_ids 
   FROM user_notification_settings 
   WHERE user_id = 3;
   "
   ```

2. **确认 Celery 服务运行**：
   ```bash
   systemctl status celery-worker
   systemctl status celery-beat
   ```

3. **查看推送日志**：
   ```bash
   tail -f /var/log/celery/worker.log | grep -i "wechat\|push\|subscribe"
   ```

4. **测试微信 API 连接**：
   ```bash
   # 获取 access_token
   curl "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=wx1234567890abcdef&secret=abcdef1234567890abcdef12"
   ```

### Q3: 提示"订阅模板未配置"？

**原因**：小程序端的模板 ID 为空或格式错误

**解决**：
1. 检查 `packages/mini-program/src/services/subscribe.ts`
2. 确认 `TEMPLATE_IDS` 中的 ID 与后端 `.env` 一致
3. 重新编译小程序：`npm run build:weapp`

### Q4: 用户拒绝订阅后如何重新开启？

**微信限制**：用户拒绝后，同一模板 **7 天内不会再弹窗**

**解决方法**：
1. 引导用户进入小程序设置页面
2. 点击右上角"..."菜单
3. 选择"设置" -> "通知管理"
4. 手动开启订阅消息

### Q5: 如何查看推送发送记录？

**方法 1：微信公众平台**
1. 登录微信公众平台
2. 进入"统计" -> "订阅消息"
3. 查看发送记录和送达率

**方法 2：后端日志**
```bash
# 查看推送日志
ssh root@39.98.206.178
grep -r "微信推送" /var/log/celery/*.log | tail -50
```

---

## 📊 推送时间表

| 推送类型 | 触发时间 | 模板 ID | 说明 |
|---------|---------|---------|------|
| 早间简报 | 每天 7:00 | MORNING_BRIEFING | 包含睡眠总结、今日建议 |
| 喝水提醒 | 每天 9:00, 11:00, 14:00, 16:00, 19:00 | HEALTH_REMINDER | 根据用户画像定制 |
| 洗鼻提醒 | 每天 7:00, 22:00 | HEALTH_REMINDER | 鼻炎患者专属 |
| 运动提醒 | 每天 18:00 | HEALTH_REMINDER | 久坐提醒 |
| 健康预警 | 实时检测 | HEALTH_ALERT | 心率异常、睡眠不足等 |
| 目标进度 | 每周日 20:00 | GOAL_PROGRESS | 周目标完成情况 |
| 周报通知 | 每周一 8:00 | WEEKLY_REPORT | 上周健康总结 |

---

## 🎯 快速验证步骤

**5 分钟快速验证**：

```bash
# 1. 编译小程序
cd packages/mini-program && npm run build:weapp

# 2. 在微信开发者工具中预览

# 3. 手机扫码打开小程序

# 4. 进入"我的"页面

# 5. 点击"开启消息提醒"

# 6. 在授权窗口中选择模板并允许

# 7. 查看后端数据库确认
ssh root@39.98.206.178 "sudo -u postgres psql -d health_db -c 'SELECT * FROM user_notification_settings WHERE user_id = 3;'"

# 8. 手动触发测试推送（可选）
# 使用上面的 test_push.sh 脚本
```

---

## 📞 技术支持

如果遇到问题，请提供以下信息：

1. **小程序控制台日志**（微信开发者工具 -> 控制台）
2. **后端日志**：
   ```bash
   tail -100 /var/log/celery/worker.log
   ```
3. **数据库订阅状态**：
   ```bash
   sudo -u postgres psql -d health_db -c "SELECT * FROM user_notification_settings WHERE user_id = 3;"
   ```
4. **错误截图**

---

**配置完成！** 🎉

现在您可以开始使用小程序订阅推送功能了！
