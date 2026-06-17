# 小程序个人资料编辑功能修复

## 问题描述

用户反馈小程序的个人资料页面无法编辑个人信息，输入框无法输入内容。

## 问题分析

在 Taro 小程序中，`Input` 组件可能因为以下原因无法正常编辑：

1. **缺少必要属性**：某些小程序环境需要显式设置 `disabled={false}` 来确保输入框可编辑
2. **CSS 样式干扰**：可能存在 CSS 样式阻止了用户交互
3. **事件未正确绑定**：`onInput` 事件可能未正确触发

## 修复方案

### 1. 为所有 Input 组件添加必要属性

**文件：`packages/mini-program/src/pages/profile/index.tsx`**

为所有 `Input` 组件添加以下属性：

```tsx
<Input
  type="number"
  value={profile.height_cm?.toString() || ''}
  onInput={e => updateField('height_cm', e.detail.value ? Number(e.detail.value) : null)}
  placeholder="输入身高"
  className="form-input"
  disabled={false}  // ✅ 显式设置为可编辑
  focus={false}     // ✅ 避免自动聚焦
/>
```

**修改的输入框：**
- ✅ 身高输入框
- ✅ 当前体重输入框
- ✅ 所在城市输入框
- ✅ 目标步数输入框
- ✅ 目标睡眠输入框
- ✅ 目标饮水输入框
- ✅ 目标运动输入框
- ✅ 目标体重输入框

### 2. 优化 CSS 样式确保可交互

**文件：`packages/mini-program/src/pages/profile/index.scss`**

为 `.form-input` 类添加交互相关样式：

```scss
.form-input {
  width: 100%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  padding: 24px;
  color: #fff;
  font-size: 32px;
  box-sizing: border-box;
  
  // ✅ 确保输入框可以交互
  pointer-events: auto;
  user-select: text;
  -webkit-user-select: text;
}
```

**CSS 属性说明：**
- `pointer-events: auto` - 确保元素可以接收鼠标/触摸事件
- `user-select: text` - 允许用户选择文本
- `-webkit-user-select: text` - WebKit 内核兼容性

### 3. 添加调试日志

为 `updateField` 函数添加日志，便于追踪问题：

```tsx
const updateField = (field: keyof UserProfile, value: any) => {
  console.log('[Profile] 更新字段:', field, '=', value);  // ✅ 调试日志
  if (profile) {
    setProfile({ ...profile, [field]: value });
  }
};
```

## 技术要点

### 1. Taro Input 组件特性

在 Taro 小程序中，`Input` 组件的行为可能与 Web 不同：

```tsx
// ❌ 可能无法编辑（某些环境）
<Input value={value} onInput={handler} />

// ✅ 显式设置可编辑
<Input 
  value={value} 
  onInput={handler}
  disabled={false}  // 显式设置
  focus={false}     // 避免自动聚焦
/>
```

### 2. 输入类型选择

不同的输入类型适用于不同场景：

| 类型 | 用途 | 示例 |
|------|------|------|
| `text` | 普通文本 | 城市名称 |
| `number` | 整数 | 步数、年龄 |
| `digit` | 带小数点的数字 | 体重、身高 |

### 3. 事件处理

Taro Input 的 `onInput` 事件返回的数据结构：

```tsx
onInput={e => {
  // e.detail.value 是输入的值（字符串）
  const value = e.detail.value;
  
  // 需要转换为数字
  const numValue = Number(value);
  
  // 处理空值
  const finalValue = value ? numValue : null;
  
  updateField('field_name', finalValue);
}}
```

## 测试建议

### 1. 基本输入测试

- [ ] 点击"身高"输入框，能否弹出键盘
- [ ] 输入数字，能否正常显示
- [ ] 输入后失焦，数据是否保存到 state
- [ ] 点击"保存设置"，数据是否成功提交

### 2. 不同输入类型测试

- [ ] 数字输入框（身高、体重）- 只能输入数字
- [ ] 小数输入框（目标睡眠）- 可以输入小数点
- [ ] 文本输入框（城市）- 可以输入中文和英文

