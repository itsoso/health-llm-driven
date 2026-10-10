# 餐食草稿热量缺失仍显示高置信

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 展示修复；实际识别缺值原因待请求证据 |

primary controller: health-harness-orchestrator；overlay: safety-gate。

## G1 准入
PASS。用户截图火锅草稿食物列表已识别，热量和宏量值为空，却显示高置信、识别完成。应明确识别食物不等于完成营养估算，不能把缺失当零或用部分热量冒充整餐总值。

## G2 源码定位与范围
PASS（局部展示修复）。food_recognition.sanitize_food_recognition_result 汇总逐项营养：任一食物缺对应营养即返回该总值null，保留缺失语义。agent_executor 映射 total_calories 到草稿 calories；DietDraftCard 的紧凑态固定“识别完成”“营养为估算值”，置信徽章只看识别confidence，因此与空值矛盾。
截图不足以判断是模型缺字段、个别食物份量不明还是其他原因；已请求用户提供本轮run编号，不宣称本餐热量已计算。不得猜测汤底/蘸料实际摄入，不从截图补录健康数据。

## G3 局部实现与验证
先新增/更新两个失败测试再改 UI；无热量时显示“热量待估算”“热量缺失”和“未估出”，提示修正实际食物及份量，可删除未食用部分。保留修正入口、已知宏量值和确认流程，不新增模型调用，不改写入策略。
修改仅 DietDraftCard.tsx、cards/__tests__/registry.test.tsx。现有结构化食物数组测试仅蛋白有值，预期同步改为热量缺失。原有完整热量卡继续显示正常状态。
无请求日志、真实模型或本餐计算结果证据。未提交/部署/OTA、未模拟器视觉验收，遵守统一发布owner冻结。
- 新鲜验证：卡片registry 102通过（/tmp/reva-food-missing-final.log）；识别sanitizer 35通过（/tmp/reva-food-missing-sanitizer.log）；Mobile tsc通过；SystemMap checker通过；diff检查通过。测试不代表用户照片已完成真实模型估算。
- 独立文件预审GO（非固定SHA G4）：缺失不伪造零或高置信、完整值分支保持、修正入口可用、计算/写入未改。建议后续补零热量与auto_save_fallback+null边界断言，非阻断。源码hash 78362ace8423294908060632e87e72bd49962d439a62bb6743e9272211bfc19e。
