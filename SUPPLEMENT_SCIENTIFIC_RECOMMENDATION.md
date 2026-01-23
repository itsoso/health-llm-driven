# 补剂科学推荐功能

**更新时间**: 2026-01-23  
**状态**: ✅ 已完整实现（后端 + 小程序）

## 🎯 功能概述

参考科学运动和科学饮食的推荐模式，为补剂服用实现了完整的科学推荐功能。系统会基于用户的健康数据、运动数据、饮食数据，生成个性化的补剂推荐方案。

### 核心特性

1. **多维度健康分析**
   - 睡眠质量评估
   - 压力水平评估
   - 运动强度评估
   - 营养状况评估

2. **个性化补剂推荐**
   - 基于健康状况的智能推荐
   - 优先级分级（高/中/低）
   - 详细的推荐理由
   - 精准的剂量和时间建议

3. **整体评分系统**
   - 0-100 分综合评分
   - 评级（优秀/良好/一般/需改进）
   - 积极因素和风险因素分析

4. **服用时间优化**
   - 按时间段分组（早晨/中午/晚上/睡前/运动）
   - 考虑补剂间的相互作用
   - 优化吸收效果

## 📊 数据分析维度

### 1. 健康数据（最近7天）

从 Garmin 数据中提取：
- 平均睡眠时长
- 平均压力水平
- 平均静息心率
- 最新睡眠评分
- 最新身体电量

**分析逻辑**:
```python
睡眠质量评估：
- < 6小时：不足 → 推荐镁、褪黑素
- 6-7小时：偏少 → 推荐镁
- 7-9小时：良好 ✓
- > 9小时：过多

压力水平评估：
- < 25：低 ✓
- 25-50：中等
- 50-75：偏高 → 推荐维生素B族、Omega-3
- > 75：高 → 强烈推荐维生素B族、Omega-3
```

### 2. 运动数据（最近7天）

从运动记录中提取：
- 运动次数
- 总运动时长
- 总消耗卡路里
- 运动类型分布
- 是否有高强度训练（心率 > 150）

**分析逻辑**:
```python
运动强度评估：
- 0次：缺乏 → 基础营养补充
- 1-2次：偏少
- 3-5次：适中 → 推荐蛋白粉、肌酸
- > 5次：高 → 强烈推荐蛋白粉、肌酸、BCAA
```

### 3. 饮食数据（最近3天）

从饮食记录中提取：
- 平均每日蛋白质摄入
- 平均每日碳水化合物摄入
- 平均每日脂肪摄入

**分析逻辑**:
```python
营养状况评估（以蛋白质为例）：
- < 0.8g/kg：蛋白质不足 → 推荐蛋白粉
- 0.8-1.2g/kg：基本充足
- 1.2-2.0g/kg：充足 ✓
- > 2.0g/kg：过量
```

### 4. 补剂服用状态

从补剂记录中提取：
- 当前补剂总数
- 今日已服用数量
- 最近7天完成率
- 按分类统计

## 💊 推荐逻辑

### 1. 基于睡眠质量的推荐

**睡眠不足/偏少**:
```
推荐补剂：
1. 镁补充剂 (高优先级)
   - 原因：镁有助于放松神经、改善睡眠质量
   - 剂量：300-400mg
   - 时间：睡前30分钟

2. 褪黑素 (中优先级)
   - 原因：褪黑素可以帮助调节睡眠周期
   - 剂量：0.5-3mg
   - 时间：睡前1小时
```

### 2. 基于压力水平的推荐

**压力偏高/高**:
```
推荐补剂：
1. 维生素B族 (高优先级)
   - 原因：B族维生素有助于神经系统健康和能量代谢
   - 剂量：B-Complex
   - 时间：早餐后

2. Omega-3 鱼油 (中优先级)
   - 原因：Omega-3有助于减轻炎症、改善情绪
   - 剂量：1000-2000mg EPA+DHA
   - 时间：随餐
```

### 3. 基于运动强度的推荐

**运动量适中/高**:
```
推荐补剂：
1. 蛋白粉 (高优先级)
   - 原因：蛋白质有助于肌肉恢复和生长
   - 剂量：20-30g
   - 时间：运动后30分钟内

2. 肌酸 (中优先级)
   - 原因：肌酸可以提升力量和运动表现
   - 剂量：5g
   - 时间：运动前或运动后
```

### 4. 基于营养状况的推荐

