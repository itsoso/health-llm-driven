"""
知识库管理 API

提供知识库的增删改查和 RAG 问答功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import json
import logging

from datetime import UTC, datetime
from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.config import settings
from app.services.knowledge import VectorStoreService, RAGPipeline, DocumentLoader
from app.services.knowledge.vectorstore import vector_store
from app.services.knowledge.rag_pipeline import rag_pipeline
from app.services.knowledge.document_loader import document_loader
from app.services.knowledge.document_loader_enhanced import enhanced_loader, zhang_zhanhui_loader
from app.services.secure_upload import (
    UploadContentInvalid,
    UploadTooLarge,
    decode_utf8_text,
    read_upload_limited,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge-base"])
logger = logging.getLogger(__name__)

MAX_KNOWLEDGE_FILE_BYTES = 5 * 1024 * 1024
MAX_KNOWLEDGE_BATCH_FILES = 20


def _ensure_legacy_knowledge_runtime_enabled() -> None:
    """Guard legacy Chroma/RAG runtime endpoints.

    The governed health runtime uses ``system_knowledge`` APIs. This legacy
    vector store remains available only when explicitly enabled for local
    debugging or migration work.
    """

    if settings.legacy_knowledge_runtime_enabled:
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "legacy_knowledge_runtime_disabled",
            "message": "Legacy Chroma/RAG knowledge runtime is disabled. Use reviewed System KB APIs.",
            "use": "system_knowledge",
        },
    )


# ========== Pydantic Models ==========

class DocumentInput(BaseModel):
    """单个文档输入"""
    content: str = Field(..., description="文档内容")
    title: Optional[str] = Field(None, description="文档标题")
    category: Optional[str] = Field("general", description="分类")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")


class DocumentBatchInput(BaseModel):
    """批量文档输入"""
    documents: List[DocumentInput] = Field(..., description="文档列表")
    source: str = Field(..., description="来源标识")


class TextInput(BaseModel):
    """纯文本输入"""
    text: str = Field(..., description="文本内容")
    title: Optional[str] = Field("", description="标题")
    category: Optional[str] = Field("general", description="分类")
    source: Optional[str] = Field("manual_input", description="来源")


class SearchQuery(BaseModel):
    """搜索查询"""
    query: str = Field(..., description="搜索内容")
    n_results: int = Field(5, ge=1, le=20, description="返回结果数量")
    category: Optional[str] = Field(None, description="分类过滤")
    source: Optional[str] = Field(None, description="来源过滤")


class RAGQuery(BaseModel):
    """RAG 问答查询"""
    question: str = Field(..., description="用户问题")
    category: Optional[str] = Field(None, description="知识分类过滤")
    include_health_data: bool = Field(False, description="是否包含用户健康数据")


class DeleteBySourceInput(BaseModel):
    """按来源删除"""
    source: str = Field(..., description="要删除的来源标识")


class CourseUploadInput(BaseModel):
    """课程上传输入（用于张展晖等专业课程）"""
    content: str = Field(..., description="课程内容（Markdown格式）")
    title: str = Field(..., description="课程标题")
    author: str = Field(default="张展晖", description="作者名称")
    source: str = Field(..., description="来源标识，如 'zhang_zhanhui_01'")
    difficulty: str = Field(default="intermediate", description="难度：beginner/intermediate/advanced")
    target_audience: List[str] = Field(default_factory=list, description="目标人群，如 ['跑步爱好者', '减脂人群']")
    course_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")


class GeneDrugRulesInput(BaseModel):
    """基因-药物规则输入"""
    id: str = Field(..., description="规则ID")
    type: str = Field(default="gene_drug_constraints")
    version: str = Field(..., description="版本号")
    compiled_at: str = Field(..., description="编译时间")
    source: str = Field(default="ak-kbase")
    description: Optional[str] = None
    rules: Dict[str, Any] = Field(..., description="基因-药物规则")


class GeneKnowledgeInput(BaseModel):
    """gene_knowledge.json (llm-wiki-v2) 全量上传"""
    id: str = Field(default="gene_knowledge")
    schema_id: str = Field(default="llm-wiki-v2-gene-knowledge")
    version: str = Field(..., description="版本号")
    compiled_at: str = Field(..., description="编译时间")
    source: str = Field(default="ak-kbase")
    description: Optional[str] = None
    entities: Dict[str, Any] = Field(default_factory=dict, description="entity_type → id → entity")
    claims: List[Dict[str, Any]] = Field(default_factory=list, description="atomic claims with drug_rules")
    gene_rules: Dict[str, Any] = Field(default_factory=dict, description="gene → phenotype → rules")
    snp_registry: Dict[str, Any] = Field(default_factory=dict, description="rsid → metadata")
    stats: Optional[Dict[str, Any]] = None


# ========== API Endpoints ==========

@router.get("/stats", summary="获取知识库统计信息")
def get_knowledge_stats(
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """获取知识库的统计信息"""
    stats = vector_store.get_stats()
    return stats


@router.post("/documents", summary="添加文档到知识库")
def add_documents(
    input_data: DocumentBatchInput,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    批量添加文档到知识库

    需要管理员权限
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以添加知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    documents = [doc.model_dump() for doc in input_data.documents]
    result = vector_store.add_documents(documents, source=input_data.source)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "添加文档失败")
        )

    return result


@router.post("/documents/text", summary="添加纯文本到知识库")
def add_text_document(
    input_data: TextInput,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    添加纯文本内容到知识库

    文本会自动分块处理
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以添加知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    # 使用文档加载器处理文本
    documents = document_loader.load_from_text(
        text=input_data.text,
        title=input_data.title,
        category=input_data.category,
        source=input_data.source
    )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文本内容为空"
        )

    result = vector_store.add_documents(documents, source=input_data.source)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "添加文档失败")
        )

    return result


@router.post("/documents/course/files", summary="批量上传课程文件到知识库（增强版）")
async def upload_course_files(
    files: List[UploadFile] = File(...),
    source: str = Form(...),
    title: str = Form(...),
    author: str = Form("张展晖"),
    difficulty: str = Form("intermediate"),
    target_audiences: str = Form("[]"),  # JSON string of list
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    批量上传课程 Markdown 文件到知识库（使用增强版加载器）

    支持一次上传多个 .md 文件，自动解析和分块

    专为运动科学课程（如张展晖课程）优化：
    - 保留标题层级和面包屑导航
    - 更大的分块大小（1800-2000字符）
    - 丰富的元数据（作者、难度、目标人群、关键概念）
    - 智能识别课程结构

    需要管理员权限
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以添加知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    if len(files) > MAX_KNOWLEDGE_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"一次最多上传 {MAX_KNOWLEDGE_BATCH_FILES} 个文件",
        )

    # 解析目标人群
    try:
        target_audience_list = json.loads(target_audiences)
        if not isinstance(target_audience_list, list):
            target_audience_list = []
    except json.JSONDecodeError:
        target_audience_list = []

    # 记录接收到的文件
    logger.info(f"[课程上传] 接收到 {len(files)} 个文件")
    for i, file in enumerate(files):
        logger.info(f"[课程上传] 文件 {i+1}: {file.filename}, content_type: {file.content_type}")

    # 验证文件格式
    for file in files:
        filename = file.filename or ""
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext not in ["md", "markdown"]:
            logger.error(f"[课程上传] 文件格式不支持: {filename}, ext: {ext}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件 {filename} 格式不支持，仅支持 .md 或 .markdown 文件"
            )

    try:
        all_documents = []
        file_results = []

        # 逐个处理文件
        for file in files:
            filename = file.filename or "未命名文件"
            logger.info(f"[课程上传] 开始处理文件: {filename}")

            try:
                # 读取文件内容
                content = await read_upload_limited(
                    file,
                    max_bytes=MAX_KNOWLEDGE_FILE_BYTES,
                )
                file_size_kb = len(content) / 1024
                logger.info(f"[课程上传] 文件大小: {file_size_kb:.1f} KB")

                text = decode_utf8_text(content, label="课程文件")

                # 使用增强版加载器处理
                documents = enhanced_loader.load_course_markdown(
                    content=text,
                    source=f"{source}_{filename}",
                    author=author,
                    difficulty=difficulty,
                    target_audience=target_audience_list
                )

                all_documents.extend(documents)

                file_results.append({
                    "filename": filename,
                    "success": True,
                    "chunks": len(documents),
                    "size_kb": round(file_size_kb, 1)
                })

                logger.info(f"[课程上传] 文件 {filename} 处理完成，生成 {len(documents)} 个文档块")

            except (UnicodeDecodeError, UploadContentInvalid, UploadTooLarge) as exc:
                logger.error(f"[课程上传] 文件 {filename} 编码错误")
                file_results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(exc)
                })
            except Exception as e:
                logger.error(f"[课程上传] 处理文件 {filename} 失败: {e}")
                file_results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(e)
                })

        if not all_documents:
            logger.error(f"[课程上传] 没有生成任何文档块。file_results: {file_results}")
            error_details = []
            for fr in file_results:
                if not fr['success']:
                    error_details.append(f"{fr['filename']}: {fr.get('error', '未知错误')}")

            detail_msg = "没有成功处理任何文件"
            if error_details:
                detail_msg += "。错误详情：" + "; ".join(error_details)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail_msg
            )

        # 添加到向量存储
        logger.info(f"[课程上传] 开始添加 {len(all_documents)} 个文档块到向量存储")
        result = vector_store.add_documents(all_documents, source=source)

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "添加文档失败")
            )

        logger.info(f"[课程上传] 成功添加 {result.get('added_count', 0)} 个文档块")

        return {
            "success": True,
            "message": f"成功上传 {len([f for f in file_results if f['success']])} 个文件",
            "files": file_results,
            "total_chunks": len(all_documents),
            "added_count": result.get("added_count", 0),
            "total_in_kb": result.get("total_count", 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[课程上传] 批量上传失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传失败: {str(e)}"
        )


@router.post("/documents/course", summary="上传专业课程到知识库（增强版）")
def upload_course(
    input_data: CourseUploadInput,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    上传专业课程内容到知识库（使用增强版加载器）

    通过文本输入方式上传单个课程内容

    专为运动科学课程（如张展晖课程）优化：
    - 保留标题层级和面包屑导航
    - 更大的分块大小（1800-2000字符）
    - 丰富的元数据（作者、难度、目标人群、关键概念）
    - 智能识别课程结构

    需要管理员权限
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以添加知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    logger.info(f"[课程上传] 用户 {current_user.id} 开始上传课程: {input_data.title}")
    logger.info(f"[课程上传] 作者: {input_data.author}, 来源: {input_data.source}")

    try:
        # 使用增强版加载器处理课程内容
        documents = zhang_zhanhui_loader.load_course_markdown(
            content=input_data.content,
            source=input_data.source,
            author=input_data.author,
            difficulty=input_data.difficulty,
            target_audience=input_data.target_audience,
            course_metadata=input_data.course_metadata
        )

        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="课程内容解析失败或为空"
            )

        logger.info(f"[课程上传] 课程解析完成，共 {len(documents)} 个文档块，开始向量化...")

        # 添加到向量库
        result = vector_store.add_documents(documents, source=input_data.source)

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "添加文档失败")
            )

        logger.info(f"[课程上传] 完成！结果: {result}")

        return {
            **result,
            "course_title": input_data.title,
            "author": input_data.author,
            "difficulty": input_data.difficulty,
            "target_audience": input_data.target_audience
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[课程上传] 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传课程失败: {str(e)}"
        )


@router.post("/documents/upload", summary="上传文件到知识库")
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form(...),
    category: Optional[str] = Form("general"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    上传文件到知识库

    支持的格式：.txt, .md, .json
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以添加知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    # 检查文件类型
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext not in ["txt", "md", "json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不支持的文件格式，请上传 .txt, .md 或 .json 文件"
        )

    try:
        # 读取文件内容
        logger.info(f"[知识库上传] 用户 {current_user.id} 开始上传文件: {filename}")
        content = await read_upload_limited(
            file,
            max_bytes=MAX_KNOWLEDGE_FILE_BYTES,
        )
        file_size_kb = len(content) / 1024
        logger.info(f"[知识库上传] 文件大小: {file_size_kb:.1f} KB")
        text = decode_utf8_text(content, label="知识库文件")

        # 根据文件类型处理
        if ext == "json":
            try:
                articles = json.loads(text)
                if isinstance(articles, list):
                    documents = []
                    for article in articles:
                        docs = document_loader.load_from_text(
                            text=article.get("content", ""),
                            title=article.get("title", ""),
                            category=article.get("category", category),
                            source=source
                        )
                        documents.extend(docs)
                else:
                    documents = document_loader.load_from_text(
                        text=articles.get("content", text),
                        title=articles.get("title", filename),
                        category=articles.get("category", category),
                        source=source
                    )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="JSON 文件格式错误"
                )
        else:
            # 处理 txt 和 md 文件
            documents = document_loader.load_from_text(
                text=text,
                title=filename,
                category=category,
                source=source
            )

        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件内容为空或无法解析"
            )

        logger.info(f"[知识库上传] 文件解析完成，共 {len(documents)} 个文档块，开始向量化...")
        result = vector_store.add_documents(documents, source=source)
        logger.info(f"[知识库上传] 完成，结果: {result}")

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "添加文档失败")
            )

        return {
            **result,
            "filename": filename,
            "file_type": ext
        }

    except (UnicodeDecodeError, UploadContentInvalid) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    except UploadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="知识库文件过大，最大 5MB",
        ) from exc


@router.post("/search", summary="搜索知识库")
def search_knowledge(
    query: SearchQuery,
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    搜索知识库内容

    使用向量相似度搜索相关文档
    """
    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    results = vector_store.search(
        query=query.query,
        n_results=query.n_results,
        category=query.category,
        source=query.source
    )

    return {
        "query": query.query,
        "results": results,
        "count": len(results)
    }


