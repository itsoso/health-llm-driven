# -*- coding: utf-8 -*-
"""多模态录入:化验单拍照解析(Next Horizon Tier 5)回归。

钉:JSON 解析确定性正确;箭头/脏值清洗;非数值丢弃不猜;端点 mock vision 返回结构。
真实 OCR 准确率非 CI 可验(vision 非确定性),故只测解析逻辑 + 端点契约。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.lab_photo_parse import parse_lab_items


def test_parse_clean_json():
    raw = json.dumps({"items": [
        {"item_name": "白蛋白", "value": "45", "unit": "g/L"},
        {"item_name": "肌酐", "value": "80", "unit": "umol/L"},
    ]}, ensure_ascii=False)
    out = parse_lab_items(raw)
    assert len(out) == 2
    assert out[0] == {"item_name": "白蛋白", "value": 45.0, "unit": "g/L"}


def test_parse_strips_arrows_and_drops_nonnumeric():
    raw = '```json\n{"items":[{"item_name":"血糖","value":"5.7↑","unit":"mmol/L"},' \
          '{"item_name":"乙肝","value":"阴性","unit":null},' \
          '{"item_name":"","value":"3","unit":null}]}\n```'
    out = parse_lab_items(raw)
    assert len(out) == 1                       # 阴性(非数值)+ 空名 都丢弃
    assert out[0]["item_name"] == "血糖" and out[0]["value"] == 5.7


def test_parse_garbage_returns_empty():
    assert parse_lab_items("看不清") == []
    assert parse_lab_items('{"items": "oops"}') == []
    assert parse_lab_items("") == []


@pytest.mark.asyncio
async def test_parse_lab_photo_uses_vision():
    from app.services import lab_photo_parse as m
    fake = AsyncMock(return_value='{"items":[{"item_name":"白蛋白","value":"45","unit":"g/L"}]}')
    with patch("app.services.llm.get_vision_provider") as gp:
        gp.return_value.chat_with_vision = fake
        out = await m.parse_lab_photo("BASE64", "jpeg")
    assert out == [{"item_name": "白蛋白", "value": 45.0, "unit": "g/L"}]
    assert fake.called


def test_endpoint_requires_auth(client):
    r = client.post("/api/v1/medical-exams/parse-photo", json={"image_base64": "x"})
    assert r.status_code in (401, 403)
