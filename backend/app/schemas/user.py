"""用户Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional


class UserCreate(BaseModel):
    """创建用户"""
    name: str
    birth_date: date
    gender: str


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    name: str
    birth_date: date
    gender: str
    
    class Config:
        from_attributes = True