### 3. 选择器测试

- [ ] 性别选择器能否正常弹出
- [ ] 血型选择器能否正常选择
- [ ] 时区选择器能否正常选择

### 4. 标签选择测试

- [ ] 慢性病史标签能否点击选中/取消
- [ ] 过敏源标签能否点击选中/取消
- [ ] 已选标签是否正确显示

### 5. 数据持久化测试

- [ ] 修改数据后点击保存
- [ ] 返回上一页再进入
- [ ] 数据是否正确保存

## 调试方法

### 1. 查看控制台日志

在小程序开发工具中查看控制台，应该能看到：

```
[Profile] 更新字段: height_cm = 175
[Profile] 更新字段: current_weight_kg = 70
```

### 2. 检查网络请求

保存时应该发送 PUT 请求到 `/api/v1/profile/me`：

```json
{
  "gender": "male",
  "height_cm": 175,
  "current_weight_kg": 70,
  "city": "北京",
  ...
}
```

### 3. 检查响应

成功保存后应该看到 Toast 提示："保存成功"

## 常见问题

### Q1: 输入框点击后没有反应

**可能原因：**
- CSS 样式 `pointer-events: none` 阻止了交互
- Input 组件被其他元素遮挡
- `disabled` 属性被设置为 `true`

**解决方案：**
- 检查 CSS 样式
- 检查 z-index 层级
- 确保 `disabled={false}`

### Q2: 输入后数据没有更新

**可能原因：**
- `onInput` 事件未正确绑定
- `updateField` 函数未正确更新 state
- `value` 属性未绑定到 state

**解决方案：**
- 检查事件处理函数
- 添加 console.log 调试
- 确认 state 更新逻辑

### Q3: 保存后数据丢失

**可能原因：**
- API 请求失败
- 数据格式不正确
- 后端验证失败

**解决方案：**
- 检查网络请求
- 查看后端日志
- 验证数据格式

## 部署状态

- ✅ 代码已提交到 GitHub
- ⏳ 需要重新编译小程序
- ⏳ 需要上传到微信小程序后台
- ⏳ 需要提交审核（如果是线上版本）

## 后续步骤

### 1. 本地测试

```bash
cd packages/mini-program
npm run dev:weapp
```

在微信开发者工具中测试所有输入框是否可以正常编辑。

### 2. 编译生产版本

```bash
cd packages/mini-program
npm run build:weapp
```

### 3. 上传到微信小程序后台

使用微信开发者工具上传代码包。

### 4. 提交审核

如果需要更新线上版本，提交微信审核。

## 相关文件

### 已修改的文件

1. `packages/mini-program/src/pages/profile/index.tsx` - 个人资料页面逻辑
2. `packages/mini-program/src/pages/profile/index.scss` - 个人资料页面样式

### 未修改的文件

- 后端 API 无需修改
- 其他小程序页面无需修改

## 注意事项

1. **兼容性**
   - 确保在不同微信版本中测试
   - 检查 iOS 和 Android 平台的表现

2. **性能**
   - 输入时不要频繁调用 API
   - 使用防抖处理频繁输入

3. **用户体验**
   - 输入框应该有清晰的焦点状态
   - 保存成功后给予明确反馈
   - 输入错误时给予提示

## 后续优化建议

1. **输入验证**
   - 添加输入范围验证（如身高 50-250cm）
   - 添加格式验证（如手机号格式）
   - 实时显示验证错误

2. **自动保存**
   - 输入完成后自动保存（防抖）
   - 避免用户忘记点击保存按钮

3. **离线支持**
   - 本地缓存用户输入
   - 网络恢复后自动同步

4. **更好的反馈**
   - 显示保存状态（保存中、已保存、保存失败）
   - 未保存时退出给予提示

---

**修复完成时间**: 2026-01-22  
**修复人**: AI Assistant  
**Commit**: c4e56f5  
**版本**: v1.0