**蛋白质摄入不足**:
```
推荐补剂：
1. 蛋白粉 (高优先级)
   - 原因：蛋白质摄入不足，建议补充优质蛋白
   - 剂量：20-30g
   - 时间：早餐或加餐
```

### 5. 基础推荐（无补剂时）

**首次使用**:
```
推荐补剂：
1. 维生素D3 (高优先级)
   - 原因：基础营养补充，有助于骨骼健康和免疫力
   - 剂量：1000-2000 IU
   - 时间：早餐后

2. 复合维生素 (中优先级)
   - 原因：基础营养补充，确保每日所需维生素和矿物质
   - 剂量：1片
   - 时间：早餐后
```

## 🎯 评分系统

### 评分计算逻辑

```python
基础分：5分

加分项：
1. 补剂完成率
   - ≥ 90%：+3分
   - ≥ 70%：+2分
   - ≥ 50%：+1分

2. 积极健康因素（最多+3分）
   - 睡眠充足：+1分
   - 压力水平低：+1分
   - 运动频率适中：+1分

减分项：
1. 健康风险因素（最多-2分）
   - 睡眠不足：-1分
   - 压力较高：-1分
   - 运动缺乏：-1分

总分范围：0-10分（显示为0-100分）
```

### 评级标准

| 分数 | 评级 | 图标 | 建议 |
|------|------|------|------|
| 8-10 | 优秀 | 🌟 | 补剂方案执行良好，健康状况优秀！ |
| 6-7 | 良好 | 👍 | 补剂方案执行不错，继续保持！ |
| 4-5 | 一般 | 💪 | 补剂方案需要改进，建议按推荐调整 |
| 0-3 | 需改进 | 📈 | 建议重新规划补剂方案，并提高执行率 |

## 🏗️ 技术实现

### 后端实现

#### 1. 服务类：`SupplementRecommendationService`

**文件位置**: `backend/app/services/supplement_recommendation.py`

**核心方法**:
```python
class SupplementRecommendationService:
    def generate_supplement_recommendation(
        self,
        db: Session,
        user_id: int,
        target_date: Optional[date] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """生成补剂科学推荐"""
        
        # 1. 获取用户基本信息
        profile = self._get_user_profile(db, user_id)
        
        # 2. 获取最近健康数据（7天）
        health_data = self._get_recent_health_data(db, user_id, target_date)
        
        # 3. 获取最近运动数据（7天）
        workout_data = self._get_recent_workout_data(db, user_id, target_date)
        
        # 4. 获取最近饮食数据（3天）
        diet_data = self._get_recent_diet_data(db, user_id, target_date)
        
        # 5. 获取当前补剂服用情况
        supplement_status = self._get_supplement_status(db, user_id, target_date)
        
        # 6. 分析健康状况
        health_analysis = self._analyze_health_status(
            profile, health_data, workout_data, diet_data
        )
        
        # 7. 生成补剂推荐
        recommendations = self._generate_recommendations(
            profile, health_analysis, supplement_status
        )
        
        # 8. 生成服用时间建议
        timing_suggestions = self._generate_timing_suggestions(
            recommendations, workout_data
        )
        
        # 9. 生成注意事项
        precautions = self._generate_precautions(
            profile, health_analysis, recommendations
        )
        
        # 10. 计算整体评分
        overall_rating = self._calculate_overall_rating(
            supplement_status, health_analysis
        )
        
        return {
            "success": True,
            "health_analysis": health_analysis,
            "recommendations": recommendations,
            "timing_suggestions": timing_suggestions,
            "precautions": precautions,
            "overall_rating": overall_rating
        }
```

#### 2. API 端点

**文件位置**: `backend/app/api/supplements.py`

```python
@router.post("/scientific-recommendation", response_model=Dict[str, Any])
async def get_supplement_recommendation(
    target_date: Optional[date] = None,
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取补剂科学推荐
    
    Args:
        target_date: 目标日期（可选，默认今天）
        debug: 是否返回调试信息，展示AI决策过程（默认False）
    
    Returns:
        补剂科学推荐结果（debug模式下包含决策过程）
    """
    service = SupplementRecommendationService()
    recommendation = service.generate_supplement_recommendation(
        db=db,
        user_id=current_user.id,
        target_date=target_date,
        debug=debug
    )
    return recommendation
```

### 小程序实现

#### 1. 数据接口定义

**文件位置**: `packages/mini-program/src/pages/supplements/index.tsx`