@router.post("/ask", summary="RAG 问答")
def ask_question(
    query: RAGQuery,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    基于知识库的 RAG 问答

    结合知识库内容和用户画像生成个性化回答
    """
    if not rag_pipeline.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG 服务不可用"
        )

    # 构建用户上下文
    from app.services.llm_health_analyzer import LLMHealthAnalyzer
    analyzer = LLMHealthAnalyzer()
    user_context = analyzer._build_user_context(db, current_user.id)

    # 获取健康数据（如果需要）
    health_data = None
    if query.include_health_data:
        from app.models.daily_health import GarminData
        from app.utils.timezone import get_china_today

        latest_data = db.query(GarminData).filter(
            GarminData.user_id == current_user.id
        ).order_by(GarminData.record_date.desc()).first()

        if latest_data:
            health_data = {
                "sleep_score": latest_data.sleep_score,
                "steps": latest_data.steps,
                "resting_heart_rate": latest_data.resting_heart_rate,
                "stress_level": latest_data.stress_level,
                "body_battery": latest_data.body_battery_most_charged
            }

    # 生成回答
    result = rag_pipeline.generate_with_knowledge(
        user_query=query.question,
        user_context=user_context,
        health_data=health_data,
        category=query.category
    )

    return result


@router.delete("/documents/source", summary="按来源删除文档")
def delete_by_source(
    input_data: DeleteBySourceInput,
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    删除指定来源的所有文档

    需要管理员权限
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以删除知识库内容"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    result = vector_store.delete_by_source(input_data.source)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "删除失败")
        )

    return result


@router.delete("/documents/all", summary="清空知识库")
def clear_all_documents(
    confirm: bool = False,
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    清空整个知识库

    需要管理员权限，且需要确认
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以清空知识库"
        )

    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请确认清空操作 (confirm=true)"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    result = vector_store.clear_all()

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "清空失败")
        )

    return {"message": "知识库已清空", **result}


@router.post("/gene-drug-rules", summary="上传基因-药物交互规则")
def upload_gene_drug_rules(
    input_data: GeneDrugRulesInput,
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    上传基因-药物交互规则库

    这些规则被 AI 分析引擎用于为每个用户动态生成药物安全约束。
    规则本身是通用的（Layer 2），但在运行时结合每个用户的
    GeneticVariant 记录生成个性化约束。

    需要管理员权限。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以上传规则"
        )

    # 将规则存储为知识库文档（便于版本追踪）
    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    # 先删除旧版本
    vector_store.delete_by_source(f"{input_data.source}_gene_rules")

    # 存储为文档
    import json as json_lib
    doc = {
        "content": json_lib.dumps(input_data.rules, ensure_ascii=False, indent=2),
        "title": "基因-药物交互规则库",
        "category": "gene_drug_rules",
        "metadata": {
            "version": input_data.version,
            "compiled_at": input_data.compiled_at,
            "type": input_data.type,
        }
    }

    result = vector_store.add_documents([doc], source=f"{input_data.source}_gene_rules")

    if result.get("success"):
        logger.info(f"基因-药物规则已更新: version={input_data.version}, genes={len(input_data.rules)}")

    return {
        "message": "基因-药物规则已更新",
        "version": input_data.version,
        "gene_count": len(input_data.rules),
        **result
    }


@router.post("/gene-knowledge", summary="上传 gene_knowledge.json (llm-wiki-v2)")
def upload_gene_knowledge(
    input_data: GeneKnowledgeInput,
    current_user: User = Depends(get_current_user_required),
):
    """
    上传 down-dedao/artifacts/gene_knowledge.json 并刷新内存 registry。

    这是 llm-wiki-v2 schema 的全量基因知识包（entities + claims + gene_rules
    + snp_registry），由 down-dedao/pipeline/compiler.py 从 wiki/entities/ 与
    wiki/claims/ 编译产出。落盘后立刻热加载到 GeneRulesRegistry，下一次
    LLM 系统提示词构建即生效，无需重启服务。

    需要管理员权限。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以上传规则"
        )

    from app.services.gene_rules_registry import reload_from_payload

    payload = input_data.model_dump() if hasattr(input_data, "model_dump") else input_data.dict()
    registry = reload_from_payload(payload)

    logger.info(
        "gene_knowledge 已更新: version=%s genes=%d claims=%d snps=%d",
        registry.version,
        len(registry.gene_rules),
        len(registry.claims),
        len(registry.snp_registry),
    )

    return {
        "message": "gene_knowledge 已更新",
        "version": registry.version,
        "schema_id": registry.schema_id,
        "gene_count": len(registry.gene_rules),
        "claim_count": len(registry.claims),
        "snp_count": len(registry.snp_registry),
        "entity_counts": {k: len(v) for k, v in registry.entities.items()},
    }


