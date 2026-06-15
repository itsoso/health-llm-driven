"""CGM 急性血糖告警的新鲜度门(安全评审 CGM 加固收尾)。

修复:补录历史极值血糖 / 传感器停同步的旧 spike 被当「最新读数」误触「立即就医」CRITICAL。
门规则:能证明读数陈旧(latest_measured_at 已知且 >60min)才抑制;年龄未知不抑制(保真阳性)。
"""
from datetime import datetime, timedelta, timezone

from app.agents.safety_guardian.rules.cgm import (
    cgm_severe_hyperglycemia,
    cgm_severe_hypoglycemia,
)
from app.twin.schema import CgmContext, HealthTwin, TwinMeta


def _twin(mg_dl, measured_at):
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.cgm = CgmContext(has_cgm=True, latest_mg_dl=mg_dl, latest_measured_at=measured_at)
    return t


def test_fresh_severe_low_fires():
    now = datetime.now(timezone.utc)
    assert cgm_severe_hypoglycemia(_twin(45, now - timedelta(minutes=5))) is not None


def test_stale_severe_low_suppressed():
    # 昨天的 45 mg/dL(补录/停同步)→ 不该触发"立即补糖"急性告警
    old = datetime.now(timezone.utc) - timedelta(hours=20)
    assert cgm_severe_hypoglycemia(_twin(45, old)) is None


def test_unknown_age_still_fires():
    # measured_at 未知 → 不抑制(保真阳性)
    assert cgm_severe_hypoglycemia(_twin(45, None)) is not None


def test_fresh_severe_high_fires():
    now = datetime.now(timezone.utc)
    assert cgm_severe_hyperglycemia(_twin(320, now - timedelta(minutes=10))) is not None


def test_stale_severe_high_suppressed():
    old = datetime.now(timezone.utc) - timedelta(days=1)
    assert cgm_severe_hyperglycemia(_twin(320, old)) is None
