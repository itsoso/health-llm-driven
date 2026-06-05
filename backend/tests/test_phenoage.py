# -*- coding: utf-8 -*-
"""PhenoAge 抓手回归 —— Levine 2018 表型年龄。

钉住四件事:
1. golden:对一组健康 50 岁样例,代码输出 ≈ 独立手算值 41.68 岁(对齐论文系数+单位)
2. 方向性:健康 marker → 偏年轻;恶化 marker → 偏老
3. 缺值兜底:任一输入 None → 返回 None(不猜算)
4. 单位敏感:白蛋白用错单位(g/dL 当 g/L)会得到离谱结果(守护"单位纪律")

golden 值的独立来源:用模块 docstring 声明的单位,按 Levine 2018 公式逐项手算
(见 docs/design-longevity-mvp.md §3),与本实现互为交叉验证,非自证。
"""
from app.services.phenoage import compute_phenoage


# 健康 50 岁样例(单位见 phenoage.py docstring)
_HEALTHY_50 = dict(
    albumin_g_per_l=45.0,
    creatinine_umol_per_l=80.0,
    glucose_mmol_per_l=5.0,
    crp_mg_per_dl=0.1,
    lymphocyte_pct=30.0,
    mcv_fl=90.0,
    rdw_pct=13.0,
    alp_u_per_l=60.0,
    wbc_10e9_per_l=6.0,
    age_years=50.0,
)


def test_golden_healthy_50yo():
    """对齐独立手算:PhenoAge ≈ 41.68(误差 < 0.1 岁)。"""
    r = compute_phenoage(**_HEALTHY_50)
    assert r is not None
    assert abs(r.phenotypic_age - 41.68) < 0.1, f"got {r.phenotypic_age}"
    # delta = 表型年龄 - 实足年龄,健康样例应为负(偏年轻)
    assert r.delta_years < 0
    assert abs(r.delta_years - (r.phenotypic_age - 50.0)) < 0.011
    assert r.evidence_tier == "validated"
    assert r.claim_boundary  # 诚实纪律:边界声明非空


def test_unhealthy_older_than_healthy():
    """恶化各项 marker(炎症/血糖/RDW 升高,白蛋白降低)→ 表型年龄显著变老。"""
    bad = dict(_HEALTHY_50)
    bad.update(
        albumin_g_per_l=38.0,    # 低白蛋白
        glucose_mmol_per_l=9.0,  # 高血糖
        crp_mg_per_dl=1.0,       # 炎症
        rdw_pct=16.0,            # RDW 升高(强权重)
        wbc_10e9_per_l=9.0,
    )
    healthy = compute_phenoage(**_HEALTHY_50)
    worse = compute_phenoage(**bad)
    assert healthy is not None and worse is not None
    assert worse.phenotypic_age > healthy.phenotypic_age + 5  # 明显更老


def test_missing_input_returns_none():
    incomplete = dict(_HEALTHY_50)
    incomplete["crp_mg_per_dl"] = None
    assert compute_phenoage(**incomplete) is None


def test_crp_floor_no_crash_on_zero():
    """CRP=0(检测不到)不应 ln(0) 崩溃,应走下限。"""
    z = dict(_HEALTHY_50)
    z["crp_mg_per_dl"] = 0.0
    r = compute_phenoage(**z)
    assert r is not None
    assert r.phenotypic_age == r.phenotypic_age  # 非 NaN


def test_unit_sensitivity_albumin():
    """守护单位纪律:白蛋白误用 g/dL(4.5)代替 g/L(45)→ 结果明显偏离,
    用来防止未来有人传错单位却以为没事。"""
    wrong = dict(_HEALTHY_50)
    wrong["albumin_g_per_l"] = 4.5  # 错:这是 g/dL 数值
    correct = compute_phenoage(**_HEALTHY_50)
    bad = compute_phenoage(**wrong)
    assert correct is not None and bad is not None
    # 白蛋白系数为负,数值小 40 倍 → 表型年龄会明显偏老
    assert abs(bad.phenotypic_age - correct.phenotypic_age) > 1.0
