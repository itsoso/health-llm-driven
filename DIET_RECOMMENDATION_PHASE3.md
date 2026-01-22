# 智能饮食推荐系统 Phase 3 - 知识增强 (RAG)

## 🎉 Phase 3 完成

Phase 3 通过整合 RAG（Retrieval-Augmented Generation）技术，为推荐系统添加了专业的营养学知识支持，让每一条推荐都有科学依据。

---

## 📚 营养学知识库

### 知识库文件
**位置**: `backend/knowledge/nutrition_knowledge.md`

**大小**: 496 行，涵盖 11 大主题

### 知识库内容

#### 1. 基础代谢率和总能量消耗
- **Mifflin-St Jeor 公式**：最准确的 BMR 计算方法
- **科学依据**：基于 498 名健康成年人的研究（1990年）
- **TDEE 活动系数**：5 个级别，从久坐到极度活动

#### 2. 宏量营养素分配

| 模式 | 蛋白质 | 碳水 | 脂肪 | 科学依据 |
|------|--------|------|------|----------|
| 减重 | 30% | 40% | 30% | 高蛋白保护肌肉量，增加饱腹感 |
| 维持 | 25% | 45% | 30% | 符合中国居民膳食指南 |
| 增重 | 25% | 50% | 25% | 充足碳水促进肌肉合成 |

#### 3. 特殊饮食模式
- **生酮饮食**：5-10% 碳水，70-75% 脂肪
  - 原理：进入酮症状态，燃烧脂肪供能
  - 科学依据：短期（3-6个月）减重效果显著
  - 注意事项：可能出现"生酮流感"，需补充电解质

- **低碳水饮食**：20-30% 碳水
  - 比生酮更易坚持
  - 对减重和血糖控制有效

- **素食饮食**：
  - 蛋白质来源：豆类、豆制品、谷物、坚果
  - 注意事项：补充 B12、铁、锌、钙

#### 4. 慢性病饮食管理

##### 高血压 - DASH 饮食
- **限制钠**：<2000mg/天（理想 <1500mg）
- **增加钾**：3500-5000mg/天（香蕉、土豆、菠菜）
- **增加镁**：400-420mg/天（深绿色蔬菜、坚果）
- **科学依据**：DASH 饮食可降低收缩压 8-14mmHg

##### 糖尿病 - 血糖管理
- **控制总碳水量**：45-60g/餐
- **选择低GI食物**：GI < 55
- **分餐制**：3 正餐 + 2-3 加餐
- **高纤维**：25-30g/天
- **科学依据**：低GI饮食可改善 HbA1c 0.5%

##### 高血脂
- **限制饱和脂肪**：<7% 总热量
- **避免反式脂肪**：0g
- **增加 Omega-3**：深海鱼（三文鱼、鲭鱼）
- **科学依据**：地中海饮食可降低 LDL 胆固醇 10-15%

#### 5. 特定营养素功能

##### 蛋白质
| 食物 | 蛋白质含量 | 生物价值 |
|------|-----------|---------|
| 鸡蛋 | 13g/100g | 100 |
| 鸡胸肉 | 31g/100g | 79 |
| 三文鱼 | 25g/100g | 83 |
| 豆腐 | 8g/100g | 64 |

**每日推荐量**：
- 普通成人：0.8g/kg
- 运动人群：1.2-2.0g/kg
- 老年人：1.0-1.2g/kg

##### 碳水化合物 - GI 值分类
- **低GI (<55)**：燕麦、糙米、豆类、大部分水果
- **中GI (55-70)**：全麦面包、香蕉
- **高GI (>70)**：白米饭、白面包、土豆

##### 脂肪 - 必需脂肪酸
- **Omega-3**：抗炎、心血管保护、大脑健康
  - 来源：深海鱼、亚麻籽、核桃
- **Omega-6**：细胞膜结构
  - 来源：植物油、坚果
- **理想比例**：Omega-6:Omega-3 = 4:1

