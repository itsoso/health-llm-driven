"""
GET  /api/v1/admin/llm/status   — 当前活跃 provider + 配置概况
POST /api/v1/admin/llm/switch   — 临时切换 (内存) provider, 不改 .env
POST /api/v1/admin/llm/ping     — 测当前 provider 延迟 + 中文 tool calling

Karpathy "autonomy slider" 思想: 让管理员能 A/B 切多 LLM 后端验证体验.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.api.deps import get_db
from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/llm", tags=["admin"])


class LLMStatusResponse(BaseModel):
    active_provider: str
    available_providers: list[str]
    current_model: str
    base_url_preview: str
    has_api_key: bool


@router.get("/performance-stats", summary="LLM 性能聚合 (p50/p95 + 成功率 + 成本)")
def performance_stats(
    days: int = 7,
    group_by: str = "model",
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """按 model/provider/caller 聚合 llm_usage_log, 返回 p50/p95/p99/avg/
    success_rate/total_tokens/cost. 来自 2026-05-13 用户诉求 (积累性能优化).

    group_by: model / provider / caller (默认 model)
    days: 时间窗口 (默认 7 天)
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text

    if group_by not in ("model", "provider", "caller"):
        raise HTTPException(400, detail="group_by 必须是 model / provider / caller")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    sql = text(f"""
        SELECT
            {group_by} AS label,
            COUNT(*) AS n,
            ROUND(AVG(latency_ms)::numeric, 0) AS avg_ms,
            ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)::numeric, 0) AS p50_ms,
            ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric, 0) AS p95_ms,
            ROUND(percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms)::numeric, 0) AS p99_ms,
            ROUND(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END)::numeric, 4) AS success_rate,
            SUM(total_tokens) AS total_tokens,
            ROUND(SUM(cost_usd)::numeric, 4) AS cost_usd
        FROM llm_usage_log
        WHERE created_at >= :cutoff AND latency_ms IS NOT NULL
        GROUP BY {group_by}
        ORDER BY n DESC
    """)
    rows = db.execute(sql, {"cutoff": cutoff}).fetchall()

    return {
        "window": {"days": days, "since": cutoff.isoformat()},
        "group_by": group_by,
        "stats": [
            {
                "label": r.label,
                "n": r.n,
                "avg_ms": int(r.avg_ms) if r.avg_ms is not None else None,
                "p50_ms": int(r.p50_ms) if r.p50_ms is not None else None,
                "p95_ms": int(r.p95_ms) if r.p95_ms is not None else None,
                "p99_ms": int(r.p99_ms) if r.p99_ms is not None else None,
                "success_rate": float(r.success_rate) if r.success_rate is not None else None,
                "total_tokens": int(r.total_tokens) if r.total_tokens is not None else 0,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else 0.0,
            }
            for r in rows
        ],
    }


