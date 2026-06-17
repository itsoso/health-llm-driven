# 饮食推荐页面布局重新设计

**更新时间**: 2026-01-23  
**目标**: 将关键信息前置，技术细节后置或隐藏，提升用户体验

## 🎯 设计目标

### 用户需求
- ✅ 快速了解今日营养摄入情况
- ✅ 获取重要的健康提醒和建议
- ✅ 查看具体的食物推荐
- ❌ 不需要每次都看技术细节（BMR、TDEE、健康状态）

### 设计原则
1. **关键信息优先**: 用户最关心的内容放在最前面
2. **渐进式展示**: 技术细节可选显示，不干扰主流程
3. **简洁明了**: 减少信息过载，提高可读性

## 📊 布局调整

### 修改前（旧布局）

```
1. 个人信息 + 代谢信息
2. 今日营养进度
3. 健康状态
4. 重要提醒 + 健康提示
5. 食物推荐
6. 科学依据（可展开）
```

**问题**:
- ❌ 技术细节（BMR、TDEE）占据首屏
- ❌ 用户最关心的提醒和推荐在下方
- ❌ 信息层次不清晰

### 修改后（新布局）

```
1. 今日营养进度 ⭐
2. 重要提醒 + 健康提示 ⭐
3. 食物推荐 ⭐
4. [显示详细数据] 按钮
   ↓ (点击后展开)
5. 个人信息 (Debug)
6. 代谢信息 (Debug)
7. 健康状态 (Debug)
8. 科学依据（可展开）
```

**改进**:
- ✅ 关键信息（进度、提醒、推荐）在首屏
- ✅ 技术细节隐藏在 Debug 模式
- ✅ 用户可以按需查看详细数据

## 🔧 实现细节

### 1. 添加 Debug 模式开关

```typescript
// frontend/src/app/diet-recommendation/page.tsx

const [showDebugInfo, setShowDebugInfo] = useState(false)

// 页面标题右侧添加按钮
<button
  onClick={() => setShowDebugInfo(!showDebugInfo)}
  className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-white rounded-lg transition-colors"
>
  {showDebugInfo ? '隐藏详细数据' : '显示详细数据'}
</button>
```

### 2. 重新组织内容顺序

#### 第一行：今日营养进度
```tsx
<div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
  <h2>今日营养进度</h2>
  {/* 热量、蛋白质、碳水、脂肪进度条 */}
</div>
```

#### 第二行：重要提醒 + 健康提示
```tsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
  {/* 重要提醒（红色） */}
  <div className="bg-red-50 border-2 border-red-200">
    <h2>重要提醒</h2>
    {/* 警告列表 */}
  </div>
  
  {/* 健康提示（绿色） */}
  <div className="bg-green-50 border-2 border-green-200">
    <h2>健康提示</h2>
    {/* 提示列表 */}
  </div>
</div>
```

#### 第三行：食物推荐
```tsx
<div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
  <h2>食物推荐</h2>
  {/* 食物推荐卡片 */}
</div>
```

#### Debug 模式：详细数据
```tsx
{showDebugInfo && (
  <div className="space-y-6 mb-6">
    {/* 个人信息 */}
    <div className="bg-white rounded-2xl shadow-lg p-6">...</div>
    
    {/* 代谢信息 */}
    <div className="bg-gradient-to-br from-purple-600 to-blue-600">...</div>
    
    {/* 健康状态 */}
    <div className="bg-white rounded-2xl shadow-lg p-6">...</div>
  </div>
)}
```

## 📱 小程序设计建议

### 布局顺序（与 Web 一致）

```
1. 今日营养进度
   - 热量进度条
   - 蛋白质进度条
   - 碳水进度条
   - 脂肪进度条

2. 重要提醒
   - 红色背景
   - 显著的警告图标

3. 健康提示
   - 绿色背景
   - 灯泡图标

4. 食物推荐
   - 分类显示（蛋白质、碳水、脂肪）
   - 优先级标签

5. [查看详细数据] 按钮
   ↓ 点击后跳转到新页面或展开
   
6. 个人信息（可选）
7. 代谢信息（可选）
8. 健康状态（可选）
```

### 小程序实现要点

#### 1. 使用折叠面板

