"""Model controls and persisted overrides are restricted to administrators."""
import pytest
from fastapi import HTTPException
from app.models.user import User
from app.models.user_profile import UserProfile
from app.api.user_llm_preference import get_preference, update_preference, PreferenceUpdate

def user(db, admin=False):
    u=User(username='admin' if admin else 'member', name='Synthetic', hashed_password='synthetic', is_admin=admin)
    db.add(u);db.commit();return u

def test_member_catalog_and_update_are_denied_without_profile_mutation(db):
    u=user(db)
    pref=get_preference(current_user=u, db=db)
    assert pref.model_id is None and pref.options == []
    with pytest.raises(HTTPException) as e:
        update_preference(PreferenceUpdate(model_id='qwen3.8-max'), current_user=u, db=db)
    assert e.value.status_code == 403
    assert db.query(UserProfile).filter_by(user_id=u.id).first() is None

def test_admin_can_select_disclosed_available_model(db, monkeypatch):
    from app.api import user_llm_preference as api
    u=user(db, True)
    option=api.ModelOption(id='synthetic',label='Synthetic',provider='synthetic',model='synthetic',speed_tier='fast')
    monkeypatch.setattr(api,'_list_options',lambda:[option])
    assert update_preference(PreferenceUpdate(model_id='synthetic'),current_user=u,db=db).model_id=='synthetic'

def test_demoted_admin_legacy_preference_cannot_override_default(db, monkeypatch):
    from types import SimpleNamespace
    from app.services.llm import factory, model_registry
    u=user(db);db.add(UserProfile(user_id=u.id,llm_model_id='synthetic'));db.commit()
    monkeypatch.setattr(factory,'_create_from_entry',lambda *a:pytest.fail('non-admin override used'))
    monkeypatch.setattr(model_registry,'get_model',lambda *a:SimpleNamespace())
    monkeypatch.setattr('app.services.ai_consent.is_disclosed_model',lambda *a:True)
    default=SimpleNamespace(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
    monkeypatch.setattr(factory,'get_llm_provider',lambda:default)
    assert factory.create_provider_for_user(u.id,db) is default

@pytest.mark.parametrize('admin', [False, True])
def test_extra_context_override_requires_current_db_admin(db, admin):
    import json
    from app.services.agent_executor import AgentExecutor
    u=user(db,admin)
    executor=AgentExecutor(db)
    override=executor._admin_model_override(json.dumps({'model_id':'qwen3.7-plus'}),u.id)
    assert override == ('qwen3.7-plus' if admin else None)

async def test_member_selftest_cannot_call_provider(db, monkeypatch):
    from app.api.user_llm_preference import selftest
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_user',lambda *a:pytest.fail('provider invoked'))
    with pytest.raises(HTTPException) as e:
        await selftest(current_user=user(db),db=db)
    assert e.value.status_code==403

def test_demotion_disables_every_legacy_preference_consumer(db, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.services.agent_executor import AgentExecutor
    from app.services.llm import model_registry
    u=user(db,True);db.add(UserProfile(user_id=u.id,llm_model_id='qwen3.7-plus'));db.commit()
    ex=AgentExecutor(db);ex._current_user_id=u.id
    monkeypatch.setattr(model_registry,'get_active_model_id',lambda:None)
    monkeypatch.setattr(model_registry,'get_model',lambda *a:SimpleNamespace(provider='langbridge-proxy',model='commercial/synthetic'))
    assert ex._user_effective_model_id()=='qwen3.7-plus'
    assert ex._should_send_raw_images_to_primary_model(u.id)
    u.is_admin=False;db.commit()
    assert ex._user_effective_model_id() is None
    assert not ex._should_send_raw_images_to_primary_model(u.id)
    assert ex._admin_model_override(json.dumps({'model_id':'qwen3.7-plus'}),u.id) is None
