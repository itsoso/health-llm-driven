"""Conversation starters endpoint tests.

Goal: The new-chat empty state should show dynamic prompt chips derived from
recent user data (exams/workouts/supplements/sleep) with a safe default fallback.
"""

from datetime import date, datetime, timedelta, timezone


DEFAULT_SUGGESTIONS = [
    "分析我最近的代谢健康",
    "今天怎么安排训练和恢复",
    "结合基因和体检给我建议",
    "帮我复盘最近的睡眠质量",
]


def test_endpoint_returns_default_suggestions_when_no_data(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert payload["opener"] is None
    assert payload["suggestions"] == DEFAULT_SUGGESTIONS


def test_endpoint_includes_exam_hint_when_recent_exam_exists(client, db, auth_user_and_headers):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = auth_user_and_headers

    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today() - timedelta(days=3),
        exam_type="comprehensive",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    db.add(
        MedicalExamItem(
            exam_id=exam.id,
            category="lipid",
            item_name="LDL-C",
            value=4.2,
            unit="mmol/L",
            reference_range="<3.4",
            result="偏高",
            is_abnormal="high",
            source="manual",
        )
    )
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload["suggestions"], list)
    assert any("体检" in text for text in payload["suggestions"])
    assert any("LDL" in text for text in payload["suggestions"])


def test_endpoint_prioritizes_goal_water_and_diet_gaps(client, db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake
    from app.models.goal import Goal, GoalPeriod, GoalStatus, GoalType

    user, headers = auth_user_and_headers
    today = date.today()

    db.add(Goal(
        user_id=user.id,
        goal_type=GoalType.WEIGHT,
        goal_period=GoalPeriod.MONTHLY,
        title="把体重降到 75kg",
        target_value=75,
        target_unit="kg",
        current_value=78,
        start_date=today - timedelta(days=10),
        status=GoalStatus.ACTIVE,
        priority=9,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=today,
        intake_time=datetime.now(timezone.utc),
        amount_ml=300,
        drink_type="water",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert len(suggestions) == 4
    assert any("把体重降到 75kg" in text for text in suggestions)
    assert any("饮水 300/2000ml" in text for text in suggestions)
    assert any("还没记录饮食" in text for text in suggestions)


def test_endpoint_includes_latest_workout_detail_and_gene_risk(client, db, auth_user_and_headers):
    from app.models.daily_health import WorkoutRecord
    from app.models.genetic_data import GeneticProfile, GeneticVariant

    user, headers = auth_user_and_headers
    today = date.today()

    db.add(WorkoutRecord(
        user_id=user.id,
        workout_date=today,
        workout_type="running",
        workout_name="晨跑",
        duration_seconds=1800,
        distance_meters=5200,
        avg_heart_rate=145,
        training_load=88,
        source="garmin",
    ))
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="WeGene",
        test_date=today - timedelta(days=20),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add(GeneticVariant(
        user_id=user.id,
        profile_id=profile.id,
        rsid="rs1801133",
        category="nutrition",
        gene_name="MTHFR",
        genotype="TT",
        result_label="叶酸代谢关注",
        risk_level="high",
        variant_nature="risk",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert any("最近一次跑步" in text and "5.2km" in text for text in suggestions)
    assert any("MTHFR TT" in text for text in suggestions)
