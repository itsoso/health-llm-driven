# 小程序饮食推荐页面修复和优化

**更新时间**: 2026-01-23  
**问题**: 导入路径错误 + 布局需要优化

## 🐛 问题 1: 导入路径错误

### 错误信息

```
resolve '../../utils/request' in '/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/src/pages/diet-recommendation'
  /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/src/utils/request doesn't exist
```

### 问题原因

```typescript
// ❌ 错误的导入路径
import { request } from '../../utils/request'
```

`request` 工具实际位置：`packages/mini-program/src/services/request.ts`

### 解决方案

```typescript
// ✅ 正确的导入路径
import { request } from '../../services/request'
```

## 🎨 问题 2: 布局优化

### 修改前（旧布局）

```
1. 个人信息
2. 代谢信息
3. 营养进度
4. 健康状态
5. 警告
6. 提示
7. 食物推荐
8. 科学见解
```

**问题**:
- ❌ 技术细节（个人信息、代谢信息、健康状态）占据首屏
- ❌ 用户最关心的内容（进度、提醒、推荐）在下方
- ❌ 需要滚动多次才能看到关键信息

### 修改后（新布局）

```
[显示详细数据] 按钮

1. 营养进度 ⭐
2. 重要提醒 ⭐
3. 健康提示 ⭐
4. 食物推荐 ⭐

--- Debug 模式（点击后展开）---

5. 个人信息 (Debug)
6. 代谢信息 (Debug)
7. 健康状态 (Debug)

--- 始终可见 ---

8. 科学见解（可展开）
```

**改进**:
- ✅ 关键信息在首屏
- ✅ 技术细节可选显示
- ✅ 用户体验更好

## 🔧 实现细节

### 1. 添加 Debug 模式开关

```tsx
// packages/mini-program/src/pages/diet-recommendation/index.tsx

const [showDebugInfo, setShowDebugInfo] = useState(false)

// 页面顶部添加开关
<View className="debug-toggle" onClick={() => setShowDebugInfo(!showDebugInfo)}>
  <Text className="toggle-text">
    {showDebugInfo ? '隐藏详细数据' : '显示详细数据'}
  </Text>
</View>
```

### 2. 重新组织内容顺序

```tsx
<ScrollView className="diet-recommendation-page" scrollY>
  {/* Debug 开关 */}
  <View className="debug-toggle">...</View>

  {/* 第一优先级：营养进度 */}
  <View className="card progress-card">...</View>

  {/* 第二优先级：重要提醒 */}
  {recommendation.warnings && recommendation.warnings.length > 0 && (
    <View className="card warnings-card">...</View>
  )}

  {/* 第三优先级：健康提示 */}
  {recommendation.tips && recommendation.tips.length > 0 && (
    <View className="card tips-card">...</View>
  )}

  {/* 第四优先级：食物推荐 */}
  {recommendation.food_recommendations && recommendation.food_recommendations.length > 0 && (
    <View className="card food-recommendations-card">...</View>
  )}

  {/* Debug 模式：详细数据 */}
  {showDebugInfo && (
    <>
      <View className="card user-info-card">...</View>
      <View className="card metabolism-card">...</View>
      <View className="card health-status-card">...</View>
    </>
  )}

  {/* 科学见解（始终可见） */}
  {recommendation.scientific_insights?.available && (
    <View className="card scientific-card">...</View>
  )}
</ScrollView>
```

### 3. 样式建议

需要在 `index.scss` 中添加 Debug 开关的样式：

```scss
// packages/mini-program/src/pages/diet-recommendation/index.scss

.debug-toggle {
  margin: 20rpx 30rpx;
  padding: 20rpx;
  background: #f5f5f5;
  border-radius: 10rpx;
  text-align: center;
  
  .toggle-text {
    color: #666;
    font-size: 28rpx;
  }
  
  &:active {
    background: #e5e5e5;
  }
}
```

## 📊 用户体验改进

### 修改前

