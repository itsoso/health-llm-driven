"""应用配置"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用设置"""
    
    # OpenAI配置
    openai_api_key: Optional[str] = None
    
    # Garmin API配置
    garmin_api_key: Optional[str] = None
    garmin_api_secret: Optional[str] = None
    
    # 数据库配置
    database_url: str = "sqlite:///./health.db"
    
    # 应用配置
    app_env: str = "development"
    debug: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

