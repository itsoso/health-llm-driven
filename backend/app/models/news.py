"""资讯文章模型"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base


class NewsArticle(Base):
    """资讯文章 - 来自 browser-llm-orchestrator 的群聊总结和研究结论"""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)

    # 来源标识
    source_batch_id = Column(String(100), unique=True, index=True, nullable=False)  # browser-llm-orch 的 batch_id
    source_type = Column(String(50), nullable=False)  # chatlog_analysis, custom_prompt, daily_recap

    # 文章内容
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)  # 摘要 (前200字)
    content = Column(Text, nullable=False)  # 完整 Markdown 内容

    # 元数据
    tags = Column(Text, nullable=True)  # JSON 数组: ["标签1", "标签2"]
    topics = Column(Text, nullable=True)  # JSON 数组: 主题列表
    key_people = Column(Text, nullable=True)  # JSON 数组: 关键人物
    source_group = Column(String(200), nullable=True)  # 来源群聊名称

    # LLM 信息
    llm_models = Column(Text, nullable=True)  # JSON 数组: 使用的模型列表
    aggregator_model = Column(String(100), nullable=True)  # 聚合模型

    # 状态
    is_published = Column(Boolean, default=True)  # 是否发布
    is_pinned = Column(Boolean, default=False)  # 是否置顶
    view_count = Column(Integer, default=0)  # 阅读次数

    # 时间
    source_created_at = Column(DateTime(timezone=True), nullable=True)  # 源数据创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_news_published_created', 'is_published', 'created_at'),
    )


class NewsApiKey(Base):
    """资讯 API 密钥 - 用于外部系统写入"""
    __tablename__ = "news_api_keys"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)  # 密钥名称 (如: browser-llm-orch)
    api_key = Column(String(64), unique=True, index=True, nullable=False)  # API Key (SHA256 hash)

    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NewsComment(Base):
    """资讯文章评论"""
    __tablename__ = "news_comments"

    id = Column(Integer, primary_key=True, index=True)

    article_id = Column(Integer, index=True, nullable=False)  # 文章ID
    user_id = Column(Integer, index=True, nullable=False)  # 评论用户ID
    parent_id = Column(Integer, index=True, nullable=True)  # 父评论ID（用于回复）

    content = Column(Text, nullable=False)  # 评论内容
    is_deleted = Column(Boolean, default=False)  # 是否已删除

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_news_comments_article', 'article_id', 'created_at'),
    )
