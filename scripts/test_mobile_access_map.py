from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import dump_mobile_access_map as dma  # noqa: E402


def test_every_mobile_app_page_becomes_a_route_node() -> None:
    snapshot = dma.build_mobile_access_map()
    route_files = dma.discover_route_files()
    route_file_set = {str(p.relative_to(ROOT)) for p in route_files}
    node_file_set = {node["file"] for node in snapshot["nodes"]}

    assert route_file_set
    assert route_file_set == node_file_set


def test_settings_system_map_entry_resolves_to_route() -> None:
    snapshot = dma.build_mobile_access_map()
    settings_edges = [
        edge for edge in snapshot["edges"]
        if edge["kind"] == "settings_row" and edge.get("label") == "系统地图"
    ]

    assert settings_edges
    assert {edge["source"] for edge in settings_edges} == {"/settings", "/(tabs)/me"}
    assert {edge["target"] for edge in settings_edges} == {"/system-map"}
    assert all(edge["resolved"] for edge in settings_edges)


def test_core_user_journeys_and_flow_evaluation_are_generated() -> None:
    snapshot = dma.build_mobile_access_map()
    journey_ids = {journey["id"] for journey in snapshot["journeys"]}

    assert "daily_execution_loop" in journey_ids
    assert "fast_capture_loop" in journey_ids
    assert "lab_import_review_loop" in journey_ids
    assert snapshot["evaluation"]["settings_hub"]["risk"] == "high_density"
    assert snapshot["evaluation"]["core_loop_alignment"]["primary_tab_model"] == [
        "今日",
        "私教",
        "记录",
        "我",
    ]
