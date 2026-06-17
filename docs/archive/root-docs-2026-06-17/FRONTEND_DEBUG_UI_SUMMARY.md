# 前端 Debug UI 实现总结

## 已完成功能

### 1. 运动前指导页面 (`/workout-guidance`)

#### 新增功能
- ✅ Debug 模式开关（Checkbox）
- ✅ Debug 信息展示面板（紫色主题）
- ✅ API 调用支持 debug 参数

#### UI 布局

```
┌─────────────────────────────────────────┐
│  🎯 智能运动指导                         │
├─────────────────────────────────────────┤
│  运动前指导                              │
│  ┌───────────────────────────────────┐  │
│  │ 选择目标（可选）                   │  │
│  │ 运动类型（可选）                   │  │
│  │                                   │  │
│  │ ☑ Debug 模式（展示 AI 决策过程）   │  │
│  │                                   │  │
│  │ [🎯 获取运动前指导]                │  │
│  └───────────────────────────────────┘  │
├─────────────────────────────────────────┤
│  🔍 AI 决策过程 (Debug 面板)             │
│  ┌───────────────────────────────────┐  │
│  │ 📋 决策步骤                        │  │
│  │  1. 获取用户基本信息               │  │
│  │  2. 获取用户运动目标               │  │
│  │  3. 获取最近7天Garmin健康数据      │  │
│  │  ...                              │  │
│  ├───────────────────────────────────┤  │
│  │ 🧠 推理过程                        │  │
│  │  ✅ 用户资料：35岁，男，体重70kg   │  │
│  │  🎯 自动选择活跃目标：提升配速     │  │
│  │  📊 最近健康状态：睡眠评分85...    │  │
│  │  💓 基于年龄和静息心率计算心率区间 │  │
│  │  ...                              │  │
│  ├───────────────────────────────────┤  │
│  │ 📊 数据来源                        │  │
│  │  [点击查看详细数据来源 →]          │  │
│  │  (展开后显示 JSON 格式数据)        │  │
│  └───────────────────────────────────┘  │
├─────────────────────────────────────────┤
│  📊 当前状态                             │
│  🎯 今日训练目标                         │
│  🔥 热身建议                             │
│  ⚠️ 关键提醒                             │
│  📚 科学知识要点                         │
└─────────────────────────────────────────┘
```

#### 代码实现

**状态管理：**
```typescript
const [debugMode, setDebugMode] = useState(false);
```

**Debug 开关：**
```tsx
<div className="mb-4 flex items-center gap-3 p-4 bg-slate-700/50 rounded-lg">
  <input
    type="checkbox"
    id="debugMode"
    checked={debugMode}
    onChange={(e) => setDebugMode(e.target.checked)}
    className="w-5 h-5 text-blue-600"
  />
  <label htmlFor="debugMode" className="text-gray-300">
    🔍 Debug 模式（展示 AI 决策过程）
  </label>
</div>
```

**API 调用：**
```typescript
const preGuidanceMutation = useMutation({
  mutationFn: () => workoutGuidanceApi.getPreWorkoutGuidance(
    selectedGoalId, 
    workoutType || undefined, 
    debugMode  // 传递 debug 参数
  ),
  // ...
});
```

**Debug 面板：**
```tsx
{preGuidance.debug && (
  <div className="bg-gradient-to-br from-purple-900/50 to-purple-800/30 rounded-xl p-6">
    <h3 className="text-2xl font-bold text-white mb-4">
      🔍 AI 决策过程
    </h3>
    
    {/* 决策步骤 */}
    <div className="mb-6">
      <h4 className="text-lg font-semibold text-white mb-3">
        📋 决策步骤
      </h4>
      {preGuidance.debug.steps.map((step, index) => (
        <div key={index} className="flex items-start gap-3 bg-slate-800/50 rounded-lg p-3">
          <span className="text-purple-400 font-bold">{index + 1}</span>
          <span className="text-gray-200">{step}</span>
        </div>
      ))}
    </div>
    
    {/* 推理过程 */}
    <div className="mb-6">
      <h4 className="text-lg font-semibold text-white mb-3">
        🧠 推理过程
      </h4>
      {preGuidance.debug.reasoning.map((reason, index) => (
        <div key={index} className="bg-slate-800/50 rounded-lg p-3">
          <span className="text-gray-200 text-sm">{reason}</span>
        </div>
      ))}
    </div>
    
    {/* 数据来源 */}
    <details className="bg-slate-800/50 rounded-lg">
      <summary className="cursor-pointer p-4 text-purple-300">
        点击查看详细数据来源 →
      </summary>
      <pre className="text-xs text-gray-300 overflow-x-auto bg-slate-900/50 rounded p-4">
        {JSON.stringify(preGuidance.debug.data_sources, null, 2)}
      </pre>
    </details>
  </div>
)}
```