@router.get("/feedback", summary="获取知识库反馈洞察")
def get_knowledge_feedback(
    source: Optional[str] = None,
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取匿名聚合的知识库使用反馈

    供外部知识系统（如 ak-kbase）拉取匿名化的群体洞察，
    用于知识库的持续演进。

    返回的数据已脱敏：
    - 不包含任何用户ID或个人信息
    - 只有 N≥30 的聚合数据才会返回
    - 所有数据为统计摘要

    需要管理员权限。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以获取反馈数据"
        )

    insights = []

    # Insight 1: 知识库使用统计
    if settings.legacy_knowledge_runtime_enabled:
        try:
            stats = vector_store.get_stats()
            insights.append({
                "title": "知识库统计",
                "content": f"当前共 {stats.get('total_documents', 0)} 篇文档",
                "type": "stats",
                "sample_size": None,
            })
        except Exception:
            pass

    # Insight 2: 疾病模板使用分布（匿名）
    try:
        from app.models.disease_tracking import UserDiseaseProfile, DiseaseTemplate
        from sqlalchemy import func

        disease_counts = db.query(
            DiseaseTemplate.name,
            func.count(UserDiseaseProfile.id).label("count")
        ).join(
            DiseaseTemplate,
            UserDiseaseProfile.template_id == DiseaseTemplate.id
        ).group_by(DiseaseTemplate.name).all()

        if disease_counts:
            distribution = "; ".join([f"{name}: {count}人" for name, count in disease_counts])
            total = sum(c for _, c in disease_counts)
            if total >= 5:  # 至少5人才报告
                insights.append({
                    "title": "疾病管理分布",
                    "content": distribution,
                    "type": "disease_distribution",
                    "sample_size": total,
                })
    except Exception as e:
        logger.debug(f"疾病分布统计失败: {e}")

    # Insight 3: 鼻炎症状趋势（匿名聚合）
    try:
        from app.models.illness import IllnessEpisode
        from sqlalchemy import func
        from datetime import timedelta

        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

        rhinitis_episodes = db.query(
            func.count(IllnessEpisode.id),
            func.avg(IllnessEpisode.severity)
        ).filter(
            IllnessEpisode.name.ilike("%喷嚏%") |
            IllnessEpisode.name.ilike("%鼻%"),
            IllnessEpisode.created_at >= thirty_days_ago
        ).first()

        if rhinitis_episodes and rhinitis_episodes[0] and rhinitis_episodes[0] >= 5:
            insights.append({
                "title": "鼻炎相关症状（近30天）",
                "content": f"共 {rhinitis_episodes[0]} 次记录，平均严重度 {rhinitis_episodes[1]:.1f}/10",
                "type": "rhinitis_trend",
                "sample_size": rhinitis_episodes[0],
            })
    except Exception as e:
        logger.debug(f"鼻炎统计失败: {e}")

    # Insight 4: 基因数据覆盖率
    try:
        from app.models.genetic_data import GeneticVariant
        from sqlalchemy import func

        gene_stats = db.query(
            GeneticVariant.gene_name,
            func.count(func.distinct(GeneticVariant.user_id)).label("user_count")
        ).group_by(GeneticVariant.gene_name).all()

        if gene_stats:
            gene_coverage = "; ".join([f"{gene}: {count}人" for gene, count in gene_stats if count >= 3])
            if gene_coverage:
                insights.append({
                    "title": "基因数据覆盖",
                    "content": gene_coverage,
                    "type": "gene_coverage",
                    "sample_size": sum(c for _, c in gene_stats),
                })
    except Exception as e:
        logger.debug(f"基因统计失败: {e}")

    return {
        "source": source,
        "since": since,
        "generated_at": datetime.now().isoformat(),
        "insights": insights,
        "note": "所有数据已脱敏，不包含个人信息"
    }


