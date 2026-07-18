"""
Hybrid Search — LLM Wiki v2 阶段 C.

混合三路检索 + Reciprocal Rank Fusion (RRF):
1. **BM25**: 个人语料 (memory_facts + entities) 的关键字匹配, 自带中文 char-ngram 分词
2. **Graph traversal**: query 提到的 entity → 2-hop 邻域
3. **(后续)** Vector: ChromaDB 语义检索, 暂未接入

为什么不用 rank_bm25 / elasticsearch:
- 单用户语料量 < 10k 条, 内存版 BM25 秒级
- 中文 jieba 分词需要外部依赖, char + 2/3-gram 对短文本足够
- 持久化用 PG 即可, 不引入新基础设施

为什么用 RRF (rank fusion 而非 score 融合):
- 不同信号 score 不可比 (BM25 vs graph confidence)
- RRF 公式: score = sum(1 / (k + rank_i)), k=60
- 论文证明 RRF 在 IR 任务上稳定优于线性加权

调用方:
- orchestrator._inject_memory: 替换原有 facts + KG 双路注入, 改为单一 hybrid
- /api/v1/hybrid-search/me?q=...
"""
from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─────────────────────── 简易中文分词 ───────────────────────

# 原写法 r'..."\'""''\(\)...' 在 27 27 处提前闭合 raw string,
# 后段的 '\(\)' 是非 raw, Python 3.12 会报 SyntaxWarning.
# 用 triple-quoted raw string 避免单引号冲突.
_PUNCT = re.compile(r"""[\s　,，.。;；:：!！?？"'""''()（）\[\]【】{}<>《》/\\|@#$%^&*+=~`-]+""")
_ASCII = re.compile(r'[a-zA-Z0-9]+')
_CJK = re.compile(r'[一-鿿]')


