# 运动指导专业性改进

## 改进内容

### 1. 后端改进 (backend/app/services/pre_workout_guidance.py)

#### 运动类型中文映射
```python
workout_type_map = {
    "RUNNING": "跑步",
    "CARDIO": "心肺训练",
    "WEIGHT_LOSS": "减脂训练",
    "MUSCLE_GAIN": "力量训练",
    "EXERCISE": "有氧运动"
}
```

#### 个性化训练目标描述
根据用户的健康状态生成更精准的建议：

- **睡眠不足** (< 70分): "今日建议进行轻度跑步，睡眠不足时以恢复为主，保持低强度训练。"
- **压力较大** (> 60): "今日建议进行放松性跑步，压力较大时避免高强度，注重身心恢复。"
- **状态良好**: "今日建议进行跑步，保持适当强度，注意心率控制和身体感受。"

### 2. 小程序前端改进

#### 新增工具函数 (packages/mini-program/src/utils/workout.ts)

```typescript
// 运动类型映射
export const WORKOUT_TYPE_MAP: Record<string, string> = {
  'RUNNING': '跑步',
  'CARDIO': '心肺训练',
  'WEIGHT_LOSS': '减脂训练',
  'MUSCLE_GAIN': '力量训练',
  'EXERCISE': '有氧运动'
};

// 运动类型图标
export const WORKOUT_TYPE_ICON: Record<string, string> = {
  'RUNNING': '🏃',
  'CARDIO': '💓',
  'WEIGHT_LOSS': '🔥',
  'MUSCLE_GAIN': '💪',
  'EXERCISE': '🏋️'
};

// 获取完整显示（图标 + 名称）
export function getWorkoutTypeDisplay(type: string): string {
  const icon = getWorkoutTypeIcon(type);
  const name = getWorkoutTypeName(type);
  return `${icon} ${name}`;
}
```

#### 页面标题动态显示

**改进前:**
```
🎯 智能运动指导
基于张展晖课程的科学训练建议
```

**改进后:**
```
🏋️ 有氧运动 智能运动指导
有氧运动训练 · 基于科学训练理论
```

### 3. 显示效果对比

| 运动类型 | 改进前 | 改进后 |
|---------|-------|--------|
| EXERCISE | "今日建议进行EXERCISE训练" | "🏋️ 有氧运动 - 今日建议进行有氧运动" |
| RUNNING | "今日建议进行RUNNING训练" | "🏃 跑步 - 今日建议进行跑步" |
| CARDIO | "今日建议进行CARDIO训练" | "💓 心肺训练 - 今日建议进行心肺训练" |

## 部署状态

- ✅ 后端已部署 (commit: ab5eebd)
- ⏳ 小程序需要重新编译

## 小程序编译说明

1. 在微信开发者工具中打开项目
2. 点击"编译"按钮
3. 测试运动指导功能
4. 确认显示效果符合预期

## 扩展建议

如需添加更多运动类型，只需在以下位置添加映射：

1. **后端**: `backend/app/services/pre_workout_guidance.py` 的 `workout_type_map`
2. **小程序**: `packages/mini-program/src/utils/workout.ts` 的 `WORKOUT_TYPE_MAP` 和 `WORKOUT_TYPE_ICON`

例如添加游泳：
```typescript
'SWIMMING': '游泳',  // 中文名称
'SWIMMING': '🏊',    // 图标
```
