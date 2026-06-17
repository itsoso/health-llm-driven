# 小程序订阅消息优化说明

## 问题背景

用户在小程序中开启消息提醒时，遇到以下问题：
1. 只成功订阅了1个模板，其他2个被拒绝
2. 出现错误：`requestSubscribeMessage:fail can only be invoked by user TAP gesture.`

## 问题原因

### 微信订阅消息限制

1. **每次最多3个模板**：`wx.requestSubscribeMessage` 一次调用最多只能请求3个模板ID
2. **必须由用户点击触发**：订阅请求必须在用户点击事件的同步调用链中，不能在异步回调或延迟后调用
3. **用户可以选择性授权**：用户可以选择授权部分模板，拒绝其他模板

### 原代码问题

```typescript
// ❌ 错误做法：自动分批请求
for (let i = 0; i < allKeys.length; i += 3) {
  const batch = allKeys.slice(i, i + 3);
  const batchResult = await requestSubscribe(batch); // 第二次调用时已不在用户点击上下文中
}
```

当有5个模板时：
- 第1次请求（前3个）：✅ 正常，在用户点击上下文中
- 第2次请求（后2个）：❌ 失败，已经不在用户点击上下文中

## 解决方案

### 1. 优先级策略

只请求最重要的3个模板，按优先级排序：

```typescript
// ✅ 正确做法：只请求前3个最重要的模板
const priorityKeys = ['HEALTH_REMINDER', 'MORNING_BRIEFING', 'HEALTH_ALERT'];
return await requestSubscribe(priorityKeys);
```

**模板优先级：**
1. 🔔 **健康提醒** (HEALTH_REMINDER) - 喝水、洗鼻、运动等日常提醒
2. 🌅 **早间简报** (MORNING_BRIEFING) - 每日健康摘要
3. ⚠️ **健康预警** (HEALTH_ALERT) - 异常健康指标提醒

**暂不默认请求的模板：**
- 📊 目标进度 (GOAL_PROGRESS)
- 📈 周报通知 (WEEKLY_REPORT)

### 2. 用户体验优化

#### 提示信息优化

```typescript
// 显示授权和未授权的数量
let message = `已开启${acceptedCount}项提醒`;
if (rejectedCount > 0) {
  message += `，${rejectedCount}项未授权`;
}
```

#### 多次订阅支持

用户可以多次点击"开启消息提醒"或"添加更多订阅"按钮：
- 第1次：请求前3个模板
- 第2次：再次请求前3个模板（用户可以重新授权之前拒绝的）

### 3. 后续扩展方案

如果需要订阅更多模板，可以：

**方案A：分步引导**
```typescript
// 在不同场景下请求不同模板
- 完成目标打卡后 → 请求"目标进度"模板
- 查看周报时 → 请求"周报通知"模板
```

**方案B：手动选择**
```typescript
// 提供模板列表，让用户选择要订阅的模板
const templates = [
  { key: 'HEALTH_REMINDER', name: '健康提醒', desc: '喝水、运动等日常提醒' },
  { key: 'MORNING_BRIEFING', name: '早间简报', desc: '每日健康数据摘要' },
  // ...
];
```

## 当前配置

### 模板配置 (packages/mini-program/src/services/subscribe.ts)

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo',
};
```

### 默认请求的模板

```typescript
const priorityKeys = ['HEALTH_REMINDER', 'MORNING_BRIEFING', 'HEALTH_ALERT'];
```

## 用户操作指南

### 如何订阅消息提醒

1. 打开小程序，进入"我的"页面
2. 点击"开启消息提醒"按钮
3. 在弹出的授权窗口中，勾选要接收的消息类型
4. 点击"允许"完成授权

### 如何添加更多订阅

1. 进入"我的"页面
2. 在"消息提醒"区域，点击"添加更多订阅"
3. 重新授权之前拒绝的模板，或授权新的模板类型

### 如何管理订阅

1. 进入"我的"页面
2. 查看"已订阅 X项"状态
3. 可以通过开关控制是否接收通知（不会取消订阅，只是暂时关闭）

## 技术细节

### 订阅流程

```
用户点击按钮
    ↓
requestAllSubscriptions()
    ↓
requestSubscribe(['HEALTH_REMINDER', 'MORNING_BRIEFING', 'HEALTH_ALERT'])
    ↓
wx.requestSubscribeMessage({ tmplIds: [...] })
    ↓
用户授权
    ↓
saveSubscribeSettings(acceptedTemplates)
    ↓
POST /api/wechat/subscribe/settings
    ↓
保存到数据库
```

### 数据存储

**数据库表：** `user_notification_settings`

**字段：**
- `wechat_template_ids`: JSON 格式，存储已授权的模板ID
  ```json
  {
    "reminder": "rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI",
    "morning_briefing": "A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg"
  }
  ```

### API 接口

**获取订阅设置：**
```
GET /api/wechat/subscribe/settings
```

**保存订阅设置：**
```
POST /api/wechat/subscribe/settings
Body: {
  "template_ids": {
    "reminder": "rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI",
    "morning_briefing": "A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg"
  },
  "enabled": true
}
```

## 注意事项

1. **用户拒绝后的限制**：用户拒绝某个模板后，7天内不会再弹出该模板的授权窗口
2. **模板ID有效性**：确保在微信公众平台申请并配置了正确的模板ID
3. **测试环境**：开发版和体验版可以正常测试订阅消息功能
4. **生产环境**：需要小程序审核通过后才能正常使用

## 相关文档

- [微信小程序订阅消息官方文档](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/subscribe-message.html)
- [MINI_PROGRAM_SUBSCRIBE_GUIDE.md](./MINI_PROGRAM_SUBSCRIBE_GUIDE.md) - 订阅消息设置指南
- [MINI_PROGRAM_REBUILD_GUIDE.md](./MINI_PROGRAM_REBUILD_GUIDE.md) - 小程序构建和发布指南

## 更新日志

- **2026-01-22**: 修复分批请求问题，优化为只请求前3个最重要的模板
- **2026-01-22**: 修复 POST 和 GET 接口的 JSON 解析问题
- **2026-01-22**: 添加数据库字段迁移，支持订阅消息功能