def _tokenize(text: str) -> List[str]:
    """生成 token 列表:
    - 空白/标点 split
    - ASCII 单词整体保留 (lowercase)
    - 中文做 char + 2-gram (覆盖 '美托洛尔' '高血压' 之类多字词)
    """
    if not text:
        return []
    text = text.lower()
    # 先按标点切大段
    chunks = _PUNCT.split(text)
    tokens: List[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        # 提取 ASCII 词
        ascii_words = _ASCII.findall(chunk)
        tokens.extend(ascii_words)
        # 中文部分: char + bigram + trigram
        cjk_seq = "".join(_CJK.findall(chunk))
        if not cjk_seq:
            continue
        # 单字
        tokens.extend(list(cjk_seq))
        # 2-gram
        for i in range(len(cjk_seq) - 1):
            tokens.append(cjk_seq[i:i + 2])
        # 3-gram (有助 '美托洛尔' '甘油三酯' 之类)
        for i in range(len(cjk_seq) - 2):
            tokens.append(cjk_seq[i:i + 3])
    return tokens


# ─────────────────────── BM25 ───────────────────────


@dataclass
class Doc:
    """BM25 索引文档."""
    id: str             # 'fact:123' / 'entity:45'
    source_type: str    # 'fact' | 'entity'
    source_id: int
    text: str
    tokens: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MiniBM25:
    """简化 BM25, 单查询/单语料内存索引."""
    K1 = 1.5
    B = 0.75

    def __init__(self, docs: List[Doc]):
        self.docs = docs
        self.N = len(docs)
        self.avg_dl = sum(len(d.tokens) for d in docs) / max(1, self.N)
        # IDF
        df: Dict[str, int] = defaultdict(int)
        for d in docs:
            for t in set(d.tokens):
                df[t] += 1
        self.idf = {
            t: math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)
            for t, n in df.items()
        }

    def search(self, query: str, top_k: int = 20) -> List[Tuple[Doc, float]]:
        q_tokens = _tokenize(query)
        if not q_tokens or self.N == 0:
            return []
        scores: List[Tuple[Doc, float]] = []
        for d in self.docs:
            score = 0.0
            tf: Dict[str, int] = defaultdict(int)
            for t in d.tokens:
                tf[t] += 1
            dl = len(d.tokens)
            for q in q_tokens:
                if q not in tf:
                    continue
                idf = self.idf.get(q, 0.0)
                f = tf[q]
                norm = (f * (self.K1 + 1)) / (
                    f + self.K1 * (1 - self.B + self.B * dl / max(1, self.avg_dl))
                )
                score += idf * norm
            if score > 0:
                scores.append((d, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ─────────────────────── 语料构建 ───────────────────────


def _build_user_corpus(db: Session, user_id: int) -> List[Doc]:
    """拉用户的全部 active memory_facts + entities, 拼成 BM25 文档.

    单用户量级几千条以内, 即使每查询重建索引也没问题.
    后续可加 Redis 缓存 user_id → 索引 (TTL 60s).
    """
    from app.models.memory_fact import MemoryFact
    from app.models.health_kg import HealthEntity

    docs: List[Doc] = []

    # facts
    facts = db.query(MemoryFact).filter(
        MemoryFact.user_id == user_id,
        MemoryFact.superseded_at.is_(None),
    ).all()
    from app.services.memory_service import effective_memory_predicate

    for f in facts:
        predicate = effective_memory_predicate(
            f.predicate, object_value=f.object_value, tags=f.tags or [],
        )
        text = f"{f.subject} {predicate} {f.object_value} {f.object_unit or ''} " + \
               " ".join(f.tags or [])
        d = Doc(
            id=f"fact:{f.id}",
            source_type="fact",
            source_id=f.id,
            text=text,
            tokens=_tokenize(text),
            metadata={
                "tier": f.tier,
                "predicate": predicate,
                "confidence": f.effective_confidence,
                "tags": f.tags,
            },
        )
        docs.append(d)

    # entities
    entities = db.query(HealthEntity).filter(
        HealthEntity.user_id == user_id,
        HealthEntity.is_active == True,  # noqa: E712
    ).all()
    for e in entities:
        text = " ".join([e.canonical_name] + list(e.aliases or []))
        d = Doc(
            id=f"entity:{e.id}",
            source_type="entity",
            source_id=e.id,
            text=text,
            tokens=_tokenize(text),
            metadata={
                "type": e.type,
                "confidence": e.confidence,
            },
        )
        docs.append(d)

    return docs


# ─────────────────────── Graph 检索 ───────────────────────


def _graph_search(
    db: Session, user_id: int, query: str,
    *, max_seeds: int = 3, hops: int = 2, max_per_hop: int = 5,
) -> List[Tuple[str, float]]:
    """从 query 抽 mentioned entities → 2-hop 展开 → (doc_id, score) 列表.

    score 用 confidence × hop_decay (hop1=1.0, hop2=0.6, hop3=0.3).
    """
    from app.services.kg_service import mention_to_entities, expand_neighborhood

    seeds = mention_to_entities(db, user_id, query, max_entities=max_seeds)
    if not seeds:
        return []

    out: Dict[str, float] = {}
    HOP_DECAY = {1: 1.0, 2: 0.6, 3: 0.3}

    # seed 本身也算 hit
    for s in seeds:
        out[f"entity:{s.id}"] = max(out.get(f"entity:{s.id}", 0.0), s.confidence * 1.0)

    for s in seeds:
        nbrs = expand_neighborhood(db, user_id, s.id, hops=hops, max_per_hop=max_per_hop)
        for n in nbrs:
            doc_id = f"entity:{n['entity_id']}"
            decay = HOP_DECAY.get(n["hop"], 0.1)
            score = float(n["confidence"]) * decay
            out[doc_id] = max(out.get(doc_id, 0.0), score)

    return sorted(out.items(), key=lambda x: x[1], reverse=True)


# ─────────────────────── RRF 融合 ───────────────────────


def reciprocal_rank_fusion(
    rankings: List[List[Tuple[str, float]]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """标准 RRF: 多路 ranking 通过 1/(k+rank) 融合.

    rankings: 各路检索的 (doc_id, score) 列表, 已按 score desc 排序.
    返回融合后的 (doc_id, rrf_score) 列表.
    """
    fused: Dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, (doc_id, _) in enumerate(ranking, 1):
            fused[doc_id] += 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


# ─────────────────────── 主入口 ───────────────────────


@dataclass
class HybridHit:
    doc_id: str
    source_type: str  # 'fact' | 'entity'
    source_id: int
    rrf_score: float
    text_preview: str
    metadata: Dict[str, Any]


def hybrid_retrieve(
    db: Session, user_id: int, query: str,
    *, top_k: int = 10, bm25_k: int = 20, graph_k: int = 20,
) -> List[HybridHit]:
    """主入口: 跑 BM25 + Graph, RRF 融合, 返回 top_k.

    后续可加 Vector path (ChromaDB 个人 partition).
    """
    if not query or not query.strip():
        return []

    # 1) 构语料 + BM25
    corpus = _build_user_corpus(db, user_id)
    if not corpus:
        return []

    bm25 = MiniBM25(corpus)
    bm25_hits = bm25.search(query, top_k=bm25_k)
    bm25_ranking = [(d.id, score) for d, score in bm25_hits]

    # 2) Graph
    graph_ranking = _graph_search(db, user_id, query, hops=2, max_per_hop=5)[:graph_k]

    # 3) RRF 融合
    fused = reciprocal_rank_fusion([bm25_ranking, graph_ranking], k=60)

    # 4) 还原为 HybridHit
    doc_index: Dict[str, Doc] = {d.id: d for d in corpus}
    hits: List[HybridHit] = []
    for doc_id, rrf_score in fused[:top_k]:
        d = doc_index.get(doc_id)
        if not d:
            # entity 来自 graph 路径可能不在 BM25 corpus 内
            # (理论上 corpus 包含所有 entity, 这里防御)
            continue
        hits.append(HybridHit(
            doc_id=doc_id,
            source_type=d.source_type,
            source_id=d.source_id,
            rrf_score=rrf_score,
            text_preview=d.text[:160],
            metadata=d.metadata,
        ))
    return hits


def render_hits_for_prompt(hits: List[HybridHit], max_lines: int = 10) -> str:
    """LLM prompt 注入."""
    if not hits:
        return ""
    lines = ["## 个人知识检索 (BM25 + 图谱混合, 按相关性排)"]
    for h in hits[:max_lines]:
        kind = "📋 事实" if h.source_type == "fact" else "🔗 实体"
        conf = h.metadata.get("confidence", 0.5)
        lines.append(f"{kind} (rrf={h.rrf_score:.3f}, conf={conf:.2f}): {h.text_preview}")
    return "\n".join(lines)
