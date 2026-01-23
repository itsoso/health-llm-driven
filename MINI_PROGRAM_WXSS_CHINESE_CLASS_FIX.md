# 小程序 WXSS 中文类名编译错误修复

**日期**: 2026-01-23  
**状态**: ✅ 已修复

## 🐛 问题描述

小程序补剂页面编译时出现 WXSS 文件错误：

```
[ WXSS 文件编译错误] 
./pages/supplements/index.wxss(1:13333): unexpected `�` at pos 13333
```

## 🔍 问题分析

### 1. 错误定位

通过 hexdump 检查编译后的 wxss 文件：

```bash
dd if=dist/pages/supplements/index.wxss bs=1 skip=13320 count=30 | hexdump -C
```

输出：
```
00000000  72 64 2e 70 72 69 6f 72  69 74 79 2d e9 ab 98 7b  |rd.priority-...{|
00000010  62 61 63 6b 67 72 6f 75  6e 64 3a 72 67 62        |background:rgb|
```

发现问题：`e9 ab 98` 是中文字符"高"的 UTF-8 编码。

### 2. 根本原因

**微信小程序的 WXSS 编译器不支持 CSS 类名中的中文字符**

原代码中使用了中文类名：
```scss
.rec-card {
  &.priority-高 {  // ❌ 中文类名
    border-color: rgba(#EF4444, 0.5);
  }
  
  &.priority-中 {  // ❌ 中文类名
    border-color: rgba(#F59E0B, 0.5);
  }
}

.rec-priority {
  &.高 {  // ❌ 中文类名
    background: rgba(#EF4444, 0.2);
  }
  
  &.中 {  // ❌ 中文类名
    background: rgba(#F59E0B, 0.2);
  }
  
  &.低 {  // ❌ 中文类名
    background: rgba($text-secondary, 0.2);
  }
}
```

虽然 SCSS 源文件可以包含中文，但编译后的 WXSS 文件中的类名不能包含中文字符。

## ✅ 解决方案

### 1. 修改 SCSS 文件

将中文类名改为英文：

```scss
// packages/mini-program/src/pages/supplements/index.scss

.rec-card {
  &.priority-high {  // ✅ 英文类名
    border-color: rgba(#EF4444, 0.5);
    background: rgba(#EF4444, 0.05);
  }
  
  &.priority-medium {  // ✅ 英文类名
    border-color: rgba(#F59E0B, 0.5);
    background: rgba(#F59E0B, 0.05);
  }
}

.rec-priority {
  &.high {  // ✅ 英文类名
    background: rgba(#EF4444, 0.2);
    color: #EF4444;
  }
  
  &.medium {  // ✅ 英文类名
    background: rgba(#F59E0B, 0.2);
    color: #F59E0B;
  }
  
  &.low {  // ✅ 英文类名
    background: rgba($text-secondary, 0.2);
    color: $text-secondary;
  }
}
```

### 2. 添加转换函数

在 TSX 文件中添加中文到英文的转换函数：

```typescript
// packages/mini-program/src/pages/supplements/index.tsx

// 转换中文优先级为英文类名
const getPriorityClass = (priority: string): string => {
  const map: Record<string, string> = {
    '高': 'high',
    '中': 'medium',
    '低': 'low'
  };
  return map[priority] || priority;
};
```

### 3. 更新 JSX 中的类名引用

```tsx
{recommendation.recommendations.map((rec, idx) => (
  <View 
    key={idx} 
    className={`rec-card priority-${getPriorityClass(rec.priority)}`}  // ✅ 使用转换函数
  >
    <View className="rec-header">
      <Text className="rec-icon">{rec.icon}</Text>
      <Text className="rec-name">{rec.name}</Text>
      <Text className={`rec-priority ${getPriorityClass(rec.priority)}`}>  // ✅ 使用转换函数
        {rec.priority}优先  {/* 显示文本仍为中文 */}
      </Text>
    </View>
    {/* ... */}
  </View>
))}
```

## 📊 修改对比

### 修改前

| 位置 | 类名 | 问题 |
|------|------|------|
| SCSS | `.priority-高` | ❌ 中文类名 |
| SCSS | `.priority-中` | ❌ 中文类名 |
| SCSS | `.高` | ❌ 中文类名 |
| SCSS | `.中` | ❌ 中文类名 |
| SCSS | `.低` | ❌ 中文类名 |
| TSX | `priority-${rec.priority}` | ❌ 直接使用中文 |
| TSX | `${rec.priority}` | ❌ 直接使用中文 |

