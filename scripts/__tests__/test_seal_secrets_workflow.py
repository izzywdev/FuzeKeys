"""Provisioning safety checks; tools are mocked and no credentials are retrieved."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / '.github/workflows/seal-secrets.yml'


class SealSecretsWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
        cls.steps = cls.doc['jobs']['seal']['steps']
        cls.seal = next(s for s in cls.steps if s.get('name', '').startswith('Seal a2a-'))

    def test_target_checks_out_master_and_limits_files(self):
        target = self.doc['on']['workflow_dispatch']['inputs']['target']
        self.assertEqual(self.doc['permissions'], {'contents': 'read'})
        self.assertEqual(target['default'], 'all')
        self.assertEqual(target['options'], ['all', 'a2a-only'])
        self.assertEqual(self.steps[0]['with']['ref'], 'master')
        self.assertEqual(self.steps[0]['with']['persist-credentials'], 'false')
        mint = next(s for s in self.steps if s.get('id') == 'app_token')
        self.assertNotIn('continue-on-error', mint)
        self.assertEqual(mint['with']['permission-contents'], 'write')
        self.assertEqual(mint['with']['permission-pull-requests'], 'write')
        for step in self.steps:
            if step.get('name', '').startswith('Seal ') and step is not self.seal:
                self.assertEqual(step['if'], "inputs.target != 'a2a-only'")
        pr = self.steps[-1]['with']
        self.assertEqual(pr['base'], 'master')
        self.assertEqual(pr['token'], '${{ steps.app_token.outputs.token }}')
        self.assertIn('chore/seal-a2a-provider-anthropic', pr['branch'])
        self.assertIn('deploy/argocd/sealed/a2a-provider-anthropic.yaml', pr['add-paths'])
        self.assertEqual(pr['sign-commits'], 'true')

    def run_seal(self, key, existing=False, fail=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sealed = root / 'deploy/argocd/sealed'
            sealed.mkdir(parents=True)
            path = sealed / 'a2a-provider-anthropic.yaml'
            if existing:
                path.write_text('existing ciphertext')
            tools = root / 'bin'
            tools.mkdir()
            (tools / 'kubectl').write_text('#!/bin/bash\nprintf mock-secret\n')
            (tools / 'kubeseal').write_text('#!/bin/bash\ncat >/dev/null\n' + ('exit 2\n' if fail else 'printf mock-ciphertext\n'))
            for tool in tools.iterdir():
                tool.chmod(0o755)
            # All unrelated provider, datastore, and app credentials are absent.
            env = {'ANTHROPIC_API_KEY': key, 'PATH': str(tools) + ':' + os.environ['PATH']}
            result = subprocess.run(['bash', '-c', self.seal['run']], cwd=root, env=env, capture_output=True, text=True)
            self.assertNotIn('dummy-private-value', result.stdout + result.stderr)
            return result.returncode, path.read_text() if path.exists() else None

    def test_missing_or_whitespace_secret_fails_before_write(self):
        for value in ['', ' \n\t']:
            status, content = self.run_seal(value)
            self.assertNotEqual(status, 0)
            self.assertIsNone(content)

    def test_seals_nonempty_key(self):
        self.assertEqual(self.run_seal('dummy-private-value'), (0, 'mock-ciphertext'))

    def test_existing_ciphertext_never_rotates(self):
        self.assertEqual(self.run_seal('', existing=True), (0, 'existing ciphertext'))

    def test_sealing_failure_fails_job(self):
        status, _ = self.run_seal('dummy-private-value', fail=True)
        self.assertNotEqual(status, 0)


if __name__ == '__main__':
    unittest.main()
