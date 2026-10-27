"""Photo leftovers produce an owner-bound, revision-checked edit proposal.

The original photo snapshot is the absolute baseline even after a prior edit.
Nothing in this module creates, updates or deletes a diet record or photo asset.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import base64
import binascii
import hashlib
import json
import re
from time import perf_counter
from zoneinfo import ZoneInfo

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietPhotoAsset, DietRecord
from app.services.ai.diet_leftover_vision import estimate_leftovers, LeftoverRecognitionError
from app.services.chat_utils import read_owned_chat_image_data_uri
from app.services.post_record_quality import build_diet_adjust_action
from app.utils.number_format import format_display_number

_LEFTOVER = re.compile(r'剩余|剩下|剩菜|没吃完|未吃完|餐后(?:的)?照片|leftovers?', re.I)
_MEALS = {'早餐':'breakfast','早饭':'breakfast','午餐':'lunch','午饭':'lunch',
          '晚餐':'dinner','晚饭':'dinner','加餐':'snack'}
_MEAL = '(?:早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)'
_REQUESTS = (
    re.compile(rf'(?P<meal>{_MEAL})剩余部分[，, ]*通过剩余部分[，, ]*修正记录的(?P<same>{_MEAL})[。.!！]?'),
    re.compile(rf'(?:请)?(?:根据|用|通过)(?:这张|这份)?(?:剩余|剩菜|餐后|没吃完)(?:部分)?(?:的)?照片'
               rf'(?:来)?(?:修正|修改|更新)(?:我(?:的)?)?(?:今天(?:的)?)?(?P<meal>{_MEAL})(?:记录)?[。.!！]?'),
    re.compile(rf'(?:这是)?(?:我(?:的)?)?(?:今天(?:的)?)?(?P<meal>{_MEAL})(?:的)?(?:剩余|剩下|没吃完)(?:部分)?'
               r'[，, ]*(?:请)?(?:根据|用|通过)(?:这张)?照片(?:来)?(?:修正|修改|更新)(?:这餐|原来|原)?(?:的)?记录[。.!！]?'),
)
_QUANTITY = re.compile(r'(?:约|大约)?\s*(?P<amount>\d+(?:\.\d+)?|[一二两三四五六七八九十半])\s*(?P<unit>千克|公斤|毫升|克|碗|份|个|只|块|片|杯|盘|根|颗|粒|g|kg|ml|mL)')
_NUMBERS = dict(zip('一二两三四五六七八九十半', (1,2,2,3,4,5,6,7,8,9,10,.5)))
# Full source-caption grammar: unrecognized dates, subjects, cancellation and
# hypothetical clauses cannot become today's owned photo by omission.
_SOURCE_CAPTION = re.compile(
    rf'(?:请)?(?:帮我|给我)?(?:记录(?:一下)?|这是)?(?:我(?:的)?)?(?:今天(?:的)?)?'
    rf'(?:这餐|这一餐|这顿饭|这顿|{_MEAL}|今早|今中午|今晚)?(?:的)?'
    r'(?:剩菜(?:照片)?|剩余(?:部分|这么多|照片)?|剩下(?:部分|这么多|照片)?|没吃完(?:的部分)?)'
    r'(?:照片)?(?:请?(?:计算(?:一下|下)?|算(?:一下|下)?|估算(?:一下|下)?)'
    r'(?:今天|今早|今中午|今晚)?(?:真正|实际)?(?:摄入量|吃下的份量))?'
)


def is_leftover_context(text):
    """A broad exclusion, never permission to read or write any record."""
    return bool(_LEFTOVER.search(str(text or ''))) or _requested_meal(text) is not None


def is_leftover_correction_request(text):
    """Only a complete current-turn request may enter the photo continuation."""
    return _requested_meal(text) is not None


def _requested_meal(text):
    for pattern in _REQUESTS:
        match = pattern.fullmatch(str(text or '').strip())
        if match:
            meal = _MEALS[match['meal']]
            same = match.groupdict().get('same')
            return meal if same is None or _MEALS[same] == meal else None
    return None


def _clarify(detail, *, reason='leftover_details_required', cards=None):
    return {'status':'waiting_for_user','reason':reason,'cards':cards or [],
            'sources_used':['本人指定餐次记录'] if cards else [],
            'reply':'尚未修改饮食记录。' + detail}


def _portion(food):
    if not isinstance(food, dict) or not isinstance(food.get('name'), str):
        return None
    name = food['name'].strip()
    if not 1 <= len(name) <= 40 or re.search(r'[\n+＋;；]', name):
        return None
    quantity = str(food.get('quantity') or '').strip()
    if len(quantity) > 40:
        return None
    match = _QUANTITY.fullmatch(quantity)
    if not match:
        return None
    amount = Decimal(str(_NUMBERS.get(match['amount'], match['amount'])))
    if not amount.is_finite() or not 0 < amount <= 10000:
        return None
    return name, amount, match['unit']


def consumed_description(foods, result):
    from app.services.ai.diet_leftover_vision import validate_leftover_result
    valid = validate_leftover_result(result, len(foods))
    labels = []
    for food, item in zip(foods, valid['items']):
        portion = _portion(food)
        if portion is None:
            raise LeftoverRecognitionError('baseline_quantity_unavailable')
        name, amount, unit = portion
        consumed = amount * (Decimal(1) - Decimal(str(item['remaining_fraction'])))
        if unit in {'千克', '公斤', 'kg'}:
            consumed *= 1000
            unit = '克'
        if consumed > 0:
            display = format_display_number(float(consumed))
            # This text becomes editable command input. Never round a write
            # quantity just to meet the display precision limit.
            if Decimal(str(display)) != consumed:
                raise LeftoverRecognitionError('portion_requires_manual_quantity')
            labels.append(f'{name} 约{display}{unit}')
    if not labels:
        raise LeftoverRecognitionError('no_consumed_food')
    return ' + '.join(labels)


def _editor(target, proposed=None):
    fields = ('meal_type','food_items','calories','protein','carbs','fat','fiber')
    action = build_diet_adjust_action(target.id, {key:getattr(target,key) for key in fields}, current_record=target)
    seed = action['payload']['patch']['adjust_record']
    if proposed is not None:
        seed['proposed_food_items'] = proposed
    return {'type':'record_quality','data':{
        'domain':'diet','title':f'{target.record_date} 餐后份量待确认','summary':'请核对实际吃下的食物和份量',
        'record_id':target.id,'expanded_sections':['adjust_record'],'adjust_record':dict(seed),
        'boundary':'照片对比是估算，尚未保存；确认后仅更新原餐并重新估算营养。',
    },'actions':[action]}


def _baseline(db, user_id, target):
    assets = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.user_id==user_id,DietPhotoAsset.diet_record_id==target.id,
        DietPhotoAsset.lifecycle=='attached',DietPhotoAsset.deleted_at.is_(None),
        DietPhotoAsset.classification=='food').order_by(DietPhotoAsset.ordinal).limit(4).all()
    if not assets or len(assets)>3:
        return None
    snapshot=assets[0].recognition_snapshot
    if (not isinstance(snapshot,dict) or snapshot.get('recognition_version')!='contextual_meal_photo_v1'
            or snapshot.get('multi_photo_incomplete') or snapshot.get('consumed_fraction',1)!=1
            or any(a.recognition_snapshot!=snapshot for a in assets)):
        return None
    foods=snapshot.get('foods')
    if not isinstance(foods,list) or not 1<=len(foods)<=12 or any(_portion(f) is None for f in foods):
        return None
    if len({a.origin_message_id for a in assets})!=1:
        return None
    source=(db.query(AgentMessage).join(AgentConversation)
        .filter(AgentConversation.user_id==user_id, AgentMessage.id==assets[0].origin_message_id,
                AgentMessage.role=='user').first())
    if source is None or not source.image_url:
        return None
    try:
        urls=json.loads(source.image_url)
    except (ValueError,TypeError):
        return None
    if (not isinstance(urls,list) or len(urls)!=len(assets)
            or [a.ordinal for a in assets]!=list(range(len(assets)))):
        return None
    try:
        images=[read_owned_chat_image_data_uri(url,user_id) for url in urls if isinstance(url,str)]
    except (ValueError,OSError):
        return None
    if len(images)!=len(assets):
        return None
    try:
        if any(hashlib.sha256(base64.b64decode(image.split(',',1)[1],validate=True)).hexdigest()
               != asset.content_sha256 for image,asset in zip(images,assets)):
            return None
    except (ValueError,IndexError,binascii.Error):
        return None
    return foods,images


def _clarified_photo(db, user_id, conversation_id, current_message_id, meal, now, timezone_name):
    # Never search past another turn, infer a target from model prose, or use a
    # previous day's photo for an explicit request about today's meal.
    recent = (db.query(AgentMessage).join(AgentConversation).filter(
        AgentConversation.user_id == user_id, AgentConversation.id == conversation_id,
        AgentMessage.id < current_message_id).order_by(AgentMessage.id.desc()).limit(2).all())
    if len(recent) != 2:
        return None
    answer, source = recent
    meta = answer.meta if isinstance(answer.meta, dict) else {}
    outcome = meta.get('turn_outcome')
    if (answer.role != 'assistant' or source.role != 'user'
            or meta.get('mode') != 'diet_photo_correction_proposal'
            or meta.get('client_turn_finalized') is not True
            or not isinstance(outcome, dict) or outcome.get('status') != 'waiting_for_user'
            or outcome.get('reason_code') != 'leftover_details_required'
            or not is_leftover_context(source.content) or source.created_at is None):
        return None
    created = source.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    local_zone = ZoneInfo(timezone_name)
    if (not timedelta(0) <= now - created <= timedelta(minutes=30)
            or created.astimezone(local_zone).date() != now.astimezone(local_zone).date()):
        return None
    caption = re.sub(r'\n\[附图: 1张\]$', '', source.content).strip()
    compact = re.sub(r'[\s，,。.!！]', '', caption)
    if _requested_meal(caption) != meal and not _SOURCE_CAPTION.fullmatch(compact):
        return None
    mentioned = {_MEALS[label] for label in _MEALS if label in caption}
    for label, value in (('今晚','dinner'), ('今早','breakfast'), ('今中午','lunch')):
        if label in caption:
            mentioned.add(value)
    if mentioned and mentioned != {meal}:
        return None
    try:
        urls = json.loads(source.image_url)
        if not isinstance(urls, list) or len(urls) != 1 or not isinstance(urls[0], str):
            return None
        data_uri = read_owned_chat_image_data_uri(urls[0], user_id)
        header, data = data_uri.split(',', 1)
        media = {'data:image/jpeg;base64':'jpeg', 'data:image/png;base64':'png',
                 'data:image/webp;base64':'webp'}.get(header)
        if media is None or not base64.b64decode(data, validate=True):
            return None
    except (TypeError, ValueError, OSError, binascii.Error):
        return None
    return [{'base64':data, 'type':media}]


async def build_leftover_proposal(db,user_id,conversation_id,current_message_id,text,images,now,timezone_name):
    images = images or []
    meal=_requested_meal(text)
    if meal is None:
        return _clarify('剩余照片不会记为新吃的一餐。请明确要修正的餐次，例如“根据剩菜照片修正今天午餐记录”。')
    if type(user_id) is not int or user_id<=0 or not isinstance(now,datetime) or now.tzinfo is None:
        return _clarify('无法核实本次请求，请从原餐记录点击修正本餐。')
    current=(db.query(AgentMessage).join(AgentConversation)
        .filter(AgentConversation.user_id==user_id,AgentConversation.id==conversation_id,
                AgentMessage.id==current_message_id,AgentMessage.role=='user').first())
    if current is None or current.content not in {text, f'{text}\n[附图: {len(images)}张]'}:
        return _clarify('无法核实本次照片来源，请从原餐记录点击修正本餐。')
    if not images and not current.image_url:
        images = _clarified_photo(db, user_id, conversation_id, current_message_id,
                                 meal, now, timezone_name)
        if images is None:
            return _clarify('没有找到紧接本次补充、且与今天指定餐次一致的剩菜照片。请重新附上该餐的剩菜照片并说明餐次，或从原餐记录点击修正本餐。')
    elif not current.image_url:
        return _clarify('无法核实本次照片来源，请从原餐记录点击修正本餐。')
    if len(images)!=1:
        return _clarify('请发送一张能看清整份剩余餐食的照片；本次没有新增或修改记录。')
    targets=db.query(DietRecord).filter(DietRecord.user_id==user_id,
        DietRecord.record_date==now.astimezone(ZoneInfo(timezone_name)).date(),
        DietRecord.meal_type==meal).limit(2).all()
    if len(targets)!=1:
        return _clarify('没有找到唯一对应的今日餐次记录，请在饮食页选择原记录后修正。')
    target=targets[0]
    baseline=_baseline(db,user_id,target)
    if baseline is None:
        return _clarify('缺少可核对的餐前照片或原始份量，不能仅凭剩余照片算出已吃多少。请在下方填写实际吃下的食物和份量后保存。',cards=[_editor(target)])
    # Freeze the revision before awaiting the model. A concurrent edit must
    # conflict at confirmation instead of silently replacing newer data.
    card=_editor(target)
    started=perf_counter()
    try:
        result=await estimate_leftovers(baseline[0],baseline[1],images[0])
        proposed=consumed_description(baseline[0],result)
    except LeftoverRecognitionError:
        answer=_clarify('照片对比还不能可靠确定实际吃下的份量（例如遮挡、食物不一致或全部剩下）。请在下方核对实际食用内容；本次没有写入。',cards=[card])
        answer.update(vision_calls=1, vision_ms=int((perf_counter()-started)*1000))
        return answer
    card['data']['adjust_record']['proposed_food_items']=proposed
    card['actions'][0]['payload']['patch']['adjust_record']['proposed_food_items']=proposed
    answer = _clarify(f'根据餐前和剩余照片，估算实际吃下：{proposed}。请核对下方份量，点击保存后更新原餐并重新估算营养，不会新增一餐。',
        reason='leftover_confirmation_required',cards=[card])
    answer['sources_used'] = ['本人指定餐次记录','本人餐前与餐后照片']
    answer.update(vision_calls=1, vision_ms=int((perf_counter()-started)*1000))
    return answer
