/**
 * Client for the FuzeFront Security API.
 *
 * This is the ONLY thing FuzeKeys knows about authentication. There is no
 * identity-provider SDK here, no issuer URL, no OIDC client config, no policy
 * engine — those are FuzeFront's private implementation details, deliberately
 * invisible from a consuming product.
 *
 * Every path below is taken verbatim from the published contract
 * (`@fuzefront/security-client` / `packages/security/openapi.yaml`). Nothing is
 * invented: if FuzeKeys ever needs a capability with no operation in that
 * contract, the fix is to raise a contract gap with FuzeFront, never to reach
 * around it.
 *
 * WHY NOT `import { ... } from '@fuzefront/security-client'`? The package is
 * published to a restricted GitHub Packages registry that this app's build does
 * not authenticate against, so it cannot be a dependency yet. The shapes below
 * are therefore a hand-mirror of that package's exported types, marked so they
 * can be swapped for the real import in one commit once the registry
 * credentials are wired (the package also declares a React 19 peer, which this
 * app does not yet satisfy — see the PR description).
 */

// ── Contract types (mirrored from @fuzefront/security-client) ────────────────

/** `AuthMode` — provider-neutral token formats. Never a vendor name. */
export type AuthMode = 'legacy-hs256' | 'federated-jwks'

/** `SocialProvider` — extensible; `google` is first. */
export type SocialProvider = 'google'

export type MfaFactorType = 'totp' | 'sms' | 'email' | 'webauthn'

/** `Identity` — the contract keystone. */
export interface Identity {
  userId: string
  tenantId: string | null
  roles: string[]
  email?: string
  authMode: AuthMode
  issuedAt?: number
  expiresAt?: number
  issuer?: string
}

export interface SecurityUser {
  id: string
  email: string
  firstName?: string
  lastName?: string
  roles: string[]
}

export interface SessionInfo {
  identity: Identity
  user: SecurityUser
}

/** `AuthMethods` — capability descriptor driving which affordances to render. */
export interface AuthMethods {
  password: boolean
  social: SocialProvider[]
  mfa: { enabled: boolean; types: MfaFactorType[] }
  verification: { email: boolean; sms: boolean }
}

/** `SessionResult` — discriminated on `status`. Narrow before reading fields. */
export type SessionResult =
  | { status: 'authenticated'; token: string; sessionId?: string; user: SecurityUser }
  | {
      status: 'mfa_required'
      challengeId: string
      factors: { factorId: string; type: MfaFactorType }[]
    }

export interface EmailAvailability {
  available: boolean
  email: string
}

export interface AuthzDecision {
  allow: boolean
}

export interface ResourceRef {
  type: string
  key?: string
}

/** One `AuthzCheckRequest`, using the bare keys from registration/policy.json. */
export interface AuthzCheckRequest {
  subject: string
  tenant: string
  resource: ResourceRef
  action: string
  context?: Record<string, unknown>
}

export class SecurityApiError extends Error {
  readonly status: number
  readonly code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'SecurityApiError'
    this.status = status
    this.code = code
  }
}

// ── Transport ────────────────────────────────────────────────────────────────

/**
 * SAME-ORIGIN base, always.
 *
 * FuzeKeys runs both as a Module-Federation remote inside the FuzeFront host
 * and standalone behind its own ingress. In both cases the Security API is
 * reachable on the current origin. Hard-coding an absolute host would break
 * under local TLS (mixed content) and would pin the app to one environment.
 */
const SECURITY_BASE = '/v1/security'

const TOKEN_STORAGE_KEY = 'fuzefront.session.token'

export function getStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* storage unavailable (private mode); the session simply won't persist */
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { authenticated = false }: { authenticated?: boolean } = {}
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (authenticated) {
    const token = getStoredToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${SECURITY_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  })

  if (response.status === 204) return undefined as T

  let body: any = null
  const text = await response.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    throw new SecurityApiError(
      response.status,
      body?.message || body?.error || `Security API request failed (${response.status})`,
      body?.code
    )
  }

  return body as T
}

// ── Session (AuthN) ──────────────────────────────────────────────────────────

/** `GET /v1/security/session` — the current identity ("me"). */
export function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>('/session', { method: 'GET' }, { authenticated: true })
}

