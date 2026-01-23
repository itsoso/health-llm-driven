# Web 端压力指数展示优化

**修复时间**: 2026-01-23  
**修复内容**: 优化压力指数的表情和状态展示

## 🐛 问题描述

Web 端 (https://health.westwetlandtech.com/overview) 的压力指数展示问题：
- ❌ 所有压力值都显示苦脸表情 😰
- ❌ 没有根据压力值显示不同的状态

## 📊 小程序的正确逻辑

小程序中的压力展示逻辑（参考 `packages/mini-program/src/pages/index/index.tsx`）：

```typescript
// 表情显示
const getStressEmoji = (stress: number | null | undefined) => {
  if (!stress) return '😐';
  if (stress <= 25) return '🙂';  // 放松
  if (stress <= 50) return '😐';  // 正常
  if (stress <= 75) return '😟';  // 中等
  return '😰';                     // 偏高
};

// 状态文字和颜色
export function getStressLevel(stress: number | null | undefined): { level: string; color: string } {
  if (stress === null || stress === undefined) {
    return { level: '未知', color: '#9CA3AF' };
  }
  if (stress <= 25) return { level: '放松', color: '#10B981' };  // 绿色
  if (stress <= 50) return { level: '正常', color: '#3B82F6' };  // 蓝色
  if (stress <= 75) return { level: '中等', color: '#F59E0B' };  // 黄色
  return { level: '偏高', color: '#EF4444' };                    // 红色
}
```

## ✅ 修复方案

### 修改前

```tsx
{/* 压力 */}
<MetricCard icon="😰" title="压力">
  <div className="text-3xl font-bold text-gray-800">
    {record?.stress_level || '--'}
  </div>
</MetricCard>
```

**问题**: 固定显示 😰 表情，无论压力值多少

### 修改后

```tsx
{/* 压力 */}
<MetricCard 
  icon={(() => {
    const stress = record?.stress_level;
    if (!stress) return '😐';
    if (stress <= 25) return '😊';  // 放松
    if (stress <= 50) return '😐';  // 正常
    if (stress <= 75) return '😟';  // 中等
    return '😰';                     // 偏高
  })()} 
  title="压力"
>
  <div className="text-3xl font-bold text-gray-800">
    {record?.stress_level || '--'}
  </div>
  {record?.stress_level && (
    <div className={`text-sm font-medium mt-1 ${
      record.stress_level <= 25 ? 'text-green-600' :
      record.stress_level <= 50 ? 'text-blue-600' :
      record.stress_level <= 75 ? 'text-yellow-600' :
      'text-red-600'
    }`}>
      {record.stress_level <= 25 ? '放松' :
       record.stress_level <= 50 ? '正常' :
       record.stress_level <= 75 ? '中等' :
       '偏高'}
    </div>
  )}
</MetricCard>
```

## 📈 压力等级划分

| 压力值 | 表情 | 状态 | 颜色 | 说明 |
|--------|------|------|------|------|
| 0-25 | 😊 | 放松 | 🟢 绿色 | 状态良好，继续保持 |
| 26-50 | 😐 | 正常 | 🔵 蓝色 | 压力适中，注意休息 |
| 51-75 | 😟 | 中等 | 🟡 黄色 | 压力偏高，建议放松 |
| 76-100 | 😰 | 偏高 | 🔴 红色 | 压力过高，需要休息 |

## 🎯 效果对比

### 修复前
```
压力指数: 20
表情: 😰 (固定)
状态: 无
```

### 修复后
```
压力指数: 20
表情: 😊 (根据数值)
状态: 放松 (绿色)
```

## 📝 技术细节

### 1. 动态表情计算

使用立即执行函数表达式 (IIFE) 计算表情：

```tsx
icon={(() => {
  const stress = record?.stress_level;
  if (!stress) return '😐';
  if (stress <= 25) return '😊';
  if (stress <= 50) return '😐';
  if (stress <= 75) return '😟';
  return '😰';
})()}
```

### 2. 状态文字和颜色

使用条件渲染和 Tailwind CSS 类：

```tsx
{record?.stress_level && (
  <div className={`text-sm font-medium mt-1 ${
    record.stress_level <= 25 ? 'text-green-600' :
    record.stress_level <= 50 ? 'text-blue-600' :
    record.stress_level <= 75 ? 'text-yellow-600' :
    'text-red-600'
  }`}>
    {/* 状态文字 */}
  </div>
)}
```

### 3. Tailwind CSS 颜色

- `text-green-600`: #10B981 (放松)
- `text-blue-600`: #3B82F6 (正常)
- `text-yellow-600`: #F59E0B (中等)
- `text-red-600`: #EF4444 (偏高)

## 🚀 部署记录

### 1. 代码提交

```bash
git add frontend/src/app/overview/page.tsx
git commit -m "fix: 优化 Web 端压力指数展示，根据数值显示不同表情和状态"
git push
```

### 2. 服务器部署

```bash
cd /opt/health-app/frontend
git pull
npm run build
pm2 restart health-frontend
```

### 3. 部署结果

```
✓ Compiled successfully
✓ Generating static pages (34/34)
[PM2] [health-frontend] ✓
```

## ✅ 验证步骤

1. 访问：https://health.westwetlandtech.com/overview
2. 查看压力指数卡片
3. 验证以下情况：
   - ✅ 压力值 0-25: 显示 😊 和绿色"放松"
   - ✅ 压力值 26-50: 显示 😐 和蓝色"正常"
   - ✅ 压力值 51-75: 显示 😟 和黄色"中等"
   - ✅ 压力值 76-100: 显示 😰 和红色"偏高"
   - ✅ 无数据: 显示 😐 和 "--"

## 📚 相关文件

- **Web 端**: `frontend/src/app/overview/page.tsx`
- **小程序**: `packages/mini-program/src/pages/index/index.tsx`
- **类型定义**: `packages/mini-program/src/types/index.ts`

## 💡 设计原则

### 1. 用户友好

- 使用直观的表情符号
- 颜色与状态匹配（绿色=好，红色=差）
- 提供清晰的状态文字

### 2. 一致性

- Web 端和小程序逻辑一致
- 表情和颜色标准统一
- 压力等级划分相同

### 3. 可读性

- 大字号显示数值
- 小字号显示状态
- 颜色区分明显

## 🎨 UI 示例

### 低压力 (20)
```
😊 压力
   20
   放松 (绿色)
```

### 正常压力 (40)
```
😐 压力
   40
   正常 (蓝色)
```

### 中等压力 (60)
```
😟 压力
   60
   中等 (黄色)
```

### 高压力 (85)
```
😰 压力
   85
   偏高 (红色)
```

## 🔄 未来优化

### 1. 添加趋势图

显示压力值的历史变化趋势

### 2. 添加建议

根据压力等级提供个性化建议：
- 放松: "状态良好，继续保持"
- 正常: "压力适中，注意休息"
- 中等: "压力偏高，建议放松"
- 偏高: "压力过高，需要休息"

### 3. 添加动画

表情切换时添加平滑过渡动画

## ✅ 总结

### 修复内容

- ✅ 根据压力值显示不同表情（😊 😐 😟 😰）
- ✅ 添加状态文字（放松、正常、中等、偏高）
- ✅ 添加颜色区分（绿、蓝、黄、红）
- ✅ 与小程序逻辑保持一致

### 影响范围

- 页面: https://health.westwetlandtech.com/overview
- 组件: 压力指数卡片
- 用户: 所有 Web 端用户

### 用户体验提升

- ✅ 更直观的视觉反馈
- ✅ 更清晰的状态说明
- ✅ 更友好的界面设计

---

**修复完成！** 🎉
