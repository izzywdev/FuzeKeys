/**
 * Session state for FuzeKeys.
 *
 * Before: this context owned a login form's worth of logic — it POSTed
 * email + password + master key to FuzeKeys' backend and stashed a
 * FuzeKeys-minted JWT in localStorage.
 *
 * Now: FuzeKeys holds no credentials at all. The session comes from the
 * FuzeFront Security API — either inherited from the host shell (portal mode,
 * where the user is already signed in) or established by FuzeFront's own
 * sign-in surface (standalone mode). This context just reads it, exposes it,
 * and hands logout back to FuzeFront.
 *
 * `vault` is tracked separately and deliberately: the master key unlocks
 * FuzeKeys' encrypted store and has nothing to do with who you are. Being
 * signed in does NOT mean the vault is open.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from 'react'

import { authService, User, VaultStatus } from '../services/authService'
import {
  Identity,
  SecurityApiError,
  createSession,
  deleteSession,
  exchangeSessionCode,
  getSession,
  getStoredToken,
  setStoredToken,
  startSocialLogin,
  SocialProvider,
} from '../services/securityClient'

interface AuthContextType {
  /** Normalized FuzeFront identity, or null when not signed in. */
  identity: Identity | null
  /** FuzeKeys-local projection of the signed-in principal. */
  user: User | null
  isAuthenticated: boolean
  loading: boolean
  /** Vault (master key) state — independent of being signed in. */
  vault: VaultStatus
  /**
   * Password sign-in via `POST /v1/security/session`.
   * Returns 'mfa_required' when FuzeFront wants step-up; the caller must send
   * the user to FuzeFront's sign-in surface to complete it — FuzeKeys does not
   * implement MFA challenge UI.
   */
  signIn: (email: string, password: string) => Promise<'authenticated' | 'mfa_required'>
  /** Social sign-in via `GET /v1/security/social/{provider}/start` (navigates). */
  signInWithProvider: (provider: SocialProvider) => void
  /** Exchange a social-callback code via `POST /v1/security/session/exchange`. */
  completeSocialSignIn: (code: string) => Promise<'authenticated' | 'mfa_required'>
  /** Revoke the session (FuzeFront `DELETE /v1/security/session`). */
  signOut: () => Promise<void>
  unlockVault: (masterKey: string) => Promise<void>
  setupVault: (masterKey: string) => Promise<void>
  refresh: () => Promise<void>
}

const CLOSED_VAULT: VaultStatus = { vault_initialized: false, vault_unlocked: false }

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [vault, setVault] = useState<VaultStatus>(CLOSED_VAULT)
  const [loading, setLoading] = useState(true)

  const clearSession = useCallback(() => {
    setStoredToken(null)
    setIdentity(null)
    setUser(null)
    setVault(CLOSED_VAULT)
  }, [])

  /** Hydrate from whatever token we have: FuzeFront first, then FuzeKeys. */
  const hydrate = useCallback(async () => {
    if (!getStoredToken()) {
      clearSession()
      setLoading(false)
      return
    }

    try {
      const session = await getSession()
      setIdentity(session.identity)

      // FuzeKeys' own projection: the integer id its vault relations use, plus
      // vault status. A failure here is NOT a sign-out — the FuzeFront session
      // is valid; it is FuzeKeys that is unhappy.
      try {
        const [me, vaultStatus] = await Promise.all([
          authService.getCurrentUser(),
          authService.getVaultStatus(),
        ])
        setUser(me)
        setVault(vaultStatus)
      } catch {
        setUser(null)
        setVault(CLOSED_VAULT)
      }
    } catch (error) {
      // Only a genuine rejection clears the session. A 503 means FuzeFront is
      // unreachable, which is not evidence the user is signed out.
      if (error instanceof SecurityApiError && error.status === 401) {
        clearSession()
      } else {
        setIdentity(null)
        setUser(null)
      }
    } finally {
      setLoading(false)
    }
  }, [clearSession])

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  const adoptResult = useCallback(
    async (
      result: Awaited<ReturnType<typeof createSession>>
    ): Promise<'authenticated' | 'mfa_required'> => {
      // Narrow on the discriminator before touching `token` — an MFA-enabled
      // account otherwise looks like a successful login with no token.
      if (result.status !== 'authenticated') return 'mfa_required'
      setStoredToken(result.token)
      await hydrate()
      return 'authenticated'
    },
    [hydrate]
  )

  const signIn = useCallback(
    async (email: string, password: string) => adoptResult(await createSession(email, password)),
    [adoptResult]
  )

  const completeSocialSignIn = useCallback(
    async (code: string) => adoptResult(await exchangeSessionCode(code)),
    [adoptResult]
  )

  const signInWithProvider = useCallback((provider: SocialProvider) => {
    startSocialLogin(provider)
  }, [])

  const signOut = useCallback(async () => {
    try {
      // FuzeKeys' logout forwards to FuzeFront's revoke, so the token is
      // actually invalidated rather than merely forgotten.
      await authService.logout()
    } catch {
      // Best effort — fall back to revoking directly.
      try {
        await deleteSession()
      } catch {
        /* the token is discarded either way */
      }
    } finally {
      clearSession()
    }
  }, [clearSession])

  const unlockVault = useCallback(async (masterKey: string) => {
    setVault(await authService.unlockVault(masterKey))
  }, [])

  const setupVault = useCallback(async (masterKey: string) => {
    setVault(await authService.setupVault(masterKey))
  }, [])

  const value = useMemo<AuthContextType>(
    () => ({
      identity,
      user,
      isAuthenticated: identity !== null,
      loading,
      vault,
      signIn,
      signInWithProvider,
      completeSocialSignIn,
      signOut,
      unlockVault,
      setupVault,
      refresh: hydrate,
    }),
    [
      identity,
      user,
      loading,
      vault,
      signIn,
      signInWithProvider,
      completeSocialSignIn,
      signOut,
      unlockVault,
      setupVault,
      hydrate,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
