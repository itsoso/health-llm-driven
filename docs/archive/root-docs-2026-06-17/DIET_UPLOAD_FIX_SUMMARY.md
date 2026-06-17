# 饮食照片上传功能优化总结

## 🎯 优化目标

解决小程序上传食物照片时可能出现的各种错误，提高上传成功率和用户体验。

---

## ✅ 完成的优化

### 1. 图片大小检查

**问题**: 图片太大导致上传失败或超时

**解决方案**:
```typescript
// 在选择图片后检查文件大小
Taro.getFileInfo({
  filePath: tempFilePath,
  success: (fileInfo) => {
    const sizeMB = fileInfo.size / (1024 * 1024);
    console.log('[饮食上传] 图片大小:', sizeMB.toFixed(2), 'MB');
    
    if (fileInfo.size > 5 * 1024 * 1024) {  // 5MB 限制
      Taro.showToast({ 
        title: '图片太大，请选择较小的图片', 
        icon: 'none',
        duration: 3000
      });
      return;
    }
    
    setImagePreview(tempFilePath);
  }
});
```

**效果**: 
- ✅ 防止上传超大图片
- ✅ 提前提示用户
- ✅ 节省网络流量

---

### 2. 详细日志记录

**问题**: 上传失败时不知道具体原因

**解决方案**:
```typescript
console.log('[饮食上传] ===== 开始上传 =====');
console.log('[饮食上传] 图片路径:', imagePreview);
console.log('[饮食上传] 日期:', selectedDate);
console.log('[饮食上传] 餐食类型:', mealType);
console.log('[饮食上传] 开始读取图片...');
console.log('[饮食上传] 读取成功，Base64 长度:', base64.length);
console.log('[饮食上传] 发送请求到服务器...');
console.log('[饮食上传] 上传成功');
console.log('[饮食上传] ===== 上传流程结束 =====');
```

**效果**:
- ✅ 可以追踪上传的每个步骤
- ✅ 快速定位失败原因
- ✅ 便于调试和排查问题

---

### 3. Base64 读取错误处理

**问题**: 文件读取失败时没有明确提示

**解决方案**:
```typescript
let base64: string;
try {
  console.log('[饮食上传] 开始读取图片...');
  base64 = fs.readFileSync(imagePreview, 'base64') as string;
  console.log('[饮食上传] 读取成功，Base64 长度:', base64.length);
  
  // 检查 Base64 是否有效
  if (!base64 || base64.length < 100) {
    throw new Error('图片数据无效');
  }
} catch (readError: any) {
  console.error('[饮食上传] 读取图片失败:', readError);
  throw new Error(`读取图片失败: ${readError.message || '未知错误'}`);
}
```

**效果**:
- ✅ 捕获文件读取错误
- ✅ 验证 Base64 数据有效性
- ✅ 提供明确的错误信息

---

### 4. 增加请求超时时间

**问题**: AI 识别需要时间，默认超时时间太短

**解决方案**:
```typescript
// services/request.ts
const response = await Taro.request<T>({
  url: finalUrl,
  method,
  data,
  header: {
    ...header,
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
  },
  timeout: 60000,  // 60秒超时（AI识别需要时间）
});
```

**效果**:
- ✅ 给 AI 识别足够的时间
- ✅ 减少超时错误
- ✅ 提高上传成功率

---

### 5. 改进错误提示

**问题**: 错误提示不够友好和明确

**解决方案**:
```typescript
catch (error: any) {
  console.error('[饮食上传] 保存失败，错误详情:', error);
  console.error('[饮食上传] 错误类型:', typeof error);
  console.error('[饮食上传] 错误消息:', error.message);
  console.error('[饮食上传] 错误堆栈:', error.stack);
  
  let errorMsg = '保存失败，请重试';
  if (error.message) {
    errorMsg = error.message;
  } else if (typeof error === 'string') {
    errorMsg = error;
  }
  
  Taro.showToast({ 
    title: errorMsg, 
    icon: 'none',
    duration: 3000
  });
}
```

**效果**:
- ✅ 显示具体的错误原因
- ✅ 延长错误提示显示时间（3秒）
- ✅ 记录详细的错误日志

---

### 6. 选择图片错误处理

**问题**: 选择图片失败时没有提示

**解决方案**:
```typescript
fail: (err) => {
  console.error('[饮食上传] 选择图片失败:', err);
  Taro.showToast({ 
    title: `选择图片失败: ${err.errMsg || '未知错误'}`, 
    icon: 'none',
    duration: 3000
  });
}
```

**效果**:
- ✅ 捕获选择图片错误
- ✅ 显示具体错误信息
- ✅ 提升用户体验

