"""
Fuel Strategist —— L3 能量策略 specialist。

职责：
- 读 Twin 的饮食今日 + 身体组成 + 训练负荷 + 补剂 + 基因
- 计算能量缺口、宏量完成度、饮水进度
- 输出下一餐建议 + 补水提醒 + 补剂时机
"""

from app.agents.fuel_strategist.strategist import FuelStrategistSpecialist

__all__ = ["FuelStrategistSpecialist"]
