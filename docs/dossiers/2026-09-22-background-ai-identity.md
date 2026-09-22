# Dossier: 后台 AI 调用身份隔离修复

- 当前阶段：本切片 G3/G4 通过，等待其余待修项统一发布；未 push、未部署。
- 用户需求：在“分析线上日志和用户 prompts”后要求“继续”。
- 基线：`d31ab9cef`，开工时 main 干净，远端已快进同步，已检查开放 PR。
- Run ledger：`docs/_generated/harness-runs/f641b4b5bfad.jsonl`（本地，不提交）。

## Correct Course / 范围

初始 feature 路由包含补剂续问探索。Discovery 确认该功能涉及新确认契约、
同日剂量冲突和 PostgreSQL 幂等约束，不能混入提示词小修。
已询问用户是否采用确认卡；尚未得到选择，不进入该功能实现。
当前切片重新按 `quick_fix --overlay safety` 路由：只修复现有后台生活事件
抽取与洞察调用的身份丢失，不新增产品行为或授权，不自动重试历史任务。
多模型复盘及 SNP 预热另行调查，不声称本切片覆盖全部后台调用。

## 证据与既有契约

- 日志分析窗口为 2026-09-15 14:30 至 09-22 14:30（北京时间）；
  life_event.extractor 的 147 次调用中 141 次失败且缺用户身份，
  insight.llm_pattern_mining 的 21 次调用均缺用户身份而失败。
  这是调用样本，不是全站用户成功率；原始用户 prompts 未导出入库。
- 源码两处 `set_caller` 均未绑定 user_id；生活事件查询已校验消息归属，
  洞察输入查询已按 user_id 隔离。
- 沿用 `docs/specs/active/2026-09-06-third-party-ai-consent.md`：
  当前版本授权、有效账号和已披露目的地仍由实际发送守卫逐次验证。
- 不改 API、schema、模型、prompt、健康写入含义或前端；不授予同意。

## 实现与验证计划

1. RED：真实入口缺用户身份、拒绝/撤回/未知目标零发送、跨用户恢复及异常恢复。
2. 最小实现：可恢复的后台 AI 作用域绑定用户与调用方，清除继承的管理员、
   run、usage capture 状态；作用域在协程内部建立，覆盖 run_async 新线程分支。
3. GREEN：相邻生活事件、洞察、AI consent 和 usage 测试；检查生成物与完整 CI 闸。
4. 本地固定提交后独立 Safety Gate；GO 前不 push/deploy。

## 补剂 Discovery（未实现）

只读 agent `/root/continuation_discovery`：当前相邻追问索引并非可提交草稿；
现有 medication WriteIntent 不能承载补剂类型。需要 flush-only 领域服务、
来源唯一约束、双端卡片和显式确认，且不同同日剂量应停止核对而非默认覆盖。
基线测试 42 passed / 11 PostgreSQL-only skipped，不代表新功能通过。

## Gate 记录

- RED：新测试在修改业务代码前为 26 failed / 7 passed（包含 6 个被导入的
  既有测试；已改别名避免重复收集）。缺用户身份和作用域缺失均真实失败。
  日志 `/tmp/reva-background-ai-red.log`。G3 后续待执行；不以 SQLite 证明生产事务语义。
- 日志隐私 RED：两入口上游异常含合成敏感载荷时 2 failed；改为仅记录异常
  类型并保留原失败语义后通过，不再把异常正文/堆栈复制进普通业务日志。
- G3 增量合跑：CI 环境 `APP_ENV=test DATABASE_URL=sqlite:///:memory:
  TZ=Asia/Shanghai`，新测试 + life_events / insight_generator / ai_consent /
  llm_usage_tracker / llm_budget_guard 共 115 passed / 2 PostgreSQL-only skipped；
  `/tmp/reva-background-ai-integration.log`。
