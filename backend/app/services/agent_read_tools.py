"""D1 读拉类工具进程内直读实现 (garmin-sync 治理 Wave 3).

背景: agent_executor 的读工具过去对每个维度打 localhost 回环
(`_api_get(f"{base}{path}")`) 重入整个 FastAPI 中间件栈, 付跨-worker 饥饿 + 内层 60s
中间件连杀 + 双鉴权/双 JSON 税。本模块把这些**只读**维度改为进程内直读 —— 与
`health_read.py`(canonical 可穿戴/化验读层)同一"读层"概念, 但拆成独立模块以守 500 行预算
且随增量 B 增长。

**契约(每个 reader 都遵守)**:
- 签名 `read_x(db, user_id, ...) -> str`; 同步 DB 读(由 agent_executor._read_in_process
  在 fresh SessionLocal + 线程池里跑)。
- **user_id 隔离**: 每个查询显式 `filter(... user_id == user_id)`; user_id 为 None → 诚实
  Error 串, 绝不裸查。
- **数据等价**: 输出与旧 HTTP 端点的响应体**数据等价** —— 走与端点**相同的 response_model**
  序列化(或逐字段复刻端点的 dict 投影), 由 golden-master 测试逐维度钉死。D1 是纯 transport
  变更, LLM 所见绝不因换传输而漂移。
- **绝不调 build_twin**(其 Phase B 忽略传入 db 自开 SessionLocal 连真 PG)。只做具体表查询 /
  复用已有 service 读函数。
- 显示截断由调用方 `agent_executor._truncate_for_display` 统一施加(单一真源), 此处不截断。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import desc as sa_desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def read_weight(db: Session, user_id: Optional[int], *, limit: int = 10) -> str:
    """体重记录 — 镜像 GET /weight/records/me?limit=N (app/api/weight.py::get_my_weight_records)。

    端点无 start/end 过滤(tool 不传), order by record_date desc, limit N, 经
    WeightRecordResponse 序列化。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询体重"
    from app.models.weight import WeightRecord
    from app.schemas.weight import WeightRecordResponse

    rows = (
        db.query(WeightRecord)
        .filter(WeightRecord.user_id == user_id)
        .order_by(sa_desc(WeightRecord.record_date))
        .limit(limit)
        .all()
    )
    payload = [WeightRecordResponse.model_validate(r).model_dump(mode="json") for r in rows]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_genetic_profiles(db: Session, user_id: Optional[int]) -> str:
    """基因档案列表 — 镜像 GET /genetic/profiles/me (genetic_data.py::list_profiles)。

    仅暴露档案**元数据**(provider/date/report_id/notes), 不含变异位点(genetic variants 是
    另一维度, 增量 B)。逐字段复刻端点的 dict 投影以保数据等价。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询基因档案"
    from app.models.genetic_data import GeneticProfile

    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .order_by(sa_desc(GeneticProfile.test_date))
        .all()
    )
    payload = [
        {
            "id": p.id,
            "user_id": p.user_id,
            "test_provider": p.test_provider,
            "test_date": str(p.test_date),
            "report_id": p.report_id,
            "notes": p.notes,
            "created_at": str(p.created_at) if p.created_at else None,
        }
        for p in profiles
    ]
    return json.dumps(payload, ensure_ascii=False, default=str)


def read_supplement_daily_guide(db: Session, user_id: Optional[int]) -> str:
    """每日补剂动态指南 — 镜像 GET /supplements/daily-guide
    (supplements.py::get_supplement_daily_guide → get_daily_supplement_guide)。

    复用既有 service 函数(非 LLM, 确定性), target_date=None → 今天, 与端点一致。
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法获取补剂指南"
    from app.services.daily_supplement_guide import get_daily_supplement_guide

    guide = get_daily_supplement_guide(db, user_id, None)
    return json.dumps(guide, ensure_ascii=False, default=str)
