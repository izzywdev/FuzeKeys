"""Infrastructure device callbacks and sockets must fail closed."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.models.sms import SmsDevice, SmsOtpRequest
from app.routers import infrastructure, sms


class User:
    def __init__(self, user_id):
        self.id = user_id


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


@pytest_asyncio.fixture(autouse=True)
async def isolated_device_state(db_session):
    original_monitors = dict(infrastructure.email_monitors)
    original_active = list(infrastructure.mobile_manager.active_connections)
    original_devices = dict(infrastructure.mobile_manager.device_connections)
    original_commands = dict(infrastructure.mobile_commands)
    infrastructure.email_monitors.clear()
    infrastructure.mobile_manager.active_connections.clear()
    infrastructure.mobile_manager.device_connections.clear()
    infrastructure.mobile_commands.clear()
    db_session.add_all(
        [
            SmsDevice(
                device_id="device-a",
                device_name="device-a",
                is_active=True,
                device_key_hash=sms._device_key_digest("key-a"),
                key_rotated_at=datetime.now(timezone.utc),
            ),
            SmsDevice(
                device_id="device-b",
                device_name="device-b",
                is_active=True,
                device_key_hash=sms._device_key_digest("key-b"),
                key_rotated_at=datetime.now(timezone.utc),
            ),
        ]
    )
    await db_session.commit()
    yield
    infrastructure.email_monitors.clear()
    infrastructure.email_monitors.update(original_monitors)
    infrastructure.mobile_manager.active_connections[:] = original_active
    infrastructure.mobile_manager.device_connections.clear()
    infrastructure.mobile_manager.device_connections.update(original_devices)
    infrastructure.mobile_commands.clear()
    infrastructure.mobile_commands.update(original_commands)


def pending_request(request_id, **overrides):
    value = {
        "request_id": request_id,
        "service": "example",
        "status": "waiting",
        "timeout_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    value.update(overrides)
    return SmsOtpRequest(**value)


@pytest.mark.asyncio
async def test_request_is_withheld_until_authorized_assignment(monkeypatch, db_session):
    broadcast = AsyncMock()
    monkeypatch.setattr(infrastructure.sms_manager, "broadcast", broadcast)
    result = await infrastructure.request_sms_verification(
        infrastructure.SmsVerificationRequest(
            site="example",
            phone_number="+15555550100",
        ),
        db=db_session,
        current_user=User(7),
    )
    assert result["status"] == "pending"
    assert "sent" not in result["message"].lower()
    broadcast.assert_not_awaited()
    stored = (
        await db_session.execute(
            select(SmsOtpRequest).where(
                SmsOtpRequest.request_id == result["request_id"]
            )
        )
    ).scalar_one()
    assert stored.owner_user_id == 7
    assert stored.target_phone_number == "+15555550100"
    assert stored.assigned_device_id is None


@pytest.mark.asyncio
async def test_verification_code_is_visible_only_to_request_creator(db_session):
    db_session.add(
        pending_request(
            "owned",
            owner_user_id=7,
            status="completed",
            otp_code="123456",
        )
    )
    db_session.add(
        pending_request(
            "legacy",
            owner_user_id=None,
            status="completed",
            otp_code="654321",
        )
    )
    await db_session.commit()
    result = await infrastructure.get_sms_verification(
        "owned", db=db_session, current_user=User(7)
    )
    assert result.code == "123456"

    for request_id in ("owned", "legacy", "missing"):
        with pytest.raises(HTTPException) as hidden:
            await infrastructure.get_sms_verification(
                request_id, db=db_session, current_user=User(8)
            )
        assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_verification_timeout_is_persisted(db_session):
    request = pending_request(
        "expired-owner-read",
        owner_user_id=7,
        timeout_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db_session.add(request)
    await db_session.commit()
    result = await infrastructure.get_sms_verification(
        request.request_id, db=db_session, current_user=User(7)
    )
    assert result.status == "timeout"
    await db_session.refresh(request)
    assert request.status == "timeout"


@pytest.mark.asyncio
async def test_email_monitor_is_visible_only_to_request_creator():
    created = await infrastructure.setup_email_monitoring(
        infrastructure.EmailMonitoringRequest(
            email="owner@example.com",
            sender_patterns=["security"],
            subject_patterns=["code"],
        ),
        current_user=User(7),
    )
    monitor_id = created["monitor_id"]
    assert infrastructure.email_monitors[monitor_id]["owner_user_id"] == 7

    result = await infrastructure.get_email_verification(
        monitor_id, current_user=User(7)
    )
    assert result["monitor_id"] == monitor_id

    with pytest.raises(HTTPException) as hidden:
        await infrastructure.get_email_verification(monitor_id, current_user=User(8))
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_authenticated_device_cannot_claim_unassigned_request(db_session):
    request = pending_request("req")
    db_session.add(request)
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await infrastructure.complete_sms_verification(
            "req", "123456", "device-a", x_device_key="key-a", db=db_session
        )
    assert denied.value.status_code == 409
    await db_session.refresh(request)
    assert request.status == "waiting"
    assert request.otp_code is None


@pytest.mark.asyncio
async def test_only_assigned_device_can_complete_pending_request(db_session):
    request = pending_request("req", assigned_device_id="device-a")
    db_session.add(request)
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await infrastructure.complete_sms_verification(
            "req", "123456", "device-b", x_device_key="key-b", db=db_session
        )
    assert denied.value.status_code == 403

    result = await infrastructure.complete_sms_verification(
        "req", " 123456 ", "device-a", x_device_key="key-a", db=db_session
    )
    assert result["status"] == "success"
    await db_session.refresh(request)
    assert request.status == "completed"
    assert request.otp_code == "123456"


@pytest.mark.asyncio
async def test_expired_and_invalid_codes_fail_before_completion(db_session):
    expired_request = pending_request(
        "expired",
        assigned_device_id="device-a",
        timeout_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db_session.add(expired_request)
    await db_session.commit()
    with pytest.raises(HTTPException) as expired:
        await infrastructure.complete_sms_verification(
            "expired", "123456", "device-a", x_device_key="key-a", db=db_session
        )
    assert expired.value.status_code == 410
    await db_session.refresh(expired_request)
    assert expired_request.status == "timeout"
    assert expired_request.otp_code is None

    invalid_request = pending_request("invalid", assigned_device_id="device-a")
    db_session.add(invalid_request)
    await db_session.commit()
    with pytest.raises(HTTPException) as invalid:
        await infrastructure.complete_sms_verification(
            "invalid", "not-an-otp", "device-a", x_device_key="key-a", db=db_session
        )
    assert invalid.value.status_code == 400
    await db_session.refresh(invalid_request)
    assert invalid_request.status == "waiting"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_id,key",
    [("", None), ("device-a", None), ("device-a", "wrong"), ("unknown", "key-a")],
)
async def test_invalid_mobile_socket_closes_before_join(db_session, device_id, key):
    websocket = FakeWebSocket(device_id, key)
    await infrastructure.mobile_commands_websocket(websocket, db=db_session)
    assert websocket.accepted is False
    assert websocket.closed == (1008, "Device authentication failed")
    assert websocket not in infrastructure.mobile_manager.active_connections
    assert device_id not in infrastructure.mobile_manager.device_connections


@pytest.mark.asyncio
async def test_authenticated_mobile_socket_joins_and_is_removed(db_session):
    websocket = FakeWebSocket(
        "device-a",
        "key-a",
        incoming=[json.dumps({"type": "command_result", "secret": "redacted"})],
    )
    await infrastructure.mobile_commands_websocket(websocket, db=db_session)
    assert websocket.accepted is True
    assert websocket.closed is None
    assert websocket not in infrastructure.mobile_manager.active_connections
    assert "device-a" not in infrastructure.mobile_manager.device_connections


@pytest.mark.asyncio
async def test_mobile_command_targets_one_connected_device(monkeypatch):
    send = AsyncMock(return_value=True)
    broadcast = AsyncMock()
    monkeypatch.setattr(
        infrastructure.mobile_manager, "is_device_connected", lambda _: True
    )
    monkeypatch.setattr(infrastructure.mobile_manager, "send_to_device", send)
    monkeypatch.setattr(infrastructure.mobile_manager, "broadcast", broadcast)

    result = await infrastructure.send_mobile_command(
        infrastructure.MobileCommandRequest(
            device_id="device-a",
            command_type="extract_totp",
            parameters={"site": "example"},
        ),
        current_user=User(7),
    )

    command = infrastructure.mobile_commands[result["command_id"]]
    assert command["owner_user_id"] == 7
    assert command["device_id"] == "device-a"
    send.assert_awaited_once()
    assert send.await_args.args[1] == "device-a"
    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_command_rejects_unavailable_device(monkeypatch):
    monkeypatch.setattr(
        infrastructure.mobile_manager, "is_device_connected", lambda _: False
    )
    with pytest.raises(HTTPException) as denied:
        await infrastructure.send_mobile_command(
            infrastructure.MobileCommandRequest(
                device_id="offline",
                command_type="extract_totp",
                parameters={},
            ),
            current_user=User(7),
        )
    assert denied.value.status_code == 409
    assert infrastructure.mobile_commands == {}


@pytest.mark.asyncio
async def test_mobile_result_requires_target_device_and_owner(db_session):
    infrastructure.mobile_commands["cmd"] = {
        "owner_user_id": 7,
        "device_id": "device-a",
        "status": "pending",
    }

    wrong_device = FakeWebSocket(
        "device-b",
        "key-b",
        incoming=[
            json.dumps(
                {"type": "command_result", "command_id": "cmd", "result": "stolen"}
            )
        ],
    )
    await infrastructure.mobile_commands_websocket(wrong_device, db=db_session)
    assert infrastructure.mobile_commands["cmd"]["status"] == "pending"
    assert "result" not in infrastructure.mobile_commands["cmd"]

    assigned_device = FakeWebSocket(
        "device-a",
        "key-a",
        incoming=[
            json.dumps({"type": "command_result", "command_id": "cmd", "result": "ok"})
        ],
    )
    await infrastructure.mobile_commands_websocket(assigned_device, db=db_session)
    assert infrastructure.mobile_commands["cmd"]["status"] == "completed"

    with pytest.raises(HTTPException) as hidden:
        await infrastructure.get_mobile_command_result("cmd", current_user=User(8))
    assert hidden.value.status_code == 404

    result = await infrastructure.get_mobile_command_result("cmd", current_user=User(7))
    assert result == {"command_id": "cmd", "status": "completed", "result": "ok"}
