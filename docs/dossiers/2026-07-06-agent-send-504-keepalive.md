# Dossier: Agent Send 504 Keepalive Fix

| 字段 | 值 |
|---|---|
| slug | `agent-send-504-keepalive` |
| 创建日期 | 2026-07-06 |
| 当前阶段 | S7 验证 |
| 状态 | implemented-local-gate |
| 负责 | Claude |
| 反馈环 | pytest 回归(秒级) / 生产 eval 单题验收 |

## S0 · 用户需求

> 对比评测实锤:POST /api/v1/agent/send 上,重量级深分析问题(如补剂互作全查、胃溃疡根因多源推理)确定性 504 —— backend/main.py 的 60s 请求超时中间件杀掉长回合。/agent/stream(SSE)不受影响。按方案 A:/agent/send 内部改为消费自家流式管线聚合成完整回复,实现后用评测题 state_supplement_interaction、root_cause_ulcer_etiology 打真实环境验收,写超时回归测试。

## G1 · 准入裁决

- first_class_objects:无新增(纯缺陷修复,复用既有 AgentExecutor 流式管线)
- core_loop_step:对话入口可用性 —— 非流式客户端的深分析回合完整返回
- target_surface / safety_level / autonomy_tier:API(`/agent/send`)/ 无新健康建议面 / 无自治动作
- smallest_end_to_end_slice:单端点保活流式聚合 + 压缩时间尺度回归测试 + 生产两题验收
- 裁决:PASS(bug fix,不引入新一等对象,不触碰安全规则/敏感数据)

## 根因

`main.py` `RequestContextMiddleware` 对非流式路径 `asyncio.wait_for(call_next, 60s)`。
`wait_for` 只计到 **response start**;非流式 JSON 要到回合结束才发 start → 深分析
回合(>60s)确定性 504。且有效超时 = min(服务端, nginx, 客户端),单抬服务端上限
(方案 B)不解决 nginx `proxy_read_timeout` 与客户端 socket idle。

## 修法(方案 A)

`backend/app/api/agent.py` `agent_send`:
- 快窗(`AGENT_SEND_KEEPALIVE_SECONDS`=10s)内完成 → 历史非流式路径,错误保持 4xx/5xx,契约零变化。
- 超窗 → chunked `StreamingResponse`(`application/json` + `X-Accel-Buffering: no`):每 10s 吐一个空格(RFC 8259 合法 JSON 前导空白),同时重置服务端/nginx/客户端三层 idle 计时器;末尾吐完整 JSON 对象。缓冲整 body 再 `json.loads` 的客户端零感知。
- 硬上限 `AGENT_SEND_HARD_CAP_SECONDS`=300s:取消回合 + in-body `error`,fail-loud,不吊死 worker。
- 流开始后(200 已定格)的失败 → `body.error` 字段(形状与成功响应一致)。

配套:
- `run_xiaoba.py` poster 对 `body.error` fail-loud 抛出;加 `--only` 单题过滤(未知 id exit 2)。
- `main.py` 注释钉死:`/agent/send` 别加进 `LONG_REQUEST_PATHS`。

## 客户端受伤面核查(有效超时=min 两端)

| 客户端 | 端点 | 超时语义 | 结论 |
|---|---|---|---|
| eval runner (`run_xiaoba`) | `/agent/send` | urllib socket timeout=120(逐 recv idle) | 保活字节重置,修复覆盖 |
| Siri 意图 | `/agent/stream` + **`/orchestrator/chat`** | URLSession idle 25–30s | `/orchestrator/chat` 未修,**已立独立任务** |
| watch | 快速记录类端点 | — | 不受影响 |
| mac / mobile / web | `/agent/stream`(SSE) | — | 不受影响 |

## 研发任务 / 验证记录

- Run Ledger: `docs/_generated/harness-runs/01888babec83.jsonl`(本地,不提交)
- 回归测试(`backend/tests/test_agent_conversations_api.py`):压缩时间尺度(中间件 1s + 回合 2.5s)断言 200 + 保活前导空白 + 完整 JSON;流后错误 envelope;快窗错误保持 500;硬上限真取消。16/16 绿。
- 假绿排除实证:同一慢回合把保活窗抬到 > 中间件超时(=旧非流式行为)→ 确认 504;证明回归测试的绿来自提前 response start。
- eval poster 单测(`test_comparative_eval.py`):error envelope fail-loud + 成功透传。31/31 绿。
- 生产验收(2026-07-06,deploy 45d24db2,健康度 60/60):
  - `state_supplement_interaction`:**latency 100.5s(>60s),完整 2416 字回答,无 error** —— 修复前该场景确定性 504,实锤生效。
  - `root_cause_ulcer_etiology` 首跑 `IncompleteRead(11 bytes)`:归因为**并发部署**(另一 agent 01:08:53 部署 18b68982,其 restart 01:10:14 SIGKILL 掐断流式中的连接;服务器 reflog + .env mtime + systemd Stopping 时间线铁证),非本修复缺陷。
  - `root_cause_ulcer_etiology` 重跑:**latency 214.6s,响应 start 恰在快窗 10s([SLOW] 10012ms status=200),全程无 504/断流,完整 JSON** —— 传输层通过。但回答内容退化(重复开场白+拒答):内层 executor→localhost `POST /orchestrator/chat` 被 60s 中间件连杀 3 次(01:17:35/01:18:38/01:19:41,orchestrator 实际需 65s+)。**内层 hop 是独立缺陷**,已交由 /orchestrator/chat 保活修复任务(用户已启动的并行 session)。

## 状态更新

- S7 验证完成:传输层 504 修复上线并双题验证;遗留 = `/orchestrator/chat`(Siri 25s idle + executor 内层 hop)在并行 session 修。
