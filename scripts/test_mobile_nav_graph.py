from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_nav_module():
    spec = importlib.util.spec_from_file_location(
        "mobile_nav_graph", ROOT / "mobile" / "scripts" / "dump_nav_graph.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _graph() -> dict:
    return {
        "_note": "fixture",
        "counts": {
            "nodes": 1,
            "edges": 0,
            "orphans": 0,
            "dead_ends": 1,
            "external_unmatched": 0,
        },
        "tabs": ["/"],
        "nodes": ["/"],
        "edges": [],
        "orphans": [],
        "dead_ends": ["/"],
        "external_unmatched": {},
    }


def test_check_mode_fails_on_drift_without_writing(tmp_path, monkeypatch) -> None:
    nav = _load_nav_module()
    mobile = tmp_path / "mobile"
    mobile.mkdir()
    out = tmp_path / "mobile-nav-graph.json"
    out.write_text('{"stale": true}\n', encoding="utf-8")
    before = out.read_bytes()
    monkeypatch.setattr(nav, "MOBILE", mobile)
    monkeypatch.setattr(nav, "OUT", out)
    monkeypatch.setattr(nav, "build_graph", _graph)

    assert nav.main(["--check"]) == 1
    assert out.read_bytes() == before


def test_check_mode_accepts_matching_graph_without_writing(tmp_path, monkeypatch) -> None:
    nav = _load_nav_module()
    mobile = tmp_path / "mobile"
    mobile.mkdir()
    out = tmp_path / "mobile-nav-graph.json"
    out.write_text(
        json.dumps(_graph(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(nav, "MOBILE", mobile)
    monkeypatch.setattr(nav, "OUT", out)
    monkeypatch.setattr(nav, "build_graph", _graph)

    def reject_write(*args, **kwargs):
        raise AssertionError("--check must not write the generated graph")

    monkeypatch.setattr(Path, "write_text", reject_write)

    assert nav.main(["--check"]) == 0


def test_check_mode_fails_when_output_is_missing(tmp_path, monkeypatch) -> None:
    nav = _load_nav_module()
    mobile = tmp_path / "mobile"
    mobile.mkdir()
    monkeypatch.setattr(nav, "MOBILE", mobile)
    monkeypatch.setattr(nav, "OUT", tmp_path / "missing.json")
    monkeypatch.setattr(nav, "build_graph", _graph)

    assert nav.main(["--check"]) == 1
