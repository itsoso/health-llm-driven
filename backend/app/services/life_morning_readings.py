"""Read only the authenticated owner's morning reports from trusted Proofroom."""
import json
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.life_morning_readings import MorningReadingDetail, MorningReadingItem, MorningReadingList

ORIGIN = 'https://base.executor.life'
MAX_BYTES = 2_500_000
PAGE_SIZE = 30


def _client():
    return httpx.Client(timeout=10, follow_redirects=False, trust_env=False)


def _read(client, path, token):
    try:
        with client.stream('GET', ORIGIN + path, headers={'Authorization': 'Bearer ' + token}) as response:
            if response.status_code == 404:
                raise HTTPException(404, '晨读不存在或无权访问')
            if response.status_code != 200:
                raise HTTPException(502, '晨读服务暂不可用，请稍后重试')
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise HTTPException(502, '晨读响应超出范围')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '晨读服务暂不可用，请稍后重试') from None


def _verify_owner(client, owner_id, token):
    identity = _read(client, '/api/external-reports/identity', token)
    if type(identity.get('user_id')) is not int or identity['user_id'] != owner_id:
        raise HTTPException(502, '晨读账号校验未通过')


def _item(row):
    try:
        stamp = datetime.fromisoformat(row['generated_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError()
        return MorningReadingItem(report_id=row['report_id'], title=row['title'], generated_at=stamp,
                                  reading_date=stamp.astimezone(ZoneInfo('Asia/Taipei')).date())
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
        raise HTTPException(502, '晨读数据未通过校验') from None


def list_readings(owner_id: int, token: str, offset: int) -> MorningReadingList:
    with _client() as client:
        _verify_owner(client, owner_id, token)
        rows = _read(client, f'/api/external-reports?offset={offset}', token).get('items')
        if not isinstance(rows, list) or len(rows) > PAGE_SIZE or any(not isinstance(r, dict) for r in rows):
            raise HTTPException(502, '晨读列表未通过校验')
        items = [_item(r) for r in rows if r.get('source') == 'morning_reading']
        return MorningReadingList(items=items, next_offset=offset + PAGE_SIZE if len(rows) == PAGE_SIZE and offset + PAGE_SIZE <= 100_000 else None)


def get_reading(owner_id: int, token: str, report_id: str) -> MorningReadingDetail:
    report_id = str(UUID(report_id))
    with _client() as client:
        _verify_owner(client, owner_id, token)
        row = _read(client, '/api/external-reports/' + report_id, token).get('report')
        if (not isinstance(row, dict) or type(row.get('user_id')) is not int
                or row['user_id'] != owner_id or row.get('source') != 'morning_reading'
                or row.get('report_id') != report_id):
            raise HTTPException(404, '晨读不存在或无权访问')
        try:
            return MorningReadingDetail(**_item(row).model_dump(), content_text=row['content_text'])
        except (KeyError, ValidationError):
            raise HTTPException(502, '晨读正文未通过校验') from None
