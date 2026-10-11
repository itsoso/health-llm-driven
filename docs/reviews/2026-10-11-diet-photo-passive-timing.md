# 拍照记餐性能：被动分段证据

延续 `docs/dossiers/2026-10-08-diet-vision-latency.md`，不修改性能线程拥有的 benchmark、测试和 dossier。不执行额外真实模型评测；后端计时批次已部署，尚无自然请求计时样本或线上提速结论。

## 本轮实现

Base64 和 URL 识别共用固定日志格式，记录 provider 等待及 decode_sanitize 两段耗时。异常和取消分别记录 failed/cancelled，原结果、异常传播、consent、模型参数和营养未知值语义保留。日志不含图片、URL、用户标识、识别正文或异常原文。

`scripts/summarize_food_vision_timing.py --log <日志文件> --output <聚合JSON>` 流式读取固定指标，按入口、阶段、状态统计样本数及 P50 / 样本P95 / 样本P99；无事件保留缺失，超过事件预算失败，禁止静默截断。输出不携带源日志载荷。单阶段聚合不能当作同一请求配对或端到端延迟，provider 耗时也不等于纯推理或首token等待；returned 不代表识别成功或已写入。

## 验证与下一步

计时 RED 11 failed 后实现；最终识别输出、未知值、usage/context、取消和日志汇总相关测试74 passed，真实退出码0。日志 `/tmp/reva-food-passive-timing-red.log`、`/tmp/reva-food-passive-timing-final.log`；初次测试未配置本地数据库失败，随后显式隔离SQLite作为纯逻辑单元测试环境，不涉及数据库语义验证。

现有旧样本清单引用的图片不完整；不使用异图或旧报告代替当前同批基线。provider 已通过线程调用，不是事件循环同步阻塞。多图串行仍需先核对同批请求证据和 executor 所有权；暂不改变并发、输出合同、分辨率或模型。本轮没有线上提速百分比。下一步从自然发生且已同意的请求收集指标窗口，并与 API 现有 vision/calibration/draft 分段共同裁决运行优化；无需主动增加真实评测请求。

## 独立审查与证据边界

G4 GO：固定代码候选 `1210729227c5f7432101641bd95c776b3bc37e52`，独立74项测试、exit0；日志 `/tmp/reva-food-timing-independent-isolated.log`。独立COVERAGE_FILE隔离了其他session的coverage输出；此前共享coverage冲突证据保留，未作为通过依据。此GO不替代完整CI、部署和线上验收。

只读检索今日北京时间00:00起既有 health-backend journal 的固定 `[diet_photo] recognition completed` 指标，匹配样本0（不是证明没有请求），分位数均null。输出 `/tmp/reva-food-natural-request-baseline.json` 只含聚合指标，没有导出原日志或发起模型请求。合成 NullHandler 下每阶段计时中位开销0.00234ms，不能推导生产日志I/O成本或线上收益；证据 `/tmp/reva-food-passive-timing-overhead.json`。System Map、diff及路径敏感LLM变更闸通过，后者live_required=false。

## 发布交付

发布代码 SHA `fcff574ab0d17a231aaf7c1714a0ab01319dc5a6`。完整CI [38137169736](https://github.com/itsoso/health-llm-driven/actions/runs/38137169736)成功；隔离精确提交的本地CI-mode3579 passed /22 skipped /84 subtests passed，exit0。运行代码独立G4 GO，授权操作流程初审缺历史前置检查的BLOCK已修复并复审GO；三个操作wrapper与完整回执分别保留。

一次后端发布 [38138287518](https://github.com/itsoso/health-llm-driven/actions/runs/38138287518) 与服务端终态均SUCCEEDED。生产HEAD匹配候选、工作树干净，四个服务active，公网健康接口200，业务租约已释放。部署源码和日志汇总脚本均逐字节匹配该SHA。GitHub watch曾出现网络EOF，后续只读查询确认运行成功，没有重跑部署。部署shell finalized计时393秒不代表识别延迟或授权/CI总耗时。

部署后读取最近15分钟日志，固定新指标匹配0条，保留缺失；没有额外模型调用。此轮只有后端改动，无需OTA或TestFlight；原d777的OTA回执仍完整。发布证据 `docs/reviews/2026-10-11-diet-photo-timing-release-receipt.json`。

已安装的采集入口（生产项目根目录，输出仅聚合指标）：

```bash
set -o pipefail
journalctl -u health-backend --since '15 minutes ago' --no-pager -o cat | backend/venv/bin/python scripts/summarize_food_vision_timing.py --log /dev/stdin --output /tmp/reva-food-timing-window.json
```

采集不会发送模型请求；基于自然发生且已有consent的识别调用。provider两种入口各保留returned/failed/cancelled，不能直接把汇总事件数当作成功照片数或聊天轮次数。
