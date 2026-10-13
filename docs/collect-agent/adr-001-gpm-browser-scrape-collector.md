# ADR-001: Google Password Manager collector (safe, throttled browser scrape)

* Status: Proposed (needs security sign-off)
* Story: FKY-13, unblocks FKY-4
* Inputs fixed by the owner (D-1): automated browser scrape, no human in the loop for the scrape, polite throttling, only the user's own authenticated Google account, secrets in memory only, no secret trace on local disk.

## 1. Context

Google Password Manager has no public API for reading saved passwords. The only supported
read surfaces are the web UI at `passwords.google.com` and Chrome's own password manager.
Reading Chrome's local `Login Data` database directly is a different (and worse) technique:
on Windows it sits behind Chrome's App-Bound Encryption, and bypassing that looks exactly
like an infostealer to EDR. This ADR therefore covers only the **web UI scrape** that the
owner chose.

Two platform facts shape every choice below:

1. **Chrome 136+ ignores `--remote-debugging-port` / `--remote-debugging-pipe` on the default
   user-data directory** and requires a non-standard `--user-data-dir`, which also uses a
   *different* encryption key from the real profile. Source: Chrome for Developers,
   "Changes to remote debugging switches to improve security"
   (https://developer.chrome.com/blog/remote-debugging-port). So "drive the user's real Chrome
   profile" is not available, and copying the real profile to a new directory neither works
   (different key) nor is acceptable (it would copy the session to disk).
2. **A persisted Google session is a bearer secret with the full power of the account.** Any
   design that keeps the user signed in between runs writes that bearer to disk, which D-1
   forbids.

## 2. Decision summary

| Topic | Decision |
|-------|----------|
| Browser | The user's **installed Chrome stable** (fallback: installed Edge/Chromium). No bundled browser, no Chrome for Testing |
| Session | **Fresh, agent-owned, incognito session per run** in a throw-away, non-default user-data dir. **Never** the real profile. **Never** a persistent profile, and never a silent fallback to one |
| Control channel | CDP over **`--remote-debugging-pipe`** (inherited handles). **No TCP debug port** is ever opened |
| Window | **Headed and visible** (needed for the user's own sign-in/MFA; also the honest posture). Not headless |
| Google credentials / MFA / CAPTCHA | The agent **never types, reads, stores or solves** them. The user completes sign-in/re-auth in the window; the agent only waits and resumes |
| Challenge or block | **Stop immediately**, no retry in the run, server-enforced exponential cool-down, circuit breaker |
| Scope | Navigation restricted to an allowlist of Google origins by CDP request interception; account identity checked before any read |
| Secret handling | Read from the DOM into `[]byte`, sealed immediately to the inbox public key, plaintext zeroed; nothing plaintext leaves RAM |
| Parsing | **Deterministic selectors only. No LLM-assisted parsing.** Selector drift fails closed |

## 3. How the browser is driven

### 3.1 Options considered

| Option | Verdict | Why |
|--------|---------|-----|
| A. Headless Chromium on the **user's real profile** | **Rejected** | Chrome 136+ blocks debugging the default dir; copying the profile breaks cookie decryption and leaves the session on disk; headless cannot show sign-in/MFA; headless is also the most bot-flagged mode |
| B. **Fresh automated incognito session**, agent-owned dir, user signs in each run | **Chosen** | Satisfies "no secret trace" (incognito keeps cookies in memory); works on Chrome 136+; no real-profile access; user sees everything |
| C. Chrome for Testing (the Chrome team's recommended automation build) | Rejected | ~150 MB bundled binary breaks "minimal footprint"; Google sign-in is likelier to be refused in a test build; extra supply-chain surface |
| D. Persistent agent profile that remembers the Google login | **Rejected (O-1)** | The remembered session is a disk-resident bearer secret; contradicts D-1 "no trace". Needs an explicit owner decision to ever allow |
| E. Browser extension in the user's real profile | Rejected | Conflicts with D-2 (Go single binary) and grants a long-lived extension broad access to the real session |
| F. Decrypt Chrome `Login Data` locally | Rejected | Defeats App-Bound Encryption by design; EDR-hostile; not what the owner chose |
| G. User-driven CSV export | Rejected | A human step and a plaintext file on disk |

### 3.2 Launch parameters (normative for FKY-4)

* Executable: Chrome stable from the standard install locations (registry `App Paths`), then Edge. Verify the Authenticode signature of the browser executable (publisher is Google LLC / Microsoft Corporation) before launch; refuse an unsigned or mismatched browser.
* Flags: `--incognito`, `--user-data-dir=%LOCALAPPDATA%\FuzeKeys\tmp\gpm-<128-bit-random>` (non-default is mandatory on 136+), `--remote-debugging-pipe`, `--no-first-run`, `--no-default-browser-check`, `--disable-extensions`, `--disable-background-networking`, `--disable-sync`, `--disk-cache-size=1`, `--media-cache-size=1`, `--lang=en-US`.
* The agent **must not** pass `--enable-automation` and **must not** patch `navigator.webdriver`, spoof fingerprints, or otherwise try to evade bot detection. If Google refuses the session ("This browser or app may not be secure"), the run **fails closed** with `browser_refused`. Stealth is an explicit non-goal: it is both an arms race and a ToS escalation.
* Chrome runs inside a **Windows Job Object with `KILL_ON_JOB_CLOSE`**, so it dies with the agent (crash, kill, uninstall).
* Cleanup: delete the temp dir on exit; at every agent start, sweep stale `gpm-*` dirs. A post-run **leak audit** asserts the dir holds no `Cookies`, `Login Data`, `Web Data` or `History` database with content (incognito should never create them) and aborts loudly if it does.
* Do **not** call `Page.captureScreenshot`, `Tracing.*`, HAR/`Network.getResponseBody` bulk capture, or `DOM.getOuterHTML` on password pages; do **not** use the page's "Copy password" button (clipboard history and Windows cloud clipboard are disk-resident traces). Read the revealed value from the element once, into `[]byte`.
* Driver library: `chromedp` (MIT) configured with its default automation flags **removed**, or a ~500 line direct CDP-over-pipe client on the stdlib. Either is acceptable; the choice is an FKY-4 implementation detail but the flag list above is not.

### 3.3 Browser and profile variation (Chrome-version drift)

* Support **Chrome stable N through N-2** and current Edge. Gate on `Browser.getVersion`; do not sniff the UA string.
* Selectors live in versioned **recipes** shipped *inside* the signed binary (never fetched from the server, so a compromised server cannot redirect the scraper). Locator priority: ARIA role/name -> stable `data-*` / `jsname` hooks -> structure. Text-matching is avoided so non-English UI does not break it (`--lang=en-US` is also set for the browser chrome, though the Google account language still applies).
* On recipe mismatch the run **aborts** with `recipe_mismatch` and reports only a structural fingerprint (hash of the element-role tree, no text). **There is no LLM fallback** for parsing: sending the GPM DOM to a model would put plaintext secrets on an LLM data path, which is the thing the PII-tokenizer invariants exist to prevent (see threat model INV-1).
* **Enterprise policy** that disables incognito (`IncognitoModeAvailability`) or password management is detected (launch failure / policy read) and the run refuses. It never retries in a normal window.
* **Multiple Chrome profiles** are irrelevant (we use none). **Multiple signed-in Google accounts** are handled by the own-account check (section 6).

## 4. MFA, re-auth and challenges without storing secrets

The agent is a *bystander* to Google's own authentication.

1. The window opens at `https://passwords.google.com/`. If not signed in, Google redirects to `accounts.google.com`. The agent shows a tray notification ("Sign in to your Google account in the opened window") and **waits**. While the page is on an `accounts.google.com` origin the agent issues **no DOM reads, no input events, no screenshots**; it polls only the **URL host** until it returns to `passwords.google.com` (timeout 10 min, then `signin_timeout`).
2. 2-step verification, passkeys, security keys, device prompts, and "Verify it's you" re-auth at reveal time are all completed by the user in the window. The agent never sees or keeps any of it. It resumes automatically once the page is back on the password list.
3. Re-auth prompts are expected during a long run. A *rate* of re-auth prompts above 2 per 10 minutes is treated as a challenge signal (section 5.3) and stops the run.
4. CAPTCHA, "unusual traffic" interstitials and `/sorry/` pages are **never solved** and are terminal for the run (`challenge_blocked`).
5. No Google cookie, token, password or one-time code ever crosses the agent boundary. The agent's only knowledge of auth state is "which origin is the tab on".

**Consequence (O-1):** because the session is incognito (no persistence, by D-1's "no trace"), **a Google sign-in is needed at the start of every run**. The scrape itself is fully automated (D-1 holds for the scrape); Google's own authentication is not and must not be. Unattended scheduled GPM runs are therefore not offered in v1. They would require the owner to accept a persisted Google session on disk, which is a deliberate trade the owner has not made.

## 5. Throttling and rate limiting ("polite scraping")

Normative defaults (server policy may only make them **slower or lower**, never faster):

### 5.1 Cadence

| Parameter | Value |
|-----------|-------|
| Concurrency | 1 tab, 1 in-flight page action, no prefetch, no parallel tabs |
| Minimum gap between any two navigations | 4 s |
| Target pace per entry (open entry + reveal + read) | median **8 s**, log-normal jitter (sigma 0.35), clamped to **[4 s, 20 s]** (about 7 entries/min) |
| Hard ceiling | **12 page actions/min** via token bucket (burst 3), enforced in the driver regardless of recipe |
| Rest | after every **25 entries**, sleep uniformly **45-90 s** |
| Jitter source | `crypto/rand`-seeded; no fixed period anywhere |
| Run size | default **<= 1,000 entries**, hard cap 2,000; wall-clock cap **3 h** |
| Run frequency | **<= 1 GPM run per 24 h** and **<= 3 per 7 days** per device, enforced server-side at `POST /api/v1/collect/runs` |
| Start-time jitter (if ever scheduled) | +/- 30 min |

Indicative duration: 500 entries at ~8 s plus rests is ~75 minutes. That is intended: slow is the point.

### 5.2 Adaptive slow-down (AIMD)

If the median action latency over the last 10 actions exceeds 5 s, multiply all delays by 2 (up to x8). After every 25 clean entries multiply by 0.9 back toward 1.0. Never go below the defaults.

### 5.3 Challenge / block signals and backoff

Signals (any one is terminal for the run): HTTP 429 or 403 on a `passwords.google.com` XHR observed via CDP `Network` events; navigation to a `/sorry/` path; a reCAPTCHA frame or `accounts.google.com/.../challenge` that is not the user's own sign-in step; "unusual traffic" text; more than 2 re-auth prompts in 10 min; a single navigation stalled > 30 s twice in a row.

Response: stop issuing requests **immediately**, close the run with outcome `blocked` and a `block_reason` code, discard in-memory plaintext, close the browser. **No retry within the run.**

Cool-down is **server-authoritative** (the agent has no disk to remember it, and a tampered client must not be able to skip it). `POST /api/v1/collect/runs` for source `gpm_web` returns `429` + `Retry-After` until `cooldown_until`:

| Consecutive blocked runs | Cool-down |
|--------------------------|-----------|
| 1 | 30 min |
| 2 | 4 h |
| 3 | 24 h |
| 4 | 7 days **and the circuit breaker opens**: the GPM source is disabled for the device until the user re-enables it in the portal |

A successful (even partial, non-blocked) run resets the counter.

## 6. Own-account-only enforcement

Defence in depth; each control independently prevents scraping someone else's account.

1. **No server-supplied targets.** Origins, URLs, recipes and selectors are compiled into the signed binary. The server can arm a run for a *source type* (`gpm_web`, `wincred`); it cannot give the agent a URL, script, selector or account. A compromised FuzeKeys server therefore cannot turn the fleet into a scraper.
2. **Origin allowlist enforced in the browser.** CDP `Fetch.requestPaused` blocks any request outside `passwords.google.com`, `accounts.google.com`, `myaccount.google.com`, `ogs.google.com`, `www.gstatic.com`, `fonts.gstatic.com`, `www.google.com` (sign-in assets only). Everything else is failed with `BlockedByClient`.
3. **Expected account binding.** At pairing the user declares the Google account they intend to collect (`expected_google_account`), stored server-side and delivered to the agent per run. Before any entry is read the agent verifies the signed-in account identity from the account chip equals it (case-folded, comparison done in memory, never logged). Mismatch -> `account_mismatch`, abort.
4. **Single-account sessions only.** If the account chooser shows more than one signed-in account, or the "add account" flow is entered, abort (`ambiguous_account`). The agent never switches accounts.
5. **No credential entry.** The agent has no code path that types into `accounts.google.com`. Own-account proof is the user's ability to complete Google's sign-in themselves.
6. **Interactive user only.** Run only in the interactive logon session of the Windows user who paired the device (the DPAPI-protected device key makes another Windows user's session unable to use the pairing at all). Refuse to run as SYSTEM or from a service/RDP-shadow context.
7. **Managed (Workspace) accounts** require an explicit portal attestation ("I am permitted to export this account's saved passwords"); default for non-`gmail.com`/`googlemail.com` accounts is *blocked*. Employer policy is the user's and the employer's call, not ours to bypass.
8. **Consent record.** Pairing with `gpm_web` enabled requires the user to accept a consent text (own account, throttling, Google ToS risk). The acceptance is stored with the device.

## 7. In-memory only, no secret trace on local disk

| Disk-leak channel | Control |
|-------------------|---------|
| Browser profile (cookies, cache, history, Login Data) | Incognito + non-default throw-away dir + tiny caches + job object + sweep-on-start + post-run leak audit |
| Agent process memory -> pagefile | Secret values only as `[]byte` in a `Secret` type; `VirtualLock` on the working buffer (best effort); zeroise after seal and on every error path; never convert to `string`. **Preflight: refuse to run if the system drive is not BitLocker/Device-Encryption protected** unless the user explicitly acknowledges (pagefile/hiberfil are then ciphertext) |
| Hibernation / sleep mid-run | Request `ES_SYSTEM_REQUIRED` while running; on `PBT_APMSUSPEND` zero buffers, kill the browser, abort the run (`suspended`) |
| Crash dumps / WER | `SetErrorMode(SEM_FAILCRITICALERRORS \| SEM_NOGPFAULTERRORBOX)`; per-user WER exclusion for the agent exe; `GOTRACEBACK=none` in release builds; top-level `recover()` logs only the error class |
| Logs | Typed, allow-listed fields only; `Secret` implements `slog.LogValuer` returning `[redacted]` and `MarshalJSON` returning an error; no format-string logging of item data (see threat model INV-3) |
| Clipboard | Never used |
| Screenshots / tracing | Never captured. (Windows Recall excludes private-browsing windows in supported browsers; we rely on incognito and treat this as *inferred*, to be verified on a Copilot+ PC in FKY-4) |
| Telemetry | Counters and reason codes only. No origins, usernames or counts that identify specific entries |
| Network | TLS only, to the single configured API origin (dial allowlist in the HTTP transport); no proxies from environment; no DNS-over-anything else |

Mandatory acceptance test (FKY-4): the **canary test**. Run a full scrape against a local mock of the GPM pages whose entries contain random canary strings. After the run, search the temp dir, `%LOCALAPPDATA%\FuzeKeys`, `%TEMP%`, the WER/crash-dump dirs and the agent log for the canaries (UTF-8 and UTF-16LE). Any hit fails the build.

## 8. What is collected

Per entry: `origin` (host as shown), `username`, `password`, `note` if present, `source = gpm_web`, `collected_at`. GPM exposes no TOTP seed. Each entry is canonicalised, sealed on its own (ADR-003) as soon as it is read, and uploaded in batches of <= 25 so little is ever resident.

## 9. Risks and consequences

* **R-1 Google ToS / account action.** Automated access to Google properties may violate Google's terms and could draw account restrictions. This is a product/legal risk to the user's Google account, not a vulnerability. Mitigations are the throttle, stop-on-challenge and the consent text; it should still get an owner/legal look before GA. (Flagged, not re-litigated.)
* **R-2 Fragility.** Any UI change breaks the recipe. Accepted: it fails closed and reports a structural fingerprint.
* **R-3 Looks like an infostealer to AV/EDR.** Mitigations in ADR-002 (signing, open source, no network except FuzeKeys, visible UI).
* **R-4 Same-user malware** can read the Chrome process memory during a run. Accepted and documented; the run is short and incognito.

## 10. Acceptance criteria for FKY-4 (derived)

1. Canary test passes (no plaintext on disk, including UTF-16LE).
2. Throttle test: a fake clock proves the ceiling (<=12 actions/min), the 4 s navigation floor, the rest after 25 entries, and AIMD behaviour.
3. Each block signal in 5.3 stops the run within one action and produces `blocked`.
4. Origin allowlist test: a mock page that tries to load an off-list origin is blocked.
5. Account mismatch / multi-account / managed-account cases abort.
6. No code path imports an HTTP client targeting anything but the API origin, nor any LLM SDK (depguard / import-allowlist lint).
7. Leak audit and Job Object kill verified by killing the agent mid-run.
