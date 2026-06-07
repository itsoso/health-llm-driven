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

    # === LLM Provider 统一配置 ===
    llm_provider: str = "tokenplan"  # tokenplan (默认, 阿里云 MiniMax) | openclaw | openai | ollama
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "qwen-vl-max"
    agent_model: Optional[str] = None  # Hermes Agent 专用模型（默认复用 llm_model）
    agent_base_url: Optional[str] = None  # Agent 专用 LLM 端点（默认复用 OpenClaw Gateway）
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

    # OpenClaw 多模型分析配置（可选）
    openclaw_analyze_url: Optional[str] = None
    openclaw_analyze_api_key: Optional[str] = None
    openclaw_analyze_user_id: Optional[str] = None

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

    # OpenClaw 配置 (AI 对话服务)
    openclaw_base_url: str = ""
    openclaw_api_key: Optional[str] = None
    openclaw_model: str = "openclaw:main"

    # OpenClaw Gateway
    openclaw_gateway_url: str = ""
    openclaw_runtime_base_dir: str = "/srv/health-platform/tenants"
    assistant_openclaw_allowed_hosts: str = "127.0.0.1,localhost,bot.executor.life"
    assistant_openclaw_health_check_ttl_seconds: int = 60
    openclaw_ssh_host: str = ""
    openclaw_ssh_port: int = 22222

    # 站点 URL（用于生成分享链接、Webhook 回调、Siri 快捷指令等）
    site_base_url: str = ""
    health_api_base_url: str = ""

    # 空气质量 API 配置 (https://aqicn.org/data-platform/token/)
    aqicn_api_token: Optional[str] = None  # aqicn.org API Token

    # 阿里云智能搜索 (夸克搜索) 配置
    aliyun_access_key_id: Optional[str] = None
    aliyun_access_key_secret: Optional[str] = None

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
    # 主动触达全局打扰预算:每用户每周跨所有 *_watch 主动推送上限(0=不限)
    proactive_weekly_budget: int = 1
    # 任务分级模型路由(成本/延迟):开后按 task_tier 选模型;默认关=零行为变更
    task_tiered_routing: bool = False
    # 多模型 panel(高风险裁决多模型投票):primitive,默认关
    multi_model_panel: bool = False

    # 邀请码配置
    default_invite_code: str = "LLM"  # 默认邀请码

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
