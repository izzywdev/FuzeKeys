# ADR-002: Go single-binary agent, code signing, Windows install/uninstall, Credential Manager scan

* Status: Proposed (needs security sign-off)
* Story: FKY-13, unblocks FKY-4
* Inputs fixed by the owner (D-2): Go single binary, signed, minimal footprint, console/tray helper.
* Note on the `desktop-packaging` skill: the repo's skill (`.claude/skills/desktop-packaging/SKILL.md`) is an Electron-oriented stub (main/renderer split, contextIsolation, auto-update, signing/notarization, per-OS installers). Only its **signing, auto-update and per-OS installer** concerns carry over; the Electron process-model items do not apply to a Go binary, and the skill has no concrete commands to inherit. This ADR is therefore the first concrete content for that skill.

## 1. Decision summary

| Topic | Decision |
|-------|----------|
| Language / build | Go (current stable at build time), `CGO_ENABLED=0`, `-trimpath`, `-buildmode=exe`, `-ldflags "-s -w -buildid= -H=windowsgui"` and `AttachConsole(ATTACH_PARENT_PROCESS)` for CLI subcommands. One `fuzekeys-agent.exe` |
| First target | `windows/amd64`; `windows/arm64` second. macOS Keychain / Linux libsecret collectors are future ADRs (Credential Manager is Windows-only) |
| Location in repo | New top-level Go module `agent/` (own `go.mod`, own release workflow tagged `agent-v*`). It is **not** baked into the backend/frontend/tokenizer images, so it does not trigger the `release-version` gate; FKY-4 must still keep that gate's path list in mind |
| Footprint | One exe (target < 15 MB), **no service, no driver, no listening socket, no admin**, per-user state under `%LOCALAPPDATA%\FuzeKeys` |
| Process model | Single process, single instance (named mutex). Subcommands and the tray share the process; **no localhost HTTP/IPC server** (a local port is attackable by any same-user process) |
| Signing | Authenticode (SHA-256, RFC 3161 timestamp) applied **in CI by a bot/OIDC identity**, never a maintainer's personal key or token |
| Distribution | GitHub Releases: signed `.msi` (per-user) + signed portable `.exe` + checksums + SBOM + build-provenance attestation |
| Update | Signed manifest + Authenticode verification + server-side `min_agent_version` kill-switch |
| Uninstall | Self-revoke the device server-side, delete every artefact in the inventory (section 7), then verify with `doctor --leftovers` |

## 2. Dependency policy (minimal footprint, small attack surface)

* Standard library first: `crypto/*` (RSA-OAEP, AES-GCM, ECDSA P-256, HMAC, SHA-256), `net/http`, `log/slog`, `encoding/json`, `os/exec`. Go 1.26 also adds `crypto/hpke` (RFC 9180), which is the planned v2 sealing primitive (ADR-003 section 7).
* Permitted third-party: `golang.org/x/sys/windows` (BSD-3), a tray library (`fyne.io/systray` or equivalent, Apache-2.0, no cgo on Windows), and `chromedp` (MIT) only if the direct CDP client is not written. All MIT/Apache/BSD, compatible with this MIT repo (`CLAUDE.md`: do not ship non-MIT/proprietary licensing).
* **No cgo, no embedded browser, no LLM SDK, no telemetry SDK.** Enforce with an import allowlist lint (`depguard`) and `go.sum` review.
* Supply-chain gates in the agent workflow: `govulncheck`, Trivy (existing Harden Gate), gitleaks, Actions pinned by commit SHA (existing repo practice), `go mod verify`, reproducible build check (`-trimpath`, `-buildid=`, pinned toolchain, `SOURCE_DATE_EPOCH`).
* `runtime/secret` (Go 1.26 experiment) is **not** relied upon: it is behind `GOEXPERIMENT=runtimesecret` and its platform coverage is unverified for Windows. Secret hygiene uses explicit `[]byte` + zeroing + `VirtualLock` (ADR-001 section 7).

## 3. Commands and tray

`fuzekeys-agent.exe` with no arguments starts the tray helper.

| Command | Purpose |
|---------|---------|
| `pair` | Start device pairing (shows the Short Authentication String; ADR-003) |
| `run --source gpm_web\|wincred` | Run one collection (also reachable from the tray menu) |
| `status` | Pairing state, last run outcome (counts and codes only) |
| `unpair` | Self-revoke on the server, then wipe local state |
| `uninstall --purge` | Unpair + remove every artefact (section 7) |
| `doctor [--leftovers]` | Environment preflight (BitLocker, browser, clock skew) / list any residue |
| `version` | Version, build provenance id, signing publisher |

The tray shows: paired / not paired, "Collect now" (when armed), a non-blocking cancel toast when a run begins, and the block/cool-down state. It never displays an item value.

## 4. Windows install model

