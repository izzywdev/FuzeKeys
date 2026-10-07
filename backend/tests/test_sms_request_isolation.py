"""Durable SMS device authentication and creator-scoped request assignment."""

import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sms import SmsDevice, SmsOtpRequest
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


async def _device(db, device_id, key):
    db.add(
        SmsDevice(
            device_id=device_id,
            device_name=device_id,
            is_active=True,
            device_key_hash=sms._device_key_digest(key),
            key_rotated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


def _registration(device_id="device-a"):
    return sms.DeviceRegistrationRequest(
        device_id=device_id,
        device_name="Pixel",
        os_version="14",
        app_version="1.0.0",
    )


def _request(request_id, *, owner=7, device=None, status="waiting", expires=300):
    now = datetime.now(timezone.utc)
    return SmsOtpRequest(
        request_id=request_id,
        service="test",
        status=status,
        owner_user_id=owner,
        assigned_device_id=device,
        created_at=now,
        timeout_at=now + timedelta(seconds=expires),
    )


@pytest.mark.asyncio
async def test_device_only_sees_its_assigned_waiting_unexpired_requests(db_session):
    await _device(db_session, "device-a", "key-a")
    await _device(db_session, "device-b", "key-b")
    db_session.add_all(
        [
            _request("own", device="device-a"),
            _request("other", device="device-b"),
            _request("legacy"),
            _request("expired", device="device-a", expires=-1),
            _request("completed", device="device-a", status="completed"),
        ]
    )
    await db_session.commit()

    result = await sms.get_otp_requests("device-a", x_device_key="key-a", db=db_session)
    assert [row["request_id"] for row in result] == ["own"]
    other = await sms.get_otp_requests("device-b", x_device_key="key-b", db=db_session)
    assert [row["request_id"] for row in other] == ["other"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device,key", [("device-a", None), ("device-a", "key-b"), ("unknown", "key-a")]
)
async def test_missing_wrong_and_other_device_keys_are_rejected(
    db_session, device, key
):
    await _device(db_session, "device-a", "key-a")
    with pytest.raises(HTTPException) as denied:
        await sms.get_otp_requests(device, x_device_key=key, db=db_session)
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_registration_persists_only_digest_and_rotation_revokes_old_key(
    db_session, monkeypatch
):
    enrollment = "e" * 32
    monkeypatch.setenv("SMS_DEVICE_ENROLLMENT_TOKEN", enrollment)
    first = await sms.register_device(
        _registration(),
        x_enrollment_token=enrollment,
        db=db_session,
    )
    issued = first["api_key"]
    db_session.expunge_all()
    assert await sms._verify_device(db_session, "device-a", issued) is True
    row = (
        await db_session.execute(
            select(SmsDevice).where(SmsDevice.device_id == "device-a")
        )
    ).scalar_one()
    assert row.device_key_hash == sms._device_key_digest(issued)
    assert issued not in row.device_key_hash

    second = await sms.register_device(
        _registration(),
        x_enrollment_token=enrollment,
        db=db_session,
    )
    assert second["api_key"] != issued
    assert await sms._verify_device(db_session, "device-a", issued) is False
    assert await sms._verify_device(db_session, "device-a", second["api_key"]) is True
    row = (
        await db_session.execute(
            select(SmsDevice).where(SmsDevice.device_id == "device-a")
        )
    ).scalar_one()
    row.is_active = False
    await db_session.commit()
    assert await sms._verify_device(db_session, "device-a", second["api_key"]) is False


@pytest.mark.asyncio
async def test_registration_denial_cannot_rotate_existing_device(
    db_session, monkeypatch
):
    await _device(db_session, "device-a", "current-key")
    monkeypatch.setenv("SMS_DEVICE_ENROLLMENT_TOKEN", "e" * 32)
    with pytest.raises(HTTPException) as denied:
        await sms.register_device(
            _registration(),
            x_enrollment_token="wrong",
            db=db_session,
        )
    assert denied.value.status_code == 401
    assert await sms._verify_device(db_session, "device-a", "current-key") is True


@pytest.mark.asyncio
async def test_new_request_expiry_is_epoch_time_in_every_host_timezone(db_session):
    before = time.time()
    result = await sms.request_otp(
        "test",
        timeout_seconds=300,
        db=db_session,
        current_user=SimpleNamespace(id=7),
    )
    assert before + 300 <= result["timeout"] <= time.time() + 300
    row = (
        await db_session.execute(
            select(SmsOtpRequest).where(
                SmsOtpRequest.request_id == result["request_id"]
            )
        )
    ).scalar_one()
    assert row.owner_user_id == 7
    assert before <= sms._utc(row.created_at).timestamp() <= time.time()


@pytest.mark.asyncio
async def test_otp_result_is_visible_only_to_request_creator(db_session):
    row = _request("owned", owner=7, status="completed")
    row.otp_code = "123456"
    db_session.add(row)
    await db_session.commit()

    result = await sms.get_request_status(
        "owned", db=db_session, current_user=SimpleNamespace(id=7)
    )
    assert result["otp_code"] == "123456"
    for request_id in ("owned", "missing"):
        with pytest.raises(HTTPException) as hidden:
            await sms.get_request_status(
                request_id, db=db_session, current_user=SimpleNamespace(id=8)
            )
        assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_assignment_is_creator_bound_and_targets_one_active_device(
    db_session, monkeypatch
):
    await _device(db_session, "device-a", "key-a")
    db_session.add(_request("assign-me", owner=7))
    await db_session.commit()
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(sms.sms_manager, "send_to_device", send)

    with pytest.raises(HTTPException) as hidden:
        await sms.assign_otp_request(
            "assign-me",
            "device-a",
            db=db_session,
            current_user=SimpleNamespace(id=8),
        )
    assert hidden.value.status_code == 404

    result = await sms.assign_otp_request(
        "assign-me",
        "device-a",
        db=db_session,
        current_user=SimpleNamespace(id=7),
    )
    assert result["device_id"] == "device-a"
    row = (
        await db_session.execute(
            select(SmsOtpRequest).where(SmsOtpRequest.request_id == "assign-me")
        )
    ).scalar_one()
    assert row.assigned_device_id == "device-a"
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_callback_is_rejected_before_storing_otp(db_session):
    await _device(db_session, "device-a", "key-a")
    db_session.add(_request("expired", device="device-a", expires=-1))
    await db_session.commit()
    request = sms.OtpRequest(
        otp="123456",
        sender="test",
        message_body="test",
        timestamp=1700000000000,
        device_id="device-a",
        request_id="expired",
    )
    with pytest.raises(HTTPException) as denied:
        await sms.receive_otp(request, x_device_key="key-a", db=db_session)
    assert denied.value.status_code == 410
    row = (
        await db_session.execute(
            select(SmsOtpRequest).where(SmsOtpRequest.request_id == "expired")
        )
    ).scalar_one()
    assert row.status == "timeout"
    assert row.otp_code is None
