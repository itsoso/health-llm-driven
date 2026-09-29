"""Family reads are scoped, consented and revocable without impersonation."""

from datetime import date
import pytest
from app.models.user import User
from app.models.family import FamilyGroup, FamilyMember
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.illness import IllnessEpisode, IllnessUpdate
from app.services.auth import auth_service


def headers(user):
    return {
        "Authorization": "Bearer "
        + auth_service.create_access_token({"sub": str(user.id)})
    }


@pytest.fixture
def household(db):
    users = [
        User(
            name=n,
            username=f"family_{n}",
            email=f"{n}@example.test",
            is_active=True,
            is_approved=True,
        )
        for n in ("parent", "daughter", "sibling", "outsider")
    ]
    db.add_all(users)
    db.flush()
    parent, child, sibling, outsider = users
    group = FamilyGroup(name="Test household", owner_id=parent.id)
    db.add(group)
    db.flush()
    members = [
        FamilyMember(
            family_group_id=group.id,
            user_id=u.id,
            relationship_type="self" if u == parent else "daughter",
            nickname="Child" if u == child else u.name,
            role="owner" if u == parent else "member",
            can_view=True,
            can_edit=u == parent,
        )
        for u in users[:3]
    ]
    db.add_all(members)
    report = MedicalExam(
        user_id=child.id, exam_date=date(2026, 1, 2), notes="source notes"
    )
    report.items = [
        MedicalExamItem(item_name="Sample", value=1.2345, is_abnormal="high")
    ]
    private = MedicalExam(
        user_id=parent.id, exam_date=date(2026, 1, 2), notes="parent-only"
    )
    episode = IllnessEpisode(
        user_id=child.id,
        name="Test illness",
        start_date=date(2026, 1, 1),
        severity=None,
    )
    episode.updates = [
        IllnessUpdate(user_id=child.id, update_date=date(2026, 1, 2), notes="improving")
    ]
    db.add_all([report, private, episode])
    db.commit()
    return parent, child, sibling, outsider, members[1], report


def test_owner_reads_child_records_without_switching_identity(client, household):
    parent, child, _, _, _, report = household
    r = client.get(f"/api/v1/family/members/{child.id}/health", headers=headers(parent))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers["Cache-Control"]
    body = r.json()
    assert body["member"]["relationship_type"] == "daughter"
    assert [x["id"] for x in body["reports"]] == [report.id]
    assert body["reports"][0]["items"][0]["value"] == 1.2345
    assert body["reports"][0]["items"][0]["display_value"] == "1.23"
    assert body["episodes"][0]["severity"] is None
    assert body["episodes"][0]["updates"][0]["notes"] == "improving"
    assert "parent-only" not in r.text
    assert (
        client.get("/api/v1/auth/me", headers=headers(parent)).json()["id"] == parent.id
    )


@pytest.mark.parametrize("actor_index", [2, 3])
def test_non_owner_cannot_read_another_member(client, household, actor_index):
    r = client.get(
        f"/api/v1/family/members/{household[1].id}/health",
        headers=headers(household[actor_index]),
    )
    assert r.status_code == 403


@pytest.mark.parametrize("revocation", ["view", "membership", "inactive"])
def test_read_authorization_rechecked_each_request(client, db, household, revocation):
    parent, child, _, _, membership, _ = household
    url = f"/api/v1/family/members/{child.id}/health"
    assert client.get(url, headers=headers(parent)).status_code == 200
    if revocation == "view":
        membership.can_view = False
    elif revocation == "membership":
        db.delete(membership)
    else:
        child.is_active = False
    db.commit()
    assert client.get(url, headers=headers(parent)).status_code == 403


def test_cannot_attach_arbitrary_registered_user(client, household):
    parent, _, _, outsider, _, _ = household
    r = client.post(
        "/api/v1/family/members",
        headers=headers(parent),
        json={
            "name": "Not evidence of consent",
            "relationship_type": "daughter",
            "existing_user_id": outsider.id,
        },
    )
    assert r.status_code == 403


def test_read_sharing_does_not_allow_edit_proxy(client, household):
    parent, child, *_ = household
    r = client.post(
        "/api/v1/family/switch", headers=headers(parent), json={"user_id": child.id}
    )
    assert r.status_code == 403


