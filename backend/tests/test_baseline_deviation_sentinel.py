"""王牌③「静息 HR 漂移哨兵」单测(TDD 先行)。

D1 改设计后(2026-06-16):哨兵从"减一层"(急性值 continue 让给 SafetyGuardian)
改为"加一层安全网"——**永不静默丢急性值**,无论如何都产 advisory,按严重度升级 detail
文案带就医出口。根因:哨兵 `clean[-1]` 与 SafetyGuardian `twin.physiological.resting_hr`
的「latest」语义不一致,数据不同步时急性 RHR 两路全漏。

钉:
1. RHR 偏离(普通)→ 1 条 advisory,type/status/source 正确,detail 含 message + 「相关,非因果」。
2. 急性高(latest≥100)→ 产 1 条 advisory(不再 0 条!),detail 含「就医」。
3. 急性低(latest<40)→ 产 1 条 advisory(不再 0 条!),detail 含「就医」。
4. RHR 无偏离 → 0 条。
5. 非 SENTINEL 指标(HRV)偏离 → 0 条(王牌③只做 RHR)。
6. low_confidence 偏离 → advisory 在,message 已含「仅供参考」,但**不**触发持续就医出口。
7. compute_personal_baselines 抛异常 → 返回 []( 降级,不破坏议程)。
8. 措辞安全:detail 不含禁词,含「非因果」;急性/持续分支含「就医」。
9. 集成:agenda_service.today() 的 items 含一条 type=="baseline_deviation"。
10. D1 核心:急性值存在 → 哨兵无论如何兜底产 advisory(模拟 SafetyGuardian 会漏)。
11. 持续亚急性 rising → detail 含「若持续」就医出口。
12. 单次抖动(stable)→ detail 不含「就医」「若持续」(只软 info)。

构造 MetricBaseline 直喂(monkeypatch compute_personal_baselines),不依赖 DB 造数。
"""
from app.services import baseline_deviation_sentinel as sentinel
from app.services.personal_baseline import MetricBaseline

# 禁词对齐 reviewer 约束:不得出现 感染/炎症/疾病/确诊/治疗。
# 注意「非诊断」是 reviewer 批准的筛查免责声明(筛查非诊断),不属禁词——故不收 "诊断"。
FORBIDDEN_WORDS = ["感染", "炎症", "疾病", "确诊", "治疗"]


def _rhr(
    *,
    z=2.5,
    latest=61.0,
    is_deviation=True,
    low_confidence=False,
    trend="rising",
    message="静息心率 比你 90 天基线高 2.5σ (52bpm→61bpm) ↑趋势",
):
    return MetricBaseline(
        key="resting_heart_rate",
        label="静息心率",
        unit="bpm",
        baseline_mean=52.0,
        baseline_std=3.6,
        n_days=90,
        latest=latest,
        latest_date="2026-06-16",
        z=z,
        trend=trend,
        is_deviation=is_deviation,
        low_confidence=low_confidence,
        message=message if is_deviation else None,
    )


def _patch_baselines(monkeypatch, baselines):
    monkeypatch.setattr(
        sentinel,
        "compute_personal_baselines",
        lambda db, user_id, today=None: list(baselines),
    )


# ── 1. 正例(普通漂移)─────────────────────────────────────────────────────
def test_rhr_deviation_produces_advisory(monkeypatch):
    # latest=61 在 (40,100) 内,trend=rising,但 low_confidence 影响升级 → 用 stable 测纯普通
    mb = _rhr(trend="stable")
    _patch_baselines(monkeypatch, [mb])

    advs = sentinel.deviation_advisories(db=None, user_id=42)
    assert len(advs) == 1
    a = advs[0]
    assert a["type"] == "baseline_deviation"
    assert a["status"] == "info"
    assert a["metric"] == "resting_heart_rate"
    assert a["time_window"] == "anytime"
    assert a["source"]["object_type"] == "baseline_deviation"
    assert a["source"]["object_id"] == 42
    assert a["z"] == 2.5
    assert a["low_confidence"] is False
    # detail 透传 mb.message + 非因果邀请
    assert mb.message in a["detail"]
    assert "相关,非因果" in a["detail"]


