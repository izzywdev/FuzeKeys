"""Infrastructure device callbacks and sockets must fail closed."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

from app.routers import infrastructure, sms


class FakeWebSocket:
    def __init__(self, device_id="", key=None, incoming=None):
        self.query_params = {"device_id": device_id} if device_id else {}
        self.headers = {"x-device-key": key} if key is not None else {}
        self.incoming = list(incoming or [])
        self.accepted = False
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=None):
        self.closed = (code, reason)

    async def receive_text(self):
        if not self.incoming:
            raise WebSocketDisconnect()
        item = self.incoming.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_text(self, value):
        pass


@pytest.fixture(autouse=True)
def isolated_device_state():
    original_keys = dict(sms.registered_device_keys)
    original_requests = dict(infrastructure.verification_requests)
    original_active = list(infrastructure.mobile_manager.active_connections)
    original_devices = dict(infrastructure.mobile_manager.device_connections)
    sms.registered_device_keys.clear()
    infrastructure.verification_requests.clear()
    infrastructure.mobile_manager.active_connections.clear()
    infrastructure.mobile_manager.device_connections.clear()
    sms.registered_device_keys.update({"device-a": "key-a", "device-b": "key-b"})
    yield
    sms.registered_device_keys.clear()
    sms.registered_device_keys.update(original_keys)
    infrastructure.verification_requests.clear()
    infrastructure.verification_requests.update(original_requests)
    infrastructure.mobile_manager.active_connections[:] = original_active
    infrastructure.mobile_manager.device_connections.clear()
    infrastructure.mobile_manager.device_connections.update(original_devices)


def pending_request(**overrides):
    value = {
        "status": "pending",
        "timeout_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
async def test_request_is_withheld_until_authorized_assignment(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(infrastructure.sms_manager, "broadcast", broadcast)
    result = await infrastructure.request_sms_verification(
        infrastructure.SmsVerificationRequest(
            site="example",
            phone_number="+15555550100",
        ),
        db=None,
        current_user=object(),
    )
    assert result["status"] == "pending"
    assert "sent" not in result["message"].lower()
    broadcast.assert_not_awaited()
    stored = infrastructure.verification_requests[result["request_id"]]
    assert "assigned_device_id" not in stored


@pytest.mark.asyncio
async def test_authenticated_device_cannot_claim_unassigned_request():
    infrastructure.verification_requests["req"] = pending_request()
    before = dict(infrastructure.verification_requests["req"])
    with pytest.raises(HTTPException) as denied:
        await infrastructure.complete_sms_verification(
            "req", "123456", "device-a", x_device_key="key-a"
        )
    assert denied.value.status_code == 409
    assert infrastructure.verification_requests["req"] == before


@pytest.mark.asyncio
async def test_only_assigned_device_can_complete_pending_request():
    infrastructure.verification_requests["req"] = pending_request(
        assigned_device_id="device-a"
    )
    with pytest.raises(HTTPException) as denied:
        await infrastructure.complete_sms_verification(
            "req", "123456", "device-b", x_device_key="key-b"
        )
    assert denied.value.status_code == 403

    result = await infrastructure.complete_sms_verification(
        "req", " 123456 ", "device-a", x_device_key="key-a"
    )
    assert result["status"] == "success"
    stored = infrastructure.verification_requests["req"]
    assert stored["status"] == "completed"
    assert stored["code"] == "123456"


@pytest.mark.asyncio
async def test_expired_and_invalid_codes_fail_before_completion():
    infrastructure.verification_requests["expired"] = pending_request(
        assigned_device_id="device-a",
        timeout_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(HTTPException) as expired:
        await infrastructure.complete_sms_verification(
            "expired", "123456", "device-a", x_device_key="key-a"
        )
    assert expired.value.status_code == 410
    assert infrastructure.verification_requests["expired"]["status"] == "timeout"
    assert "code" not in infrastructure.verification_requests["expired"]

    infrastructure.verification_requests["invalid"] = pending_request(
        assigned_device_id="device-a"
    )
    with pytest.raises(HTTPException) as invalid:
        await infrastructure.complete_sms_verification(
            "invalid", "not-an-otp", "device-a", x_device_key="key-a"
        )
    assert invalid.value.status_code == 400
    assert infrastructure.verification_requests["invalid"]["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_id,key",
    [("", None), ("device-a", None), ("device-a", "wrong"), ("unknown", "key-a")],
)
async def test_invalid_mobile_socket_closes_before_join(device_id, key):
    websocket = FakeWebSocket(device_id, key)
    await infrastructure.mobile_commands_websocket(websocket)
    assert websocket.accepted is False
    assert websocket.closed == (1008, "Device authentication failed")
    assert websocket not in infrastructure.mobile_manager.active_connections
    assert device_id not in infrastructure.mobile_manager.device_connections


@pytest.mark.asyncio
async def test_authenticated_mobile_socket_joins_and_is_removed():
    websocket = FakeWebSocket(
        "device-a",
        "key-a",
        incoming=[json.dumps({"type": "command_result", "secret": "redacted"})],
    )
    await infrastructure.mobile_commands_websocket(websocket)
    assert websocket.accepted is True
    assert websocket.closed is None
    assert websocket not in infrastructure.mobile_manager.active_connections
    assert "device-a" not in infrastructure.mobile_manager.device_connections
