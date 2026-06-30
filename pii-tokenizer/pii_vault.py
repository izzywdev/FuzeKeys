"""Shared PII tokenization library.

tokenize(text)   -> detect PII/secrets (Presidio + regex + optional LLM), Vault-encrypt each
                    value, store ciphertext in Redis keyed by a `<TYPE_id>` token, return
                    redacted text.
detokenize(text) -> find `<TYPE_id>` tokens, look up ciphertext in Redis, Vault-decrypt, restore.

Real values are NEVER stored in Redis — only Vault ciphertext. Detokenization requires Vault.
Used by both the LiteLLM proxy guardrail and the Claude Code PreToolUse/PostToolUse hooks.

Second-stage LLM detection (Feature 2): when LLM_PII_DETECTION=true, a local Gemma model via
Ollama is called *after* Presidio + SECRET_PATTERNS to catch PII the patterns miss. Fail-open:
any Ollama error simply returns an empty span list.
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
# Containerized runtime: when VAULT_TOKEN isn't set in the env, read the root token from the
# Vault init file written by the vault-bootstrap container (shared volume mounted at /init).
if not VAULT_TOKEN:
    _init_file = os.environ.get("VAULT_INIT_FILE", "/init/.vault-init.json")
    try:
        with open(_init_file, encoding="utf-8") as _fh:
            VAULT_TOKEN = json.load(_fh).get("root_token", "")
    except Exception:
        pass
VAULT_KEY = os.environ.get("VAULT_TRANSIT_KEY", "pii")
PRESIDIO_URL = os.environ.get("PRESIDIO_URL", "http://localhost:5002")
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "0"))
ENTITIES = [e for e in os.environ.get(
    "PII_ENTITIES", "CREDIT_CARD,US_SSN,EMAIL_ADDRESS,PHONE_NUMBER,IBAN_CODE").split(",") if e]
SCORE = float(os.environ.get("PII_SCORE_THRESHOLD", "0.5"))
MAX_CHARS = int(os.environ.get("MAX_TOKENIZE_CHARS", "20000"))

# --- Feature 2: LLM second-stage detection config (Ollama / Gemma) ---
LLM_PII_DETECTION = os.environ.get("LLM_PII_DETECTION", "false").lower() in ("1", "true", "yes")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_PII_MODEL = os.environ.get("OLLAMA_PII_MODEL", "gemma3:4b")
LLM_PII_MAX_CHARS = int(os.environ.get("LLM_PII_MAX_CHARS", "8000"))
LLM_PII_TIMEOUT = int(os.environ.get("LLM_PII_TIMEOUT", "30"))

# Load the PII taxonomy document once at import time (embedded in the LLM prompt).
_SKILL_PATH = os.path.join(os.path.dirname(__file__), "skills", "pii_types.md")
_LLM_SKILL_DOC = ""
try:
    with open(_SKILL_PATH, encoding="utf-8") as _fh:
        _LLM_SKILL_DOC = _fh.read()
except Exception:
    pass  # Fail-open: missing skill doc -> prompt has no taxonomy table

_r = redis.from_url(REDIS_URL, decode_responses=True)

# Presidio entity_type -> short token prefix
ENTITY_PREFIX = {
    "CREDIT_CARD": "CCD",
    "EMAIL_ADDRESS": "EMAIL",
    "US_SSN": "SSN",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN",
    # LLM-detected types (Feature 2)
    "PERSON": "NAME",
    "ADDRESS": "ADDR",
    "LOCATION": "ADDR",
    "DATE_OF_BIRTH": "DOB",
    "PASSPORT": "PASSPORT",
    "DRIVER_LICENSE": "DL",
    "BANK_ACCOUNT": "BANK",
    "IP_ADDRESS": "IP",
    "API_KEY": "APIKEY",
    "PASSWORD": "PWD",
    "USERNAME": "USER",
}

# High-confidence secret/key patterns (detected locally; Presidio doesn't cover these well).
SECRET_PATTERNS = [
    ("APIKEY", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("APIKEY", re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}")),
    ("APIKEY", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("APIKEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("APIKEY", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("APIKEY", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    # Feature 1: Atlassian Cloud API tokens / PATs.
    # AT[A-Z]TT covers ATATT (Cloud API token) and ATCTT (Connect/OAuth token).
    ("APIKEY", re.compile(r"AT[A-Z]TT[A-Za-z0-9_\-=\.]{20,}")),
    # ATBB covers Atlassian Bitbucket tokens (ATBB<base64body>).
    ("APIKEY", re.compile(r"ATBB[A-Za-z0-9_\-=\.]{20,}")),
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


def _llm_detect(text):
    """Ask the local Gemma model (via Ollama) to find PII the pattern stage missed.

    Returns a list of (start, end, "LLM:<TYPE>") tuples. Fail-open: any error returns [].
    Only called when LLM_PII_DETECTION=true and len(text) <= LLM_PII_MAX_CHARS.
    """
    if not LLM_PII_DETECTION:
        return []
    if len(text) > LLM_PII_MAX_CHARS:
        return []
    try:
        taxonomy_section = (
            f"\n\n{_LLM_SKILL_DOC}\n\n" if _LLM_SKILL_DOC else ""
        )
        prompt = (
            "You are a PII detection engine. Identify all personally identifiable information "
            "and secrets in the text below."
            f"{taxonomy_section}"
            "Text to analyse:\n"
            "---\n"
            f"{text}\n"
            "---\n"
            'Return ONLY valid JSON: {"pii": [{"type": "TYPE", "value": "exact substring"}]}. '
            "No prose."
        )
        resp = _post_json(
            f"{OLLAMA_URL}/api/generate",
            {
                "model": OLLAMA_PII_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=LLM_PII_TIMEOUT,
        )
        raw = resp.get("response", "{}")
        parsed = json.loads(raw)
        items = parsed.get("pii", [])
        spans = []
        for item in items:
            entity_type = str(item.get("type", "")).strip()
            value = str(item.get("value", "")).strip()
            if not entity_type or not value:
                continue
            # Find all occurrences of this value in the text.
            pos = 0
            while True:
                idx = text.find(value, pos)
                if idx == -1:
                    break
                spans.append((idx, idx + len(value), "LLM:" + entity_type))
                pos = idx + len(value)
        return spans
    except Exception:
        return []  # Fail-open: Ollama down/slow/malformed response


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
    # Feature 2: LLM second-stage detection (fail-open if Ollama unreachable).
    spans.extend(_llm_detect(text))
    return spans


def _prefix_for(entity_type):
    if entity_type.startswith("SECRET:"):
        return entity_type.split(":", 1)[1]
    if entity_type.startswith("LLM:"):
        entity_type = entity_type.split(":", 1)[1]
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
