"""Wave 1 · garmin_sync 作为 agent 触发动作(异步 job)的执行模型 + 诚实契约。

覆盖 founder 2026-07-14 "帮我同步"永久转圈根治:
- garmin_sync 不再内联阻塞(record_map 里的同步 POST 已删),改专属分支
  _trigger_garmin_sync:本地 precondition fail-loud → Celery enqueue → 乐观 ack。
- 三护栏:未绑定/禁用/失效/MFA → 明确指引且**不 enqueue**;满足 → enqueue 并 ack。
- 诚实:garmin_sync 不进写回执诚实闸(_write_tool_attempted False),否则真成功/
  MFA 失败都被误判"未取得可验证写入回执"。
"""
import pytest

import app.tasks.garmin_sync as garmin_task
from app.models.user import GarminCredential
from app.services.agent_executor import AgentExecutor, _write_tool_attempted

_UID = 4242


def _add_cred(db, **overrides):
    fields = dict(
        user_id=_UID,
        garmin_email="u@garmin.c",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        requires_mfa=False,
    )
    fields.update(overrides)
    db.add(GarminCredential(**fields))
    db.commit()


def _executor(db):
    ex = AgentExecutor(db)
    ex._current_user_id = _UID
    return ex


# ── 写诚实闸豁免:garmin_sync 不是写记录 ─────────────────────────────────
def test_garmin_sync_is_not_a_write_attempt():
    # record_type 与 type 双键都要豁免(模型两种都吐过)
    assert _write_tool_attempted("health_record", {"record_type": "garmin_sync"}) is False
    assert _write_tool_attempted("health_record", {"type": "garmin_sync"}) is False
    assert _write_tool_attempted("health_record", '{"record_type": "garmin_sync"}') is False
    # 真写记录仍判 True(不误伤)
    assert _write_tool_attempted("health_record", {"record_type": "water"}) is True
    assert _write_tool_attempted("health_record", {"record_type": "weight"}) is True


# ── 护栏①:precondition fail-loud,且不 enqueue ──────────────────────────
@pytest.mark.asyncio
async def test_no_credential_fails_loud_no_enqueue(db, monkeypatch):
    calls = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay",
                        lambda *a, **k: calls.append((a, k)))
    out = await _executor(db)._trigger_garmin_sync()
    assert "绑定" in out
    assert "设置" in out
    assert calls == []  # 未绑定绝不入队


@pytest.mark.asyncio
async def test_sync_disabled_fails_loud_no_enqueue(db, monkeypatch):
    calls = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay",
                        lambda *a, **k: calls.append((a, k)))
    _add_cred(db, sync_enabled=False)
    out = await _executor(db)._trigger_garmin_sync()
    assert "关闭" in out
    assert calls == []


@pytest.mark.asyncio
async def test_invalid_credentials_fail_loud_no_enqueue(db, monkeypatch):
    calls = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay",
                        lambda *a, **k: calls.append((a, k)))
    _add_cred(db, credentials_valid=False)
    out = await _executor(db)._trigger_garmin_sync()
    assert "失效" in out or "重新绑定" in out
    assert calls == []


@pytest.mark.asyncio
async def test_mfa_degrades_to_guidance_no_enqueue(db, monkeypatch):
    """护栏③:MFA → 指引,不自动重试/不入队。"""
    calls = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay",
                        lambda *a, **k: calls.append((a, k)))
    _add_cred(db, requires_mfa=True)
    out = await _executor(db)._trigger_garmin_sync()
    assert "MFA" in out or "两步验证" in out
    assert calls == []


# ── 护栏②:满足前提 → enqueue(notify_on_failure=True)+ 乐观 ack ─────────
@pytest.mark.asyncio
async def test_happy_path_enqueues_and_acks(db, monkeypatch):
    calls = []
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay",
                        lambda *a, **k: calls.append((a, k)))
    _add_cred(db)
    out = await _executor(db)._trigger_garmin_sync()
    # 乐观 ack:告诉用户后台在跑、会刷新、失败会告知(不谎报"已完成")
    assert "后台" in out
    assert "完成" not in out.split("。")[0] or "通常" in out  # 不是"已完成"式谎报
    # 恰好入队一次,带 notify_on_failure=True(fail-loud 前提)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == _UID
    assert kwargs.get("notify_on_failure") is True


@pytest.mark.asyncio
async def test_enqueue_failure_fails_loud(db, monkeypatch):
    """broker 挂了 → 不谎报成功,给可操作指引。"""
    def _boom(*a, **k):
        raise RuntimeError("broker down")
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "delay", _boom)
    _add_cred(db)
    out = await _executor(db)._trigger_garmin_sync()
    assert "暂时不可用" in out or "手动同步" in out


@pytest.mark.asyncio
async def test_no_user_id_fails_loud(db):
    ex = AgentExecutor(db)
    ex._current_user_id = None
    out = await ex._trigger_garmin_sync()
    assert "身份" in out or "稍后" in out
