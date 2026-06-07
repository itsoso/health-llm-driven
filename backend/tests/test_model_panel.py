# -*- coding: utf-8 -*-
"""多模型 panel(RFC 方向八)回归。

钉:多数投票 + 一致度 + unanimous;空/归一化;run_panel 并行编排(mock provider)+
单模型失败降级不崩。真实"抓幻觉"效果需线上 eval,不在 CI 验。
"""
from unittest.mock import patch

import pytest

from app.services.llm.model_panel import aggregate_votes, run_panel


def test_aggregate_majority_and_agreement():
    out = aggregate_votes(["yes", "yes", "no"])
    assert out["decision"] == "yes" and out["n"] == 3
    assert out["agreement"] == round(2 / 3, 3) and out["unanimous"] is False


def test_aggregate_unanimous_and_normalize():
    out = aggregate_votes([" Yes ", "yes", "YES"])
    assert out["decision"] == "yes" and out["unanimous"] is True and out["agreement"] == 1.0


def test_aggregate_empty():
    out = aggregate_votes([None, "", "  "])
    assert out["decision"] is None and out["n"] == 0


@pytest.mark.asyncio
async def test_run_panel_parallel_with_mock():
    class _P:
        def __init__(self, txt): self.txt = txt
        async def chat(self, **kw): return {"content": self.txt}

    seq = iter([_P("安全"), _P("安全"), _P("不安全")])
    with patch("app.services.llm.factory._create_from_entry", side_effect=lambda e: next(seq)), \
         patch("app.services.llm.model_registry.get_model", side_effect=lambda m: object()):
        out = await run_panel([{"role": "user", "content": "q"}], ["m1", "m2", "m3"])
    assert out["answered"] == 3 and out["requested"] == 3
    labels = [r["text"] for r in out["responses"] if "text" in r]
    assert aggregate_votes(labels)["decision"] == "安全"  # 2:1 多数


@pytest.mark.asyncio
async def test_run_panel_degrades_on_failure():
    with patch("app.services.llm.model_registry.get_model", side_effect=lambda m: None):
        out = await run_panel([{"role": "user", "content": "q"}], ["bad1", "bad2"])
    assert out["answered"] == 0
    assert all("error" in r for r in out["responses"])
