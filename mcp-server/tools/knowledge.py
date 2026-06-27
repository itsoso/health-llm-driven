"""系统知识库工具 - reviewed KB 查询与治理报告"""
import json
import logging
from typing import Any, Optional

from client import HealthAPIClient

logger = logging.getLogger(__name__)

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    """获取单例 HealthAPIClient 实例（懒初始化）"""
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


async def search_reviewed_knowledge(
    query: str,
    limit: int = 5,
    doc_type: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> str:
    """搜索已审核系统知识库。

    只返回后端 serving gate 允许的 reviewed local KB；外部搜索结果不会通过此工具直出。

    Args:
        query: 搜索词，例如 "葡萄柚 用药相互作用"
        limit: 返回条数，默认 5
        doc_type: 可选文档类型过滤，例如 "claim" / "entity" / "contraindication"
        entity_type: 可选实体类型过滤，例如 "condition" / "gene" / "supplement"
    """
    params: dict[str, Any] = {"q": query, "limit": limit}
    if doc_type:
        params["doc_type"] = doc_type
    if entity_type:
        params["entity_type"] = entity_type
    data = await get_client().get("/knowledge/search", params=params)
    return _json(data)


async def lookup_reviewed_knowledge_for_twin(twin: dict[str, Any]) -> str:
    """基于 Twin 摘要查找 reviewed 系统知识库命中项。

    Args:
        twin: 精简 Twin payload，字段可含 genetics、labs、wearable、medications、supplements、goals。
    """
    data = await get_client().post("/knowledge/lookup_for_twin", data=twin)
    return _json(data)


async def get_knowledge_coverage_report() -> str:
    """获取系统知识库 coverage report。

    需要后端 admin token；用于治理覆盖率、外部证据率、eval 覆盖和 unsupported 看板。
    """
    data = await get_client().get("/admin/knowledge/coverage_report")
    return _json(data)


async def get_knowledge_eval_report(case_ids: Optional[list[str]] = None) -> str:
    """运行系统知识库 reviewed eval cases。

    需要后端 admin token；不生成医疗建议，只返回 deterministic eval 结果。

    Args:
        case_ids: 可选 eval case id 列表；为空时运行默认 eval 集合。
    """
    params = {"case_id": case_ids} if case_ids else None
    data = await get_client().get("/admin/knowledge/eval_report", params=params)
    return _json(data)
