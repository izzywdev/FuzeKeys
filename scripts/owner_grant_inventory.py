"""Read-only inventory of instance owner grants. Never applies policy or grants."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

# Select only identifiers; never fetch PII, encrypted values or Vault paths.
INVENTORY_SQL = """
WITH owned AS (
 SELECT 'Identity' AS resource_type, 'identity:' || CAST(id AS TEXT) AS resource_key,
        user_id FROM identities
 UNION ALL
 SELECT 'Account', 'account:' || CAST(a.id AS TEXT), i.user_id
 FROM accounts a LEFT JOIN identities i ON i.id = a.identity_id
 UNION ALL
 SELECT 'VaultAsset', 'api-credential:' || CAST(c.id AS TEXT), i.user_id
 FROM api_credentials c LEFT JOIN identities i ON i.id = c.identity_id
)
SELECT o.resource_type, o.resource_key, o.user_id, p.subject, p.tenant, p.verified_at
FROM owned o LEFT JOIN platform_identities p ON p.user_id = o.user_id
ORDER BY o.resource_type, o.resource_key
"""


def build_inventory(rows):
    grants = []
    rejected = []
    seen = set()
    for row in rows:
        key = (row["resource_type"], row["resource_key"])
        if key in seen:
            raise ValueError("Duplicate resource ownership mapping")
        seen.add(key)
        subject, tenant = row["subject"], row["tenant"]
        if (
            row["user_id"] is None
            or not row["verified_at"]
            or not isinstance(subject, str)
            or not subject.strip()
            or not isinstance(tenant, str)
            or not tenant.strip()
            or subject.strip() != subject
            or tenant.strip() != tenant
        ):
            rejected.append(
                {
                    "resource_type": key[0],
                    "resource_key": key[1],
                    "reason": "orphan_or_unverified_platform_binding",
                }
            )
            continue
        grants.append(
            {
                "subject": subject,
                "tenant": tenant,
                "resource_type": "fuzekeys_" + key[0],
                "resource_key": key[1],
                "role": "owner",
            }
        )
    grants.sort(key=lambda grant: (grant["resource_type"], grant["resource_key"]))
    rejected.sort(key=lambda row: (row["resource_type"], row["resource_key"]))
    payload = {"grants": grants, "rejected": rejected}
    checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    metadata = {
        "checksum_sha256": checksum,
        "resource_count": len(seen),
        "verified_resource_count": len(grants),
        "rejected_count": len(rejected),
        "requires_current_membership_verification": True,
    }
    if rejected:
        # All-or-nothing: no partial grant set is approved when any owner is unknown.
        return {
            "mode": "dry-run",
            "ready": False,
            "grants": [],
            "rejected": rejected,
            **metadata,
        }
    return {
        "mode": "dry-run",
        "ready": True,
        "grants": grants,
        "rejected": [],
        **metadata,
    }


async def read_inventory(url):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                result = await connection.execute(text(INVENTORY_SQL))
                return build_inventory(result.mappings())
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL_ASYNC") or os.environ.get("DATABASE_URL")
    if not url:
        parser.error("DATABASE_URL_ASYNC or DATABASE_URL is required")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        parser.error("Only PostgreSQL asyncpg URLs are supported")
    inventory = asyncio.run(read_inventory(url))
    # Inventory contains subject identifiers; create private file and refuse overwrite.
    descriptor = os.open(Path(args.output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as target:
        json.dump(inventory, target, indent=2)
        target.write("\n")
    return 0 if inventory["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
