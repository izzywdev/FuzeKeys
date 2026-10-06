"""Device authentication must not expose another device's pending work."""

import os
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import sms


@pytest.fixture(autouse=True, params=["UTC", "Asia/Jerusalem", "America/Los_Angeles"])
def host_timezone(request, monkeypatch):
    previous = os.environ.get("TZ")
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield
    if previous is None:
        monkeypatch.delenv("TZ")
    else:
        monkeypatch.setenv("TZ", previous)
    time.tzset()


@pytest.fixture(autouse=True)
def isolated_device_state():
    original_keys = dict(sms.registered_device_keys)
    original_requests = dict(sms.pending_otp_requests)
    sms.registered_device_keys.clear()
    sms.pending_otp_requests.clear()
    sms.registered_device_keys.update({"device-a": "key-a", "device-b": "key-b"})
    yield
    sms.registered_device_keys.clear()
    sms.registered_device_keys.update(original_keys)
    sms.pending_otp_requests.clear()
    sms.pending_otp_requests.update(original_requests)


@pytest.mark.asyncio
async def test_device_only_sees_its_assigned_waiting_unexpired_requests():
    future = time.time() + 300
    sms.pending_otp_requests.update(
        {
            "own": {
                "assigned_device_id": "device-a",
                "status": "waiting",
                "timeout": future,
            },
            "other": {
                "assigned_device_id": "device-b",
                "status": "waiting",
                "timeout": future,
            },
            "legacy": {"status": "waiting", "timeout": future},
            "malformed": {
                "assigned_device_id": 1,
                "status": "waiting",
                "timeout": future,
            },
            "expired": {
                "assigned_device_id": "device-a",
                "status": "waiting",
                "timeout": time.time() - 1,
            },
            "completed": {
                "assigned_device_id": "device-a",
                "status": "completed",
                "timeout": future,
            },
        }
    )
    before = {key: dict(value) for key, value in sms.pending_otp_requests.items()}
    result = await sms.get_otp_requests("device-a", x_device_key="key-a", db=None)
    assert [row["request_id"] for row in result] == ["own"]
    assert sms.pending_otp_requests == before
    other = await sms.get_otp_requests("device-b", x_device_key="key-b", db=None)
    assert [row["request_id"] for row in other] == ["other"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device,key", [("device-a", None), ("device-a", "key-b"), ("unknown", "key-a")]
)
async def test_missing_wrong_and_other_device_keys_are_rejected(device, key):
    with pytest.raises(HTTPException) as denied:
        await sms.get_otp_requests(device, x_device_key=key, db=None)
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_new_request_expiry_is_epoch_time_in_every_host_timezone(monkeypatch):
    class Database:
        def add(self, row):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(sms.sms_manager, "broadcast", AsyncMock())
    before = time.time()
    result = await sms.request_otp(
        "test", timeout_seconds=300, db=Database(), current_user=object()
    )
    assert before + 300 <= result["timeout"] <= time.time() + 300
    pending = sms.pending_otp_requests[result["request_id"]]
    assert before <= pending["created_at"] <= time.time()


@pytest.mark.asyncio
async def test_expired_callback_is_rejected_before_storing_otp():
    sms.pending_otp_requests["expired"] = {
        "assigned_device_id": "device-a",
        "status": "waiting",
        "timeout": time.time() - 1,
    }
    request = sms.OtpRequest(
        otp="123456",
        sender="test",
        message_body="test",
        timestamp=1700000000000,
        device_id="device-a",
        request_id="expired",
    )
    with pytest.raises(HTTPException) as denied:
        await sms.receive_otp(request, x_device_key="key-a", db=None)
    assert denied.value.status_code == 410
    assert "otp_code" not in sms.pending_otp_requests["expired"]
