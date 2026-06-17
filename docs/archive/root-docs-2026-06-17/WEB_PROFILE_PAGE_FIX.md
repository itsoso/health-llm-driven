# Web 个人资料页面修复

## 问题描述

用户反馈 Web 端个人资料页面（https://health.westwetlandtech.com/profile）无法打开。

## 问题原因

生产环境的前端代码未更新到最新版本，导致页面构建文件过期。

### 问题分析

1. **后端 API 正常**
   - 测试 `/api/v1/profile/me` 端点返回 401（需要认证）
   - 说明路由已正确注册，API 功能正常

2. **前端代码存在**
   - `frontend/src/app/profile/page.tsx` 文件存在
   - 本地构建成功，无 lint 错误
   - 页面大小：8.31 kB

3. **生产环境代码过期**
   - 服务器上的代码停留在旧版本（commit: 63835b4）
   - 最新代码未部署到生产环境
   - 前端构建文件未更新

## 修复方案

### 1. 更新生产环境代码

```bash
cd /opt/health-app/frontend
git pull origin main
```

### 2. 重新构建前端

```bash
npm run build
```

### 3. 重启前端服务

```bash
pm2 restart health-frontend
```

## 修复结果

### 部署状态

- ✅ 代码已更新到最新版本（commit: 70c575c）
- ✅ 前端已重新构建
- ✅ 前端服务已重启
- ✅ 页面可以正常访问（HTTP 200 OK）

### 验证结果

```bash
$ curl -I "https://health.westwetlandtech.com/profile"
HTTP/2 200 
server: nginx/1.18.0 (Ubuntu)
content-type: text/html; charset=utf-8
content-length: 17938
```

## 页面功能

### 个人资料页面特性

**页面路径：** `/profile`

**功能模块：**

1. **基本信息**
   - 性别选择
   - 出生日期
   - 身高（cm）
   - 血型
   - 当前体重（kg）
   - 所在城市
   - 时区设置

2. **健康状况**
   - 慢性病史（可添加/删除）
   - 过敏源（可添加/删除）
   - 家族病史（快速选择）

3. **生活习惯**
   - 运动频率
   - 饮食偏好
   - 吸烟状态
   - 饮酒情况
   - 通常入睡时间
   - 通常起床时间
   - 工作类型
   - 每日久坐时长

4. **健康目标**
   - 目标步数
   - 目标睡眠时长
   - 目标饮水量
   - 目标运动时长
   - 目标体重
   - 目标卡路里消耗

### UI 特性

- ✅ 响应式设计（支持桌面和移动端）
- ✅ Tab 导航（4 个标签页）
- ✅ BMI 卡片显示（自动计算）
- ✅ 年龄显示（根据出生日期计算）
- ✅ 实时保存功能
- ✅ 深色主题（渐变背景）

## 技术要点

### 1. Next.js 静态页面生成

页面使用 `'use client'` 标记为客户端组件：

```tsx
'use client';

export default function ProfilePage() {
  // ...
}
```

### 2. 认证保护

页面通过 `useAuth` Hook 检查用户登录状态：

```tsx
const { user, isLoading: authLoading } = useAuth();

if (!user) {
  router.push('/login');
  return null;
}
```

### 3. 数据获取

使用 React Query 获取用户画像数据：

```tsx
const { data: profile, isLoading } = useQuery<UserProfile>({
  queryKey: ['userProfile'],
  queryFn: async () => {
    const response = await api.get('/profile/me');
    return response.data;
  },
  enabled: !!user,
});
```

### 4. 数据更新

使用 Mutation 更新用户画像：

```tsx
const updateMutation = useMutation({
  mutationFn: async (data: Partial<UserProfile>) => {
    const response = await api.put('/profile/me', data);
    return response.data;
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['userProfile'] });
    alert('保存成功！');
  },
});
```

## 部署流程

### 标准部署步骤

1. **提交代码到 GitHub**
   ```bash
   git add .
   git commit -m "feat: 更新功能"
   git push origin main
   ```

2. **登录服务器**
   ```bash
   ssh root@39.98.206.178
   ```

3. **更新前端代码**
   ```bash
   cd /opt/health-app/frontend
   git pull origin main
   ```

4. **重新构建**
   ```bash
   npm run build
   ```

5. **重启服务**
   ```bash
   pm2 restart health-frontend
   ```

### 自动化部署脚本

可以使用项目中的 `deploy.sh` 脚本：

```bash
./deploy.sh
```

该脚本会自动执行：
- 推送代码到 GitHub
- 部署前端（拉取代码、构建、重启）
- 部署后端（拉取代码、安装依赖、重启）

## 常见问题

### Q1: 页面显示空白

**可能原因：**
- 前端构建失败
- JavaScript 错误
- API 请求失败

**解决方案：**
- 检查浏览器控制台错误
- 检查网络请求
- 重新构建前端

### Q2: 页面显示 404

**可能原因：**
- 路由配置错误
- 页面文件不存在
- 前端服务未启动

**解决方案：**
- 检查文件是否存在
- 验证路由配置
- 重启前端服务

### Q3: 数据无法保存

**可能原因：**
- API 请求失败
- 认证 Token 过期
- 数据验证失败

**解决方案：**
- 检查网络请求
- 重新登录
- 验证数据格式

## 监控建议

### 1. 前端服务监控

```bash
# 检查服务状态
pm2 status health-frontend

# 查看日志
pm2 logs health-frontend --lines 50

# 查看错误日志
pm2 logs health-frontend --err --lines 50
```

### 2. Nginx 访问日志

```bash
# 查看访问日志
tail -f /var/log/nginx/access.log | grep "/profile"

# 查看错误日志
tail -f /var/log/nginx/error.log
```

### 3. 页面性能监控

- 首次加载时间
- API 响应时间
- 页面大小（当前：17.9 KB）

## 后续优化建议

### 1. 自动部署

- 设置 GitHub Actions 自动部署
- 代码推送后自动构建和部署
- 减少手动操作错误

### 2. 健康检查

- 添加前端健康检查端点
- 定期检查页面可访问性
- 异常时自动告警

### 3. 版本管理

- 在页面中显示版本号
- 记录部署历史
- 方便问题追溯

### 4. 缓存优化

- 设置合理的缓存策略
- 静态资源 CDN 加速
- 提升页面加载速度

## 相关文件

### 前端文件

- `frontend/src/app/profile/page.tsx` - 个人资料页面
- `frontend/src/services/api.ts` - API 服务
- `frontend/src/contexts/AuthContext.tsx` - 认证上下文

### 后端文件

- `backend/app/api/user_profile.py` - 用户画像 API
- `backend/app/models/user_profile.py` - 用户画像模型
- `backend/app/schemas/user_profile.py` - 用户画像 Schema

### 配置文件

- `frontend/next.config.js` - Next.js 配置
- `frontend/package.json` - 依赖配置
- `deploy.sh` - 部署脚本

## 注意事项

1. **代码同步**
   - 确保生产环境代码与 GitHub 同步
   - 定期检查代码版本
   - 避免手动修改生产环境代码

2. **构建验证**
   - 部署前在本地构建验证
   - 检查构建输出是否正常
   - 确认页面大小合理

3. **服务重启**
   - 重启后检查服务状态
   - 验证页面可访问性
   - 查看日志确认无错误

4. **用户影响**
   - 选择低峰期部署
   - 部署后及时验证
   - 出现问题快速回滚

---

**修复完成时间**: 2026-01-22  
**修复人**: AI Assistant  
**部署版本**: 70c575c  
**页面状态**: ✅ 正常访问
