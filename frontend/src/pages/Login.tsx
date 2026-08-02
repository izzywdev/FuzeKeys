/**
 * Sign-in surface — a REDIRECT, not a form.
 *
 * FuzeKeys used to render its own email + password + master-key form. It no
 * longer does, and the deletion is the point: a product that renders a
 * credential form has taken ownership of authentication, and every such form
 * is another place for password handling, MFA, social login, lockout and reset
 * to be got subtly wrong. Authentication is FuzeFront's.
 *
 * In portal mode (FuzeKeys mounted as a Module-Federation remote) the user is
 * already signed in and never sees this. In standalone mode this hands them to
 * FuzeFront's sign-in surface and comes back.
 *
 * NOTE: `@fuzefront/identity-ui` is NOT used here because it does not export a
 * sign-in or sign-up component — it is member / invite / API-token MANAGEMENT
 * UI (`IdentityPage`, `MembersTable`, `InviteModal`, `TokenList`). There is no
 * published FuzeFront package exporting a reusable sign-in screen, so the
 * hand-off below is the closest thing to "don't hand-roll an auth screen" that
 * the platform currently makes possible. Raised as a contract gap in the PR.
 */

import React, { useEffect, useState } from 'react'

import { useAuth } from '../contexts/AuthContext'
import { AuthMethods, getAuthMethods } from '../services/securityClient'

/**
 * Where FuzeFront's sign-in lives. Same-origin by construction: FuzeKeys is
 * served from the FuzeFront portal origin in portal mode and behind the same
 * ingress in standalone mode, so an absolute host would break under local TLS.
 */
const FUZEFRONT_SIGN_IN_PATH = '/login'

function redirectToFuzeFront(path: string): void {
  const returnTo = encodeURIComponent(window.location.href)
  window.location.href = `${path}?redirect=${returnTo}`
}

const Login: React.FC = () => {
  const { isAuthenticated, loading } = useAuth()
  const [methods, setMethods] = useState<AuthMethods | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Ask FuzeFront which affordances exist. FuzeKeys does not know or care
    // which identity provider is behind them.
    getAuthMethods()
      .then(setMethods)
      .catch(() => setError('Could not reach the sign-in service.'))
  }, [])

  useEffect(() => {
    if (!loading && !isAuthenticated && methods) {
      redirectToFuzeFront(FUZEFRONT_SIGN_IN_PATH)
    }
  }, [loading, isAuthenticated, methods])

  if (isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <p className="text-gray-700">You are signed in.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6 text-center">
        <h2 className="text-3xl font-extrabold text-gray-900">Sign in to FuzeKeys</h2>

        {error ? (
          <>
            <p role="alert" className="text-red-600">
              {error}
            </p>
            <button
              type="button"
              className="btn-primary w-full"
              onClick={() => redirectToFuzeFront(FUZEFRONT_SIGN_IN_PATH)}
            >
              Continue to sign in
            </button>
          </>
        ) : (
          <>
            <p className="text-gray-600">
              FuzeKeys uses your FuzeFront account. Redirecting you to sign in…
            </p>
            <button
              type="button"
              className="btn-primary w-full"
              onClick={() => redirectToFuzeFront(FUZEFRONT_SIGN_IN_PATH)}
            >
              Continue to sign in
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default Login
