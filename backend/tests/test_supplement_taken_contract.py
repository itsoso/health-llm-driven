"""补剂依从写入契约:「是否已服」必须显式,缺省不得静默落 taken=false。

2026-09 生产事故:外部客户端按 OpenAPI 必填字段 POST /supplements/records
(supplement_id / user_id / record_date + notes),备注写明已服却没带 taken →
schema 默认 False → 实际服用被记成未服,Twin 在服集 / 依从统计 / DSI 推理全部漏计。
遗留列 taken_count 不在 ORM 映射内(DB 默认 1),不代表服用,静默丢弃会掩盖契约误用。
"""
from datetime import date, time, timedelta

import pytest

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.twin import _collectors
from tests.conftest import create_authenticated_user

RECORDS = "/api/v1/supplements/records"


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _definition(db, user_id, name="镁"):
    supp = SupplementDefinition(user_id=user_id, name=name, is_active=True)
    db.add(supp)
    db.commit()
    db.refresh(supp)
    return supp


def _rows(db, supplement_id):
    return db.query(SupplementRecord).filter(SupplementRecord.supplement_id == supplement_id).all()


def _error_fields(resp):
    return {(err["type"], err["loc"][-1]) for err in resp.json()["detail"]}


def test_record_without_taken_is_rejected_and_writes_nothing(client, db):
    """事故原样载荷:备注描述已服但缺 taken → 422 点名 taken,不落任何行。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)

    resp = client.post(
        RECORDS,
        json={
            "supplement_id": supp.id,
            "user_id": user.id,
            "record_date": (date.today() - timedelta(days=1)).isoformat(),
            "notes": "补记录·昨天早餐后服用",
        },
        headers=_headers(token),
    )

    assert resp.status_code == 422
    assert ("missing", "taken") in _error_fields(resp)
    assert _rows(db, supp.id) == []


def test_record_rejects_legacy_taken_count_field(client, db):
    """taken_count 是未映射的遗留列名,不能被静默吞掉当作「已记录」。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)

    resp = client.post(
        RECORDS,
        json={
            "supplement_id": supp.id,
            "user_id": user.id,
            "record_date": date.today().isoformat(),
            "taken": True,
            "taken_count": 1,
        },
        headers=_headers(token),
    )

    assert resp.status_code == 422
    assert ("extra_forbidden", "taken_count") in _error_fields(resp)
    assert _rows(db, supp.id) == []


def test_backdated_intake_with_explicit_taken_is_counted_by_twin(client, db):
    """显式 taken=true 的补记(不带被服务端忽略的 user_id)落库为已服,Twin 在服集可见。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id, name="辅酶Q10")
    yesterday = date.today() - timedelta(days=1)

    resp = client.post(
        RECORDS,
        json={
            "supplement_id": supp.id,
            "record_date": yesterday.isoformat(),
            "taken": True,
            "notes": "补记录·昨天早餐后服用",
        },
        headers=_headers(token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["taken"] is True
    assert resp.json()["user_id"] == user.id
    [row] = _rows(db, supp.id)
    assert (row.record_date, row.taken) == (yesterday, True)
    assert "辅酶Q10" in _collectors.fetch_supplement_today(db, user.id)["taking_recent_names"]


def test_record_rejects_non_boolean_taken(client, db):
    """"yes"/1 不能被宽松转换成「已服」写进依从事实。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)

    resp = client.post(
        RECORDS,
        json={"supplement_id": supp.id, "record_date": date.today().isoformat(), "taken": "yes"},
        headers=_headers(token),
    )

    assert resp.status_code == 422
    assert _rows(db, supp.id) == []


def test_record_upsert_keeps_fields_the_caller_did_not_send(client, db):
    """同日 upsert 只改调用方显式给出的字段:不抹掉 NFC 已写的服用时刻/备注,并落本次剂量。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)
    today = date.today()
    db.add(SupplementRecord(
        user_id=user.id, supplement_id=supp.id, record_date=today,
        taken=True, taken_time=time(8, 0), notes="早餐后",
    ))
    db.commit()

    resp = client.post(
        RECORDS,
        json={
            "supplement_id": supp.id,
            "user_id": user.id,
            "record_date": today.isoformat(),
            "taken": True,
            "actual_dosage": "2粒",
        },
        headers=_headers(token),
    )

    assert resp.status_code == 200, resp.text
    [row] = _rows(db, supp.id)
    db.refresh(row)
    assert row.taken is True
    assert row.taken_time == time(8, 0)
    assert row.notes == "早餐后"
    assert row.actual_dosage == "2粒"


def test_record_upsert_explicit_untake_still_applies(client, db):
    """显式 taken=false 仍是合法撤销(界面取消勾选语义不变)。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)
    today = date.today()
    db.add(SupplementRecord(user_id=user.id, supplement_id=supp.id, record_date=today, taken=True))
    db.commit()

    resp = client.post(
        RECORDS,
        json={
            "supplement_id": supp.id,
            "user_id": user.id,
            "record_date": today.isoformat(),
            "taken": False,
        },
        headers=_headers(token),
    )

    assert resp.status_code == 200, resp.text
    [row] = _rows(db, supp.id)
    db.refresh(row)
    assert row.taken is False


