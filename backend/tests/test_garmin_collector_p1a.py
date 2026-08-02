"""
P1a collector 解析层测试。
用 mock 的 raw_data 喂给 parse_to_garmin_data_create，验证新字段抽取正确。
完整网络调用测试在 P1a-07 的线上 smoke test 里做（需要真实凭据）。
"""
from datetime import date
import pytest
from unittest.mock import MagicMock

from app.services.data_collection.garmin_connect import GarminConnectService


@pytest.fixture
def service():
    """构造一个不真正登录的 service 实例，只测解析逻辑。"""
    svc = GarminConnectService.__new__(GarminConnectService)
    svc.user_id = 1
    svc.email = "test@example.com"
    return svc


class TestParseTrainingReadiness:
    def test_parses_score_and_factors(self, service):
        raw = {
            "training_readiness": {
                "score": 82,
                "level": "MODERATE",
                "feedbackShort": "good_recovery",
                "sleepScore": 88,
                "hrvWeeklyAverage": 55.0,
                "acuteLoad": 320.5,
            },
        }
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.training_readiness_score == 82
        assert result.training_readiness_level == "MODERATE"
        assert result.training_readiness_factors is not None
        assert result.training_readiness_factors.get("sleepScore") == 88
        assert result.training_readiness_factors.get("hrvWeeklyAverage") == 55.0

    def test_handles_list_response(self, service):
        """某些账户 training_readiness 返回 list，collector 会取最后一个；此处模拟已取完。"""
        raw = {"training_readiness": {}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.training_readiness_score is None
        assert result.training_readiness_factors is None

    def test_missing_training_readiness_ok(self, service):
        """没有字段时不报错。"""
        result = service.parse_to_garmin_data_create({}, user_id=1, record_date=date(2026, 4, 23))
        assert result.training_readiness_score is None
        assert result.training_status is None

    def test_non_numeric_score_is_tolerated(self, service):
        """Garmin 偶发返回 list 等非标准值时，解析层应降级为空而不是整日失败。"""
        raw = {"training_readiness": {"score": ["unexpected"]}}

        result = service.parse_to_garmin_data_create(
            raw,
            user_id=1,
            record_date=date(2026, 4, 23),
        )

        assert result.training_readiness_score is None


class TestParseTrainingStatus:
    """Garmin trainingStatus 是枚举整数（如 8 = productive），trainingStatusKey 才是字符串。
    Regression: 实际线上样本把整数直接塞进 GarminData.training_status 触发 Pydantic 校验失败。"""

    def test_prefers_training_status_key(self, service):
        raw = {
            "training_status": {
                "mostRecentTrainingStatus": {
                    "latestTrainingStatusData": {
                        "3434423431": {
                            "trainingStatus": 8,
                            "trainingStatusKey": "productive",
                            "trainingStatusFeedbackPhrase": "keep_going",
                        }
                    }
                }
            }
        }
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.training_status == "productive"
        assert result.training_status_feedback == "keep_going"

    def test_falls_back_to_str_when_no_key(self, service):
        raw = {
            "training_status": {
                "mostRecentTrainingStatus": {
                    "latestTrainingStatusData": {
                        "device-1": {"trainingStatus": 8}
                    }
                }
            }
        }
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        # 没有 trainingStatusKey 时转成字符串兜底
        assert result.training_status == "8"

    def test_top_level_int_is_coerced(self, service):
        raw = {"training_status": {"trainingStatus": 5}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.training_status == "5"


class TestParseEnduranceHillHydration:
    def test_endurance_score(self, service):
        raw = {"endurance_score": {"overallScore": 7900, "classification": "trained"}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.endurance_score == 7900

    def test_hill_score(self, service):
        raw = {"hill_score": {"overallScore": 60}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.hill_score == 60

    def test_hydration(self, service):
        raw = {"hydration": {"valueInML": 1850, "userDailyAverage": 2000}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.hydration_ml == 1850

    def test_hydration_fallback_key(self, service):
        raw = {"hydration": {"hydration": 1500}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.hydration_ml == 1500


class TestParseRacePredictions:
    def test_race_predictions_populated(self, service):
        raw = {
            "race_predictions": {
                "time5K": 1500,
                "time10K": 3200,
                "timeHalfMarathon": 7400,
                "timeMarathon": 15600,
            },
        }
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.race_predictions == {
            "5k": 1500, "10k": 3200, "half_marathon": 7400, "marathon": 15600,
        }

    def test_race_predictions_partial_filters_nulls(self, service):
        raw = {"race_predictions": {"time5K": 1500, "time10K": None, "timeMarathon": 15000}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.race_predictions == {"5k": 1500, "marathon": 15000}

    def test_race_predictions_all_null_returns_none(self, service):
        raw = {"race_predictions": {"time5K": None, "time10K": None}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.race_predictions is None


class TestParseHrvSummary:
    def test_hrv_summary_backfills_daily_fields(self, service):
        """hrv_data.hrvSummary 可以补 GarminData 日级 hrv / 7day_avg / status。"""
        raw = {
            "hrv_raw": {
                "hrvSummary": {"lastNightAvg": 48.0, "weeklyAvg": 52.0, "status": "BALANCED"},
                "hrvReadings": [],
            },
        }
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.hrv == 48.0
        assert result.hrv_7day_avg == 52.0
        assert result.hrv_status == "BALANCED"


class TestParseMaxMetricsFitnessAge:
    def test_generic_fitness_age(self, service):
        raw = {"max_metrics": {"generic": {"vo2MaxPreciseValue": 54.2, "fitnessAge": 35}}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.vo2max_fitness_age == 35

    def test_flat_fitness_age(self, service):
        raw = {"max_metrics": {"fitnessAge": 40}}
        result = service.parse_to_garmin_data_create(raw, user_id=1, record_date=date(2026, 4, 23))
        assert result.vo2max_fitness_age == 40
