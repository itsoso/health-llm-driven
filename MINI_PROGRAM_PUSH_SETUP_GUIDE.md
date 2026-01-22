# 📱 小程序推送配置完整指南

> 微信小程序订阅消息推送配置教程

---

## 📋 目录

1. [配置概览](#配置概览)
2. [微信公众平台配置](#微信公众平台配置)
3. [后端环境变量配置](#后端环境变量配置)
4. [小程序端配置](#小程序端配置)
5. [测试验证](#测试验证)
6. [常见问题](#常见问题)

---

## 🎯 配置概览

### 推送类型

| 推送类型 | 说明 | 触发时机 | 配置状态 |
|---------|------|---------|---------|
| 健康提醒 | 喝水、洗鼻、运动等提醒 | 定时触发 | ⏳ 待配置 |
| 早间简报 | 每日健康数据摘要 | 每天 7:30 | ⏳ 待配置 |
| 健康预警 | 异常指标提醒 | 数据异常时 | ⏳ 待配置 |
| 目标进度 | 健康目标完成度 | 每周一次 | ⏳ 待配置 |
| 周报通知 | 每周健康报告 | 每周一 9:00 | ⏳ 待配置 |

### 配置流程

```
1. 微信公众平台申请模板 
   ↓
2. 获取模板ID
   ↓
3. 配置后端环境变量
   ↓
4. 配置小程序前端
   ↓
5. 用户授权订阅
   ↓
6. 后端发送推送
```

---

## 🔧 微信公众平台配置

### 步骤 1: 登录微信公众平台

1. 访问 https://mp.weixin.qq.com/
2. 使用小程序管理员账号登录
3. 进入对应的小程序

### 步骤 2: 申请订阅消息模板

1. 左侧菜单：**功能** → **订阅消息**
2. 点击 **选用模板**
3. 搜索并添加以下类型的模板：

#### 2.1 健康提醒模板

**关键词**: 健康提醒、事项提醒、待办提醒

**推荐模板格式**:
```
{{thing1.DATA}}      # 提醒标题
{{thing2.DATA}}      # 提醒内容
{{time3.DATA}}       # 提醒时间
{{thing4.DATA}}      # 温馨提示
```

**示例**:
```
提醒标题: 💧 喝水提醒
提醒内容: 您已经2小时没有喝水了
提醒时间: 2026-01-22 14:30
温馨提示: 保持充足水分有助于健康
```

#### 2.2 早间简报模板

**关键词**: 数据统计、日报、健康报告

**推荐模板格式**:
```
{{thing1.DATA}}      # 简报标题
{{thing2.DATA}}      # 睡眠数据
{{thing3.DATA}}      # 运动数据
{{thing4.DATA}}      # 健康建议
{{time5.DATA}}       # 日期
```

#### 2.3 健康预警模板

**关键词**: 异常提醒、预警通知

**推荐模板格式**:
```
{{thing1.DATA}}      # 预警类型
{{thing2.DATA}}      # 异常数据
{{thing3.DATA}}      # 建议措施
{{time4.DATA}}       # 检测时间
```

#### 2.4 目标进度模板

**关键词**: 进度提醒、任务进度

**推荐模板格式**:
```
{{thing1.DATA}}      # 目标名称
{{character_string2.DATA}}  # 完成进度
{{thing3.DATA}}      # 剩余天数
{{thing4.DATA}}      # 鼓励语
```

#### 2.5 周报模板

**关键词**: 周报、数据报告

**推荐模板格式**:
```
{{thing1.DATA}}      # 报告标题
{{thing2.DATA}}      # 本周总结
{{thing3.DATA}}      # 数据亮点
{{thing4.DATA}}      # 下周建议
{{time5.DATA}}       # 统计周期
```

### 步骤 3: 记录模板ID

添加模板后，会生成唯一的**模板ID**（格式如：`xxxxxxxxxxxxxxxxxxxxxxxxxxx`）

**重要**: 请记录每个模板的ID，后续配置需要用到。

---

## ⚙️ 后端环境变量配置

### 配置文件位置

```bash
/opt/health-app/backend/.env
```

### 必需配置

```bash
# 微信小程序基础配置
WECHAT_APPID=wx1234567890abcdef          # 小程序 AppID
WECHAT_SECRET=abcdef1234567890abcdef12   # 小程序 AppSecret

# 或者使用这个命名（两者选其一）
WECHAT_MINI_APP_ID=wx1234567890abcdef
WECHAT_MINI_APP_SECRET=abcdef1234567890abcdef12

# 订阅消息模板ID（替换为实际的模板ID）
WECHAT_TEMPLATE_REMINDER=xxxxxxxxxxxxxxxxxxxxxxxxxxx     # 健康提醒
WECHAT_TEMPLATE_BRIEFING=xxxxxxxxxxxxxxxxxxxxxxxxxxx     # 早间简报
WECHAT_TEMPLATE_ALERT=xxxxxxxxxxxxxxxxxxxxxxxxxxx        # 健康预警
WECHAT_TEMPLATE_GOAL=xxxxxxxxxxxxxxxxxxxxxxxxxxx         # 目标进度
WECHAT_TEMPLATE_WEEKLY=xxxxxxxxxxxxxxxxxxxxxxxxxxx       # 周报
```

### 获取 AppID 和 AppSecret

1. 微信公众平台 → **开发** → **开发管理** → **开发设置**
2. 找到 **AppID (小程序ID)** 和 **AppSecret (小程序密钥)**
3. 如果 AppSecret 未生成，点击 **生成** 并妥善保存

### 配置示例

```bash
# 完整配置示例
WECHAT_APPID=wx8a1b2c3d4e5f6789
WECHAT_SECRET=1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p

WECHAT_TEMPLATE_REMINDER=7Hs8Kj9Lm0Np1Qr2St3Uv4Wx5Yz6
WECHAT_TEMPLATE_BRIEFING=8Jt9Ku0Lv1Mw2Nx3Oy4Pz5Qa6Rb7
WECHAT_TEMPLATE_ALERT=9Ku0Lv1Mw2Nx3Oy4Pz5Qa6Rb7Sc8
WECHAT_TEMPLATE_GOAL=0Lv1Mw2Nx3Oy4Pz5Qa6Rb7Sc8Td9
WECHAT_TEMPLATE_WEEKLY=1Mw2Nx3Oy4Pz5Qa6Rb7Sc8Td9Ue0
```

### 应用配置

```bash
# 1. 编辑配置文件
ssh root@39.98.206.178
cd /opt/health-app/backend
vim .env

# 2. 添加上述配置

# 3. 重启后端服务
systemctl restart health-backend

# 4. 验证配置
systemctl status health-backend
```

---

## 📱 小程序端配置

### 配置文件位置

```
packages/mini-program/src/services/subscribe.ts
```

### 步骤 1: 更新模板ID

打开 `subscribe.ts` 文件，找到 `TEMPLATE_IDS` 配置：

```typescript
export const TEMPLATE_IDS = {
  // 健康提醒模板（用于喝水、洗鼻、运动等提醒）
  HEALTH_REMINDER: '7Hs8Kj9Lm0Np1Qr2St3Uv4Wx5Yz6', // 替换为实际模板ID
  
  // 早间简报模板
  MORNING_BRIEFING: '8Jt9Ku0Lv1Mw2Nx3Oy4Pz5Qa6Rb7', // 替换为实际模板ID
  
  // 健康预警模板
  HEALTH_ALERT: '9Ku0Lv1Mw2Nx3Oy4Pz5Qa6Rb7Sc8', // 替换为实际模板ID
  
  // 目标进度模板
  GOAL_PROGRESS: '0Lv1Mw2Nx3Oy4Pz5Qa6Rb7Sc8Td9', // 替换为实际模板ID
  
  // 周报模板
  WEEKLY_REPORT: '1Mw2Nx3Oy4Pz5Qa6Rb7Sc8Td9Ue0', // 替换为实际模板ID
};
```

### 步骤 2: 重新编译小程序

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program

# 安装依赖（如果还没安装）
npm install

# 编译小程序
npm run build:weapp

# 编译完成后，dist 目录会生成小程序代码
```

### 步骤 3: 上传小程序

#### 方式 1: 使用微信开发者工具

1. 打开微信开发者工具
2. 导入项目：选择 `packages/mini-program/dist` 目录
3. 填写 AppID
4. 点击 **上传** → 填写版本号和备注
5. 登录微信公众平台 → **版本管理** → 提交审核

#### 方式 2: 使用命令行工具（推荐）

```bash
# 安装 miniprogram-ci
npm install -g miniprogram-ci

# 上传代码
miniprogram-ci upload \
  --pp ./packages/mini-program/dist \
  --pkp ./packages/mini-program/private.key \
  --appid wx8a1b2c3d4e5f6789 \
  --uv 1.0.0 \
  --ud "配置订阅消息推送"
```

---

## 🧪 测试验证

### 1. 测试订阅授权

在小程序中测试订阅功能：

```typescript
// 在设置页面或合适的位置调用
import { requestAllSubscriptions } from '@/services/subscribe';

// 请求订阅所有消息
const result = await requestAllSubscriptions();

if (result.success) {
  console.log('订阅成功:', result.acceptedTemplates);
} else {
  console.log('订阅失败:', result.error);
}
```

### 2. 测试推送发送

#### 后端测试脚本

```python
# backend/scripts/test_wechat_push.py
import asyncio
from app.services.notification.wechat_push import WeChatPushService

async def test_push():
    service = WeChatPushService()
    
    # 测试健康提醒
    result = await service.send_health_reminder(
        openid="用户的openid",
        template_id="健康提醒模板ID",
        reminder_title="💧 喝水提醒",
        reminder_content="您已经2小时没有喝水了",
        page="pages/index/index"
    )
    
    print("推送结果:", result)

if __name__ == "__main__":
    asyncio.run(test_push())
```

#### 运行测试

```bash
cd /opt/health-app/backend
python3 scripts/test_wechat_push.py
```

### 3. 查看推送日志

```bash
# 查看后端日志
tail -f /var/log/health-backend/app.log | grep "微信订阅消息"

# 查看 Celery 日志（定时任务）
tail -f /var/log/celery/worker.log | grep "推送"
```

### 4. 数据库验证

```sql
-- 查看用户订阅设置
SELECT 
    u.id,
    u.username,
    u.wechat_openid,
    uns.enabled,
    uns.wechat_enabled,
    uns.wechat_template_ids
FROM users u
LEFT JOIN user_notification_settings uns ON u.id = uns.user_id
WHERE u.wechat_openid IS NOT NULL;

-- 查看推送日志
SELECT 
    id,
    user_id,
    notification_type,
    channel,
    status,
    created_at,
    sent_at,
    error_message
FROM notification_logs
ORDER BY created_at DESC
LIMIT 20;
```

---

## 🐛 常见问题

### 问题 1: 推送失败 - errcode 43101

**错误信息**: "用户拒绝接受消息"

**原因**: 
- 用户未订阅此类消息
- 用户订阅已过期（微信订阅消息有效期为1次）

**解决方法**:
1. 引导用户重新订阅
2. 在小程序中添加订阅引导页面
3. 在关键操作后提示用户订阅

```typescript
// 在合适的时机提示订阅
import { showSubscribeGuide } from '@/services/subscribe';

// 例如：用户完成打卡后
await showSubscribeGuide();
```

### 问题 2: 推送失败 - errcode 47003

**错误信息**: "模板参数不正确"

**原因**: 
- 模板参数格式不匹配
- 参数值超出长度限制

**解决方法**:
1. 检查模板参数格式
2. 确保参数值符合微信要求：
   - `thing` 类型：最多 20 个字符
   - `character_string` 类型：最多 32 个字符
   - `time` 类型：标准时间格式

### 问题 3: 无法获取 access_token

**错误信息**: "invalid appid" 或 "invalid appsecret"

**原因**: 
- AppID 或 AppSecret 配置错误
- 配置文件未生效

**解决方法**:
```bash
# 1. 检查配置
cat /opt/health-app/backend/.env | grep WECHAT

# 2. 验证配置是否正确
# 登录微信公众平台确认 AppID 和 AppSecret

# 3. 重启服务
systemctl restart health-backend
```

### 问题 4: 用户订阅后仍收不到推送

**排查步骤**:

1. **检查用户 OpenID**
```sql
SELECT wechat_openid FROM users WHERE id = 1;
```

2. **检查订阅设置**
```sql
SELECT * FROM user_notification_settings WHERE user_id = 1;
```

3. **检查推送日志**
```sql
SELECT * FROM notification_logs 
WHERE user_id = 1 
ORDER BY created_at DESC 
LIMIT 10;
```

4. **手动测试推送**
```bash
# 使用后端 API 测试
curl -X POST https://health.westwetlandtech.com/api/v1/notification/test-push \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试推送",
    "content": "这是一条测试消息",
    "channel": "wechat"
  }'
```

### 问题 5: 模板ID配置不生效

**原因**: 前端和后端配置不一致

**解决方法**:

1. **确保前端配置正确**
```typescript
// packages/mini-program/src/services/subscribe.ts
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: '实际的模板ID',
  // ...
};
```

2. **确保后端配置正确**
```bash
# /opt/health-app/backend/.env
WECHAT_TEMPLATE_REMINDER=实际的模板ID
```

3. **重新编译并上传小程序**
```bash
cd packages/mini-program
npm run build:weapp
# 使用微信开发者工具上传
```

4. **重启后端服务**
```bash
systemctl restart health-backend
```

---

## 📊 推送效果监控

### 监控指标

```sql
-- 推送成功率统计
SELECT 
    notification_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as success,
    ROUND(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as success_rate
FROM notification_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY notification_type;

-- 用户订阅情况统计
SELECT 
    COUNT(*) as total_users,
    SUM(CASE WHEN uns.enabled = true THEN 1 ELSE 0 END) as subscribed_users,
    SUM(CASE WHEN uns.wechat_template_ids IS NOT NULL THEN 1 ELSE 0 END) as has_templates
FROM users u
LEFT JOIN user_notification_settings uns ON u.id = uns.user_id
WHERE u.wechat_openid IS NOT NULL;
```

---

## 🚀 部署检查清单

部署前请确认以下项目：

- [ ] 微信公众平台已申请所有需要的订阅消息模板
- [ ] 已记录所有模板ID
- [ ] 后端 `.env` 文件已配置 `WECHAT_APPID` 和 `WECHAT_SECRET`
- [ ] 后端 `.env` 文件已配置所有 `WECHAT_TEMPLATE_*` 变量
- [ ] 小程序 `subscribe.ts` 已更新所有模板ID
- [ ] 小程序已重新编译 (`npm run build:weapp`)
- [ ] 小程序已上传到微信公众平台
- [ ] 后端服务已重启 (`systemctl restart health-backend`)
- [ ] 已测试订阅授权流程
- [ ] 已测试推送发送功能
- [ ] 已配置 Celery 定时任务（用于定时推送）

---

## 📞 技术支持

如遇到问题，请提供以下信息：

1. **错误日志**: 后端日志中的错误信息
2. **配置信息**: 脱敏后的配置（不要包含密钥）
3. **测试结果**: 订阅授权和推送测试的结果
4. **用户ID**: 测试用户的ID
5. **推送类型**: 哪种类型的推送失败

---

**配置日期**: 2026-01-22  
**文档版本**: v1.0  
**维护者**: Health LLM Team
