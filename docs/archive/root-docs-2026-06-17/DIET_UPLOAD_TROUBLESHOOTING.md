# 小程序食物照片上传问题排查和解决方案

## 🔍 问题排查步骤

### 1. 查看控制台错误

在微信开发者工具中打开 Console 面板，查看是否有以下错误：

#### 错误类型 A: 图片读取失败
```
选择图片失败: xxx
智能识别失败: xxx
```

**可能原因**:
- 文件路径无效
- 文件系统权限问题
- 图片格式不支持

#### 错误类型 B: 网络请求失败
```
请求失败: xxx
保存失败: xxx
```

**可能原因**:
- 网络超时
- Token 过期
- 服务器错误

#### 错误类型 C: Base64 编码问题
```
Failed to execute 'atob' on 'Window'
Invalid character in base64 string
```

**可能原因**:
- Base64 字符串格式错误
- 图片太大导致内存溢出

---

## 🐛 常见问题和解决方案

### 问题 1: 图片太大导致上传失败

**症状**: 
- 选择图片后长时间无响应
- 提示"保存失败"或"识别失败"
- 控制台显示内存溢出

**原因**: 
- 原图太大（> 5MB）
- Base64 编码后超过小程序内存限制

**解决方案**:

```typescript
// 在 handleChooseImage 中添加图片压缩
const handleChooseImage = () => {
  Taro.chooseImage({
    count: 1,
    sizeType: ['compressed'],  // ✅ 已设置压缩
    sourceType: ['album', 'camera'],
    success: (res) => {
      const tempFilePath = res.tempFilePaths[0];
      
      // 检查文件大小
      Taro.getFileInfo({
        filePath: tempFilePath,
        success: (fileInfo) => {
          console.log('图片大小:', fileInfo.size / 1024, 'KB');
          
          if (fileInfo.size > 5 * 1024 * 1024) {  // 5MB
            Taro.showToast({ 
              title: '图片太大，请选择较小的图片', 
              icon: 'none' 
            });
            return;
          }
          
          setImagePreview(tempFilePath);
          setRecognitionResult(null);
        }
      });
    },
    fail: (err) => {
      console.error('选择图片失败:', err);
      Taro.showToast({ 
        title: `选择图片失败: ${err.errMsg}`, 
        icon: 'none' 
      });
    },
  });
};
```

---

### 问题 2: Base64 读取失败

**症状**:
- 提示"识别失败，请重试"
- 控制台显示 `readFileSync` 错误

**原因**:
- 文件路径格式错误
- 文件系统权限问题
- 临时文件已被清理

**解决方案**:

```typescript
// 在 handleRecognizeAndSave 中添加错误处理
const handleRecognizeAndSave = async () => {
  if (!imagePreview) {
    Taro.showToast({ title: '请先选择图片', icon: 'none' });
    return;
  }

  if (isSaving) {
    return;
  }

  setIsSaving(true);
  setIsRecognizing(true);
  
  try {
    const fs = Taro.getFileSystemManager();
    
    // 添加错误处理
    let base64: string;
    try {
      base64 = fs.readFileSync(imagePreview, 'base64') as string;
      console.log('[饮食上传] Base64 长度:', base64.length);
    } catch (readError) {
      console.error('[饮食上传] 读取图片失败:', readError);
      throw new Error('读取图片失败，请重新选择');
    }

    // 检查 Base64 是否有效
    if (!base64 || base64.length < 100) {
      throw new Error('图片数据无效，请重新选择');
    }

    console.log('[饮食上传] 开始上传...');
    
    await request({
      url: '/diet/recognize-and-save',
      method: 'POST',
      data: {
        image_base64: base64,
        image_type: 'jpeg',
        record_date: selectedDate,
        meal_type: mealType,
        notes: formData.notes || null,
      },
    });

    console.log('[饮食上传] 上传成功');
    Taro.showToast({ title: '保存成功！', icon: 'success' });
    resetForm();
    loadDailySummary();
  } catch (error: any) {
    console.error('[饮食上传] 保存失败:', error);
    Taro.showToast({ 
      title: error.message || '保存失败，请重试', 
      icon: 'none',
      duration: 3000
    });
  } finally {
    setIsRecognizing(false);
    setIsSaving(false);
  }
};
```

---

### 问题 3: 网络请求超时

**症状**:
- 长时间显示"识别中..."
- 最终提示"保存失败"
- Network 面板显示请求超时

**原因**:
- 图片太大导致上传慢
- AI 识别耗时长
- 网络不稳定

**解决方案**:

