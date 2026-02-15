"""
夸克搜索服务
使用阿里云智能搜索服务 (IQS) 为健康顾问提供实时信息
"""
import asyncio
import logging
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 阿里云配置
ALIYUN_ACCESS_KEY_ID = os.environ.get('ALIYUN_ACCESS_KEY_ID', '')
ALIYUN_ACCESS_KEY_SECRET = os.environ.get('ALIYUN_ACCESS_KEY_SECRET', '')


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    link: str
    snippet: str
    published_time: Optional[str] = None
    main_text: Optional[str] = None
    summary: Optional[str] = None


class QuarkSearchClient:
    """夸克搜索客户端"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from alibabacloud_iqs20241111.client import Client
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=ALIYUN_ACCESS_KEY_ID,
                access_key_secret=ALIYUN_ACCESS_KEY_SECRET,
            )
            config.endpoint = "iqs.cn-zhangjiakou.aliyuncs.com"
            self._client = Client(config)
        return self._client

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """执行搜索"""
        from alibabacloud_iqs20241111 import models as iqs_models
        from alibabacloud_tea_util import models as util_models

        client = self._get_client()

        contents_obj = iqs_models.RequestContents()
        if hasattr(contents_obj, 'items'):
            contents_obj.items = ["mainText", "summary"]

        search_input = iqs_models.UnifiedSearchInput(
            query=query[:100],
            engine_type="GenericAdvanced",
            time_range="NoLimit",
            contents=contents_obj,
        )
        request = iqs_models.UnifiedSearchRequest(body=search_input)

        runtime = util_models.RuntimeOptions(
            read_timeout=15000,
            connect_timeout=5000,
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.unified_search_with_options(request, {}, runtime)
        )

        results = []
        if response and response.body:
            page_items = getattr(response.body, 'page_items', None) or []
            for item in page_items[:max_results]:
                results.append(SearchResult(
                    title=getattr(item, 'title', '') or '',
                    link=getattr(item, 'link', '') or '',
                    snippet=getattr(item, 'snippet', '') or '',
                    published_time=getattr(item, 'published_time', None),
                    main_text=getattr(item, 'main_text', None),
                    summary=getattr(item, 'summary', None),
                ))

        return results

    async def search_with_context(self, query: str, max_results: int = 5, context_length: int = 300) -> str:
        """搜索并返回格式化的上下文文本"""
        try:
            results = await self.search(query, max_results)
            if not results:
                return ""

            parts = []
            for i, r in enumerate(results, 1):
                content = r.summary or r.main_text or r.snippet
                if content and len(content) > context_length:
                    content = content[:context_length] + "..."
                if content:
                    parts.append(f"{i}. {r.title}\n   {content}")
                    if r.published_time:
                        parts.append(f"   发布时间: {r.published_time}")

            return "\n".join(parts) if parts else ""
        except Exception as e:
            logger.warning(f"夸克搜索失败: {e}")
            return ""


# 全局单例
_client: Optional[QuarkSearchClient] = None


def get_search_client() -> Optional[QuarkSearchClient]:
    """获取搜索客户端（如果配置了阿里云密钥）"""
    global _client
    if not ALIYUN_ACCESS_KEY_ID or not ALIYUN_ACCESS_KEY_SECRET:
        return None
    if _client is None:
        try:
            _client = QuarkSearchClient()
            logger.info("夸克搜索客户端已初始化")
        except Exception as e:
            logger.warning(f"夸克搜索客户端初始化失败: {e}")
            return None
    return _client
