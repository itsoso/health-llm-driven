# 小程序登录界面调试指南

**问题**: 未登录状态下没有显示邀请码输入框

## 问题分析

### 1. 登录状态判断逻辑

**文件**: `packages/mini-program/src/pages/index/index.tsx`

**关键代码**:
```typescript
// 第52行：登录状态初始值
const [isLoggedIn, setIsLoggedIn] = useState(false);

// 第71-84行：页面加载时检查登录状态
useEffect(() => {
  checkLoginStatus();
  // ... 时间更新逻辑
}, []);

// 第86-93行：页面显示时检查登录状态
Taro.useDidShow(() => {
  const token = getToken();
  if (token) {
    loadHomeData();
  } else {
    checkLoginStatus();
  }
});

// 第95-103行：检查登录状态函数
const checkLoginStatus = async () => {
  const token = getToken();
  setIsLoggedIn(!!token);  // ⚠️ 关键：根据 token 设置登录状态
  if (token) {
    const storedName = Taro.getStorageSync('user_name');
    setUserName(storedName || '自由是自律的泡沫用户');
    loadHomeData();
  }
};

// 第257-311行：未登录页面渲染
if (!isLoggedIn) {
  return (
    <View className="index-page login-page">
      {/* 登录界面，包含邀请码输入框 */}
    </View>
  );
}
```

### 2. Token 获取逻辑

**文件**: `packages/mini-program/src/services/request.ts`

```typescript
// 第10行：Token 存储 key
const TOKEN_KEY = 'access_token';

// 第15-17行：获取 Token
export function getToken(): string | null {
  return Taro.getStorageSync(TOKEN_KEY) || null;
}
```

## 可能的问题

### 问题1: Token 未清除

**症状**: 
- 用户已登录，但 token 无效
- `isLoggedIn = true`，显示已登录页面
- 实际上应该显示登录界面

**检查方法**:
```javascript
// 在微信开发者工具的控制台执行
console.log('Token:', wx.getStorageSync('access_token'));
console.log('User Name:', wx.getStorageSync('user_name'));
```

**解决方法**:
```javascript
// 清除 token
wx.removeStorageSync('access_token');
wx.removeStorageSync('user_name');
// 刷新页面
```

### 问题2: 页面状态未更新

**症状**:
- Token 已清除
- 但页面仍显示已登录状态

**检查方法**:
1. 查看控制台是否有错误
2. 检查 `checkLoginStatus` 是否被调用
3. 检查 `isLoggedIn` 状态

**解决方法**:
1. 重新编译小程序
2. 清除缓存后重新打开

### 问题3: 条件渲染问题

**症状**:
- `isLoggedIn = false`
- 但登录界面不显示

**检查方法**:
```typescript
// 在 index.tsx 中添加调试日志
console.log('isLoggedIn:', isLoggedIn);
console.log('Token:', getToken());
```

## 调试步骤

### 步骤1: 检查 Token 状态

在微信开发者工具的控制台执行：

```javascript
// 检查 token
console.log('Token:', wx.getStorageSync('access_token'));

// 检查用户名
console.log('User Name:', wx.getStorageSync('user_name'));

// 检查所有存储
console.log('All Storage:', wx.getStorageInfoSync());
```

### 步骤2: 清除 Token

如果 token 存在，清除它：

```javascript
wx.removeStorageSync('access_token');
wx.removeStorageSync('user_name');
console.log('Token 已清除');
```

### 步骤3: 刷新页面

1. 点击微信开发者工具的"编译"按钮
2. 或者在控制台执行：
   ```javascript
   wx.reLaunch({ url: '/pages/index/index' });
   ```

### 步骤4: 检查登录界面

确认看到：
1. 标题："自由是自律的泡沫"
2. 副标题："个人健康管理助手"
3. **两个输入框**：
   - 昵称输入框（可选）
   - **邀请码输入框（必填）**
4. 登录按钮："微信一键登录"

### 步骤5: 添加调试日志

修改 `packages/mini-program/src/pages/index/index.tsx`：

```typescript
const checkLoginStatus = async () => {
  const token = getToken();
  console.log('🔍 检查登录状态');
  console.log('  Token:', token);
  console.log('  Token 类型:', typeof token);
  console.log('  Token 长度:', token?.length);
  
  setIsLoggedIn(!!token);
  console.log('  设置 isLoggedIn:', !!token);
  
  if (token) {
    const storedName = Taro.getStorageSync('user_name');
    setUserName(storedName || '自由是自律的泡沫用户');
    loadHomeData();
  }
};

// 在渲染部分添加日志
console.log('🎨 渲染页面');
console.log('  isLoggedIn:', isLoggedIn);
console.log('  userName:', userName);

if (!isLoggedIn) {
  console.log('  ✅ 显示登录页面');
  return (
    <View className="index-page login-page">
      {/* ... */}
    </View>
  );
}

console.log('  ✅ 显示已登录页面');
```

