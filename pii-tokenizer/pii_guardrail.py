"""LiteLLM custom guardrail: tokenize PII/secrets in outgoing prompt messages at the proxy,
so the upstream LLM (Anthropic/OpenAI) only ever receives `<TYPE_id>` tokens.

Register in the LiteLLM config:
    guardrails:
      - guardrail_name: pii-tokenizer
        litellm_params:
          guardrail: pii_guardrail.PIITokenizer
          mode: pre_call
          default_on: true
Requires the pii-vault dir on PYTHONPATH (so `pii_guardrail` and `pii_vault` import)."""
from litellm.integrations.custom_guardrail import CustomGuardrail

import pii_vault as pv


class PIITokenizer(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages")
        if messages:
            for m in messages:
                content = m.get("content")
                if isinstance(content, str):
                    m["content"] = pv.tokenize(content)
                elif isinstance(content, list):
                    for part in content:
                        if (isinstance(part, dict) and part.get("type") == "text"
                                and isinstance(part.get("text"), str)):
                            part["text"] = pv.tokenize(part["text"])
        return data
