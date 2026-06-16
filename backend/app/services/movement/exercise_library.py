"""循证动作内容库 (R17 裁决④:循证内容 + LLM 只合成)。

代码内注册表(仿 gene_rules_registry 风格,不建 DB 表)。每条动作的 form cue / 进阶规则 /
语音串都是**人写死的循证内容**,带 evidence_tier。LLM 不参与生成 form cue —— 错 form → 受伤
= 运动版医疗边界(守原则①确定性优先)。

进阶规则(progression_rule)是**确定性函数**:吃「上次完成情况」→ 产出本次 plan + 一句进阶说明。
门控降量逻辑在 guided_task.py(yellow 减量 / red swap),本模块只管「全量进阶曲线」。

证据级: A 多 RCT/Meta+强指南 · B 单 RCT/大样本观察 · C 机制合理人体证据不足。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class Plan:
    sets: Optional[int] = None
    reps: Optional[int] = None
    duration_sec: Optional[int] = None
    rest_sec: Optional[int] = None


@dataclass(frozen=True)
class LastCompletion:
    """上次完成情况(从 ExerciseRecord / agenda 完成事件取;取不到 → None 字段)。"""
    completed: Optional[bool] = None     # 是否完成
    reps: Optional[int] = None           # 上次实际次数(单组)
    sets: Optional[int] = None
    rpe: Optional[float] = None          # 自觉用力度 6-20 或 1-10(此处按 1-10)


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    domain: str                          # strength | mobility
    evidence_tier: str                   # A | B | C
    cues: List[str]
    default_plan: Plan
    progression_rule: Callable[["Exercise", Optional[LastCompletion]], "ProgressionResult"]
    voice_script: List[str]
    media_ref: Optional[str] = None
    contraindications: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgressionResult:
    plan: Plan
    note: str


# ── 确定性进阶规则 ────────────────────────────────────────────────
# 规则:上次完成且 RPE 不高(<8/10) → 加量;上次未完成或 RPE 高 → 维持(不降,降量是门控的事)。

def _progress_reps(ex: "Exercise", last: Optional[LastCompletion]) -> ProgressionResult:
    base = ex.default_plan
    if last is None or last.completed is None:
        return ProgressionResult(base, "首次/无历史:按默认量起步,记下 RPE 以便下次进阶")
    if last.completed and (last.rpe is None or last.rpe < 8):
        bumped = replace(base, reps=(base.reps or 0) + 2)
        return ProgressionResult(bumped, f"上次完成且不吃力 → 每组 +2 次({base.reps}→{bumped.reps})")
    if last.completed:
        return ProgressionResult(base, "上次完成但偏吃力(RPE≥8):维持当前量,巩固一次")
    return ProgressionResult(base, "上次未完成:维持当前量,先做满再加")


def _progress_hold(ex: "Exercise", last: Optional[LastCompletion]) -> ProgressionResult:
    """柔韧/拉伸:按时长进阶,封顶 90s/动作(久拉无额外收益,B)。"""
    base = ex.default_plan
    if last is None or last.completed is None or not last.completed:
        return ProgressionResult(base, "按默认时长完成即可,贵在每日坚持")
    cur = base.duration_sec or 0
    nxt = min(cur + 30, 90)
    if nxt == cur:
        return ProgressionResult(base, "已达单组时长上限(90s),保持频率即可")
    bumped = replace(base, duration_sec=nxt)
    return ProgressionResult(bumped, f"上次完成 → 每组 +30s({cur}→{nxt}s)")


# ── 注册表 ────────────────────────────────────────────────────────
_LIBRARY: Dict[str, Exercise] = {
    "pushup_standard": Exercise(
        id="pushup_standard",
        name="标准俯卧撑",
        domain="strength",
        evidence_tier="B",
        cues=[
            "双手略宽于肩,手指朝前,掌根压实地面",
            "收紧核心与臀,身体从头到脚跟成一条直线,别塌腰别撅臀",
            "下放时肘部约 45° 贴近身体(不外展成 90°),胸口接近地面",
            "全程匀速,下放 2 秒、推起 1 秒,呼气推起",
        ],
        default_plan=Plan(sets=3, reps=15, rest_sec=60),
        progression_rule=_progress_reps,
        voice_script=[
            "准备:双手撑地,身体成一条直线",
            "开始第一组,跟我节奏:下——起",
            "保持核心收紧,别塌腰",
            "本组完成,休息 60 秒",
        ],
        media_ref="exercise/pushup_standard.mp4",
        contraindications=["肩/腕/肘急性疼痛 → 停", "近期上肢手术或骨折未愈 → 停"],
    ),
    "pushup_knee": Exercise(
        id="pushup_knee",
        name="跪姿俯卧撑",
        domain="strength",
        evidence_tier="B",
        cues=[
            "膝盖着地作为支点,小腿可交叠抬起",
            "膝到头仍保持一条直线,核心收紧,别在髋部折叠",
            "下放时肘约 45° 贴身,胸口接近地面",
            "降低了负荷,适合标准俯卧撑做不满 8 个时过渡",
        ],
        default_plan=Plan(sets=3, reps=12, rest_sec=60),
        progression_rule=_progress_reps,
        voice_script=[
            "准备:膝盖着地,膝到头成一条直线",
            "开始第一组:下——起",
            "髋别下塌,核心收住",
            "本组完成,休息 60 秒",
        ],
        media_ref="exercise/pushup_knee.mp4",
        contraindications=["肩/腕/肘急性疼痛 → 停", "膝部不能受压 → 改其他降级动作"],
    ),
    "stretch_basic": Exercise(
        id="stretch_basic",
        name="基础全身拉伸",
        domain="mobility",
        evidence_tier="C",
        cues=[
            "每个动作静态保持,拉到轻微紧绷感即可,不到疼痛",
            "全程自然呼吸,呼气时尝试再放松一点,别憋气也别弹震",
            "颈/肩/胸/髋/腿后侧依次过一遍,两侧对称",
            "恢复不足或休息日的低负荷选择,促进血流、不增训练压力",
        ],
        default_plan=Plan(sets=1, duration_sec=300, rest_sec=0),
        progression_rule=_progress_hold,
        voice_script=[
            "我们做一组轻拉伸,放松身体",
            "从颈部开始,缓慢转动,保持呼吸",
            "到大腿后侧,前屈拉到轻微紧绷,保持",
            "很好,慢慢起身,结束",
        ],
        media_ref="exercise/stretch_basic.mp4",
        contraindications=["拉伸中任何关节锐痛 → 停"],
    ),
}

# RED zone 兜底动作(strength 在 red 被 swap 成它)
RED_FALLBACK_ID = "stretch_basic"

# 各 domain 的默认首选动作
_DOMAIN_DEFAULT: Dict[str, str] = {
    "strength": "pushup_standard",
    "mobility": "stretch_basic",
}


def get_exercise(exercise_id: str) -> Optional[Exercise]:
    return _LIBRARY.get(exercise_id)


def default_exercise_for_domain(domain: str) -> Optional[Exercise]:
    ex_id = _DOMAIN_DEFAULT.get(domain)
    return _LIBRARY.get(ex_id) if ex_id else None


def red_fallback_exercise() -> Exercise:
    return _LIBRARY[RED_FALLBACK_ID]


def all_exercises() -> List[Exercise]:
    return list(_LIBRARY.values())