### 修改后

| 位置 | 类名 | 状态 |
|------|------|------|
| SCSS | `.priority-high` | ✅ 英文类名 |
| SCSS | `.priority-medium` | ✅ 英文类名 |
| SCSS | `.high` | ✅ 英文类名 |
| SCSS | `.medium` | ✅ 英文类名 |
| SCSS | `.low` | ✅ 英文类名 |
| TSX | `priority-${getPriorityClass(rec.priority)}` | ✅ 转换为英文 |
| TSX | `${getPriorityClass(rec.priority)}` | ✅ 转换为英文 |
| 显示 | `{rec.priority}优先` | ✅ 显示仍为中文 |

## 🔧 验证步骤

### 1. 清理并重新编译

```bash
cd packages/mini-program
rm -rf dist
npm run build:weapp
```

### 2. 检查编译结果

```bash
# 检查类名是否改为英文
grep -o "priority-[^{]*{" dist/pages/supplements/index.wxss

# 输出应该是：
# priority-high{
# priority-medium{
```

### 3. 检查第 13333 字符位置

```bash
dd if=dist/pages/supplements/index.wxss bs=1 skip=13320 count=50 2>/dev/null

# 输出应该是：
# rd.priority-high{background:rgba(239,68,68,.05);bo
```

✅ 不再包含中文字符！

## 📝 经验总结

### 1. 微信小程序 WXSS 限制

**不支持的内容**:
- ❌ CSS 类名中的中文字符
- ❌ CSS 类名中的特殊 Unicode 字符
- ❌ CSS 类名中的 emoji

**支持的内容**:
- ✅ 英文字母（a-z, A-Z）
- ✅ 数字（0-9）
- ✅ 连字符（-）
- ✅ 下划线（_）
- ✅ CSS 属性值中的中文（如 `content: "中文"`）
- ✅ 注释中的中文

### 2. 最佳实践

**CSS 类名命名规范**:
```scss
// ✅ 推荐：使用英文
.priority-high { }
.status-active { }
.level-advanced { }

// ❌ 避免：使用中文
.priority-高 { }
.status-激活 { }
.level-高级 { }
```

**数据转换策略**:
```typescript
// 后端返回中文 → 前端转换为英文类名
const getClassName = (chineseValue: string): string => {
  const map: Record<string, string> = {
    '高': 'high',
    '中': 'medium',
    '低': 'low',
    '激活': 'active',
    '禁用': 'disabled'
  };
  return map[chineseValue] || chineseValue;
};

// 使用
<View className={`priority-${getClassName(priority)}`}>
  {priority}  {/* 显示仍为中文 */}
</View>
```

### 3. 调试技巧

**如何定位中文类名问题**:

1. **查看编译错误信息**
   ```
   unexpected `�` at pos 13333
   ```
   记录错误位置（13333）

2. **使用 hexdump 查看二进制内容**
   ```bash
   dd if=dist/xxx.wxss bs=1 skip=13320 count=50 | hexdump -C
   ```
   
3. **查找 UTF-8 中文编码**
   - 中文字符通常是 3 字节 UTF-8 编码
   - 范围：`e4-e9` 开头
   - 例如："高" = `e9 ab 98`

4. **搜索源文件中的中文类名**
   ```bash
   grep -n "class.*[\u4e00-\u9fa5]" src/**/*.scss
   ```

## 🎯 影响范围

### 修改的文件

1. `packages/mini-program/src/pages/supplements/index.scss`
   - 5 处中文类名改为英文

2. `packages/mini-program/src/pages/supplements/index.tsx`
   - 添加 `getPriorityClass` 转换函数
   - 2 处类名引用使用转换函数

### 功能影响

- ✅ 样式显示：完全一致
- ✅ 用户体验：无变化
- ✅ 显示文本：仍为中文
- ✅ 编译：成功，无错误

## 🚀 部署状态

- ✅ 代码已修复
- ✅ 编译成功
- ✅ 已提交到 Git
- ✅ 可以在微信开发者工具中正常使用

## 📚 相关文档

- [微信小程序 WXSS 文档](https://developers.weixin.qq.com/miniprogram/dev/framework/view/wxss.html)
- [CSS 类名命名规范](https://www.w3.org/TR/CSS21/syndata.html#characters)

---

**修复完成！** 🎉

现在小程序可以正常编译，不再出现 WXSS 中文类名错误。
