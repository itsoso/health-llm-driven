"""C2 动作图文指导 —— 策展确定性数据集(非 LLM)。

为什么是硬编码而非 LLM 生成:动作要领 / 常见错误 / 伤病红线属健康安全内容,
LLM 幻觉出的错误姿势或伤病建议是安全风险。这里全部人工策展、可评审、可 diff。
每条动作**必须**带非空 injury_red_lines + safety_note(出现红线立即停止并就医)。

数据流(纯读,无 DB):
    EXERCISES (dict) ──list_exercises()──▶ 浏览列表(key+name)
                     ──get_exercise(key)──▶ 完整图文条目 / None(未知 key)

新增动作:在 EXERCISES 加一条,injury_red_lines 与 safety_note 不得留空(测试守门)。
exercise_key 与 C1 周计划 / C3 Rokid 共用命名空间(如 "pushup"),改名要全链路一起改。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 通用安全兜底措辞:所有动作 safety_note 至少含「非医疗建议 + 伤病/慢病先就医」语义。
_SAFETY_NOTE = (
    "这是一般性运动要领,不是医疗建议。"
    "有伤病、慢性病或正在康复中,先咨询医生或康复师再练;"
    "练习中出现持续疼痛、头晕、胸闷等不适请立即停止并尽快就医。"
)

# 多条动作共用的通用伤病红线(再各自补专属红线)。
_COMMON_RED_LINES = [
    "关节或肌肉出现尖锐 / 持续疼痛(非普通酸胀)——立即停止",
    "胸痛、胸闷、心悸或呼吸困难——立即停止并尽快就医",
    "头晕、眼前发黑、恶心——立即停止,坐下休息,必要时就医",
]


def _entry(
    *,
    exercise_key: str,
    name: str,
    steps: List[str],
    common_mistakes: List[str],
    extra_red_lines: List[str],
) -> Dict[str, Any]:
    return {
        "exercise_key": exercise_key,
        "name": name,
        "steps": steps,
        "common_mistakes": common_mistakes,
        # 通用红线在前,专属红线在后;全部去就医出口
        "injury_red_lines": _COMMON_RED_LINES + extra_red_lines,
        "safety_note": _SAFETY_NOTE,
    }


EXERCISES: Dict[str, Dict[str, Any]] = {
    "pushup": _entry(
        exercise_key="pushup",
        name="俯卧撑",
        steps=[
            "双手略宽于肩,撑在地面,手腕在肩膀正下方。",
            "身体从头到脚跟保持一条直线,收紧核心和臀部。",
            "屈肘下降,肘部约朝向斜后方(不要完全外展),胸口接近地面。",
            "撑起回到起始位,全程呼吸顺畅,下降吸气、推起呼气。",
            "做不动标准式可改用屈膝俯卧撑或扶台阶的斜面俯卧撑过渡。",
        ],
        common_mistakes=[
            "塌腰、撅臀,核心没收紧导致下背受力。",
            "头部前探、含胸,颈部代偿发力。",
            "肘部完全向两侧外展,给肩关节增加压力。",
            "只做半程、下降幅度不够,失去训练意义。",
        ],
        extra_red_lines=[
            "肩关节弹响伴疼痛或无力——立即停止",
            "手腕负重时刺痛或麻木——立即停止,必要时就医",
        ],
    ),
    "squat": _entry(
        exercise_key="squat",
        name="徒手深蹲",
        steps=[
            "双脚与肩同宽或略宽,脚尖略外展。",
            "挺胸收腹,目视前方,重心落在全脚掌。",
            "屈髋屈膝向下坐,膝盖方向与脚尖一致,下蹲到大腿接近水平(量力而行)。",
            "脚跟发力站起,顶峰收紧臀部,不要锁死膝关节。",
            "下蹲吸气、起身呼气,保持脊柱中立不弓背。",
        ],
        common_mistakes=[
            "膝盖内扣(向内夹),增加膝关节压力。",
            "弓背或过度前倾,腰椎受力。",
            "脚跟离地、重心前移到脚尖。",
            "下蹲过快失控、起身时猛地反弹。",
        ],
        extra_red_lines=[
            "膝关节深处疼痛、卡顿或打软——立即停止",
            "下背部出现牵拉或放射性疼痛——立即停止,必要时就医",
        ],
    ),
    "plank": _entry(
        exercise_key="plank",
        name="平板支撑",
        steps=[
            "前臂着地,肘部在肩膀正下方,前臂与上臂约成直角。",
            "脚尖踩地,身体从头到脚跟保持一条直线。",
            "收紧核心和臀部,骨盆略后倾,不塌腰也不撅臀。",
            "自然呼吸,从能稳定保持的较短时间开始,逐步延长。",
            "保持中颈中立,目光落在双手前方地面。",
        ],
        common_mistakes=[
            "塌腰下沉,腰椎过度受力。",
            "撅臀过高,失去核心张力。",
            "憋气硬撑,应保持均匀呼吸。",
            "为追求时长而牺牲姿势,失稳后仍硬撑。",
        ],
        extra_red_lines=[
            "下背部出现明显疼痛(非肌肉酸胀)——立即停止",
            "肩部或手腕承重疼痛——立即停止,必要时就医",
        ],
    ),
    "pullup": _entry(
        exercise_key="pullup",
        name="引体向上",
        steps=[
            "正握或反握单杠,握距约与肩同宽或略宽。",
            "悬垂时主动沉肩、收紧肩胛,不要完全松垮挂着。",
            "用背部带动手臂,把胸口向单杠方向拉,下巴过杠。",
            "控制速度缓慢下放到手臂接近伸直,保持张力。",
            "拉不起来可用弹力带辅助或先做离心(慢放)与悬垂练习。",
        ],
        common_mistakes=[
            "靠甩动身体借力(摆荡式),失去背部训练效果。",
            "下放时完全放松、突然坠落,易拉伤肩肘。",
            "耸肩发力,肩颈代偿。",
            "幅度不足,没有下巴过杠或没有放到接近伸直。",
        ],
        extra_red_lines=[
            "肩关节或肘关节牵拉痛、弹响伴疼痛——立即停止",
            "手指 / 前臂麻木或握力突然丧失——立即停止,必要时就医",
        ],
    ),
    "lunge": _entry(
        exercise_key="lunge",
        name="箭步蹲",
        steps=[
            "双脚分开站立,挺胸收腹,核心收紧。",
            "一脚向前迈出一大步,重心居中。",
            "屈双膝下蹲,前膝在脚踝上方、不超过脚尖太多,后膝接近地面但不触地。",
            "前脚跟发力站起,回到起始位,左右交替。",
            "保持躯干直立,膝盖方向与脚尖一致。",
        ],
        common_mistakes=[
            "前膝过度前移超过脚尖,膝关节压力增大。",
            "上身前倾或弓背。",
            "步幅太小导致前膝压力集中。",
            "起身时左右晃动、重心不稳。",
        ],
        extra_red_lines=[
            "膝关节疼痛、打软或不稳——立即停止",
            "髋部或腹股沟出现牵拉痛——立即停止,必要时就医",
        ],
    ),
    "glute-bridge": _entry(
        exercise_key="glute-bridge",
        name="臀桥",
        steps=[
            "仰卧屈膝,双脚踩地与髋同宽,脚跟靠近臀部。",
            "双臂放身体两侧,掌心向下辅助稳定。",
            "收紧臀部,把骨盆抬起到肩-髋-膝接近一条直线。",
            "顶峰停顿挤压臀部,缓慢下放但不完全落地保持张力。",
            "全程用臀部发力,避免靠腰部硬挺。",
        ],
        common_mistakes=[
            "靠腰部反弓发力而不是臀部,下背受力。",
            "抬得过高造成腰椎过伸。",
            "脚离臀太远,腘绳肌代偿过多。",
            "下放过快、失去控制。",
        ],
        extra_red_lines=[
            "下背部出现疼痛或牵拉(非臀部发力感)——立即停止",
            "颈部承重不适——立即停止,必要时就医",
        ],
    ),
}


def list_exercises() -> List[Dict[str, str]]:
    """浏览用列表:只返回 key + name。"""
    return [{"exercise_key": k, "name": v["name"]} for k, v in EXERCISES.items()]


def get_exercise(exercise_key: str) -> Optional[Dict[str, Any]]:
    """完整图文条目;未知 key → None(端点转 404)。"""
    return EXERCISES.get(exercise_key)