# ── 2. 急性高 → 产升级 advisory(不再 defer)──────────────────────────────
def test_rhr_acute_high_produces_escalated_advisory(monkeypatch):
    # latest=102 ≥ 100:哨兵不再静默丢,产 advisory 带就医出口(SafetyGuardian 之外的安全网)
    _patch_baselines(monkeypatch, [_rhr(latest=102.0, z=5.0)])
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    a = advs[0]
    assert a["status"] == "info"  # 渲染语义不变,升级在 detail
    assert "就医" in a["detail"]
    assert "偏离正常范围" in a["detail"]
    # 急性升级不得出现禁词
    for w in FORBIDDEN_WORDS:
        assert w not in a["detail"]


# ── 3. 急性低 → 产升级 advisory(不再 defer)──────────────────────────────
def test_rhr_acute_low_produces_escalated_advisory(monkeypatch):
    # latest=38 < 40:同样产 advisory 带就医出口
    _patch_baselines(monkeypatch, [_rhr(latest=38.0, z=-4.0, trend="falling")])
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    assert "就医" in advs[0]["detail"]
    assert "偏离正常范围" in advs[0]["detail"]


# ── 4. 无偏离 → 0 条 ───────────────────────────────────────────────────────
def test_rhr_no_deviation_produces_nothing(monkeypatch):
    _patch_baselines(monkeypatch, [_rhr(is_deviation=False, z=0.4, latest=53.0)])
    assert sentinel.deviation_advisories(db=None, user_id=1) == []


# ── 4a. 残留洞(reviewer 实锤):急性 + is_deviation=False → 仍产 advisory ──
def test_acute_high_but_not_statistical_deviation_still_alerts(monkeypatch):
    # 基线本身高且方差大(mean=88/std=9),latest=101 → z≈1.44<2.0 → is_deviation=False。
    # 旧门序在 is_deviation 门把这条静默丢了;急性值必须破门兜底产 advisory。
    mb = _rhr(latest=101.0, z=1.4, is_deviation=False, message=None)
    _patch_baselines(monkeypatch, [mb])
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1, "急性值即使非统计偏离也必须兜底产 advisory,不得静默丢"
    detail = advs[0]["detail"]
    assert "就医" in detail
    assert "偏离正常范围" in detail
    # message=None 不得渲染成字面 "None"
    assert "None" not in detail
    # 仍带归因邀请(标非因果)
    assert "非因果" in detail
    for w in FORBIDDEN_WORDS:
        assert w not in detail


# ── 4b. 退化 std 的急性低 + is_deviation=False → 仍产 advisory ─────────────
def test_acute_low_but_not_statistical_deviation_still_alerts(monkeypatch):
    # brady 急性(latest=38<40)但统计上未判偏离(message=None)→ 同样兜底 + 就医出口。
    mb = _rhr(latest=38.0, is_deviation=False, trend="stable", message=None)
    _patch_baselines(monkeypatch, [mb])
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    detail = advs[0]["detail"]
    assert "就医" in detail
    assert "偏离正常范围" in detail
    assert "None" not in detail


# ── 4c. 非急性 + is_deviation=False → 仍 0 条(确认没误伤 is_deviation 门)─
def test_non_acute_non_deviation_still_skipped(monkeypatch):
    # 普通范围内(latest=58)非偏离 → 只有急性才破 is_deviation 门;这条仍跳过。
    _patch_baselines(
        monkeypatch, [_rhr(latest=58.0, is_deviation=False, trend="stable")]
    )
    assert sentinel.deviation_advisories(db=None, user_id=1) == []


# ── 5. 非 SENTINEL 指标(HRV)偏离 → 0 条 ──────────────────────────────────
def test_non_sentinel_metric_ignored(monkeypatch):
    hrv = MetricBaseline(
        key="hrv",
        label="HRV",
        unit="ms",
        baseline_mean=58.0,
        baseline_std=6.0,
        n_days=90,
        latest=40.0,
        latest_date="2026-06-16",
        z=-3.0,
        trend="falling",
        is_deviation=True,
        low_confidence=False,
        message="HRV 比你 90 天基线低 3.0σ (58ms→40ms) ↓趋势",
    )
    _patch_baselines(monkeypatch, [hrv])
    assert sentinel.deviation_advisories(db=None, user_id=1) == []


