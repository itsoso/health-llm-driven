"""Bounded current-self intake grammar shared by authorization and execution.

Spans refer to the NFKC, whitespace-free source; they are never model offsets.
No unknown residue, date inference, strength conversion or partial grants.
"""
from dataclasses import dataclass
import re
import unicodedata
from typing import Literal

_COUNT = r'(?:[1-9][0-9]*|[一二两三四五六七八九]|[一二三四五六七八九]?十[一二三四五六七八九]?)'
_SUPPLEMENT = r'(?:锌片|钙片|鱼油|肌酸|甘氨酸镁|褪黑素|复合维生素|维生素[abcd][0-9]*)'
_DRINK = r'(?:豆浆|牛奶|酸奶)'
_DOSE = rf'{_COUNT}(?:粒|片)'
_VOLUME = rf'(?:[1-9][0-9]*\.[0-9]+|{_COUNT}|半)(?:杯|毫升|ml)'
_HEADER = re.compile(r'(?:请|帮我)?(?:记录|记下)(?:一下)?(?:补剂|饮食)?[:：]?[，,]?')
_PREFIX = re.compile(r'(?:我)?(?:今天|刚才|刚刚)?')
_VERB = re.compile(r'(?:刚)?(?P<verb>服用了|吃了|服了|喝了)')
_SEPARATOR = re.compile(r'(?:[，,、](?:并且|然后|还有|还|和|以及)?|并且|然后|还有|还|以及|和)')
_PATTERNS = tuple(
    (kind, re.compile(pattern))
    for kind, name, amount in (
        ('supplement', _SUPPLEMENT, _DOSE), ('diet', _DRINK, _VOLUME)
    )
    for pattern in (rf'(?P<amount>{amount})(?P<name>{name})', rf'(?P<name>{name})(?P<amount>{amount})')
)


@dataclass(frozen=True)
class IntakeItem:
    record_type: Literal['supplement', 'diet']
    name: str
    amount_text: str
    source_span: tuple[int, int]

    @property
    def canonical_text(self) -> str:
        label, verb = ('补剂', '吃了') if self.record_type == 'supplement' else ('饮食', '喝了')
        return f'记录{label}{verb}{self.amount_text}{self.name}'


@dataclass(frozen=True)
class IntakePlan:
    status: Literal['not_applicable', 'complete', 'needs_clarification']
    items: tuple[IntakeItem, ...] = ()
    reason: str = ''


def parse_intake_plan(value: str) -> IntakePlan:
    text = ''.join(unicodedata.normalize('NFKC', str(value or '')).split()).casefold()
    header = _HEADER.match(text)
    mixed_candidate = bool(re.search(_SUPPLEMENT, text) and re.search(_DRINK, text))
    if header is None:
        return IntakePlan('needs_clarification' if mixed_candidate and re.search(r'记录|记下', text) else 'not_applicable', reason='untrusted_prefix')
    end = len(text) - (1 if text.endswith(('.', '。', '!', '！')) else 0)
    position = header.end()
    items: list[IntakeItem] = []
    previous_verb = ''
    while position < end:
        start = position
        prefix = _PREFIX.match(text, position)
        position = prefix.end()
        verb = _VERB.match(text, position)
        if verb:
            previous_verb = verb.group('verb')
            position = verb.end()
        elif not items:
            break
        match = next(((kind, pattern.match(text, position)) for kind, pattern in _PATTERNS
                      if pattern.match(text, position)), None)
        if match is None:
            break
        kind, parsed = match
        if (kind == 'diet') != (previous_verb == '喝了'):
            break
        if any(item.name == parsed.group('name') for item in items) or len(items) == 8:
            return IntakePlan('needs_clarification', reason='duplicate_or_limit')
        items.append(IntakeItem(kind, parsed.group('name'), parsed.group('amount'), (start, parsed.end())))
        position = parsed.end()
        if position == end:
            return IntakePlan('complete', tuple(items))
        separator = _SEPARATOR.match(text, position)
        if separator:
            position = separator.end()
        elif not _VERB.match(text, position) and not text.startswith('我', position):
            break
    # Only claim incomplete mixed input or a recognized intake prefix. Other
    # established health-write grammars retain their existing authorization.
    if mixed_candidate or items:
        return IntakePlan('needs_clarification', reason='unconsumed_input')
    return IntakePlan('not_applicable')
