"""文件上传API"""
import os
import uuid
import logging
import base64
import imghdr
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel

from app.models.user import User
from app.api.deps import get_current_user_required
from app.utils.image_compression import compress_image, should_compress, get_image_info

router = APIRouter()
logger = logging.getLogger(__name__)

# 上传目录配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
COMPRESSION_THRESHOLD_KB = 500  # 超过500KB自动压缩
COMPRESSION_QUALITY = 85  # 压缩质量
MAX_IMAGE_DIMENSION = 1920  # 最大宽高


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


def validate_image_content(content: bytes) -> None:
    """验证上传内容是否为允许的图片格式"""
    detected = imghdr.what(None, h=content)
    if detected not in {"jpeg", "png", "gif", "webp"}:
        raise HTTPException(status_code=400, detail="文件内容不是有效图片")


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
    
    # 验证图片内容
    validate_image_content(content)
    
    # 获取原始图片信息
    original_size = len(content)
    logger.info(f"原始图片大小: {original_size / 1024:.1f}KB")
    
    # 压缩图片 (如果需要)
    if should_compress(content, COMPRESSION_THRESHOLD_KB):
        logger.info(f"图片超过 {COMPRESSION_THRESHOLD_KB}KB，开始压缩...")
        try:
            compressed_content, detected_format = compress_image(
                content,
                max_width=MAX_IMAGE_DIMENSION,
                max_height=MAX_IMAGE_DIMENSION,
                quality=COMPRESSION_QUALITY,
                output_format=None,  # 保持原格式
                preserve_exif=True
            )
            
            # 使用压缩后的内容
            content = compressed_content
            # 更新扩展名 (如果格式改变)
            if detected_format in ALLOWED_EXTENSIONS:
                extension = detected_format
            
            compressed_size = len(content)
            compression_ratio = (1 - compressed_size / original_size) * 100
            logger.info(
                f"压缩完成: {original_size / 1024:.1f}KB -> {compressed_size / 1024:.1f}KB "
                f"(节省 {compression_ratio:.1f}%)"
            )
        except Exception as e:
            logger.error(f"图片压缩失败，使用原图: {e}")
    else:
        logger.info(f"图片大小 {original_size / 1024:.1f}KB，无需压缩")

    # 生成文件名并保存
    filename = generate_filename(extension, category)
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    # 返回相对URL
    url = f"/api/v1/upload/files/{filename}"
    
    logger.info(f"用户 {current_user.id} 上传图片: {filename} (最终大小: {len(content) / 1024:.1f}KB)")
    
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

        # 验证图片内容
        validate_image_content(image_data)
        
        # 获取原始图片信息
        original_size = len(image_data)
        logger.info(f"Base64图片原始大小: {original_size / 1024:.1f}KB")
        
        # 压缩图片 (如果需要)
        if should_compress(image_data, COMPRESSION_THRESHOLD_KB):
            logger.info(f"图片超过 {COMPRESSION_THRESHOLD_KB}KB，开始压缩...")
            try:
                compressed_data, detected_format = compress_image(
                    image_data,
                    max_width=MAX_IMAGE_DIMENSION,
                    max_height=MAX_IMAGE_DIMENSION,
                    quality=COMPRESSION_QUALITY,
                    output_format=None,
                    preserve_exif=True
                )
                
                # 使用压缩后的内容
                image_data = compressed_data
                # 更新格式
                if detected_format in ALLOWED_EXTENSIONS:
                    image_type = detected_format
                
                compressed_size = len(image_data)
                compression_ratio = (1 - compressed_size / original_size) * 100
                logger.info(
                    f"压缩完成: {original_size / 1024:.1f}KB -> {compressed_size / 1024:.1f}KB "
                    f"(节省 {compression_ratio:.1f}%)"
                )
            except Exception as e:
                logger.error(f"图片压缩失败，使用原图: {e}")
        else:
            logger.info(f"图片大小 {original_size / 1024:.1f}KB，无需压缩")
        
        # 生成文件名并保存
        filename = generate_filename(image_type, request.category)
        filepath = os.path.join(UPLOAD_DIR, filename)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(image_data)
        
        # 返回相对URL
        url = f"/api/v1/upload/files/{filename}"
        
        logger.info(f"用户 {current_user.id} 上传Base64图片: {filename} (最终大小: {len(image_data) / 1024:.1f}KB)")
        
        return UploadResponse(
            success=True,
            url=url,
            filename=filename
        )
        
    except Exception as e:
        logger.error(f"Base64图片上传失败: {e}")
        raise HTTPException(status_code=400, detail=f"图片处理失败: {str(e)}")


@router.get("/files/{category}/{filename}")
async def get_uploaded_file(
    category: str,
    filename: str
):
    """
    获取上传的文件（公开访问，无需认证）
    
    图片文件应该可以公开访问，以便在小程序和网页中显示
    """
    filepath = os.path.join(UPLOAD_DIR, category, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 安全检查：确保路径在上传目录内
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(os.path.realpath(UPLOAD_DIR)):
        raise HTTPException(status_code=403, detail="访问被拒绝")
    
    return FileResponse(filepath)
