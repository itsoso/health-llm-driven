"""
图片压缩工具

支持多种格式的图片压缩,自动优化文件大小
"""
import io
import logging
from typing import Tuple, Optional
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# 压缩配置
DEFAULT_MAX_WIDTH = 1920  # 最大宽度
DEFAULT_MAX_HEIGHT = 1920  # 最大高度
DEFAULT_QUALITY = 85  # JPEG 质量 (1-100)
THUMBNAIL_SIZE = (800, 800)  # 缩略图尺寸
WEBP_QUALITY = 80  # WebP 质量


def compress_image(
    image_data: bytes,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
    quality: int = DEFAULT_QUALITY,
    output_format: Optional[str] = None,
    preserve_exif: bool = True
) -> Tuple[bytes, str]:
    """
    压缩图片

    Args:
        image_data: 原始图片数据
        max_width: 最大宽度
        max_height: 最大高度
        quality: 压缩质量 (1-100)
        output_format: 输出格式 (None=自动, 'JPEG', 'PNG', 'WEBP')
        preserve_exif: 是否保留 EXIF 信息

    Returns:
        (压缩后的图片数据, 图片格式)
    """
    try:
        # 打开图片
        img = Image.open(io.BytesIO(image_data))

        # 记录原始信息
        original_format = img.format or 'JPEG'
        original_size = len(image_data)
        original_dimensions = img.size

        # 自动旋转 (根据 EXIF 信息)
        if preserve_exif:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.warning(f"EXIF 旋转失败: {e}")

        # 转换 RGBA 为 RGB (如果输出为 JPEG)
        target_format = output_format or original_format
        if target_format.upper() == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode not in ('RGB', 'RGBA', 'L'):
            img = img.convert('RGB')

        # 调整尺寸 (保持宽高比)
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            logger.info(f"图片尺寸调整: {original_dimensions} -> {img.size}")

        # 压缩并保存到内存
        output = io.BytesIO()

        if target_format.upper() == 'PNG':
            # PNG 使用优化和压缩
            img.save(output, format='PNG', optimize=True, compress_level=9)
        elif target_format.upper() == 'WEBP':
            # WebP 格式
            img.save(output, format='WEBP', quality=WEBP_QUALITY, method=6)
        else:
            # JPEG 格式 (默认)
            target_format = 'JPEG'
            save_kwargs = {
                'format': 'JPEG',
                'quality': quality,
                'optimize': True,
                'progressive': True  # 渐进式 JPEG
            }

            # 保留 EXIF (如果需要)
            if preserve_exif and hasattr(img, 'info') and 'exif' in img.info:
                save_kwargs['exif'] = img.info['exif']

            img.save(output, **save_kwargs)

        compressed_data = output.getvalue()
        compressed_size = len(compressed_data)

        # 计算压缩率
        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

        logger.info(
            f"图片压缩完成: {original_format} -> {target_format}, "
            f"{original_size / 1024:.1f}KB -> {compressed_size / 1024:.1f}KB "
            f"(压缩率: {compression_ratio:.1f}%)"
        )

        return compressed_data, target_format.lower()

    except Exception as e:
        logger.error(f"图片压缩失败: {e}")
        # 压缩失败时返回原图
        return image_data, 'jpeg'


def create_thumbnail(
    image_data: bytes,
    size: Tuple[int, int] = THUMBNAIL_SIZE,
    quality: int = 80
) -> bytes:
    """
    创建缩略图

    Args:
        image_data: 原始图片数据
        size: 缩略图尺寸 (width, height)
        quality: 压缩质量

    Returns:
        缩略图数据
    """
    try:
        img = Image.open(io.BytesIO(image_data))

        # 自动旋转
        try:
            img = ImageOps.exif_transpose(img)
        except:
            pass

        # 转换模式
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # 创建缩略图
        img.thumbnail(size, Image.Resampling.LANCZOS)

        # 保存
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)

        return output.getvalue()

    except Exception as e:
        logger.error(f"缩略图创建失败: {e}")
        return image_data


def get_image_info(image_data: bytes) -> dict:
    """
    获取图片信息

    Args:
        image_data: 图片数据

    Returns:
        图片信息字典
    """
    try:
        img = Image.open(io.BytesIO(image_data))

        return {
            'format': img.format,
            'mode': img.mode,
            'size': img.size,
            'width': img.width,
            'height': img.height,
            'file_size': len(image_data),
            'has_exif': hasattr(img, 'info') and 'exif' in img.info
        }
    except Exception as e:
        logger.error(f"获取图片信息失败: {e}")
        return {}


def should_compress(image_data: bytes, threshold_kb: int = 500) -> bool:
    """
    判断是否需要压缩

    Args:
        image_data: 图片数据
        threshold_kb: 阈值 (KB)

    Returns:
        是否需要压缩
    """
    size_kb = len(image_data) / 1024
    return size_kb > threshold_kb
