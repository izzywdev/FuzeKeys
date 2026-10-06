"""Connector grant snapshots carry authoritative tuple hashes and no secrets."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from apply_owner_grants import (
    ProvisioningRejected,
    tuple_payload,
    validate_inventory,
    verify_decisions,
)
from owner_grant_inventory import build_connector_inventory


def row(tenant="tenant-a", owner="owner", provider="slack"):
    key = (
        "connector:"
        + hashlib.sha256(
            json.dumps(
                [tenant, owner, provider], separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    return {
        "id": 1,
        "tenant_id": tenant,
        "owner_subject": owner,
        "provider": provider,
        "resource_key": key,
        "desired_state": "present",
    }


def test_snapshot_and_operator_wire_preserve_exact_owner_provider_tuple():
    source = row(owner="owner-שלום")
    inventory = build_connector_inventory([source])
    grants = validate_inventory(inventory, inventory["checksum_sha256"], "tenant-a")
    assert len(grants) == 1
    assert grants[0]["resource_key"] == source["resource_key"]
    assert tuple_payload(grants[0])["connectorProvider"] == "slack"
    assert not any("vault" in key or "credential" in key for key in grants[0])


@pytest.mark.parametrize(
    "change",
    [
        {"resource_key": "connector:" + "0" * 64},
        {"desired_state": "absent"},
        {"owner_subject": "another-owner"},
    ],
)
def test_sql_intent_disagreement_cannot_provision(change):
    source = row()
    source.update(change)
    with pytest.raises(ValueError):
        build_connector_inventory([source])


def test_unbound_rows_are_not_inferred_and_foreign_tenant_rejected():
    inventory = build_connector_inventory([row(tenant=None)])
    assert inventory["ready"] is False
    assert inventory["grants"] == []
    inventory = build_connector_inventory([row()])
    with pytest.raises(ProvisioningRejected):
        validate_inventory(inventory, inventory["checksum_sha256"], "tenant-b")


@pytest.mark.asyncio
async def test_connector_canaries_check_every_real_action_and_foreign_principal():
    class Response:
        def __init__(self, allowed):
            self.allowed = allowed

        def raise_for_status(self):
            pass

        def json(self):
            return {"allow": self.allowed}

    client = AsyncMock()
    client.post.side_effect = [Response(True)] * 6 + [Response(False)]
    grant = build_connector_inventory([row()])["grants"][0]
    await verify_decisions(client, grant)
    calls = [call.kwargs["json"] for call in client.post.await_args_list]
    assert [call["action"] for call in calls] == [
        "read",
        "create",
        "configure",
        "disconnect",
        "reveal",
        "write_credential",
        "configure",
    ]
    assert calls[-1]["subject"] == "fuzekeys-owner-canary-unassigned"
    assert all("connectorProvider" not in call for call in calls)
