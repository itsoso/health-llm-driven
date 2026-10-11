# 拍照记餐性能：被动分段证据

延续 `docs/dossiers/2026-10-08-diet-vision-latency.md`，不修改性能线程拥有的 benchmark、测试和 dossier。不执行额外真实模型评测；当前阶段为本地实现和验证，未部署。

## 本轮实现

Base64 和 URL 识别共用固定日志格式，记录 provider 等待及 decode_sanitize 两段耗时。异常和取消分别记录 failed/cancelled，原结果、异常传播、consent、模型参数和营养未知值语义保留。日志不含图片、URL、用户标识、识别正文或异常原文。

`scripts/summarize_food_vision_timing.py --log <日志文件> --output <聚合JSON>` 流式读取固定指标，按入口、阶段、状态统计样本数及 P50 / 样本P95 / 样本P99；无事件保留缺失，超过事件预算失败，禁止静默截断。输出不携带源日志载荷。单阶段聚合不能当作同一请求配对或端到端延迟，provider 耗时也不等于纯推理或首token等待；returned 不代表识别成功或已写入。

## 验证与下一步

计时 RED 11 failed 后实现；最终识别输出、未知值、usage/context、取消和日志汇总相关测试74 passed，真实退出码0。日志 `/tmp/reva-food-passive-timing-red.log`、`/tmp/reva-food-passive-timing-final.log`；初次测试未配置本地数据库失败，随后显式隔离SQLite作为纯逻辑单元测试环境，不涉及数据库语义验证。

现有旧样本清单引用的图片不完整；不使用异图或旧报告代替当前同批基线。provider 已通过线程调用，不是事件循环同步阻塞。多图串行仍需先核对同批请求证据和 executor 所有权；暂不改变并发、输出合同、分辨率或模型。本轮没有线上提速百分比。下一步从自然发生且已同意的请求收集指标窗口，并与 API 现有 vision/calibration/draft 分段共同裁决运行优化；无需主动增加真实评测请求。
