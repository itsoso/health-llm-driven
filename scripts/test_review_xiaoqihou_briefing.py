"""Fixed fresh briefing preserves every previous owner row; never retries."""
import importlib.util
import json
from pathlib import Path
import pytest
from test_review_demo_briefing_repair import pg as legacy_pg, snapshot


def load():
    path = Path(__file__).with_name('review_xiaoqihou_briefing.py')
    spec = importlib.util.spec_from_file_location('xiaoqihou_core_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def pg(legacy_pg, monkeypatch):
    old, engine, schema = legacy_pg
    m = load()
    monkeypatch.setattr(m.rows, 'SCHEMA', schema)
    yield m, engine, schema


def test_inspect_requires_new_fixed_profile():
    m = load()
    assert m.TARGET == '8f7d94696424f92ff57243edb906cd6d2dd14a3a'
    assert m.SESSION_KEY == 'app-store-review-demo-xiaoqihou-v1'
    assert m.FIXTURE_SHA256 == '40263013f3b91292e997343f535a45520ec9c28c979e5410530f0f11c0beed14'


def test_pg_preserves_old_rows_and_other_owner(pg):
    from sqlalchemy import text
    m, e, s = pg
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with e.begin() as c:
        before = m.inspect_briefing_metadata(c, 'review@example.invalid', 1)
    with e.begin() as c:
        all_before = {t:c.execute(text(f'SELECT to_jsonb(t) FROM {s}.{t} t ORDER BY id')).scalars().all()
                      for t in ('users','agent_conversations','agent_messages')}
        result = m.create_briefing_rows(c, 'review@example.invalid', 1, before['database_snapshot_sha256'], fixture,
                                      ordering_metadata_plan=before['ordering_metadata_plan'])
        for t, existing in all_before.items():
            assert c.execute(text(f'SELECT to_jsonb(t) FROM {s}.{t} t WHERE id=ANY(:ids) ORDER BY id'),
                             {'ids':[r['id'] for r in existing]}).scalars().all() == existing
    with e.begin() as c:
        m.verify_created_briefing_rows(c, 'review@example.invalid', 1, result['after_sha256'], fixture)
    with pytest.raises(m.RepairError), e.begin() as c:
        m.create_briefing_rows(c, 'review@example.invalid', 1, before['database_snapshot_sha256'], fixture)


@pytest.mark.parametrize('change', ['future','duplicate','other_owner_key','admin','drift'])
def test_pg_rejects_without_new_rows(pg, change):
    from sqlalchemy import text
    m,e,s=pg
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with e.begin() as c:
        before=m.inspect_briefing_metadata(c,'review@example.invalid',1)
    with e.begin() as c:
        if change=='future': c.execute(text(f"UPDATE {s}.agent_conversations SET updated_at=now()+interval '1 hour' WHERE user_id=1"))
        elif change in ('duplicate','other_owner_key'):
            c.execute(text(f'UPDATE {s}.agent_conversations SET session_key=:key WHERE user_id=:uid'),
                      {'key':m.SESSION_KEY,'uid':2 if change=='other_owner_key' else 1})
        elif change=='admin': c.execute(text(f'UPDATE {s}.users SET is_admin=true WHERE id=1'))
        else: c.execute(text(f"UPDATE {s}.agent_messages SET content='drift' WHERE id=1"))
    with pytest.raises(m.RepairError), e.begin() as c:
        m.create_briefing_rows(c,'review@example.invalid',1,before['database_snapshot_sha256'],fixture)
    with e.begin() as c:
        assert c.execute(text(f'SELECT count(*) FROM {s}.agent_conversations')).scalar_one()==2
        assert c.execute(text(f'SELECT count(*) FROM {s}.agent_messages')).scalar_one()==2


def test_uncertain_attempt_never_replayed(tmp_path):
    m=load()
    class A:
        record=tmp_path/'intent'
        calls=0
        def inspect(self): return dict(target_sha=m.TARGET,action=m.ACTION,fixture_sha256=m.FIXTURE_SHA256,
            legacy_closure_sha256='a'*64,production_evidence_sha256='b'*64,database_snapshot_sha256='c'*64,
            health_snapshot_sha256='d'*64,demo_user_id=1,ordering_metadata_plan=m.empty_ordering_plan())
        def prepare_record(self): self.record.mkdir()
        def write(self,n,v): (self.record/n).write_text(json.dumps(v))
        def apply_once(self,e):
            self.calls+=1
            raise RuntimeError('synthetic lost commit')
    a=A(); digest=m.repair(a)['evidence_sha256']
    with pytest.raises(m.RepairError): m.repair(a,evidence_sha256=digest)
    with pytest.raises(RuntimeError): m.repair(a,authorized=True,evidence_sha256=digest)
    with pytest.raises(m.RepairError): m.repair(a,authorized=True,evidence_sha256=digest)
    assert a.calls==1 and (a.record/'intent.json').is_file()
