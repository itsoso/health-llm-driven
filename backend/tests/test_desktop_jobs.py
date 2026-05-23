from datetime import datetime, timezone


def test_create_and_list_desktop_gene_reanalysis_job(client, auth_user_and_headers):
    user, headers = auth_user_and_headers

    created = client.post(
        "/api/v1/desktop/import-jobs",
        headers=headers,
        json={
            "job_type": "gene_reanalysis",
            "source_kind": "genome_txt",
            "source_name": "wegene.txt",
            "source_hash": "sha256:abc",
            "request_payload": {"profile_id": 123},
        },
    )

    assert created.status_code == 200
    body = created.json()
    assert body["user_id"] == user.id
    assert body["job_type"] == "gene_reanalysis"
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["source_hash"] == "sha256:abc"

    listed = client.get("/api/v1/desktop/jobs", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]


def test_desktop_jobs_are_scoped_to_current_user(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    from app.models.desktop_job import DesktopJob
    from app.models.user import User

    other = User(
        username="desktop_job_other",
        email="desktop_job_other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    other_job = DesktopJob(
        user_id=other.id,
        job_type="system_kb_rebuild",
        status="queued",
        source_kind="system",
        source_name="kb",
    )
    db.add(other_job)
    db.commit()
    db.refresh(other_job)

    detail = client.get(f"/api/v1/desktop/jobs/{other_job.id}", headers=headers)
    listed = client.get("/api/v1/desktop/jobs", headers=headers)

    assert detail.status_code == 404
    assert listed.status_code == 200
    assert listed.json() == []


def test_retry_failed_desktop_job_creates_retry_job(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.desktop_job import DesktopJob

    failed = DesktopJob(
        user_id=user.id,
        job_type="dedao_compile",
        status="failed",
        progress=25,
        source_kind="dedao_folder",
        source_name="down-dedao",
        source_hash="sha256:def",
        request_payload={"path": "~/work/personal/down-dedao"},
        error_message="parser failed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(failed)
    db.commit()
    db.refresh(failed)

    resp = client.post(f"/api/v1/desktop/jobs/{failed.id}/retry", headers=headers)

    assert resp.status_code == 200
    retry = resp.json()
    assert retry["status"] == "queued"
    assert retry["progress"] == 0
    assert retry["retry_of_job_id"] == failed.id
    assert retry["job_type"] == "dedao_compile"
    assert retry["request_payload"] == {"path": "~/work/personal/down-dedao"}


def test_retry_rejects_non_failed_desktop_job(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.desktop_job import DesktopJob

    queued = DesktopJob(user_id=user.id, job_type="eval_run", status="queued")
    db.add(queued)
    db.commit()
    db.refresh(queued)

    resp = client.post(f"/api/v1/desktop/jobs/{queued.id}/retry", headers=headers)

    assert resp.status_code == 409


def test_create_desktop_job_rejects_unknown_job_type(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/desktop/import-jobs",
        headers=headers,
        json={"job_type": "unknown"},
    )

    assert resp.status_code == 422
