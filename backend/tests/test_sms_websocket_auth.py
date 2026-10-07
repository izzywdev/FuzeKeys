"""SMS WebSocket clients must authenticate before joining the device manager."""

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.routers import sms


class FakeWebSocket:
    def __init__(self, device_id="", key=None, incoming=None):
        self.query_params = {"device_id": device_id} if device_id else {}
        self.headers = {"x-device-key": key} if key is not None else {}
        self.incoming = list(incoming or [])
        self.accepted = False
        self.closed = None
        self.sent = []

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
        self.sent.append(value)


@pytest.fixture(autouse=True)
def isolated_device_state():
    original_keys = dict(sms.registered_device_keys)
    original_active = list(sms.sms_manager.active_connections)
    original_devices = dict(sms.sms_manager.device_connections)
    sms.registered_device_keys.clear()
    sms.sms_manager.active_connections.clear()
    sms.sms_manager.device_connections.clear()
    sms.registered_device_keys["device-a"] = sms._device_key_digest("key-a")
    yield
    sms.registered_device_keys.clear()
    sms.registered_device_keys.update(original_keys)
    sms.sms_manager.active_connections[:] = original_active
    sms.sms_manager.device_connections.clear()
    sms.sms_manager.device_connections.update(original_devices)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_id,key",
    [("", None), ("device-a", None), ("device-a", "wrong"), ("unknown", "key-a")],
)
async def test_invalid_handshake_closes_before_joining_manager(device_id, key):
    websocket = FakeWebSocket(device_id, key)
    await sms.sms_interceptor_websocket(websocket)
    assert websocket.accepted is False
    assert websocket.closed == (1008, "Device authentication failed")
    assert websocket not in sms.sms_manager.active_connections
    assert device_id not in sms.sms_manager.device_connections


@pytest.mark.asyncio
async def test_authenticated_device_joins_responds_and_is_removed():
    websocket = FakeWebSocket(
        "device-a",
        "key-a",
        incoming=[json.dumps({"type": "ping"})],
    )
    await sms.sms_interceptor_websocket(websocket)
    assert websocket.accepted is True
    assert websocket.closed is None
    assert websocket.sent == [json.dumps({"type": "pong"})]
    assert websocket not in sms.sms_manager.active_connections
    assert "device-a" not in sms.sms_manager.device_connections