#### 6. 微量营养素
- **维生素D**：钙吸收、骨骼健康、免疫功能
- **维生素B12**：红细胞生成、神经功能（素食者需补充）
- **维生素C**：抗氧化、免疫、胶原蛋白合成
- **钙**：骨骼健康、肌肉收缩
- **铁**：血红蛋白、氧气运输
- **镁**：能量代谢、肌肉放松、神经功能
- **钾**：血压调节、心脏功能

#### 7. 运动营养

##### 运动前（1-3小时）
- **目标**：提供能量、避免胃部不适
- **推荐**：燕麦粥 + 香蕉、全麦面包 + 花生酱
- **营养比例**：碳水为主（3-4g/kg），低脂肪

##### 运动后（30分钟内）
- **目标**：恢复肌糖原、促进肌肉修复
- **黄金比例**：碳水:蛋白质 = 3:1 或 4:1
- **推荐**：巧克力牛奶、香蕉 + 蛋白粉、鸡胸肉 + 糙米饭
- **科学依据**：运动后 30-60 分钟是"合成代谢窗口"

#### 8. 睡眠与营养

##### 助眠食物
- **色氨酸丰富**：火鸡、鸡肉、香蕉、牛奶、坚果
  - 原理：色氨酸 → 5-羟色胺 → 褪黑素
- **镁丰富**：深绿色蔬菜、南瓜籽、黑巧克力
  - 原理：镁促进 GABA 分泌，帮助放松

##### 避免食物（睡前 4-6 小时）
- **咖啡因**：咖啡、茶、可乐、巧克力（半衰期 5-6 小时）
- **酒精**：虽然助入睡，但破坏深度睡眠
- **高脂肪食物**：消化慢，影响睡眠质量

#### 9. 压力与营养

##### 抗压营养素
- **镁**：调节皮质醇（压力激素）
- **维生素B族**：神经系统健康、能量代谢
- **维生素C**：降低皮质醇水平
- **Omega-3**：抗炎、改善情绪

##### 避免食物
- **高糖食物**：血糖波动加重压力
- **咖啡因过量**：增加焦虑

#### 10. 水分和电解质
- **基础需求**：男性 3.7L/天，女性 2.7L/天
- **运动额外需求**：每小时 500-1000ml
- **脱水影响**：2% 体重流失 → 运动表现下降 10-20%

#### 11. 食物营养成分数据
包含常见食物的详细营养成分表：
- 蛋白质食物（鸡胸肉、三文鱼、鸡蛋、豆腐等）
- 碳水食物（含 GI 值）
- 脂肪食物（含脂肪类型）
- 蔬菜

---

## 🧠 RAG 知识检索集成

### 智能查询逻辑

系统会根据用户的个人状态，自动构建相关查询：

```python
# 1. 体重目标
if weight_goal == 'lose':
    query_parts.append("减重期间的营养素分配比例和科学依据")
elif weight_goal == 'gain':
    query_parts.append("增重增肌期间的营养素分配和科学依据")

# 2. 慢性病
if '高血压' in chronic_conditions:
    query_parts.append("高血压患者的DASH饮食原则")
if '糖尿病' in chronic_conditions:
    query_parts.append("糖尿病患者的血糖管理和低GI食物")

# 3. 饮食偏好
if diet_preference == 'vegetarian':
    query_parts.append("素食者的蛋白质来源和营养补充")
elif diet_preference == 'keto':
    query_parts.append("生酮饮食的原理和注意事项")

# 4. 睡眠质量
if sleep_score < 70:
    query_parts.append("助眠食物和睡眠营养")

# 5. 压力水平
if stress_level > 50:
    query_parts.append("抗压力营养素和食物")
```

### 知识提取

从 RAG 检索结果中提取相关段落：
- 优先查找包含所有关键词的段落
- 如果没有，返回包含任一关键词的段落
- 限制长度为 500 字符，保持可读性

---

## 📊 API 响应增强

### 新增字段：scientific_insights

