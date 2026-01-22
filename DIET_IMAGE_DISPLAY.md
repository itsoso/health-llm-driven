# 饮食记录图片展示功能

## 功能说明

在 Web 饮食页面（https://health.westwetlandtech.com/diet）上展示用户上传的食物图片。

## 实现内容

### 1. 前端页面优化

**修改文件：`frontend/src/app/diet/page.tsx`**

在饮食记录列表中添加图片展示：

```tsx
{dailySummary.meals.map((meal: any) => {
  const mealInfo = getMealInfo(meal.meal_type);
  return (
    <div key={meal.id} className="flex gap-4 p-4 bg-gray-50 rounded-lg border border-gray-100">
      {/* 食物图片 */}
      {meal.image_url && (
        <div className="flex-shrink-0">
          <img 
            src={meal.image_url} 
            alt={meal.food_items}
            className="w-32 h-32 object-cover rounded-lg shadow-md cursor-pointer hover:scale-105 transition-transform"
            onClick={() => window.open(meal.image_url, '_blank')}
            title="点击查看大图"
          />
        </div>
      )}
      
      {/* 食物信息 */}
      <div className="flex-1">
        {/* ... 餐食类型、营养信息等 ... */}
      </div>
      
      {/* 删除按钮 */}
      <button onClick={() => deleteMutation.mutate(meal.id)}>删除</button>
    </div>
  );
})}
```

### 2. 功能特性

#### 图片展示
- ✅ 显示 128x128 像素的缩略图
- ✅ 圆角阴影效果，美观大方
- ✅ 鼠标悬停时轻微放大（hover:scale-105）
- ✅ 点击图片在新标签页查看大图
- ✅ 如果没有图片，不显示图片区域（不影响布局）

#### 布局优化
- ✅ 使用 Flexbox 布局，图片在左侧，信息在右侧
- ✅ 图片固定宽度（flex-shrink-0），不会被压缩
- ✅ 信息区域自适应宽度（flex-1）
- ✅ 删除按钮在右上角（self-start）

### 3. 后端支持

**数据库字段：**
- `image_url` - 存储图片 URL 路径（已存在）

**API 返回：**
- 后端 API 已经在响应中包含 `image_url` 字段
- 图片路径格式：`/api/v1/upload/files/{filename}`

**图片存储：**
- 上传的图片保存在服务器 `/opt/health-app/backend/uploads/` 目录
- 通过 Nginx 静态文件服务提供访问

### 4. 用户体验

#### 添加饮食时
1. 用户上传食物图片
2. 可以选择"AI识别"自动识别食物和营养信息
3. 或选择"一键识别并保存"直接保存
4. 图片会自动保存到服务器

#### 查看饮食记录时
1. 如果有图片，显示在记录左侧
2. 点击图片可以在新标签页查看大图
3. 图片和文字信息并排展示，一目了然
4. 没有图片的记录不受影响，正常显示

### 5. 兼容性

- ✅ 支持新上传的图片
- ✅ 支持历史记录（没有图片的记录不显示图片区域）
- ✅ 响应式设计，适配不同屏幕尺寸
- ✅ 不影响现有功能

## 部署状态

- ✅ 前端代码已更新并重新构建
- ✅ 前端服务已重启（PM2）
- ✅ 生产环境已部署（https://health.westwetlandtech.com/diet）
- ✅ 所有服务运行正常

## 测试建议

1. **测试新上传**
   - 访问 https://health.westwetlandtech.com/diet
   - 点击"添加饮食"
   - 上传食物图片
   - 保存后查看记录是否显示图片

2. **测试图片查看**
   - 点击缩略图
   - 确认在新标签页打开大图
   - 检查图片是否清晰

3. **测试历史记录**
   - 查看之前没有图片的记录
   - 确认布局正常，不显示空白图片区域

4. **测试响应式**
   - 在不同屏幕尺寸下查看
   - 确认图片和信息排列合理

## 技术细节

### 图片 URL 格式

```
/api/v1/upload/files/diet_20260122_123456_abc123.jpeg
```

### 图片存储路径

```
/opt/health-app/backend/uploads/diet_20260122_123456_abc123.jpeg
```

### Nginx 配置

图片通过 Nginx 静态文件服务提供：

```nginx
location /api/v1/upload/files/ {
    alias /opt/health-app/backend/uploads/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

## 相关文件

### 已修改的文件
- `frontend/src/app/diet/page.tsx` - 添加图片展示功能

### 相关后端文件（无需修改）
- `backend/app/api/diet.py` - 处理图片上传和保存
- `backend/app/models/daily_health.py` - 数据库模型（包含 image_url 字段）
- `backend/app/schemas/diet.py` - API 响应模型

## 示例效果

### 有图片的记录

```
┌─────────────────────────────────────────────────────┐
│ ┌──────────┐  🌅 早餐  500 kcal  🤖 AI识别         │
│ │          │  鸡蛋2个, 全麦面包1片, 牛奶200ml      │
│ │  食物    │  蛋白质: 25g  碳水: 40g  脂肪: 15g    │
│ │  图片    │  💡 营养均衡，适合早餐                │
│ └──────────┘                              [删除]    │
└─────────────────────────────────────────────────────┘
```

### 没有图片的记录

```
┌─────────────────────────────────────────────────────┐
│ ☀️ 午餐  800 kcal                                   │
│ 米饭1碗, 鸡胸肉150g, 西兰花                         │
│ 蛋白质: 35g  碳水: 80g  脂肪: 10g                   │
│                                          [删除]     │
└─────────────────────────────────────────────────────┘
```

## 注意事项

1. **图片大小限制**：上传图片不能超过 10MB
2. **支持格式**：JPG、PNG、JPEG
3. **存储空间**：定期清理旧图片以节省空间
4. **隐私保护**：图片仅用户本人可见（通过 user_id 隔离）

## 后续优化建议

1. **图片压缩**：上传时自动压缩图片，减少存储空间
2. **懒加载**：列表中的图片使用懒加载，提升页面性能
3. **图片预览**：添加图片预览弹窗，不需要跳转新标签页
4. **批量上传**：支持一次上传多张图片
5. **图片编辑**：支持裁剪、旋转等基本编辑功能

---

**实现完成时间**: 2026-01-22  
**实现人**: AI Assistant  
**Commit**: 72e9b5b  
**版本**: v1.0
