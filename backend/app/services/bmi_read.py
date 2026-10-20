"""Owner-scoped, dated, deterministic BMI facts. No profile weight fallback."""
from datetime import date
import math
from app.models.user_profile import UserProfile
from app.models.weight import WeightRecord
from app.utils.number_format import format_display_number


def read_bmi(db, user_id: int, reference_date: date) -> dict:
    if type(user_id) is not int or user_id <= 0 or type(reference_date) is not date:
        raise ValueError('invalid_bmi_read_scope')
    height = db.query(UserProfile.height_cm).filter(UserProfile.user_id == user_id).scalar()
    # SQL selects only the bounded facts needed for this calculation. The
    # date is user-local; future records and malformed weights are excluded.
    row = (db.query(WeightRecord.weight, WeightRecord.record_date)
           .filter(WeightRecord.user_id == user_id, WeightRecord.record_date <= reference_date,
                   WeightRecord.weight > 0, WeightRecord.weight < float('inf'))
           .order_by(WeightRecord.record_date.desc(), WeightRecord.created_at.desc(), WeightRecord.id.desc()).first())
    if height is None or not math.isfinite(height) or height <= 0:
        return {'status': 'missing_data', 'missing': ['height_cm']}
    if row is None:
        return {'status': 'missing_data', 'missing': ['dated_weight']}
    denominator = (height / 100) ** 2 if height < 1e150 else float('inf')
    if denominator <= 0 or not math.isfinite(denominator):
        return {'status': 'invalid_data', 'missing': ['valid_measurements']}
    bmi = row.weight / denominator
    if not math.isfinite(bmi):
        return {'status': 'invalid_data', 'missing': ['valid_measurements']}
    return {'status': 'complete', 'height_cm': height, 'weight_kg': row.weight,
            'weight_date': row.record_date.isoformat(), 'bmi': bmi}


def bmi_reply(result: dict) -> str:
    if result.get('status') == 'invalid_data':
        return '现有身高或体重数值无效，暂时无法计算 BMI。请核对测量数值和单位后再计算。'
    if result.get('status') != 'complete':
        missing = '身高' if result.get('missing') == ['height_cm'] else '带测量日期的有效体重'
        return f'目前缺少{missing}，暂时无法计算 BMI。请先补充记录，再计算。'
    f = format_display_number
    return (f"根据你记录的身高 {f(result['height_cm'])} cm 和 {result['weight_date']} 的体重 "
            f"{f(result['weight_kg'])} kg，BMI 为 {f(result['bmi'])}。\n\n"
            '计算方法：体重（kg）÷ 身高（m）的平方。使用的是上述日期的体重，不代表今天重新测量。'
            'BMI 是体格指标，不能单独判断健康状况。')
