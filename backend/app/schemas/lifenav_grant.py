"""The first release shares only the generic navigation projection."""
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LifeNavGrantCreate(StrictModel):
    recipient_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    redirect_uri: str = Field(max_length=500)
    state: str = Field(min_length=24, max_length=128, pattern=r'^[a-zA-Z0-9_-]+$')
    code_challenge: str = Field(min_length=43, max_length=43, pattern=r'^[a-zA-Z0-9_-]+$')
    scope: Literal['navigation:generic'] = 'navigation:generic'
    window_policy: Literal['current_trailing7'] = 'current_trailing7'
    expires_in_days: int = Field(default=7, ge=1, le=7)

    @field_validator('redirect_uri')
    @classmethod
    def fixed_https_callback(cls, value):
        url = urlsplit(value)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError('需要固定 HTTPS 回调地址')
        return value


class LifeNavGrantView(StrictModel):
    grant_id: str
    recipient_id: str
    scope: Literal['navigation:generic'] = 'navigation:generic'
    window_policy: Literal['current_trailing7'] = 'current_trailing7'
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    connected: bool


class LifeNavGrantCreated(StrictModel):
    grant_id: str
    authorization_url: str
    expires_at: datetime


class LifeNavCodeExchange(StrictModel):
    client_id: str = Field(min_length=1, max_length=100)
    client_secret: SecretStr = Field(min_length=16, max_length=256)
    code: SecretStr = Field(min_length=32, max_length=128)
    redirect_uri: str = Field(max_length=500)
    state: str = Field(min_length=24, max_length=128)
    code_verifier: SecretStr = Field(min_length=43, max_length=128)


class LifeNavToken(StrictModel):
    access_token: str
    token_type: Literal['Bearer'] = 'Bearer'
    expires_at: datetime
