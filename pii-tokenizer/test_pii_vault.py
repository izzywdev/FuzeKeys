"""Round-trip test: tokenize -> assert Redis holds ciphertext only -> detokenize restores."""
import re
import pii_vault as pv

SAMPLE = ("Customer card 4111111111111111, email john.doe@example.com, "
          "SSN 078-05-1120, calling +1 (415) 555-2671, "
          "anthropic key sk-ant-abc123def456ghi789jkl012mno345.")


def main():
    red = pv.tokenize(SAMPLE)
    print("REDACTED:", red)

    # No raw PII should survive in the redacted text.
    for leak in ["4111111111111111", "john.doe@example.com", "078-05-1120", "sk-ant-abc123"]:
        assert leak not in red, f"LEAK: {leak} still present"

    tokens = re.findall(r"<[A-Z]+_[A-Za-z0-9]+>", red)
    assert tokens, "no tokens produced"
    print("TOKENS:", tokens)

    # Redis must hold Vault ciphertext only — never the plaintext.
    for tok in tokens:
        data = pv._r.hgetall(tok)
        assert data.get("ciphertext", "").startswith("vault:"), f"{tok} missing vault ciphertext"
        assert SAMPLE.find(data["ciphertext"]) == -1
    print("REDIS: ciphertext-only confirmed")

    restored = pv.detokenize(red)
    print("RESTORED:", restored)
    assert restored == SAMPLE, "round-trip mismatch"
    print("ROUND-TRIP OK")


if __name__ == "__main__":
    main()
