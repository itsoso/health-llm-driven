"""
向量存储服务

使用 Chroma 作为向量数据库，存储和检索健康知识文档
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.utils.runtime_data import runtime_data_path

logger = logging.getLogger(__name__)

# 尝试导入 chromadb
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb 未安装，知识库功能将不可用。请运行: pip install chromadb")

# 尝试导入 OpenAI embeddings
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class VectorStoreService:
    """
    向量存储服务

    使用 Chroma 进行向量存储和相似度检索
    支持 OpenAI embeddings 或本地 embeddings
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "health_knowledge"
    ):
        self.persist_directory = (
            persist_directory
            if persist_directory is not None
            else str(runtime_data_path("knowledge_base"))
        )
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.openai_client = None
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self._embedding_disabled_until = 0  # 熔断时间戳
        self._fallback_client = None  # DashScope 容灾客户端
        self._fallback_model = "text-embedding-v3"

        self._initialize()

    def _initialize(self):
        """初始化向量存储"""
        if not CHROMA_AVAILABLE:
            logger.error("Chroma 不可用，无法初始化向量存储")
            return

        try:
            # 确保目录存在
            os.makedirs(self.persist_directory, exist_ok=True)

            # 初始化 Chroma 客户端（持久化模式）
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )

            # 获取或创建集合
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "健康知识库"}
            )

            logger.info(f"向量存储初始化成功，集合: {self.collection_name}")
            logger.info(f"当前文档数量: {self.collection.count()}")

            # 初始化 OpenAI 客户端（用于 embeddings）
            from app.config import settings
            if OPENAI_AVAILABLE and settings.openai_api_key:
                client_kwargs = {"api_key": settings.openai_api_key}
                if settings.openai_base_url:
                    client_kwargs["base_url"] = settings.openai_base_url
                self.openai_client = OpenAI(**client_kwargs)
                logger.info("OpenAI embeddings 已启用")
            else:
                logger.warning("OpenAI 未配置，将使用 Chroma 默认 embeddings")

            # 初始化 DashScope 容灾客户端
            fallback_key = getattr(settings, "llm_vision_api_key", None)
            if OPENAI_AVAILABLE and fallback_key:
                self._fallback_client = OpenAI(
                    api_key=fallback_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
                logger.info("DashScope embeddings 容灾已启用")

        except Exception as e:
            logger.error(f"向量存储初始化失败: {e}")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.collection is not None

    def _get_embeddings(self, texts: List[str], batch_size: int = 50) -> List[List[float]]:
        """
        获取文本的向量表示（分批处理）
        OpenAI 优先，失败自动 fallback 到 DashScope
        """
        if not self.openai_client and not self._fallback_client:
            return None

        import time
        # 熔断期内直接走 fallback
        use_fallback = time.time() < self._embedding_disabled_until

        if not use_fallback and self.openai_client:
            result = self._call_embedding(self.openai_client, self.embedding_model, texts, batch_size)
            if result is not None:
                return result
            # 主路径失败，尝试 fallback
            logger.warning("OpenAI embeddings 失败，尝试 DashScope 容灾")

        if self._fallback_client:
            result = self._call_embedding(self._fallback_client, self._fallback_model, texts, batch_size)
            if result is not None:
                return result

        return None

    def _call_embedding(self, client, model: str, texts: List[str], batch_size: int) -> List[List[float]]:
        """调用单个 embedding 提供商"""
        import time
        try:
            all_embeddings = []
            total_batches = (len(texts) + batch_size - 1) // batch_size

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = client.embeddings.create(model=model, input=batch)
                all_embeddings.extend([item.embedding for item in response.data])

            logger.info(f"embeddings 完成({model})，共 {len(all_embeddings)} 个")
            return all_embeddings

        except Exception as e:
            error_msg = str(e)
            logger.error(f"embeddings 失败({model}): {error_msg}")
            if "insufficient_quota" in error_msg or "429" in error_msg:
                self._embedding_disabled_until = time.time() + 600
                logger.warning(f"{model} 配额耗尽/限流，熔断 10 分钟")
            return None

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        添加文档到向量存储

        Args:
            documents: 文档列表，每个文档应包含:
                - content: 文档内容
                - title: 标题（可选）
                - category: 分类（可选）
                - metadata: 其他元数据（可选）
            source: 来源标识

        Returns:
            添加结果统计
        """
        if not self.is_available():
            return {"success": False, "error": "向量存储不可用"}

        try:
            ids = []
            contents = []
            metadatas = []

            for i, doc in enumerate(documents):
                doc_id = f"{source}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                content = doc.get("content", "")

                if not content.strip():
                    continue

                # 基础元数据
                metadata = {
                    "source": source,
                    "title": doc.get("title", ""),
                    "category": doc.get("category", "general"),
                    "created_at": datetime.now().isoformat(),
                }

                # 合并额外的元数据，并处理不支持的类型
                extra_metadata = doc.get("metadata", {})
                for key, value in extra_metadata.items():
                    # ChromaDB 只支持 str, int, float, bool, None
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        metadata[key] = value
                    elif isinstance(value, list):
                        # 将列表转换为逗号分隔的字符串
                        metadata[key] = ", ".join(str(v) for v in value)
                    elif isinstance(value, dict):
                        # 将字典转换为 JSON 字符串
                        import json
                        metadata[key] = json.dumps(value, ensure_ascii=False)
                    else:
                        # 其他类型转换为字符串
                        metadata[key] = str(value)

                ids.append(doc_id)
                contents.append(content)
                metadatas.append(metadata)

            if not contents:
                return {"success": False, "error": "没有有效的文档内容"}

            # 获取 embeddings（如果使用 OpenAI）
            embeddings = self._get_embeddings(contents)

            # 添加到集合
            if embeddings:
                self.collection.add(
                    ids=ids,
                    documents=contents,
                    metadatas=metadatas,
                    embeddings=embeddings
                )
            else:
                # 使用 Chroma 默认 embeddings
                self.collection.add(
                    ids=ids,
                    documents=contents,
                    metadatas=metadatas
                )

            logger.info(f"成功添加 {len(ids)} 个文档到知识库")
            return {
                "success": True,
                "added_count": len(ids),
                "total_count": self.collection.count()
            }

        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return {"success": False, "error": str(e)}

    def search(
        self,
        query: str,
        n_results: int = 5,
        category: Optional[str] = None,
        source: Optional[str] = None,
        conditions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相关文档

        Args:
            query: 搜索查询
            n_results: 返回结果数量
            category: 按分类过滤
            source: 按来源过滤
            conditions: 用户健康条件标签列表，用于分层检索

        Returns:
            相关文档列表
        """
        if not self.is_available():
            return []

        try:
            # 构建过滤条件
            where_filter = None
            if category or source:
                conditions_list = []
                if category:
                    conditions_list.append({"category": category})
                if source:
                    conditions_list.append({"source": source})

                if len(conditions_list) == 1:
                    where_filter = conditions_list[0]
                else:
                    where_filter = {"$and": conditions_list}

            # 获取查询的 embedding
            query_embedding = None
            if self.openai_client:
                embeddings = self._get_embeddings([query])
                if embeddings:
                    query_embedding = embeddings[0]

            # 如果有用户条件标签，执行分层检索
            if conditions:
                return self._search_with_conditions(
                    query, query_embedding, conditions, n_results, where_filter
                )

            # 普通搜索
            return self._execute_search(query, query_embedding, n_results, where_filter)

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def _execute_search(
        self,
        query: str,
        query_embedding: Optional[List[float]],
        n_results: int,
        where_filter: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """执行单次向量搜索"""
        try:
            if query_embedding:
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where_filter,
                    include=["documents", "metadatas", "distances"]
                )
            else:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where_filter,
                    include=["documents", "metadatas", "distances"]
                )

            formatted_results = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    formatted_results.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": results["distances"][0][i] if results.get("distances") else None,
                        "relevance_score": 1 - (results["distances"][0][i] if results.get("distances") else 0)
                    })

            return formatted_results
        except Exception as e:
            logger.error(f"搜索执行失败: {e}")
            return []

    def _search_with_conditions(
        self,
        query: str,
        query_embedding: Optional[List[float]],
        conditions: List[str],
        n_results: int,
        base_filter: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        条件感知的分层检索

        1. 搜索匹配用户条件的 Layer 2 文档
        2. 搜索通用 Layer 1 文档
        3. 合并去重，条件匹配的优先
        """
        all_results = []
        seen_contents = set()

        # Phase 1: 搜索条件匹配的文档
        for condition in conditions[:5]:  # 最多5个条件避免过多查询
            try:
                condition_filter = {"conditions": {"$contains": condition}}
                if base_filter:
                    condition_filter = {"$and": [base_filter, condition_filter]}

                results = self._execute_search(query, query_embedding, n_results, condition_filter)
                for r in results:
                    content_key = r["content"][:100]  # 用前100字符去重
                    if content_key not in seen_contents:
                        seen_contents.add(content_key)
                        r["metadata"]["matched_condition"] = condition
                        all_results.append(r)
            except Exception as e:
                logger.debug(f"条件 '{condition}' 检索失败（可能无匹配文档）: {e}")
                continue

        # Phase 2: 搜索通用文档 (Layer 1)
        try:
            universal_filter = {"layer": "1"}
            if base_filter:
                universal_filter = {"$and": [base_filter, universal_filter]}

            universal_results = self._execute_search(query, query_embedding, n_results, universal_filter)
            for r in universal_results:
                content_key = r["content"][:100]
                if content_key not in seen_contents:
                    seen_contents.add(content_key)
                    all_results.append(r)
        except Exception as e:
            logger.debug(f"通用知识检索失败: {e}")

        # Phase 3: 如果条件检索结果不足，补充无条件通用搜索
        if len(all_results) < n_results:
            try:
                fallback_results = self._execute_search(query, query_embedding, n_results, base_filter)
                for r in fallback_results:
                    content_key = r["content"][:100]
                    if content_key not in seen_contents:
                        seen_contents.add(content_key)
                        all_results.append(r)
            except Exception:
                pass

        # 按相关度排序，截取
        all_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return all_results[:n_results]

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        if not self.is_available():
            return {"available": False}

        try:
            count = self.collection.count()

            # 获取分类统计
            # 注意：Chroma 不直接支持聚合查询，这里简化处理

            return {
                "available": True,
                "total_documents": count,
                "collection_name": self.collection_name,
                "persist_directory": self.persist_directory,
                "embedding_model": self.embedding_model if self.openai_client else "default"
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"available": False, "error": str(e)}

    def delete_by_source(self, source: str) -> Dict[str, Any]:
        """删除指定来源的所有文档"""
        if not self.is_available():
            return {"success": False, "error": "向量存储不可用"}

        try:
            # Chroma 支持按条件删除
            self.collection.delete(
                where={"source": source}
            )
            logger.info(f"已删除来源为 '{source}' 的所有文档")
            return {"success": True, "source": source}
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return {"success": False, "error": str(e)}

    def clear_all(self) -> Dict[str, Any]:
        """清空所有文档（谨慎使用）"""
        if not self.is_available():
            return {"success": False, "error": "向量存储不可用"}

        try:
            # 删除并重新创建集合
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "健康知识库"}
            )
            logger.info("已清空知识库")
            return {"success": True}
        except Exception as e:
            logger.error(f"清空知识库失败: {e}")
            return {"success": False, "error": str(e)}


# 懒加载单例 — 避免 import 时触发 ChromaDB 模型下载阻塞 worker
_vector_store_instance: Optional[VectorStoreService] = None

def _get_vector_store() -> VectorStoreService:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStoreService()
    return _vector_store_instance

class _LazyVectorStore:
    """代理对象，首次访问属性时才初始化 VectorStoreService"""
    def __getattr__(self, name):
        return getattr(_get_vector_store(), name)

vector_store = _LazyVectorStore()
