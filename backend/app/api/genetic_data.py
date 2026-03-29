"""基因数据 API — 基因检测档案 + 变异位点管理 + 交叉分析"""
import logging
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models.user import User
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)

router = APIRouter()


# ══════════════════════════════════════════════════════════
# Pydantic Schemas
# ══════════════════════════════════════════════════════════

class ProfileCreateRequest(BaseModel):
    test_provider: str = Field(..., max_length=100, description="检测机构（如华大基因、微基因）")
    test_date: date = Field(..., description="检测日期")
    report_id: Optional[str] = Field(None, max_length=100, description="报告编号")
    notes: Optional[str] = Field(None, description="备注")


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    test_provider: str
    test_date: date
    report_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class VariantCreateRequest(BaseModel):
    profile_id: int = Field(..., description="所属基因档案 ID")
    category: str = Field(..., max_length=50, description="分类: nutrition/exercise/drug_sensitivity/disease_risk/sleep")
    gene_name: str = Field(..., max_length=50, description="基因名称")
    variant_name: Optional[str] = Field(None, max_length=100, description="变异名称")
    genotype: Optional[str] = Field(None, max_length=50, description="基因型")
    result_label: Optional[str] = Field(None, max_length=100, description="结果标签")
    risk_level: str = Field("info", description="风险等级: low/medium/high/info")
    description: Optional[str] = Field(None, description="描述")
    health_implications: Optional[Dict[str, Any]] = Field(None, description="健康影响 JSON")


class VariantBatchCreateRequest(BaseModel):
    variants: List[VariantCreateRequest] = Field(..., min_length=1, description="变异位点列表")


class VariantUpdateRequest(BaseModel):
    category: Optional[str] = Field(None, max_length=50)
    gene_name: Optional[str] = Field(None, max_length=50)
    variant_name: Optional[str] = Field(None, max_length=100)
    genotype: Optional[str] = Field(None, max_length=50)
    result_label: Optional[str] = Field(None, max_length=100)
    risk_level: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = None
    health_implications: Optional[Dict[str, Any]] = None


class VariantResponse(BaseModel):
    id: int
    user_id: int
    profile_id: int
    category: str
    gene_name: str
    variant_name: Optional[str] = None
    genotype: Optional[str] = None
    result_label: Optional[str] = None
    risk_level: str = "info"
    description: Optional[str] = None
    health_implications: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════
# PDF 上传 + AI 自动提取
# ══════════════════════════════════════════════════════════

class GeneticPdfUploadRequest(BaseModel):
    test_provider: str = Field(..., description="检测机构")
    test_date: date = Field(..., description="检测日期")
    pdf_base64: str = Field(..., description="PDF 文件 base64")
    notes: Optional[str] = None


