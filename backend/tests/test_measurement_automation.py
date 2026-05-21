"""Device-first measurement automation capability map."""

from app.services.measurement_automation import (
    get_measurement_capability_map,
    measurement_plan_for,
)


def test_measurement_capability_map_covers_core_health_loop_metrics():
    capability_map = get_measurement_capability_map()

    for metric in ["weight", "waist_cm", "blood_pressure", "cgm"]:
        assert metric in capability_map
        assert capability_map[metric]["fallback_ui"] == "manual_one_screen"
        assert capability_map[metric]["automation_path"][0]["method"] in {
            "device",
            "system_health_store",
        }


def test_measurement_plan_prefers_system_store_before_manual():
    plan = measurement_plan_for("waist_cm")

    methods = [step["method"] for step in plan["automation_path"]]
    assert "system_health_store" in methods
    assert methods[-1] == "manual"
    assert plan["dedupe_key"] == "user_id + metric + source + timestamp_bucket + value"