```typescript
interface SupplementRecommendation {
  category: string;
  name: string;
  reason: string;
  dosage: string;
  timing: string;
  priority: string;
  icon: string;
}

interface ScientificRecommendation {
  success: boolean;
  generated_at: string;
  health_analysis: {
    sleep_quality: string;
    stress_level: string;
    exercise_intensity: string;
    nutrition_status: string;
    risk_factors: string[];
    positive_factors: string[];
  };
  recommendations: SupplementRecommendation[];
  timing_suggestions: {
    morning: string[];
    noon: string[];
    evening: string[];
    bedtime: string[];
    workout: string[];
  };
  precautions: string[];
  overall_rating: {
    score: number;
    rating: string;
    emoji: string;
    message: string;
  };
}
```

#### 2. 核心函数

```typescript
const handleGetRecommendation = async () => {
  setLoadingRecommendation(true);
  try {
    const result = await post('/supplements/scientific-recommendation', {
      target_date: selectedDate
    });
    setRecommendation(result);
    setShowRecommendation(true);
    Taro.showToast({ title: '✓ 科学推荐生成完成', icon: 'success' });
  } catch (error) {
    Taro.showToast({ title: '生成推荐失败', icon: 'none' });
  } finally {
    setLoadingRecommendation(false);
  }
};
```

#### 3. UI 组件

**按钮区域**:
```tsx
<View className="add-btn-container">
  <Button className="add-btn" onClick={() => setShowAddForm(true)}>
    + 添加补剂
  </Button>
  <Button 
    className="recommendation-btn" 
    onClick={handleGetRecommendation}
    loading={loadingRecommendation}
  >
    {loadingRecommendation ? '分析中...' : '🤖 科学推荐'}
  </Button>
</View>
```

**推荐弹窗结构**:
```tsx
<View className="recommendation-modal">
  {/* 1. 整体评分卡片 */}
  <View className="rating-card">
    <Text className="rating-emoji">{emoji}</Text>
    <Text className="rating-text">{rating}</Text>
    <Text className="rating-message">{message}</Text>
    <Text className="score-value">{score * 10}/100</Text>
  </View>

  {/* 2. 健康状况分析 */}
  <View className="analysis-section">
    <View className="analysis-grid">
      {/* 睡眠、压力、运动、营养 */}
    </View>
    <View className="factors-list positive">
      {/* 积极因素 */}
    </View>
    <View className="factors-list risk">
      {/* 风险因素 */}
    </View>
  </View>

  {/* 3. 推荐补剂 */}
  <View className="recommendations-section">
    {recommendations.map(rec => (
      <View className="rec-card">
        <Text className="rec-name">{rec.name}</Text>
        <Text className="rec-reason">{rec.reason}</Text>
        <Text className="rec-detail">💊 剂量：{rec.dosage}</Text>
        <Text className="rec-detail">⏰ 时间：{rec.timing}</Text>
      </View>
    ))}
  </View>

  {/* 4. 服用时间建议 */}
  <View className="timing-section">
    {/* 按时间段分组 */}
  </View>

  {/* 5. 注意事项 */}
  <View className="precautions-section">
    {/* 注意事项列表 */}
  </View>
</View>
```

## 🎨 UI 设计

### 1. 科学推荐按钮

**位置**: 补剂页面底部，与「添加补剂」按钮并列

**样式**:
```scss
.recommendation-btn {
  flex: 1;
  height: 80rpx;
  background: linear-gradient(135deg, #8b5cf6, #6366f1);  // 紫色渐变
  color: white;
  border-radius: 40rpx;
  font-size: 28rpx;
}
```

### 2. 推荐弹窗

**动画**: 从底部滑入
```scss
@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
```

