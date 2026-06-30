"""Metric chart dynamic-card builders."""
from datetime import date, timedelta


def test_metric_chart_builds_sleep_score_from_garmin_data(db):
    from app.models.daily_health import GarminData
    from app.services.metric_chart_cards import build_metric_chart

    today = date.today()
    db.add_all([
        GarminData(user_id=3, record_date=today - timedelta(days=2), sleep_score=72, data_source="garmin"),
        GarminData(user_id=3, record_date=today - timedelta(days=1), sleep_score=81, data_source="garmin"),
        GarminData(user_id=3, record_date=today, sleep_score=86, data_source="garmin"),
    ])
    db.commit()

    card = build_metric_chart(db, user_id=3, query="画最近7天睡眠评分趋势")

    assert card is not None
    assert card["metric"] == "sleep_score"
    assert card["title"] == "最近7天 睡眠评分"
    assert card["unit"] == "分"
    assert card["coverage"] == {"days_with_data": 3, "days_in_window": 8}
    assert card["latest"] == {
        "date": today.isoformat(),
        "value": 86.0,
        "source": "garmin",
    }
    assert [point["value"] for point in card["series"]] == [72.0, 81.0, 86.0]


def test_metric_chart_builds_weight_from_weight_records(db):
    from app.models.weight import WeightRecord
    from app.services.metric_chart_cards import build_metric_chart

    today = date.today()
    db.add_all([
        WeightRecord(user_id=3, record_date=today - timedelta(days=4), weight=74.5),
        WeightRecord(user_id=3, record_date=today - timedelta(days=2), weight=74.0),
        WeightRecord(user_id=3, record_date=today, weight=73.8),
    ])
    db.commit()

    card = build_metric_chart(db, user_id=3, query="绘制最近30天体重曲线")

    assert card is not None
    assert card["metric"] == "weight"
    assert card["title"] == "最近30天 体重"
    assert card["unit"] == "kg"
    assert card["latest"] == {
        "date": today.isoformat(),
        "value": 73.8,
        "source": "manual",
    }
    assert card["summary"]["last_30_vs_prev_30_delta"] is None
    assert [point["value"] for point in card["series"]] == [74.5, 74.0, 73.8]


def test_metric_chart_does_not_trigger_for_record_intent(db):
    from app.models.weight import WeightRecord
    from app.services.metric_chart_cards import build_metric_chart

    today = date.today()
    db.add_all([
        WeightRecord(user_id=3, record_date=today - timedelta(days=1), weight=74.0, source="manual"),
        WeightRecord(user_id=3, record_date=today, weight=73.8, source="manual"),
    ])
    db.commit()

    assert build_metric_chart(db, user_id=3, query="记录今天体重 73.8kg") is None
