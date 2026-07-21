"""文件上传API"""
import os
import uuid
import logging
import base64
from datetime import datetime
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel, Field

from app.models.user import User
from app.api.deps import get_current_user, get_current_user_required
from app.database import get_db
from app.services.private_uploads import (
    PRIVATE_UPLOAD_CATEGORIES,
    build_signed_private_upload_url,
    verify_signed_private_upload_url,
)
from app.utils.image_compression import compress_image, should_compress
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    read_upload_limited,
    validate_image_bytes,
)
from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)

# 上传目录配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_CATEGORIES = {"diet", "medical", "avatar", "other"}
PRIVATE_CATEGORIES = set(PRIVATE_UPLOAD_CATEGORIES) - {"chat"}
PUBLIC_CATEGORIES = {"avatar"}
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
    image_base64: str = Field(..., min_length=1, max_length=14_000_000)
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


def normalize_category(category: str) -> str:
    normalized = str(category or "").strip().lower()
    if normalized not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="不支持的图片分类")
    return normalized


def generate_filename(
    extension: str,
    category: str = "other",
    owner_id: int | None = None,
) -> str:
    """生成唯一文件名"""
    normalized_category = normalize_category(category)
    if normalized_category in PRIVATE_CATEGORIES and owner_id is None:
        raise ValueError("private_upload_owner_required")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    if normalized_category in PRIVATE_CATEGORIES:
        return f"{normalized_category}/{int(owner_id)}/{timestamp}_{unique_id}.{extension}"
    return f"{normalized_category}/{timestamp}_{unique_id}.{extension}"


def _uploaded_file_url(filename: str, category: str, owner_id: int) -> str:
    safe_filename = os.path.basename(filename)
    if category in PRIVATE_CATEGORIES:
        return build_signed_private_upload_url(category, owner_id, safe_filename)
    return f"/api/v1/upload/files/{category}/{safe_filename}"


def validate_image_content(content: bytes) -> None:
    """验证上传内容是否为允许的图片格式（magic number 检测，替代废弃的 imghdr）"""
    header = content[:12]
    is_jpeg = header[:2] == b'\xff\xd8'
    is_png = header[:8] == b'\x89PNG\r\n\x1a\n'
    is_gif = header[:3] in (b'GIF', )
    is_webp = header[:4] == b'RIFF' and header[8:12] == b'WEBP'
    if not (is_jpeg or is_png or is_gif or is_webp):
        raise HTTPException(status_code=400, detail="文件内容不是有效图片")


def _legacy_medical_file_belongs_to_user(
    db: Session,
    user_id: int,
    relative_url: str,
) -> bool:
    from app.models.family_health import MedicalReport

    rows = db.query(MedicalReport.image_urls).filter(
        MedicalReport.user_id == user_id,
    ).all()
    for (raw_urls,) in rows:
        values = raw_urls if isinstance(raw_urls, list) else [raw_urls]
        for value in values:
            if isinstance(value, str) and urlsplit(value).path == relative_url:
                return True
    return False


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
    category = normalize_category(category)

    # 检查文件类型
    extension = get_file_extension(file.filename or "")
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {extension}，允许: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    try:
        content = await read_upload_limited(file, max_bytes=MAX_FILE_SIZE)
        detected_kind = validate_image_bytes(content, declared_extension=extension)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="图片过大") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    extension = detected_kind

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
    filename = generate_filename(extension, category, current_user.id)
    filepath = os.path.join(UPLOAD_DIR, filename)

    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(content)

    # 返回相对URL
    url = _uploaded_file_url(filename, category, current_user.id)

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
    category = normalize_category(request.category)

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

        image_data = base64.b64decode(base64_data, validate=True)

        # 检查大小
        if len(image_data) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"图片太大，最大允许 {MAX_FILE_SIZE // 1024 // 1024}MB"
            )

        image_type = validate_image_bytes(
            image_data,
            declared_extension=image_type,
        )

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
        filename = generate_filename(image_type, category, current_user.id)
        filepath = os.path.join(UPLOAD_DIR, filename)

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(image_data)

        # 返回相对URL
        url = _uploaded_file_url(filename, category, current_user.id)

        logger.info(f"用户 {current_user.id} 上传Base64图片: {filename} (最终大小: {len(image_data) / 1024:.1f}KB)")

        return UploadResponse(
            success=True,
            url=url,
            filename=filename
        )

    except Exception as e:
        logger.error(f"Base64图片上传失败: {e}")
        raise HTTPException(status_code=400, detail=f"图片处理失败: {str(e)}")


@router.get("/files/chat/{owner_id}/{filename}")
async def get_private_chat_image(
    owner_id: int,
    filename: str,
    expires: Optional[int] = Query(default=None),
    signature: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_current_user),
):
    from app.services.chat_utils import verify_signed_chat_image_url

    owner_authenticated = bool(
        current_user
        and current_user.id == owner_id
        and current_user.is_active
        and current_user.is_approved
    )
    capability_authenticated = verify_signed_chat_image_url(
        owner_id, filename, expires, signature,
    )
    if not owner_authenticated and not capability_authenticated:
        status_code = 403 if current_user else 401
        raise HTTPException(status_code=status_code, detail="访问被拒绝")
    owner_root = os.path.realpath(os.path.join(UPLOAD_DIR, "chat", str(owner_id)))
    filepath = os.path.realpath(os.path.join(owner_root, os.path.basename(filename)))
    if not filepath.startswith(f"{owner_root}{os.sep}"):
        raise HTTPException(status_code=403, detail="访问被拒绝")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath)