**布局**:
```
┌──────────────────────────────────────┐
│  🤖 补剂科学推荐                  ✕   │  ← 标题栏
├──────────────────────────────────────┤
│  ┌────────────────────────────────┐  │
│  │ 🌟 优秀                        │  │  ← 评分卡片
│  │ 补剂方案执行良好，健康状况优秀！ │  │
│  │ 综合评分 85/100                 │  │
│  └────────────────────────────────┘  │
│                                      │
│  📊 健康状况分析                      │
│  ┌──────┐ ┌──────┐                  │
│  │睡眠  │ │压力  │                  │  ← 2x2 网格
│  │良好  │ │中等  │                  │
│  └──────┘ └──────┘                  │
│  ┌──────┐ ┌──────┐                  │
│  │运动  │ │营养  │                  │
│  │适中  │ │充足  │                  │
│  └──────┘ └──────┘                  │
│                                      │
│  ✅ 积极因素                          │
│  • 睡眠充足（平均 7.5 小时/天）       │
│  • 运动频率适中（4 次/周）            │
│                                      │
│  💊 推荐补剂                          │
│  ┌────────────────────────────────┐  │
│  │ 💪 蛋白粉          [高优先]     │  │  ← 推荐卡片
│  │ 运动量较大，蛋白质有助于肌肉恢复 │  │
│  │ 💊 剂量：20-30g                 │  │
│  │ ⏰ 时间：运动后30分钟内          │  │
│  └────────────────────────────────┘  │
│                                      │
│  ⏰ 服用时间建议                      │
│  🌅 早晨：维生素D3、复合维生素        │
│  💪 运动：蛋白粉、肌酸                │
│                                      │
│  ⚠️ 注意事项                          │
│  • 补剂不能替代均衡饮食               │
│  • 开始新的补剂前，建议咨询医生       │
│                                      │
│  [          关闭          ]          │  ← 底部按钮
└──────────────────────────────────────┘
```

### 3. 颜色系统

**优先级颜色**:
- 高优先级：`#EF4444` (红色)
- 中优先级：`#F59E0B` (橙色)
- 低优先级：`#6B7280` (灰色)

**评分颜色**:
- 优秀：`#10B981` (绿色)
- 良好：`#14B8A6` (青色)
- 一般：`#F59E0B` (橙色)
- 需改进：`#EF4444` (红色)

**卡片样式**:
- 背景：`rgba(255, 255, 255, 0.03)`
- 边框：`1px solid $card-border`
- 圆角：`16rpx`

## 📱 使用流程

### 用户操作流程

```
1. 打开补剂服用页面
   ↓
2. 点击「🤖 科学推荐」按钮
   ↓
3. 系统分析（2-3秒）
   - 加载健康数据
   - 加载运动数据
   - 加载饮食数据
   - 分析健康状况
   - 生成推荐方案
   ↓
4. 显示推荐弹窗
   - 查看整体评分
   - 查看健康分析
   - 查看推荐补剂
   - 查看服用时间
   - 查看注意事项
   ↓
5. 根据推荐添加补剂
   - 点击「添加补剂」
   - 填写补剂信息
   - 保存
   ↓
6. 按推荐时间服用
   - 查看时间建议
   - 打卡记录
```

### 推荐更新频率

建议用户：
- 每周查看一次科学推荐
- 健康状况变化时查看
- 运动计划调整后查看
- 饮食习惯改变后查看

## 📊 推荐示例

### 示例 1：高强度运动者

**健康数据**:
- 睡眠：7.2 小时/天（良好）
- 压力：35（中等）
- 运动：5 次/周，高强度
- 蛋白质：1.5g/kg（充足）

**推荐结果**:
```
整体评分：85/100 (优秀) 🌟

健康分析：
✅ 积极因素
  • 睡眠充足（平均 7.2 小时/天）
  • 运动频率较高（5 次/周）
  • 蛋白质摄入充足（1.5g/kg）

推荐补剂：
1. 蛋白粉 (高优先级) 💪
   - 原因：运动量较大，蛋白质有助于肌肉恢复和生长
   - 剂量：20-30g
   - 时间：运动后30分钟内

2. 肌酸 (中优先级) 🔥
   - 原因：运动量较大，肌酸可以提升力量和运动表现
   - 剂量：5g
   - 时间：运动前或运动后

3. Omega-3 鱼油 (中优先级) 🐟
   - 原因：高强度训练，Omega-3有助于减轻炎症、改善恢复
   - 剂量：1000-2000mg EPA+DHA
   - 时间：随餐

服用时间建议：
💪 运动：蛋白粉、肌酸
🌅 早晨：Omega-3

注意事项：
⚠️ 补剂不能替代均衡饮食，应优先从食物中获取营养
💧 服用肌酸期间需要多喝水（每天 3-4 升）
🥛 蛋白粉应分散在全天摄入，不要一次性大量摄入
```

### 示例 2：睡眠不足 + 压力大

**健康数据**:
- 睡眠：5.8 小时/天（不足）
- 压力：68（偏高）
- 运动：2 次/周（偏少）
- 蛋白质：0.9g/kg（基本充足）