- G3 PostgreSQL 17 临时独占测试库：background_ai_identity / life_events /
  insight_generator / ai_consent 共 86 passed，零 skip；
  `/tmp/reva-background-ai-postgres.log`。没有读取/更改生产记录或同意状态。
- System Map、mobile-nav、doc-drift、git diff --check 通过；密钥扫描通过。
- LLM change gate 命中调用层；首次 live 运行因本地未配置模型凭据失败，
  不视为通过。仅将已有本地配置的 TokenPlan 凭据读入评测进程内存，
  使用合成用户和内存测试库重跑，不加载该文件的数据库或生产配置。
- 配置后 live 重跑 exit 0：invariants 12/12，health_agent_core 50/50，
  orchestrator 5/5（平均评分 0.96）；轨迹契约 12/12、goldens 9/9。
  `/tmp/reva-background-ai-live-configured.log`。内存评测库未创建 usage 表，
  有旁路统计/测试环境 quota 警告；不以此证明生产计费写入或额度库可用。
  生产额度语义由既有 budget 测试覆盖，真实环境仍需发布后验证。
- G4 第一轮：`/root/background_ai_safety` 对固定提交 `92af066de` 裁定
  **NO-GO**。run_async 的 running-loop 线程分支不复制 ContextVar，导致
  `_cookie_subject_missing=True` 丢失，恢复 owner 后可能跳过 409 会话守卫。
- 整改 RED：真实 insight 入口 + running loop + cookie subject missing
  复现 1 failed / 2 passed，`/tmp/reva-background-ai-cookie-red.log`。
  在线程桥使用 copy_context 传递上下文，不修改 consent 守卫或伪造会话。
  新增同步/运行中 loop 两分支的上下文传递与异常不泄漏测试。
- 整改 G3：全增量 CI-mode 合跑 122 passed / 2 PostgreSQL-only skipped，
  `/tmp/reva-background-ai-integration-v2.log`；PostgreSQL 93 passed / 0 skipped，
  `/tmp/reva-background-ai-postgres-v2.log`；live 再跑 5/5，离线 62/62，
  轨迹 21/21，`/tmp/reva-background-ai-live-v2.log`；全部真实 exit 0。
  独占临时 PG 实例已停止，保留其合成测试目录便于审计；无生产数据。
- G4 第二轮：独立 reviewer `/root/background_ai_safety_rereview` 审查
  `2abbae299` 相对 `d31ab9cef` 的累计固定 diff，裁决 **GO**。
  原 cookie 守卫阻断已闭合；reviewer 独立复跑上下文/桥接 13 passed、
  实际入口 cookie 组合 4 passed，额外 CancelledError 探针通过。
  该裁决不代表其他入口全部修复或生产上线成功。
- G5/G6：未部署，未验证。

## 下一切片（未完成，不纳入本提交的修复声明）

- `MultiModelAnalyzeClient.analyze` 未接收 user_id，daily insights 与跑后分析
  调用链需要显式传递，并检查错误结果不能被渲染/推送为分析成功。
- `snp_prewarm` 每日 02:30 调 `get_snp_detail`，其模型调用未设置 caller/user；
  与此前 unknown 样本的定时特征吻合，但尚无 trace 证据证明全部样本同源。
  后续需同时核实基因归属、缓存隔离和失败计数，不能只修身份后宣称全部恢复。
- 补剂确认卡：待用户选择；维持“未确认不写、缺单位不猜、历史失败不重放”。
- 遵循用户“全部解决之后再部署和发布”，本切片仅本地保存；未设置远端
  live gate 放行变量，发布前仍需精确 main revision CI 与整体上线验证。

## 继续执行：多模型复盘与 SNP 预热

- 用户再次要求“继续”，基线 `02cb75d77`；工作树干净，本地领先远端三项
  已审提交，fetch 后无新远端提交，开放 PR 未覆盖这两个修复入口。
- Router：implementation + safety；Health Harness 接手续作，复用本 Dossier
  与原 ledger，不建立平行状态。外部 TDD/验证技能未安装，遵循仓库 RED/GREEN。