@router.get("/files/chat/{filename}")
async def get_legacy_private_chat_image(
    filename: str,
    owner_id: Optional[int] = Query(default=None),
    expires: Optional[int] = Query(default=None),
    signature: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Protect legacy chat files by checking ownership through message history."""
    from app.models.agent_conversation import AgentConversation, AgentMessage

    from app.services.chat_utils import verify_signed_chat_image_url

    safe_filename = os.path.basename(filename)
    capability_authenticated = bool(
        owner_id is not None
        and verify_signed_chat_image_url(
            owner_id, safe_filename, expires, signature, legacy=True,
        )
    )
    owner_authenticated = False
    if current_user and current_user.is_active and current_user.is_approved:
        relative_url = f"/api/v1/upload/files/chat/{safe_filename}"
        owner_authenticated = (
            db.query(AgentMessage.id)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(
                AgentConversation.user_id == current_user.id,
                AgentMessage.image_url.contains(relative_url),
            )
            .first()
        ) is not None
    if not owner_authenticated and not capability_authenticated:
        status_code = 404 if current_user else 401
        raise HTTPException(status_code=status_code, detail="文件不存在")
    chat_root = os.path.realpath(os.path.join(UPLOAD_DIR, "chat"))
    filepath = os.path.realpath(os.path.join(chat_root, safe_filename))
    if not filepath.startswith(f"{chat_root}{os.sep}"):
        raise HTTPException(status_code=403, detail="访问被拒绝")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath)


@router.get("/files/{category}/{owner_id}/{filename}")
async def get_private_uploaded_file(
    category: str,
    owner_id: int,
    filename: str,
    expires: Optional[int] = Query(default=None),
    signature: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_current_user),
):
    normalized_category = str(category or "").strip().lower()
    if normalized_category not in PRIVATE_CATEGORIES:
        raise HTTPException(status_code=404, detail="文件不存在")
    owner_authenticated = bool(
        current_user
        and current_user.id == owner_id
        and current_user.is_active
        and current_user.is_approved
    )
    capability_authenticated = verify_signed_private_upload_url(
        normalized_category,
        owner_id,
        filename,
        expires,
        signature,
    )
    if not owner_authenticated and not capability_authenticated:
        status_code = 403 if current_user else 401
        raise HTTPException(status_code=status_code, detail="访问被拒绝")
    owner_root = os.path.realpath(
        os.path.join(UPLOAD_DIR, normalized_category, str(owner_id))
    )
    filepath = os.path.realpath(os.path.join(owner_root, os.path.basename(filename)))
    if not filepath.startswith(f"{owner_root}{os.sep}"):
        raise HTTPException(status_code=403, detail="访问被拒绝")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath)


@router.get("/files/{category}/{filename}")
async def get_uploaded_file(
    category: str,
    filename: str,
    owner_id: Optional[int] = Query(default=None),
    expires: Optional[int] = Query(default=None),
    signature: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取上传的文件。只有头像公开；历史健康图片必须证明 owner。
    """
    if category == "chat":
        raise HTTPException(status_code=403, detail="聊天健康图片需要认证")
    normalized_category = str(category or "").strip().lower()
    if normalized_category in PRIVATE_CATEGORIES:
        safe_filename = os.path.basename(filename)
        capability_authenticated = bool(
            owner_id is not None
            and verify_signed_private_upload_url(
                normalized_category,
                owner_id,
                safe_filename,
                expires,
                signature,
                legacy=True,
            )
        )
        owner_authenticated = False
        if (
            current_user
            and current_user.is_active
            and current_user.is_approved
        ):
            relative_url = (
                f"/api/v1/upload/files/{normalized_category}/{safe_filename}"
            )
            if normalized_category == "diet":
                # Legacy diet paths do not carry an owner id. A DietRecord row
                # alone is not an ownership proof because image_url was
                # historically client writable. Record responses issue a
                # short-lived capability URL for legitimate legacy images.
                owner_authenticated = False
            elif normalized_category == "medical":
                owner_authenticated = _legacy_medical_file_belongs_to_user(
                    db,
                    current_user.id,
                    relative_url,
                )
        if not owner_authenticated and not capability_authenticated:
            status_code = 404 if current_user else 401
            raise HTTPException(status_code=status_code, detail="文件不存在")
    elif normalized_category not in PUBLIC_CATEGORIES:
        raise HTTPException(status_code=404, detail="文件不存在")
    filepath = os.path.join(UPLOAD_DIR, normalized_category, os.path.basename(filename))

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 安全检查：确保路径在上传目录内
    real_path = os.path.realpath(filepath)
    category_root = os.path.realpath(os.path.join(UPLOAD_DIR, normalized_category))
    if not real_path.startswith(f"{category_root}{os.sep}"):
        raise HTTPException(status_code=403, detail="访问被拒绝")

    return FileResponse(filepath)
