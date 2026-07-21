"""处方识别 + 原研药查询。

上传处方照片 → vision OCR 提取药品(并规整通用名)→ 逐药查原研药精选表 →
返回结果**供用户确认**(不直接入库;OCR/识别可能出错)。
"""
import base64
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.ai.prescription_ocr import recognize_prescription
from app.services.originator_drugs import _normalize, find_originator
from app.services.originator_recommendations import pending_originator_recs, set_status
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    read_upload_limited,
    validate_image_bytes,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB


def _enrich(items: list[dict]) -> list[dict]:
    """给每个识别出的药附上原研药信息(表外为 None)。"""
    out: list[dict] = []
    for it in items:
        name = it.get("generic_name") or it.get("raw_name") or ""
        orig = find_originator(name)
        out.append({
            "raw_name": it.get("raw_name"),
            "generic_name": it.get("generic_name"),
            "dosage": it.get("dosage"),
            "frequency": it.get("frequency"),
            "originator": orig,  # {generic, brand, manufacturer} 或 None
            "has_originator": orig is not None,
        })
    return out


@router.post("/recognize", summary="处方图片识别 + 原研药查询")
async def recognize_prescription_image(
    file: UploadFile = File(..., description="处方图片 (jpg/png/heic/webp)"),
    current_user: User = Depends(get_current_user_required),
):
    """上传处方照片,返回识别到的药品 + 各自的原研药(供用户确认,不入库)。"""
    filename = (file.filename or "").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("jpg", "jpeg", "png", "heic", "webp"):
        raise HTTPException(status_code=400, detail="请上传图片文件 (jpg/png/heic/webp)")
    image_type = "jpeg" if ext in ("jpg", "jpeg") else ext

    try:
        content = await read_upload_limited(file, max_bytes=MAX_IMAGE_BYTES)
        image_type = validate_image_bytes(content, declared_extension=ext)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail="图片过大,请压缩后重试") from exc
    except UploadContentInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    image_base64 = base64.b64encode(content).decode("ascii")

    logger.info(f"[处方识别] user={current_user.id} 开始 OCR ({len(content)} bytes)")
    result = await recognize_prescription(image_base64, image_type=image_type)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    items = _enrich(result.get("items", []) or [])
    if not items:
        raise HTTPException(status_code=422, detail="未能从图片识别出药品,请换一张更清晰的处方照片")

    matched = sum(1 for it in items if it["has_originator"])
    logger.info(f"[处方识别] user={current_user.id} 识别 {len(items)} 药,命中原研 {matched}")
    return {
        "items": items,
        "matched_originators": matched,
        "note": "OCR 结果可能有误,请核对;原研药仅供参考,具体以药师/医生为准。",
    }


@router.get("/originator", summary="按药名查原研药(单条)")
async def lookup_originator(
    name: str,
    current_user: User = Depends(get_current_user_required),
):
    """给一个药名(通用名/品牌/含规格),查其原研药;表外返回 has_originator=false。"""
    orig = find_originator(name)
    return {"query": name, "originator": orig, "has_originator": orig is not None}


@router.get("/recommendations", summary="基于在用药的原研药可换建议(已采纳/忽略的不返回)")
def get_recommendations(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """对话/客户端共用:用户在用仿制药里有原研药可换、且尚未采纳/忽略的列表。"""
    return {"recommendations": pending_originator_recs(db, current_user.id)}


class RecStatusBody(BaseModel):
    generic_name: str            # 通用名(任意形式,内部规范化)
    status: str                  # adopted=已采纳(系统推荐) / dismissed=不需要 / suggested=重置以重新推荐
    brand: str | None = None
    manufacturer: str | None = None


@router.post("/recommendations/status", summary="采纳/忽略/重置某药的原研药推荐")
def set_recommendation_status(
    body: RecStatusBody,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """采纳后标识为系统推荐 → 后续对话不再二次推荐;dismissed 同样抑制;suggested 可重新推荐。"""
    if body.status not in ("adopted", "dismissed", "suggested"):
        raise HTTPException(status_code=400, detail="status 须为 adopted/dismissed/suggested")
    key = _normalize(body.generic_name)
    if not key:
        raise HTTPException(status_code=400, detail="药名不能为空")
    rec = set_status(db, current_user.id, key, body.status,
                     brand=body.brand, manufacturer=body.manufacturer, source="manual")
    return {"generic_name": rec.generic_name, "status": rec.status}