```json
{
  "scientific_insights": {
    "available": true,
    "bmr_tdee_explanation": "Mifflin-St Jeor 公式说明...",
    "macronutrient_rationale": "减重模式营养素分配依据...",
    "diet_mode_guidance": "生酮饮食原理和注意事项...",
    "chronic_disease_guidance": [
      {
        "condition": "高血压",
        "guidance": "DASH 饮食原则..."
      }
    ],
    "sleep_nutrition": "助眠食物和色氨酸原理...",
    "stress_nutrition": "抗压营养素和镁的作用...",
    "references": ["nutrition_knowledge.md"]
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| available | boolean | 知识是否成功检索 |
| bmr_tdee_explanation | string | BMR/TDEE 计算原理 |
| macronutrient_rationale | string | 营养素分配的科学依据 |
| diet_mode_guidance | string | 饮食模式指导（生酮/低碳/素食） |
| chronic_disease_guidance | array | 慢性病饮食管理建议 |
| sleep_nutrition | string | 睡眠营养建议 |
| stress_nutrition | string | 压力营养建议 |
| references | array | 知识来源 |

---

## 🎯 使用场景示例

### 场景 1: 减重用户 + 高血压

**用户状态**：
- 体重目标：减重
- 慢性病：高血压
- 当前体重：85kg
- 目标体重：75kg

**RAG 查询**：
```
减重期间的营养素分配比例和科学依据。
高血压患者的DASH饮食原则。
```

**返回的科学见解**：
```json
{
  "bmr_tdee_explanation": "Mifflin-St Jeor 公式是目前最准确的 BMR 计算方法，基于 1990 年 498 名健康成年人的研究...",
  "macronutrient_rationale": "减重模式：蛋白质 30%（1.8-2.2g/kg）、碳水 40%、脂肪 30%。高蛋白增加饱腹感，保护肌肉量，热效应高...",
  "chronic_disease_guidance": [
    {
      "condition": "高血压",
      "guidance": "DASH 饮食可降低收缩压 8-14mmHg。限制钠 <2000mg/天，增加钾 3500-5000mg/天（香蕉、土豆、菠菜）..."
    }
  ]
}
```

### 场景 2: 素食增肌用户 + 睡眠不佳

**用户状态**：
- 体重目标：增重
- 饮食偏好：素食
- 睡眠评分：65

**RAG 查询**：
```
增重增肌期间的营养素分配和科学依据。
素食者的蛋白质来源和营养补充。
助眠食物和睡眠营养。
```

**返回的科学见解**：
```json
{
  "macronutrient_rationale": "增重模式：蛋白质 25%（1.6-2.0g/kg）、碳水 50%、脂肪 25%。充足碳水（5-7g/kg）支持高强度训练...",
  "diet_mode_guidance": "素食蛋白质来源：豆类（大豆、黑豆、鹰嘴豆）、豆制品（豆腐、豆浆）、谷物（藜麦、燕麦）、坚果。注意补充维生素 B12...",
  "sleep_nutrition": "色氨酸丰富食物：香蕉、牛奶、坚果。原理：色氨酸 → 5-羟色胺 → 褪黑素（睡眠激素）。镁促进 GABA 分泌，帮助放松..."
}
```

### 场景 3: 糖尿病患者 + 压力大

**用户状态**：
- 慢性病：糖尿病
- 压力水平：65

**RAG 查询**：
```
糖尿病患者的血糖管理和低GI食物。
抗压力营养素和食物。
```

**返回的科学见解**：
```json
{
  "chronic_disease_guidance": [
    {
      "condition": "糖尿病",
      "guidance": "控制总碳水量 45-60g/餐，选择低GI食物（<55）：燕麦、糙米、豆类。分餐制：3正餐+2-3加餐。高纤维 25-30g/天..."
    }
  ],
  "stress_nutrition": "镁调节皮质醇（压力激素），来源：深绿色蔬菜、坚果、全谷物。维生素 B 族支持神经系统。Omega-3 抗炎、改善情绪..."
}
```

---

## 🔧 技术实现

### RAG Pipeline 集成

```python
from app.services.rag_pipeline import rag_pipeline

