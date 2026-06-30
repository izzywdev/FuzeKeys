"""LiteLLM custom guardrail: tokenize PII/secrets in outgoing prompt messages at the proxy,
so the upstream LLM (Anthropic/OpenAI) only ever receives `<TYPE_id>` tokens.

Containerized: this calls the tokenizer HTTP service (TOKENIZER_URL) instead of importing
pii_vault, so the LiteLLM image needs no Redis/Vault/Presidio deps — only stdlib urllib.

Register in the LiteLLM config:
    guardrails:
      - guardrail_name: pii-tokenizer
        litellm_params:
          guardrail: pii_guardrail.PIITokenizer
          mode: pre_call
          default_on: true
Requires this file on PYTHONPATH and TOKENIZER_URL reachable from the proxy container."""
import json
import os
import urllib.request

from litellm.integrations.custom_guardrail import CustomGuardrail

TOKENIZER_URL = os.environ.get("TOKENIZER_URL", "http://tokenizer:8099")


def _tokenize(text):
    """POST text to the tokenizer service; fail-open (return the original text on any error)."""
    if not text:
        return text
    try:
        req = urllib.request.Request(
            TOKENIZER_URL + "/tokenize",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())["text"]
    except Exception:
        return text


class PIITokenizer(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages")
        if messages:
            for m in messages:
                content = m.get("content")
                if isinstance(content, str):
                    m["content"] = _tokenize(content)
                elif isinstance(content, list):
                    for part in content:
                        if (isinstance(part, dict) and part.get("type") == "text"
                                and isinstance(part.get("text"), str)):
                            part["text"] = _tokenize(part["text"])
        return data
