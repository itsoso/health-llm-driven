"""血压分类 —— 单一真源。

原本内联在 `app/api/blood_pressure.py`。D1(garmin-sync 治理 Wave 3)把 blood_pressure
读维度迁进程内直读时抽到这里,让 api 层与 service 层(`agent_read_tools`)共用同一实现,
避免 service 层 import api 层(层倒挂)。抽取后 api 端点行为一字不变(golden-master 校验)。
"""
from __future__ import annotations


def classify_blood_pressure(systolic: int, diastolic: int) -> str:
    """血压分类"""
    if systolic < 120 and diastolic < 80:
        return "正常"
    elif systolic < 130 and diastolic < 80:
        return "正常偏高"
    elif systolic < 140 or diastolic < 90:
        return "高血压前期"
    elif systolic < 160 or diastolic < 100:
        return "高血压1级"
    elif systolic < 180 or diastolic < 110:
        return "高血压2级"
    else:
        return "高血压3级"