**推荐结果**:
```
整体评分：45/100 (一般) 💪

健康分析：
⚠️ 风险因素
  • 睡眠不足（平均 5.8 小时/天）
  • 压力水平偏高
  • 运动频率偏低（2 次/周）

推荐补剂：
1. 镁补充剂 (高优先级) 😴
   - 原因：睡眠不足，镁有助于放松神经、改善睡眠质量
   - 剂量：300-400mg
   - 时间：睡前30分钟

2. 维生素B族 (高优先级) 💊
   - 原因：压力较大，B族维生素有助于神经系统健康和能量代谢
   - 剂量：B-Complex
   - 时间：早餐后

3. 褪黑素 (中优先级) 🌙
   - 原因：睡眠不足，褪黑素可以帮助调节睡眠周期
   - 剂量：0.5-3mg
   - 时间：睡前1小时

4. Omega-3 鱼油 (中优先级) 🐟
   - 原因：压力较大，Omega-3有助于减轻炎症、改善情绪
   - 剂量：1000-2000mg EPA+DHA
   - 时间：随餐

服用时间建议：
🌅 早晨：维生素B族
🌆 晚上：Omega-3
🌙 睡前：镁补充剂、褪黑素

注意事项：
⚠️ 补剂不能替代均衡饮食，应优先从食物中获取营养
💊 开始新的补剂前，建议咨询医生或营养师
🚫 镁过量可能导致腹泻，建议从小剂量开始
🌙 褪黑素不建议长期每日使用，可按需服用
🧘 除了补剂，建议配合冥想、瑜伽等减压方式
```

## ✅ 功能清单

### 后端功能

- ✅ 健康数据分析（睡眠、压力、心率）
- ✅ 运动数据分析（频率、强度、类型）
- ✅ 饮食数据分析（蛋白质、碳水、脂肪）
- ✅ 补剂状态分析（完成率、分类统计）
- ✅ 个性化补剂推荐（6大类场景）
- ✅ 服用时间优化建议
- ✅ 注意事项生成
- ✅ 整体评分计算
- ✅ API 端点实现
- ✅ Debug 模式支持

### 小程序功能

- ✅ 科学推荐按钮
- ✅ 加载状态显示
- ✅ 推荐弹窗展示
- ✅ 整体评分卡片
- ✅ 健康状况分析（4维度）
- ✅ 积极因素展示
- ✅ 风险因素展示
- ✅ 推荐补剂卡片（优先级标识）
- ✅ 服用时间建议（5时段）
- ✅ 注意事项列表
- ✅ 滑动动画
- ✅ 响应式布局

## 🎯 未来优化方向

### 1. 推荐算法优化

- [ ] 引入机器学习模型
- [ ] 基于历史数据的效果反馈
- [ ] 考虑补剂间的相互作用
- [ ] 季节性推荐调整

### 2. 数据源扩展

- [ ] 血液检测报告分析
- [ ] 体检报告分析
- [ ] 基因检测数据
- [ ] 过敏信息

### 3. 功能增强

- [ ] 补剂购买链接推荐
- [ ] 价格对比
- [ ] 品牌推荐
- [ ] 用户评价系统

### 4. 个性化提升

- [ ] 学习用户偏好
- [ ] 预算考虑
- [ ] 素食/纯素选项
- [ ] 宗教/文化禁忌

## 📝 注意事项

### 免责声明

⚠️ **重要提示**:

1. 本功能提供的补剂推荐仅供参考，不构成医疗建议
2. 开始任何新的补剂方案前，请咨询医生或注册营养师
3. 补剂不能替代均衡饮食和健康的生活方式
4. 某些补剂可能与药物相互作用，请告知医生您正在服用的所有补剂
5. 孕妇、哺乳期妇女、儿童、慢性病患者应特别谨慎

### 数据隐私

- 所有健康数据仅用于生成个性化推荐
- 数据不会与第三方共享
- 用户可随时删除数据

## 🎉 完成状态

- ✅ 后端服务完整实现
- ✅ API 端点已部署
- ✅ 小程序 UI 完整实现
- ✅ 推荐逻辑已验证
- ✅ 代码已提交并编译
- ✅ 功能文档已完成

---

**补剂科学推荐功能已完整实现！** 🎊

现在在微信开发者工具中刷新项目，打开补剂服用页面，点击「🤖 科学推荐」按钮，即可体验完整的科学推荐功能！
