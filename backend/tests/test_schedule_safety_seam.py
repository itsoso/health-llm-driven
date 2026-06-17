"""cut 5 安全 seam:DDI/DSI 硬禁忌 → 补剂拒排 / 处方药行警告。R4:处方药永不被拒。"""
from app.services.schedule_safety_seam import compute_seam
from app.services.day_schedule_service import schedule_from_medications


class _M:
    def __init__(self, id, name, category):
        self.id = id
        self.name = name
        self.category = category


def test_seam_dsi_rejects_supplement_warns_drug():
    # 维K 补剂 × 华法林(HIGH 拮抗)→ 补剂拒排、华法林只警告不拒。
    meds = [_M(1, "Vitamin K", "supplement"), _M(2, "华法林", "medication")]
    forbidden, warnings = compute_seam(meds)
    assert 1 in forbidden                 # 维K 补剂 → 拒排
    assert 2 in warnings                  # 华法林 → 行警告
    assert 2 not in forbidden             # R4:处方药永不被拒


def test_schedule_rejects_supplement_keeps_warned_drug():
    meds = [_M(1, "Vitamin K", "supplement"), _M(2, "华法林", "medication")]
    out = schedule_from_medications(meds)
    rejected_ids = {r["id"] for r in out["rejected"]}
    assert "med:1" in rejected_ids        # 维K 进 rejected(走告警通道,不排时间轴)
    sched = {s["id"]: s for s in out["scheduled"]}
    assert "med:2" in sched               # 华法林 仍排上(不漏给药)
    assert sched["med:2"].get("warning")  # 且带行警告


def test_seam_low_interaction_no_action():
    # 钙×铁(INFO 错峰)→ seam 不动(交给求解器螯合间隔);不拒不警告。
    meds = [_M(1, "钙片", "supplement"), _M(2, "铁剂", "supplement")]
    forbidden, warnings = compute_seam(meds)
    assert forbidden == {} and warnings == {}


def test_seam_no_meds_safe():
    assert compute_seam([]) == ({}, {})