```
用户打开小程序 → 看到个人信息 → 不理解 → 继续滚动
→ 看到代谢信息 → 不理解 → 继续滚动
→ 看到进度条 → 继续滚动 → 看到提醒 → 继续滚动
→ 看到推荐 → 终于找到想要的信息
```

**问题**: 
- ❌ 需要滚动多次
- ❌ 首屏信息对普通用户不友好
- ❌ 关键信息被埋没

### 修改后

```
用户打开小程序 → 立即看到进度条 → 看到提醒和建议
→ 看到食物推荐 → 完成主要任务
→ (可选) 点击"显示详细数据" → 查看技术细节
```

**改进**:
- ✅ 首屏即可看到关键信息
- ✅ 信息层次清晰
- ✅ 技术细节按需查看

## 🎯 与 Web 端保持一致

### 布局顺序

| 优先级 | Web 端 | 小程序端 | 状态 |
|--------|--------|---------|------|
| 1 | 今日营养进度 | 今日营养进度 | ✅ 一致 |
| 2 | 重要提醒 + 健康提示 | 重要提醒 + 健康提示 | ✅ 一致 |
| 3 | 食物推荐 | 食物推荐 | ✅ 一致 |
| Debug | 个人信息、代谢、健康状态 | 个人信息、代谢、健康状态 | ✅ 一致 |
| 可选 | 科学依据 | 科学见解 | ✅ 一致 |

### Debug 模式

| 功能 | Web 端 | 小程序端 | 状态 |
|------|--------|---------|------|
| 开关位置 | 页面标题右侧 | 页面顶部 | ✅ 实现 |
| 默认状态 | 隐藏 | 隐藏 | ✅ 一致 |
| 展开方式 | 点击按钮 | 点击按钮 | ✅ 一致 |
| 包含内容 | 个人信息、代谢、健康状态 | 个人信息、代谢、健康状态 | ✅ 一致 |

## ✅ 修复清单

- ✅ 修复导入路径：`../../utils/request` → `../../services/request`
- ✅ 添加 Debug 模式开关
- ✅ 重新组织内容顺序
- ✅ 将技术细节移到 Debug 模式
- ✅ 与 Web 端布局保持一致
- ✅ 提交代码
- ⏳ 添加 Debug 开关样式（需要在 index.scss 中添加）
- ⏳ 测试小程序功能

## 📝 后续工作

### 1. 添加样式

在 `packages/mini-program/src/pages/diet-recommendation/index.scss` 中添加：

```scss
.debug-toggle {
  margin: 20rpx 30rpx;
  padding: 20rpx;
  background: #f5f5f5;
  border-radius: 10rpx;
  text-align: center;
  
  .toggle-text {
    color: #666;
    font-size: 28rpx;
  }
  
  &:active {
    background: #e5e5e5;
  }
}
```

### 2. 测试功能

- [ ] 测试页面加载
- [ ] 测试 Debug 模式开关
- [ ] 测试所有卡片显示
- [ ] 测试科学见解展开/收起
- [ ] 测试在不同屏幕尺寸下的显示

### 3. 优化细节

- [ ] 添加加载动画
- [ ] 添加错误提示优化
- [ ] 添加空状态提示
- [ ] 优化卡片间距和样式

## 📄 相关文件

- `packages/mini-program/src/pages/diet-recommendation/index.tsx` - 页面逻辑
- `packages/mini-program/src/pages/diet-recommendation/index.scss` - 页面样式
- `packages/mini-program/src/services/request.ts` - 请求工具
- `frontend/src/app/diet-recommendation/page.tsx` - Web 端参考

## 🔗 相关文档

- `DIET_RECOMMENDATION_LAYOUT_REDESIGN.md` - Web 端布局重新设计
- `MINI_PROGRAM_QUICK_START.md` - 小程序快速开始指南

---

**修复完成时间**: 2026-01-23 10:50  
**状态**: ✅ 代码已提交  
**测试状态**: ⏳ 待测试
