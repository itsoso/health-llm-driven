# -*- coding: utf-8 -*-
"""Cross-Source Validator —— 跨设备同指标一致性裁决。

多源(Garmin / Apple Watch / RingConn)同指标差异过大 → 标记数据可疑,并给出"暂以谁为准"。
有异常才产出 finding;无异常 / 单源不产出(不制造噪声)。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)

WINDOW_DAYS = 7


class CrossSourceValidatorSpecialist:
    """同时戴 ≥2 台设备时,检测同指标跨源异常。"""

    name = "cross_source_validator"
    category = "data_quality"

    # twin.meta.data_sources 是 collector 类别(garmin/labs/cgm...),不是设备级源,
    # 无法据此判断"几台设备";真正的 per-device 计数在 GarminData.data_source,需 db。
    # 所以 applies_to 只做"有穿戴数据 + 相关意图"的粗筛,真正的 ≥2 设备门槛交给 run:
    # detect_cross_source_anomalies 在不足两源同指标时本就返回空,不会产噪声。
    _TRIGGER_CATEGORIES = {"recovery", "longitudinal", "safety"}

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        sources = getattr(twin.meta, "data_sources", None) or []
        if "garmin" not in sources:
            return False  # 没有穿戴数据 → 跨源无从谈起
        if self._TRIGGER_CATEGORIES & set(intent.categories):
            return True
        # 显式提到设备/数据质量的查询也触发
        q = (intent.raw_query or "").lower()
        return any(k in q for k in ("设备", "手表", "戒指", "数据准", "数据可疑", "对不上", "一致"))

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        db = context.get("db")

        def _elapsed() -> int:
            return int((time.monotonic() - t0) * 1000)

        if db is None:
            # 没有 db 无法取窗口数据 —— 不假装成功,产出空(标记原因到 raw)。
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary="跨源校验跳过:缺少数据库会话",
                findings=[],
                raw={"skipped": "no_db"},
                ms_elapsed=_elapsed(),
            )

        try:
            from app.services.cross_source_validator import detect_cross_source_anomalies

            anomalies = detect_cross_source_anomalies(
                db, twin.meta.user_id, days=WINDOW_DAYS
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[specialist.cross_source_validator] 执行失败: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"跨源校验失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=_elapsed(),
            )

        if not anomalies:
            # 无异常 → 不制造噪声,产出空 finding(summary 给个干净状态)。
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary="多源数据一致,未发现跨源异常",
                findings=[],
                raw={"anomaly_count": 0, "window_days": WINDOW_DAYS},
                ms_elapsed=_elapsed(),
            )

        findings = [
            {
                "metric": a["metric"],
                "label": a["label"],
                "sources": a["sources"],
                "outlier_source": a["outlier_source"],
                "deviation_pct": a["deviation_pct"],
                "trusted_source": a["trusted_source"],
                "hint": a["hint"],
            }
            for a in anomalies
        ]
        n = len(findings)
        metrics_str = "、".join(a["label"] for a in anomalies[:3])
        summary = f"{n} 项指标跨源差异过大({metrics_str}),相关源数据可疑"

        return SpecialistFinding(
            specialist_name=self.name,
            category=self.category,
            summary=summary,
            findings=findings,
            raw={"anomaly_count": n, "window_days": WINDOW_DAYS},
            ms_elapsed=_elapsed(),
        )
