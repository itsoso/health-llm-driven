"""文件上传API"""
import os
import uuid
import logging
import base64
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel

from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()
logger = logging.getLogger(__name__)

# 上传目录配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    url: str = ""
    filename: str = ""
    error: str = ""


class Base64UploadRequest(BaseModel):
    """Base64上传请求"""
    image_base64: str
    image_type: str = "jpeg"
    category: str = "diet"  # 分类: diet, medical, avatar 等


def ensure_upload_dir():
    """确保上传目录存在"""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    # 创建子目录
    for subdir in ["diet", "medical", "avatar", "other"]:
        subpath = os.path.join(UPLOAD_DIR, subdir)
        if not os.path.exists(subpath):
            os.makedirs(subpath)


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def generate_filename(extension: str, category: str = "other") -> str:
    """生成唯一文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return f"{category}/{timestamp}_{unique_id}.{extension}"


@router.post("/image", response_model=UploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    category: str = Form(default="other"),
    current_user: User = Depends(get_current_user_required)
):
    """
    上传图片文件
    
    - **file**: 图片文件
    - **category**: 分类 (diet/medical/avatar/other)
    """
    ensure_upload_dir()
    
    # 检查文件类型
    extension = get_file_extension(file.filename or "")
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {extension}，允许: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # 读取文件内容
    content = await file.read()
    
    # 检查文件大小
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件太大，最大允许 {MAX_FILE_SIZE // 1024 // 1024}MB"
        )
    
    # 生成文件名并保存
    filename = generate_filename(extension, category)
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    # 返回相对URL
    url = f"/api/v1/upload/files/{filename}"
    
    logger.info(f"用户 {current_user.id} 上传图片: {filename}")
    
    return UploadResponse(
        success=True,
        url=url,
        filename=filename
    )


@router.post("/image/base64", response_model=UploadResponse)
async def upload_image_base64(
    request: Base64UploadRequest,
    current_user: User = Depends(get_current_user_required)
):
    """
    上传Base64编码的图片
    
    - **image_base64**: Base64编码的图片数据
    - **image_type**: 图片类型 (jpeg/png/gif/webp)
    - **category**: 分类 (diet/medical/avatar/other)
    """
    ensure_upload_dir()
    
    # 验证图片类型
    image_type = request.image_type.lower()
    if image_type == "jpg":
        image_type = "jpeg"
    
    if image_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片类型: {image_type}"
        )
    
    try:
        # 解码Base64
        # 处理可能的 data URL 前缀
        base64_data = request.image_base64
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        
        image_data = base64.b64decode(base64_data)
        
        # 检查大小
        if len(image_data) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"图片太大，最大允许 {MAX_FILE_SIZE // 1024 // 1024}MB"
            )
        
        # 生成文件名并保存
        filename = generate_filename(image_type, request.category)
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(image_data)
        
        # 返回相对URL
        url = f"/api/v1/upload/files/{filename}"
        
        logger.info(f"用户 {current_user.id} 上传Base64图片: {filename}")
        
        return UploadResponse(
            success=True,
            url=url,
            filename=filename
        )
        
    except Exception as e:
        logger.error(f"Base64图片上传失败: {e}")
        raise HTTPException(status_code=400, detail=f"图片处理失败: {str(e)}")


@router.get("/files/{category}/{filename}")
async def get_uploaded_file(category: str, filename: str):
    """
    获取上传的文件
    """
    filepath = os.path.join(UPLOAD_DIR, category, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 安全检查：确保路径在上传目录内
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(os.path.realpath(UPLOAD_DIR)):
        raise HTTPException(status_code=403, detail="访问被拒绝")
    
    return FileResponse(filepath)