def test_relation_update_does_not_expand_permissions(client, db, household):
    parent, child, _, outsider, membership, _ = household
    url = f"/api/v1/family/members/{membership.id}/relationship"
    payload = {"relationship_type": "daughter", "nickname": "Little one"}
    assert client.patch(url, headers=headers(outsider), json=payload).status_code == 403
    assert client.patch(url, headers=headers(parent), json=payload).status_code == 200
    db.refresh(membership)
    assert membership.nickname == "Little one"
    assert membership.can_edit is False
    assert (
        client.patch(
            url, headers=headers(parent), json={"relationship_type": "owner"}
        ).status_code
        == 422
    )


def test_invitation_retains_account_and_member_can_leave(client, db, household):
    parent, _, _, outsider, _, _ = household
    invite = client.post("/api/v1/family/invitation/create", headers=headers(parent))
    assert invite.status_code == 200
    accepted = client.post(
        "/api/v1/family/invitation/accept",
        headers=headers(outsider),
        json={
            "code": invite.json()["code"],
            "relationship_type": "daughter",
            "nickname": "Little one",
        },
    )
    assert accepted.status_code == 200
    mid = accepted.json()["member_id"]
    assert db.get(FamilyMember, mid).user_id == outsider.id
    assert db.get(FamilyMember, mid).can_edit is False
    url = f"/api/v1/family/members/{outsider.id}/health"
    assert client.get(url, headers=headers(parent)).status_code == 200
    assert (
        client.delete(
            f"/api/v1/family/members/{mid}", headers=headers(outsider)
        ).status_code
        == 200
    )
    assert client.get(url, headers=headers(parent)).status_code == 403


def test_dashboard_does_not_disclose_sibling_health(client, household):
    parent, child, sibling, *_ = household
    body = client.get("/api/v1/family/dashboard", headers=headers(sibling)).json()
    assert {m["user_id"] for m in body["members"]} == {sibling.id}
    body = client.get("/api/v1/family/dashboard", headers=headers(parent)).json()
    assert body["is_owner"] is True
    assert (
        next(m for m in body["members"] if m["user_id"] == child.id)["can_view"] is True
    )


def test_member_cannot_forge_owner_edit_grant(client, db, household):
    parent, child, sibling, _, membership, _ = household
    membership.can_edit = True
    db.commit()
    token = auth_service.create_access_token(
        {"sub": str(child.id), "acting_as": child.id, "original_user": sibling.id}
    )
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 403
    )


