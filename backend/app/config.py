"""应用配置"""
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    """应用设置"""
    
    # OpenAI配置
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 代理地址，如: https://api.openai-proxy.com/v1
    openai_model: str = "gpt-4o-mini"  # 默认模型
    
    # Garmin 凭据 (用于后台自动同步)
    garmin_email: Optional[str] = None
    garmin_password: Optional[str] = None

    # Garmin API配置 (OAuth遗留)
    garmin_api_key: Optional[str] = None
    garmin_api_secret: Optional[str] = None

    # 华为 Health Kit 配置
    huawei_client_id: Optional[str] = None
    huawei_client_secret: Optional[str] = None
    
    # 微信小程序配置
    wechat_appid: Optional[str] = None  # 小程序 AppID
    wechat_secret: Optional[str] = None  # 小程序 AppSecret
    
    # OpenClaw 配置 (AI 对话服务)
    openclaw_base_url: str = "https://bot.executor.life/v1"
    openclaw_api_key: Optional[str] = None
    openclaw_model: str = "openclaw:main"

    # 空气质量 API 配置 (https://aqicn.org/data-platform/token/)
    aqicn_api_token: Optional[str] = None  # aqicn.org API Token

    # 和风天气 API 配置 (https://dev.qweather.com/)
    qweather_api_key: Optional[str] = None  # 和风天气 API Key
    qweather_api_type: str = "free"  # free 或 premium

    # 数据库配置
    database_url: str = "sqlite:///./health.db"
    
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
    apns_private_key_path: Optional[str] = None
    apns_bundle_id: str = "life.executor.health"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量


settings = Settings()
