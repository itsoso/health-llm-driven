"""Executable record contracts shared by planning, policy, dispatch and proof.

Resolving a contract binds user-owned facts; an unresolved completion obligation
never grants permission. Provider proposals may omit facts but may not contradict
or add to the bound record. Only authoritative event readback completes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Callable

from pydantic import BaseModel, ValidationError
from app.schemas.record_capability import NasalWashRecord


@dataclass(frozen=True)
class RecordCapability:
    record_type: str
    label: str
    schema: type[BaseModel]
    parse: Callable[[str, datetime], BaseModel | None]
    endpoint: str
    readback_endpoint: str
    resource_type: str
    description: str
    auto_record_channels: tuple[str, ...] = ("typed",)
    event_type: str = "wash"


@dataclass(frozen=True)
class BoundRecord:
    capability: RecordCapability
    # Serialized at resolution, so callers cannot mutate the authorization.
    payload_json: str

    def arguments(self) -> dict:
        return {'record_type': self.capability.record_type, 'data': json.loads(self.payload_json)}

    def accepts(self, arguments: dict) -> bool:
        if (set(arguments) - {'record_type', 'data'}
                or arguments.get('record_type') != self.capability.record_type
                or not isinstance(arguments.get('data'), dict)):
            return False
        data = arguments['data']
        expected = json.loads(self.payload_json)
        # Omitted values are filled from the user's statement, never the model.
        return all(k in expected and not isinstance(v, bool) and v == expected[k]
                   for k, v in data.items())

    def event_id(self, source: str) -> str:
        return hashlib.sha256((source + '\0' + self.capability.record_type).encode()).hexdigest()

    def verifies(self, row: dict, *, owner_id: int, event_id: str) -> bool:
        expected = json.loads(self.payload_json)
        event = row.get('event')
        return bool(
            type(row.get('user_id')) is int and row['user_id'] == owner_id
            and type(row.get('id')) is int and row['id'] > 0
            and row.get('checkin_date') == expected['record_date']
            and isinstance(event, dict) and event.get('event_id') == event_id
            and event.get('type') == self.capability.event_type
            and type(event.get('count')) is int
            and (event.get('volume_ml') is None or type(event.get('volume_ml')) in (int, float))
            and all(event.get(k) == v for k, v in expected.items() if k != 'record_date')
        )


_NUM = r'(?:[1-9]\d?|一|二|两|三|四|五|六|七|八|九|十)'
_PREFIX = r'(?:(?:请|麻烦)?(?:帮我|替我|给我)?(?:记录|记下|记一下|打卡|保存)(?:一下)?[，,:：]*)?'
_DAY = r'(?:(?P<day>今天|今日|昨天|昨日)(?:[（(](?P<label>\d{4}-\d{2}-\d{2})[）)])?|(?P<date>\d{4}-\d{2}-\d{2}))?'
_WASH = re.compile(
    rf'^{_PREFIX}{_DAY}[，,:：]*(?:我)?(?:已|已经)?(?:洗鼻|冲洗鼻腔|鼻腔冲洗)(?:了)?'
    rf'(?P<count>{_NUM})次[，,。;；]*'
    r'(?:(?:使用|用)(?:了)?(?:一支|一瓶)?(?:(?P<before>\d+(?:\.\d+)?)(?:毫升|ml)(?:的)?'
    r'(?P<solution>生理盐水|盐水|清水)|(?P<solution_first>生理盐水|盐水|清水)'
    r'(?P<after>\d+(?:\.\d+)?)(?:毫升|ml)))?[。.!！]*$', re.IGNORECASE,
)


def _parse_nasal_wash(text: str, now: datetime) -> BaseModel | None:
    match = _WASH.fullmatch(re.sub(r'\s+', '', text))
    if match is None:
        return None
    groups = match.groupdict()
    target = now.date() - timedelta(days=int(groups['day'] in {'昨天', '昨日'}))
    if groups['label'] and groups['label'] != target.isoformat():
        return None
    if groups['date']:
        from datetime import date
        try:
            target = date.fromisoformat(groups['date'])
        except ValueError:
            return None
        if target > now.date():
            return None
    numbers = dict(zip('一二两三四五六七八九十', (1,2,2,3,4,5,6,7,8,9,10)))
    count = numbers.get(groups['count'])
    if count is None:
        count = int(groups['count'])
    volume = groups['before'] or groups['after']
    try:
        return NasalWashRecord(count=count, volume_ml=float(volume) if volume else None,
                               solution=groups['solution'] or groups['solution_first'], record_date=target)
    except ValidationError:
        return None


RECORD_CAPABILITIES = (
    RecordCapability('nasal_wash', '洗鼻', NasalWashRecord, _parse_nasal_wash,
                     '/checkin/nasal-wash', '/checkin/{record_id}/nasal-wash/{event_id}', 'health_checkin',
                     '记录本人已完成的洗鼻行为；count 为本次次数，volume_ml 为本次总用量（毫升），'
                     'solution 为用户说出的液体，record_date 为当地日期。未提供的用量和液体留空，不推算或推荐剂量。'),
)


def resolve_record_capability(text: str, now: datetime) -> BoundRecord | None:
    matches = []
    for capability in RECORD_CAPABILITIES:
        payload = capability.parse(str(text or ''), now)
        if payload is not None:
            matches.append(BoundRecord(capability, payload.model_dump_json()))
    return matches[0] if len(matches) == 1 else None


def record_capability(record_type: str) -> RecordCapability | None:
    return next((item for item in RECORD_CAPABILITIES if item.record_type == record_type), None)


def capability_contract_payload() -> dict:
    from pathlib import Path
    import inspect
    return {'version': 1, 'behavior_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'records': {item.record_type: {'schema': item.schema.model_json_schema(),
                       'schema_behavior_sha256': hashlib.sha256(inspect.getsource(item.schema).encode()).hexdigest(),
                       'endpoint': item.endpoint, 'readback_endpoint': item.readback_endpoint,
                       'auto_record_channels': item.auto_record_channels, 'event_type': item.event_type,
                       'resource_type': item.resource_type}
                        for item in RECORD_CAPABILITIES}}
