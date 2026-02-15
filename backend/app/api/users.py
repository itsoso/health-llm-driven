"""用户API"""
import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field
from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


class UpdateNameRequest(BaseModel):
    """更新用户名请求"""
    name: str = Field(..., min_length=1, max_length=50, description="新的用户名/昵称")


class UpdateNameResponse(BaseModel):
    """更新用户名响应"""
    success: bool
    name: str


class AvatarResponse(BaseModel):
    """头像上传响应"""
    success: bool
    avatar_url: str = ""


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


@router.post("/me/avatar", response_model=AvatarResponse, summary="上传头像")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """上传并更新当前用户头像"""
    # 检查文件类型
    ext = ""
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片太大，最大5MB")

    # 保存文件
    avatar_dir = os.path.join(UPLOAD_DIR, "avatar")
    os.makedirs(avatar_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{unique_id}.{ext}"
    filepath = os.path.join(avatar_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    avatar_url = f"/api/v1/upload/files/avatar/{filename}"
    current_user.avatar_url = avatar_url
    db.commit()

    logger.info(f"用户 {current_user.id} 上传头像: {filename}")
    return AvatarResponse(success=True, avatar_url=avatar_url)


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

