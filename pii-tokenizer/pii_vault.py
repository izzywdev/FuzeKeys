"""Shared PII tokenization library.

tokenize(text)   -> detect PII/secrets (Presidio + regex), Vault-encrypt each value,
                    store ciphertext in Redis keyed by a `<TYPE_id>` token, return redacted text.
detokenize(text) -> find `<TYPE_id>` tokens, look up ciphertext in Redis, Vault-decrypt, restore.

Real values are NEVER stored in Redis — only Vault ciphertext. Detokenization requires Vault.
Used by both the LiteLLM proxy guardrail and the Claude Code PreToolUse/PostToolUse hooks.
"""
import os
import re
import json
import base64
import hashlib
import uuid
import urllib.request

import redis


def _load_env(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env(os.path.join(os.path.dirname(__file__), ".env"))

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")
VAULT_KEY = os.environ.get("VAULT_TRANSIT_KEY", "pii")
PRESIDIO_URL = os.environ.get("PRESIDIO_URL", "http://localhost:5002")
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "0"))
ENTITIES = [e for e in os.environ.get(
    "PII_ENTITIES", "CREDIT_CARD,US_SSN,EMAIL_ADDRESS,PHONE_NUMBER,IBAN_CODE").split(",") if e]
SCORE = float(os.environ.get("PII_SCORE_THRESHOLD", "0.5"))
MAX_CHARS = int(os.environ.get("MAX_TOKENIZE_CHARS", "20000"))

_r = redis.from_url(REDIS_URL, decode_responses=True)

# Presidio entity_type -> short token prefix
ENTITY_PREFIX = {
    "CREDIT_CARD": "CCD",
    "EMAIL_ADDRESS": "EMAIL",
    "US_SSN": "SSN",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN",
}

# High-confidence secret/key patterns (detected locally; Presidio doesn't cover these well).
SECRET_PATTERNS = [
    ("APIKEY", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("APIKEY", re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}")),
    ("APIKEY", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("APIKEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("APIKEY", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("APIKEY", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("TOKEN", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
]

# Matches tokens we emit, e.g. <CCD_ab12cd34ef56>
TOKEN_RE = re.compile(r"<([A-Z]+)_([A-Za-z0-9]{6,})>")

# Structured-numeric entities must not be matched *inside* a larger identifier/version
# string. Presidio flatly scores PHONE_NUMBER ~0.4 for both real phones and fragments like
# the "4-5-20251001" inside "claude-haiku-4-5-20251001", so a score threshold can't tell
# them apart. Instead: if the span is glued to surrounding alphanumerics that contain a
# letter, it's part of an identifier — not standalone PII — so we drop it.
_IDENTIFIER_GUARDED = {"CREDIT_CARD", "US_SSN", "PHONE_NUMBER", "IBAN_CODE"}
_HAS_ALPHA = re.compile(r"[A-Za-z]")


def _in_identifier(text, start, end):
    i = start
    while i > 0 and (text[i - 1].isalnum() or text[i - 1] in "-_"):
        i -= 1
    j = end
    while j < len(text) and (text[j].isalnum() or text[j] in "-_"):
        j += 1
    return bool(_HAS_ALPHA.search(text[i:start] + text[end:j]))


def _post_json(url, payload, headers=None, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _vault_encrypt(plaintext):
    b64 = base64.b64encode(plaintext.encode()).decode()
    out = _post_json(f"{VAULT_ADDR}/v1/transit/encrypt/{VAULT_KEY}",
                     {"plaintext": b64}, {"X-Vault-Token": VAULT_TOKEN})
    return out["data"]["ciphertext"]


def _vault_decrypt(ciphertext):
    out = _post_json(f"{VAULT_ADDR}/v1/transit/decrypt/{VAULT_KEY}",
                     {"ciphertext": ciphertext}, {"X-Vault-Token": VAULT_TOKEN})
    return base64.b64decode(out["data"]["plaintext"]).decode()


def _detect(text):
    """Return list of (start, end, entity_type) spans."""
    spans = []
    try:
        res = _post_json(f"{PRESIDIO_URL}/analyze",
                         {"text": text, "language": "en",
                          "entities": ENTITIES, "score_threshold": SCORE})
        spans = [(r["start"], r["end"], r["entity_type"])
                 for r in res if r.get("score", 0) >= SCORE]
        # Drop numeric-entity matches embedded in identifiers/version strings.
        spans = [sp for sp in spans
                 if not (sp[2] in _IDENTIFIER_GUARDED and _in_identifier(text, sp[0], sp[1]))]
    except Exception:
        pass  # Presidio unreachable -> fall back to regex-only secret detection
    for label, pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end(), "SECRET:" + label))
    return spans


def _prefix_for(entity_type):
    if entity_type.startswith("SECRET:"):
        return entity_type.split(":", 1)[1]
    return ENTITY_PREFIX.get(entity_type, re.sub(r"[^A-Z]", "", entity_type.upper()) or "PII")


def _store(token, ciphertext, etype):
    _r.hset(token, mapping={"ciphertext": ciphertext, "type": etype})
    if TOKEN_TTL > 0:
        _r.expire(token, TOKEN_TTL)


def tokenize(text):
    """Replace detected PII/secrets in `text` with stable `<TYPE_id>` tokens."""
    if not text or not isinstance(text, str):
        return text
    if MAX_CHARS > 0 and len(text) > MAX_CHARS:
        return text
    spans = _detect(text)
    if not spans:
        return text
    # Drop overlaps: prefer earlier start, then longer span.
    spans = sorted(set(spans), key=lambda s: (s[0], -(s[1] - s[0])))
    chosen, last_end = [], -1
    for s, e, t in spans:
        if s >= last_end:
            chosen.append((s, e, t))
            last_end = e
    out = text
    for s, e, t in sorted(chosen, key=lambda x: x[0], reverse=True):
        raw = text[s:e]
        prefix = _prefix_for(t)
        vhash = "valhash:" + hashlib.sha256((prefix + "|" + raw).encode()).hexdigest()
        token = _r.get(vhash)
        if not token:
            cipher = _vault_encrypt(raw)
            token = f"<{prefix}_{uuid.uuid4().hex[:12]}>"
            _store(token, cipher, t)
            _r.set(vhash, token, ex=TOKEN_TTL if TOKEN_TTL > 0 else None)
        out = out[:s] + token + out[e:]
    return out


def detokenize(text):
    """Replace `<TYPE_id>` tokens with their decrypted real values."""
    if not text or not isinstance(text, str):
        return text

    def repl(m):
        token = m.group(0)
        data = _r.hgetall(token)
        if not data or "ciphertext" not in data:
            return token
        try:
            return _vault_decrypt(data["ciphertext"])
        except Exception:
            return token

    return TOKEN_RE.sub(repl, text)


def detokenize_obj(obj):
    """Recursively detokenize all string values in a JSON-like structure."""
    if isinstance(obj, str):
        return detokenize(obj)
    if isinstance(obj, list):
        return [detokenize_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: detokenize_obj(v) for k, v in obj.items()}
    return obj


def tokenize_obj(obj):
    """Recursively tokenize all string values in a JSON-like structure."""
    if isinstance(obj, str):
        return tokenize(obj)
    if isinstance(obj, list):
        return [tokenize_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: tokenize_obj(v) for k, v in obj.items()}
    return obj
