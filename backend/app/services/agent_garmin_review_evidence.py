"""Evidence limits for one closed Garmin review; never grants tool authority."""
import math
import re
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

_UNSUPPORTED = re.compile(
    r'\d{1,3}\s*岁|最大心率.{0,18}\d+(?:\.\d+)?\s*[%％]|'
    r'(?:心率|训练).{0,8}(?:区间|分区)|'
    r'心率.{0,12}(?:稳定|平稳|波动正常)|(?:无|没有)(?:明显)?异常波动|'
    r'(?:中等|适中|正常|安全).{0,6}强度|强度.{0,8}(?:中等|适中|正常|安全)|'
    r'(?:这次|本次|你|数据|运动).{0,20}(?:正常|安全|适合)|适合.{0,10}(?:日常|耐力|基础)|'
    r'每周.{0,18}(?:次|增加|提升|缩短)|(?:缩短|加快|提高).{0,20}配速'
)
_DENIAL = re.compile(r'不能|无法|不可|不足以|不代表|并非|尚不能|未能|不应|缺少|未知|尚未|不确定')


def has_unsupported_garmin_claim(text: str) -> bool:
    # Split adversative clauses so a prior disclaimer cannot excuse a later
    # positive assertion ("不能保证安全，但数据正常").
    for clause in re.split(r'[。！？!?；;，,\n]|但是|然而|不过|仍然|依然|却|但|仍', text or ''):
        if _UNSUPPORTED.search(clause) and not _DENIAL.search(clause):
            return True
    return False


def bounded_garmin_record_facts(payload: dict | None) -> str:
    """Project verified finite metrics, not the rejected model's interpretation."""
    payload = payload or {}
    record = payload.get('record') if payload.get('availability') == 'available' else None
    lines = ['以下仅陈述本轮读取的已存记录，未采用缺少证据的个体分析。']
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
        lines.append('本轮没有可用于个体分析的完整运动记录。')
    lines.append('未提供年龄、个人最大心率依据和连续心率序列，无法判断个人心率区间、波动或运动是否安全，也不能据此制定个体进阶训练安排。')
    lines.append('如运动中或运动后出现不适，请停止活动并及时寻求医疗帮助。')
    return '\n'.join(lines)