@router.post("/profiles/upload-pdf", summary="上传基因检测 PDF，AI 自动提取基因位点")
def upload_genetic_pdf(
    req: GeneticPdfUploadRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """上传基因检测 PDF 报告，AI 后台异步提取基因位点数据"""
    # 1. 创建档案
    profile = GeneticProfile(
        user_id=current_user.id,
        test_provider=req.test_provider,
        test_date=req.test_date,
        notes=req.notes or "PDF 自动提取",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # 2. 后台提取
    import threading
    threading.Thread(
        target=_extract_genetic_from_pdf,
        args=(profile.id, current_user.id, req.pdf_base64),
        daemon=True,
    ).start()

    return {
        "id": profile.id,
        "status": "processing",
        "message": "PDF 已上传，AI 正在后台提取基因位点...",
    }


def _extract_genetic_from_pdf(profile_id: int, user_id: int, pdf_base64: str):
    """后台线程：PDF → 图片 → LLM 提取基因位点 → 保存"""
    import asyncio
    import json
    import base64
    import re

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # PDF 转图片
        from app.api.family_health import _pdf_to_images_base64
        images = _pdf_to_images_base64(pdf_base64)
        logger.info(f"[基因PDF] profile={profile_id} PDF 转换为 {len(images)} 页")

        all_variants = []

        # 逐页 LLM 提取
        from app.services.llm_provider import get_llm_provider
        import time

        prompt = """请从这份基因检测报告页面中提取所有基因位点信息。

对每个基因位点，返回 JSON 数组：
```json
[
  {
    "category": "nutrition/exercise/drug_sensitivity/disease_risk/sleep/other",
    "gene_name": "基因名称（如 MTHFR）",
    "variant_name": "变异位点（如 C677T）",
    "genotype": "检测结果（如 CT）",
    "result_label": "中文结果描述（如 叶酸代谢轻度减弱）",
    "risk_level": "low/medium/high/info",
    "description": "简短说明"
  }
]
```

category 分类规则：
- nutrition: 营养代谢相关（叶酸、咖啡因、乳糖、酒精、维生素等）
- exercise: 运动能力相关（肌肉类型、耐力、有氧能力等）
- drug_sensitivity: 药物敏感性（药物代谢酶、过敏风险等）
- disease_risk: 疾病风险（心血管、糖尿病、肿瘤等）
- sleep: 睡眠相关（昼夜节律、深度睡眠等）
- other: 其他

如果页面中没有基因位点信息，返回空数组 []。只返回 JSON，不要其他文字。"""

        provider = get_llm_provider()

        for i, img_b64 in enumerate(images):
            try:
                # 压缩图片
                from app.services.openclaw_service import OpenClawService
                compressed = OpenClawService._compress_image_static(img_b64)

                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    provider.chat_with_vision(prompt, compressed, "jpeg")
                )
                loop.close()

                # 解析 JSON
                text = result if isinstance(result, str) else str(result)
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
                if json_match:
                    variants = json.loads(json_match.group())
                    all_variants.extend(variants)
                    logger.info(f"[基因PDF] 第{i+1}页提取到 {len(variants)} 个位点")

                time.sleep(2)  # 限流
            except Exception as e:
                logger.warning(f"[基因PDF] 第{i+1}页提取失败: {e}")
                continue

        # 保存提取的位点
        saved = 0
        for v in all_variants:
            try:
                variant = GeneticVariant(
                    user_id=user_id,
                    profile_id=profile_id,
                    category=v.get("category", "other"),
                    gene_name=v.get("gene_name", ""),
                    variant_name=v.get("variant_name", ""),
                    genotype=v.get("genotype", ""),
                    result_label=v.get("result_label", ""),
                    risk_level=v.get("risk_level", "info"),
                    description=v.get("description", ""),
                )
                db.add(variant)
                saved += 1
            except Exception as e:
                logger.warning(f"[基因PDF] 保存位点失败: {e}")

        # 更新档案备注
        profile = db.query(GeneticProfile).get(profile_id)
        if profile:
            profile.notes = f"PDF 自动提取完成，共 {saved} 个位点"
        db.commit()
        logger.info(f"[基因PDF] profile={profile_id} 完成，提取 {saved} 个位点")

    except Exception as e:
        logger.error(f"[基因PDF] profile={profile_id} 处理失败: {e}", exc_info=True)
        try:
            profile = db.query(GeneticProfile).get(profile_id)
            if profile:
                profile.notes = f"PDF 提取失败: {str(e)[:100]}"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ══════════════════════════════════════════════════════════
# 基因档案 CRUD
# ══════════════════════════════════════════════════════════

@router.post("/profiles", summary="创建基因检测档案")
def create_profile(
    req: ProfileCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = GeneticProfile(
        user_id=current_user.id,
        test_provider=req.test_provider,
        test_date=req.test_date,
        report_id=req.report_id,
        notes=req.notes,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "test_provider": profile.test_provider,
        "test_date": str(profile.test_date),
        "report_id": profile.report_id,
        "notes": profile.notes,
    }


@router.get("/profiles/me", summary="我的基因档案列表")
def list_profiles(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == current_user.id)
        .order_by(desc(GeneticProfile.test_date))
        .all()
    )
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "test_provider": p.test_provider,
            "test_date": str(p.test_date),
            "report_id": p.report_id,
            "notes": p.notes,
            "created_at": str(p.created_at) if p.created_at else None,
        }
        for p in profiles
    ]


