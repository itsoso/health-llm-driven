from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.schemas.life_navigation import LifeData, LifeWorkspaceWrite
from app.services import life_navigation as service


def note(**changes):
    return dict(id=str(uuid4()), title='合成笔记', body='仅测试文本', **changes)


def test_notebook_bounds_and_unique_ids():
    item = note()
    assert LifeData(notebook=[item]).notebook[0].body == '仅测试文本'
    for entries in ([item, item], [{**item, 'title': 'x' * 201}], [{**item, 'body': 'x' * 20001}], [note() for _ in range(101)]):
        with pytest.raises(ValidationError):
            LifeData(notebook=entries)


def test_notebook_persists_isolated_and_rejects_legacy_erasure(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    saved = service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data={'notebook': [note()]}))
    assert saved.revision == 1
    assert service.get_workspace(db, user.id).data.notebook[0].body == '仅测试文本'
    assert service.get_workspace(db, user.id + 10000).data.notebook == []
    with pytest.raises(service.HTTPException) as error:
        service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=1, data={'strategy': {'vision': 'old client'}}))
    assert error.value.status_code == 409
    db.rollback()
    assert len(service.get_workspace(db, user.id).data.notebook) == 1
    empty = service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=1, data={'notebook': []}))
    assert empty.data.notebook == []
    assert service.restore_workspace(db, user.id, 1, 2).data.notebook[0].body == '仅测试文本'