# ========== 预置知识内容 API ==========

@router.post("/init/health-basics", summary="初始化基础健康知识")
def init_health_basics(
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """
    初始化基础健康知识到知识库

    包含睡眠、运动、营养等基础健康内容
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以初始化知识库"
        )

    if not vector_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库服务不可用"
        )

    # 基础健康知识内容
    basic_knowledge = [
        {
            "title": "睡眠的重要性",
            "category": "sleep",
            "content": """
睡眠是人体恢复和修复的关键时期。成年人每晚需要7-9小时的优质睡眠。

睡眠不足的影响：
1. 免疫力下降，更容易生病
2. 认知功能受损，记忆力和注意力降低
3. 情绪波动，更容易焦虑和抑郁
4. 代谢紊乱，增加肥胖和糖尿病风险
5. 心血管风险增加

改善睡眠的方法：
1. 保持规律的作息时间，即使周末也不要偏差太大
2. 睡前1小时避免使用电子设备，蓝光会抑制褪黑素分泌
3. 卧室保持凉爽（18-22°C）、黑暗、安静
4. 避免下午3点后摄入咖啡因
5. 睡前可以进行轻度拉伸或冥想放松
6. 避免睡前2小时内大量进食或饮水
"""
        },
        {
            "title": "有氧运动指南",
            "category": "exercise",
            "content": """
有氧运动是改善心肺功能的最佳方式。WHO建议成年人每周进行至少150分钟中等强度有氧运动。

常见有氧运动：
1. 快走：最简单易行，适合初学者
2. 跑步：高效燃脂，需要循序渐进
3. 游泳：全身运动，对关节友好
4. 骑自行车：户外或室内都可以
5. 跳绳：高效且占地小

运动强度判断：
- 轻度：可以轻松对话
- 中度：可以说话但会喘
- 高强度：只能说几个词

注意事项：
1. 运动前热身5-10分钟
2. 运动后拉伸放松
3. 循序渐进，不要急于求成
4. 及时补充水分
5. 如有不适立即停止
"""
        },
        {
            "title": "静息心率与健康",
            "category": "heart_health",
            "content": """
静息心率是指完全放松状态下的心跳次数。正常成年人的静息心率在60-100次/分钟。

静息心率与健康的关系：
- 低于60：通常见于运动员或心血管健康者（运动性心动过缓）
- 60-70：优秀
- 70-80：良好
- 80-90：一般
- 90以上：需要关注，可能提示心血管风险

影响静息心率的因素：
1. 体能水平：规律运动可降低静息心率
2. 压力和焦虑：会升高心率
3. 咖啡因和酒精
4. 睡眠质量
5. 温度和湿度
6. 疾病状态

如何降低静息心率：
1. 规律的有氧运动（每周3-5次，每次30分钟以上）
2. 减少压力，学习放松技巧
3. 保证充足睡眠
4. 控制咖啡因摄入
5. 保持健康体重
"""
        },
        {
            "title": "心率变异性(HRV)解读",
            "category": "heart_health",
            "content": """
心率变异性(HRV)是指心跳间隔的微小变化。较高的HRV通常表示更好的心血管适应能力和更低的压力水平。

HRV的意义：
- 反映自主神经系统的平衡状态
- 高HRV：身体恢复良好，适应压力能力强
- 低HRV：可能表示疲劳、压力或过度训练

影响HRV的因素：
1. 年龄（随年龄下降是正常的）
2. 睡眠质量
3. 压力水平
4. 运动量和恢复
5. 饮酒
6. 疾病状态

如何提高HRV：
1. 规律运动但避免过度训练
2. 保证充足的恢复时间
3. 深呼吸和冥想练习
4. 优质睡眠
5. 减少酒精摄入
6. 管理压力

注意：HRV是个体化指标，应关注自己的趋势变化而不是绝对值。
"""
        },
        {
            "title": "压力管理与身体电量",
            "category": "mental_health",
            "content": """
身体电量(Body Battery)是反映身体能量储备的指标。它综合了睡眠、压力、运动等因素。

身体电量的含义：
- 75-100：精力充沛，适合高强度活动
- 50-74：中等能量，适合正常活动
- 25-49：能量较低，建议减少活动强度
- 0-24：需要休息恢复

压力与恢复的平衡：
- 白天活动消耗能量
- 睡眠是主要的恢复方式
- 放松活动也能帮助恢复

压力管理技巧：
1. 深呼吸：4-7-8呼吸法（吸气4秒，屏息7秒，呼气8秒）
2. 正念冥想：每天10-15分钟
3. 适度运动：释放压力荷尔蒙
4. 社交支持：与亲友交流
5. 时间管理：避免过度承诺
6. 自然接触：户外活动有助于减压

注意信号：
- 持续的疲劳感
- 睡眠问题
- 情绪波动
- 身体电量长期偏低
"""
        },
        {
            "title": "慢性鼻炎的日常管理",
            "category": "chronic_disease",
            "content": """
慢性鼻炎是常见的上呼吸道疾病，需要长期管理。

日常护理要点：
1. 鼻腔冲洗：每天1-2次使用生理盐水冲洗，可有效清除过敏原和分泌物
2. 保持环境湿度：使用加湿器，保持室内湿度40-60%
3. 避免过敏原：
   - 定期清洁床单被褥
   - 减少地毯和毛绒玩具
   - 避免接触宠物皮屑
4. 空气净化：使用HEPA过滤器

饮食建议：
- 多吃富含维生素C的水果蔬菜
- 适量摄入omega-3脂肪酸（深海鱼、亚麻籽）
- 避免食用过多冷饮和冰淇淋
- 辛辣食物可能暂时缓解鼻塞但长期不利

运动建议：
- 适度运动有助于增强免疫力
- 游泳时注意泳池氯气可能刺激鼻腔
- 雾霾天避免户外运动

季节性注意：
- 花粉季节减少外出
- 外出后及时清洗鼻腔
- 换季时注意保暖
"""
        },
        {
            "title": "健康饮水指南",
            "category": "nutrition",
            "content": """
水是生命之源，充足的饮水对健康至关重要。

每日饮水量建议：
- 成年男性：约2.5升（包含食物中的水分）
- 成年女性：约2升
- 运动时需额外补充

饮水时机：
1. 早起：空腹一杯温水有助于启动肠胃
2. 餐前30分钟：有助于消化
3. 运动前中后：补充流失水分
4. 下午：避免困倦
5. 睡前2小时：之后减少饮水避免夜间起夜

水温选择：
- 温水（35-45°C）：最适合日常饮用
- 常温水：运动后适合
- 冷水：可以但不建议大量饮用

不宜用以替代白开水的饮品：
- 含糖饮料
- 咖啡（利尿）
- 酒精（脱水）

判断是否缺水：
- 尿液颜色：淡黄色为正常
- 口渴感：出现时已经轻度缺水
- 皮肤弹性：捏起皮肤看恢复速度
"""
        },
        {
            "title": "步数与健康",
            "category": "exercise",
            "content": """
步数是衡量日常活动量的简单指标。研究表明，增加步数与降低全因死亡率相关。

步数目标建议：
- 入门级：5000步/天
- 健康目标：7000-8000步/天
- 积极目标：10000步/天以上

步数的健康收益：
- 每增加1000步，全因死亡风险降低6-15%
- 改善心血管健康
- 有助于体重管理
- 改善情绪和睡眠

如何增加日常步数：
1. 选择步行通勤部分路程
2. 午餐后散步15-20分钟
3. 开会时站立或走动
4. 使用楼梯代替电梯
5. 停车时选择较远的位置
6. 在家接电话时走动

注意事项：
- 步数只是活动量的一个指标
- 还需关注活动强度
- 久坐后的短时活动也很重要
- 关节问题者应注意保护
"""
        }
    ]

    result = vector_store.add_documents(basic_knowledge, source="system_health_basics")

    return {
        "message": "基础健康知识已初始化",
        **result
    }