### 步骤6: 重新编译

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

## 常见问题排查

### Q1: 控制台显示 "Token: null" 但仍显示已登录页面

**原因**: 
- 状态更新延迟
- 页面缓存

**解决**:
1. 重新编译小程序
2. 清除缓存
3. 检查是否有其他地方设置了 `isLoggedIn = true`

### Q2: 登录界面显示，但邀请码输入框不显示

**原因**:
- 样式问题
- 输入框被隐藏
- 条件渲染问题

**检查**:
1. 检查样式文件 `index.scss`
2. 检查是否有 `display: none`
3. 检查元素是否被其他元素覆盖

**解决**:
```scss
// 确保输入框样式正确
.login-input {
  width: 100%;
  height: 80px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid $card-border;
  border-radius: $radius-sm;
  padding: 0 20px;
  font-size: 28px;
  color: $text-white;
  margin-bottom: 20px;
  box-sizing: border-box;
  display: block; // 确保显示
  visibility: visible; // 确保可见
}
```

### Q3: 输入框显示，但输入后没有反应

**原因**:
- 状态绑定问题
- 事件处理问题

**检查**:
```typescript
// 确认状态定义
const [inputInviteCode, setInputInviteCode] = useState('');

// 确认输入框绑定
<Input
  className="login-input"
  type="text"
  placeholder="请输入邀请码（必填）"
  value={inputInviteCode}
  onInput={(e) => {
    console.log('输入邀请码:', e.detail.value);
    setInputInviteCode(e.detail.value.toUpperCase());
  }}
  maxlength={20}
/>
```

## 快速测试脚本

在微信开发者工具控制台执行：

```javascript
// 1. 检查当前状态
console.log('=== 当前状态 ===');
console.log('Token:', wx.getStorageSync('access_token'));
console.log('User Name:', wx.getStorageSync('user_name'));

// 2. 清除登录状态
console.log('\n=== 清除登录状态 ===');
wx.removeStorageSync('access_token');
wx.removeStorageSync('user_name');
console.log('已清除');

// 3. 重新加载页面
console.log('\n=== 重新加载页面 ===');
wx.reLaunch({ 
  url: '/pages/index/index',
  success: () => console.log('页面已重新加载'),
  fail: (err) => console.error('重新加载失败:', err)
});
```

## 预期结果

执行上述脚本后，应该看到：

1. **登录界面**:
   ```
   ┌─────────────────────────┐
   │  自由是自律的泡沫       │
   │  个人健康管理助手       │
   │                         │
   │  ┌───────────────────┐  │
   │  │ 输入您的昵称（可选）│  │
   │  └───────────────────┘  │
   │  ┌───────────────────┐  │
   │  │ 请输入邀请码（必填）│  │ ← 这个必须显示
   │  └───────────────────┘  │
   │  ┌───────────────────┐  │
   │  │  微信一键登录      │  │
   │  └───────────────────┘  │
   │                         │
   │  登录即表示同意...      │
   └─────────────────────────┘
   ```

2. **控制台日志**:
   ```
   🔍 检查登录状态
     Token: null
     设置 isLoggedIn: false
   🎨 渲染页面
     isLoggedIn: false
     ✅ 显示登录页面
   ```

## 如果问题仍然存在

### 方案1: 强制显示登录界面

临时修改代码，强制显示登录界面：

```typescript
// 在 index.tsx 顶部添加
const FORCE_SHOW_LOGIN = true; // 调试用

// 修改条件判断
if (!isLoggedIn || FORCE_SHOW_LOGIN) {
  return (
    <View className="index-page login-page">
      {/* 登录界面 */}
    </View>
  );
}
```

### 方案2: 检查编译产物

```bash
# 检查编译后的文件
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist
ls -la

# 检查 pages/index/index.js 是否包含邀请码相关代码
grep -n "邀请码" pages/index/index.js
```

### 方案3: 完全重新编译

```bash
# 清除编译产物
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
rm -rf dist node_modules/.cache

# 重新编译
npm run build:weapp
```

## 总结

**最可能的原因**:
1. Token 未清除，导致 `isLoggedIn = true`
2. 页面缓存，需要重新编译
3. 状态更新延迟

**最快的解决方法**:
1. 在微信开发者工具控制台执行快速测试脚本
2. 清除 token
3. 重新加载页面
4. 确认看到邀请码输入框

**如果仍然不显示**:
1. 添加调试日志
2. 检查控制台输出
3. 确认 `isLoggedIn` 的值
4. 检查样式文件
5. 重新编译小程序

---

**调试人员**: AI Assistant  
**创建时间**: 2026-01-22 16:45  
**状态**: 待验证
