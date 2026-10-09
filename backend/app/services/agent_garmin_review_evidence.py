"""Evidence limits for one closed Garmin review; never grants tool authority."""
import math
from datetime import datetime

from app.utils.number_format import format_display_number

GARMIN_REVIEW_EVIDENCE_LIMITS = (
    '本轮仅有已存运动记录的汇总字段；未提供年龄、个人最大心率依据、静息心率或连续心率序列。'
    '记录中的最高心率是这次记录的峰值，不是个人最大心率。'
    '时间仅按返回值及明确时区陈述；不得把带UTC偏移的时间猜作用户当地上午或下午。'
    '不得猜年龄或计算个人最大心率百分比、心率区间、训练区间；'
    '不得从平均和峰值心率判断波动稳定、无异常、强度适中、运动安全或适合个人。'
    '不得开具每周频次、提速或增加训练量的个体进阶处方。'
    '可以陈述实际指标、明确缺失证据，并提供停止不适活动及就医等有条件的通用提醒。'
)

def bounded_garmin_record_facts(payload: dict | None) -> str:
    """Project verified finite metrics, not the rejected model's interpretation."""
    payload = payload or {}
    record = payload.get('record') if payload.get('availability') == 'available' else None
    lines = ['本轮仅核对同步状态与已存记录，不是完整的个体训练分析。']
    if isinstance(record, dict):
        lines.append('记录来源：佳明。')
        for key, label in [('start_time', '开始时间'), ('end_time', '结束时间')]:
            raw = record.get(key)
            if isinstance(raw, str):
                try:
                    parsed = datetime.fromisoformat(raw)
                except ValueError:
                    continue
                if parsed.utcoffset() is not None:
                    lines.append(f'{label}：{parsed.isoformat()}。')
        for key, label, unit, divisor in [
            ('distance_meters', '距离', '公里', 1000),
            ('duration_seconds', '时长', '分钟', 60),
            ('avg_heart_rate', '平均心率', '次/分', 1),
            ('max_heart_rate', '记录内最高心率', '次/分', 1),
        ]:
            value = record.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                lines.append(f'{label}：{format_display_number(value / divisor)} {unit}。')
    else:
        lines.append('本轮未取得可用于分析的完整运动记录。')
    lines.append('未提供年龄、个人最大心率依据和连续心率序列，无法判断个人心率区间、波动或运动是否安全，也不能据此制定个体进阶训练安排。')
    lines.append('下一步请先确认同步完成及记录对应的活动；个体强度与进阶安排需要补充必要的健康背景和运动证据。')
    lines.append('如运动中或运动后出现不适，请停止活动并及时寻求医疗帮助。')
    return '\n'.join(lines)
