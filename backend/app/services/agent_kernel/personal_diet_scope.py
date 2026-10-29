"""Explicit first-person dietary evidence; unknown residue grants no authority."""
from dataclasses import dataclass
import re

_SELF = r'(?:我(?:自己|本人|个人)?|本人)的'
_SYSTEM = rf'(?:(?:health|健康)(?:系统|平台|应用)(?:中|里|内){_SELF})?'
_ITEMS = {'genetic': r'基因(?:信息|数据|检测结果)?', 'age': r'年龄',
          'weight': r'体重(?:记录|数据)?', 'season': r'季节'}
_REQUEST = re.compile(
    rf'(?:请)?(?:建议我(?:应该|该)?吃(?:点啥|什么)[，,。]?)?'
    rf'(?:基于|结合|根据){_SELF}{_SYSTEM}'
    r'(?:(?:信息|资料|数据)[，,]?(?:包括|包含))?'
    r'(?P<basis>.+?)(?:等)?[，,。]?'
    r'(?:请)?(?:给我(?:健康)?饮食(?:的)?(?:分析和推荐|分析和建议|建议|推荐)|'
    r'推荐我吃什么)[。.!！?？]?', re.I,
)
_SEPARATOR = re.compile(r'[，,、]|以及|和|与|及')

@dataclass(frozen=True)
class PersonalDietScope:
    evidence_dimensions: tuple[str, ...]
    season_requested: bool
    output_format: str = 'text'

    def queries(self):
        return [{'dimension': d} for d in self.evidence_dimensions]


def resolve_personal_diet_scope(text: str) -> PersonalDietScope | None:
    if not isinstance(text, str) or len(text) > 1000:
        return None
    match = _REQUEST.fullmatch(re.sub(r'\s+', '', text))
    if match is None:
        return None
    dimensions = []
    season = False
    for item in _SEPARATOR.split(match['basis']):
        item = re.sub(rf'^{_SELF}', '', item)
        dimension = next((key for key, pattern in _ITEMS.items() if re.fullmatch(pattern, item)), None)
        if dimension is None:
            return None
        if dimension == 'season':
            season = True
        elif dimension not in dimensions:
            dimensions.append(dimension)
    return PersonalDietScope(tuple(dimensions), season) if dimensions else None


def personal_diet_prompt(scope: PersonalDietScope) -> str:
    return (
        '[本轮个人饮食建议边界]\n'
        f'先实际查询明确列出的本人依据：{scope.queries()}，再给饮食分析和可执行的食物搭配建议。'
        '缺失的数据必须说明，不得拿历史上下文冒充本轮已查询。年龄只返回周岁或未知；'
        '体重查询最多最近10条，基因查询只覆盖当前账号的活动档案，不代表完整检测。'
        '区分事实、证据局限和建议。没有位点/解读证据不得推断基因风险或指定特殊饮食；'
        '基因倾向不是确诊，不据此断言疾病、食物过敏或绝对禁食。'
        '本轮未查询的病史、用药、补剂、今日摄入、恢复状态和所在地不能写成当前事实。'
        '信息不足时不估算个人热量缺口或治疗性营养目标；提供有条件的食物搭配和替换选项。'
        '食盐和钠不是同一单位；本轮建议只给少盐的食物/酱料替换，不输出盐或钠的每日克数目标。'
        '不能把空记录当作没有风险，不得开方、调药、推荐补剂剂量或宣称饮食能治疗疾病。'
        '即使信息缺失，也给明确标注适用前提的通用饮食选项，而不是只输出数据卡片。'
        '仅做只读分析，不保存计划、记录、提醒，不调用不受限的健康分析工具。'
        + ('季节只能依据当前日期作有条件的提示；所在地、气候和食材可得性未知时明确说明，'
           '不能仅凭时区认定所在地或查询定位。' if scope.season_requested else '')
    )


def personal_diet_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest, authorization_module_behavior_names,
    )
    return {'version': 'personal-diet-v1', 'items': dict(_ITEMS),
            'grammar': authorization_grammar_digest(globals()),
            'behavior': authorization_behavior_digest(globals(), authorization_module_behavior_names(globals(), __name__))}

_BASIS_LABELS = {'age': r'年龄|周岁|岁', 'weight': r'体重', 'genetic': r'基因|位点|遗传'}
_FOOD = re.compile(r'蔬菜|水果|全谷|粗粮|杂粮|豆类|豆腐|鱼|鸡蛋|蛋白质|奶|坚果|主食|含糖饮料|盐|油炸')
_DIET_ACTION = re.compile(r'建议|可(?:以)?(?:先|选|以|用|尝试|搭配)|选择|搭配|替换|减少|增加|优先|限制|少吃|多吃')
PERSONAL_DIET_INCOMPLETE_NOTICE = '查询已完成，但本轮饮食分析和建议尚未完成，不能视为个性化饮食方案。'
_SALT_QUANTITY = re.compile(
    r'(?:钠|盐)(?:摄入量|摄入|用量|总量|每日|每天|一天|建议|应|需|控制在|限制在|低于|少于|不超过|小于|最多|约|为|总|含量|目标|[<≤=：:（）()\s／/]|天){0,12}'
    r'(?:\d+(?:\.\d+)?|[一二三四五六七八九十两半]+)\s*(?:毫克|克|mg|g)'
    r'|(?:\d+(?:\.\d+)?|[一二三四五六七八九十两半]+)\s*(?:毫克|克|mg|g)\s*(?:[/／每]天)?\s*(?:总钠|钠|食盐|盐)',
    re.IGNORECASE,
)


def personal_diet_answer_complete(scope: PersonalDietScope, text: str) -> bool:
    """Task coverage only, never proof of medical correctness or read authority."""
    matching_text = re.sub(r'[*_`]', '', text)
    if _SALT_QUANTITY.search(matching_text) or not all(re.search(_BASIS_LABELS[d], text) for d in scope.evidence_dimensions):
        return False
    clauses = re.findall(r'[^。！？!?\n]+[。！？!?]?', text)
    return any(_FOOD.search(clause) and _DIET_ACTION.search(clause)
               and not re.search(r'[？?]|尚未|未提供|没(?:有)?给|还没|无法给|不能给|未生成|没有建议|'
                                 r'需要我|要不要|想让我|我(?:会|将|准备)|稍后|下一轮|待会|稍等', clause)
               for clause in clauses)
