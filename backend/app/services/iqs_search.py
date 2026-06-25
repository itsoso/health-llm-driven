"""阿里云 IQS 实时搜索 — 给合成回答做 grounding(接地)降幻觉。

用途: orchestrator 合成回答前, 检索实时/外部事实(最新指南、药物信息、研究进展等),
注入 prompt 让模型"依据证据作答"而非凭训练记忆编造。

安全边界(医疗场景关键):
- 实时证据**只补充时效性/通用外部事实**, 不得覆盖用户个人健康数据 / specialist 裁决。
- 任何失败/超时/未配置 → 返回空串, **绝不阻断回答生成**(graceful degradation)。
- 凭据从 settings(.env)读, 端点张家口, 与 browser-llm-orchestrator 同源实现。
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "iqs.cn-zhangjiakou.aliyuncs.com"
_client = None  # 进程级单例


def _enabled() -> bool:
    return bool(
        getattr(settings, "aliyun_iqs_grounding_enabled", False)
        and settings.aliyun_access_key_id
        and settings.aliyun_access_key_secret
    )


def _get_client():
    global _client
    if _client is None:
        from alibabacloud_iqs20241111.client import Client
        from alibabacloud_tea_openapi import models as open_api_models

        cfg = open_api_models.Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
        )
        cfg.endpoint = _ENDPOINT
        _client = Client(cfg)
    return _client


async def _raw_search(query: str, max_results: int, time_range: str) -> List[dict]:
    from alibabacloud_iqs20241111 import models as iqs_models
    from alibabacloud_tea_util import models as util_models

    client = _get_client()
    contents = iqs_models.RequestContents()
    if hasattr(contents, "items"):
        contents.items = ["mainText", "summary", "rerankScore"]
    search_input = iqs_models.UnifiedSearchInput(
        query=query[:500], engine_type="GenericAdvanced",
        time_range=time_range, contents=contents,
    )
    request = iqs_models.UnifiedSearchRequest(body=search_input)
    runtime = util_models.RuntimeOptions(read_timeout=20000, connect_timeout=8000)
    resp = await client.unified_search_with_options_async(request, {}, runtime)
    out = []
    if resp and resp.body:
        for item in (getattr(resp.body, "page_items", None) or [])[:max_results]:
            out.append({
                "title": getattr(item, "title", "") or "",
                "link": getattr(item, "link", "") or "",
                "summary": getattr(item, "summary", None) or getattr(item, "snippet", "") or "",
                "published_time": getattr(item, "published_time", None),
            })
    return out


def _format_block(query: str, items: List[dict], max_chars: int = 2200) -> str:
    """格式化成可注入 synthesis prompt 的【实时检索证据】块。"""
    lines = [
        f"【实时检索证据 · 关于「{query[:40]}」· 共{len(items)}条】",
        "(以下为联网实时检索结果。仅用于补充时效性/外部通用事实, 引用时标来源序号;"
        "**不得覆盖**上文用户个人健康数据与专家裁决; 与本块无关的问题忽略此块、不要臆造。)",
    ]
    used = 0
    for i, it in enumerate(items, 1):
        body = (it.get("summary") or "").strip().replace("\n", " ")
        when = f" ({it['published_time']})" if it.get("published_time") else ""
        block = f"[{i}]{when} {it['title']}\n    {body[:280]}\n    来源: {it['link']}"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


async def fetch_realtime_evidence(
    query: str,
    *,
    max_results: int = 6,
    timeout_s: float = 6.0,
    time_range: str = "NoLimit",
) -> str:
    """检索实时证据并返回格式化【实时检索证据】块; 未启用/失败/超时/无结果 → 返回 ""。

    永不抛异常 — 调用方可无条件 await 并直接拼进 prompt。
    """
    if not _enabled() or not (query or "").strip():
        return ""
    try:
        items = await asyncio.wait_for(
            _raw_search(query, max_results, time_range), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        logger.warning(f"[iqs] 检索超时 {timeout_s}s, 降级无证据: {query[:40]}")
        return ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[iqs] 检索失败降级: {type(e).__name__}: {str(e)[:160]}")
        return ""
    if not items:
        return ""
    logger.info(f"[iqs] grounding 命中 {len(items)} 条: {query[:40]}")
    return _format_block(query, items)
