"""Security contract for legacy personal-health routes.

Compatibility URLs may remain available, but they must never be anonymous and
must not let an ordinary user select another tenant with a client-supplied ID.
"""

from datetime import date

import pytest

from app.models.disease import DiseaseRecord
from app.models.user import User


ANONYMOUS_GET_PATHS = [
    "/api/v1/diseases/user/1",
    "/api/v1/diseases/1",
    "/api/v1/data-collection/garmin/sync-status/1",
    "/api/v1/diet-recommendation/1",
    "/api/v1/garmin-analysis/user/1/sleep",
    "/api/v1/garmin-analysis/user/1/heart-rate",
    "/api/v1/garmin-analysis/user/1/body-battery",
    "/api/v1/garmin-analysis/user/1/activity",
    "/api/v1/garmin-analysis/user/1/comprehensive",
    "/api/v1/daily-recommendation/user/1/recommendations",
    "/api/v1/daily-recommendation/user/1/today",
    "/api/v1/daily-recommendation/user/1/today-simple",
    "/api/v1/daily-recommendation/user/1/analysis/2026-07-21",
    "/api/v1/daily-recommendation/user/1/quick-summary",
    "/api/v1/daily-recommendation/user/1/sleep-insights",
    "/api/v1/daily-recommendation/user/1/activity-insights",
    "/api/v1/daily-recommendation/user/1/heart-insights",
    "/api/v1/daily-recommendation/user/1/recovery-status",
    "/api/v1/ai-insights/insights/daily",
    "/api/v1/supplements/products",
]


ANONYMOUS_POST_REQUESTS = [
    (
        "/api/v1/diseases/",
        {},
        {
            "user_id": 1,
            "disease_name": "test",
            "diagnosis_date": "2026-07-21",
        },
    ),
    (
        "/api/v1/daily-health/diet",
        {},
        {
            "user_id": 1,
            "record_date": "2026-07-21",
            "meal_type": "lunch",
            "food_name": "test",
        },
    ),
    (
        "/api/v1/daily-health/water",
        {},
        {"user_id": 1, "record_date": "2026-07-21", "amount": 200},
    ),
    (
        "/api/v1/daily-health/supplement",
        {},
        {
            "user_id": 1,
            "record_date": "2026-07-21",
            "supplement_name": "test",
        },
    ),
    (
        "/api/v1/daily-health/outdoor",
        {},
        {"user_id": 1, "record_date": "2026-07-21"},
    ),
    (
        "/api/v1/data-collection/garmin/sync",
        {"user_id": 1, "target_date": "2026-07-21"},
        None,
    ),
    (
        "/api/v1/data-collection/garmin/sync-range",
        {
            "user_id": 1,
            "start_date": "2026-07-20",
            "end_date": "2026-07-21",
        },
        None,
    ),
]


@pytest.mark.parametrize("path", ANONYMOUS_GET_PATHS)
def test_legacy_personal_health_get_requires_authentication(client, path):
    response = client.get(path)
    assert response.status_code == 401, (path, response.status_code, response.text)


@pytest.mark.parametrize("path,params,payload", ANONYMOUS_POST_REQUESTS)
def test_legacy_personal_health_write_requires_authentication(
    client, path, params, payload
):
    response = client.post(path, params=params, json=payload)
    assert response.status_code == 401, (path, response.status_code, response.text)


def _create_other_user(db) -> User:
    user = User(
        username="legacy-route-other-user",
        email="legacy-route-other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.parametrize(
    "path_template",
    [
        "/api/v1/diseases/user/{user_id}",
        "/api/v1/data-collection/garmin/sync-status/{user_id}",
        "/api/v1/diet-recommendation/{user_id}",
        "/api/v1/garmin-analysis/user/{user_id}/heart-rate",
        "/api/v1/daily-recommendation/user/{user_id}/quick-summary",
    ],
)
def test_legacy_user_selector_rejects_cross_user_access(
    client, db, auth_user_and_headers, path_template
):
    _, headers = auth_user_and_headers
    other = _create_other_user(db)

    response = client.get(path_template.format(user_id=other.id), headers=headers)

    assert response.status_code == 403, (response.status_code, response.text)


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/v1/diseases/",
            {
                "disease_name": "forged",
                "diagnosis_date": "2026-07-21",
            },
        ),
        (
            "/api/v1/daily-health/diet",
            {
                "record_date": "2026-07-21",
                "meal_type": "lunch",
                "food_name": "forged",
            },
        ),
        (
            "/api/v1/daily-health/water",
            {"record_date": "2026-07-21", "amount": 200},
        ),
        (
            "/api/v1/daily-health/supplement",
            {"record_date": "2026-07-21", "supplement_name": "forged"},
        ),
        (
            "/api/v1/daily-health/outdoor",
            {"record_date": "2026-07-21"},
        ),
    ],
)
def test_legacy_body_user_id_cannot_write_another_tenant(
    client, db, auth_user_and_headers, path, payload
):
    _, headers = auth_user_and_headers
    other = _create_other_user(db)
    payload["user_id"] = other.id

    response = client.post(path, headers=headers, json=payload)

    assert response.status_code == 403, (response.status_code, response.text)


def test_disease_detail_is_hidden_from_another_user(
    client, db, auth_user_and_headers
):
    _, headers = auth_user_and_headers
    other = _create_other_user(db)
    disease = DiseaseRecord(
        user_id=other.id,
        disease_name="private",
        diagnosis_date=date(2026, 7, 21),
    )
    db.add(disease)
    db.commit()
    db.refresh(disease)

    response = client.get(f"/api/v1/diseases/{disease.id}", headers=headers)

    assert response.status_code == 404
