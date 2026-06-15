"""health_record skill 录入域加固 —— 弱模型 tool-calling 容错(schema 层)。

覆盖系统审查发现的「静默默认 / 必填易漏 / 单位陷阱」三类:
- CGM:mmol/L 自动换算 mg/dL、measured_at 默认 now、二者皆缺报错
- mood:record_date 默认今天
- illness:见 test_illness_episode_alias.py
"""
from datetime import date

import pytest


class TestCgmReadingHardening:
    def test_mmol_auto_converts_to_mgdl(self):
        from app.api.cgm import CgmReadingIn
        r = CgmReadingIn(glucose_mmol_l=6.5)
        assert r.glucose_mg_dl == 117.0          # 6.5 × 18.0(与 property 同口径)

    def test_measured_at_not_defaulted_in_schema(self):
        # schema 不默认 measured_at(默认在单条端点;batch 缺时间须被 service 跳过)
        from app.api.cgm import CgmReadingIn
        assert CgmReadingIn(glucose_mmol_l=6.5).measured_at is None

    def test_mgdl_still_works(self):
        from app.api.cgm import CgmReadingIn
        r = CgmReadingIn(glucose_mg_dl=110)
        assert r.glucose_mg_dl == 110

    def test_neither_raises(self):
        from app.api.cgm import CgmReadingIn
        with pytest.raises(Exception):
            CgmReadingIn()

    def test_mmol_high_out_of_range_rejected(self):
        from app.api.cgm import CgmReadingIn
        with pytest.raises(Exception):
            CgmReadingIn(glucose_mmol_l=99)  # > 33 上限

    def test_mmol_converts_below_floor_rejected(self):
        # 安全评审阻断1:mmol 1.0 → 18mg/dL(<20)必须被换算后复检拒绝,不得绕过下限
        from app.api.cgm import CgmReadingIn
        with pytest.raises(Exception):
            CgmReadingIn(glucose_mmol_l=1.0)


class TestMoodHardening:
    def test_record_date_defaults_today(self):
        from app.schemas.mood import MoodRecordCreate
        m = MoodRecordCreate(mood_score=4)
        assert m.record_date == date.today()

    def test_mood_score_range_enforced(self):
        from app.schemas.mood import MoodRecordCreate
        with pytest.raises(Exception):
            MoodRecordCreate(mood_score=8)  # 1–5 才合法