- T2 主代理：多模型客户端必须显式接收 owner；失败/空输出不得变成成功
  推送或跑后成功响应；保留现有 API failure shape 与推送隐私 backstop。
- T3 `genetic_prewarm_fix`：详情模型调用绑定 owner，检查缓存归属、失败无
  缓存、预热计数与上限；不修改临床提示词/建议语义或数据库结构。
- 两路径都先加失败测试，随后 CI-mode / PostgreSQL / 必要 live / 独立
  固定提交安全复审。补剂确认卡仍是独立产品切片；本次不自动补录历史数据。

### T2/T3 实现与新鲜验证

- 多模型客户端及每日复盘、手动/自动跑后分析均显式传 owner，复用已审
  background_ai_scope；只有 completed 且非空文本能进入保存/成功展示/推送。
  保存失败不报告成功；自动跑后仅跳过已完成且非空的同用户历史分析，
  不因历史失败行阻止当前调用，也不扫描或自动重放历史失败。
- 每日复盘成功/失败/跳过与通知投递结果分开统计；修复真实运动分支引用
  不存在 activity_type 的问题，使用已有 workout_type。
- 自动跑后锁屏文案在截断前经过既有 llm_push_backstop，正文仍在已保存
  的应用内分析中；新增敏感词与良性文案正反例。模型异常正文不返给用户。
- SNP 只读取同用户 profile/variant；无命中不发送不相关健康上下文；协程内
  绑定 owner/caller，保留会话与 consent 守卫。失败尝试受 TOP_N 限制，
  failed / failed_users 可见，不再把 actions=None 当作预热成功。
- 新内部 require_cached 参数仅供预热使用；普通详情 API shape 不变。
  成功预热必须命中有效缓存或 SET 获明确肯定回执；普通读取仍可使用新结果。
  维持原 user+rsid+genotype key/24h TTL 与删除索引，未改临床 prompt。
- 补 Redis 工具日志隐私：连接 URL、key、pattern、异常正文均不再输出，
  避免 SNP genotype/密码进日志；SET 不再把否定回执当成功。
- RED：多模型 17 failed；投递状态 2 failed；SNP 初轮 8 failed/15 passed、
  缓存补充 10 failed/31 passed；Redis 日志与确认 7 failed。
- G3：`/tmp/reva-bg-cont-integration.log`，CI-mode 全增量合跑
  **390 passed / 2 PostgreSQL-only skipped**，exit 0。
- PostgreSQL：独占合成测试库，`/tmp/reva-bg-cont-postgres.log`，
  **109 passed / 0 skipped**，exit 0。无生产数据读写。
- Live：`/tmp/reva-bg-cont-live.log`，离线 62/62、真实模型 5/5、
  轨迹 21/21，exit 0；同前轮内存 usage 表警告边界，不冒充生产计费证明。
- System Map / doc-drift / diff check / secrets scan 均通过。
- G4：独立 `/root/background_remaining_safety` 对固定提交 `d17112ffc`
  相对 `02cb75d77` 的 14 文件裁定 **GO**；身份/额度/consent/缓存/通知与
  失败诚实性未发现范围内阻断。不是生产上线验证。
- 之后仅补四个 authenticated 普通/Siri HTTP 成功失败契约测试；业务源码
  保持受审版本不变，`/tmp/reva-multi-api-verification.log` 30 passed。
  最终 CI-mode 全增量重跑 `/tmp/reva-bg-cont-integration-final.log`：
  **394 passed / 2 PostgreSQL-only skipped**，exit 0。
- 临时 PostgreSQL fast-stop 首次等待超时；随后检查 pg_ctl 无运行实例、
  端口无响应、日志记录正常 shutdown，确认已停止（不是强制杀进程）。
- 对外 API 路由与 schema、Mobile/Web 类型、DB schema 均无变化；新增结果
  计数字段仅用于 Celery 内部返回。后端、OTA 均尚未发布。
