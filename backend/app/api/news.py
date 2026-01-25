"""资讯 API - VIP/管理员可见，支持外部 API Key 写入"""
import hashlib
import secrets
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.database import get_db
from app.models.news import NewsArticle, NewsApiKey
from app.models.user import User
from app.api.deps import get_current_user_required
from app.utils.timezone import CHINA_TIMEZONE

router = APIRouter(prefix="/news", tags=["news"])


# ==================== Schemas ====================

class ArticleCreate(BaseModel):
    """创建文章请求"""
    source_batch_id: str
    source_type: str  # chatlog_analysis, custom_prompt, daily_recap
    title: str
    summary: Optional[str] = None
    content: str
    tags: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    key_people: Optional[List[str]] = None
    source_group: Optional[str] = None
    llm_models: Optional[List[str]] = None
    aggregator_model: Optional[str] = None
    source_created_at: Optional[datetime] = None


class ArticleResponse(BaseModel):
    """文章响应"""
    id: int
    source_batch_id: str
    source_type: str
    title: str
    summary: Optional[str]
    content: Optional[str]  # 列表时不返回完整内容
    tags: Optional[List[str]]
    topics: Optional[List[str]]
    key_people: Optional[List[str]]
    source_group: Optional[str]
    llm_models: Optional[List[str]]
    aggregator_model: Optional[str]
    is_pinned: bool
    view_count: int
    source_created_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ArticleListItem(BaseModel):
    """文章列表项（不含完整内容）"""
    id: int
    source_batch_id: str
    source_type: str
    title: str
    summary: Optional[str]
    tags: Optional[List[str]]
    source_group: Optional[str]
    is_pinned: bool
    view_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreate(BaseModel):
    """创建 API Key 请求"""
    name: str


class ApiKeyResponse(BaseModel):
    """API Key 响应"""
    id: int
    name: str
    api_key: Optional[str]  # 只在创建时返回原始 key
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 工具函数 ====================

def hash_api_key(key: str) -> str:
    """对 API Key 进行 SHA256 哈希"""
    return hashlib.sha256(key.encode()).hexdigest()


def parse_json_field(value: Optional[str]) -> Optional[List[str]]:
    """解析 JSON 字段"""
    if not value:
        return None
    try:
        return json.loads(value)
    except:
        return None


def serialize_json_field(value: Optional[List[str]]) -> Optional[str]:
    """序列化 JSON 字段"""
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def article_to_response(article: NewsArticle, include_content: bool = True) -> dict:
    """将数据库模型转换为响应字典"""
    data = {
        "id": article.id,
        "source_batch_id": article.source_batch_id,
        "source_type": article.source_type,
        "title": article.title,
        "summary": article.summary,
        "tags": parse_json_field(article.tags),
        "topics": parse_json_field(article.topics),
        "key_people": parse_json_field(article.key_people),
        "source_group": article.source_group,
        "llm_models": parse_json_field(article.llm_models),
        "aggregator_model": article.aggregator_model,
        "is_pinned": article.is_pinned,
        "view_count": article.view_count,
        "source_created_at": article.source_created_at,
        "created_at": article.created_at,
    }
    if include_content:
        data["content"] = article.content
    return data


# ==================== 权限检查 ====================

def check_news_access(user: User) -> bool:
    """检查用户是否有资讯访问权限（管理员或 VIP）"""
    # 管理员始终有权限
    if user.is_admin:
        return True
    # TODO: 后续可以添加 VIP 字段检查
    # if hasattr(user, 'is_vip') and user.is_vip:
    #     return True
    # 暂时：已审核用户都可以访问
    return user.is_approved


async def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> NewsApiKey:
    """验证 API Key"""
    key_hash = hash_api_key(x_api_key)
    api_key = db.query(NewsApiKey).filter(
        NewsApiKey.api_key == key_hash,
        NewsApiKey.is_active == True
    ).first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # 更新最后使用时间
    api_key.last_used_at = datetime.now(CHINA_TIMEZONE)
    db.commit()

    return api_key


# ==================== 用户端接口 ====================

