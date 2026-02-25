"""资讯 API - 多租户资讯系统，支持个人推送和公开API"""
import hashlib
import secrets
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from pydantic import BaseModel

from app.database import get_db
from app.models.news import NewsArticle, NewsApiKey, NewsComment
from app.models.user import User
from app.api.deps import get_current_user_required, get_current_user
from app.utils.timezone import CHINA_TIMEZONE

router = APIRouter(prefix="/news", tags=["news"])


# ==================== Schemas ====================

class ArticleCreate(BaseModel):
    """创建文章请求（外部系统）"""
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


class UserArticlePush(BaseModel):
    """用户推送 LLM 分析结果到资讯"""
    source_batch_id: str
    title: str
    content: str
    summary: Optional[str] = None
    source_type: str = "custom_prompt"
    tags: Optional[List[str]] = None
    llm_models: Optional[List[str]] = None
    aggregator_model: Optional[str] = None
    visibility: str = "public"  # "public" / "private"


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
    user_id: Optional[int] = None
    visibility: str = "public"
    author_name: Optional[str] = None
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
    user_id: Optional[int] = None
    visibility: str = "public"
    author_name: Optional[str] = None
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


class CommentCreate(BaseModel):
    """创建评论请求"""
    content: str
    parent_id: Optional[int] = None  # 回复时需要传入父评论ID


class CommentUser(BaseModel):
    """评论用户信息"""
    id: int
    name: str
    is_admin: bool = False


class CommentResponse(BaseModel):
    """评论响应"""
    id: int
    article_id: int
    user_id: int
    parent_id: Optional[int]
    content: str
    created_at: datetime
    user: CommentUser
    replies: List["CommentResponse"] = []

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


def article_to_response(article: NewsArticle, include_content: bool = True, author_name: str = None) -> dict:
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
        "user_id": article.user_id,
        "visibility": article.visibility or "public",
        "author_name": author_name,
        "source_created_at": article.source_created_at,
        "created_at": article.created_at,
    }
    if include_content:
        data["content"] = article.content
    return data


def _get_author_names(db: Session, articles: list) -> dict:
    """批量获取文章作者名"""
    user_ids = list(set(a.user_id for a in articles if a.user_id))
    if not user_ids:
        return {}
    users = db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
    return {u.id: u.name for u in users}


# ==================== 权限检查 ====================

def check_news_access(user: User) -> bool:
    """检查用户是否有资讯访问权限（管理员或已审核用户）"""
    if user.is_admin:
        return True
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
    feed: Optional[str] = Query("all", pattern="^(all|mine|community)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取资讯列表，支持 feed 过滤：all/mine/community"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限访问资讯")

    query = db.query(NewsArticle).filter(NewsArticle.is_published == True)

    if feed == "mine":
        # 仅自己的文章（含私密）
        query = query.filter(NewsArticle.user_id == current_user.id)
    elif feed == "community":
        # 他人公开 + 系统文章
        query = query.filter(
            or_(
                NewsArticle.user_id == None,
                (NewsArticle.user_id != current_user.id) & (NewsArticle.visibility == "public")
            )
        )
    else:
        # all: 自己的全部 + 他人公开 + 系统文章
        query = query.filter(
            or_(
                NewsArticle.user_id == None,
                NewsArticle.user_id == current_user.id,
                NewsArticle.visibility == "public"
            )
        )

    if source_type:
        query = query.filter(NewsArticle.source_type == source_type)

    # 置顶优先，然后按创建时间倒序
    query = query.order_by(desc(NewsArticle.is_pinned), desc(NewsArticle.created_at))

    articles = query.offset((page - 1) * page_size).limit(page_size).all()

    # 批量获取作者名
    author_names = _get_author_names(db, articles)

    return [article_to_response(a, include_content=False, author_name=author_names.get(a.user_id)) for a in articles]


@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取资讯详情，含可见性检查"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限访问资讯")

    article = db.query(NewsArticle).filter(
        NewsArticle.id == article_id,
        NewsArticle.is_published == True
    ).first()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 可见性检查
    if article.user_id is not None and article.user_id != current_user.id:
        if article.visibility != "public":
            raise HTTPException(status_code=403, detail="该文章为私密文章")

    # 增加阅读次数
    article.view_count += 1
    db.commit()

    # 获取作者名
    author_name = None
    if article.user_id:
        user = db.query(User.name).filter(User.id == article.user_id).first()
        author_name = user.name if user else None

    return article_to_response(article, include_content=True, author_name=author_name)


# ==================== 用户推送接口 ====================