@router.get("/profiles/{profile_id}", summary="基因档案详情（含变异位点）")
def get_profile_detail(
    profile_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.id == profile_id, GeneticProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="基因档案不存在")

    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.profile_id == profile.id)
        .order_by(GeneticVariant.category, GeneticVariant.gene_name)
        .all()
    )

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "test_provider": profile.test_provider,
        "test_date": str(profile.test_date),
        "report_id": profile.report_id,
        "notes": profile.notes,
        "created_at": str(profile.created_at) if profile.created_at else None,
        "variants": [
            {
                "id": v.id,
                "category": v.category,
                "gene_name": v.gene_name,
                "variant_name": v.variant_name,
                "genotype": v.genotype,
                "result_label": v.result_label,
                "risk_level": v.risk_level,
                "description": v.description,
                "health_implications": v.health_implications,
            }
            for v in variants
        ],
    }


@router.delete("/profiles/{profile_id}", summary="删除基因档案（级联删除变异位点）")
def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.id == profile_id, GeneticProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="基因档案不存在")

    # 先删除关联的变异位点（SQLite 不支持 ON DELETE CASCADE）
    db.query(GeneticVariant).filter(GeneticVariant.profile_id == profile.id).delete()
    db.delete(profile)
    db.commit()
    return {"message": "已删除", "id": profile_id}


# ══════════════════════════════════════════════════════════
# 变异位点 CRUD
# ══════════════════════════════════════════════════════════

@router.post("/variants/batch", summary="批量创建变异位点")
def batch_create_variants(
    req: VariantBatchCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 验证所有 profile_id 属于当前用户
    profile_ids = set(v.profile_id for v in req.variants)
    valid_profiles = (
        db.query(GeneticProfile.id)
        .filter(GeneticProfile.id.in_(profile_ids), GeneticProfile.user_id == current_user.id)
        .all()
    )
    valid_ids = {p.id for p in valid_profiles}
    invalid_ids = profile_ids - valid_ids
    if invalid_ids:
        raise HTTPException(status_code=404, detail=f"基因档案不存在或无权访问: {invalid_ids}")

    created = []
    for v in req.variants:
        variant = GeneticVariant(
            user_id=current_user.id,
            profile_id=v.profile_id,
            category=v.category,
            gene_name=v.gene_name,
            variant_name=v.variant_name,
            genotype=v.genotype,
            result_label=v.result_label,
            risk_level=v.risk_level,
            description=v.description,
            health_implications=v.health_implications,
        )
        db.add(variant)
        created.append(variant)

    db.commit()
    for v in created:
        db.refresh(v)

    return {
        "created": len(created),
        "ids": [v.id for v in created],
    }


@router.put("/variants/{variant_id}", summary="更新变异位点")
def update_variant(
    variant_id: int,
    req: VariantUpdateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variant = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.id == variant_id, GeneticVariant.user_id == current_user.id)
        .first()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="变异位点不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(variant, key, value)

    db.commit()
    db.refresh(variant)
    return {
        "id": variant.id,
        "category": variant.category,
        "gene_name": variant.gene_name,
        "variant_name": variant.variant_name,
        "genotype": variant.genotype,
        "result_label": variant.result_label,
        "risk_level": variant.risk_level,
        "description": variant.description,
        "health_implications": variant.health_implications,
    }


@router.delete("/variants/{variant_id}", summary="删除变异位点")
def delete_variant(
    variant_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    variant = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.id == variant_id, GeneticVariant.user_id == current_user.id)
        .first()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="变异位点不存在")

    db.delete(variant)
    db.commit()
    return {"message": "已删除", "id": variant_id}