def test_proxy_cannot_expand_family_authorization(client, db, household):
    parent, child, _, _, membership, _ = household
    child.is_managed = True
    child.managed_by = parent.id
    membership.can_edit = True
    db.commit()
    switched = client.post(
        "/api/v1/family/switch", headers=headers(parent), json={"user_id": child.id}
    )
    assert switched.status_code == 200
    proxy = {"Authorization": "Bearer " + switched.json()["access_token"]}
    assert (
        client.post(
            "/api/v1/family/groups", headers=proxy, json={"name": "Escalation"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/family/members/{parent.id}/health", headers=proxy
        ).status_code
        == 403
    )
    assert client.post("/api/v1/family/switch-back", headers=proxy).status_code == 200


def test_view_revocation_removes_dashboard_and_digest_access(client, db, household):
    parent, child, _, _, membership, _ = household
    membership.can_view = False
    db.commit()
    members = client.get("/api/v1/family/dashboard", headers=headers(parent)).json()[
        "members"
    ]
    assert child.id not in {m["user_id"] for m in members}

    from app.services.family_daily_check import run_family_daily_check
    from app.services.family_weekly_digest import generate_weekly_digest

    daily = run_family_daily_check(db, parent.id)["member_reports"]
    weekly = generate_weekly_digest(db, parent.id)["members"]
    assert child.id not in {m["user_id"] for m in daily}
    assert child.id not in {m["user_id"] for m in weekly}


def test_input_limits_and_bad_relation_rejected(client, household):
    parent, child, *_ = household
    assert (
        client.get(
            f"/api/v1/family/members/{child.id}/health?limit=1000",
            headers=headers(parent),
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/family/members",
            headers=headers(parent),
            json={
                "name": "Untrusted",
                "relationship_type": "owner",
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("legacy_kind", ["registered_edit", "wrong_manager"])
def test_legacy_links_do_not_grant_records_or_proxy(client, db, household, legacy_kind):
    parent, child, _, outsider, membership, _ = household
    membership.can_edit = True
    if legacy_kind == "wrong_manager":
        child.is_managed = True
        child.managed_by = outsider.id
    db.commit()
    assert (
        client.get(
            f"/api/v1/family/members/{child.id}/health", headers=headers(parent)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/family/switch", headers=headers(parent), json={"user_id": child.id}
        ).status_code
        == 403
    )


def test_legacy_registered_link_requires_authenticated_reacceptance(
    client, db, household
):
    parent, child, _, _, membership, _ = household
    membership.can_edit = True
    db.commit()
    code = client.post(
        "/api/v1/family/invitation/create", headers=headers(parent)
    ).json()["code"]
    assert (
        client.post(
            "/api/v1/family/invitation/accept",
            headers=headers(child),
            json={
                "code": code,
                "relationship_type": "daughter",
                "nickname": "Child",
            },
        ).status_code
        == 200
    )
    db.refresh(membership)
    assert membership.can_edit is False
    assert (
        client.get(
            f"/api/v1/family/members/{child.id}/health", headers=headers(parent)
        ).status_code
        == 200
    )


def test_all_memberships_can_be_found_and_revoked_even_for_owner(client, db, household):
    parent, _, _, outsider, _, _ = household
    assert (
        client.post(
            "/api/v1/family/groups",
            headers=headers(outsider),
            json={"name": "Other household"},
        ).status_code
        == 200
    )
    code = client.post(
        "/api/v1/family/invitation/create", headers=headers(outsider)
    ).json()["code"]
    result = client.post(
        "/api/v1/family/invitation/accept",
        headers=headers(parent),
        json={"code": code, "relationship_type": "other"},
    )
    assert result.status_code == 200
    mid = result.json()["member_id"]
    body = client.get("/api/v1/family/dashboard", headers=headers(parent)).json()
    assert body["is_owner"] is True
    assert any(m["member_id"] == mid and not m["is_owner"] for m in body["memberships"])
    assert (
        client.delete(
            f"/api/v1/family/members/{mid}", headers=headers(parent)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/family/members/{parent.id}/health", headers=headers(outsider)
        ).status_code
        == 403
    )


def test_mismatched_illness_update_is_not_disclosed(client, db, household):
    parent, child, _, outsider, _, _ = household
    episode = db.query(IllnessEpisode).filter_by(user_id=child.id).one()
    db.add(
        IllnessUpdate(
            episode_id=episode.id,
            user_id=outsider.id,
            update_date=date(2026, 1, 3),
            notes="private outsider update",
        )
    )
    db.commit()
    r = client.get(f"/api/v1/family/members/{child.id}/health", headers=headers(parent))
    assert r.status_code == 200
    assert "private outsider update" not in r.text


def test_api_key_cannot_expand_to_family_records(client, db, household):
    import hashlib
    from app.models.user_api_key import UserApiKey

    parent, child, *_ = household
    key = "synthetic-family-read-key"
    db.add(
        UserApiKey(
            user_id=parent.id,
            name="Family restriction test",
            api_key=hashlib.sha256(key.encode()).hexdigest(),
            scopes="read,write",
        )
    )
    db.commit()
    r = client.get(
        f"/api/v1/family/members/{child.id}/health", headers={"X-API-Key": key}
    )
    assert r.status_code == 403


@pytest.mark.parametrize("grant", ["can_view", "can_edit"])
def test_existing_managed_proxy_rejects_revoked_grant(client, db, household, grant):
    parent, child, _, _, member, _ = household
    child.is_managed = True
    child.managed_by = parent.id
    member.can_edit = True
    db.commit()
    r = client.post(
        "/api/v1/family/switch", headers=headers(parent), json={"user_id": child.id}
    )
    assert r.status_code == 200
    proxy = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=proxy).status_code == 200
    setattr(member, grant, False)
    db.commit()
    assert client.get("/api/v1/auth/me", headers=proxy).status_code == 403


@pytest.mark.parametrize("field", ["is_managed", "can_edit"])
def test_null_flags_are_not_registered_invitation_provenance(
    client, db, household, field
):
    parent, child, _, _, member, _ = household
    setattr(child if field == "is_managed" else member, field, None)
    db.commit()
    assert (
        client.get(
            f"/api/v1/family/members/{child.id}/health", headers=headers(parent)
        ).status_code
        == 403
    )