@router.get("/articles", response_model=List[ArticleListItem])
async def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取资讯列表（需要 VIP/管理员权限）"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限访问资讯")

    query = db.query(NewsArticle).filter(NewsArticle.is_published == True)

    if source_type:
        query = query.filter(NewsArticle.source_type == source_type)

    # 置顶优先，然后按创建时间倒序
    query = query.order_by(desc(NewsArticle.is_pinned), desc(NewsArticle.created_at))

    articles = query.offset((page - 1) * page_size).limit(page_size).all()

    return [article_to_response(a, include_content=False) for a in articles]


@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取资讯详情（需要 VIP/管理员权限）"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限访问资讯")

    article = db.query(NewsArticle).filter(
        NewsArticle.id == article_id,
        NewsArticle.is_published == True
    ).first()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 增加阅读次数
    article.view_count += 1
    db.commit()

    return article_to_response(article, include_content=True)


# ==================== 外部写入接口 (API Key 认证) ====================

@router.post("/external/articles", response_model=ArticleResponse)
async def create_article_external(
    article: ArticleCreate,
    api_key: NewsApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """创建文章（外部系统通过 API Key 调用）"""
    # 检查是否已存在
    existing = db.query(NewsArticle).filter(
        NewsArticle.source_batch_id == article.source_batch_id
    ).first()

    if existing:
        # 更新已存在的文章
        existing.title = article.title
        existing.summary = article.summary
        existing.content = article.content
        existing.tags = serialize_json_field(article.tags)
        existing.topics = serialize_json_field(article.topics)
        existing.key_people = serialize_json_field(article.key_people)
        existing.source_group = article.source_group
        existing.llm_models = serialize_json_field(article.llm_models)
        existing.aggregator_model = article.aggregator_model
        existing.source_created_at = article.source_created_at
        db.commit()
        db.refresh(existing)
        return article_to_response(existing)

    # 创建新文章
    db_article = NewsArticle(
        source_batch_id=article.source_batch_id,
        source_type=article.source_type,
        title=article.title,
        summary=article.summary or (article.content[:200] if article.content else None),
        content=article.content,
        tags=serialize_json_field(article.tags),
        topics=serialize_json_field(article.topics),
        key_people=serialize_json_field(article.key_people),
        source_group=article.source_group,
        llm_models=serialize_json_field(article.llm_models),
        aggregator_model=article.aggregator_model,
        source_created_at=article.source_created_at,
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)

    return article_to_response(db_article)


# ==================== 管理员接口 ====================

@router.get("/admin/api-keys", response_model=List[ApiKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """列出所有 API Key（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    keys = db.query(NewsApiKey).all()
    return [{"id": k.id, "name": k.name, "api_key": None, "is_active": k.is_active,
             "last_used_at": k.last_used_at, "created_at": k.created_at} for k in keys]


@router.post("/admin/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    key_data: ApiKeyCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建新的 API Key（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    # 生成随机 API Key
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)

    db_key = NewsApiKey(
        name=key_data.name,
        api_key=key_hash,
    )
    db.add(db_key)
    db.commit()
    db.refresh(db_key)

    # 只在创建时返回原始 key
    return {
        "id": db_key.id,
        "name": db_key.name,
        "api_key": raw_key,  # 原始 key，只返回一次
        "is_active": db_key.is_active,
        "last_used_at": db_key.last_used_at,
        "created_at": db_key.created_at,
    }


@router.delete("/admin/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除 API Key（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    key = db.query(NewsApiKey).filter(NewsApiKey.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    db.delete(key)
    db.commit()

    return {"ok": True, "message": "API Key 已删除"}


@router.patch("/admin/articles/{article_id}")
async def update_article_admin(
    article_id: int,
    is_published: Optional[bool] = None,
    is_pinned: Optional[bool] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """管理员更新文章状态（发布/置顶）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    if is_published is not None:
        article.is_published = is_published
    if is_pinned is not None:
        article.is_pinned = is_pinned

    db.commit()

    return {"ok": True, "message": "文章已更新"}
