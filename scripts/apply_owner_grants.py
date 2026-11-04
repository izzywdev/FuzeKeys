"""Review and apply exact, verified owner tuples through Security, never Permit.

Requires a production SQL re-inventory and fresh membership proof. Mutations
are explicit (--apply) and journaled; there is no tenant-wide fallback or revoke.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from owner_grant_inventory import read_connector_inventory, read_inventory

RESOURCE_PREFIXES = {
    "fuzekeys_Identity": "identity",
    "fuzekeys_Account": "account",
    "fuzekeys_VaultAsset": "api-credential",
    "fuzekeys_Connector": "connector",
}


class ProvisioningRejected(Exception):
    """Stop without interpreting transport/provider errors as permission."""


def validate_inventory(inventory, checksum, tenant):
    if (
        not isinstance(inventory, dict)
        or inventory.get("mode") != "dry-run"
        or inventory.get("ready") is not True
        or inventory.get("rejected") != []
        or inventory.get("requires_current_membership_verification") is not True
        or not isinstance(tenant, str)
        or not tenant
        or tenant.strip() != tenant
    ):
        raise ProvisioningRejected("Inventory is not ready for this tenant")
    grants = inventory.get("grants")
    if not isinstance(grants, list):
        raise ProvisioningRejected("Malformed grant inventory")
    seen = set()
    for grant in grants:
        expected_fields = {
            "subject",
            "tenant",
            "resource_type",
            "resource_key",
            "role",
        }
        if (
            isinstance(grant, dict)
            and grant.get("resource_type") == "fuzekeys_Connector"
        ):
            expected_fields.add("connector_provider")
        if not isinstance(grant, dict) or set(grant) != expected_fields:
            raise ProvisioningRejected("Malformed grant tuple")
        prefix = RESOURCE_PREFIXES.get(grant["resource_type"])
        subject = grant["subject"]
        if (
            not prefix
            or not isinstance(grant["resource_key"], str)
            or not re.fullmatch(
                re.escape(prefix)
                + (r":[0-9a-f]{64}" if prefix == "connector" else r":[1-9][0-9]*"),
                grant["resource_key"],
            )
            or grant["role"] != "owner"
            or grant["tenant"] != tenant
            or not isinstance(subject, str)
            or not subject
            or subject.strip() != subject
        ):
            raise ProvisioningRejected("Grant is not an exact tenant owner tuple")
        key = (grant["resource_type"], grant["resource_key"])
        if key in seen:
            raise ProvisioningRejected("Duplicate resource tuple")
        seen.add(key)
        if prefix == "connector":
            provider = grant["connector_provider"]
            if (
                not isinstance(provider, str)
                or len(provider) > 80
                or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", provider)
            ):
                raise ProvisioningRejected("Connector provider is invalid")
            expected_key = (
                "connector:"
                + hashlib.sha256(
                    json.dumps(
                        [tenant, subject, provider],
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest()
            )
            if grant["resource_key"] != expected_key:
                raise ProvisioningRejected(
                    "Connector instance key differs from verified owner tuple"
                )
    payload = {"grants": grants, "rejected": []}
    computed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        not isinstance(checksum, str)
        or computed != checksum
        or inventory.get("checksum_sha256") != checksum
    ):
        raise ProvisioningRejected("Inventory checksum differs from reviewed snapshot")
    count = len(grants)
    if any(
        type(inventory.get(name)) is not int or inventory[name] != value
        for name, value in (
            ("resource_count", count),
            ("verified_resource_count", count),
            ("rejected_count", 0),
        )
    ):
        raise ProvisioningRejected("Inventory counts are inconsistent")
    return grants


def security_origin(raw):
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ProvisioningRejected("Security must be an HTTPS origin")
    return raw.rstrip("/")


def tuple_payload(grant):
    payload = {
        "subject": grant["subject"],
        "tenant": grant["tenant"],
        "role": "owner",
        "resource": {"type": grant["resource_type"], "key": grant["resource_key"]},
    }
    if grant["resource_type"] == "fuzekeys_Connector":
        payload["connectorProvider"] = grant["connector_provider"]
    return payload


async def require_membership(client, grant):
    response = await client.get(
        "/api/v1/security/authz/membership-proof",
        params={
            "subject": grant["subject"],
            "tenant": grant["tenant"],
        },
    )
    response.raise_for_status()
    proof = response.json()
    if (
        not isinstance(proof, dict)
        or proof.get("subject") != grant["subject"]
        or proof.get("tenant") != grant["tenant"]
        or proof.get("active") is not True
    ):
        raise ProvisioningRejected("Fresh membership proof rejected")


async def verify_decisions(client, grant):
    payload = tuple_payload(grant)
    payload.pop("role")
    payload.pop("connectorProvider", None)
    actions = ("read", "update", "delete")
    if grant["resource_type"] == "fuzekeys_Identity":
        actions += ("use",)
    elif grant["resource_type"] == "fuzekeys_Connector":
        actions = (
            "read",
            "create",
            "configure",
            "disconnect",
            "reveal",
            "write_credential",
        )
    for action in actions:
        response = await client.post(
            "/api/v1/security/authz/check", json={**payload, "action": action}
        )
        response.raise_for_status()
        if response.json().get("allow") is not True:
            raise ProvisioningRejected("Owner decision canary rejected")
    # The grant must never confer update permission to an unassigned principal.
    response = await client.post(
        "/api/v1/security/authz/check",
        json={
            **payload,
            "subject": "fuzekeys-owner-canary-unassigned",
            "action": "configure"
            if grant["resource_type"] == "fuzekeys_Connector"
            else "update",
        },
    )
    response.raise_for_status()
    if response.json().get("allow") is not False:
        raise ProvisioningRejected("Foreign-principal denial canary rejected")


async def provision(client, grants, *, apply, verify_snapshot, journal):
    # Complete all proofs before the first mutation; the grant endpoint must
    # also recheck current SQL membership, closing the proof/grant race.
    for grant in {g["subject"]: g for g in grants}.values():
        await require_membership(client, grant)
    await verify_snapshot()
    if not apply:
        return 0
    completed = 0
    for grant in grants:
        await verify_snapshot()
        await require_membership(client, grant)
        payload = tuple_payload(grant)
        # Record intent before the network: a lost response is an indeterminate
        # write, never proof it failed. Do not automatically revoke by ID:
        # the current provider IDs omit the instance and can alias grants.
        journal({"event": "grant-requested", "tuple": payload})
        response = await client.post("/api/v1/security/authz/grants", json=payload)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or any(
            result.get(k) != v for k, v in payload.items()
        ):
            raise ProvisioningRejected("Grant acknowledgement does not match tuple")
        journal({"event": "grant-acknowledged", "tuple": payload})
        await verify_decisions(client, grant)
        journal({"event": "canary-verified", "tuple": payload})
        completed += 1
    return completed


async def run(args):
    import httpx

    inventory = json.loads(Path(args.inventory).read_text())
    grants = validate_inventory(inventory, args.checksum, args.tenant)
    url = os.environ.get("DATABASE_URL_ASYNC") or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        raise ProvisioningRejected(
            "Production PostgreSQL inventory connection required"
        )

    async def verify_snapshot():
        current = await (
            read_connector_inventory(url, args.tenant)
            if args.connectors
            else read_inventory(url)
        )
        if current != inventory:
            raise ProvisioningRejected("SQL ownership changed; review a new inventory")

    token = Path(args.token_file).read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise ProvisioningRejected("Operator token is malformed")
    descriptor = os.open(args.journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:

        def journal(event):
            output.write(json.dumps(event, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())

        async with httpx.AsyncClient(
            base_url=security_origin(args.security_url),
            headers={"Authorization": "Bearer " + token},
            timeout=5.0,
            follow_redirects=False,
        ) as client:
            count = await provision(
                client,
                grants,
                apply=args.apply,
                verify_snapshot=verify_snapshot,
                journal=journal,
            )
        print(
            json.dumps(
                {
                    "mode": "applied" if args.apply else "preflight",
                    "verified_grants": count,
                    "proposed_grants": len(grants),
                }
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in (
        "inventory",
        "checksum",
        "tenant",
        "token-file",
        "security-url",
        "journal",
    ):
        parser.add_argument("--" + argument, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--connectors", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception:
        # Provider bodies and exception strings can include tokens/DSNs. The
        # private journal supplies exact tuples for operator reconciliation.
        parser.exit(
            1, "Provisioning stopped; reconcile private journal before retry.\n"
        )


if __name__ == "__main__":
    main()
