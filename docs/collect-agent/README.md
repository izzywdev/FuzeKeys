# Collect-identities local agent: design spike (FKY-13)

| | |
|---|---|
| Story | FKY-13 "Design spike: Collect-identities local agent and secure device pairing" |
| Unblocks | FKY-4 (implementation) |
| Status | **Proposed. Requires security sign-off before FKY-4 starts.** Docs only: no code, no `appVersion` bump |
| Date | 2026-10-13 |
| Classification | `oss-public` (MIT). Everything here is public. No real secrets, tokens or personal data appear in these documents; all examples are synthetic |

## What this is

A local **collect agent** (Go, single signed binary, Windows first) that gathers a user's
existing credentials from two places on the user's own machine and delivers them to the
user's personal FuzeKeys vault **without the device ever holding the master key and without
any server component ever seeing a plaintext secret**:

1. **Google Password Manager (GPM)**, by an automated, throttled browser scrape of the user's own signed-in Google account.
2. **Windows Credential Manager**, via `CredEnumerateW` for the logged-in Windows user.

## Documents

| # | Document | Answers |
|---|----------|---------|
| 1 | [adr-001-gpm-browser-scrape-collector.md](adr-001-gpm-browser-scrape-collector.md) | How the GPM scrape is driven, throttled, confined to the user's own account, kept memory-only, and how it survives MFA/challenges without storing secrets |
| 2 | [adr-002-go-agent-packaging-and-windows.md](adr-002-go-agent-packaging-and-windows.md) | Go single binary, code signing, install/update/uninstall on Windows, Credential Manager / DPAPI scanning |
| 3 | [adr-003-device-pairing-and-upload-token.md](adr-003-device-pairing-and-upload-token.md) | Pairing-code flow, scoped short-lived upload token, revocation, sealing to the user's vault key, why the broker `operation` grant is not reused as-is |
| 4 | [../contracts/collect-import.v1.yaml](../contracts/collect-import.v1.yaml) | Bulk-import endpoint contract **stub** (OpenAPI 3.1): idempotent, de-duped, vault seam |
| 5 | [threat-model-data-path.md](threat-model-data-path.md) | Data-path threat model: tokenize-before-send, Vault-encryption and no-PII-in-logs invariants; edge cases; attacks; residual risk; security acceptance tests for FKY-4 |

## Fixed inputs (owner decisions, not re-litigated)

* **D-1.** GPM access is an **automated browser scrape**, no human in the loop for the scrape itself, with polite throttling and rate-limiting, operating **only the user's own authenticated Google account**, secrets **in memory only**, **no secret trace on local disk**.
* **D-2.** Agent technology is a **Go single binary (signed)**, minimal footprint, console/tray helper.

## Decision ledger (what this spike decides)

| ID | Decision | Where |
|----|----------|-------|
| S-1 | Drive a **fresh, agent-owned, incognito Chrome/Edge session over `--remote-debugging-pipe`**; never the user's real profile, never a persistent profile, never a fallback to one | ADR-001 |
| S-2 | The agent **never handles Google credentials, MFA or CAPTCHA**. Sign-in/re-auth is the user's own action in the visible window; the agent only waits. It stops (does not solve) on any challenge | ADR-001 |
| S-3 | Throttle: median 1 reveal / 8 s, hard ceiling 12 actions/min, 45-90 s rest every 25 entries, <=1 GPM run / 24 h, exponential cool-down (30 min / 4 h / 24 h / 7 d) enforced **server-side**, circuit breaker after 4 consecutive blocks | ADR-001 |
| S-4 | Per-user install, no service, no listening port, no admin; Authenticode-signed in CI by a bot/OIDC identity; signed update manifest; self-revoking uninstall | ADR-002 |
| S-5 | Credential Manager read is `CredEnumerateW(NULL, 0)` in the interactive user's own logon session. **No DPAPI masterkey or `Credentials` file access** | ADR-002 |
| S-6 | Pairing is **portal-initiated** (code shown in the portal) **plus a mandatory device-vs-portal Short Authentication String (SAS) confirmation** and step-up; a leaked code alone cannot pair a device | ADR-003 |
| S-7 | The device holds **only** a signing key, a non-master `tag_key`, and the **public** inbox key. Items are **sealed (hybrid RSA-OAEP-256 + AES-256-GCM, the `envelope.py` scheme) to a per-user inbox public key** whose private half exists only wrapped under the user's vault key on user clients | ADR-003 |
| S-8 | Upload tokens are **opaque, hashed at rest, run-scoped, 10 min TTL, sender-constrained (DPoP, RFC 9449)**. A **new `collect` module with its own signing/secret domain**; the broker is a pattern source, not the transport | ADR-003 |
| S-9 | The server stages **ciphertext only** (`inbox`); a user client decrypts, **reviews**, and writes to the personal Vaultwarden vault with client-side encryption, then acks. Dedupe is a **blind index** (`HMAC(tag_key, origin\|username)`) | ADR-003, contract |

