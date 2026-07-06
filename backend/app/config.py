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
    tokenplan_monthly_budget_cny: float = 698.0  # 阿里云百炼 TokenPlan 月套餐成本,用于 Admin 成本摊销
    tokenplan_monthly_token_quota: int = 0  # 0=未知;配置后 Admin 才能做额度阈值预警
    llm_auto_recovery_enabled: bool = True  # quota/rate_limit/timeout/provider_error 自动尝试备用模型
    llm_recovery_model_id: Optional[str] = None  # 为空则按可用模型自动挑选非 TokenPlan/快速可靠模型

    # === LLM Provider 统一配置 ===
    llm_provider: str = "tokenplan"  # tokenplan (默认, 阿里云 MiniMax) | openai | ollama
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "qwen-vl-max"
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

    # 阿里云 TokenPlan (兼容 OpenAI 协议) — 国内直连低延迟, 套餐固定成本
    # 模型选项: qwen3.6-plus / deepseek-v3.2 / glm-5 / MiniMax-M2.5
    tokenplan_api_key: Optional[str] = None
    tokenplan_base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    tokenplan_model: str = "MiniMax-M2.5"

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
    debug: bool = True

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
    # 任务分级模型路由(成本/延迟):开后按 task_tier 选模型;默认关=零行为变更
    task_tiered_routing: bool = False
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

    # Legacy Chroma/RAG 知识库运行时开关。
    # 默认 False: 用户问答与 health agent 只能使用 reviewed System KB。
    # 仅在本地调试旧索引时显式打开。
    legacy_knowledge_runtime_enabled: bool = False

    # dedao-kbase -> Reva System KB draft 同步配置。
    # export URL 是传输通道，不是运行时医疗权威；同步结果始终先进入 draft/review gate。
    dedao_kbase_export_url: Optional[str] = None
    dedao_kbase_evidence_manifest_url: Optional[str] = None
    dedao_kbase_auth_token: Optional[str] = None
    dedao_kbase_source_root: str = "/Users/liqiuhua/work/personal/down-dedao"
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

        # 生产环境必须设置独立的加密密钥
        if self.app_env == "production":
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
