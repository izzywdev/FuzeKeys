"""Route additions/remounts must be visible in the reviewed runtime inventory."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mounted_authorization_inventory import build_inventory

from app.main import app


def test_reviewed_inventory_matches_all_actual_mounted_routes():
    root = Path(__file__).resolve().parents[2]
    snapshot = json.loads(
        (root / "docs/security/mounted-route-authorization.json").read_text()
    )
    assert build_inventory(app) == snapshot
    tuples = {(row["method"], row["path"]) for row in snapshot["routes"]}
    assert ("POST", "/api/v1/auth/platform-link") in tuples
    assert ("GET", "/api/v1/connectors/google-gmail/credential") in tuples
    assert ("PUT", "/api/v1/connectors/{provider}/credential") in tuples
    assert ("POST", "/api/v1/sites/") not in tuples
    assert not any("background" in row["endpoint"] for row in snapshot["routes"])
    assert any(
        row["assessment"] == "enrollment_token_platform_mapping_gap"
        for row in snapshot["routes"]
    )
    assert any(
        row["assessment"] == "durable_local_owner_platform_mapping_gap"
        for row in snapshot["routes"]
    )
    assert any(
        row["assessment"] == "platform_policy_design_gap" for row in snapshot["routes"]
    )
    assert snapshot["production_verified"] is False
