"""Hybrid Search API (LLM Wiki v2)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.hybrid_search import hybrid_retrieve

router = APIRouter(prefix="/hybrid-search", tags=["hybrid-search"])


@router.get("/me", summary="个人语料 + 图谱混合检索")
def my_hybrid(
    q: str = Query(..., min_length=1, max_length=500, description="查询文本"),
    top_k: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    hits = hybrid_retrieve(db, current_user.id, q, top_k=top_k)
    return [{
        "doc_id": h.doc_id,
        "source_type": h.source_type,
        "source_id": h.source_id,
        "rrf_score": round(h.rrf_score, 5),
        "text_preview": h.text_preview,
        "metadata": h.metadata,
    } for h in hits]
