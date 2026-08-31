#!/usr/bin/env python3
"""Self-tests for gate-a2a.

MODELLED ON test_gate_identifier.py, and the modelling is the point: every case below
asserts the gate **FAILS** on a reconstruction of a real defect. A gate proven only on a
clean tree is the exact thing this family keeps shipping — `gate-toolchain` had a job in
7 repos and its script in 1, so six reported green while enforcing nothing.

The clean-tree case is here too, but it is ONE test out of many, deliberately.

Every fixture is synthetic. No test reads, writes, prints or asserts on a secret VALUE —
`_sealed()` writes a placeholder ciphertext string and the assertions only ever look at
KEY NAMES, mirroring the gate's own boundary.

Registry-touching checks always run with --offline so the suite is hermetic; I2 (the
live pullability lookup) is covered by test_registry_* against a stubbed resolver.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gate_a2a  # noqa: E402

HAVE_YAML = gate_a2a._yaml_load.__module__ is not None
try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="gate-a2a-")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)

    # ---------------------------------------------------------------- fixture helpers
    def w(self, rel, text):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def manifest(self, **a2a):
        block = {"enabled": True, "servingRoles": ["demo"], "entryRole": "demo"}
        block.update(a2a)
        self.w(".fuze/manifest.json", json.dumps({"repo": "izzywdev/Demo", "a2a": block}))

    def role(self, name="demo", skills=None):
        self.w(f"agent-templates/roles/{name}/role.json",
               json.dumps({"role": name, "name": f"Demo {name}", "skills": skills or []}))

    def skill(self, name):
        self.w(f".claude/skills/{name}/SKILL.md", f"# {name}\n")

    def claude_md(self):
        self.w("CLAUDE.md", "# Demo\n")

    def values(self, rel="helm/demo/values.yaml", a2a=None):
        body = {"a2a": a2a if a2a is not None else self.good_a2a()}
        self.w(rel, yaml.safe_dump(body, sort_keys=False))

    def good_a2a(self):
        return {
            "enabled": True,
            "image": {"repository": gate_a2a.SHARED_IMAGE, "tag": "abc123", "pullPolicy": "IfNotPresent"},
            "service": {"type": "ClusterIP", "port": 8080},
            "inClusterUrl": "http://a2a-demo.demo.svc.cluster.local:8080/rpc",
            "auth": {"oidcIssuerUrl": "https://idp.example/o/demo/", "audience": "a2a"},
            "tenants": [{"tenant": "Demo", "repo": "izzywdev/Demo", "ref": "main",
                         "enabled": True, "entryRole": "demo"}],
        }

    def _sealed(self, name, keys):
        """A SealedSecret fixture. The 'ciphertext' is a placeholder — never a secret."""
        self.w(f"deploy/sealed-secrets/{name}.yaml", yaml.safe_dump({
            "apiVersion": "bitnami.com/v1alpha1", "kind": "SealedSecret",
            "metadata": {"name": name},
            "spec": {"encryptedData": {k: "AgB-PLACEHOLDER-NOT-A-SECRET" for k in keys}},
        }, sort_keys=False))

    def policy(self, obj):
        self.w("governance/a2a-policy.json", json.dumps(obj))

    def run_gate(self, *flags):
        return gate_a2a.main([self.repo, "--offline", *flags])

    def healthy(self):
        """A fully-wired repo — the baseline every failure test perturbs by ONE thing."""
        self.manifest()
        self.role(skills=["demo-skill"])
        self.skill("demo-skill")
        self.claude_md()
        self.values()


@unittest.skipUnless(HAVE_YAML, "PyYAML required for values-file fixtures")
class TestPassesWhenActuallyCorrect(Base):
    def test_healthy_repo_passes(self):
        self.healthy()
        self.assertEqual(self.run_gate(), 0)


class TestSkipIsOnlyEverAnAbsence(Base):
    def test_no_manifest_at_all_skips(self):
        # No .fuze/manifest.json => no declared surface => honest skip.
        self.assertEqual(gate_a2a.main([self.repo, "--offline"]), 0)

    def test_enabled_false_skips(self):
        self.w(".fuze/manifest.json", json.dumps({"repo": "x", "a2a": {"enabled": False}}))
        self.assertEqual(gate_a2a.main([self.repo, "--offline"]), 0)

    def test_ENABLED_WITH_NOTHING_BUILT_FAILS(self):
        """The headline case. Declared surface + nothing deployed must RED, not skip.

        Measured 2026-08-23: 4 of 8 a2a-enabled repos were exactly here.
        """
        self.manifest()
        self.role(skills=["demo-skill"])
        self.skill("demo-skill")
        self.claude_md()
        self.assertEqual(self.run_gate(), 1)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestImage(Base):
    def test_forked_image_repository_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["image"]["repository"] = "ghcr.io/izzywdev/demo-own-a2a"
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--image"), 1)

    def test_prod_pinning_latest_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["image"]["tag"] = "latest"
        self.values(rel="helm/demo/values-prod.yaml", a2a=a)
        self.assertEqual(self.run_gate("--image"), 1)

    def test_single_tenant_without_inClusterUrl_fails(self):
        """The pod that starts, goes green, and publishes the WRONG endpoint."""
        self.healthy()
        a = self.good_a2a()
        del a["inClusterUrl"]
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--image"), 1)

    def test_undeclared_image_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["image"] = {}
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--image"), 1)


class TestRegistryLookupIsReal(Base):
    """I2 must be an ANSWER from the registry, not a grep for a `ghcr.io/` string."""

    def test_404_tag_is_fatal(self):
        orig = gate_a2a.registry_manifest_status
        gate_a2a.registry_manifest_status = lambda r, t, timeout=15: (404, "HTTP 404")
        self.addCleanup(setattr, gate_a2a, "registry_manifest_status", orig)
        docs = [("helm/demo/values.yaml", {"a2a": {
            "image": {"repository": gate_a2a.SHARED_IMAGE, "tag": "nope"}, "tenants": []}})]
        out = gate_a2a.check_image(self.repo, {}, gate_a2a.DEFAULT_POLICY, docs, online=True)
        self.assertTrue(any(f.code == "I2" and f.fatal for f in out))

    def test_200_tag_passes(self):
        orig = gate_a2a.registry_manifest_status
        gate_a2a.registry_manifest_status = lambda r, t, timeout=15: (200, "ok")
        self.addCleanup(setattr, gate_a2a, "registry_manifest_status", orig)
        docs = [("helm/demo/values.yaml", {"a2a": {
            "image": {"repository": gate_a2a.SHARED_IMAGE, "tag": "abc"}, "tenants": []}})]
        out = gate_a2a.check_image(self.repo, {}, gate_a2a.DEFAULT_POLICY, docs, online=True)
        self.assertFalse([f for f in out if f.code == "I2"])

    def test_unreachable_registry_is_a_WARNING_not_a_silent_pass(self):
        orig = gate_a2a.registry_manifest_status
        gate_a2a.registry_manifest_status = lambda r, t, timeout=15: (None, "registry unreachable")
        self.addCleanup(setattr, gate_a2a, "registry_manifest_status", orig)
        docs = [("helm/demo/values.yaml", {"a2a": {
            "image": {"repository": gate_a2a.SHARED_IMAGE, "tag": "abc"}, "tenants": []}})]
        out = gate_a2a.check_image(self.repo, {}, gate_a2a.DEFAULT_POLICY, docs, online=True)
        i2 = [f for f in out if f.code == "I2"]
        self.assertTrue(i2, "an unverified image must be REPORTED, never silently fine")
        self.assertFalse(i2[0].fatal)
        self.assertIn("UNVERIFIED", i2[0].message)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestSkills(Base):
    def test_named_skill_that_does_not_resolve_fails(self):
        self.healthy()
        self.role(skills=["demo-skill", "ghost-skill"])
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_named_skill_fails_EVEN_UNDER_THE_RATCHET(self):
        """S1 is never ratcheted. A NEW violation must always red."""
        self.healthy()
        self.role(skills=["ghost-skill"])
        self.policy({"skills": {"adoption": "warn",
                                "ratchet": {"knownUnadopted": ["izzywdev/Demo"]}}})
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_card_skill_id_in_bundle_field_fails(self):
        """The live fuzekeys defect: `keys.grant` is a CARD id, not a bundle name."""
        self.healthy()
        self.role(skills=["keys.grant"])
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_zero_skills_fails_with_NO_policy_file(self):
        """Absence of the ratchet file is NOT permission — the default is `fail`."""
        self.healthy()
        self.role(skills=[])
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_zero_skills_is_soft_ONLY_for_a_repo_the_ratchet_NAMES(self):
        self.healthy()
        self.role(skills=[])
        self.policy({"skills": {"adoption": "warn",
                                "ratchet": {"knownUnadopted": ["izzywdev/Demo"]}}})
        self.assertEqual(self.run_gate("--skills"), 0)

    def test_zero_skills_still_fails_for_a_repo_the_ratchet_does_NOT_name(self):
        """`warn` must not be a fleet-wide opt-out; an unlisted repo stays hard."""
        self.healthy()
        self.role(skills=[])
        self.policy({"skills": {"adoption": "warn",
                                "ratchet": {"knownUnadopted": ["izzywdev/SomeoneElse"]}}})
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_malformed_policy_does_not_grant_the_lenient_mode(self):
        self.healthy()
        self.role(skills=[])
        self.w("governance/a2a-policy.json", "{ this is not json")
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_missing_serving_role_json_fails(self):
        self.healthy()
        os.remove(os.path.join(self.repo, "agent-templates/roles/demo/role.json"))
        self.assertEqual(self.run_gate("--skills"), 1)

    def test_missing_root_CLAUDE_md_fails(self):
        self.healthy()
        os.remove(os.path.join(self.repo, "CLAUDE.md"))
        self.assertEqual(self.run_gate("--skills"), 1)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestCreds(Base):
    def test_unresolvable_secretRef_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "a2a-card-signing", "key": "jws.key"},
                            "keyId": "a2a-v1"}
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_resolvable_secretRef_passes(self):
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "a2a-card-signing", "key": "jws.key"},
                            "keyId": "a2a-v1"}
        self.values(a2a=a)
        self._sealed("a2a-card-signing", ["jws.key"])
        self.assertEqual(self.run_gate("--creds"), 0)

    def test_sealed_secret_present_but_WRONG_KEY_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "a2a-card-signing", "key": "jws.key"}}
        self.values(a2a=a)
        self._sealed("a2a-card-signing", ["some-other-key"])
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_cardSigning_without_keySecretRef_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keyId": "a2a-v1"}
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_auth_without_issuer_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["auth"] = {"audience": "a2a"}
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_single_tenant_pod_with_no_auth_at_all_fails(self):
        self.healthy()
        a = self.good_a2a()
        del a["auth"]
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_externallyProvisioned_WITHOUT_a_reason_still_fails(self):
        """An opt-out with no owner is ignored — same rule as platformAuth.enforce."""
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "vault-managed", "key": "jws.key"}}
        self.values(a2a=a)
        self.policy({"creds": {"sealedSecretDirs": ["deploy/sealed-secrets"],
                               "externallyProvisioned": {"vault-managed": ""}}})
        self.assertEqual(self.run_gate("--creds"), 1)

    def test_externallyProvisioned_WITH_a_reason_passes(self):
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "vault-managed", "key": "jws.key"}}
        self.values(a2a=a)
        self.policy({"creds": {"sealedSecretDirs": ["deploy/sealed-secrets"],
                               "externallyProvisioned": {
                                   "vault-managed": "provisioned by FuzeInfra external-secrets"}}})
        self.assertEqual(self.run_gate("--creds"), 0)

    def test_gate_never_surfaces_a_secret_VALUE(self):
        """The 2026-07-29 leak rule, asserted mechanically.

        A SealedSecret's ciphertext must never appear in gate output, even though the
        gate opens the file to read its KEY NAMES.
        """
        import io
        from contextlib import redirect_stdout
        self.healthy()
        a = self.good_a2a()
        a["cardSigning"] = {"keySecretRef": {"name": "a2a-card-signing", "key": "jws.key"}}
        self.values(a2a=a)
        self.w("deploy/sealed-secrets/a2a-card-signing.yaml", yaml.safe_dump({
            "apiVersion": "bitnami.com/v1alpha1", "kind": "SealedSecret",
            "metadata": {"name": "a2a-card-signing"},
            "spec": {"encryptedData": {"jws.key": "SENTINEL-CIPHERTEXT-MUST-NOT-BE-PRINTED"}},
        }))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.run_gate()
        self.assertNotIn("SENTINEL-CIPHERTEXT-MUST-NOT-BE-PRINTED", buf.getvalue())


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestEnv(Base):
    def test_inline_env_value_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["tenants"][0]["env"] = [{"name": "API_TOKEN", "value": "hunter2"}]
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--env"), 1)

    def test_env_with_no_valueFrom_fails(self):
        self.healthy()
        a = self.good_a2a()
        a["tenants"][0]["env"] = [{"name": "API_TOKEN"}]
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--env"), 1)

    def test_env_from_secretRef_passes(self):
        self.healthy()
        a = self.good_a2a()
        a["tenants"][0]["env"] = [
            {"name": "API_TOKEN", "valueFrom": {"name": "demo-a2a", "key": "api-token"}}]
        self.values(a2a=a)
        self._sealed("demo-a2a", ["api-token"])
        self.assertEqual(self.run_gate("--env", "--creds"), 0)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestMemoryStaysAClient(Base):
    def test_chroma_SERVER_in_the_a2a_chart_fails(self):
        """PYSEC-2026-311 is a SERVER advisory; the pod must stay a client."""
        self.healthy()
        self.w("helm/demo/templates/a2a.yaml",
               "spec:\n  containers:\n    - name: chroma\n      image: chromadb/chroma:0.5.0\n")
        self.assertEqual(self.run_gate("--memory"), 1)

    def test_client_only_chart_passes(self):
        self.healthy()
        self.w("helm/demo/templates/a2a.yaml",
               "spec:\n  containers:\n    - name: a2a\n"
               f"      image: {gate_a2a.SHARED_IMAGE}:abc123\n"
               "      env:\n        - name: CHROMA_HOST\n          value: chroma.fuzeinfra\n")
        self.assertEqual(self.run_gate("--memory"), 0)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestApiSurface(Base):
    def test_raw_rest_fallback_is_REFUSED(self):
        self.healthy()
        a = self.good_a2a()
        a["tenants"][0]["restBaseUrl"] = "http://demo-backend.demo.svc.cluster.local:3000"
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--api-surface"), 1)

    def test_mcp_only_passes(self):
        self.healthy()
        self.assertEqual(self.run_gate("--api-surface"), 0)


class TestForks(Base):
    def test_a_second_a2a_Dockerfile_fails(self):
        self.manifest()
        self.role(skills=["demo-skill"])
        self.skill("demo-skill")
        self.claude_md()
        self.w("deploy/a2a/Dockerfile",
               "FROM python:3.12-slim\nCOPY a2a/ /app/a2a/\nCMD [\"python\", \"-m\", \"a2a.runtime\"]\n")
        self.assertEqual(self.run_gate("--forks"), 1)

    def test_an_ordinary_Dockerfile_is_not_a_fork(self):
        self.manifest()
        self.role(skills=["demo-skill"])
        self.skill("demo-skill")
        self.claude_md()
        self.w("Dockerfile", "FROM node:24-alpine\nCMD [\"node\", \"server.js\"]\n")
        self.assertEqual(self.run_gate("--forks"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(HAVE_YAML, "PyYAML required")
class TestOverlaysAreNotFalsePositives(Base):
    """A gate that reds on correct config is a gate people switch off.

    fuzesales/values-contabo.yaml is literally `a2a: {enabled: false}`. Reporting a
    missing image on a file that was never meant to declare one is noise, and noise is
    how a real finding gets ignored.
    """

    def test_disabled_overlay_is_not_checked_as_a_declaration(self):
        """The exact fuzesales/values-contabo.yaml shape."""
        self.healthy()
        self.w("helm/demo/values-contabo.yaml", yaml.safe_dump({"a2a": {"enabled": False}}))
        self.assertEqual(self.run_gate(), 0)

    def test_a_FULL_declaration_shipping_enabled_false_IS_still_checked(self):
        """`enabled: false` must not be an escape hatch.

        A chart's own values.yaml ships the server disabled by default (the dev shape)
        while carrying the full declaration — a2a-shared/values.yaml does exactly that.
        Skipping on `enabled: false` would stop checking the repos that HAVE a pod.
        """
        self.healthy()
        a = self.good_a2a()
        a["enabled"] = False
        del a["inClusterUrl"]
        self.values(a2a=a)
        self.assertEqual(self.run_gate("--image"), 1)

    def test_partial_overlay_with_neither_image_nor_tenants_is_skipped(self):
        self.healthy()
        self.w("helm/demo/values-staging.yaml",
               yaml.safe_dump({"a2a": {"service": {"port": 8081}}}))
        self.assertEqual(self.run_gate(), 0)

    def test_an_overlay_that_DOES_declare_an_image_is_still_checked(self):
        self.healthy()
        self.w("helm/demo/values-prod.yaml", yaml.safe_dump(
            {"a2a": {"image": {"repository": gate_a2a.SHARED_IMAGE, "tag": "latest"}}}))
        self.assertEqual(self.run_gate("--image"), 1)
