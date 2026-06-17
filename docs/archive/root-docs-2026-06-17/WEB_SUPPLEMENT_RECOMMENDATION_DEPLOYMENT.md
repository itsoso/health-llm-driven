# Web 端补剂科学推荐功能部署指南

**日期**: 2026-01-23  
**功能**: 补剂科学推荐独立页面  
**路由**: `/supplement-recommendation`

## 📦 部署步骤

### 1. 服务器部署（生产环境）

```bash
# SSH 登录服务器
ssh root@health.westwetlandtech.com

# 进入项目目录
cd /opt/health-app

# 拉取最新代码
git pull origin main

# 进入前端目录
cd frontend

# 安装依赖（如果有新依赖）
pnpm install

# 构建生产版本
pnpm run build

# 重启 Next.js 服务
pm2 restart health-frontend
# 或
pm2 restart all

# 查看日志
pm2 logs health-frontend --lines 50
```

### 2. 验证部署

访问以下 URL 验证功能：

1. **补剂推荐页面**
   ```
   https://health.westwetlandtech.com/supplement-recommendation
   ```

2. **补剂管理页面**（检查快捷按钮）
   ```
   https://health.westwetlandtech.com/supplements
   ```

3. **导航栏**（检查"补剂推荐"入口）
   - 点击"每日记录"下拉菜单
   - 应该看到"补剂推荐"选项

### 3. 功能测试

#### 3.1 基础功能测试

- [ ] 页面能正常加载
- [ ] 显示加载动画
- [ ] 成功获取推荐数据
- [ ] 显示评分卡片
- [ ] 显示健康分析（4 个指标）
- [ ] 显示推荐补剂列表
- [ ] 显示服用时间表
- [ ] 显示注意事项

#### 3.2 交互测试

- [ ] 点击"刷新推荐"按钮能重新加载
- [ ] 调试信息展开/收起正常
- [ ] 响应式设计在不同屏幕尺寸下正常

#### 3.3 入口测试

- [ ] 导航栏"每日记录" → "补剂推荐"能跳转
- [ ] 补剂管理页面"🤖 科学推荐"按钮能跳转
- [ ] 页面 URL 正确

#### 3.4 错误处理测试

- [ ] 无数据时显示友好提示
- [ ] API 错误时显示错误信息
- [ ] 点击"重新加载"能恢复

### 4. 性能检查

```bash
# 检查 Next.js 服务状态
pm2 status

# 检查内存使用
pm2 monit

# 检查日志是否有错误
pm2 logs health-frontend --err --lines 100
```

### 5. Nginx 配置（无需修改）

现有 Nginx 配置已支持所有 Next.js 路由：

```nginx
location / {
    proxy_pass http://127.0.0.1:30001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
}
```

### 6. 常见问题排查

#### 问题 1: 页面 404

**原因**: Next.js 构建不完整或服务未重启

**解决**:
```bash
cd /opt/health-app/frontend
rm -rf .next
pnpm run build
pm2 restart health-frontend
```

#### 问题 2: API 调用失败

**原因**: 后端服务未启动或 API 路由错误

**解决**:
```bash
# 检查后端服务
pm2 status health-backend

# 重启后端
pm2 restart health-backend

# 检查日志
pm2 logs health-backend --lines 50
```

#### 问题 3: 显示空白或加载失败

**原因**: 用户数据不足或 API 返回错误

**解决**:
1. 打开浏览器开发者工具（F12）
2. 查看 Console 错误信息
3. 查看 Network 标签，检查 API 请求状态
4. 确认用户有足够的健康数据（Garmin 同步）

#### 问题 4: 样式错误或布局混乱

**原因**: Tailwind CSS 未正确编译

**解决**:
```bash
cd /opt/health-app/frontend
rm -rf .next
pnpm run build
pm2 restart health-frontend
```

### 7. 回滚方案

如果部署后出现严重问题，可以回滚到上一个版本：

```bash
cd /opt/health-app

# 查看最近的提交
git log --oneline -5

# 回滚到上一个提交（8f44579 之前）
git reset --hard 05feedc

# 重新构建和重启
cd frontend
pnpm run build
pm2 restart health-frontend
```

### 8. 监控指标

部署后需要监控以下指标：

- **页面加载时间**: < 2 秒
- **API 响应时间**: < 5 秒
- **错误率**: < 1%
- **用户访问量**: 记录访问日志

### 9. 数据库检查

确认后端数据库有足够的数据支持推荐：

```sql
-- 检查用户健康数据
SELECT user_id, COUNT(*) as record_count
FROM garmin_data
WHERE record_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY user_id;

-- 检查补剂定义
SELECT user_id, COUNT(*) as supplement_count
FROM supplement_definitions
WHERE is_active = true
GROUP BY user_id;

-- 检查补剂打卡记录
SELECT user_id, COUNT(*) as checkin_count
FROM supplement_records
WHERE record_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY user_id;
```

### 10. 后续优化

部署完成后可以考虑的优化：

1. **缓存推荐结果**
   - 同一天内相同用户的推荐可以缓存
   - 减少 AI 分析次数，提升响应速度

2. **历史记录功能**
   - 保存每次推荐结果
   - 支持查看历史推荐

3. **一键添加功能**
   - 从推荐结果直接添加补剂到列表
   - 自动填充剂量和时间

4. **分享功能**
   - 生成推荐报告图片
   - 支持分享到社交平台

5. **推送通知**
   - 定期推送补剂推荐更新
   - 提醒用户查看新的推荐

---

## 📊 部署检查清单

### 部署前

- [x] 代码已提交到 Git
- [x] 后端 API 已实现并测试
- [x] 前端页面已开发完成
- [x] 导航入口已添加
- [x] 文档已更新

### 部署中

- [ ] 服务器代码已拉取
- [ ] 依赖已安装
- [ ] 前端已构建
- [ ] 服务已重启

### 部署后

- [ ] 页面能正常访问
- [ ] 功能测试通过
- [ ] 入口测试通过
- [ ] 错误处理正常
- [ ] 性能指标正常
- [ ] 无严重错误日志

---

## 🔗 相关链接

- **生产环境**: https://health.westwetlandtech.com/supplement-recommendation
- **补剂管理**: https://health.westwetlandtech.com/supplements
- **后端 API**: https://health.westwetlandtech.com/api/v1/supplements/scientific-recommendation
- **API 文档**: `backend/app/api/supplements.py`
- **服务类**: `backend/app/services/supplement_recommendation.py`

---

## 📝 部署记录

| 日期 | 版本 | 操作人 | 状态 | 备注 |
|------|------|--------|------|------|
| 2026-01-23 | 8f44579 | AI | 待部署 | 初始版本，添加补剂推荐页面 |

---

**准备就绪！** 🚀 现在可以在服务器上执行部署步骤。