# ── 6. low_confidence 透传 + 不触发持续就医出口 ───────────────────────────
def test_low_confidence_deviation_passed_through(monkeypatch):
    msg = "静息心率 比你 18 天基线高 2.5σ (52bpm→61bpm) ↑趋势 (数据较少, 仅供参考)"
    # rising + low_confidence:置信不足 → **不**升级持续就医出口
    _patch_baselines(
        monkeypatch, [_rhr(low_confidence=True, trend="rising", message=msg)]
    )
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    assert advs[0]["low_confidence"] is True
    assert "仅供参考" in advs[0]["detail"]
    # 置信不足不升级:不应出现持续就医出口
    assert "若持续" not in advs[0]["detail"]
    assert "就医" not in advs[0]["detail"]


# ── 7. compute_personal_baselines 抛异常 → 降级返回 [] ─────────────────────
def test_baseline_exception_degrades_to_empty(monkeypatch):
    def _boom(db, user_id, today=None):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(sentinel, "compute_personal_baselines", _boom)
    # 不抛,返回空
    assert sentinel.deviation_advisories(db=None, user_id=1) == []


# ── 8. 措辞安全:无禁词,含非因果 ──────────────────────────────────────────
def test_advisory_wording_safety(monkeypatch):
    _patch_baselines(monkeypatch, [_rhr(trend="stable")])
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    detail = advs[0]["detail"]
    for w in FORBIDDEN_WORDS:
        assert w not in detail, f"禁词出现在 advisory detail: {w!r}"
    assert "非因果" in detail
    # 模块级常量本身也得干净
    assert "非因果" in sentinel.ATTRIBUTION_INVITE
    for w in FORBIDDEN_WORDS:
        assert w not in sentinel.ATTRIBUTION_INVITE


# ── 9. 集成:进入 agenda today() ──────────────────────────────────────────
def test_sentinel_item_in_agenda_today(monkeypatch, db, auth_user_and_headers):
    from app.services import agenda_service

    user, _ = auth_user_and_headers
    _patch_baselines(monkeypatch, [_rhr(trend="stable")])

    result = agenda_service.today(db, user.id)
    items = result["items"]
    sentinel_items = [i for i in items if i["type"] == "baseline_deviation"]
    assert len(sentinel_items) == 1
    assert sentinel_items[0]["metric"] == "resting_heart_rate"
    assert "非因果" in sentinel_items[0]["detail"]


# ── 10. D1 核心:急性值无论如何都兜底产 advisory ──────────────────────────
def test_d1_acute_value_always_produces_safety_net(monkeypatch):
    # 模拟「SafetyGuardian 会漏」(twin.resting_hr=None 时急性规则 early-return)。
    # 哨兵以窗口内 clean[-1]=102 检测到急性 → 必须自身产带就医出口的 advisory 兜底。
    _patch_baselines(monkeypatch, [_rhr(latest=102.0, z=5.0)])
    advs = sentinel.deviation_advisories(db=None, user_id=7)
    assert len(advs) == 1, "急性值必须兜底产 advisory,不得静默丢"
    assert "就医" in advs[0]["detail"]
    assert "偏离正常范围" in advs[0]["detail"]
    # 仍标非因果(归因邀请保留)
    assert "非因果" in advs[0]["detail"]


# ── 11. 持续亚急性 rising → 带「若持续」就医出口 ──────────────────────────
def test_subacute_rising_has_persistence_exit(monkeypatch):
    # 高置信 + rising + 非急性(latest 在界内)→ 「若持续数日不回落,建议就医排查」
    _patch_baselines(
        monkeypatch, [_rhr(trend="rising", low_confidence=False, latest=61.0)]
    )
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    detail = advs[0]["detail"]
    assert "若持续" in detail
    assert "就医" in detail
    for w in FORBIDDEN_WORDS:
        assert w not in detail


# ── 12. 单次抖动(stable)→ 不带就医出口 ──────────────────────────────────
def test_single_jitter_stable_no_medical_exit(monkeypatch):
    # 非急性 + 无方向漂移(stable)→ 只软 info + 归因邀请,不升级
    _patch_baselines(
        monkeypatch, [_rhr(trend="stable", low_confidence=False, latest=61.0)]
    )
    advs = sentinel.deviation_advisories(db=None, user_id=1)
    assert len(advs) == 1
    detail = advs[0]["detail"]
    assert "就医" not in detail
    assert "若持续" not in detail
    assert "偏离正常范围" not in detail
    assert "非因果" in detail
