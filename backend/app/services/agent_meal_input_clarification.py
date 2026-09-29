"""Closed meal-input frames that require clarification, never write authority.

Only complete original utterances are considered. No quote/provenance erasure,
history lookup, model-selected target, or current-clock meal inference belongs
here. Existing attached-media and explicitly targeted correction paths remain
responsible for their own authorization and verified receipts.
"""
from dataclasses import dataclass
import re


_MEAL = r"早餐|午餐|晚餐|加餐"
_MISSING_IMAGE_RECORD = re.compile(
    rf"(?:请)?(?:帮我)?(?:"
    rf"(?:根据|按照)(?:这张|这些)?(?:图片|照片)(?:来)?(?:记录|保存)(?:今天)?(?:{_MEAL})|"
    rf"(?:记录|保存)(?:这张|这些)?(?:图片|照片)(?:里|中)(?:的)?(?:今天)?(?:{_MEAL})"
    rf")[。.!！]?"
)
_UNTARGETED_PORTION = re.compile(
    r"(?:其实|实际上)?(?:我)?只吃了(?:一半|二分之一|1[/／]2)[。.!！]?"
)
_UNTARGETED_MEAL_RELABEL = re.compile(
    rf"不是(?P<previous>{_MEAL})[，,]是(?P<replacement>{_MEAL})[。.!！]?"
)


@dataclass(frozen=True)
class MealInputClarification:
    reason_code: str
    reply: str


def resolve_meal_input_clarification(
    text: str, *, has_attachment: bool,
) -> MealInputClarification | None:
    if has_attachment:
        return None
    # Whitespace is presentation only; every semantic character must match.
    source = re.sub(r"[ \t]+", "", str(text or "")).strip()
    if _MISSING_IMAGE_RECORD.fullmatch(source):
        return MealInputClarification(
            "meal_image_required",
            "本轮没有收到图片，尚未记录这餐。请上传图片，或直接写明这餐吃了什么及份量。",
        )
    relabel = _UNTARGETED_MEAL_RELABEL.fullmatch(source)
    if (_UNTARGETED_PORTION.fullmatch(source)
            or (relabel and relabel["previous"] != relabel["replacement"])):
        return MealInputClarification(
            "meal_correction_target_required",
            "你要修改哪一餐或哪条记录？请说明日期、餐次或记录编号，并写明要改的内容。"
            "本轮尚未新增或修改记录。",
        )
    return None
