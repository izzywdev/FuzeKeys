import importlib.util
import sqlite3
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "owner_grant_inventory.py"
spec = importlib.util.spec_from_file_location("inventory", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OwnerInventoryTests(unittest.TestCase):
    def row(self, **changes):
        row = dict(
            resource_type="Identity",
            resource_key="identity:3",
            user_id=7,
            subject="platform-subject",
            tenant="verified-tenant",
            verified_at="date",
        )
        row.update(changes)
        return row

    def test_exact_instance_owner(self):
        result = module.build_inventory([self.row()])
        self.assertTrue(result["ready"])
        self.assertEqual(
            result["grants"],
            [
                dict(
                    subject="platform-subject",
                    tenant="verified-tenant",
                    resource_type="fuzekeys_Identity",
                    resource_key="identity:3",
                    role="owner",
                )
            ],
        )

    def test_unlinked_or_orphan_aborts_entire_set(self):
        for changes in [
            dict(subject=None),
            dict(tenant=None),
            dict(verified_at=None),
            dict(user_id=None),
            dict(subject="   "),
            dict(tenant=" bad"),
        ]:
            with self.subTest(changes=changes):
                result = module.build_inventory(
                    [self.row(), self.row(resource_key="identity:4", **changes)]
                )
                self.assertFalse(result["ready"])
                self.assertEqual(result["grants"], [])
                self.assertEqual(len(result["rejected"]), 1)

    def test_duplicate_binding_is_rejected(self):
        with self.assertRaises(ValueError):
            module.build_inventory([self.row(), self.row(subject="different")])

    def test_multiple_resource_namespaces_do_not_collide(self):
        rows = [
            self.row(),
            self.row(resource_type="Account", resource_key="account:3"),
            self.row(resource_type="VaultAsset", resource_key="api-credential:3"),
        ]
        self.assertEqual(len(module.build_inventory(rows)["grants"]), 3)

    def test_sql_inherits_exact_foreign_identity_owner_and_rejects_orphans(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
        CREATE TABLE identities(id INTEGER, user_id INTEGER);
        CREATE TABLE accounts(id INTEGER, identity_id INTEGER);
        CREATE TABLE api_credentials(id INTEGER, identity_id INTEGER);
        CREATE TABLE platform_identities(user_id INTEGER, subject TEXT, tenant TEXT, verified_at TEXT);
        INSERT INTO identities VALUES(1, 10), (2, 20);
        INSERT INTO platform_identities VALUES(10, 'alice', 'tenant-a', 'date'), (20, 'bob', 'tenant-b', 'date');
        INSERT INTO accounts VALUES(7, 2);
        INSERT INTO api_credentials VALUES(8, 1);
        """
        )
        result = module.build_inventory(db.execute(module.INVENTORY_SQL))
        owners = {
            g["resource_key"]: (g["subject"], g["tenant"]) for g in result["grants"]
        }
        self.assertEqual(owners["account:7"], ("bob", "tenant-b"))
        self.assertEqual(owners["api-credential:8"], ("alice", "tenant-a"))
        db.execute("INSERT INTO accounts VALUES(9, 999)")
        result = module.build_inventory(db.execute(module.INVENTORY_SQL))
        self.assertFalse(result["ready"])
        self.assertEqual(result["grants"], [])
        self.assertEqual(result["rejected"][0]["resource_key"], "account:9")
        db.close()

    def test_checksum_deterministic_and_membership_still_required(self):
        rows = [self.row(), self.row(resource_key="identity:4")]
        first = module.build_inventory(rows)
        second = module.build_inventory(reversed(rows))
        self.assertEqual(first["checksum_sha256"], second["checksum_sha256"])
        self.assertEqual(first["resource_count"], 2)
        self.assertTrue(first["requires_current_membership_verification"])

    def test_queries_are_read_only_and_do_not_select_secrets(self):
        self.assertNotIn("encrypted_", module.INVENTORY_SQL)
        self.assertNotIn("openbao_path", module.INVENTORY_SQL)
        self.assertIn("LEFT JOIN identities", module.INVENTORY_SQL)
        self.assertIn("LEFT JOIN platform_identities", module.INVENTORY_SQL)


if __name__ == "__main__":
    unittest.main()
