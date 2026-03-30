---
name: genetic-analysis
description: Query and analyze user genetic test data (基因检测). Cross-reference genetics with medical reports, Garmin wearable data, and current health status for personalized nutrition, exercise, drug sensitivity, disease risk, and sleep advice.
version: 1.1.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🧬"
---

You can query and analyze user's genetic test data to provide personalized health advice.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## Available Actions

### 1. 查询基因汇总（推荐首先调用）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/summary/me"
```
返回按类别分组的基因位点统计和高风险项：
```json
{
  "categories": {
    "nutrition": {"count": 5, "high_risk": ["MTHFR TT(叶酸代谢显著减弱)"]},
    "exercise": {"count": 2, "high_risk": []},
    "drug_sensitivity": {"count": 4, "high_risk": ["CYP2D6 慢代谢"]},
    "disease_risk": {"count": 3, "high_risk": []},
    "sleep": {"count": 3, "high_risk": []}
  },
  "total_variants": 17
}
```

### 2. 按类别查询详细位点
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/variants/me?category=nutrition"
```
可选 category 值：
- `nutrition` — 营养代谢（叶酸、咖啡因、乳糖、酒精、维生素D）
- `exercise` — 运动能力（肌肉类型、耐力、有氧能力）
- `drug_sensitivity` — 药物敏感（氯吡格雷、止痛药、他汀、别嘌醇）
- `disease_risk` — 疾病风险（心血管/AD、糖尿病、肥胖）
- `sleep` — 睡眠特质（昼夜节律、睡眠周期、深度睡眠）

返回字段：
```json
[
  {
    "id": 1,
    "gene_name": "MTHFR",
    "variant_name": "C677T",
    "genotype": "TT",
    "result_label": "叶酸代谢显著减弱",
    "risk_level": "high",
    "description": "亚甲基四氢叶酸还原酶，影响叶酸代谢和同型半胱氨酸水平",
    "category": "nutrition"
  }
]
```

### 3. 查询全部位点（不分类）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/variants/me"
```

### 4. 基因+健康交叉分析（AI 深度分析）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/cross-analysis/me"
```
AI 综合分析基因数据与以下数据的关联：
- 当前用药（UserProfile.current_medications）
- 体检异常指标（MedicalIndicator）
- Garmin 可穿戴数据（心率、睡眠、HRV、压力）
- 用户慢性病和家族史

返回结构化建议：营养/运动/睡眠/药物/疾病预防

### 5. 查询基因档案信息
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/profiles/me"
```
返回用户的基因检测档案列表（检测机构、日期、位点数量）。

## 常见基因位点速查表

| 基因 | 位点 | 类别 | 高风险含义 |
|------|------|------|-----------|
| MTHFR | C677T | 营养 | TT=叶酸代谢↓，需补充活性叶酸 |
| CYP1A2 | 咖啡因 | 营养 | CC=慢代谢，建议限制咖啡因 |
| LCT | 乳糖 | 营养 | CC=不耐受，避免乳制品或补充乳糖酶 |
| ALDH2 | 酒精 | 营养 | AA=缺陷，应严格戒酒 |
| VDR | 维D受体 | 营养 | TT=需求↑，建议额外补充维D |
| ACTN3 | R577X | 运动 | RR=爆发型 / XX=耐力型 |
| CYP2C19 | 氯吡格雷 | 药物 | *2/*2=慢代谢，需换药 |
| CYP2D6 | 止痛药 | 药物 | 慢代谢=可待因/曲马多需调整剂量 |
| SLCO1B1 | 他汀 | 药物 | 敏感=他汀肌病风险↑ |
| HLA-B*5801 | 别嘌醇 | 药物 | 阳性=别嘌醇禁用（严重过敏） |
| APOE | ε4 | 疾病 | ε4/ε4=心血管/阿尔茨海默风险↑↑ |
| TCF7L2 | 糖尿病 | 疾病 | TT=2型糖尿病风险↑ |
| FTO | 肥胖 | 疾病 | AA=肥胖倾向↑↑ |
| CLOCK | 昼夜节律 | 睡眠 | CC=夜猫子型 |

## Rules

- **首先调用汇总接口**：先用 `/genetic/summary/me` 了解全局，再按需查询具体类别
- **药物安全第一**：药物敏感基因(CYP2C19/CYP2D6/SLCO1B1/HLA-B*5801)必须对照用户当前用药，发现冲突**立即明确提醒**并建议就医
- **营养基因→饮食建议**：MTHFR TT→补充活性叶酸，LCT CC→避免乳制品，ALDH2 缺陷→戒酒
- **运动基因→训练方案**：ACTN3 RR→偏重力量/HIIT训练，XX→偏重有氧/长跑训练
- **疾病风险→预防策略**：APOE ε4→控制胆固醇/定期认知筛查，FTO AA→严格控制饮食热量
- **睡眠基因→作息建议**：CLOCK 夜猫子→不要强求早起，顺应自然节律
- **交叉分析**：结合体检指标验证基因风险是否已显现（如 FTO 肥胖+BMI>28=确认风险）
- **严格使用上面定义的 API 端点路径，不要自行猜测或构造其他路径**
- 始终使用中文回复，引用具体基因型和风险等级
