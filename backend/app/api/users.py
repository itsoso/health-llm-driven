"""用户API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field
from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()


class UpdateNameRequest(BaseModel):
    """更新用户名请求"""
    name: str = Field(..., min_length=1, max_length=50, description="新的用户名/昵称")


class UpdateNameResponse(BaseModel):
    """更新用户名响应"""
    success: bool
    name: str


@router.post("/me/name", response_model=UpdateNameResponse, summary="更新当前用户昵称")
def update_my_name(
    request: UpdateNameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """更新当前登录用户的昵称"""
    current_user.name = request.name
    db.commit()
    return UpdateNameResponse(success=True, name=current_user.name)


@router.post("/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """创建用户"""
    db_user = User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/", response_model=List[UserResponse])
def get_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取用户列表"""
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """获取用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

