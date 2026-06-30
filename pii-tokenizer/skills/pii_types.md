# PII Type Taxonomy

This document defines the supported PII entity types for the Gemma-based second-stage
LLM detector. The prompt embeds this table so the model knows exactly which types to
report and how to format them.

## Supported Entity Types

| Type | Token Prefix | Examples |
|------|-------------|---------|
| PERSON | NAME | "John Smith", "Maria Garcia", "Dr. Alice Wong" |
| EMAIL_ADDRESS | EMAIL | "user@example.com", "john.doe+tag@company.org" |
| PHONE_NUMBER | PHONE | "+1-555-123-4567", "0044 20 7946 0958", "(800) 555-0100" |
| ADDRESS | ADDR | "123 Main St, Springfield, IL 62701", "10 Downing Street, London" |
| DATE_OF_BIRTH | DOB | "1985-03-22", "March 22, 1985", "22/03/1985" |
| US_SSN | SSN | "123-45-6789", "987-65-4320" |
| CREDIT_CARD | CCD | "4111 1111 1111 1111", "5500-0000-0000-0004" |
| BANK_ACCOUNT | BANK | "GB82 WEST 1234 5698 7654 32", "12345678 / sort code 01-02-03" |
| PASSPORT | PASSPORT | "A12345678" (US), "GBR123456789" |
| DRIVER_LICENSE | DL | "D1234567" (CA), "1234-5678-9012" |
| IP_ADDRESS | IP | "192.168.1.1", "2001:0db8:85a3::8a2e:0370:7334" |
| API_KEY | APIKEY | "sk-proj-abc123...", "ghp_XXXX...", "ATATT3xFfGF..." |
| PASSWORD | PWD | any value labelled "password", "passwd", "secret" in context |
| USERNAME | USER | "jsmith", "@alice", login names used alongside credentials |

## Detection Rules

1. **Return values verbatim** — copy the exact substring from the input; do NOT paraphrase,
   truncate, or expand.
2. **Do NOT flag code, version strings, or technical identifiers** — things like
   `claude-haiku-4-5-20251001`, `v2.3.1`, hex hashes (`a1b2c3d4`), UUIDs
   (`550e8400-e29b-41d4-a716-446655440000`), and file paths are NOT PII.
3. **Do NOT flag already-tokenized placeholders** — strings matching the pattern
   `<TYPE_id>` (e.g. `john.doe@example.com`, `078-05-1120`) are token
   placeholders already emitted by this system; leave them untouched.
4. **Confidence** — only report values you are highly confident are real PII or secrets.
   Prefer precision over recall; a false negative is safer than a false positive.
5. **Completeness** — if the same value appears multiple times in the text, report it
   once (the lookup logic finds all occurrences).

## Output Format

Return ONLY a strict JSON object. No prose, no explanation, no markdown wrapper:

```json
{"pii": [{"type": "ENTITY_TYPE", "value": "exact substring from input"}]}
```

If no PII is found, return:

```json
{"pii": []}
```

Valid `type` values are exactly the uppercase labels in the table above (first column).
