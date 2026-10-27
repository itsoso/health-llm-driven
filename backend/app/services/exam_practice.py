"""Read-only study projections and serialized, idempotent server-graded submissions."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from pydantic import ValidationError
from app.models.exam_practice import ExamAttemptRecord
from app.models.life_navigation import LifeNavigationWorkspace
from app.models.user import User
from app.schemas.exam_practice import Catalog, ExamAttempt, ExamAttemptWrite, ExamHistory, ExamPlanBlock, ExamPractice, ExamProgress, ExamQuestion

TAIPEI = ZoneInfo('Asia/Taipei')
CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'exam_questions.json'
LEGACY_KEYS = ['english','comprehensive','review','e01','e02','e03','e04','e05','e06','e07','e08','m01','m02','m03','m04','m05','m06','l01','l02','l03','l04','l05','l06','writing','paper-english','paper-comprehensive','paper-writing','paper-review']
LEGACY_NOTICE = '旧工作区仅能证明每日首次与最近复练，精确时间和被覆盖的中间尝试未知；同日旧记录先于服务端流水展示，不代表已核实先后顺序。新提交逐次保留，不随工作区覆盖。'


def utcnow():
    return datetime.now(timezone.utc)


def load_catalog():
    try:
        return Catalog.model_validate(json.loads(CATALOG_PATH.read_text(encoding='utf-8')))
    except (OSError, ValueError, ValidationError) as exc:
        raise HTTPException(503, '审校题库暂不可用，请稍后重试') from exc


def legacy_task_id(day, key):
    if key in LEGACY_KEYS:
        code = LEGACY_KEYS.index(key) + 1
    elif re.fullmatch(r'[eml]1(?:0[1-9]|1[0-9]|20)', key):
        code = {'e':1000,'m':2000,'l':3000}[key[0]] + int(key[1:])
    else:
        return None
    value = day.isoformat()
    return f'e6ba2027-{value[:4]}-4{value[5:7]}{value[8]}-8{value[9]}00-{code:012x}'


def _aware(stamp):
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def _view(row):
    question = ExamQuestion.model_validate({key: value for key, value in row.question_snapshot.items()
                                            if key not in ('answer', 'explanation')})
    return ExamAttempt(id=row.id, question=question, question_id=row.question_id, question_version=row.question_version,
        choice_index=row.choice_index, correct_index=row.correct_index, correct=row.correct,
        explanation=row.question_snapshot['explanation'], study_date=row.study_date,
        answered_at=_aware(row.answered_at), elapsed_seconds=row.elapsed_seconds, source='submitted')


def submit(db, user_id, payload):
    payload = ExamAttemptWrite.model_validate(payload.model_dump())
    try:
        # PostgreSQL NO KEY UPDATE serializes owner writes while permitting child FK checks.
        user = db.query(User).filter_by(id=user_id).populate_existing().with_for_update(key_share=True).first()
        if not user or not user.is_active or not user.is_approved or user.is_managed:
            raise HTTPException(403, '请使用有效的本人账号')
        existing = db.query(ExamAttemptRecord).filter_by(user_id=user_id, request_id=str(payload.request_id)).first()
        if existing:
            if (existing.question_id, existing.question_version, existing.choice_index, existing.elapsed_seconds) != (
                    payload.question_id, payload.question_version, payload.choice_index, payload.elapsed_seconds):
                raise HTTPException(409, '此请求标识已用于另一份作答，请勿覆盖原记录')
            answer = _view(existing)
            db.commit()
            return answer
        question = next((q for q in load_catalog().questions if q.id == payload.question_id), None)
        if question is None:
            raise HTTPException(404, '题目不存在，请刷新题库')
        if payload.question_version != question.version:
            raise HTTPException(409, '题目版本已更新，请刷新后重新作答')
        if payload.choice_index >= len(question.options):
            raise HTTPException(422, '请选择有效答案')
        stamp = utcnow().astimezone(timezone.utc)
        record = ExamAttemptRecord(id=str(uuid4()), user_id=user_id, request_id=str(payload.request_id),
            question_id=question.id, question_version=question.version, choice_index=payload.choice_index,
            correct_index=question.answer, correct=payload.choice_index == question.answer,
            elapsed_seconds=payload.elapsed_seconds, study_date=stamp.astimezone(TAIPEI).date(), answered_at=stamp,
            question_snapshot=question.model_dump(mode='json'))
        db.add(record)
        db.flush()
        answer = _view(record)
        db.commit()
        return answer
    except Exception:
        db.rollback()
        raise


def _legacy(db, user_id, catalog, question_id=None):
    row = db.query(LifeNavigationWorkspace).filter_by(user_id=user_id).first()
    if row is None:
        return []
    # Only the original stable identities can be associated with old free-text results.
    by_prompt = {q.prompt:q for q in catalog.questions if legacy_task_id(date(2026,10,27),q.id) is not None}
    attempts = []
    for week in row.data.get('weeks', {}).values():
        for task in week.get('tasks', []):
            question = by_prompt.get(task.get('criterion'))
            if question is None or question_id is not None and question.id != question_id:
                continue
            try:
                day = date.fromisoformat(task.get('date', ''))
            except (ValueError, TypeError):
                continue
            if task.get('id') != legacy_task_id(day, question.id):
                continue
            for source, field in [('legacy_first', 'result'), ('legacy_latest', 'improvement')]:
                body = task.get(field, '')
                match = re.fullmatch(r'作答：([A-D])；正确答案：([A-D])。\n(.+)', body, re.DOTALL)
                if not match:
                    continue
                choice, correct = ord(match[1])-65, ord(match[2])-65
                if choice >= len(question.options) or correct != question.answer or match[3] != question.explanation:
                    continue
                attempts.append(ExamAttempt(id=str(uuid5(NAMESPACE_URL,f'life-exam:{user_id}:{task["id"]}:{source}')),
                    question=ExamQuestion.model_validate(question.model_dump(exclude={'answer','explanation'})),
                    question_id=question.id, question_version=1, choice_index=choice, correct_index=correct,
                    correct=choice == correct, explanation=match[3], study_date=day, answered_at=None,
                    elapsed_seconds=None, source=source))
    return attempts


def _attempts(db, user_id, catalog, question_id=None, through=None):
    query = db.query(ExamAttemptRecord).filter_by(user_id=user_id)
    if question_id is not None:
        query = query.filter_by(question_id=question_id)
    if through is not None:
        query = query.filter(ExamAttemptRecord.study_date <= through)
    # Sequence disambiguates submissions at the same server timestamp without fabricated times.
    records = [(_view(row), row.sequence) for row in query.order_by(ExamAttemptRecord.sequence).all()]
    records += [(item, -2 if item.source == 'legacy_first' else -1)
                for item in _legacy(db, user_id, catalog, question_id)
                if through is None or item.study_date <= through]
    records.sort(key=lambda item:(item[0].study_date, item[1], item[0].id))
    return [item for item, _ in records]


def history(db, user_id, question_id, offset, limit):
    rows = _attempts(db, user_id, load_catalog(), question_id)
    rows.reverse()
    return ExamHistory(items=rows[offset:offset+limit], total=len(rows))


def _progress(attempts):
    grouped = defaultdict(list)
    for attempt in attempts:
        grouped[attempt.question_id].append(attempt)
    result = []
    for question_id, records in grouped.items():
        latest = records[-1]
        days = {}
        for record in records:
            days[record.study_date] = record.correct
        streak = 0
        for correct in reversed(list(days.values())):
            if not correct:
                break
            streak += 1
        interval = [1,3,7][min(max(streak-1,0),2)]
        result.append(ExamProgress(question_id=question_id, attempt_count=len(records),
            latest_correct=latest.correct, ever_wrong=any(not r.correct for r in records),
            last_date=latest.study_date, next_review_date=latest.study_date+timedelta(days=interval)))
    return result


def practice(db, user_id, day=None):
    catalog = load_catalog()
    today = utcnow().astimezone(TAIPEI).date()
    day = day or today
    progress = _progress(_attempts(db, user_id, catalog, through=day))
    by_id = {p.question_id:p for p in progress}
    weak_topics = {(q.subject, q.topic) for q in catalog.questions if q.id in by_id and not by_id[q.id].latest_correct}
    queue = []
    for subject in ['英语', '数学', '逻辑']:
        pool = [q for q in catalog.questions if q.subject == subject]
        due = [q for q in pool if q.id in by_id and by_id[q.id].next_review_date <= day]
        due.sort(key=lambda q:(by_id[q.id].latest_correct, by_id[q.id].next_review_date, q.id))
        unseen = [q for q in pool if q.id not in by_id]
        unseen.sort(key=lambda q:((q.subject, q.topic) not in weak_topics, sha256(f'{day}:{q.id}'.encode()).hexdigest()))
        queue.extend(q.id for q in (due+unseen)[:6])
    count = {subject:sum(q.id in queue and q.subject == subject for q in catalog.questions) for subject in ['英语','数学','逻辑']}
    english = f'当前可练{count["英语"]}题；先限时作答，再核对原文依据与生词。' if count['英语'] else '当前没有到期或未做英语题；回看已保存解析，或继续计划中的英语（二）真题分段。'
    comprehensive = f'当前可练数学{count["数学"]}题、逻辑{count["逻辑"]}题；先到期复练，再补未做题，记录卡点。' if count['数学']+count['逻辑'] else '当前没有到期或未做管综题；回看已保存解析，或继续计划中的管综真题分段。'
    plan = [ExamPlanBlock(subject='英语（二）',minutes=45,instruction=english),
            ExamPlanBlock(subject='管综专项',minutes=40,instruction=comprehensive),
            ExamPlanBlock(subject='写作训练',minutes=20,instruction='沿用已选真题写作题，先列论证提纲再写一段；本题库未提供自动作文评分。'),
            ExamPlanBlock(subject='错题复盘',minutes=15,instruction='回看已保存错题，说明错因并闭卷复述解题依据；答对一次不等于掌握。')]
    return ExamPractice(catalog_version=catalog.catalog_version, day=day, today=today,
        questions=[ExamQuestion.model_validate(q.model_dump(exclude={'answer','explanation'})) for q in catalog.questions],
        progress=progress, queue=queue, plan=plan, total_minutes=sum(p.minutes for p in plan), legacy_notice=LEGACY_NOTICE)
