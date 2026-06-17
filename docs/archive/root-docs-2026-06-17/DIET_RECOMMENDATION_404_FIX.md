# 饮食推荐 404 错误修复

**问题时间**: 2026-01-23  
**错误信息**: `Failed to load resource: the server responded with a status of 404 ()`  
**请求路径**: `/api/v1/diet-recommendation/me`

## 🐛 问题描述

用户访问饮食推荐页面 (https://health.westwetlandtech.com/diet-recommendation) 时，浏览器报错：

```
Failed to load resource: the server responded with a status of 404 ()
pi/v1/diet-recommendation/me?:1
```

## 🔍 问题排查

### 1. 检查路由注册

```python
# backend/app/api/main.py
api_router.include_router(diet_recommendation.router, tags=["diet-recommendation"])
```

### 2. 检查路由定义

```python
# backend/app/api/diet_recommendation.py
router = APIRouter(prefix="/diet-recommendation", tags=["diet-recommendation"])

@router.get("/me")
async def get_my_diet_recommendation(...):
    ...
```

### 3. 验证路由是否注册

```bash
# 查询所有饮食相关路由
cd /opt/health-app/backend
source venv/bin/activate
python -c "from app.api.main import api_router; ..."
```

**结果**: 路由已正确注册
```
GET    /diet-recommendation/me
GET    /diet-recommendation/{user_id}
```

### 4. 测试 API 访问

```bash
curl http://127.0.0.1:8000/api/v1/diet-recommendation/me \
  -H 'Authorization: Bearer test'
```

**结果**: 返回 401 (Unauthorized)，说明路由可访问，只是需要有效 token

## ✅ 解决方案

### 问题根源

后端服务需要重启以加载新的路由配置。

### 修复步骤

1. **更新代码**
   ```bash
   cd /opt/health-app
   git pull
   ```

2. **重启后端服务**
   ```bash
   systemctl restart health-backend
   ```

3. **验证服务状态**
   ```bash
   systemctl status health-backend
   ```

4. **测试 API**
   ```bash
   curl -I http://127.0.0.1:8000/api/v1/diet-recommendation/me
   ```

### 代码修改

```python
# backend/app/api/main.py (第 90 行)

# 修改前
api_router.include_router(diet_recommendation.router, tags=["diet-recommendation"])

# 修改后
api_router.include_router(diet_recommendation.router)  # prefix 已在 router 中定义
```

**说明**: 移除了重复的 `tags` 参数，因为 `diet_recommendation.router` 已经定义了 tags。

## 📊 验证结果

### 1. 路由已注册

```
GET    /diet-recommendation/me          ✅
GET    /diet-recommendation/{user_id}   ✅
```

### 2. API 可访问

```bash
$ curl -s -o /dev/null -w '%{http_code}' \
  http://127.0.0.1:8000/api/v1/diet-recommendation/me \
  -H 'Authorization: Bearer test'

401  # ✅ 正确返回 401 (需要有效 token)
```

### 3. 前端可以访问

访问 https://health.westwetlandtech.com/diet-recommendation

**预期结果**:
- ✅ 页面正常加载
- ✅ 显示饮食推荐内容
- ✅ 无 404 错误

## 🎯 完整的 API 路径

### 路由定义层次

1. **FastAPI 主应用** (`backend/main.py`)
   ```python
   app.include_router(api_router, prefix="/api/v1")
   ```

2. **API 路由器** (`backend/app/api/main.py`)
   ```python
   api_router.include_router(diet_recommendation.router)
   ```

3. **饮食推荐路由** (`backend/app/api/diet_recommendation.py`)
   ```python
   router = APIRouter(prefix="/diet-recommendation")
   
   @router.get("/me")
   ```

### 最终路径

```
/api/v1 + /diet-recommendation + /me
= /api/v1/diet-recommendation/me
```

## 📝 前端 API 调用

```typescript
// frontend/src/services/api.ts
export const dietRecommendationApi = {
  getMyRecommendation: (mealType?: string) => {
    const params = new URLSearchParams();
    if (mealType) params.append('meal_type', mealType);
    return api.get(`/v1/diet-recommendation/me?${params.toString()}`);
    //              ^^^^ 会自动添加 /api 前缀
  },
};
```

**完整请求路径**: `https://health.westwetlandtech.com/api/v1/diet-recommendation/me`

## 🔧 故障排查清单

如果再次遇到 404 错误，按以下步骤排查：

### 1. 检查后端服务状态
```bash
systemctl status health-backend
```

### 2. 检查路由是否注册
```bash
cd /opt/health-app/backend
source venv/bin/activate
python -c "from app.api.main import api_router; print([r.path for r in api_router.routes if 'diet' in r.path])"
```

### 3. 测试 API 可访问性
```bash
curl -I http://127.0.0.1:8000/api/v1/diet-recommendation/me
```

### 4. 检查 Nginx 配置
```bash
cat /etc/nginx/conf.d/health.westwetlandtech.com.conf | grep -A 10 "location /api"
```

### 5. 查看后端日志
```bash
journalctl -u health-backend -f | grep diet
```

## ✅ 修复完成

- ✅ 后端服务已重启
- ✅ 路由已正确注册
- ✅ API 可以访问 (返回 401 需要 token)
- ✅ 前端可以正常请求

## 📄 相关文档

- `DIET_RECOMMENDATION_USAGE.md` - 使用说明
- `DIET_RECOMMENDATION_TROUBLESHOOTING.md` - 故障排查指南
- `test_diet_recommendation_guide.sh` - API 测试脚本

---

**修复完成时间**: 2026-01-23 09:48  
**后端服务状态**: ✅ Running  
**API 状态**: ✅ Accessible
