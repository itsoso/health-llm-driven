# 饮食推荐功能故障排查指南

## 问题 1: 页面显示 "加载中..." 不消失

### 可能原因
- API 请求失败
- 后端服务未启动
- 认证 token 过期

### 排查步骤

1. **检查浏览器 Console**
   ```
   F12 → Console 标签
   查看是否有错误信息
   ```

2. **检查 Network 请求**
   ```
   F12 → Network 标签
   查看 /api/v1/diet-recommendation/me 请求状态
   - 200: 成功
   - 401: 未登录
   - 500: 服务器错误
   ```

3. **检查后端日志**
   ```bash
   ssh root@39.98.206.178
   journalctl -u health-backend -f | grep diet
   ```

## 问题 2: 数据显示不正确

### 可能原因
- 用户 profile 数据缺失
- 饮食记录数据缺失
- 计算逻辑错误

### 排查步骤

1. **检查用户 profile**
   ```sql
   SELECT * FROM user_profiles WHERE user_id = YOUR_USER_ID;
   ```
   
   必需字段：
   - height_cm
   - current_weight_kg
   - gender
   - birth_date

2. **检查饮食记录**
   ```sql
   SELECT * FROM diet_records 
   WHERE user_id = YOUR_USER_ID 
     AND record_date = CURRENT_DATE;
   ```

3. **检查运动数据**
   ```sql
   SELECT * FROM workout_records 
   WHERE user_id = YOUR_USER_ID 
     AND workout_date >= CURRENT_DATE - INTERVAL '7 days';
   ```

## 问题 3: 推荐内容不合理

### 可能原因
- 算法参数需要调整
- 用户数据不完整
- LLM 服务异常

### 排查步骤

1. **检查 BMR 计算**
   ```
   男性: BMR = 10 × 体重(kg) + 6.25 × 身高(cm) - 5 × 年龄 + 5
   女性: BMR = 10 × 体重(kg) + 6.25 × 身高(cm) - 5 × 年龄 - 161
   ```

2. **检查活动系数**
   ```
   久坐: 1.2
   轻度活动: 1.375
   中度活动: 1.55
   重度活动: 1.725
   极重度活动: 1.9
   ```

3. **检查营养素比例**
   ```
   蛋白质: 1.6-2.2 g/kg 体重
   碳水: 45-55% 总热量
   脂肪: 20-30% 总热量
   ```

## 问题 4: 小程序无法显示

### 可能原因
- 小程序代码未更新
- API 路径错误
- 网络请求失败

### 排查步骤

1. **检查小程序版本**
   ```
   确保使用最新的体验版或正式版
   ```

2. **检查 API 路径**
   ```typescript
   // packages/mini-program/src/services/api.ts
   const API_BASE = 'https://health.westwetlandtech.com/api/v1';
   ```

3. **查看小程序 Console**
   ```
   微信开发者工具 → Console 标签
   查看错误信息
   ```

## 问题 5: 性能问题（加载慢）

### 可能原因
- 数据量大
- 数据库查询慢
- LLM 调用超时

### 优化建议

1. **添加缓存**
   ```python
   # 缓存推荐结果 5 分钟
   @cache(ttl=300)
   def get_diet_recommendation(user_id: int):
       ...
   ```

2. **优化数据库查询**
   ```sql
   -- 添加索引
   CREATE INDEX idx_diet_records_user_date 
   ON diet_records(user_id, record_date);
   ```

3. **异步处理**
   ```python
   # 使用后台任务处理耗时操作
   background_tasks.add_task(generate_recommendations)
   ```

## 调试命令

### 1. 检查后端服务状态
```bash
systemctl status health-backend
```

### 2. 查看实时日志
```bash
journalctl -u health-backend -f
```

### 3. 测试 API
```bash
curl -X GET "https://health.westwetlandtech.com/api/v1/diet-recommendation/me" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq '.'
```

### 4. 检查数据库连接
```bash
cd /opt/health-app/backend
source venv/bin/activate
python -c "from app.database import SessionLocal; db = SessionLocal(); print('✅ 数据库连接成功')"
```

## 联系支持

如果问题仍未解决，请提供以下信息：

1. **错误截图**
2. **浏览器 Console 错误信息**
3. **Network 请求详情**
4. **用户 ID**
5. **操作步骤**

---

**最后更新**: 2026-01-23
