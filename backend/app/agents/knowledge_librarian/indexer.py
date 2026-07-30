"""
知识库索引器 —— 将得到 wiki 的健康相关 MD 文件索引到 ChromaDB。

索引策略：
- 按段落切分（## 标题为分隔符）
- 每个 chunk 带 metadata: {source_file, section_title, domain}
- 首次启动时全量索引，之后按需增量

生产存储位置：/var/lib/health-app/runtime/knowledge_chromadb/
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from app.utils.runtime_data import runtime_data_path

logger = logging.getLogger(__name__)

# 本地开发用 ~/work/personal/down-dedao/wiki，服务器用 /opt/health-app/knowledge/dedao-wiki
_LOCAL_WIKI = Path(os.path.expanduser("~/work/personal/down-dedao/wiki"))
_SERVER_WIKI = Path("/opt/health-app/knowledge/dedao-wiki")
WIKI_DIR = _LOCAL_WIKI if _LOCAL_WIKI.exists() else _SERVER_WIKI
CHROMA_PERSIST_DIR = runtime_data_path("knowledge_chromadb")
COLLECTION_NAME = "health_knowledge"

# 健康关键词 — 用于过滤非健康文件
HEALTH_KEYWORDS = {
    "健康", "营养", "基因", "睡眠", "运动", "代谢", "心率", "血压",
    "免疫", "肠道", "菌群", "微生物", "长寿", "衰老", "抗氧化", "炎症",
    "心血管", "糖尿", "脂肪", "蛋白", "维生素", "矿物质", "补剂", "药物",
    "医学", "疾病", "治疗", "诊断", "细胞", "激素", "神经", "大脑",
    "减肥", "BMI", "体重", "卡路里", "膳食", "纤维", "胆固醇",
    "HRV", "VO2", "肌肉", "骨骼", "关节", "疫苗", "抗生素",
    "过敏", "鼻炎", "哮喘", "高血压", "高血糖", "高血脂", "痛风",
    # 器官 / 系统 / 血液学 / 内分泌 — 补全曾被过滤掉的科室段落
    "肝", "肾", "甲状腺", "内分泌", "血液", "血常规", "红细胞", "白细胞",
    "血小板", "血红蛋白", "贫血", "胃", "消化", "胆", "胰", "尿酸",
    "综合征", "结节", "囊肿", "息肉",
}


def _is_health_related(text: str) -> bool:
    return any(kw in text for kw in HEALTH_KEYWORDS)


def _chunk_markdown(text: str, source_file: str, max_chunk: int = 1500) -> List[Dict[str, Any]]:
    """把 MD 文件按 ## 标题切成 chunks。"""
    chunks: List[Dict[str, Any]] = []
    sections = re.split(r"\n(?=##\s)", text)

    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue

        # 提取标题
        title_match = re.match(r"^##\s*(.+)", section)
        title = title_match.group(1).strip() if title_match else ""

        # 如果 section 太长，再按段落拆
        if len(section) > max_chunk:
            paragraphs = section.split("\n\n")
            current = ""
            for para in paragraphs:
                if len(current) + len(para) > max_chunk and current:
                    if _is_health_related(current) or _is_health_related(title):
                        chunks.append({
                            "text": current.strip(),
                            "title": title,
                            "source": source_file,
                        })
                    current = para
                else:
                    current += "\n\n" + para if current else para
            if current.strip():
                if _is_health_related(current) or _is_health_related(title):
                    chunks.append({
                        "text": current.strip(),
                        "title": title,
                        "source": source_file,
                    })
        else:
            if _is_health_related(section) or _is_health_related(title):
                chunks.append({
                    "text": section,
                    "title": title,
                    "source": source_file,
                })

    return chunks


def _get_collection():
    """获取或创建 ChromaDB collection。"""
    try:
        import chromadb

        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "得到 wiki 健康知识库"},
        )
        return collection
    except ImportError:
        logger.warning("[knowledge] chromadb 未安装，知识库不可用")
        return None
    except Exception as e:
        logger.warning(f"[knowledge] ChromaDB 初始化失败: {e}")
        return None


def build_index(force: bool = False) -> Dict[str, int]:
    """
    构建/更新知识库索引。

    Returns: {"files_scanned": N, "chunks_indexed": N, "skipped": N}
    """
    collection = _get_collection()
    if collection is None:
        return {"error": "ChromaDB 不可用", "files_scanned": 0, "chunks_indexed": 0}

    if not WIKI_DIR.exists():
        return {"error": f"Wiki 目录不存在: {WIKI_DIR}", "files_scanned": 0, "chunks_indexed": 0}

    # 扫描所有 MD 文件
    md_files = list(WIKI_DIR.rglob("*.md"))
    total_chunks = 0
    skipped = 0

    # 获取已索引的 ID 集合（用于增量）
    existing_ids = set()
    if not force:
        try:
            result = collection.get(include=[])
            existing_ids = set(result.get("ids", []))
        except Exception:
            pass

    for md_file in md_files:
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if not _is_health_related(text):
            skipped += 1
            continue

        rel_path = str(md_file.relative_to(WIKI_DIR))
        chunks = _chunk_markdown(text, rel_path)

        ids_batch = []
        docs_batch = []
        metas_batch = []

        for chunk in chunks:
            chunk_id = hashlib.sha1(
                f"{rel_path}:{chunk['title']}:{chunk['text'][:100]}".encode()
            ).hexdigest()[:16]

            if chunk_id in existing_ids and not force:
                continue

            ids_batch.append(chunk_id)
            docs_batch.append(chunk["text"])
            metas_batch.append({
                "source": chunk["source"],
                "title": chunk["title"],
            })

        if ids_batch:
            try:
                collection.upsert(
                    ids=ids_batch,
                    documents=docs_batch,
                    metadatas=metas_batch,
                )
                total_chunks += len(ids_batch)
            except Exception as e:
                logger.warning(f"[knowledge] 索引 {rel_path} 失败: {e}")

    return {
        "files_scanned": len(md_files),
        "chunks_indexed": total_chunks,
        "skipped": skipped,
        "collection_total": collection.count() if collection else 0,
    }


def search_knowledge(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """
    检索知识库。

    Returns: [{text, source, title, distance}]
    """
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
        )

        items = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            items.append({
                "text": doc,
                "source": meta.get("source", ""),
                "title": meta.get("title", ""),
                "distance": round(dist, 4) if dist is not None else None,
            })
        return items
    except Exception as e:
        logger.warning(f"[knowledge] 检索失败: {e}")
        return []
