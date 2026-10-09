"""Private aggregate operations; no LLM, Health reads/writes or timer side effects."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import update
from app.models.life_navigation import LifeNavigationWorkspace
from app.models.user import User
from app.schemas.life_navigation import LifeBackup, LifeData, LifeHistory, LifeWorkspace


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _row(db, user_id):
    return db.query(LifeNavigationWorkspace).filter_by(user_id=user_id).populate_existing().first()


def _view(row):
    if row is None:
        return LifeWorkspace()
    return LifeWorkspace(revision=row.revision, data=LifeData.model_validate(row.data), updated_at=_utc(row.updated_at))


def get_workspace(db, user_id):
    return _view(_row(db, user_id))


def get_history(db, user_id):
    row = _row(db, user_id)
    return [LifeHistory.model_validate(item) for item in row.history] if row else []


def get_backup(db, user_id):
    row = _row(db, user_id)
    return LifeBackup(workspace=_view(row), history=[LifeHistory.model_validate(item) for item in row.history] if row else [])


def _lock(db, user_id, expected_revision):
    # NO KEY UPDATE serializes owner mutations without blocking child FK checks.
    user = db.query(User).filter_by(id=user_id).populate_existing().with_for_update(key_share=True).first()
    if not user or not user.is_active or not user.is_approved or user.is_managed:
        raise HTTPException(403, '请使用有效的本人账号')
    row = _row(db, user_id)
    if (row.revision if row else 0) != expected_revision:
        raise HTTPException(409, '规划已由另一页面更新，请重新读取后核对')
    return row


def _save(db, user_id, row, expected_revision, documents):
    try:
        return _persist(db, user_id, row, expected_revision, documents)
    except Exception:
        db.rollback()
        raise


def _persist(db, user_id, row, expected_revision, documents):
    history = list(row.history) if row else []
    revision = expected_revision
    stamp = datetime.now(timezone.utc)
    for document in documents:
        revision += 1
        history.append(LifeHistory(revision=revision, data=document, updated_at=stamp).model_dump(mode='json'))
    history = history[-20:]
    data = documents[-1].model_dump(mode='json')
    if row is None:
        row = LifeNavigationWorkspace(user_id=user_id, revision=revision, data=data, history=history, updated_at=stamp)
        db.add(row)
        db.flush()
    else:
        result = db.execute(update(LifeNavigationWorkspace).where(
            LifeNavigationWorkspace.user_id == user_id,
            LifeNavigationWorkspace.revision == expected_revision,
        ).values(revision=revision, data=data, history=history, updated_at=stamp)
          .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, '规划版本冲突，未覆盖当前内容')
    saved = LifeWorkspace(revision=revision, data=documents[-1], updated_at=stamp)
    db.commit()
    return saved


def save_workspace(db, user_id, payload):
    # Revalidate before obtaining write locks; callers cannot bypass typed rules.
    document = LifeData.model_validate(payload.data.model_dump(mode='json'))
    row = _lock(db, user_id, payload.expected_revision)
    return _save(db, user_id, row, payload.expected_revision, [document])


def restore_workspace(db, user_id, revision, expected_revision):
    row = _lock(db, user_id, expected_revision)
    source = next((item for item in (row.history if row else []) if item['revision'] == revision), None)
    if source is None:
        raise HTTPException(404, '历史版本不存在或已超出保留范围')
    document = LifeData.model_validate(source['data'])
    return _save(db, user_id, row, expected_revision, [document])


def import_backup(db, user_id, expected_revision, backup):
    backup = LifeBackup.model_validate(backup.model_dump(mode='json'))
    documents = [item.data for item in backup.history]
    # The imported current state is always final, regardless of source numbering.
    if documents and documents[-1] == backup.workspace.data:
        documents = documents[:-1]
    documents.append(backup.workspace.data)
    row = _lock(db, user_id, expected_revision)
    # Retain the pre-import state even when incoming history already fills the cap.
    if row is not None and len(documents) >= 20:
        documents = documents[-19:]
    return _save(db, user_id, row, expected_revision, documents)
