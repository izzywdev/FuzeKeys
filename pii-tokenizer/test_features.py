"""pytest tests for Feature 1 (Atlassian patterns) and Feature 2 (LLM detect).

These tests exercise pii_vault._detect() and pii_vault._llm_detect() without
requiring a live Vault, Redis, Presidio, or Ollama instance.

Strategy:
- Import pii_vault with a fake Redis (monkeypatch redis.from_url before import).
- Patch pii_vault._post_json to control Presidio + Ollama responses.
- Patch pii_vault.LLM_PII_DETECTION and pii_vault._vault_encrypt/_vault_decrypt
  where tokenize() is exercised.
"""
import importlib
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Bootstrap: patch redis.from_url so pii_vault can be imported without a
# running Redis server.
# ---------------------------------------------------------------------------

def _make_fake_redis():
    fake = MagicMock()
    fake.get.return_value = None
    fake.hgetall.return_value = {}
    return fake


# Patch redis *before* importing pii_vault so the module-level `_r = redis.from_url(...)` call
# gets the fake. If pii_vault is already in sys.modules (e.g. from another test session),
# reload it so module-level code re-runs with the patch active.
_fake_redis_instance = _make_fake_redis()

import redis as _redis_module  # noqa: E402 — must be importable

_orig_from_url = _redis_module.from_url
_redis_module.from_url = lambda *a, **kw: _fake_redis_instance

# Force fresh import (or reload if already loaded).
if "pii_vault" in sys.modules:
    import pii_vault as pv  # noqa: E402
    importlib.reload(pv)
else:
    import pii_vault as pv  # noqa: E402

# Restore the real redis.from_url so unrelated code isn't affected.
_redis_module.from_url = _orig_from_url


# ---------------------------------------------------------------------------
# Helper: make _detect() skip Presidio (simulate unreachable) so we test only
# the regex / LLM paths in isolation.
# ---------------------------------------------------------------------------

def _presidio_unreachable(*args, **kwargs):
    raise ConnectionError("Presidio not running (expected in unit tests)")


# ===========================================================================
# Feature 1 — Atlassian key patterns
# ===========================================================================

class TestAtlassianPatterns(unittest.TestCase):
    """ATATT / ATCTT / ATBB family matched by SECRET_PATTERNS regex."""

    # Dummy tokens — these are NOT real credentials.
    ATATT_TOKEN = "ATATT3xFfGFOr7dummy_fake_token_for_unit_test_only_abcd1234EFGHijklMNOP=="
    ATCTT_TOKEN = "ATCTT3xFfGF_another_dummy_token_xyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456"
    ATBB_TOKEN  = "ATBB3xFfGFdummyBitbucketToken_fakefakefake00001111222233334444555566"

    def _detect_no_presidio(self, text):
        """Run _detect() with Presidio stubbed out (unreachable)."""
        with patch.object(pv, "_post_json", side_effect=_presidio_unreachable):
            return pv._detect(text)

    def test_atatt_detected_by_detect(self):
        spans = self._detect_no_presidio(f"Use token: {self.ATATT_TOKEN} to call the API.")
        types = [t for _, _, t in spans]
        self.assertTrue(
            any("APIKEY" in t for t in types),
            f"Expected APIKEY span for ATATT token, got: {types}",
        )

    def test_atctt_detected_by_detect(self):
        spans = self._detect_no_presidio(f"Token: {self.ATCTT_TOKEN}")
        types = [t for _, _, t in spans]
        self.assertTrue(any("APIKEY" in t for t in types))

    def test_atbb_detected_by_detect(self):
        spans = self._detect_no_presidio(f"Token: {self.ATBB_TOKEN}")
        types = [t for _, _, t in spans]
        self.assertTrue(any("APIKEY" in t for t in types))

    def test_atatt_span_covers_full_token(self):
        text = f"start {self.ATATT_TOKEN} end"
        spans = self._detect_no_presidio(text)
        apikey_spans = [(s, e) for s, e, t in spans if "APIKEY" in t]
        self.assertTrue(apikey_spans, "No APIKEY span found")
        start, end = apikey_spans[0]
        self.assertEqual(text[start:end], self.ATATT_TOKEN)

    def test_non_atlassian_not_matched_by_atlassian_pattern(self):
        # A plain word starting with AT but not matching ATXTT structure should not match.
        text = "ATTENTION: please review this"
        spans = self._detect_no_presidio(text)
        apikey_spans = [(s, e, t) for s, e, t in spans if "APIKEY" in t]
        self.assertFalse(apikey_spans, f"False positive: {apikey_spans}")

    def test_atlassian_pattern_in_secret_patterns_list(self):
        """Verify the Atlassian patterns are present in SECRET_PATTERNS."""
        import re
        atlassian_patterns = [
            pat for label, pat in pv.SECRET_PATTERNS
            if label == "APIKEY" and (
                pat.pattern.startswith(r"AT[A-Z]TT") or
                pat.pattern.startswith(r"ATBB")
            )
        ]
        self.assertGreaterEqual(
            len(atlassian_patterns), 2,
            "Expected at least two Atlassian patterns (AT[A-Z]TT and ATBB)",
        )

    def test_prefix_for_atlassian_secret(self):
        prefix = pv._prefix_for("SECRET:APIKEY")
        self.assertEqual(prefix, "APIKEY")