```typescript
// 在 request.ts 中增加超时时间
export async function request<T = any>(config: RequestConfig): Promise<T> {
  const { url, method = 'GET', data, params, header = {}, needAuth = true, silent = false } = config;

  // ... 其他代码 ...

  const response = await Taro.request<T>({
    url: finalUrl,
    method,
    data,
    header: {
      ...header,
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    },
    timeout: 60000,  // ✅ 增加到 60 秒（AI 识别需要时间）
  });

  // ... 其他代码 ...
}
```

---

### 问题 4: Token 过期

**症状**:
- 提示"登录已过期，请重新登录"
- Network 面板显示 401 错误

**原因**:
- JWT Token 已过期
- Token 被清除

**解决方案**:

用户需要重新登录：
1. 返回首页
2. 点击"我的"
3. 重新登录

---

### 问题 5: 服务器错误

**症状**:
- 提示"保存失败"
- Network 面板显示 500 错误

**原因**:
- 后端服务异常
- 数据库连接失败
- AI 服务不可用

**解决方案**:

查看后端日志：
```bash
ssh root@health.westwetlandtech.com "journalctl -u health-backend --since '5 minutes ago' --no-pager | tail -50"
```

---

## 🔧 代码优化建议

### 1. 添加详细日志

```typescript
const handleRecognizeAndSave = async () => {
  console.log('[饮食上传] 开始处理');
  console.log('[饮食上传] 图片路径:', imagePreview);
  console.log('[饮食上传] 日期:', selectedDate);
  console.log('[饮食上传] 餐食类型:', mealType);
  
  // ... 处理逻辑 ...
  
  console.log('[饮食上传] 完成');
};
```

### 2. 添加重试机制

```typescript
const uploadWithRetry = async (data: any, maxRetries = 3) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await request({
        url: '/diet/recognize-and-save',
        method: 'POST',
        data,
      });
    } catch (error) {
      console.error(`[饮食上传] 第 ${i + 1} 次尝试失败:`, error);
      if (i === maxRetries - 1) {
        throw error;
      }
      // 等待 1 秒后重试
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
};
```

### 3. 添加进度提示

```typescript
const handleRecognizeAndSave = async () => {
  // ... 前置检查 ...
  
  Taro.showLoading({ title: '正在识别...' });
  
  try {
    // ... 上传逻辑 ...
    Taro.hideLoading();
    Taro.showToast({ title: '保存成功！', icon: 'success' });
  } catch (error) {
    Taro.hideLoading();
    Taro.showToast({ title: '保存失败', icon: 'none' });
  }
};
```

---

## 📊 诊断清单

### 前端检查
- [ ] 控制台是否有错误日志
- [ ] Network 面板请求状态（200/401/500）
- [ ] 图片大小是否合理（< 5MB）
- [ ] Token 是否有效
- [ ] 文件路径是否正确

### 后端检查
- [ ] 后端服务是否运行（`systemctl status health-backend`）
- [ ] 后端日志是否有错误（`journalctl -u health-backend`）
- [ ] AI 服务是否可用（OpenAI API Key）
- [ ] 文件上传目录是否有写权限
- [ ] 数据库连接是否正常

---

## 🚀 快速修复步骤

### 步骤 1: 添加详细日志

修改 `packages/mini-program/src/pages/diet/index.tsx`:

```typescript
// 在 handleRecognizeAndSave 函数开头添加
console.log('[饮食上传] ===== 开始上传 =====');
console.log('[饮食上传] 图片路径:', imagePreview);

// 在 Base64 读取后添加
console.log('[饮食上传] Base64 长度:', base64.length);

// 在请求前添加
console.log('[饮食上传] 发送请求...');

// 在成功后添加
console.log('[饮食上传] 上传成功');

// 在错误处理中添加
console.error('[饮食上传] 错误详情:', error);
```

### 步骤 2: 重新编译

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

### 步骤 3: 测试验证

1. 打开微信开发者工具
2. 点击"编译"
3. 打开饮食记录页面
4. 选择图片并上传
5. 查看控制台日志

---

## 📝 错误信息收集模板

请提供以下信息以便进一步诊断：

```
1. 错误提示内容:
   ___________________________

2. 控制台日志:
   ___________________________

3. Network 面板:
   - 请求 URL: ___________________________
   - 状态码: ___________________________
   - 响应内容: ___________________________

4. 图片信息:
   - 图片大小: ___________________________
   - 图片来源: [ ] 相册  [ ] 拍照

5. 操作步骤:
   1. ___________________________
   2. ___________________________
   3. ___________________________
```

---

**建议**: 先添加详细日志，重新编译后测试，然后根据日志信息进一步诊断问题。