* **Default: per-user** install of the MSI to `%LOCALAPPDATA%\Programs\FuzeKeys\fuzekeys-agent.exe`. No elevation, no UAC prompt, no HKLM writes. An **optional per-machine** MSI (Program Files) is offered for managed fleets because it makes the binary non-writable by a non-admin same-user process (binary-planting hardening).
* Autostart is **opt-in** (`HKCU\...\Run` value); never a scheduled task or service.
* The portable exe (`--portable`) writes no registry keys and keeps state next to `%LOCALAPPDATA%\FuzeKeys`.
* WiX (or equivalent) builds the MSI; the MSI wraps only the one exe and the Start-menu shortcut. Add/Remove Programs provides the standard uninstall entry whose custom action runs `uninstall --purge`.

### State on disk (complete list; everything else is a bug)

| Path | Contents | Secret? |
|------|----------|---------|
| `...\FuzeKeys\config.json` | API origin, `device_id`, last update check, cached throttle policy, `min_agent_version` | No |
| `...\FuzeKeys\device.bin` | DPAPI blob (`CryptProtectData`, user scope, `CRYPTPROTECT_UI_FORBIDDEN`, app entropy) holding the ES256 device key, the `tag_key`, and the pinned inbox public key id and SPKI hash | **Device secret**, never a user credential |
| `...\FuzeKeys\logs\agent.log` | Rotating (5 x 1 MB) allow-listed counters/codes | No (verified by redaction tests) |
| `...\FuzeKeys\tmp\gpm-*` | Throw-away Chrome dir, normally empty of sessions | Must contain no secret (leak audit) |
| `...\FuzeKeys\updates\` | Downloaded, signature-verified update | No |

DPAPI note: user-scope DPAPI defeats offline disk theft and other Windows users, but **not** malware running as the same user. That residual is accepted and is bounded by the fact that `device.bin` holds no user credential and no master key, and that the server-side token still needs a portal-armed run.

An upgrade path to a **non-exportable TPM-backed CNG key** (Microsoft Platform Crypto Provider) for the device signing key is planned for v2; it needs `ncrypt` syscalls through `x/sys/windows` and is not required for v1.

## 5. Code signing and release integrity

### 5.1 Options for the Authenticode identity

| Option | Notes | Fit |
|--------|-------|-----|
| **Azure Artifact Signing** (the service renamed from "Trusted Signing"; no functional change per Microsoft) | Short-lived certs, no HSM to manage, CI-friendly via OIDC. Identity validation: organisations in USA, Canada, EU, UK; **individual developers only in USA and Canada** (Microsoft "Code signing options" page). SmartScreen reputation still builds over time | **Preferred** if the publisher is an eligible entity |
| OV/EV certificate with the key in a **cloud HSM/KMS** (FIPS 140-2 L2 key storage is required by the CA/B baseline) used via `signtool`/`osslsigncode` and a vendor signer | Works for any eligible buyer; annual cost; EV no longer a guaranteed SmartScreen bypass | Fallback |
| Self-signed or no signature | SmartScreen blocks; EDR will flag a credential-reading unsigned exe | **Not acceptable** |

The decision of which entity buys the identity is an owner/finance decision (open decision O-4). Technical requirements either way: private key never on a developer laptop or in a repo secret; signing happens in the release workflow under a **bot/GitHub-App/OIDC identity** (aligned with `governance/identity-and-attribution.md`: agents act as a bot, never the maintainer's personal token); timestamped; `signtool verify /pa /v` is a release gate.

### 5.2 Release artefacts

`fuzekeys-agent-<ver>-windows-amd64.msi`, `...exe`, `SHA256SUMS`, a CycloneDX SBOM, a GitHub build-provenance attestation, and a keyless `cosign` signature over `SHA256SUMS`. The pinned publisher subject is baked into the agent for update checks.

### 5.3 Update

1. Agent checks the release manifest at most once per 24 h (and on `426 Upgrade Required` from the API).
2. Manifest is verified with an **embedded Ed25519 release key** (independent of Authenticode), then the downloaded exe is verified with `WinVerifyTrust` **and** its signer subject is compared to the pinned publisher. Either failure = discard.
3. Apply on next start by atomic rename. Security releases may be applied silently; feature releases prompt in the tray.
4. The server holds `min_agent_version`: below it, `POST /runs` and imports return `426` and the agent self-updates before doing anything else. This is the revocation path for a vulnerable release.

## 6. Windows Credential Manager collector

### 6.1 What it reads

* API: `CredEnumerateW(NULL, 0, &count, &creds)`. A `NULL` filter returns every credential in the **credential set of the calling token's logon session**; that set is the logged-in user's own. (Microsoft `CredEnumerate` documentation: filter is a name prefix + `*`, `NULL` returns all; `CRED_ENUMERATE_ALL_CREDENTIALS` requires a `NULL` filter; the result is one allocated block released with `CredFree`; network logon sessions have no credential set.)
* The OS decrypts `CredentialBlob` for the caller. DPAPI is the OS's internal mechanism; the agent calls **no DPAPI API on Credential Manager data and never touches the on-disk `%APPDATA%\Microsoft\Credentials` files or DPAPI master keys**. Reading those directly is the offline-attack technique used by credential dumpers; it is explicitly **forbidden** here because it would widen reach beyond the logged-in session, trip EDR, and has no benefit over the supported API.
* The agent's own use of DPAPI is limited to protecting `device.bin` (section 4).

### 6.2 What it does with it

1. Enumerate; for each credential keep `TargetName`, `UserName`, `Type`, `Persist`, `Comment`, and the blob as raw bytes. A generic credential's blob is usually a UTF-16LE password but may be arbitrary bytes (maximum 2,560 bytes, `CRED_MAX_CREDENTIAL_BLOB_SIZE`, to be confirmed against the SDK header in FKY-4), so it is carried as bytes plus an `encoding_hint` (`utf16le` | `utf8` | `binary`), never assumed text.
2. **Default exclusions** (user can override in the portal review): `CRED_TYPE_CERTIFICATE`, `CRED_PERSIST_SESSION` entries, Microsoft-internal tokens (`MicrosoftAccount:*`, `WindowsLive:*`, `SSO_POP_Device`, `virtualapp/*`; the exact list is a tunable data table, validated against a real machine in FKY-4), and **the agent's own entries** (any `FuzeKeys:` prefix). Domain-password (`CRED_TYPE_DOMAIN_PASSWORD`) entries normally return no usable blob and are reported as metadata-only.
3. Show a **non-blocking toast** ("Reading Windows Credential Manager for <user>; Cancel within 15 s"); the portal arming is the consent, the toast is the local veto.
4. Seal each item immediately (ADR-003), `CredFree` the block, zero all copies.
5. `TargetName` often embeds hostnames or usernames, so it is sealed with the item; it is **not** sent in clear.

### 6.3 Not in v1

Web Credentials (the `PasswordVault` WinRT store used by legacy IE/Edge), Chrome/Edge local stores, Windows Hello/NGC, smart-card material, and any other user's credentials.

## 7. Uninstall and cleanup

### 7.1 Artefact inventory and removal

| Artefact | Removed by |
|----------|------------|
| Server pairing (`collector_device`) | `unpair`: signed `DELETE /api/v1/collect/devices/{device_id}`. If offline, the uninstall completes locally and tells the user to revoke in the portal; the server also expires unused devices (ADR-003) |
| `device.bin`, `config.json`, `logs\`, `updates\`, `tmp\gpm-*` | Delete the whole `%LOCALAPPDATA%\FuzeKeys` tree |
| Browser processes | Job Object kill; then kill any surviving process whose command line contains our `gpm-` dir |
| `HKCU\Software\FuzeKeys`, `HKCU\...\Run\FuzeKeysAgent`, WER exclusion value | `RegDeleteTree`/`RegDeleteValue` |
| Credential Manager entries we own (`FuzeKeys:*`, none expected in v1) | `CredDeleteW` |
| Start-menu shortcut, MSI files, Add/Remove entry | MSI uninstall |
| Scheduled tasks / services | None are ever created (so none to remove) |

### 7.2 Verification

* `doctor --leftovers` lists any residue and exits non-zero if found; the MSI custom action surfaces it.
* **CI test on a Windows runner (FKY-4):** install -> pair against a mock -> run against mocks -> uninstall -> assert: no files under the paths above, no `HKCU\Software\FuzeKeys`, no `Run` value, no `FuzeKeys:*` credential, no leftover process, and a canary scan of `%TEMP%` and crash dump dirs finds nothing.

## 8. Risks

* **AV/EDR false positives.** A signed binary that calls `CredEnumerateW` and drives a browser resembles an infostealer. Mitigations: valid Authenticode + reputation, open source (MIT) and reproducible build, talks only to the FuzeKeys API origin, visible tray and toasts, no persistence tricks, submit each release to the Microsoft Defender portal. Expect a reputation ramp (Microsoft: "reputation builds over time").
* **User-writable install dir** (per-user default) allows same-user binary planting. Accepted for default; per-machine MSI offered. Note that any same-user process can already call `CredEnumerateW` itself, so the agent adds no read capability to such malware; what it protects is the upload channel.
* **Hibernation/pagefile exposure** is mitigated by the BitLocker preflight and suspend handler (ADR-001 section 7).

## 9. Acceptance criteria for FKY-4 (derived)

1. `signtool verify /pa` passes in CI; the signing step runs as a bot/OIDC identity (no personal secret in the workflow).
2. Update tamper tests: wrong signer, valid signer with bad manifest signature, downgrade, replayed old manifest are all rejected.
3. Uninstall residue test (7.2) green on a clean Windows runner.
4. Static check: binary has no listening sockets (`netstat` during a run) and no outbound connection except the API origin and the (allow-listed) browser's Google origins.
5. `go list -deps` against the import allowlist: no LLM SDK, no telemetry SDK, no cgo.
6. Credential Manager collector fixture test: seeds fake generic credentials (UTF-16LE, UTF-8, binary, oversize) and asserts correct `encoding_hint`, exclusions, and zeroing of buffers after seal.
