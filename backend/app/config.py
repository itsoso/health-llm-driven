"""应用配置"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用设置"""
    
    # OpenAI配置
    openai_api_key: Optional[str] = None
    
    # Garmin 凭据 (用于后台自动同步)
    garmin_email: Optional[str] = None
    garmin_password: Optional[str] = None
    
    # Garmin API配置 (OAuth遗留)
    garmin_api_key: Optional[str] = None
    garmin_api_secret: Optional[str] = None
    
    # 数据库配置
    database_url: str = "sqlite:///./health.db"
    
    # 应用配置
    app_env: str = "development"
    debug: bool = True
    
    # JWT密钥（用于用户认证token签名）
    secret_key: str = "your-super-secret-key-change-in-production"
    
    # Garmin凭证加密密钥（用于加密存储的Garmin密码）
    garmin_encryption_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量


settings = Settings()