# 调用 RAG 检索
rag_result = rag_pipeline.query(
    query=combined_query,
    knowledge_base_path=self.knowledge_base_path,
    top_k=5
)
```

### 知识提取算法

```python
def _extract_section(self, rag_result: Dict[str, Any], *keywords: str) -> Optional[str]:
    """
    从 RAG 结果中提取包含关键词的段落
    
    1. 优先查找包含所有关键词的段落
    2. 如果没有，返回包含任一关键词的段落
    3. 限制长度为 500 字符
    """
    contexts = rag_result.get('contexts', [])
    
    # 查找包含所有关键词的段落
    for context in contexts:
        text = context.get('text', '')
        if all(keyword in text for keyword in keywords):
            return text[:500] + "..." if len(text) > 500 else text
    
    # 返回包含任一关键词的第一个
    for context in contexts:
        text = context.get('text', '')
        if any(keyword in text for keyword in keywords):
            return text[:500] + "..." if len(text) > 500 else text
    
    return None
```

---

## 📈 Phase 1-3 完整功能

### Phase 1: 基础推荐
- ✅ BMR/TDEE 计算
- ✅ 每日营养目标
- ✅ 今日摄入统计
- ✅ 剩余营养需求

### Phase 2: 智能推荐增强
- ✅ 健康状态整合（睡眠、压力、身体电量）
- ✅ 智能警告系统
- ✅ 个性化健康提示
- ✅ 具体食物推荐（5 大类）
- ✅ 过敏源和慢性病保护

### Phase 3: 知识增强
- ✅ 营养学知识库（11 大主题）
- ✅ RAG 知识检索
- ✅ 科学依据和详细建议
- ✅ 智能查询和知识提取

---

## 🎯 下一步：Phase 4 - 前端展示

### 小程序页面（2-3天）
- [ ] 饮食推荐页面
- [ ] 营养进度可视化
- [ ] 食物推荐列表
- [ ] 健康提示展示
- [ ] 科学见解展示

### Web 页面（2-3天）
- [ ] 饮食推荐页面
- [ ] 更丰富的可视化
- [ ] 交互式食物选择
- [ ] 详细的科学依据展示

---

## 📝 使用建议

### 1. 完善个人资料
- 填写慢性病信息（高血压、糖尿病等）
- 设置过敏源（海鲜、花生、牛奶等）
- 选择饮食偏好（素食、生酮、低碳等）

### 2. 保持数据同步
- 每天同步 Garmin 数据（睡眠、压力、身体电量）
- 及时记录饮食
- 记录运动

### 3. 查看科学见解
- 了解营养素分配的科学依据
- 学习慢性病饮食管理知识
- 根据个人状态调整饮食

### 4. 遵循个性化建议
- 关注警告和提示
- 选择推荐的食物
- 避免过敏源和限制食物

---

## 🔬 科学依据来源

知识库中的所有建议都基于权威研究和指南：

1. **Mifflin MD, et al. (1990)**. A new predictive equation for resting energy expenditure in healthy individuals. *Am J Clin Nutr*.

2. **Phillips SM, Van Loon LJ. (2011)**. Dietary protein for athletes: from requirements to optimum adaptation. *J Sports Sci*.

3. **Appel LJ, et al. (1997)**. A clinical trial of the effects of dietary patterns on blood pressure. DASH Collaborative Research Group. *N Engl J Med*.

4. **American Diabetes Association. (2021)**. Standards of Medical Care in Diabetes.

5. **International Society of Sports Nutrition. (2017)**. Position Stand: Protein and Exercise.

6. **Westerterp-Plantenga MS, et al. (2012)**. Dietary protein - its role in satiety, energetics, weight loss and health. *Br J Nutr*.

---

**Phase 3 已完成！** 🎉

现在系统不仅能提供个性化推荐，还能告诉用户**为什么**这样推荐，让每一条建议都有科学依据！