/**
 * `POST /v1/security/session` — password login.
 *
 * Returns a `SessionResult`; narrow on `status` before assuming a token, or an
 * MFA-enabled account silently appears to log in with `token === undefined`.
 */
export function createSession(email: string, password: string): Promise<SessionResult> {
  return request<SessionResult>('/session', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/** `POST /v1/security/session/exchange` — exchange a social-callback code. */
export function exchangeSessionCode(code: string): Promise<SessionResult> {
  return request<SessionResult>('/session/exchange', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

/** `DELETE /v1/security/session` — revoke the current session. */
export function deleteSession(): Promise<void> {
  return request<void>('/session', { method: 'DELETE' }, { authenticated: true })
}

/** `POST /v1/security/signup` — server-brokered account creation. */
export function signup(input: {
  email: string
  password: string
  firstName?: string
  lastName?: string
  tenantName?: string
}): Promise<{ token: string; sessionId?: string; user: SecurityUser }> {
  return request('/signup', { method: 'POST', body: JSON.stringify(input) })
}

/** `GET /v1/security/methods` — which auth affordances to render. */
export function getAuthMethods(): Promise<AuthMethods> {
  return request<AuthMethods>('/methods', { method: 'GET' })
}

/** `GET /v1/security/email-available` — inline signup-form availability check. */
export function getEmailAvailable(email: string): Promise<EmailAvailability> {
  return request<EmailAvailability>(
    `/email-available?email=${encodeURIComponent(email)}`,
    { method: 'GET' }
  )
}

/** `POST /v1/security/session/password/reset-request` — always 202, no enumeration. */
export function requestPasswordReset(email: string): Promise<void> {
  return request<void>('/session/password/reset-request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

/**
 * `GET /v1/security/social/{provider}/start` — begin social login.
 *
 * A 302 the browser must follow, so this navigates rather than fetches.
 * FuzeKeys does not know which providers exist; it renders whatever
 * `getAuthMethods().social` reports.
 */
export function startSocialLogin(provider: SocialProvider, redirectTo?: string): void {
  const target = redirectTo ?? window.location.href
  window.location.href = `${SECURITY_BASE}/social/${encodeURIComponent(
    provider
  )}/start?redirect_uri=${encodeURIComponent(target)}`
}

// ── AuthZ ────────────────────────────────────────────────────────────────────

/**
 * `POST /v1/security/authz/check` — one decision. Fail-closed.
 *
 * UI-side checks are for AFFORDANCES only (hide a button the user cannot use).
 * The backend re-checks every decision; nothing here is a security boundary.
 */
export async function authzCheck(
  identity: Identity,
  resource: ResourceRef,
  action: string
): Promise<boolean> {
  if (!identity.tenantId) return false // contract: fail closed with no tenant
  try {
    const decision = await request<AuthzDecision>(
      '/authz/check',
      {
        method: 'POST',
        body: JSON.stringify({
          subject: identity.userId,
          tenant: identity.tenantId,
          resource,
          action,
        }),
      },
      { authenticated: true }
    )
    return decision?.allow === true
  } catch {
    return false
  }
}

/**
 * `POST /v1/security/authz/bulk-check` — index-aligned decisions. Fail-closed.
 *
 * A length mismatch denies everything rather than mis-aligning decisions onto
 * the wrong resources.
 */
export async function authzBulkCheck(
  identity: Identity,
  checks: { resource: ResourceRef; action: string }[]
): Promise<boolean[]> {
  if (checks.length === 0) return []
  const denyAll = checks.map(() => false)
  if (!identity.tenantId) return denyAll
  if (checks.length > 200) {
    throw new Error('authz/bulk-check accepts at most 200 checks per call')
  }

  try {
    const body = await request<{ decisions: AuthzDecision[] }>(
      '/authz/bulk-check',
      {
        method: 'POST',
        body: JSON.stringify({
          checks: checks.map(c => ({
            subject: identity.userId,
            tenant: identity.tenantId,
            resource: c.resource,
            action: c.action,
          })),
        }),
      },
      { authenticated: true }
    )
    const decisions = body?.decisions
    if (!Array.isArray(decisions) || decisions.length !== checks.length) return denyAll
    return decisions.map(d => d?.allow === true)
  } catch {
    return denyAll
  }
}
