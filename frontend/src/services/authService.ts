/**
 * FuzeKeys' own `/api/v1/auth/*` surface.
 *
 * This used to be the login/register client: it POSTed an email, a password
 * and a master key to FuzeKeys' backend, which minted its own JWT. All of that
 * is gone — authentication belongs to the FuzeFront Security API (see
 * `securityClient.ts`), and FuzeKeys stores no password.
 *
 * What remains is the part that was always FuzeKeys' own: the encrypted vault
 * and its master key. The master key is a DOMAIN secret — it decrypts the
 * vault. It was never an authentication factor; it just happened to be
 * collected on the login form. Splitting it out preserves the capability (you
 * still cannot read a secret without it) while letting FuzeFront own identity.
 */

import { getStoredToken } from './securityClient'

/** Same-origin, exactly like the security client. Never an absolute host. */
const API_BASE = '/api/v1'

export interface User {
  id: number
  username: string
  email: string
  first_name?: string
  last_name?: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  /** Whether this user has completed vault setup. */
  vault_initialized: boolean
}

export interface VaultStatus {
  vault_initialized: boolean
  vault_unlocked: boolean
}

export class FuzeKeysApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'FuzeKeysApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  // The bearer token is the FuzeFront-minted session token. FuzeKeys' backend
  // does not verify it locally — it forwards it to GET /v1/security/session.
  const token = getStoredToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  })

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let body: any = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    throw new FuzeKeysApiError(
      response.status,
      body?.detail || `Request failed (${response.status})`
    )
  }
  return body as T
}

export const authService = {
  /** `GET /api/v1/auth/me` — the FuzeKeys-local projection of the caller. */
  getCurrentUser(): Promise<User> {
    return request<User>('/auth/me')
  },

  /** `POST /api/v1/auth/logout` — delegates to `DELETE /v1/security/session`. */
  logout(): Promise<void> {
    return request<void>('/auth/logout', { method: 'POST' })
  },

  /** `GET /api/v1/auth/vault` — is the vault set up, and is it unlocked? */
  getVaultStatus(): Promise<VaultStatus> {
    return request<VaultStatus>('/auth/vault')
  },

  /** `POST /api/v1/auth/vault/setup` — set the master key for the first time. */
  setupVault(masterKey: string): Promise<VaultStatus> {
    return request<VaultStatus>('/auth/vault/setup', {
      method: 'POST',
      body: JSON.stringify({ master_key: masterKey }),
    })
  },

  /** `POST /api/v1/auth/vault/unlock` — unlock the vault with the master key. */
  unlockVault(masterKey: string): Promise<VaultStatus> {
    return request<VaultStatus>('/auth/vault/unlock', {
      method: 'POST',
      body: JSON.stringify({ master_key: masterKey }),
    })
  },
}