@router.post("/articles/push", response_model=ArticleResponse)
async def push_article(
    article: UserArticlePush,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """推送 LLM 分析结果到自己的资讯（JWT 认证）"""
    if article.visibility not in ("public", "private"):
        raise HTTPException(status_code=400, detail="visibility 必须是 public 或 private")

    # 检查是否已存在（幂等：同一 batch_id 更新）
    existing = db.query(NewsArticle).filter(
        NewsArticle.source_batch_id == article.source_batch_id
    ).first()

    if existing:
        if existing.user_id is not None and existing.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无法更新他人的文章")
        existing.title = article.title
        existing.content = article.content
        existing.summary = article.summary or (article.content[:200] if article.content else None)
        existing.tags = serialize_json_field(article.tags)
        existing.llm_models = serialize_json_field(article.llm_models)
        existing.aggregator_model = article.aggregator_model
        existing.visibility = article.visibility
        existing.user_id = current_user.id
        db.commit()
        db.refresh(existing)
        return article_to_response(existing, author_name=current_user.name)

    # 创建新文章
    db_article = NewsArticle(
        user_id=current_user.id,
        visibility=article.visibility,
        source_batch_id=article.source_batch_id,
        source_type=article.source_type,
        title=article.title,
        summary=article.summary or (article.content[:200] if article.content else None),
        content=article.content,
        tags=serialize_json_field(article.tags),
        llm_models=serialize_json_field(article.llm_models),
        aggregator_model=article.aggregator_model,
        source_created_at=datetime.now(CHINA_TIMEZONE),
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)

    return article_to_response(db_article, author_name=current_user.name)


@router.patch("/articles/{article_id}/visibility")
async def update_article_visibility(
    article_id: int,
    visibility: str = Query(..., pattern="^(public|private)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """切换自己文章的公开/私密"""
    article = db.query(NewsArticle).filter(
        NewsArticle.id == article_id
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    if article.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只能修改自己的文章")

    article.visibility = visibility
    db.commit()
    return {"ok": True, "visibility": visibility}


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除文章（本人或管理员）"""
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    if article.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权删除此文章")

    db.delete(article)
    db.commit()
    return {"ok": True, "message": "文章已删除"}


# ==================== 公开 API（无需认证）====================

@router.get("/public/feed/{user_id}")
async def get_public_user_feed(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """公开 API：获取用户的公开资讯（无需登录）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    query = db.query(NewsArticle).filter(
        NewsArticle.user_id == user_id,
        NewsArticle.visibility == "public",
        NewsArticle.is_published == True
    ).order_by(desc(NewsArticle.created_at))

    total = query.count()
    articles = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "user_id": user_id,
        "user_name": user.name,
        "total": total,
        "page": page,
        "page_size": page_size,
        "articles": [article_to_response(a, include_content=False, author_name=user.name) for a in articles]
    }


# ==================== 外部写入接口 (API Key 认证) ====================

@router.post("/external/articles", response_model=ArticleResponse)
async def create_article_external(
    article: ArticleCreate,
    api_key: NewsApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """创建文章（外部系统通过 API Key 调用，系统级文章）"""
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

    # 创建新文章（系统级，user_id=NULL）
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


# ==================== 评论接口 ====================

def build_comment_tree(comments: List[NewsComment], users_map: dict) -> List[dict]:
    """构建评论树结构"""
    comment_map = {}
    root_comments = []

    # 先构建所有评论的映射
    for comment in comments:
        user = users_map.get(comment.user_id)
        comment_dict = {
            "id": comment.id,
            "article_id": comment.article_id,
            "user_id": comment.user_id,
            "parent_id": comment.parent_id,
            "content": comment.content if not comment.is_deleted else "[评论已删除]",
            "created_at": comment.created_at,
            "user": {
                "id": user.id if user else 0,
                "name": user.name if user else "未知用户",
                "is_admin": user.is_admin if user else False,
            },
            "replies": []
        }
        comment_map[comment.id] = comment_dict

    # 构建树形结构
    for comment in comments:
        comment_dict = comment_map[comment.id]
        if comment.parent_id and comment.parent_id in comment_map:
            comment_map[comment.parent_id]["replies"].append(comment_dict)
        else:
            root_comments.append(comment_dict)

    return root_comments


@router.get("/articles/{article_id}/comments")
async def get_article_comments(
    article_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取文章评论"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限")

    # 检查文章是否存在
    article = db.query(NewsArticle).filter(
        NewsArticle.id == article_id,
        NewsArticle.is_published == True
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 获取所有评论
    comments = db.query(NewsComment).filter(
        NewsComment.article_id == article_id
    ).order_by(NewsComment.created_at.asc()).all()

    # 获取所有评论者的用户信息
    user_ids = list(set(c.user_id for c in comments))
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    users_map = {u.id: u for u in users}

    # 构建评论树
    comment_tree = build_comment_tree(comments, users_map)

    return {"comments": comment_tree, "total": len(comments)}


@router.post("/articles/{article_id}/comments")
async def create_comment(
    article_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """发表评论"""
    if not check_news_access(current_user):
        raise HTTPException(status_code=403, detail="需要 VIP 或管理员权限")

    # 检查文章是否存在
    article = db.query(NewsArticle).filter(
        NewsArticle.id == article_id,
        NewsArticle.is_published == True
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 检查内容
    content = comment_data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="评论内容不能超过2000字")

    # 如果是回复，检查父评论是否存在
    if comment_data.parent_id:
        parent = db.query(NewsComment).filter(
            NewsComment.id == comment_data.parent_id,
            NewsComment.article_id == article_id,
            NewsComment.is_deleted == False
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="回复的评论不存在")

    # 创建评论
    new_comment = NewsComment(
        article_id=article_id,
        user_id=current_user.id,
        parent_id=comment_data.parent_id,
        content=content,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return {
        "id": new_comment.id,
        "article_id": new_comment.article_id,
        "user_id": new_comment.user_id,
        "parent_id": new_comment.parent_id,
        "content": new_comment.content,
        "created_at": new_comment.created_at,
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "is_admin": current_user.is_admin,
        },
        "replies": []
    }


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除评论（仅评论者本人或管理员）"""
    comment = db.query(NewsComment).filter(NewsComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    # 检查权限：只有评论者本人或管理员可以删除
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权删除此评论")

    # 软删除
    comment.is_deleted = True
    db.commit()

    return {"ok": True, "message": "评论已删除"}