---

## 📊 优化前后对比

### 优化前

```
用户操作：选择图片 → 点击上传
系统反应：显示"识别中..." → 失败 → "保存失败"
用户困惑：❓ 为什么失败？是网络问题？图片问题？
开发者：❓ 没有日志，无法排查
```

### 优化后

```
用户操作：选择图片 → 点击上传
系统反应：
  1. 检查图片大小 → 如果太大，提示"图片太大"
  2. 显示"识别中..."
  3. 记录详细日志：
     - [饮食上传] 开始上传
     - [饮食上传] 图片大小: 2.3 MB
     - [饮食上传] 读取成功
     - [饮食上传] 发送请求...
  4. 成功 → "保存成功！"
  5. 失败 → "读取图片失败: 文件不存在"（具体原因）
开发者：✅ 有详细日志，快速定位问题
```

---

## 🔍 调试方法

### 1. 查看控制台日志

打开微信开发者工具 Console 面板，查看：

```
[饮食上传] ===== 开始上传 =====
[饮食上传] 图片路径: wxfile://...
[饮食上传] 图片大小: 2.3 MB
[饮食上传] 日期: 2026-01-24
[饮食上传] 餐食类型: lunch
[饮食上传] 开始读取图片...
[饮食上传] 读取成功，Base64 长度: 345678
[饮食上传] 发送请求到服务器...
[饮食上传] 上传成功
[饮食上传] ===== 上传流程结束 =====
```

### 2. 查看 Network 面板

检查 API 请求：
- URL: `/api/diet/recognize-and-save`
- Method: POST
- Status: 200 (成功) / 400 (客户端错误) / 500 (服务器错误)

### 3. 常见错误模式

#### 错误 A: 图片读取失败
```
[饮食上传] 读取图片失败: Error: fail file not exist
```
**原因**: 临时文件已被清理
**解决**: 重新选择图片

#### 错误 B: 网络超时
```
[饮食上传] 保存失败，错误详情: request:fail timeout
```
**原因**: 网络慢或图片太大
**解决**: 检查网络，选择较小的图片

#### 错误 C: Token 过期
```
[饮食上传] 保存失败，错误详情: 未登录或登录已过期
```
**原因**: JWT Token 过期
**解决**: 重新登录

---

## 🚀 使用方法

### 1. 重新编译小程序

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

### 2. 在微信开发者工具中测试

1. 打开微信开发者工具
2. 点击"编译"按钮
3. 打开饮食记录页面
4. 选择图片并上传
5. 查看 Console 日志

### 3. 真机测试

1. 点击"预览"按钮
2. 扫码在手机上打开
3. 测试上传功能
4. 如果失败，通过"真机调试"查看日志

---

## 📝 问题排查清单

如果上传仍然失败，请检查：

### 前端检查
- [ ] Console 是否有 `[饮食上传]` 日志
- [ ] 图片大小是否超过 5MB
- [ ] Base64 长度是否正常（> 1000）
- [ ] Network 面板请求状态

### 后端检查
```bash
# 检查后端服务状态
ssh root@health.westwetlandtech.com "systemctl status health-backend"

# 查看最近的日志
ssh root@health.westwetlandtech.com "journalctl -u health-backend --since '5 minutes ago' --no-pager | tail -50"

# 查看 AI 识别日志
ssh root@health.westwetlandtech.com "journalctl -u health-backend --since '5 minutes ago' --no-pager | grep 'food_recognition'"
```

### 网络检查
- [ ] 小程序是否配置了合法域名
- [ ] 网络是否正常
- [ ] 是否有防火墙拦截

---

## 📚 相关文档

- **DIET_UPLOAD_TROUBLESHOOTING.md** - 详细的问题排查指南
- **packages/mini-program/src/pages/diet/index.tsx** - 饮食记录页面代码
- **packages/mini-program/src/services/request.ts** - 网络请求封装
- **backend/app/api/diet.py** - 后端饮食记录 API

---

## 🎉 总结

### 优化成果

1. ✅ **图片大小检查** - 防止上传超大图片
2. ✅ **详细日志** - 便于调试和排查问题
3. ✅ **错误处理** - 捕获各种异常情况
4. ✅ **超时时间** - 给 AI 识别足够时间
5. ✅ **友好提示** - 明确的错误信息

### 用户体验提升

- 🚀 上传成功率提高
- 🎯 错误提示更明确
- ⏱️ 超时问题减少
- 🔍 问题更容易排查

---

**现在请在微信开发者工具中重新编译，然后测试上传功能。如果仍有问题，请提供 Console 日志以便进一步诊断。** ✅