## Open items that need an owner or security decision (not blockers for approving the *design*)

See the end of [threat-model-data-path.md](threat-model-data-path.md#10-open-decisions-and-blockers-for-fky-4)
for O-1..O-7. The two that matter most:

* **O-1.** D-1 ("no human in the loop" + "no secret trace on disk") cannot both hold *across runs* for Google sign-in, because a persisted Google session is itself a bearer secret on disk. This design keeps "no trace" and requires the user to complete Google's own sign-in at the start of each run. Unattended scheduled GPM runs would need an explicit owner decision to relax "no trace".
* **O-2.** The design assumes a client-side-encrypted personal vault (Vaultwarden) and a portal that holds the vault key client-side. Neither is in production today (verified below), so FKY-4 has two prerequisites.

## Verified facts this design is built on (repo at `origin/master` e0c5837)

| Fact | Evidence |
|------|----------|
| Only interactive JWT + master-key auth exists for users; the master key is sent to the server at login and a **process-global** Fernet manager is set | `backend/app/routers/auth.py` (`login` -> `set_global_encryption_manager(user_data.master_key)`), `backend/app/utils/encryption.py` |
| Broker redeem authenticates **workload** identity from gateway headers `X-Verified-Repo` / `X-Verified-Spiffe`; broker revoke requires a `fuze-workload` token | `backend/app/broker/runtime.py:transport_from_headers`, `backend/app/routers/broker.py:revoke` |
| Broker tokens are HS256 JWTs signed with `BROKER_SIGNING_KEY`, **falling back to `SECRET_KEY`** (the user-session signing key) | `backend/app/broker/runtime.py:get_broker_config` |
| The only existing device auth is a static, non-expiring, non-user-bound bearer (`X-Device-Key`) behind one global enrollment token | `backend/app/routers/sms.py`, `backend/app/models/sms.py` |
| Vault seam has `InMemoryVault` and `OpenBaoKV2Vault` only; **no Vaultwarden adapter**; no Vaultwarden in the Helm chart | `backend/app/broker/vault.py`; `grep -ri vaultwarden deploy/` returns nothing |
| Hybrid envelope (RSA-OAEP-256 + AES-256-GCM) already exists and is tested | `backend/app/broker/envelope.py` |
| The PII tokenizer stack is **disabled** in the production chart; its hooks are fail-open | `deploy/helm/fuzekeys/values.yaml` (`tokenizer.enabled: false`), `pii-tokenizer/docs/ASSUMPTIONS.md` |
| A production router sends free-form caller `context` straight to OpenAI with no tokenizer | `backend/app/routers/chat.py:get_ai_response` |
| Loguru is configured with `diagnose=True` on the console and both main file sinks | `backend/app/utils/logging.py` |
| `contracts/openapi.yaml` is **generated** from the FastAPI app, so the stub must not live there | header of `contracts/openapi.yaml` |
