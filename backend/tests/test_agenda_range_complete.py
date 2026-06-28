"""议程区间视图 + 统一完成路由(R1 补全)。

钉:① /range 列常驻每日协议 + 窗口内复查 ② 窗口外复查不进 ③ /complete 经议程路由完成协议
(写真实记录,today 反映)④ 不支持的来源 400。"""
from datetime import date, datetime, timezone


def _freeze_agenda_today(monkeypatch, frozen: date) -> None:
    from app.services import agenda_service, health_problem_service

    monkeypatch.setattr(agenda_service, "get_user_today", lambda db, uid: frozen)
    monkeypatch.setattr(health_problem_service, "get_user_today", lambda db, uid: frozen)


def test_range_recurring_and_scheduled(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=h)  # 每日协议
    client.post("/api/v1/problems", headers=h, json={
        "name": "近期复查", "follow_up": {"next_due": "2020-02-02", "what_to_check": "x"}})  # 已逾期(窗口内)
    r = client.get("/api/v1/agenda/range?days=7", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(rp["domain"] == "hydration" for rp in body["recurring_protocols"])
    assert any("近期复查" in s["title"] for s in body["scheduled"])


def test_range_excludes_far_checkup(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/problems", headers=h, json={
        "name": "远期复查", "follow_up": {"next_due": "2027-12-31", "what_to_check": "x"}})
    body = client.get("/api/v1/agenda/range?days=7", headers=h).json()
    assert all("远期复查" not in s["title"] for s in body["scheduled"])


def test_complete_via_agenda_routes_to_protocol(client, auth_user_and_headers):
    """/agenda/complete 现走议程脊柱闭环:翻 HealthEvent 生命周期 + 双轨回写真实记录。

    响应是旧 shape 超集(object_type/object_id 保留)+ 生命周期(agenda_status/event_id/
    wrote/idempotent)。协议真实记录仍落库 → today 反映完成。
    """
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_protocol", "object_id": pid, "track": "protocol"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object_type"] == "health_protocol" and body["object_id"] == pid
    assert body["agenda_status"] == "done"
    assert body["wrote"] is True
    assert isinstance(body["event_id"], int)
    # today 反映完成(协议真实记录已落库)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    assert next(i for i in items if i["type"] == "hydration")["status"] == "completed"


