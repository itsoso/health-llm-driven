"""慢病趋势引擎 + 肝脏评估。钉:趋势方向/好转恶化;FIB-4 缺血小板返回 None 不臆测;
脂肪肝风险启发;端点鉴权 + shape。"""
from datetime import date

from sqlalchemy import text

from app.services.chronic_trends import compute_trend, adherence_rate
from app.services.liver_health import assess_liver


# ── 纯趋势函数 ──
def test_trend_rising_is_worsening_for_liver_enzymes():
    t = compute_trend([(date(2021, 8, 1), 61), (date(2023, 8, 1), 73), (date(2025, 8, 1), 78)])
    assert t is not None and t.direction == "rising"
    assert t.verdict(higher_is_worse=True) == "worsening"
    assert t.pct_change == round((78 - 61) / 61 * 100, 1)


def test_trend_falling_is_improving_when_higher_is_worse():
    t = compute_trend([(date(2026, 1, 1), 78), (date(2026, 6, 1), 43)])
    assert t.direction == "falling" and t.verdict(higher_is_worse=True) == "improving"


def test_trend_small_change_is_stable():
    t = compute_trend([(date(2026, 1, 1), 50), (date(2026, 6, 1), 51)])
    assert t.verdict(higher_is_worse=True) == "stable"  # +2% < flat_pct


def test_trend_needs_two_points():
    assert compute_trend([(date(2026, 1, 1), 50)]) is None
    assert compute_trend([]) is None


def test_adherence_rate():
    assert adherence_rate(12, 14) == round(12 / 14, 3)
    assert adherence_rate(20, 14) == 1.0  # 封顶 1.0
    assert adherence_rate(0, 0) is None


# ── 肝脏评估(种子 medical_indicators)──
def _seed(db, user_id, name, value, d):
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, unit, record_date) "
        "VALUES (:u, :n, :v, 'U/L', :d)"
    ), {"u": user_id, "n": name, "v": value, "d": d})
    db.commit()


def test_liver_no_data(db):
    assert assess_liver(db, 999, age=41)["available"] is False


def test_liver_fib4_none_without_platelets(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "谷丙转氨酶", 31, date(2026, 5, 1))
    _seed(db, user.id, "谷草转氨酶", 24, date(2026, 5, 1))
    _seed(db, user.id, "谷氨酰转肽酶", 61, date(2021, 8, 1))
    _seed(db, user.id, "谷氨酰转肽酶", 78, date(2025, 8, 1))
    a = assess_liver(db, user.id, age=41)
    assert a["available"] is True
    assert a["fib4"] is None  # 无血小板 → 不算
    assert any("血小板" in x for x in a["advice"])  # 提示补数据
    assert a["ast_alt_ratio"] == round(24 / 31, 2)  # <1
    assert a["ggt_trend"]["verdict"] == "worsening"  # 61→78 上升


def test_liver_fib4_computed_with_platelets(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "谷丙转氨酶", 31, date(2026, 5, 1))
    _seed(db, user.id, "谷草转氨酶", 24, date(2026, 5, 1))
    _seed(db, user.id, "血小板计数", 220, date(2026, 5, 1))
    a = assess_liver(db, user.id, age=41)
    # FIB-4 = 41*24 / (220*sqrt(31)) ≈ 0.80
    assert a["fib4"] is not None and 0.7 < a["fib4"] < 0.9
    assert a["fib4_band"].startswith("低")


def test_liver_endpoint_shape(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    _seed(db, user.id, "谷丙转氨酶", 47, date(2026, 5, 1))
    r = client.get("/api/v1/chronic/liver", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "available" in body and "advice" in body
    # 未鉴权
    assert client.get("/api/v1/chronic/liver").status_code in (401, 403)