@router.get("/variants/me", summary="我的变异位点列表（可按分类过滤）")
def list_variants(
    category: Optional[str] = Query(None, description="分类过滤: nutrition/exercise/drug_sensitivity/disease_risk/sleep"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(GeneticVariant).filter(GeneticVariant.user_id == current_user.id)
    if category:
        query = query.filter(GeneticVariant.category == category)
    variants = query.order_by(GeneticVariant.category, GeneticVariant.gene_name).all()

    return [
        {
            "id": v.id,
            "profile_id": v.profile_id,
            "category": v.category,
            "gene_name": v.gene_name,
            "variant_name": v.variant_name,
            "genotype": v.genotype,
            "result_label": v.result_label,
            "risk_level": v.risk_level,
            "description": v.description,
            "health_implications": v.health_implications,
        }
        for v in variants
    ]


# ══════════════════════════════════════════════════════════
# 统计摘要
# ══════════════════════════════════════════════════════════

@router.get("/summary/me", summary="基因变异分类统计")
def get_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """按分类统计变异位点数量，并列出高风险项"""
    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.user_id == current_user.id)
        .all()
    )

    categories: Dict[str, Any] = {}
    for v in variants:
        cat = v.category
        if cat not in categories:
            categories[cat] = {"count": 0, "high_risk": []}
        categories[cat]["count"] += 1
        if v.risk_level == "high":
            categories[cat]["high_risk"].append({
                "id": v.id,
                "gene_name": v.gene_name,
                "variant_name": v.variant_name,
                "result_label": v.result_label,
                "description": v.description,
            })

    return {
        "total_variants": len(variants),
        "categories": categories,
    }


# ══════════════════════════════════════════════════════════
# 交叉分析（LLM）
# ══════════════════════════════════════════════════════════

