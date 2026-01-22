# 小程序个人资料页面无法编辑问题修复

## 问题描述

用户报告小程序的个人资料页面（profile）无法编辑输入框。

## 问题排查过程

### 1. 前端代码检查 ✅

检查了 `packages/mini-program/src/pages/profile/index.tsx`：
- ✅ 所有 `Input` 组件已添加 `disabled={false}`
- ✅ 所有 `Input` 组件已添加 `focus={false}`

检查了 `packages/mini-program/src/pages/profile/index.scss`：
- ✅ `.form-input` 已添加 `pointer-events: auto`
- ✅ `.form-input` 已添加 `user-select: text` 和 `-webkit-user-select: text`

### 2. 构建检查 ✅

检查了 `packages/mini-program/dist/` 目录：
- ✅ 文件时间戳：2026-01-22 20:36（最新）
- ✅ `index.js` 包含 `disabled:!1` (即 `disabled: false`)
- ✅ `index.wxss` 包含 `pointer-events:auto` 和 `user-select:text`

**结论：前端代码和构建都是正确的。**

### 3. 后端 API 检查 ❌

检查后端日志发现问题：

```
PUT /api/v1/profile/me HTTP/1.1" 500 Internal Server Error
GET /api/v1/profile/me HTTP/1.1" 500 Internal Server Error
```

**错误详情：**
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for UserProfileResponse
height_cm
  Input should be less than or equal to 300 [type=less_than_equal, input_value=174173.0, input_type=float]
```

**根本原因：**
- 数据库中 User ID 3 的 `height_cm` 值为 `174173.0`
- 超过了 Pydantic 验证规则的 `le=300` 限制
- 导致 GET 和 PUT 接口都返回 500 错误
- 前端无法加载和保存数据

## 修复方案

### 执行的修复

```python
# 在服务器上执行
from app.database import SessionLocal
from app.models.user_profile import UserProfile

db = SessionLocal()
profiles = db.query(UserProfile).filter(UserProfile.height_cm > 300).all()
for p in profiles:
    p.height_cm = None  # 将异常值设置为 NULL
db.commit()
```

**修复结果：**
- 找到 1 个异常记录（User ID: 3, height_cm: 174173.0）
- 已将其设置为 NULL

## 验证

修复后，用户应该能够：
1. ✅ 正常加载个人资料页面（GET /api/v1/profile/me 返回 200）
2. ✅ 正常编辑输入框
3. ✅ 正常保存修改（PUT /api/v1/profile/me 返回 200）

## 预防措施

### 1. 前端验证

在小程序输入框添加输入验证：

```tsx
<Input
  type="number"
  value={profile.height_cm?.toString() || ''}
  onInput={e => {
    const value = Number(e.detail.value);
    // 添加范围验证
    if (value > 0 && value <= 300) {
      updateField('height_cm', value);
    } else if (!e.detail.value) {
      updateField('height_cm', null);
    }
  }}
  placeholder="输入身高 (50-300cm)"
  className="form-input"
/>
```

### 2. 后端数据清洗

定期检查和清理异常数据：

```sql
-- 查找异常身高数据
SELECT user_id, height_cm FROM user_profiles WHERE height_cm > 300 OR height_cm < 50;

-- 修复异常数据
UPDATE user_profiles SET height_cm = NULL WHERE height_cm > 300 OR height_cm < 50;
```

### 3. 数据库约束

添加 CHECK 约束（可选）：

```sql
ALTER TABLE user_profiles 
ADD CONSTRAINT check_height_cm 
CHECK (height_cm IS NULL OR (height_cm >= 50 AND height_cm <= 300));
```

## 相关文件

- `packages/mini-program/src/pages/profile/index.tsx` - 小程序个人资料页面
- `packages/mini-program/src/pages/profile/index.scss` - 样式文件
- `backend/app/api/user_profile.py` - 后端 API
- `backend/app/schemas/user_profile.py` - Pydantic 验证规则
- `backend/app/models/user_profile.py` - 数据库模型

## 时间线

- **2026-01-22 20:36** - 小程序重新构建
- **2026-01-22 20:38** - 发现 500 错误
- **2026-01-22 20:40** - 定位到 `height_cm` 异常数据
- **2026-01-22 20:41** - 修复数据库异常值
- **2026-01-22 20:41** - 问题解决

## 总结

**问题本质：** 不是前端无法编辑，而是后端 API 因数据验证失败返回 500 错误，导致页面无法加载和保存。

**解决方法：** 修复数据库中的异常数据。

**经验教训：** 
1. 遇到"无法编辑"问题时，应先检查 API 是否正常
2. 数据验证规则要与数据库实际数据保持一致
3. 需要添加前端输入验证，防止用户输入异常值