def test_batch_checkin_without_taken_is_rejected_before_any_write(client, db):
    """批量打卡任一项缺 taken → 422,整批不写(前一项已存在行也不能被半途改掉)。"""
    user, token = create_authenticated_user(db)
    first = _definition(db, user.id, name="维生素C")
    second = _definition(db, user.id, name="锌")
    today = date.today()
    db.add(SupplementRecord(user_id=user.id, supplement_id=first.id, record_date=today, taken=False))
    db.commit()

    resp = client.post(
        f"{RECORDS}/batch",
        json={
            "record_date": today.isoformat(),
            "checkins": [
                {"supplement_id": first.id, "taken": True},
                {"supplement_id": second.id},
            ],
        },
        headers=_headers(token),
    )

    assert resp.status_code == 422
    assert ("missing", "taken") in _error_fields(resp)
    [existing] = _rows(db, first.id)
    db.refresh(existing)
    assert existing.taken is False
    assert _rows(db, second.id) == []


@pytest.mark.parametrize("item_extra, error", [
    ({"taken": "false"}, ("bool_type", "taken")),
    ({"taken": True, "taken_count": 1}, ("extra_forbidden", "taken_count")),
    ({"taken": True, "notes": "早餐后"}, ("extra_forbidden", "notes")),
])
def test_batch_checkin_item_contract_is_strict(client, db, item_extra, error):
    """批量项只收 supplement_id + 布尔 taken:字符串布尔 / 遗留 taken_count / 会被丢弃的字段一律 422。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)

    resp = client.post(
        f"{RECORDS}/batch",
        json={
            "record_date": date.today().isoformat(),
            "checkins": [{"supplement_id": supp.id, **item_extra}],
        },
        headers=_headers(token),
    )

    assert resp.status_code == 422
    assert error in _error_fields(resp)
    assert _rows(db, supp.id) == []


def test_batch_checkin_rejects_duplicate_supplement_ids(client, db):
    """同批同一补剂出现两次 → 400 且不写(不能靠唯一约束 500 兜底)。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)

    resp = client.post(
        f"{RECORDS}/batch",
        json={
            "record_date": date.today().isoformat(),
            "checkins": [
                {"supplement_id": supp.id, "taken": True},
                {"supplement_id": supp.id, "taken": False},
            ],
        },
        headers=_headers(token),
    )

    assert resp.status_code == 400
    assert _rows(db, supp.id) == []


def test_quick_record_refuses_to_flip_existing_untaken_row(client, db):
    """当天已取消勾选(taken=false)的行不被自由文本改写:409 点名补剂,不写、不假报「已打卡」。"""
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id, name="维生素D")
    db.add(SupplementRecord(user_id=user.id, supplement_id=supp.id, record_date=date.today(), taken=False))
    db.commit()

    resp = client.post("/api/v1/quick-record", json={"text": "吃了维生素D"}, headers=_headers(token))

    assert resp.status_code == 409
    assert "维生素D" in resp.json()["detail"]
    [row] = _rows(db, supp.id)
    db.refresh(row)
    assert row.taken is False


def test_quick_record_existing_taken_row_is_idempotent(client, db):
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id, name="维生素D")
    db.add(SupplementRecord(user_id=user.id, supplement_id=supp.id, record_date=date.today(), taken=True))
    db.commit()

    resp = client.post("/api/v1/quick-record", json={"text": "吃了维生素D"}, headers=_headers(token))

    assert resp.status_code == 200, resp.text
    [row] = _rows(db, supp.id)
    db.refresh(row)
    assert row.taken is True


@pytest.mark.parametrize("text", [
    "没吃维生素D", "还没吃维生素D", "维生素D还没吃", "忘了吃维生素D", "今天不吃维生素D", "今天不 吃维生素D",
    "别忘了吃维生素D", "准备吃维生素D", "吃了维生素D吗", "昨天吃了维生素D", "拒绝吃维生素D",
    "未曾服用维生素D", "医生让我吃维生素D", "要吃维生素D",
])
def test_quick_record_non_affirmative_supplement_text_writes_nothing(client, db, text):
    """否定/漏服/别日/计划/提问不是今天的服用事实:400,不落记录,也不建出怪名定义。"""
    user, token = create_authenticated_user(db)
    _definition(db, user.id, name="维生素D")

    resp = client.post("/api/v1/quick-record", json={"text": text}, headers=_headers(token))

    assert resp.status_code == 400
    assert db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).count() == 0
    assert db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user.id).count() == 1


