"""鼻炎打卡归位:health_record(rhinitis) → upsert HealthCheckin(单条/日滚动)。

旧设计每次打卡 POST /illness/episodes mint 一条 "鼻炎发作" → 无界堆积 active
(实测 36 条卡死),且 RhinitisSpecialist / rhinitis_trend 读的是 HealthCheckin
(rhinitis_today),根本收不到 chat 打卡。新设计写 HealthCheckin(按 checkin_date
upsert,sneeze_times 合并),既不堆 episode 又直达 specialist。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_rhinitis_routes_to_healthcheckin_not_illness_episode(db):
    from app.services.agent_executor import AgentExecutor, _write_receipt_from_tool_result

    executor = AgentExecutor(db)
    executor._current_user_id = 7

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 55, "checkin_date": "2026-07-16", "sneeze_count": 5})

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "rhinitis", "data": {"sneezing": 5, "congestion": 2, "runny_nose": 1}},
        )

    # 关键:走 HealthCheckin upsert,绝不再建 illness_episode
    assert captured["url"].endswith("/checkin/"), captured["url"]
    assert "/illness/episodes" not in captured["url"]
    p = captured["payload"]
    # sneeze_count 不裸传 —— 端点从合并后的 sneeze_times 单调派生(单一真源, 防写小)
    assert "sneeze_count" not in p
    assert "checkin_date" in p
    # 详情走 sneeze_times(端点按 time 合并追加),保留 congestion/runny_nose
    assert isinstance(p.get("sneeze_times"), list) and p["sneeze_times"]
    entry = p["sneeze_times"][0]
    assert entry["count"] == 5 and entry["congestion"] == 2 and entry["runny_nose"] == 1
    # 不写 notes —— 避免覆盖当日其它打卡备注
    assert "notes" not in p
    # 成功写入被识别为回执(id-based)
    assert json.loads(result).get("id") == 55
    receipt = _write_receipt_from_tool_result("health_record", "rhinitis", result)
    assert receipt is not None
    assert receipt["resource_type"] == "health_checkin"
    assert receipt["resource_id"] == "55"


@pytest.mark.asyncio
async def test_rhinitis_no_sneeze_still_checkin_no_zero_count(db):
    """只报鼻塞/流涕(无喷嚏)也走 HealthCheckin,不硬塞 sneeze_count=0(否则覆盖当日真值)。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 56})

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "rhinitis", "data": {"congestion": 3, "runny_nose": 2}},
        )

    assert captured["url"].endswith("/checkin/")
    assert "sneeze_count" not in captured["payload"]  # 没喷嚏就不塞 count
    assert captured["payload"]["sneeze_times"][0]["congestion"] == 3


def test_checkin_endpoint_sneeze_count_monotonic_from_ledger(client, auth_user_and_headers):
    """端点从 sneeze_times ledger 单调派生 sneeze_count —— 多次增量打卡累加、绝不写小。

    (safety review IMPORTANT-1:sneeze_count 多写入方 last-writer-wins 会把当天累计写小 →
    压掉 rhinitis_trend 的 worsening 就医推送。端点求和 + max-guard 收口。)
    """
    _user, headers = auth_user_and_headers
    day = "2026-07-16"

    r1 = client.post("/api/v1/checkin/", headers=headers, json={
        "checkin_date": day, "sneeze_times": [{"time": "09:00", "count": 5}],
    })
    assert r1.status_code == 200, r1.text
    assert r1.json()["sneeze_count"] == 5

    # 又 3 次(不同 time)→ ledger 求和 8, 不是被 3 覆盖
    r2 = client.post("/api/v1/checkin/", headers=headers, json={
        "checkin_date": day, "sneeze_times": [{"time": "14:00", "count": 3}],
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["sneeze_count"] == 8

    # 再 1 次 → 9;单调递增,任何一步都不把当天累计拉低
    r3 = client.post("/api/v1/checkin/", headers=headers, json={
        "checkin_date": day, "sneeze_times": [{"time": "16:00", "count": 1}],
    })
    assert r3.status_code == 200, r3.text
    assert r3.json()["sneeze_count"] == 9


def test_undo_latest_rhinitis_event_is_scoped_and_keeps_the_day(client, db, auth_user_and_headers):
    from app.models.health_checkin import HealthCheckin
    from app.models.user import User
    from app.services.auth import auth_service

    user, headers = auth_user_and_headers
    day = "2026-07-17"
    created = client.post("/api/v1/checkin/", headers=headers, json={
        "checkin_date": day,
        "sneeze_times": [
            {"time": "14:00", "count": 2},
            {"time": "09:00", "count": 1},
        ],
    })
    assert created.status_code == 200, created.text
    checkin_id = created.json()["id"]

    undone = client.delete(
        f"/api/v1/checkin/{checkin_id}/rhinitis/latest",
        headers=headers,
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["resource_type"] == "health_checkin"
    assert undone.json()["undone"]["count"] == 2
    row = db.query(HealthCheckin).filter(HealthCheckin.id == checkin_id).one()
    assert row.sneeze_times == [{"time": "09:00", "count": 1}]
    assert row.sneeze_count == 1

    other = User(
        username="rhinitis_other",
        email="rhinitis_other@example.com",
        hashed_password="hashed_password",
        name="其他用户",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    other_token = auth_service.create_access_token({"sub": str(other.id)})
    forbidden = client.delete(
        f"/api/v1/checkin/{checkin_id}/rhinitis/latest",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert forbidden.status_code == 404