```jsx
// packages/mini-program/src/pages/diet-recommendation/index.tsx

import { View, Button } from '@tarojs/components'
import { useState } from 'react'

const [showDebug, setShowDebug] = useState(false)

<View className="page">
  {/* 关键信息 */}
  <View className="nutrition-progress">...</View>
  <View className="warnings">...</View>
  <View className="tips">...</View>
  <View className="recommendations">...</View>
  
  {/* Debug 开关 */}
  <Button onClick={() => setShowDebug(!showDebug)}>
    {showDebug ? '隐藏详细数据' : '显示详细数据'}
  </Button>
  
  {/* 详细数据 */}
  {showDebug && (
    <View className="debug-info">
      <View className="user-info">...</View>
      <View className="metabolism">...</View>
      <View className="health-status">...</View>
    </View>
  )}
</View>
```

#### 2. 使用 Taro 的 Collapse 组件

```jsx
import { AtAccordion } from 'taro-ui'

<AtAccordion
  title="查看详细数据"
  icon={{ value: 'chevron-down' }}
>
  {/* 详细数据内容 */}
</AtAccordion>
```

## 🎨 视觉设计

### 颜色方案

| 模块 | 背景色 | 边框色 | 文字色 | 说明 |
|------|--------|--------|--------|------|
| 营养进度 | 白色 | - | 灰色 | 中性，突出进度条 |
| 重要提醒 | 红色浅背景 | 红色边框 | 红色文字 | 警示性强 |
| 健康提示 | 绿色浅背景 | 绿色边框 | 绿色文字 | 积极正面 |
| 食物推荐 | 白色 | - | 灰色 | 清晰易读 |
| Debug 信息 | 白色/渐变 | - | 灰色/白色 | 低调不抢眼 |

### 图标使用

- 📊 营养进度: `ChartBarIcon`
- ⚠️ 重要提醒: `ExclamationTriangleIcon`
- 💡 健康提示: `LightBulbIcon`
- 🍽️ 食物推荐: 食物 Emoji
- 👤 个人信息: `HeartIcon`
- 🔥 代谢信息: `FireIcon`
- 🧪 科学依据: `BeakerIcon`

## 📊 用户体验改进

### 修改前

```
用户打开页面 → 看到 BMR、TDEE → 不理解 → 继续滚动
→ 看到进度条 → 继续滚动 → 看到提醒 → 继续滚动
→ 看到推荐 → 终于找到想要的信息
```

**问题**: 
- ❌ 需要滚动多次才能看到关键信息
- ❌ 首屏信息对普通用户不友好
- ❌ 信息层次混乱

### 修改后

```
用户打开页面 → 立即看到进度条 → 看到提醒和建议
→ 看到食物推荐 → 完成主要任务
→ (可选) 点击"显示详细数据" → 查看技术细节
```

**改进**:
- ✅ 首屏即可看到关键信息
- ✅ 信息层次清晰
- ✅ 技术细节按需查看

## 📈 预期效果

### 用户满意度

- **普通用户**: 快速获取关键信息，不被技术细节干扰
- **专业用户**: 可以查看详细的代谢和健康数据
- **开发者**: Debug 模式方便调试

### 页面性能

- **首屏加载**: 减少首屏内容，加载更快
- **交互流畅**: 折叠/展开动画流畅
- **移动端适配**: 小屏幕上信息层次更清晰

## 🔄 后续优化

### 1. 用户偏好记忆

```typescript
// 记住用户的 Debug 模式选择
useEffect(() => {
  const savedDebugMode = localStorage.getItem('diet_debug_mode')
  if (savedDebugMode) {
    setShowDebugInfo(savedDebugMode === 'true')
  }
}, [])

useEffect(() => {
  localStorage.setItem('diet_debug_mode', showDebugInfo.toString())
}, [showDebugInfo])
```

### 2. 添加快捷入口

```tsx
{/* 快捷操作 */}
<div className="flex gap-4 mb-6">
  <button onClick={() => scrollTo('#nutrition')}>
    查看进度
  </button>
  <button onClick={() => scrollTo('#warnings')}>
    查看提醒
  </button>
  <button onClick={() => scrollTo('#recommendations')}>
    查看推荐
  </button>
</div>
```

### 3. 添加数据导出

```tsx
<button onClick={exportData}>
  导出饮食报告
</button>
```

## ✅ 完成清单

- ✅ 添加 Debug 模式开关
- ✅ 重新组织内容顺序
- ✅ 将技术细节移到 Debug 模式
- ✅ 优化视觉层次
- ✅ 提交代码并部署
- ⏳ 小程序端实现（待完成）
- ⏳ 用户偏好记忆（待完成）

## 📄 相关文件

- `frontend/src/app/diet-recommendation/page.tsx` - Web 端页面
- `packages/mini-program/src/pages/diet-recommendation/index.tsx` - 小程序页面（待更新）

---

**更新完成时间**: 2026-01-23 10:40  
**Web 端状态**: ✅ 已部署  
**小程序端状态**: ⏳ 待更新