@pytest.mark.parametrize("text", ["吃了维生素D", "吃了 维生素D", "补剂鱼油", "吃了维生素K2（别名MK-7）"])
def test_quick_record_affirmative_supplement_text_still_parses(text):
    from app.api.quick_record import _parse_quick_record

    record_type, _data = _parse_quick_record(text)

    assert record_type == "supplement"


def test_batch_actual_dosage_round_trip_and_boolean_only_update_preserves_it(client, db):
    user, token = create_authenticated_user(db)
    first = _definition(db, user.id, 'NAC')
    second = _definition(db, user.id, 'Omega-3')
    day = date.today().isoformat()
    payload = {'record_date': day, 'checkins': [
        {'supplement_id': first.id, 'taken': True, 'actual_dosage': '2粒'},
        {'supplement_id': second.id, 'taken': True, 'actual_dosage': '1粒'},
    ]}
    response = client.post(f'{RECORDS}/batch', json=payload, headers=_headers(token))
    assert response.status_code == 200, response.text
    assert [row['actual_dosage'] for row in response.json()['results']] == ['2粒', '1粒']
    assert all(row['taken'] is True and row['record_id'] for row in response.json()['results'])
    repeat = client.post(f'{RECORDS}/batch', json=payload, headers=_headers(token))
    assert repeat.status_code == 200
    assert len(_rows(db, first.id)) == 1
    payload['checkins'] = [{'supplement_id': first.id, 'taken': True}]
    response = client.post(f'{RECORDS}/batch', json=payload, headers=_headers(token))
    assert response.json()['results'][0]['actual_dosage'] == '2粒'
    read = client.get(f'/api/v1/supplements/me/date/{day}', headers=_headers(token))
    assert read.status_code == 200
    records = {item['supplement']['id']: item['record'] for item in read.json()}
    assert records[first.id]['actual_dosage'] == '2粒'
    assert records[second.id]['actual_dosage'] == '1粒'
    db.refresh(first)
    assert first.dosage is None


def test_batch_dosage_foreign_target_rejects_whole_batch(client, db):
    user, token = create_authenticated_user(db)
    other, _ = create_authenticated_user(db)
    own = _definition(db, user.id)
    foreign = _definition(db, other.id)
    response = client.post(f'{RECORDS}/batch', headers=_headers(token), json={
        'record_date': date.today().isoformat(), 'checkins': [
            {'supplement_id': own.id, 'taken': True, 'actual_dosage': '2粒'},
            {'supplement_id': foreign.id, 'taken': True, 'actual_dosage': '1粒'},
        ],
    })
    assert response.status_code == 404
    assert _rows(db, own.id) == []
    assert _rows(db, foreign.id) == []


def test_batch_boolean_only_receipt_does_not_invent_definition_dosage(client, db):
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)
    supp.dosage = '每日2粒'
    db.commit()
    response = client.post(f'{RECORDS}/batch', headers=_headers(token), json={
        'record_date': date.today().isoformat(),
        'checkins': [{'supplement_id': supp.id, 'taken': True}],
    })
    assert response.status_code == 200
    assert response.json()['results'][0]['actual_dosage'] is None
    assert _rows(db, supp.id)[0].actual_dosage is None


@pytest.mark.parametrize('dosage', [' ', 'x' * 41, 2, True])
def test_batch_rejects_invalid_actual_dosage_before_any_write(client, db, dosage):
    user, token = create_authenticated_user(db)
    first = _definition(db, user.id, 'NAC')
    second = _definition(db, user.id, 'Omega-3')
    response = client.post(f'{RECORDS}/batch', headers=_headers(token), json={
        'record_date': date.today().isoformat(), 'checkins': [
            {'supplement_id': first.id, 'taken': True, 'actual_dosage': '2粒'},
            {'supplement_id': second.id, 'taken': True, 'actual_dosage': dosage},
        ],
    })
    assert response.status_code == 422
    assert _rows(db, first.id) == []
    assert _rows(db, second.id) == []


def test_batch_untake_preserves_dosage_until_explicitly_cleared(client, db):
    user, token = create_authenticated_user(db)
    supp = _definition(db, user.id)
    db.add(SupplementRecord(user_id=user.id, supplement_id=supp.id,
                           record_date=date.today(), taken=True, actual_dosage='2粒'))
    db.commit()
    payload = {'record_date': date.today().isoformat(),
               'checkins': [{'supplement_id': supp.id, 'taken': False}]}
    response = client.post(f'{RECORDS}/batch', headers=_headers(token), json=payload)
    assert response.status_code == 200
    result = response.json()['results'][0]
    assert result['taken'] is False
    assert result['actual_dosage'] == '2粒'
    payload['checkins'][0]['actual_dosage'] = None
    response = client.post(f'{RECORDS}/batch', headers=_headers(token), json=payload)
    assert response.status_code == 200
    assert response.json()['results'][0]['actual_dosage'] is None
    db.expire_all()
    assert _rows(db, supp.id)[0].actual_dosage is None
