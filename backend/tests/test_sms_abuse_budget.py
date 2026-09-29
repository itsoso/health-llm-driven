import concurrent.futures
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import redis


@pytest.fixture
def sms_redis(monkeypatch):
    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip("real Redis executable required for atomic quota proof")
    from app.config import settings
    with tempfile.TemporaryDirectory(prefix="reva-sms-") as directory:
        socket = str(Path(directory) / "redis.sock")
        with open(Path(directory) / "redis.log", "w") as log:
            process = subprocess.Popen([executable, "--port", "0", "--unixsocket", socket,
                                        "--save", "", "--appendonly", "no"], stdout=log, stderr=log)
            try:
                client = redis.Redis(unix_socket_path=socket)
                for _ in range(100):
                    try:
                        if client.ping():
                            break
                    except redis.RedisError:
                        time.sleep(.02)
                else:
                    pytest.fail("test Redis did not become ready")
                monkeypatch.setattr(settings, "redis_url", "unix://" + socket)
                monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0)
                yield client
            finally:
                process.terminate()
                process.wait(timeout=5)


def test_concurrent_global_sms_budget_is_atomic(sms_redis, monkeypatch):
    from app.config import settings
    from app.services.sms_abuse_budget import reserve_sms_delivery, SmsQuotaExceeded
    monkeypatch.setattr(settings, "auth_sms_global_daily_limit", 3)

    def reserve(index):
        try:
            reserve_sms_delivery(f"+861380013{index:04d}", f"192.0.2.{index}")
            return True
        except SmsQuotaExceeded:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(16))) == 3
    assert sms_redis.get("auth:sms:global:day") == b"3"


def test_phone_budget_survives_ip_rotation_without_plaintext_keys(sms_redis, monkeypatch):
    from app.config import settings
    from app.services.sms_abuse_budget import reserve_sms_delivery, SmsQuotaExceeded
    monkeypatch.setattr(settings, "auth_sms_phone_daily_limit", 2)
    phone = "+8613800138888"
    reserve_sms_delivery(phone, "192.0.2.1")
    reserve_sms_delivery(phone, "192.0.2.2")
    with pytest.raises(SmsQuotaExceeded):
        reserve_sms_delivery(phone, "192.0.2.3")
    keys = list(sms_redis.scan_iter())
    assert all(phone.encode() not in k and b"192.0.2" not in k for k in keys)
    assert all(sms_redis.ttl(k) > 0 for k in keys)


def test_sms_budget_storage_failure_fails_closed(monkeypatch):
    from app.config import settings
    from app.services.sms_abuse_budget import reserve_sms_delivery, SmsQuotaUnavailable
    monkeypatch.setattr(settings, "redis_url", "unix:///tmp/reva-nonexistent-budget-socket")
    with pytest.raises(SmsQuotaUnavailable):
        reserve_sms_delivery("+8613800138888", "192.0.2.1")


def test_ip_budget_limits_rotating_phone_numbers(sms_redis, monkeypatch):
    from app.config import settings
    from app.services.sms_abuse_budget import reserve_sms_delivery, SmsQuotaExceeded
    monkeypatch.setattr(settings, "auth_sms_ip_hourly_limit", 1)
    reserve_sms_delivery("+8613800138888", "192.0.2.1")
    with pytest.raises(SmsQuotaExceeded):
        reserve_sms_delivery("+8613800138889", "192.0.2.1")


def test_concurrent_resend_uses_one_global_budget_slot(sms_redis, monkeypatch):
    from app.config import settings
    from app.services.sms_abuse_budget import reserve_sms_delivery, SmsQuotaExceeded
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 60)
    reserve_sms_delivery("+8613800138888", "192.0.2.1")
    with pytest.raises(SmsQuotaExceeded):
        reserve_sms_delivery("+8613800138888", "192.0.2.2")
    assert sms_redis.get("auth:sms:global:day") == b"1"


@pytest.mark.parametrize("unavailable", [False, True])
def test_production_budget_denial_never_calls_paid_provider(monkeypatch, unavailable):
    from app.config import settings
    from app.services import phone_auth, sms_abuse_budget
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(phone_auth, "_aliyun_sms_configured", lambda: True)
    called = []
    monkeypatch.setattr(phone_auth, "_send_aliyun_sms", lambda *args: called.append(args))
    error = sms_abuse_budget.SmsQuotaUnavailable if unavailable else sms_abuse_budget.SmsQuotaExceeded
    def deny(*args):
        raise error("denied")
    monkeypatch.setattr(sms_abuse_budget, "reserve_sms_delivery", deny)
    expected = phone_auth.PhoneCodeDeliveryFailed if unavailable else phone_auth.PhoneCodeCooldown
    with pytest.raises(expected):
        phone_auth._deliver_code("+8613800138888", "123456", "192.0.2.1")
    assert called == []