@router.get("/performance-failures", summary="最近 LLM 失败样本")
def performance_failures(
    days: int = 7,
    limit: int = 30,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    from app.models.llm_usage import LlmUsageLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(LlmUsageLog)
        .filter(LlmUsageLog.success == 0, LlmUsageLog.created_at >= cutoff)
        .order_by(LlmUsageLog.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "window": {"days": days, "since": cutoff.isoformat()},
        "failures": [
            {
                "id": r.id,
                "provider": r.provider,
                "model": r.model,
                "caller": r.caller,
                "user_id": r.user_id,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/status", response_model=LLMStatusResponse)
def llm_status(
    admin: User = Depends(get_admin_user),
):
    """看现在用的是哪家 LLM."""
    from app.services.llm.factory import get_llm_provider, _provider_instance

    provider = get_llm_provider()
    provider_type = settings.llm_provider

    # 模型 + base_url 按 provider 取
    if provider_type == "openai":
        model = settings.openai_model
        base = settings.openai_base_url or "https://api.openai.com/v1"
        has_key = bool(settings.openai_api_key)
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
        base = settings.tokenplan_base_url
        has_key = bool(settings.tokenplan_api_key)
    elif provider_type == "openclaw":
        model = settings.openclaw_model
        base = settings.openclaw_base_url
        has_key = bool(settings.openclaw_api_key)
    elif provider_type == "ollama":
        model = settings.ollama_model
        base = settings.ollama_base_url
        has_key = True  # 本地无需 key
    else:
        model = "unknown"
        base = ""
        has_key = False

    available = ["openclaw", "openai", "ollama"]
    if settings.tokenplan_api_key:
        available.append("tokenplan")

    return LLMStatusResponse(
        active_provider=provider_type,
        available_providers=available,
        current_model=model,
        base_url_preview=base[:80] if base else "",
        has_api_key=has_key,
    )


class LLMSwitchRequest(BaseModel):
    provider: str  # openai | openclaw | ollama | tokenplan


@router.post("/switch")
def llm_switch(
    req: LLMSwitchRequest,
    admin: User = Depends(get_admin_user),
):
    """
    临时切换 LLM provider (改进程内 settings + 重置 factory 单例).
    重启进程后会回退到 .env 的 LLM_PROVIDER.

    生产场景永久切换请改 .env + 重启服务.
    """
    valid = {"openai", "openclaw", "ollama", "tokenplan"}
    if req.provider not in valid:
        raise HTTPException(400, f"不支持的 provider: {req.provider}, 可选 {sorted(valid)}")

    # tokenplan 必须有 key
    if req.provider == "tokenplan" and not settings.tokenplan_api_key:
        raise HTTPException(400, "tokenplan 切换前需先配置 TOKENPLAN_API_KEY")

    old = settings.llm_provider
    settings.llm_provider = req.provider

    # 重置 factory 单例, 下次 get_llm_provider() 重新创建
    from app.services.llm.factory import reset_llm_provider
    reset_llm_provider()

    logger.warning(
        f"[admin.llm.switch] user={admin.id} {old} → {req.provider} (内存级, 重启失效)"
    )
    return {
        "ok": True,
        "from": old,
        "to": req.provider,
        "note": "进程内切换. 永久切换请改 .env 并重启服务",
    }


class LLMPingResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int
    sample_reply: str
    error: Optional[str] = None


@router.post("/ping", response_model=LLMPingResponse)
async def llm_ping(
    admin: User = Depends(get_admin_user),
):
    """
    测当前 provider 延迟 + 中文回复. 给管理员 A/B 用.
    """
    from app.services.llm.factory import get_llm_provider

    provider = get_llm_provider()
    provider_type = settings.llm_provider
    model = ""
    if provider_type == "openai":
        model = settings.openai_model
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
    elif provider_type == "openclaw":
        model = settings.openclaw_model
    elif provider_type == "ollama":
        model = settings.ollama_model

    t0 = time.time()
    try:
        raw = await provider.chat(
            messages=[
                {"role": "system", "content": "你是健康助理. 用 ≤30 字回答."},
                {"role": "user", "content": "我今天 HRV 比平时低 12, 怎么办?"},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
        latency = int((time.time() - t0) * 1000)
        return LLMPingResponse(
            ok=True,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply=(raw or "")[:200],
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        logger.warning(f"[admin.llm.ping] failed: {e}")
        return LLMPingResponse(
            ok=False,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply="",
            error=str(e)[:200],
        )


# ───── 多模型管理: list / select / latency snapshot ─────


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    model: str
    speed_tier: str
    note: str = ""
    available: bool       # env 是否齐全
    is_active: bool       # 当前选中的


class ModelListResponse(BaseModel):
    active_id: Optional[str]   # None = 走 settings 默认
    fallback_provider: str     # active 缺失时落到哪个 provider
    fallback_model: str
    models: list[ModelInfo]


@router.get("/models", response_model=ModelListResponse)
def list_available_models(admin: User = Depends(get_admin_user)):
    """列出所有注册的模型 + 可用性 + 当前选中."""
    from app.services.llm.model_registry import MODELS, get_active_model_id, list_models
    available_ids = {m.id for m in list_models(only_available=True)}
    active = get_active_model_id()

    out = []
    for m in MODELS:
        out.append(ModelInfo(
            id=m.id,
            label=m.label,
            provider=m.provider,
            model=m.model,
            speed_tier=m.speed_tier,
            note=m.note,
            available=m.id in available_ids,
            is_active=(active == m.id),
        ))

    # fallback
    fp = settings.llm_provider
    if fp == "openai":
        fm = settings.openai_model
    elif fp == "tokenplan":
        fm = settings.tokenplan_model
    elif fp == "openclaw":
        fm = settings.openclaw_model
    else:
        fm = "?"

    return ModelListResponse(
        active_id=active,
        fallback_provider=fp,
        fallback_model=fm,
        models=out,
    )


class SelectModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str]   # None / 空 = 恢复默认


@router.post("/select-model")
def select_model(req: SelectModelRequest, admin: User = Depends(get_admin_user)):
    """切换活跃模型. 进程内, 重启失效."""
    from app.services.llm.model_registry import get_model, set_active_model_id
    from app.services.llm.factory import reset_llm_provider

    if not req.model_id:
        set_active_model_id(None)
        reset_llm_provider()
        logger.warning(f"[admin.llm.select-model] user={admin.id} 恢复默认")
        return {"ok": True, "active_id": None, "note": "恢复默认 provider"}

    entry = get_model(req.model_id)
    if not entry:
        raise HTTPException(404, f"未注册的 model: {req.model_id}")

    # 验 env 齐全
    from app.services.llm.model_registry import _env_present
    missing = [e for e in entry.requires_env if not _env_present(e, settings)]
    if missing:
        raise HTTPException(400, f"模型 {req.model_id} 需要的 env 缺失: {missing}")

    set_active_model_id(req.model_id)
    reset_llm_provider()
    logger.warning(f"[admin.llm.select-model] user={admin.id} 选中 {req.model_id}")
    return {"ok": True, "active_id": req.model_id, "label": entry.label}


class BenchmarkResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    label: str
    runs: int
    latency_ms: list[int]
    avg_ms: float
    ok: bool
    sample_reply: str


@router.post("/benchmark/{model_id}", response_model=BenchmarkResponse)
async def benchmark_model(
    model_id: str,
    runs: int = 3,
    admin: User = Depends(get_admin_user),
):
    """跑指定模型 N 次, 测延迟. 用于对比. 不切换活跃 model."""
    from app.services.llm.model_registry import get_model
    from app.services.llm.factory import _create_from_entry
    entry = get_model(model_id)
    if not entry:
        raise HTTPException(404, f"未注册: {model_id}")

    try:
        provider = _create_from_entry(entry)
    except Exception as e:
        raise HTTPException(400, f"创建 provider 失败: {e}")

    latencies = []
    sample = ""
    ok = True
    for _ in range(max(1, min(runs, 5))):
        t0 = time.time()
        try:
            reply = await provider.chat(
                messages=[{"role": "user", "content": "用一句话回答: 现在是早晨还是下午"}],
                max_tokens=40,
            )
            text = reply if isinstance(reply, str) else reply.get("content", "")
            sample = text[:40]
        except Exception as e:
            sample = f"ERR: {type(e).__name__}: {str(e)[:60]}"
            ok = False
        latencies.append(int((time.time() - t0) * 1000))

    avg = sum(latencies) / len(latencies)
    return BenchmarkResponse(
        model_id=model_id, label=entry.label, runs=len(latencies),
        latency_ms=latencies, avg_ms=round(avg, 1), ok=ok, sample_reply=sample,
    )
