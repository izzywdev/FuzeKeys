"""Render the real chart: Vault upgrades must preserve immutable claim metadata."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CHART = Path(__file__).resolve().parents[2] / "deploy/helm/fuzekeys"
HELM = os.environ.get("HELM_BINARY", "helm")
LIVE_LABELS = {
    "app.kubernetes.io/instance": "fuzekeys",
    "app.kubernetes.io/managed-by": "Helm",
    "app.kubernetes.io/name": "fuzekeys",
    "app.kubernetes.io/part-of": "fuzekeys",
    "app.kubernetes.io/version": "0.1.12",
    "fuzekeys.io/environment": "prod",
    "helm.sh/chart": "fuzekeys-0.1.15",
}


def render(chart=CHART, production=False, extra=()):
    args = [HELM, "template", "fuzekeys", str(chart)]
    if production:
        args += ["-f", str(chart / "values-contabo.yaml")]
    else:
        args += ["--set", "vault.enabled=true"]
    output = subprocess.check_output(args + list(extra), text=True)
    return next(
        resource
        for resource in yaml.safe_load_all(output)
        if resource
        and resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == "fuzekeys-vault"
    )


def immutable_spec(resource):
    # Kubernetes permits template/replicas/etc. updates, not these fields.
    return {
        key: resource["spec"].get(key)
        for key in (
            "serviceName",
            "selector",
            "volumeClaimTemplates",
            "podManagementPolicy",
        )
    }


class VaultClaimMetadataTests(unittest.TestCase):
    def test_production_matches_live_claim(self):
        claim = render(production=True)["spec"]["volumeClaimTemplates"][0]
        self.assertEqual(
            claim["metadata"], {"name": "vault-file", "labels": LIVE_LABELS}
        )
        self.assertEqual(
            claim["spec"],
            {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": "local-path",
                "resources": {"requests": {"storage": "1Gi"}},
            },
        )

    def test_new_installations_use_only_stable_labels(self):
        labels = render()["spec"]["volumeClaimTemplates"][0]["metadata"]["labels"]
        self.assertEqual(
            labels,
            {
                "app.kubernetes.io/name": "fuzekeys",
                "app.kubernetes.io/instance": "fuzekeys",
                "app.kubernetes.io/component": "vault",
            },
        )

    def test_future_versions_preserve_all_immutable_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "fuzekeys"
            shutil.copytree(CHART, chart)
            metadata = yaml.safe_load((chart / "Chart.yaml").read_text())
            metadata.update(version="9.8.7", appVersion="9.8.6")
            (chart / "Chart.yaml").write_text(yaml.safe_dump(metadata))
            for production in (False, True):
                with self.subTest(production=production):
                    before = render(production=production)
                    after = render(chart=chart, production=production)
                    self.assertEqual(immutable_spec(before), immutable_spec(after))
                    self.assertNotEqual(
                        before["spec"]["template"]["metadata"]["labels"][
                            "helm.sh/chart"
                        ],
                        after["spec"]["template"]["metadata"]["labels"][
                            "helm.sh/chart"
                        ],
                    )

    def test_claim_override_is_exact_not_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "values.yaml"
            override.write_text(
                yaml.safe_dump(
                    {
                        "vault": {
                            "persistence": {
                                "claimLabels": {"legacy.example/installed": "original"}
                            }
                        }
                    }
                )
            )
            claim = render(extra=("-f", str(override)))["spec"]["volumeClaimTemplates"][
                0
            ]
            self.assertEqual(
                claim["metadata"]["labels"], {"legacy.example/installed": "original"}
            )

    def test_nonpersistent_vault_has_no_claim_template(self):
        resource = render(extra=("--set", "vault.persistence.enabled=false"))
        self.assertNotIn("volumeClaimTemplates", resource["spec"])

    def test_no_destructive_replacement_annotation(self):
        resource = render(production=True)
        self.assertNotIn(
            "argocd.argoproj.io/sync-options",
            resource["metadata"].get("annotations", {}),
        )
        self.assertEqual(resource["spec"]["serviceName"], "fuzekeys-vault")


if __name__ == "__main__":
    unittest.main()