def test_complete_unsupported_source_400(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_problem", "object_id": 1})
    assert r.status_code == 400


def test_complete_nonexistent_protocol_404(client, auth_user_and_headers):
    """协议不存在 / 非本人 → 404(not-found,与 med/supplement 一致);不静默假装成功。"""
    _, h = auth_user_and_headers
    r = client.post("/api/v1/agenda/complete", headers=h,
                    json={"object_type": "health_protocol", "object_id": 999999})
    assert r.status_code == 404


def test_range_runtime_mode_returns_rolling_projection(client, auth_user_and_headers, monkeypatch):
    _, h = auth_user_and_headers
    _freeze_agenda_today(monkeypatch, date(2026, 6, 28))

    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    assert client.post("/api/v1/problems", headers=h, json={
        "name": "血压复查",
        "follow_up": {"next_due": "2026-06-30", "what_to_check": "家庭血压连续偏高"},
    }).status_code == 200

    r = client.get("/api/v1/agenda/range?days=7&mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "runtime"
    assert body["horizon_days"] == 7
    assert body["start"] == "2026-06-28"
    assert body["end"] == "2026-07-04"
    assert len(body["days"]) == 7
    assert body["next_action"] is not None
    assert body["next_action"]["runtime_context"]["replan_reason"]
    assert body["days"][0]["is_today"] is True
    assert body["days"][0]["next_action"]["runtime_context"]["safety_boundary"]

    future_protocol_items = [
        item
        for day in body["days"][1:]
        for window in day["time_windows"]
        for item in window["items"]
        if item["source"]["object_type"] == "health_protocol"
    ]
    assert future_protocol_items
    assert all(item["runtime_context"]["verification_window"] for item in future_protocol_items)

    scheduled_items = [
        item
        for day in body["days"]
        for window in day["time_windows"]
        for item in window["items"]
        if item["source"]["object_type"] == "health_problem"
    ]
    assert any(item["scheduled_for"] == "2026-06-30" for item in scheduled_items)


def test_today_runtime_mode_returns_one_day_projection(client, auth_user_and_headers, monkeypatch):
    _, h = auth_user_and_headers
    _freeze_agenda_today(monkeypatch, date(2026, 6, 28))
    client.post("/api/v1/protocols/seed/water-cup", headers=h)

    r = client.get("/api/v1/agenda/today?mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "runtime"
    assert body["horizon_days"] == 1
    assert len(body["days"]) == 1
    assert body["days"][0]["date"] == "2026-06-28"
    assert body["next_action"]["runtime_context"]["surface"] == "agenda"


def test_range_rejects_unknown_mode(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/agenda/range?days=7&mode=banana", headers=h)
    assert r.status_code == 422


def test_today_mode_smart_routes_to_smart_agenda(client, auth_user_and_headers, monkeypatch):
    _, h = auth_user_and_headers
    from app.services import agenda_service

    monkeypatch.setattr(agenda_service, "smart_today", lambda db, uid, followup_within_days=14, max_items=3: {
        "agenda_date": "2026-06-22",
        "mode": "smart",
        "source_count": 4,
        "smart": {"top_items": [{"id": "smart_health_problem_1_checkup"}]},
    }, raising=False)

    r = client.get("/api/v1/agenda/today?mode=smart&max_items=1", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "smart"
    assert r.json()["smart"]["top_items"][0]["id"] == "smart_health_problem_1_checkup"


def test_runtime_context_includes_key_fact_provenance_for_biomarker(
    client, db, auth_user_and_headers, monkeypatch
):
    """运行时 top action 必须能说明关键化验事实来自哪里,而不是只给黑箱结论。"""
    user, h = auth_user_and_headers
    from app.models.biomarker_observation import BiomarkerObservation
    from app.services import agenda_service
    from app.services.data_connections import create_provenance_record, upsert_data_connection

    observed_at = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)
    connection = upsert_data_connection(
        db,
        user_id=user.id,
        provider="fhir_bundle",
        provider_type="fhir_bundle",
        display_name="体检报告 FHIR Bundle",
        scopes=["lab.read"],
        source_ref="bundle-2026-06",
        metadata={"importer": "test"},
    )
    obs = BiomarkerObservation(
        user_id=user.id,
        code="lipid_ldl",
        domain="lipid",
        normalized_value=4.1,
        normalized_unit="mmol/L",
        flag="high",
        abnormal=True,
        is_risk=True,
        confidence="medium",
        observed_at=observed_at,
        source="fhir_bundle",
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    create_provenance_record(
        db,
        user_id=user.id,
        connection_id=connection.id,
        source_kind="fhir_bundle",
        source_id="Observation/ldl-2026-06",
        object_type="BiomarkerObservation",
        object_id=str(obs.id),
        transformed_by="fhir_bundle_observation_v1",
        observed_at=observed_at,
        confidence="medium",
        metadata={
            "code": {"text": "LDL-C", "coding": [{"code": "13457-7", "display": "LDL cholesterol"}]},
            "resource_status": "final",
            "raw_patient_name": "SHOULD_NOT_LEAK",
        },
        raw_hash="raw-report-hash-should-not-leak",
    )

    monkeypatch.setattr(agenda_service, "smart_today", lambda db, uid, followup_within_days=1, max_items=4: {
        "agenda_date": "2026-06-28",
        "mode": "smart",
        "smart": {"top_items": [{
            "id": "smart_daily_plan_metabolic_walk",
            "type": "movement",
            "title": "饭后步行 10 分钟",
            "status": "pending",
            "status_canonical": "pending",
            "can_complete": True,
            "can_skip": True,
            "time_window": "evening",
            "priority": 65,
            "rank_score": 84,
            "source": {"object_type": "daily_plan_action", "object_id": "metabolic_walk"},
            "why_now": "LDL-C 偏高,今天先安排低门槛代谢行动。",
            "verify_by": {"metrics": ["lipid_ldl"], "window_days": 7},
            "trajectory_context": {
                "domain": "metabolic_health",
                "level": "attention",
                "state_variable": "metabolic_labs",
                "signals": ["ldl_elevated"],
                "verification_signal": "metabolic_labs",
            },
            "confidence": "medium",
            "claim_boundary": "仅作健康管理建议,不能替代医生诊断。",
        }]},
    }, raising=False)

    r = client.get("/api/v1/agenda/range?days=1&mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    top_action = r.json()["next_action"]
    provenance = top_action["runtime_context"]["evidence"]["provenance"]
    assert provenance["policy"] == "runtime_key_fact_provenance_v1"
    assert provenance["status"] == "available"
    assert provenance["queried_metrics"] == ["lipid_ldl"]
    assert provenance["items"][0]["source_kind"] == "fhir_bundle"
    assert provenance["items"][0]["source_id"] == "Observation/ldl-2026-06"
    assert provenance["items"][0]["object_type"] == "BiomarkerObservation"
    assert provenance["items"][0]["object_id"] == str(obs.id)
    assert provenance["items"][0]["confidence"] == "medium"
    assert provenance["items"][0]["privacy_classification"] == "L3"
    assert provenance["items"][0]["metadata_summary"]["code_text"] == "LDL-C"
    assert "raw_hash" not in provenance["items"][0]
    assert "raw_patient_name" not in provenance["items"][0]["metadata_summary"]


def _runtime_item_for_protocol(body: dict, protocol_id: int, day_index: int = 1) -> dict:
    for window in body["days"][day_index]["time_windows"]:
        for item in window["items"]:
            source = item.get("source") or {}
            if source.get("object_type") == "health_protocol" and source.get("object_id") == protocol_id:
                return item
    raise AssertionError(f"runtime item not found for protocol {protocol_id}")


def test_runtime_context_omits_provenance_for_plain_protocol_without_key_fact(
    client, auth_user_and_headers, monkeypatch
):
    """普通协议没有明确关键事实时,不应把 missing provenance 噪声塞进 every item。"""
    _, h = auth_user_and_headers
    _freeze_agenda_today(monkeypatch, date(2026, 6, 28))
    protocol_id = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]

    r = client.get("/api/v1/agenda/range?days=2&mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    item = _runtime_item_for_protocol(r.json(), protocol_id)
    assert "provenance" not in item["runtime_context"]["evidence"]


def test_runtime_future_projection_downranks_recent_skip_reason(
    client, db, auth_user_and_headers, monkeypatch
):
    """跳过原因不是只记录:它必须进入未来 7 天投影的重排和解释。"""
    user, h = auth_user_and_headers
    today = date.today()
    _freeze_agenda_today(monkeypatch, today)
    from app.services import health_protocol_service as proto_svc

    water = proto_svc.create_water_cup_protocol(db, user.id)
    exercise = proto_svc.create_protocol(db, user.id, {
        "domain": "exercise",
        "name": "俯卧撑 12 个",
        "mechanism": "pre_commit",
        "cadence": "daily",
        "time_window": "morning",
        "completion_mode": "one_tap",
        "can_default_complete": False,
    })
    proto_svc.skip_protocol(db, exercise.id, user.id, reason="too_tired", day=today)

    r = client.get("/api/v1/agenda/range?days=3&mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    exercise_item = _runtime_item_for_protocol(body, exercise.id)
    water_item = _runtime_item_for_protocol(body, water.id)
    runtime_context = exercise_item["runtime_context"]
    assert runtime_context["replan_reason"] == "recent_skip_reason_projection"
    assert runtime_context["feedback_adjustment"]["latest_status"] == "skipped"
    assert runtime_context["feedback_adjustment"]["skip_reason"] == "too_tired"
    assert runtime_context["feedback_adjustment"]["strategy"] == "reduce_pressure"
    assert exercise_item["rank_score"] < water_item["rank_score"]


def test_runtime_future_projection_carries_completion_and_snooze_feedback(
    client, db, auth_user_and_headers, monkeypatch
):
    """完成与稍后都要进入 future projection,而不是只改变今天的状态。"""
    user, h = auth_user_and_headers
    today = date.today()
    _freeze_agenda_today(monkeypatch, today)
    from app.services import health_protocol_service as proto_svc

    mobility = proto_svc.create_protocol(db, user.id, {
        "domain": "activity",
        "name": "饭后散步 10 分钟",
        "mechanism": "pre_commit",
        "cadence": "daily",
        "time_window": "evening",
        "completion_mode": "one_tap",
    })
    stretch = proto_svc.create_protocol(db, user.id, {
        "domain": "exercise",
        "name": "肩颈拉伸 5 分钟",
        "mechanism": "pre_commit",
        "cadence": "daily",
        "time_window": "afternoon",
        "completion_mode": "one_tap",
    })
    proto_svc.complete_protocol(db, mobility.id, user.id, day=today)
    proto_svc.snooze_protocol(db, stretch.id, user.id, minutes=45, day=today)

    r = client.get("/api/v1/agenda/range?days=3&mode=runtime", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    completed_item = _runtime_item_for_protocol(body, mobility.id)
    snoozed_item = _runtime_item_for_protocol(body, stretch.id)
    completed_context = completed_item["runtime_context"]
    snoozed_context = snoozed_item["runtime_context"]

    assert completed_context["replan_reason"] == "recent_completion_projection"
    assert completed_context["feedback_adjustment"]["latest_status"] == "completed"
    assert completed_context["feedback_adjustment"]["strategy"] == "observe_metric_change"

    assert snoozed_context["replan_reason"] == "active_snooze_projection"
    assert snoozed_context["feedback_adjustment"]["latest_status"] == "snoozed"
    assert snoozed_context["feedback_adjustment"]["strategy"] == "respect_snooze_window"
    assert snoozed_context["feedback_adjustment"]["snoozed_until"]
