from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift as cdd  # noqa: E402


def test_mobile_route_count_excludes_app_tests() -> None:
    app_root = cdd.MOBILE / "app"
    all_tsx = [p for p in app_root.rglob("*.tsx") if p.name != "_layout.tsx"]
    expected_routes = [
        p for p in all_tsx
        if "__tests__" not in p.parts
        and not p.name.endswith((".test.tsx", ".spec.tsx"))
    ]

    assert len(expected_routes) < len(all_tsx)
    assert cdd.count_mobile_routes() == len(expected_routes)
