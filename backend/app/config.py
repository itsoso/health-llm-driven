"""应用配置"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional, List


class Settings(BaseSettings):
    """应用设置"""

    # === Sentry 错误监控（可选）===
    sentry_dsn: Optional[str] = None
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.05  # 性能采样 5%，控制额度

    # === LLM 成本告警 ===
    llm_daily_cost_alert_usd: float = 1.0  # 24h LLM 成本超过此值就 log warning
    llm_cost_usd_to_cny: float = 7.2  # 端上/看板把按量美元估算换算成人民币展示
    llm_model_pricing_json: Optional[str] = None  # 可覆盖模型价格: {"qwen3.7-plus":[0.4,1.2]} ($/1M input/output)
    tokenplan_plan_name: str = "TokenPlan 698/月"
    tokenplan_monthly_budget_cny: float = 698.0  # 阿里云百炼 TokenPlan 固定月费
    tokenplan_monthly_credits: int = 100_000  # 高级坐席月度 Credits 容量
    tokenplan_credits_per_cny: float = 100.0  # 官方示例口径:按量价值 ¥1 约对应 100 Credits
    tokenplan_model_pricing_cny_json: Optional[str] = None  # 覆盖公开人民币单价:{"model":[input,output]}
    tokenplan_monthly_token_quota: int = 0  # 0=未知;配置后 Admin 才能做额度阈值预警
    # 备用模型可能产生额外费用；必须显式开启且指定模型，默认关闭。
    llm_auto_recovery_enabled: bool = False
    llm_recovery_model_id: Optional[str] = None

    # === LLM Provider 统一配置 ===
    llm_provider: str = "tokenplan"  # tokenplan (默认, 阿里云 MiniMax) | openai | ollama
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "qwen3-vl-flash"
    agent_model: Optional[str] = None  # Hermes Agent 专用模型（默认复用 llm_model）
    agent_base_url: Optional[str] = None  # Agent 专用 LLM 端点
    agent_api_key: Optional[str] = None  # Agent 专用 API Key
    llm_vision_api_key: Optional[str] = None  # 独立 Vision API key（如 DashScope）
    llm_vision_base_url: Optional[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # === TTS (阿里云 DashScope CosyVoice) ===
    tts_provider: str = "dashscope"  # dashscope | disabled
    tts_api_key: Optional[str] = None  # DashScope API key; 空则复用 llm_vision_api_key
    # cosyvoice 模型: v2 (官方音色) / v3.5-plus (声音复刻 voice_id).
    # 实际用哪个由 voice_id 前缀决定 (见 cosyvoice.py _resolve_model), 这里只是默认 fallback.
    tts_model: str = "cosyvoice-v2"
    tts_default_voice: str = "longjiayi_v2"  # 柔软港普女声; 若有复刻音色 id, 用 tts_cloned_voice_id 覆盖
    # 用户自有的声音复刻 voice_id (target_model=cosyvoice-v3.5-plus). 例:
    # cosyvoice-v3.5-plus-bailian-7290fdddcd0c4437a10f0b4ec35453d8
    tts_cloned_voice_id: Optional[str] = None
    tts_cache_dir: str = "/tmp/tts_cache"
    tts_cache_enabled: bool = True

    # Ollama 本地模型配置
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # OpenAI配置
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 代理地址，如: https://api.openai-proxy.com/v1
    openai_model: str = "gpt-4o-mini"  # 默认模型

    # 语音识别:短按住说话优先走国内 DashScope,失败再回退 OpenAI Whisper。
    asr_dashscope_model: str = "qwen3-asr-flash"
    asr_dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    asr_realtime_model: str = "qwen3-asr-flash-realtime"
    asr_realtime_base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    asr_realtime_connect_timeout_seconds: float = 8.0
    asr_realtime_final_timeout_seconds: float = 15.0
    asr_openai_model: str = "whisper-1"
    asr_openai_fallback_enabled: bool = False
    asr_provider_timeout_seconds: float = 12.0
    asr_total_timeout_seconds: float = 25.0

    # 阿里云 TokenPlan (兼容 OpenAI 协议) — 国内直连低延迟, 套餐固定成本
    # 模型选项见 app/services/llm/model_registry.py，例如:
    # qwen3.8-max-preview / qwen3.7-plus / deepseek-v4-pro / glm-5.2 / MiniMax-M2.5
    tokenplan_api_key: Optional[str] = None
    tokenplan_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    tokenplan_model: str = "MiniMax-M2.5"

    # Wan / Model Studio AIGC: must be a pay-as-you-go Model Studio key. It is
    # deliberately separate from Token Plan because the latter is text-only and
    # may not be used from a custom application backend.
    dashscope_aigc_api_key: Optional[str] = None
    dashscope_aigc_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_aigc_image_model: str = "wan2.7-image"
    dashscope_aigc_text_to_video_model: str = "wan2.7-t2v-2026-06-12"
    dashscope_aigc_image_to_video_model: str = "wan2.7-i2v-2026-04-25"
    dashscope_aigc_source_url_ttl_seconds: int = 600
    # AIGC is billable and its task API is account-scoped. These limits are
    # enforced at provider dispatch, not merely surfaced in a client UI.
    dashscope_aigc_max_active_jobs_per_user: int = 2
    dashscope_aigc_max_active_jobs_global: int = 20
    dashscope_aigc_max_dispatches_per_user_per_day: int = 5
    dashscope_aigc_poll_min_interval_seconds: int = 6
    # DashScope task polling is account-scoped. Serialize poll leases through
    # PostgreSQL and leave at least this much spacing between any two calls.
    dashscope_aigc_global_poll_min_interval_seconds: int = 1

    # 月之暗面 Kimi (兼容 OpenAI 协议)
    moonshot_api_key: Optional[str] = None
    moonshot_base_url: str = "https://api.moonshot.cn/v1"

    # 智谱 GLM (兼容 OpenAI 协议)
    zhipu_api_key: Optional[str] = None
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # LangBridge Gateway (browser-llm-orchestrator 暴露的 OpenAI 兼容代理)
    # 让 health 透明使用 Claude/GPT/Gemini 等商用模型, 含 vision 能力.
    # base_url 形如 https://base.executor.life/api/llm , 不带 /chat/completions.
    langbridge_gateway_base_url: Optional[str] = None
    langbridge_gateway_api_key: Optional[str] = None

    # Garmin 凭据 (用于后台自动同步)
    garmin_email: Optional[str] = None
    garmin_password: Optional[str] = None

    # Garmin API配置 (OAuth遗留)
    garmin_api_key: Optional[str] = None
    garmin_api_secret: Optional[str] = None

    # 华为 Health Kit 配置
    huawei_client_id: Optional[str] = None
    huawei_client_secret: Optional[str] = None

    # Withings API 配置
    withings_client_id: Optional[str] = None
    withings_client_secret: Optional[str] = None

    # 微信小程序配置
    wechat_appid: Optional[str] = None  # 小程序 AppID
    wechat_secret: Optional[str] = None  # 小程序 AppSecret

    # 站点 URL（用于生成分享链接、Webhook 回调、Siri 快捷指令等）
    site_base_url: str = ""
    health_api_base_url: str = ""

    # 空气质量 API 配置 (https://aqicn.org/data-platform/token/)
    aqicn_api_token: Optional[str] = None  # aqicn.org API Token

    # 阿里云智能搜索 (夸克搜索 / IQS) 配置
    aliyun_access_key_id: Optional[str] = None
    aliyun_access_key_secret: Optional[str] = None
    # IQS 实时搜索 grounding 开关 — 合成回答前检索实时证据注入 prompt 降幻觉。
    # 默认关; 灰度验证后在 prod .env 置 true。需 aliyun_access_key_* 同时配好才生效。
    aliyun_iqs_grounding_enabled: bool = False

    # 和风天气 API 配置 (https://dev.qweather.com/)
    qweather_api_key: Optional[str] = None  # 和风天气 API Key
    qweather_api_type: str = "free"  # free 或 premium
    qweather_api_host: Optional[str] = None  # 自定义API Host (如: your-host.qweatherapi.com)

    # 数据库配置
    database_url: str = "postgresql://localhost/health_db"

    # PostgreSQL配置（可选，优先于sqlite）
    postgres_host: Optional[str] = None
    postgres_port: int = 5432
    postgres_db: str = "health_db"
    postgres_user: str = "health_user"
    postgres_password: Optional[str] = None

    # Redis配置
    redis_url: str = "redis://localhost:6379/0"

    # 微信小程序推送配置
    wechat_mini_app_id: Optional[str] = None
    wechat_mini_app_secret: Optional[str] = None

    # iOS APNs 推送配置
    apns_key_id: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_key_path: Optional[str] = None
    apns_private_key_path: Optional[str] = None  # alias for apns_key_path
    apns_bundle_id: str = "life.executor.health"
    apns_use_sandbox: bool = False  # 开发机走 sandbox；TestFlight/Release 走 production (False)

    # Telegram 推送配置（Agent Native 告警通道）
    telegram_bot_token: Optional[str] = None
    telegram_alert_chat_id: Optional[str] = None  # 默认告警推送的 chat_id
    # 国内服务器连不到 api.telegram.org 时二选一填 (都不填则直连):
    telegram_api_base: Optional[str] = None  # 反代 URL, 如 https://bot.executor.life/telegram-api
    telegram_proxy_url: Optional[str] = None  # HTTP/SOCKS5 代理, 如 http://127.0.0.1:7890

    # SMTP 邮件推送 (Doctor Weekly 优先通道, 阿里云 DirectMail / Resend / 通用 SMTP)
    smtp_host: Optional[str] = None                  # smtpdm.aliyun.com
    smtp_port: int = 465
    smtp_user: Optional[str] = None                  # noreply@executor.life
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None                  # 显示的发件人 (可省, 默认 smtp_user)
    smtp_use_ssl: bool = True
    smtp_timeout: int = 15

    # 外部指令通道 (Telegram) — 用户自己 / 家人 / 健康教练 在 chat 写硬性指令
    # 不涉及医生角色, 不主张医疗权威性. 系统只把指令存到 user_directives 表,
    # specialist 评估时按 source 区分严重度.
    telegram_advisor_chat_id: Optional[str] = None  # 在哪个 chat 接收指令
    telegram_advisor_user_id: Optional[int] = None  # 指令应用到哪个 User.id
    telegram_webhook_secret: Optional[str] = None
    # 历史字段名 (向后兼容, 不再推荐使用)
    telegram_doctor_chat_id: Optional[str] = None
    telegram_doctor_user_id: Optional[int] = None

    @property
    def effective_database_url(self) -> str:
        """获取实际使用的数据库URL"""
        if self.postgres_host and self.postgres_password:
            return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        return self.database_url

    # 应用配置
    app_env: str = "development"
    debug: bool = False

    # JWT密钥（用于用户认证token签名）
    secret_key: str = ""

    # Garmin凭证加密密钥（用于加密存储的Garmin密码）
    garmin_encryption_key: Optional[str] = None

    # 设备凭证加密密钥（用于统一设备凭证加密）
    device_encryption_key: Optional[str] = None

    # P2 RecoveryCoach: 用 hrv_readings 时序做 baseline (vs 旧的 hrv_latest/hrv_7d_avg)
    recovery_hrv_use_timeseries: bool = True

    # Agent Native 化(RFC 方向一 Phase A): 把 specialist 暴露为 Agent 可自主调用的工具。
    # 默认 False=行为与现状一致(specialist 仍由 orchestrator 编排); 开启进入灰度。
    agent_specialist_tools: bool = False
    # Write 自治层(Enter-key thesis 首切片): allowlist 仅 measurement_prompt 这类良性可逆非医疗写
    # 在 gate 全过(非 CRITICAL + 未超每日上限)时无需人确认自动执行。默认 True;一键关回全人确认。
    write_autonomy_enabled: bool = True
    # 主动触达全局打扰预算:每用户每周跨所有 *_watch 主动推送上限(0=不限)
    proactive_weekly_budget: int = 1
    # R15 三级通知预算:P0 必响应(处方药/复查当天/异常血压)周上限;全局周上限(跨所有 tier)
    proactive_p0_weekly_budget: int = 3
    proactive_global_weekly_budget: int = 15
    # R4 主动触达统一 Gatekeeper(每类每日预算)。off=零行为(默认,ships-OFF);
    # observe=算+记 would_drop 决策日志不实际拦(投递逐字节不变);enforce=超预算非 critical 才丢。
    # CRITICAL/safety 类别恒 bypass。翻 observe→enforce 需 founder 看两周日志后决定。
    notification_gatekeeper_mode: str = "off"
    # 任务分级模型路由(成本/延迟):开后按 task_tier 选模型;默认关=零行为变更
    task_tiered_routing: bool = False
    # R5 分析轮只读工具子集(token 优化,fast 子集的对称补全)。开后纯分析/知识轮首轮
    # 只发只读工具;模型要写→withheld-upgrade 升级回全集重跑。默认关=逐字节现状。
    analysis_turn_tool_subset: bool = False
    # XiaoBa Agent Kernel: shadow keeps decisions observable but does not block;
    # enforce blocks policy-denied write tools at the single execution choke point.
    agent_kernel_policy_mode: str = "enforce"
    # Agent Runtime P0 control plane. off=仅贯通 canonical Run identity,不写新表;
    # enforce=写 Run Ledger 并阻止同一会话的不同 active turn 并发执行。
    # 严格本地 iPhone 执行不调用云端 Agent API,因此不会创建服务端 Run。
    agent_runtime_mode: str = "off"
    # Runtime P2 worker control. These values are used only in enforce mode.
    agent_runtime_lease_seconds: int = 90
    agent_runtime_heartbeat_seconds: int = 20
    agent_runtime_deadline_seconds: int = 300
    agent_runtime_unleased_grace_seconds: int = 420
    agent_runtime_stream_queue_max_chunks: int = 128
    # GenUI metric_table 卡片(延迟, Phase-2 rank1)服务端 kill-switch:关=后端绝不发
    # metric_table 卡片、也不注入 GenUI 正文格式契约(逐字节现状)。**主门是 caps 协商**
    # (客户端声明 genui-table-v1);本 flag 只是无需客户端发版即可服务端全局停用的开关。
    # 默认开:声明了 cap 的客户端才受影响,旧端不声明 → 零行为变更。
    genui_table_enabled: bool = True
    # GenUI diet_daily_summary 结构化卡(汇总类卡结构化 v1)服务端 kill-switch:关=后端绝不
    # 把 health_query(diet) 打成结构化 diet 卡(回退通用 metric_table / 散文)。**主门仍是 caps
    # 协商**(客户端声明 genui-diet-summary-v1);本 flag 是无需客户端发版即可全局停用的开关。
    genui_diet_summary_enabled: bool = True
    # GenUI sleep_summary 结构化卡(汇总类卡族·睡眠)服务端 kill-switch:关=后端绝不把
    # health_query(sleep) 打成结构化睡眠卡(回退通用 metric_table)。**主门仍是 caps 协商**。
    genui_sleep_summary_enabled: bool = True
    # GenUI medication_list 结构化卡(汇总类卡族·用药)服务端 kill-switch:关=后端绝不把
    # health_query(medication) 打成结构化用药卡(回退通用 metric_table / 散文)。
    # **主门仍是 caps 协商**(客户端声明 genui-medication-list-v1)。
    genui_medication_list_enabled: bool = True
    # 并行工具调用(延迟, Phase-2 rank5):开后对**携带 tools 的** chat/chat_stream 请求
    # 传 parallel_tool_calls=true, 让 DashScope 一轮回多个 tool_call(默认每响应只回一个,
    # 而 fast-record prompt 早在索要 "一次性发起多个 tool_call")。多条目 record/query 回合
    # 每折叠一轮省 1.5-3s。ships-OFF: 关=请求 payload 逐字节不变;开=仅当本轮携带 tools 时
    # 才带该参数(无 tools 时带会 SDK 报错)。prod 翻开前先跑真网 eval:
    #   python3 backend/scripts/smoke_fast_tool_model.py --parallel
    llm_parallel_tool_calls: bool = False
    # R2(agent 能力路线图 Wave 1): 高置信记录轮首个工具轮 force tool_choice=health_record
    # + 关思考(两者**必须成对**: 探针实测 TokenPlan qwen 系 thinking 模式下 tool_choice=
    # object/required 400, enable_thinking=false 后 named force 双模型 PASS 且参数合法 ——
    # backend/scripts/probe_tool_choice_strict.py 2026-07-17)。仅对 qwen 系模型生效,
    # 其余 provider 不带该 kwarg = 逐字节不变。治: 弱模型"决定先聊一句不调工具"→ 0 工具
    # 调用落兜底话术。ships-OFF, 翻开前 battery 全绿。
    llm_force_record_tool_choice: bool = False
    # R1(agent 能力路线图 Wave 1): 长对话溢出"截断→摘要"。现状 build_messages(limit=15)
    # 超窗静默丢弃;开后把溢出轮次折叠成一条前情摘要消息(flash 档后台预算, Redis 缓存,
    # 增量折叠;读路径零 LLM)。fail-open: 摘要不可用 = 现状截断。窗口内行为逐字节不变。
    # ships-OFF, 翻开前 battery 全绿 + comparative 无回退。
    llm_history_compaction: bool = False
    history_compaction_model_id: str = "deepseek-v4-flash"
    # 确定性查询直出(延迟, Phase-2 rank2):开后对 fast-route 的**只读**查询回合, 执行完
    # health_query 后若本回合所有工具结果都被 query_readouts 的 top-5 维度格式化器
    # (水/体重/睡眠/步数活动/血压)覆盖, 直接从真实 tool result 渲染人话读数 + break,
    # 跳过强模型合成轮(~10-30s → ~2s)。ships-OFF: 关=逐字节现状; 开=仅在**全覆盖 + 无
    # 安全告警后缀**时短路, 任一未覆盖维度/写工具/安全后缀 → fail-open 回落合成轮。
    # 读数只从真实 tool result 渲染, 绝不编造(query_readouts 不变量, test-enforced)。
    deterministic_query_reply: bool = False
    # 合成轮思考封顶(延迟):>0 时给**合成/答案轮**的 qwen 思考阶段封顶到 N 个 token
    # (仅 ModelEntry.supports_thinking_budget=True 的模型;绝不碰工具决策轮;深度分析/
    # health_analysis 轮 fail-closed 跳过=保留完整思考)。默认 0=关=零行为变更。
    # 医疗正文相关 → ships-disabled,须过评测闸(invariant_judge + cadence family-drift)
    # 才可开。探针实证见 scripts/probe_qwen_thinking_budget.py。
    synthesis_thinking_budget: int = 0
    # 显式上下文缓存(延迟, Phase-2 rank3):开后对 ModelEntry.supports_explicit_cache=True
    # 的 DashScope 模型, 在 messages 的 append-only 边界(system + history_prefix)注入
    # Anthropic 式 cache_control ephemeral 断点。工具决策轮写 ~7.3k-16k token 的 system
    # 缓存、几秒后的合成轮命中 → 跳过整条 system 的 prefill, 合成轮 TTFT 省 1-3s, 缓存
    # 前缀输入成本降 ~90%(命中计 10% 价)。ships-OFF: 关=请求 payload 逐字节不变;开需两侧
    # 同时满足(flag + 该模型探针验证过 cache_control 命中且 usage.cached_tokens 透传)。
    # prod 翻开前先跑真网探针: backend/scripts/probe_explicit_cache.py
    llm_explicit_prompt_cache: bool = False
    # 深分析短路二次合成(计划 rank7):orchestrator 是本回合唯一实质工具、且它已产出过
    # R4/advice_guard 校验的 synthesis 时,可跳过对话 Agent 的第二次强模型合成,直接把
    # 那段 synthesis 透传流式下发(省一整次强模型调用,深分析回合时延 -5~15s)。
    #   'off'    = 默认,零行为变更(ships-off);
    #   'shadow' = 用户可见行为逐字节不变(双合成照跑),但把 would-be passthrough 文本 +
    #              计时落到 assistant message.meta.shadow_passthrough,供离线 pairwise judge;
    #   'on'     = 单工具深分析回合短路二次合成;任何"还需融合其它工具结果(记录/查询/二次
    #              分析)"的回合 fail-closed 保留二次合成(passthrough 仅当 orchestrator 输出
    #              本身即完整答案)。透传文本仍过与二次合成**同一条**出站护栏链
    #              (bracket/xml marker strip + tool-result leak 抑制 + reva-ui strip +
    #              消费层 menu_share 提取 + thinking_steps),降级/兜底路径不逃 R4。
    # 未知值 fail-closed 归一到 'off'(见 agent_executor._resolve_synthesis_passthrough_mode)。
    orchestrator_synthesis_passthrough: str = "off"
    # 深分析内层工具进程内直调(计划 rank8):对话 Agent 的 health_analysis(orchestrator)
    # 工具原本 POST localhost /orchestrator/chat(非流式)拿深分析结果 —— 该 loopback 请求
    # 重入整个 FastAPI 中间件栈,含 main.py 的 60s 请求超时中间件(历史"内层 60s 连杀"故障类
    # 的根)。True = 直接进程内 await run_orchestrator(fresh SessionLocal, user_id 显式传),
    # 绕开 HTTP + 中间件,超时改由 executor 内显式 asyncio.wait_for 接管;结果与旧 HTTP 响应体
    # SHAPE-IDENTICAL(synthesis/intent/used_specialists/findings),上层投影/shadow 捕获零改动。
    # False = 回退旧 localhost HTTP 路径(保留一个 release 后删)。
    orchestrator_in_process: bool = True
    # D1 读拉类工具进程内直调(garmin-sync 治理 Wave 3):agent 读工具原本对每个维度打
    # localhost 回环(settings.health_api_base_url)重入整个 FastAPI 中间件栈,付三重税:
    # 跨-worker 饥饿(/agent 占 worker A,回环读又占一个 slot)+ 内层 60s 中间件连杀
    # (慢读被误杀 504)+ 双鉴权/双 JSON。True = 直接进程内直调 service/repo 读
    # (fresh SessionLocal,user_id 显式传),输出与旧 HTTP 路径**数据等价**(golden-master
    # 钉死,不改变 LLM 所见);False = 回退旧 localhost HTTP 路径(保留一个 release 后删)。
    # **仅覆盖只读工具**;写工具(health_record/health_manage/intervention_cycle 等)绝不
    # 进程内 —— Wave 2 的 per-tool task.cancel() 写取消安全依赖回环提供的独立请求+独立事务
    # 隔离(cancel 只杀客户端协程杀不了已下发事务 → 不撕裂写)。
    reads_in_process: bool = True
    # 深报告并行分专家段落合成(计划 rank11):深分析合成本是一次串行强模型大 decode
    # (单 _call_llm 吃掉全部 specialist findings → p50 30-40s decode)。findings 天然
    # per-specialist,确定性专家层早已并行,只有 LLM 叙事被串行化。改为 asyncio.gather N 个
    # 小强模型段落调用(每段一个专家 finding + twin blob + 仲裁判词 + 严格段落契约),按严重度
    # 确定性拼接(safety first);_safety_wrap/validate_text 套在**拼接整体**上(加层不减层)。
    # 只对"报告形"深分析启用(≥2 substantive findings 且非 lite/siri;SoT-R 教训:对话形会劣化)。
    #   'off'    = 默认,零行为变更(ships-off):run_orchestrator 走 mega-synthesis 逐字节不变;
    #   'shadow' = 用户可见行为逐字节不变(mega 服务用户),但并行分段在后台 bg task 跑,结果 +
    #              计时落 agent_audit_log(action=shadow_parallel_synthesis)供离线 pairwise judge;
    #              shadow 失败/超时绝不影响服务回合(fail-soft),bg 用 fresh SessionLocal;
    #   'on'     = 并行分段结果直接服务用户(仍过与 mega **同一条** _strip_llm_reva_ui +
    #              _safety_wrap 出站护栏,R4 加层不减层)。分段流式是后续 seam(现只出拼接文本)。
    # 未知值 fail-closed 归一到 'off'(见 orchestrator.parallel_synthesis.resolve_mode)。
    orchestrator_parallel_synthesis: str = "off"
    # rank11 分段合成 —— 段落 LLM 调用的思考控制(SHADOW 候选,仅作用于分段路径,MEGA 不受影响)。
    # 深分析分段是**单个确定性 specialist finding 的轻量复述**(≤180字,实质在 finding 里,不在
    # 模型思考里),却每段各付 qwen3.7-max ~20s 静默思考 TTFT。对段落关思考是省 in-call TTFT 的
    # 首选候选。取值:
    #   'off'      = 默认(本候选):段落调用 enable_thinking=false(探针实证 TTFT ~36s→~1.6s);
    #   'budget512'= 段落调用 thinking_budget=512(封顶思考,~11s);
    #   'on'       = 不加思考控制(段落思考照旧,= 存量行为)。
    # 仅作用于 orchestrator._call_llm 的**段落**调用(经 _section_synthesis_ctx),且再经
    # ModelEntry.supports_thinking_budget 门控(仅探针验证过的 qwen 系置 True;非支持模型 → 不加
    # 控制,payload 逐字节不变)。MEGA synthesis 从不带思考控制(那条实验已被服务答案否决)。
    # 未知值 fail-closed 归一到 'on'(= 不改思考,见 parallel_synthesis.resolve_section_thinking)。
    parallel_synthesis_section_thinking: str = "off"
    # 深报告 mega 合成模型覆盖(2026-07-15,D 组换快模型):非空时**仅** run_orchestrator 的
    # 报告 mega 合成(_call_llm(allow_synthesis_override=True))用该 model_id 建 provider,绕过
    # per-user/task_tier。**范围严格限定深报告**——Siri 语音 / 冲突仲裁 / 段落合成 / _stream_llm
    # (web+Siri 流式)都**不受影响**(安全评审要求:覆盖范围与注释一致,不静默扩到未验证产品面)。
    # 真网探针实证:deepseek-v4-flash 合成比 qwen3.7-max 快~2×(40s vs 80s,TTFT 9.5s vs 57s),
    # 硬化合成 prompt(rule5/6)后 R4 剂量 0 句、质量可比。默认空=零变更(存量行为)。
    # 医疗正文来源例外:"医疗正文绝不来自 fast"原是为 qwen3.6-flash 那种垃圾 fast 定的经验护栏;
    # deepseek-v4-flash 是能产高质量+R4干净合成的 fast(评估+安全评审已证),此覆盖是有据的刻意例外。
    # 失败仍走 _call_llm 既有 openai fallback。**注意 R4 承重点**:_safety_wrap 只拦药物处方/调量
    # 术语,**不兜底裸补剂剂量数字**——补剂 R4 靠 rule6 硬化 prompt + 该模型的深报告验证承载,
    # 故任何 prompt/模型变更必须重跑深报告 R4 验证(不能假设确定性层兜底所有剂量)。
    orchestrator_synthesis_model_id: str = ""
    # 多模型 panel(高风险裁决多模型投票):primitive,默认关
    multi_model_panel: bool = False

    # R4 guidance_validator 第三家族:拟处方用药时序措辞软化(「每8小时服用」「建议睡前
    # 使用鼻喷剂」「漏服后6小时补服/超12小时跳过」「第N周停/减药」→ 软化为"遵医嘱/药师/说明书")。
    # ships-disabled: 默认 False=零行为变更(前两家族不受影响)。上线后先在评测臂验证过杀率
    # 再默认开。开关只控制第三家族命中→软化;负向 label-fact/医嘱/否定守卫始终生效(不放宽)。
    med_timing_softening: bool = False

    # P1 数字锚定核验(citation anchor)—— shadow 模式:核验答案里引用的个人数值能否锚定到
    # Twin,结果只进日志 + done.meta(不改写/不拦截答案)。默认 True(它本身就只观测,零行为
    # 变化;enforcement 是二期,等 shadow 数据说话)。关掉 = 连观测都跳过。
    citation_anchor_shadow: bool = True

    # 首页对话起手 chip 的 LLM 润色(rules-cast-facts → LLM rewrites → verify gate)。
    # RULES 仍是唯一事实源;LLM 只改写措辞,确定性 verify gate 拒掉 LLM 编造的内容,
    # 回退到规则模板文本。fail-safe = 规则文本。默认开;一键关回纯规则行为(字节一致)。
    starter_llm_polish_enabled: bool = True
    # 润色用的便宜快模型 id(model_registry): fast 档 + 可靠 + 纯文本, 无 vision 开销。
    starter_llm_polish_model_id: str = "deepseek-v4-flash"

    # 首页 starter chip 答案预生成(rank7 时延路线图)。默认关闭 —— safety-adjacent,
    # 需先 founder/safety 评审再 flip。开时:starters 下发后在响应路径外为 top-N chip
    # 预跑一个 **只读**(禁写工具)回合,把答案存进 Redis;tap 时 message 精确匹配 +
    # signals_hash 新鲜 + 未过期 → 秒回放已存答案(否则 fail-closed 落回实时回合)。
    # 关 = 逐字节现状(不预热、不服务、执行器 read-only 分支不触发)。
    starter_pregen_enabled: bool = False
    # 预生成答案的新鲜窗(秒)。过窗即 fail-closed 落回实时回合。短窗兜住
    # signals_hash 覆盖不到的写(CGM / 用药值变)。默认 15 分钟。
    starter_pregen_ttl_seconds: int = 900
    # 每次 starters 下发最多预热几个 chip(投机 token 上限)。默认 top-2。
    starter_pregen_max_chips: int = 2

    # Batch-1 token-perf(计划 #8):纯抽取/判重类内部 LLM 调用点从默认强模型降档到便宜快
    # 模型(deepseek-v4-flash)。这些调用点输出均为结构化字段/判重裁决,**不生成用户可见医疗
    # 建议正文**,零 R4 风险。每字段独立 env 可覆盖(同名大写)= 可逐点回滚;flash provider
    # 创建失败时经 factory.create_provider_for_extraction fail-soft 退回 get_llm_provider(),
    # 绝不断业务。
    memory_extract_model_id: str = "deepseek-v4-flash"          # conversation_memory_service._extract_with_llm
    dialog_extract_model_id: str = "deepseek-v4-flash"          # memory_dialog_extractor.extract_facts_from_dialog
    directive_parse_model_id: str = "deepseek-v4-flash"         # directive_parser._parse_with_llm
    kb_reconciliation_judge_model_id: str = "deepseek-v4-flash" # kb_reconciliation_judge._default_classifier
    action_card_extract_model_id: str = "deepseek-v4-flash"     # action_card_extractor.extract_from_content

    # Legacy Chroma/RAG 知识库运行时开关。
    # 默认 False: 用户问答与 health agent 只能使用 reviewed System KB。
    # 仅在本地调试旧索引时显式打开。
    legacy_knowledge_runtime_enabled: bool = False

    # dedao-kbase -> Reva System KB draft 同步配置。
    # export URL 是传输通道，不是运行时医疗权威；同步结果始终先进入 draft/review gate。
    dedao_kbase_export_url: Optional[str] = None
    dedao_kbase_release_base_url: Optional[str] = None
    dedao_kbase_release_batch_size: int = 50
    dedao_kbase_auth_token: Optional[str] = None
    dedao_kbase_source_root: str = "/Users/liqiuhua/work/personal/down-dedao"
    dedao_kbase_review_artifact_dir: Optional[str] = None
    system_kb_artifact_dir: Optional[str] = None
    system_kb_pgvector_enabled: bool = True
    system_kb_embedding_api_key: Optional[str] = None
    system_kb_embedding_base_url: Optional[str] = None
    system_kb_embedding_model: str = "text-embedding-3-small"
    system_kb_embedding_dimensions: int = 1536
    system_kb_embedding_batch_size: int = 50

    # 邀请码配置
    default_invite_code: str = "LLM"  # 默认邀请码

    # 手机号一体化登录注册
    auth_phone_code_dev_echo: bool = False  # dev/test 可在响应中回显验证码；生产必须关闭
    auth_phone_code_log_delivery: bool = True  # dev/test 无短信通道时允许写日志投递
    auth_phone_code_ttl_minutes: int = 5
    auth_phone_code_resend_seconds: int = 60
    auth_phone_code_max_attempts: int = 5
    auth_phone_registration_auto_approve: bool = True
    aliyun_sms_access_key_id: Optional[str] = None  # 为空则复用 aliyun_access_key_id
    aliyun_sms_access_key_secret: Optional[str] = None  # 为空则复用 aliyun_access_key_secret
    aliyun_sms_sign_name: Optional[str] = None
    aliyun_sms_template_code: Optional[str] = None
    aliyun_sms_region_id: str = "cn-hangzhou"
    # 号码认证服务「短信认证」(dypnsapi) 免资质通道：个人认证账号可用，
    # 签名/模板只能用控制台赠送值（如 恒创联众 / 100001），仅支持大陆手机号。
    # 与 aliyun_sms_* 企业签名通道并存时，企业签名优先。
    aliyun_pnvs_sign_name: Optional[str] = None
    aliyun_pnvs_template_code: Optional[str] = None

    # CORS 配置，逗号分隔的允许来源列表
    cors_allow_origins: str = ""

    @property
    def cors_allow_origins_list(self) -> List[str]:
        """将 CORS 允许来源解析为列表"""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    def validate_required_security(self) -> None:
        """验证生产环境必须的安全配置"""
        if not self.secret_key or "change-in-production" in self.secret_key:
            raise ValueError("SECRET_KEY must be set to a strong value")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")

        # 生产环境标识按大小写不敏感处理，避免 `PRODUCTION` 绕过安全校验。
        if (self.app_env or "").strip().lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.llm_auto_recovery_enabled and not (self.llm_recovery_model_id or "").strip():
                raise ValueError(
                    "LLM_RECOVERY_MODEL_ID must be explicitly configured when "
                    "LLM_AUTO_RECOVERY_ENABLED is enabled in production"
                )
            if not self.garmin_encryption_key:
                raise ValueError(
                    "GARMIN_ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
            if not self.device_encryption_key:
                raise ValueError(
                    "DEVICE_ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
