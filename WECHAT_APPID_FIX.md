# 🔧 微信 AppID 配置修复

> 2026-01-22 - 修复微信登录失败问题

---

## 🐛 问题描述

**错误信息**:
```
微信登录失败: invalid appid, rid: 6971ae4f-577ccca7-1dc4d658
```

**原因**: 
配置文件中使用了测试 AppID `wx1234567890abcdef`，这不是真实的小程序 AppID。

---

## ✅ 修复内容

### 1. 删除测试配置

从 `/opt/health-app/backend/.env` 中删除了以下测试配置：
```bash
# ❌ 已删除（测试配置）
WECHAT_APPID=wx1234567890abcdef
WECHAT_SECRET=abcdef1234567890abcdef12
WECHAT_MINI_APP_ID=wx1234567890abcdef
WECHAT_MINI_APP_SECRET=abcdef1234567890abcdef12
```

### 2. 保留正确配置

保留了真实的小程序配置：
```bash
# ✅ 正确的配置
WECHAT_APPID=wx169f93db056a7dd5
WECHAT_SECRET=bd49ab852e5eda5c423f7536910eef59
```

### 3. 重启服务

```bash
systemctl restart health-backend
# ✅ 服务已重启并正常运行
```

---

## 📋 正确的配置

### 服务器后端配置

**文件**: `/opt/health-app/backend/.env`

```bash
# 微信小程序基础配置（正确）
WECHAT_APPID=wx169f93db056a7dd5
WECHAT_SECRET=bd49ab852e5eda5c423f7536910eef59

# 订阅消息模板ID
WECHAT_TEMPLATE_REMINDER=rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI
WECHAT_TEMPLATE_BRIEFING=A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg
WECHAT_TEMPLATE_ALERT=JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg
WECHAT_TEMPLATE_GOAL=buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE
WECHAT_TEMPLATE_WEEKLY=sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo
```

### 小程序配置

**文件**: `packages/mini-program/project.config.json`

```json
{
  "appid": "wx169f93db056a7dd5"
}
```

**文件**: `packages/mini-program/src/services/subscribe.ts`

```typescript
export const TEMPLATE_IDS = {
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo',
};
```

---

## 🧪 验证修复

### 1. 检查配置

```bash
# 检查后端配置
ssh root@39.98.206.178 "cd /opt/health-app/backend && grep -E '^WECHAT_(APPID|SECRET)' .env"

# 预期输出:
# WECHAT_APPID=wx169f93db056a7dd5
# WECHAT_SECRET=bd49ab852e5eda5c423f7536910eef59
```

### 2. 检查服务状态

```bash
ssh root@39.98.206.178 "systemctl status health-backend"

# 预期: Active: active (running)
```

### 3. 测试微信登录

1. 打开小程序
2. 点击 **微信登录** 按钮
3. 授权登录
4. **预期**: 登录成功，不再显示 "invalid appid" 错误

---

## 📝 注意事项

### ⚠️ 重要提醒

1. **不要使用测试 AppID**: `wx1234567890abcdef` 是示例 AppID，不能用于实际登录
2. **AppID 必须匹配**: 后端配置的 AppID 必须与小程序 `project.config.json` 中的 AppID 一致
3. **Secret 保密**: AppSecret 是敏感信息，不要泄露或提交到代码仓库

### 正确的配置流程

1. **获取真实 AppID 和 AppSecret**
   - 登录微信公众平台
   - 进入 **开发** → **开发管理** → **开发设置**
   - 复制 AppID 和 AppSecret

2. **配置后端**
   - 编辑 `/opt/health-app/backend/.env`
   - 设置 `WECHAT_APPID` 和 `WECHAT_SECRET`
   - 重启后端服务

3. **配置小程序**
   - 确认 `project.config.json` 中的 `appid` 正确
   - 编译并上传小程序

---

## 🔍 问题排查

### 如果仍然出现 "invalid appid" 错误

1. **检查 AppID 是否正确**
   ```bash
   ssh root@39.98.206.178 "grep WECHAT_APPID /opt/health-app/backend/.env"
   ```

2. **检查是否有重复配置**
   ```bash
   ssh root@39.98.206.178 "grep -n WECHAT_APPID /opt/health-app/backend/.env"
   ```
   - 如果有多行，只保留正确的那一行

3. **确认服务已重启**
   ```bash
   ssh root@39.98.206.178 "systemctl restart health-backend"
   ```

4. **查看后端日志**
   ```bash
   ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager | grep -i wechat"
   ```

---

## 📊 配置对比

| 配置项 | 错误配置 | 正确配置 |
|--------|---------|---------|
| WECHAT_APPID | `wx1234567890abcdef` ❌ | `wx169f93db056a7dd5` ✅ |
| WECHAT_SECRET | `abcdef1234567890abcdef12` ❌ | `bd49ab852e5eda5c423f7536910eef59` ✅ |

---

## ✅ 修复结果

- ✅ 删除了测试配置
- ✅ 保留了正确的 AppID 和 Secret
- ✅ 后端服务已重启
- ✅ 配置已验证
- ✅ 微信登录应该恢复正常

---

**修复时间**: 2026-01-22 12:58  
**问题**: invalid appid 错误  
**原因**: 使用了测试 AppID  
**解决**: 恢复正确的 AppID 配置  
**状态**: ✅ 已修复