@router.get("/cross-analysis/me", summary="基因 + 健康数据交叉分析")
def get_cross_analysis(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    综合基因变异 + 用户画像（慢性病/用药）+ 最新 Garmin 数据 + 体检指标，
    通过 LLM 生成个性化交叉分析。
    """
    # 1. 获取基因变异
    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.user_id == current_user.id)
        .all()
    )
    if not variants:
        return {
            "status": "no_data",
            "message": "暂无基因数据，请先上传基因检测报告",
            "sections": {},
        }

    # 2. 用户画像
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    # 3. 最新 Garmin 数据
    garmin_summary = _get_latest_garmin_summary(db, current_user.id)

    # 4. 最新异常体检指标
    abnormal_indicators = _get_abnormal_indicators(db, current_user.id)

    # 5. 构建 LLM prompt
    prompt = _build_cross_analysis_prompt(variants, profile, garmin_summary, abnormal_indicators)

    # 6. 调用 LLM
    try:
        from app.services.llm.factory import get_llm_provider
        from app.utils.async_helpers import run_async

        provider = get_llm_provider()
        messages = [
            {"role": "system", "content": "你是一位精通基因组学和精准医学的健康顾问。请基于用户的基因检测数据和健康数据，给出个性化的交叉分析。回复使用中文，以 JSON 格式返回。"},
            {"role": "user", "content": prompt},
        ]
        result = run_async(provider.chat(messages=messages, temperature=0.3, max_tokens=3000))

        # 尝试解析 JSON
        import json
        try:
            # 处理可能的 markdown 代码块
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            sections = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            sections = {"raw_analysis": result}

        return {
            "status": "ok",
            "variant_count": len(variants),
            "sections": sections,
        }
    except Exception as e:
        logger.error(f"基因交叉分析 LLM 调用失败: {e}", exc_info=True)
        # 回退：返回模板化结构
        return {
            "status": "fallback",
            "message": "AI 分析暂时不可用，返回基础统计",
            "variant_count": len(variants),
            "sections": _build_fallback_sections(variants),
        }


def _get_latest_garmin_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """获取最新 Garmin 数据摘要"""
    try:
        from app.models.garmin import GarminData
        latest = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id)
            .order_by(desc(GarminData.date))
            .first()
        )
        if latest:
            return {
                "date": str(latest.date),
                "steps": latest.steps,
                "heart_rate_avg": latest.heart_rate_avg,
                "heart_rate_rest": latest.heart_rate_rest,
                "sleep_hours": latest.sleep_hours,
                "stress_avg": getattr(latest, "stress_avg", None),
                "body_battery_high": getattr(latest, "body_battery_high", None),
            }
    except Exception:
        pass
    return {}


def _get_abnormal_indicators(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """获取最近的异常体检指标"""
    try:
        from app.models.family_health import MedicalIndicator
        indicators = (
            db.query(MedicalIndicator)
            .filter(MedicalIndicator.user_id == user_id, MedicalIndicator.is_abnormal == True)
            .order_by(desc(MedicalIndicator.record_date))
            .limit(10)
            .all()
        )
        return [
            {
                "name": ind.name,
                "value": ind.value,
                "unit": ind.unit,
                "severity": ind.severity,
                "record_date": str(ind.record_date),
            }
            for ind in indicators
        ]
    except Exception:
        return []


def _build_cross_analysis_prompt(
    variants: List[GeneticVariant],
    profile,
    garmin_summary: Dict[str, Any],
    abnormal_indicators: List[Dict[str, Any]],
) -> str:
    """构建交叉分析 prompt"""
    parts = ["## 用户基因变异数据\n"]

    # 按分类整理变异
    by_category: Dict[str, list] = {}
    for v in variants:
        by_category.setdefault(v.category, []).append(v)

    for cat, vs in by_category.items():
        parts.append(f"### {cat}")
        for v in vs:
            line = f"- {v.gene_name}"
            if v.variant_name:
                line += f" ({v.variant_name})"
            if v.genotype:
                line += f" 基因型: {v.genotype}"
            if v.result_label:
                line += f" -> {v.result_label}"
            if v.risk_level and v.risk_level != "info":
                line += f" [风险: {v.risk_level}]"
            parts.append(line)
        parts.append("")

    # 用户画像
    if profile:
        parts.append("## 用户健康画像")
        if getattr(profile, "chronic_conditions", None):
            parts.append(f"慢性病: {profile.chronic_conditions}")
        if getattr(profile, "medications", None):
            parts.append(f"用药: {profile.medications}")
        if getattr(profile, "allergies", None):
            parts.append(f"过敏: {profile.allergies}")
        parts.append("")

    # Garmin 数据
    if garmin_summary:
        parts.append("## 最近运动/睡眠数据")
        for k, v in garmin_summary.items():
            if v is not None:
                parts.append(f"- {k}: {v}")
        parts.append("")

    # 异常指标
    if abnormal_indicators:
        parts.append("## 近期异常体检指标")
        for ind in abnormal_indicators:
            parts.append(f"- {ind['name']}: {ind['value']} {ind.get('unit', '')} ({ind.get('severity', '')}) [{ind.get('record_date', '')}]")
        parts.append("")

    parts.append(
        "请基于以上数据，返回 JSON 格式的交叉分析，包含以下字段:\n"
        "- nutrition_advice: 营养建议（考虑基因对营养吸收的影响）\n"
        "- exercise_advice: 运动建议（考虑基因对运动能力的影响）\n"
        "- sleep_advice: 睡眠建议\n"
        "- drug_alerts: 药物敏感性提醒\n"
        "- disease_prevention: 疾病预防建议\n"
        "每个字段的值为字符串，包含详细的个性化建议。"
    )

    return "\n".join(parts)


def _build_fallback_sections(variants: List[GeneticVariant]) -> Dict[str, str]:
    """LLM 不可用时的回退模板"""
    by_category: Dict[str, list] = {}
    for v in variants:
        by_category.setdefault(v.category, []).append(v)

    sections = {}

    if "nutrition" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["nutrition"])
        sections["nutrition_advice"] = f"您有 {len(by_category['nutrition'])} 个营养相关基因变异（{genes}），建议关注个性化营养摄入。"

    if "exercise" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["exercise"])
        sections["exercise_advice"] = f"您有 {len(by_category['exercise'])} 个运动相关基因变异（{genes}），建议根据基因特点选择运动方式。"

    if "sleep" in by_category:
        sections["sleep_advice"] = f"您有 {len(by_category['sleep'])} 个睡眠相关基因变异，建议关注睡眠质量优化。"

    if "drug_sensitivity" in by_category:
        genes = ", ".join(v.gene_name for v in by_category["drug_sensitivity"])
        sections["drug_alerts"] = f"您有 {len(by_category['drug_sensitivity'])} 个药物敏感性相关基因变异（{genes}），用药前请咨询医生。"

    if "disease_risk" in by_category:
        high_risk = [v for v in by_category["disease_risk"] if v.risk_level == "high"]
        sections["disease_prevention"] = f"您有 {len(by_category['disease_risk'])} 个疾病风险相关基因变异，其中 {len(high_risk)} 个为高风险，建议定期体检。"

    if not sections:
        sections["general"] = "您的基因数据已记录，建议结合体检指标进行综合分析。"

    return sections
