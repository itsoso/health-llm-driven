# 小程序补剂推荐显示修复

## 问题描述

用户反馈补剂推荐列表为空，虽然看到了"推荐补剂"的标题，但下方没有内容。

## 原因分析

1. **ScrollView 布局问题**: Taro/微信小程序的 `ScrollView` 在使用 Flex 布局时，需要显式开启 `enableFlex` 属性，否则内部的 Flex 布局可能失效或高度计算错误。
2. **底部安全区域**: 推荐弹窗底部可能被设备的 Home Indicator (底部黑条) 遮挡，导致最后的内容不可见。
3. **渲染逻辑**: 之前的逻辑是如果列表为空则隐藏整个区块，导致无法区分是"数据为空"还是"渲染失败"。

## 解决方案

### 1. 开启 Flex 布局支持

在 `packages/mini-program/src/pages/supplements/index.tsx` 中：

```tsx
<ScrollView 
  scrollY 
  className="recommendation-content" 
  enhanced 
  showScrollbar={false}
  enableFlex={true}  // ✅ 新增：开启 Flex 布局支持
>
```

### 2. 增加底部安全区域

在 `packages/mini-program/src/pages/supplements/index.scss` 中：

```scss
.recommendation-content {
  flex: 1;
  padding: 32rpx;
  // ✅ 新增：底部增加 padding，适配安全区域
  padding-bottom: calc(32rpx + env(safe-area-inset-bottom));
}
```

### 3. 优化渲染逻辑

修改列表渲染逻辑，即使为空也显示提示，便于排查：

```tsx
{recommendation.recommendations.length > 0 ? (
  recommendation.recommendations.map(...)
) : (
  <View className="rec-card">
    <Text className="rec-reason">暂无特定推荐，请保持均衡饮食。</Text>
  </View>
)}
```

## 验证方法

1. 重新编译小程序。
2. 进入补剂页面，点击"益家知研 AI 推荐"。
3. 滚动到底部，确认能看到推荐列表。

## 相关修改

- `packages/mini-program/src/pages/supplements/index.tsx`
- `packages/mini-program/src/pages/supplements/index.scss`

---

**注意**: 后端逻辑已确保至少返回 3 条推荐（包含基础推荐），因此列表不应为空。此次修复主要解决前端显示问题。