### 2. API 服务更新

**文件：** `frontend/src/services/api.ts`

```typescript
export const workoutGuidanceApi = {
  // 运动前指导
  getPreWorkoutGuidance: (
    goalId?: number, 
    workoutType?: string, 
    debug: boolean = false
  ) => {
    const params = new URLSearchParams();
    if (goalId) params.append('goal_id', goalId.toString());
    if (workoutType) params.append('workout_type', workoutType);
    if (debug) params.append('debug', 'true');
    return api.post(`/workout/pre-workout-guidance?${params.toString()}`);
  },
  
  // 运动后分析
  getPostWorkoutAnalysis: (
    workoutId: number, 
    forceRegenerate: boolean = false,
    debug: boolean = false
  ) => {
    const params = new URLSearchParams();
    if (forceRegenerate) params.append('force_regenerate', 'true');
    if (debug) params.append('debug', 'true');
    return api.post(`/workout/post-workout-analysis/${workoutId}?${params.toString()}`);
  },
};
```

## 设计特点

### 1. 视觉设计
- **紫色主题**：Debug 面板使用紫色渐变，与正常内容区分
- **图标系统**：每个部分都有对应的 emoji 图标，直观易懂
- **层次分明**：决策步骤、推理过程、数据来源分三个区域展示
- **可折叠**：详细数据来源使用 `<details>` 标签，避免信息过载

### 2. 交互设计
- **开关控制**：用户可以自由开启/关闭 Debug 模式
- **非侵入式**：Debug 面板在正常内容之前，不影响原有布局
- **响应式**：适配移动端和桌面端
- **渐进展示**：先显示步骤和推理，详细数据需要点击展开

### 3. 信息架构
```
Debug 面板
├── 决策步骤（7-8步）
│   └── 按顺序展示 AI 执行的每一步
├── 推理过程（15-20条）
│   └── 展示每一步的决策依据和数据分析
└── 数据来源（可折叠）
    ├── 用户资料
    ├── 运动目标
    ├── 健康数据
    ├── 心率区间
    └── 知识库检索结果
```

## 使用场景

### 1. 开发调试
- 验证数据流是否正确
- 检查知识库检索结果
- 观察心率区间计算逻辑

### 2. 用户信任
- 展示 AI 使用了哪些数据
- 说明建议的科学依据
- 增强对系统的信心

### 3. 参数调优
- 观察不同参数对结果的影响
- 优化知识库检索策略
- 改进算法逻辑

## 待完成功能

### 运动后分析页面 Debug 模式
由于运动详情页面较复杂，建议采用类似的实现方式：

1. 在运动详情弹窗中添加 Debug 开关
2. 在科学分析按钮旁边添加 "Debug 分析" 按钮
3. 展示运动后分析的 Debug 信息：
   - 运动数据获取
   - 心率区间分布分析
   - 训练强度评估
   - 知识库检索
   - 恢复建议生成

## 部署状态

- ✅ 后端 API 已部署（支持 debug 参数）
- ✅ 前端运动前指导页面已更新
- ⏳ 前端运动后分析页面待更新
- ⏳ 小程序端待更新

## 测试方法

1. 访问 https://health.westwetlandtech.com/workout-guidance
2. 勾选 "Debug 模式" 复选框
3. 点击 "获取运动前指导"
4. 查看紫色的 "AI 决策过程" 面板
5. 点击 "点击查看详细数据来源" 展开 JSON 数据

## 相关文件

- `frontend/src/app/workout-guidance/page.tsx` - 运动前指导页面
- `frontend/src/services/api.ts` - API 服务
- `backend/app/api/workout.py` - 后端 API 接口
- `backend/app/services/pre_workout_guidance.py` - 运动前指导服务
- `backend/app/services/post_workout_analysis.py` - 运动后分析服务
