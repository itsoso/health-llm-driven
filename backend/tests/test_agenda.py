"""统一健康议程投影(R1)。钉:① 协议待办进议程 ② 到期复查进议程
③ 完成的协议状态正确 ④ 高优先级(复查/P1)排在前 ⑤ 空态。"""


def test_empty_agenda(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/agenda/today", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0 and r.json()["items"] == []


def test_protocol_appears_in_agenda(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    water = next(i for i in items if i["type"] == "hydration")
    assert water["status"] == "pending"
    assert water["source"]["object_type"] == "health_protocol"


def test_completed_protocol_status_reflected(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    pid = client.post("/api/v1/protocols/seed/water-cup", headers=h).json()["id"]
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    assert next(i for i in items if i["type"] == "hydration")["status"] == "completed"


def test_due_checkup_in_agenda_and_priority(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    # 过期复查(过去日期)
    client.post("/api/v1/problems", headers=h, json={
        "name": "血脂复查", "risk_level": "P1",
        "follow_up": {"next_due": "2020-01-01", "what_to_check": "ApoB"}})
    # 一个普通协议
    client.post("/api/v1/protocols/seed/water-cup", headers=h)
    items = client.get("/api/v1/agenda/today", headers=h).json()["items"]
    checkup = next(i for i in items if i["type"] == "checkup")
    assert checkup["status"] == "overdue"
    assert checkup["source"]["object_type"] == "health_problem"
    # 复查(P1,priority 95)排在饮水协议(50)前面
    assert items[0]["type"] == "checkup"


def test_training_light_skipped_when_no_signal(monkeypatch):
    """无任何恢复/负荷信号(zone=unknown 且无 acwr)→ 不投训练灯(不假装黄灯)。"""
    from app.services import agenda_service
    monkeypatch.setattr(agenda_service, "training_decision",
                        lambda db, uid: {"zone": "unknown", "light": "yellow"},
                        raising=False)
    # training_decision 在函数内部 import,需 patch 源模块
    import app.services.recovery_decision as rd
    monkeypatch.setattr(rd, "training_decision",
                        lambda db, uid: {"zone": "unknown", "light": "yellow"})
    assert agenda_service._training_item(None, 1) is None


def test_training_light_projected_when_signal_present(monkeypatch):
    """有恢复信号 → 投只读训练灯项(status=info,带灯色/分数,不可完成)。"""
    from app.services import agenda_service
    import app.services.recovery_decision as rd
    monkeypatch.setattr(rd, "training_decision", lambda db, uid: {
        "zone": "rest", "light": "red", "readiness_score": 38,
        "next_action": "今天以休息为主", "reasons": ["恢复就绪度 38/100"],
        "confidence": 0.7,
    })
    item = agenda_service._training_item(None, 7)
    assert item is not None
    assert item["type"] == "training" and item["status"] == "info"
    assert item["light"] == "red" and item["readiness_score"] == 38
    assert item["priority"] == 90  # red 抬到复查档
    assert item["source"]["object_type"] == "training_decision"


def _twin_with_divergence(*divs):
    from app.twin.schema import HealthTwin, TwinMeta, CrossSourceDivergence
    from datetime import datetime
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    twin.physiological.device_agreement_index = 0.6
    twin.physiological.device_sources = ["garmin", "ringconn"]
    twin.physiological.divergent_metrics = [
        CrossSourceDivergence(metric=m, label=lbl, trusted_source="garmin",
                              outlier_source="ringconn", deviation_pct=18.0,
                              hint=f"{lbl} 差异较大")
        for m, lbl in divs
    ]
    return twin


def test_data_quality_item_when_divergence(monkeypatch):
    """跨源偏离 → 议程出 data_quality 提示项(只读,不可完成)。"""
    from app.services import agenda_service
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda db, uid, use_cache=True: _twin_with_divergence(
                            ("resting_heart_rate", "静息心率"), ("hrv", "HRV")))
    item = agenda_service._data_quality_item(None, 1)
    assert item is not None
    assert item["type"] == "data_quality" and item["status"] == "info"
    assert "静息心率" in item["title"] and "等 2 项" in item["title"]
    assert len(item["divergent_metrics"]) == 2
    assert item["source"]["object_type"] == "data_quality"


def test_data_quality_item_none_when_no_divergence(monkeypatch):
    from app.services import agenda_service
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda db, uid, use_cache=True: _twin_with_divergence())
    assert agenda_service._data_quality_item(None, 1) is None


def test_smart_today_returns_ranked_executable_contract(monkeypatch):
    """Smart Agenda 把普通议程 + Daily Plan 行动投影成统一可执行合同。"""
    from app.services import agenda_service

    monkeypatch.setattr(agenda_service, "today", lambda db, uid, followup_within_days=14: {
        "agenda_date": "2026-06-22",
        "count": 2,
        "items": [
            {
                "type": "hydration",
                "title": "喝完 2000ml 水杯",
                "status": "pending",
                "time_window": "anytime",
                "priority": 50,
                "source": {"object_type": "health_protocol", "object_id": 7},
            },
            {
                "type": "checkup",
                "title": "复查:ApoB",
                "status": "overdue",
                "time_window": "anytime",
                "priority": 95,
                "detail": "ApoB + LDL-C",
                "source": {"object_type": "health_problem", "object_id": 9},
            },
        ],
    })
    monkeypatch.setattr(agenda_service, "build_daily_operating_plan", lambda db, uid, plan_date=None: {
        "plan_date": "2026-06-22",
        "actions": [
            {
                "action_key": "movement.moderate_activity",
                "domain": "movement",
                "title": "累计 35-45 分钟中等强度活动",
                "why": "对齐每周 150 分钟中等强度活动的代谢健康目标。",
                "when": "daytime",
                "metric_key": "custom",
                "target_value": "150min_weekly",
                "confidence": "high",
                "verification": {"window_days": 7, "metrics": ["weight", "waist_cm"]},
            }
        ],
    }, raising=False)

    body = agenda_service.smart_today(None, 1, max_items=3)

    assert body["mode"] == "smart"
    assert body["source_count"] == 3
    top = body["smart"]["top_items"]
    assert len(top) == 3
    assert top[0]["source"]["object_type"] == "health_problem"
    assert top[0]["why_now"].startswith("已逾期")
    # HealthProblem 复查没有统一 agenda 完成写路径，不能给客户端一个必失败的“完成”能力。
    assert top[0]["can_complete"] is False
    protocol = next(i for i in top if i["source"]["object_type"] == "health_protocol")
    assert protocol["can_complete"] is True
    daily = next(i for i in top if i["source"]["object_type"] == "daily_plan_action")
    assert daily["can_complete"] is True
    assert daily["id"] == "smart_daily_plan_action_movement.moderate_activity"
    assert daily["why_now"] == "对齐每周 150 分钟中等强度活动的代谢健康目标。"
    assert daily["do_now"].startswith("执行: 累计 35-45")
    assert daily["verify_by"]["metrics"] == ["weight", "waist_cm"]
    assert daily["replan_policy"]["on_skip"] == "capture_reason_then_reschedule"
    assert daily["surface"]["primary"] in {"mobile", "watch", "rokid"}


def test_smart_today_attaches_trajectory_context_to_daily_plan_actions(monkeypatch):
    """Smart Agenda top action should show which HealthTrajectory state it is moving."""
    from app.services import agenda_service

    monkeypatch.setattr(agenda_service, "today", lambda db, uid, followup_within_days=14: {
        "agenda_date": "2026-06-22",
        "count": 0,
        "items": [],
    })
    monkeypatch.setattr(agenda_service, "build_daily_operating_plan", lambda db, uid, plan_date=None: {
        "plan_date": "2026-06-22",
        "actions": [
            {
                "action_key": "movement.moderate_activity",
                "domain": "movement",
                "title": "累计 35-45 分钟中等强度活动",
                "why": "对齐每周 150 分钟中等强度活动的代谢健康目标。",
                "when": "daytime",
                "metric_key": "waist_cm",
                "target_value": "waist_down_or_stable",
                "confidence": "high",
                "verification": {"window_days": 7, "metrics": ["waist_cm"]},
            }
        ],
    }, raising=False)
    monkeypatch.setattr(agenda_service, "build_health_trajectory_snapshot", lambda db, uid: {
        "trajectory_risks": [
            {
                "domain": "metabolic_health",
                "level": "attention",
                "state_variable": "waist_cm",
                "horizon": "upstream_90d",
                "why": "腰围和血压提示代谢轨迹需要关注。",
                "primary_action": "优先执行中等强度活动和腰围复盘。",
                "confidence": "high",
                "uncertainty": {"level": "medium", "drivers": ["bp_single_measurement"]},
                "evidence_tier": "clinical_guideline",
                "claim_boundary": "用于上游健康管理排序, 不替代医生诊断。",
                "verification_window": {"days": 7, "signal": "waist_cm"},
                "verification_window_days": 7,
                "verification_signal": "waist_cm",
                "modifiable_levers": ["movement", "nutrition", "sleep"],
                "personal_prediction_context": {
                    "id": "personal_prediction:cycle:1:waist_cm",
                    "prediction_type": "intervention_cycle_projection",
                    "metric": "waist_cm",
                    "domain": "metabolic_health",
                    "horizon_days": 7,
                    "expected_signal": {"metric": "waist_cm", "direction": "down", "expected_delta": -0.5},
                    "confidence": "medium",
                    "uncertainty": {"level": "medium", "drivers": ["n_of_1_observational_cycle"]},
                    "evidence_tier": "personal_observation",
                    "model_version": "personal_prediction_v1",
                    "claim_boundary": "观察性预测, 不证明单个行动造成指标变化。",
                },
            }
        ],
    }, raising=False)

    body = agenda_service.smart_today(None, 1, max_items=1)

    top = body["smart"]["top_items"][0]
    assert body["smart"]["ranking"] == "trajectory_priority_status_source_v1"
    assert top["trajectory_context"]["domain"] == "metabolic_health"
    assert top["target_state_variable"] == "waist_cm"
    assert top["verification_signal"] == "waist_cm"
    assert top["why_now"].startswith("腰围和血压提示代谢轨迹需要关注。")
    assert top["claim_boundary"] == "用于上游健康管理排序, 不替代医生诊断。"
    assert top["trajectory_context"]["uncertainty"]["level"] == "medium"
    assert top["trajectory_context"]["personal_prediction_context"]["id"] == "personal_prediction:cycle:1:waist_cm"
    assert top["trajectory_context"]["personal_prediction_context"]["model_version"] == "personal_prediction_v1"
    assert top["trajectory_context"]["verification_window"]["signal"] == "waist_cm"
    assert top["verify_by"]["trajectory"]["horizon"] == "upstream_90d"
    assert top["verify_by"]["trajectory"]["uncertainty_level"] == "medium"
    assert top["rank_reason"]["trajectory"]["state_variable"] == "waist_cm"


# ── voice_actionable:含糊语音(Rokid「确认/跳过」)自动写的权威安全门(R4) ──────────
# 权威真相 = 协议 source_model(完成实际落哪张表),不是 domain。下面对抗用例钉住:
# ① 医疗级写表(med/supp)恒 False;② domain↔source_model 漂移时按 source_model 裁决
#   (hydration domain 但 source_model=medication_logs → 仍 False,这是客户端 domain
#   白名单会漏的真实漂移场景);③ 非协议来源恒 False。

def _smart(item):
    from app.services import agenda_service
    return agenda_service._to_smart_item(item, fallback_verification=None)


def _proto_item(**kw):
    base = {
        "type": "hydration",
        "title": "x",
        "status": "pending",
        "source": {"object_type": "health_protocol", "object_id": 1},
    }
    base.update(kw)
    return base


def test_smart_item_only_advertises_completion_when_a_write_path_exists():
    follow_up = {
        "type": "checkup",
        "status": "overdue",
        "source": {"object_type": "health_problem", "object_id": 9},
    }
    daily_plan = {
        "type": "movement",
        "status": "pending",
        "source": {"object_type": "daily_plan_action", "object_id": "movement.walk"},
    }

    assert _smart(follow_up)["can_complete"] is False
    assert _smart(_proto_item())["can_complete"] is True
    assert _smart(daily_plan)["can_complete"] is True


def test_voice_actionable_true_for_nonmedical_protocols():
    # 喝水(water_records)/ 饮食(diet_records)/ 无 source_model(只写协议事件)→ 可语音。
    assert _smart(_proto_item(type="hydration", source_model="water_records"))["voice_actionable"] is True
    assert _smart(_proto_item(type="diet", source_model="diet_records"))["voice_actionable"] is True
    assert _smart(_proto_item(type="activity", source_model="exercise_records"))["voice_actionable"] is True
    assert _smart(_proto_item(type="sleep", source_model=None))["voice_actionable"] is True


def test_voice_actionable_false_for_medical_grade_writers():
    # 用药 / 补剂协议完成会写真实 MedicationLog/SupplementRecord 依从 → 永不可含糊语音自动写。
    assert _smart(_proto_item(type="medication", source_model="medication_logs"))["voice_actionable"] is False
    assert _smart(_proto_item(type="supplement", source_model="supplement_records"))["voice_actionable"] is False


def test_voice_actionable_invariant_source_model_overrides_domain_drift():
    """漂移哨兵:domain 在「安全」白名单内,但 source_model 是医疗级 → 必须 False。

    这正是客户端 domain 白名单拦不住的场景:一个 hydration-domain 协议若 source_model=
    medication_logs,完成它会写 MedicationLog。按 domain 判会放行(漏),按 source_model
    判才挡住。把安全决定钉在 source_model 上。
    """
    drift = _proto_item(type="hydration", source_model="medication_logs")
    assert _smart(drift)["voice_actionable"] is False
    drift2 = _proto_item(type="activity", source_model="supplement_records")
    assert _smart(drift2)["voice_actionable"] is False


def test_voice_actionable_false_for_correction_advisory_riding_health_protocol():
    """回归:协议自纠偏建议挂 object_type=health_protocol(type=correction, status=info),
    但它是建议、不是依从待办 —— 必须 False,否则语音"跳过"会跳掉它背后的真协议。

    (旧 domain 白名单恰好挡住 correction;换成 source_model 门后必须用 status 门显式保住。)
    """
    corr = {
        "type": "correction",
        "status": "info",
        "source": {"object_type": "health_protocol", "object_id": 5},
        # 注:correction 项无 source_model 键(非医疗级也不应据此放行)。
    }
    assert _smart(corr)["voice_actionable"] is False


def test_voice_actionable_false_for_checkup_and_nonprotocol_sources():
    # 复查 domain 协议(source_model 多为 None)也排除 —— 确认复查须手机显式操作。
    assert _smart(_proto_item(type="checkup", source_model=None))["voice_actionable"] is False
    # 非协议来源:复查(health_problem)/ Daily Plan 行动 / 训练灯 → 恒 False。
    assert _smart({"type": "checkup", "status": "overdue",
                   "source": {"object_type": "health_problem", "object_id": 9}})["voice_actionable"] is False
    assert _smart({"type": "movement", "status": "pending",
                   "source": {"object_type": "daily_plan_action", "object_id": "x"}})["voice_actionable"] is False
