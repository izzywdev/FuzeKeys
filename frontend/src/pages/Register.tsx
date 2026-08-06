/**
 * Sign-up surface — a REDIRECT, not a form.
 *
 * Account creation is `POST /v1/security/signup` on the FuzeFront Security
 * API, driven by FuzeFront's own branded sign-up screen. FuzeKeys does not
 * collect an email, a password, or anything else that would make it an
 * enrollment surface.
 *
 * See `Login.tsx` for why `@fuzefront/identity-ui` is not used here.
 */

import React, { useEffect, useState } from 'react'

import { useAuth } from '../contexts/AuthContext'
import { AuthMethods, getAuthMethods } from '../services/securityClient'

const FUZEFRONT_SIGN_UP_PATH = '/signup'

function redirectToFuzeFront(path: string): void {
  const returnTo = encodeURIComponent(window.location.href)
  window.location.href = `${path}?redirect=${returnTo}`
}

const Register: React.FC = () => {
  const { isAuthenticated, loading } = useAuth()
  const [methods, setMethods] = useState<AuthMethods | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAuthMethods()
      .then(setMethods)
      .catch(() => setError('Could not reach the sign-up service.'))
  }, [])

  useEffect(() => {
    if (!loading && !isAuthenticated && methods) {
      redirectToFuzeFront(FUZEFRONT_SIGN_UP_PATH)
    }
  }, [loading, isAuthenticated, methods])

  if (isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <p className="text-gray-700">You already have an account and are signed in.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6 text-center">
        <h2 className="text-3xl font-extrabold text-gray-900">Create a FuzeFront account</h2>

        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}

        <p className="text-gray-600">
          FuzeKeys uses your FuzeFront account. You will set up your encrypted vault
          after signing in.
        </p>

        <button
          type="button"
          className="btn-primary w-full"
          onClick={() => redirectToFuzeFront(FUZEFRONT_SIGN_UP_PATH)}
        >
          Continue to sign up
        </button>
      </div>
    </div>
  )
}

export default Register
