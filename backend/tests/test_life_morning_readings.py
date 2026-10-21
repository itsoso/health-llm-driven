"""Owner-bound private report relay; no health or workspace writes."""
import httpx
import pytest
from fastapi import HTTPException
from app.services import life_morning_readings as service

RID = 'b3cbd442-0a47-454e-8fa7-c04050828c1a'

def entry():
    return dict(report_id=RID, source='morning_reading', title='晨读', generated_at='2026-10-18T16:00:00Z')

def install(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(service, '_client', lambda: original(transport=httpx.MockTransport(handler)))

def test_list_is_owner_bound_filtered_and_paginates_without_false_completeness(monkeypatch):
    def handler(request):
        assert request.url.host == 'base.executor.life'
        assert request.headers['Authorization'] == 'Bearer owner-token'
        if request.url.path.endswith('/identity'):
            return httpx.Response(200, json={'user_id': 7})
        assert request.url.params['offset'] == '30'
        rows = [dict(entry(), source='other') for _ in range(29)] + [entry()]
        return httpx.Response(200, json={'items': rows})
    install(monkeypatch, handler)
    result = service.list_readings(7, 'owner-token', 30)
    assert len(result.items) == 1 and result.items[0].reading_date.isoformat() == '2026-10-19'
    assert result.next_offset == 60

def test_identity_mismatch_stops_before_reading_content(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={'user_id': 8})
    install(monkeypatch, handler)
    with pytest.raises(HTTPException) as caught:
        service.list_readings(7, 'secret', 0)
    assert caught.value.status_code == 502 and len(calls) == 1
    assert 'secret' not in str(caught.value)

@pytest.mark.parametrize('updates', [{'user_id': 8}, {'source': 'portfolio'}, {'report_id': 'wrong'}])
def test_detail_rejects_wrong_owner_source_or_identity(monkeypatch, updates):
    def handler(request):
        if request.url.path.endswith('/identity'):
            return httpx.Response(200, json={'user_id': 7})
        report = dict(entry(), user_id=7, content_text='Private body', content_html='<script>bad()</script>')
        report.update(updates)
        return httpx.Response(200, json={'report': report})
    install(monkeypatch, handler)
    with pytest.raises(HTTPException):
        service.get_reading(7, 'secret', RID)

def test_detail_returns_only_text_not_html_or_credentials(monkeypatch):
    def handler(request):
        if request.url.path.endswith('/identity'):
            return httpx.Response(200, json={'user_id': 7})
        return httpx.Response(200, json={'report': dict(entry(), user_id=7, content_text='Private body', content_html='<script>bad()</script>')})
    install(monkeypatch, handler)
    result = service.get_reading(7, 'secret', RID).model_dump(mode='json')
    assert result['content_text'] == 'Private body'
    assert 'content_html' not in result and 'secret' not in str(result)

@pytest.mark.parametrize('status', [302, 401, 403, 500])
def test_upstream_errors_are_not_empty_success(monkeypatch, status):
    install(monkeypatch, lambda request: httpx.Response(status, headers={'Location': 'https://evil.example'}, json={}))
    with pytest.raises(HTTPException):
        service.list_readings(7, 'secret', 0)

def test_large_response_is_rejected(monkeypatch):
    install(monkeypatch, lambda request: httpx.Response(200, content=b'x' * (service.MAX_BYTES + 1)))
    with pytest.raises(HTTPException):
        service.list_readings(7, 'secret', 0)


@pytest.fixture
def private_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.life_navigation import router
    from app.database import get_db
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


def test_route_relays_exact_owner_token_and_sets_private_headers(private_client, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    captured = []
    def listing(owner, token, offset):
        captured.append((owner, token, offset))
        return {'items': [], 'next_offset': None}
    monkeypatch.setattr(service, 'list_readings', listing)
    path = '/api/v1/life-navigation/morning-readings'
    response = private_client.get(path, headers={**headers, 'X-Reva-AI-Subject': str(user.id)})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert captured == [(user.id, headers['Authorization'][7:], 0)]
    assert private_client.get(path, headers={**headers, 'X-Reva-AI-Subject': str(user.id + 1)}).status_code == 409
    assert len(captured) == 1
    invalid = private_client.get(path + '?offset=-1', headers=headers)
    assert invalid.status_code == 422 and invalid.headers['cache-control'] == 'private, no-store'
    assert private_client.get(path).status_code == 401
    private_client.cookies.set('health_session', headers['Authorization'][7:])
    assert private_client.get(path, headers={'X-Reva-AI-Subject': str(user.id)}).status_code == 200
    assert captured[-1] == (user.id, headers['Authorization'][7:], 0)
    assert private_client.get(path, headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert len(captured) == 2


def test_route_rejects_api_keys_and_managed_accounts(private_client, db, auth_user_and_headers, monkeypatch):
    from app.models.user_api_key import UserApiKey
    from hashlib import sha256
    user, headers = auth_user_and_headers
    def forbidden(*args):
        pytest.fail('Unauthorized request reached the relay')
    monkeypatch.setattr(service, 'list_readings', forbidden)
    raw = 'synthetic-readings-key'
    db.add(UserApiKey(user_id=user.id, name='test', scopes='read,write', api_key=sha256(raw.encode()).hexdigest()))
    db.commit()
    path = '/api/v1/life-navigation/morning-readings'
    assert private_client.get(path, headers={'X-API-Key': raw}).status_code == 403
    user.is_managed = True
    db.commit()
    assert private_client.get(path, headers=headers).status_code == 403
