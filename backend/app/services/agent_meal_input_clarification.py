"""Closed meal-input frames that require clarification, never write authority.

Only complete original utterances are considered. No quote/provenance erasure,
history lookup, model-selected target, or current-clock meal inference belongs
here. Existing attached-image and explicitly targeted correction paths remain
responsible for their own authorization and verified receipts.
"""
import re
from dataclasses import dataclass

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
_MEAL_COUNT_INPUT = re.compile(
    r"(?:(?:请)?(?:帮我)?(?:记录(?:一下)?|记下))?"
    r"(?:我)?(?:(?:今天|今日|昨天|昨日)(?:的)?)?"
    r"(?:早餐|早饭|午餐|午饭|晚餐|晚饭|加餐|早上|中午|晚上)?"
    r"(?:我)?(?:是|确实|其实|实际|一共|总共)?(?:吃了|吃过|吃的|有)?"
    r"(?:[1-9][0-9]?|[一二两三四五六七八九十]+)(?:顿(?:饭)?|餐|次饭)"
    r"(?P<duplicate>[，,]?(?:都)?(?:没有|没|并非|不是)"
    r"(?:重复(?:记录|记账|录入)?|记重了?)(?:的)?)?[。.!！]?"
)


@dataclass(frozen=True)
class MealInputClarification:
    reason_code: str
    reply: str
    requires_clarification: bool = True


def resolve_meal_count_input(text: str) -> MealInputClarification | None:
    """A complete meal-count statement supplies no food or write target.

    Match the original utterance, including its entire tail. Food quantities,
    quotations, other owners and compound instructions remain on their normal
    paths. This shared predicate also runs in the final tool authorizer's
    classifier, so bypassing the local response cannot create a guessed meal.
    """
    source = re.sub(r"[ \t]+", "", str(text or "")).strip()
    match = _MEAL_COUNT_INPUT.fullmatch(source)
    if match is None:
        return None
    if match["duplicate"]:
        return MealInputClarification(
            "meal_duplicate_clarification",
            "明白，你是在说明这些餐次不是重复记录。本轮不新增、合并或删除饮食记录。",
            requires_clarification=False,
        )
    return MealInputClarification(
        "meal_food_details_required",
        "你说明的是餐次数量。要记录具体饮食，还需要确认吃了什么及份量；本轮未新增饮食记录。",
    )


def resolve_meal_input_clarification(
    text: str, *, has_image: bool,
) -> MealInputClarification | None:
    count_input = resolve_meal_count_input(text)
    if count_input is not None:
        return count_input
    # A document upload is not visual evidence or a bound meal target.
    if has_image:
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