# ===========================================================================
# Feature 2 — LLM second-stage detection
# ===========================================================================

class TestLLMDetect(unittest.TestCase):
    """_llm_detect() with _post_json monkeypatched — no live Ollama."""

    def _fake_ollama_response(self, pii_items):
        """Return a fake Ollama /api/generate response embedding the given pii list."""
        return {"response": json.dumps({"pii": pii_items})}

    # ------------------------------------------------------------------
    # Flag=off: must return [] regardless
    # ------------------------------------------------------------------

    def test_llm_detect_disabled_returns_empty(self):
        with patch.object(pv, "LLM_PII_DETECTION", False):
            result = pv._llm_detect("John Smith's email is john@example.com")
        self.assertEqual(result, [])

    def test_llm_detect_disabled_never_calls_post_json(self):
        with patch.object(pv, "LLM_PII_DETECTION", False), \
             patch.object(pv, "_post_json") as mock_post:
            pv._llm_detect("some text")
        mock_post.assert_not_called()

    # ------------------------------------------------------------------
    # Flag=on, fake Ollama response
    # ------------------------------------------------------------------

    def test_llm_detect_person_span(self):
        text = "The user Alice Johnson submitted a request."
        fake_resp = self._fake_ollama_response([{"type": "PERSON", "value": "Alice Johnson"}])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value=fake_resp):
            spans = pv._llm_detect(text)
        self.assertTrue(spans, "Expected at least one span")
        starts = {s for s, e, t in spans}
        ends = {e for s, e, t in spans}
        self.assertIn(text.index("Alice Johnson"), starts)
        self.assertIn(text.index("Alice Johnson") + len("Alice Johnson"), ends)
        types = [t for _, _, t in spans]
        self.assertTrue(any("PERSON" in t for t in types))

    def test_llm_detect_spans_use_llm_prefix(self):
        text = "Contact Bob at 555-0100."
        fake_resp = self._fake_ollama_response([{"type": "PHONE_NUMBER", "value": "555-0100"}])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value=fake_resp):
            spans = pv._llm_detect(text)
        types = [t for _, _, t in spans]
        self.assertTrue(all(t.startswith("LLM:") for t in types),
                        f"Expected all types to start with LLM:, got {types}")

    def test_llm_detect_multiple_occurrences(self):
        text = "Alice called Alice at home."
        fake_resp = self._fake_ollama_response([{"type": "PERSON", "value": "Alice"}])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value=fake_resp):
            spans = pv._llm_detect(text)
        # "Alice" appears twice in the text
        self.assertEqual(len(spans), 2, f"Expected 2 spans for two occurrences, got {spans}")

    def test_llm_detect_value_not_in_text_produces_no_span(self):
        text = "No relevant PII here."
        fake_resp = self._fake_ollama_response([{"type": "PERSON", "value": "Charlie Brown"}])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value=fake_resp):
            spans = pv._llm_detect(text)
        self.assertEqual(spans, [])

    def test_llm_detect_empty_pii_list(self):
        text = "No PII in this text whatsoever."
        fake_resp = self._fake_ollama_response([])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value=fake_resp):
            spans = pv._llm_detect(text)
        self.assertEqual(spans, [])

    def test_llm_detect_fail_open_on_connection_error(self):
        """Ollama down -> _llm_detect returns [] (never raises)."""
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", side_effect=ConnectionError("Ollama down")):
            result = pv._llm_detect("John Smith 555-1234")
        self.assertEqual(result, [])

    def test_llm_detect_fail_open_on_json_error(self):
        """Malformed Ollama response -> [] (never raises)."""
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", return_value={"response": "not json!"}):
            result = pv._llm_detect("some text")
        self.assertEqual(result, [])

    def test_llm_detect_skips_overlong_text(self):
        """Text longer than LLM_PII_MAX_CHARS is skipped."""
        long_text = "a" * (pv.LLM_PII_MAX_CHARS + 1)
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json") as mock_post:
            result = pv._llm_detect(long_text)
        self.assertEqual(result, [])
        mock_post.assert_not_called()

    # ------------------------------------------------------------------
    # _prefix_for strips LLM: prefix
    # ------------------------------------------------------------------

    def test_prefix_for_strips_llm_prefix_person(self):
        self.assertEqual(pv._prefix_for("LLM:PERSON"), "NAME")

    def test_prefix_for_strips_llm_prefix_address(self):
        self.assertEqual(pv._prefix_for("LLM:ADDRESS"), "ADDR")

    def test_prefix_for_strips_llm_prefix_dob(self):
        self.assertEqual(pv._prefix_for("LLM:DATE_OF_BIRTH"), "DOB")

    def test_prefix_for_strips_llm_prefix_ip(self):
        self.assertEqual(pv._prefix_for("LLM:IP_ADDRESS"), "IP")

    def test_prefix_for_strips_llm_prefix_password(self):
        self.assertEqual(pv._prefix_for("LLM:PASSWORD"), "PWD")

    def test_prefix_for_strips_llm_prefix_username(self):
        self.assertEqual(pv._prefix_for("LLM:USERNAME"), "USER")

    def test_prefix_for_strips_llm_prefix_bank(self):
        self.assertEqual(pv._prefix_for("LLM:BANK_ACCOUNT"), "BANK")

    def test_prefix_for_strips_llm_prefix_passport(self):
        self.assertEqual(pv._prefix_for("LLM:PASSPORT"), "PASSPORT")

    def test_prefix_for_strips_llm_prefix_dl(self):
        self.assertEqual(pv._prefix_for("LLM:DRIVER_LICENSE"), "DL")

    # ------------------------------------------------------------------
    # detect() integrates LLM spans
    # ------------------------------------------------------------------

    def test_detect_integrates_llm_spans(self):
        """_detect() calls _llm_detect() and includes its spans in the result."""
        text = "The user Alice Johnson submitted a request."
        fake_resp = self._fake_ollama_response([{"type": "PERSON", "value": "Alice Johnson"}])
        with patch.object(pv, "LLM_PII_DETECTION", True), \
             patch.object(pv, "_post_json", side_effect=[
                 # First call: Presidio (raises -> falls back)
                 ConnectionError("Presidio not running"),
                 # Second call: Ollama
                 fake_resp,
             ]):
            spans = pv._detect(text)
        llm_spans = [sp for sp in spans if sp[2].startswith("LLM:")]
        self.assertTrue(llm_spans, f"Expected LLM: spans in _detect output, got {spans}")


# ===========================================================================
# ENTITY_PREFIX coverage
# ===========================================================================

class TestEntityPrefixCoverage(unittest.TestCase):
    """All LLM types from the taxonomy must have a mapping."""

    LLM_TYPES = [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ADDRESS", "DATE_OF_BIRTH",
        "US_SSN", "CREDIT_CARD", "BANK_ACCOUNT", "PASSPORT", "DRIVER_LICENSE",
        "IP_ADDRESS", "API_KEY", "PASSWORD", "USERNAME", "LOCATION",
    ]

    def test_all_taxonomy_types_have_prefix(self):
        missing = []
        for t in self.LLM_TYPES:
            prefix = pv._prefix_for(f"LLM:{t}")
            # _prefix_for falls back to stripping non-alpha chars; an empty or "PII" result
            # for a known type means the mapping is absent.
            if prefix == "PII" or not prefix:
                missing.append(t)
        self.assertFalse(
            missing,
            f"Types missing from ENTITY_PREFIX (or resolving to generic PII): {missing}",
        )


if __name__ == "__main__":
    unittest.main()
