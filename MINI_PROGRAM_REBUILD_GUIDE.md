# 小程序重新构建和上传指南

## 问题说明

您的小程序中没有显示"消息提醒"模块，这是因为：

1. ✅ **代码已配置**：订阅消息的模板 ID 已经在代码中配置完成
2. ❌ **未重新构建**：小程序代码没有重新编译，所以新功能没有生效
3. ❌ **未重新上传**：即使本地构建了，也需要重新上传到微信小程序平台

## 解决方案：重新构建并上传小程序

### 步骤 1：重新构建小程序

在项目根目录执行：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

如果遇到依赖问题，先安装依赖：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
pnpm install
```

### 步骤 2：打开微信开发者工具

1. 打开**微信开发者工具**
2. 选择**导入项目**
3. 项目目录选择：`/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program`
4. AppID 填写：`wx169f93db056a7dd5`

### 步骤 3：预览和测试

在微信开发者工具中：

1. 点击**编译**按钮
2. 在模拟器中查看"我的"页面
3. 确认"消息提醒"模块已显示
4. 点击"开启消息提醒"测试功能

### 步骤 4：上传到微信平台

1. 点击右上角的**上传**按钮
2. 填写版本号（如 `v1.0.1`）
3. 填写项目备注（如 "添加订阅消息功能"）
4. 点击**上传**

### 步骤 5：提交审核

1. 登录[微信公众平台](https://mp.weixin.qq.com/)
2. 进入**开发管理** -> **版本管理**
3. 找到刚上传的版本
4. 点击**提交审核**
5. 填写审核信息：
   - **版本描述**：添加订阅消息功能，支持健康提醒、早间简报等通知
   - **测试账号**：提供测试账号和密码

### 步骤 6：发布上线

审核通过后：

1. 在**版本管理**中找到审核通过的版本
2. 点击**发布**
3. 用户更新小程序后即可看到新功能

## 订阅消息模板 ID 配置

当前已配置的模板 ID（位于 `packages/mini-program/src/services/subscribe.ts`）：

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo',
};
```

这些模板 ID 已经在微信公众平台配置完成，无需修改。

## 验证功能是否生效

上传新版本后，在微信开发者工具或手机上测试：

1. 打开小程序
2. 进入"我的"页面
3. 应该能看到"消息提醒"模块
4. 点击"开启消息提醒"
5. 系统会弹出订阅授权窗口
6. 选择要订阅的消息类型并允许

## 常见问题

### Q1: 构建失败，提示 "Cannot find module"

**A**: 这是依赖问题，执行以下命令：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
rm -rf node_modules
rm -rf packages/mini-program/node_modules
pnpm install
```

### Q2: 微信开发者工具中看不到新功能

**A**: 
1. 确认已执行 `npm run build:weapp`
2. 在微信开发者工具中点击**编译**按钮
3. 清除缓存：**工具** -> **清除缓存** -> **清除全部缓存**

### Q3: 上传后用户看不到新功能

**A**: 
- 新版本需要提交审核并发布后才能生效
- 用户需要重新打开小程序（或删除后重新搜索）才能更新到最新版本
- 可以在**版本管理**中强制更新

### Q4: 审核不通过

**A**: 常见原因：
- **功能描述不清**：在审核说明中详细描述订阅消息的用途
- **测试账号问题**：提供可用的测试账号
- **隐私政策**：确保小程序有隐私政策说明

## 快速命令参考

```bash
# 1. 安装依赖
cd /Users/liqiuhua/work/personal/health-llm-driven
pnpm install

# 2. 构建小程序
cd packages/mini-program
npm run build:weapp

# 3. 检查构建结果
ls -la dist/

# 4. 验证模板 ID 是否包含在构建中
grep -r "rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI" dist/
```

## 相关文档

- [小程序订阅提醒设置指南](./MINI_PROGRAM_SUBSCRIBE_GUIDE.md)
- [微信小程序订阅消息官方文档](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/subscribe-message.html)

---

**最后更新**：2026-01-22  
**维护人员**：AI Assistant
