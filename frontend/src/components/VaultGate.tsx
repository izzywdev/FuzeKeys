/**
 * Master-key gate for the encrypted vault.
 *
 * The master key used to be a third field on the login form, submitted
 * alongside email and password. That conflated two unrelated things: proving
 * who you are (FuzeFront's job) and decrypting your vault (FuzeKeys' job, and
 * the reason this product exists).
 *
 * Delegating authentication to FuzeFront made that split unavoidable — but the
 * CAPABILITY is preserved exactly, not dropped: without the master key, the
 * vault stays locked and no secret is decrypted. It just happens after sign-in
 * now instead of during it.
 *
 * `VaultGate` renders its children only once the vault is open, prompting for
 * setup (first use) or unlock (every use after) as appropriate.
 */

import React, { ReactNode, useState } from 'react'

import { useAuth } from '../contexts/AuthContext'
import { FuzeKeysApiError } from '../services/authService'

interface VaultGateProps {
  children: ReactNode
}

export const VaultGate: React.FC<VaultGateProps> = ({ children }) => {
  const { loading, isAuthenticated, vault, unlockVault, setupVault } = useAuth()
  const [masterKey, setMasterKey] = useState('')
  const [confirmKey, setConfirmKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-600">Loading…</p>
      </div>
    )
  }

  // Not signed in is not this component's problem — routing sends the user to
  // FuzeFront's sign-in surface.
  if (!isAuthenticated) return <>{children}</>
  if (vault.vault_unlocked) return <>{children}</>

  const needsSetup = !vault.vault_initialized

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)

    if (needsSetup && masterKey !== confirmKey) {
      setError('The two master keys do not match.')
      return
    }

    setBusy(true)
    try {
      if (needsSetup) await setupVault(masterKey)
      else await unlockVault(masterKey)
      setMasterKey('')
      setConfirmKey('')
    } catch (err) {
      if (err instanceof FuzeKeysApiError) {
        setError(err.message)
      } else {
        setError('Could not open the vault. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6">
        <div className="text-center">
          <h2 className="text-3xl font-extrabold text-gray-900">
            {needsSetup ? 'Set up your vault' : 'Unlock your vault'}
          </h2>
          <p className="mt-2 text-gray-600">
            {needsSetup
              ? 'Choose a master key. It encrypts everything in your vault and is never sent to FuzeFront — if you lose it, the data cannot be recovered.'
              : 'Your master key decrypts your stored identities and credentials.'}
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="off"
            className="input-field w-full"
            placeholder="Master key"
            aria-label="Master key"
            value={masterKey}
            onChange={e => setMasterKey(e.target.value)}
          />

          {needsSetup && (
            <input
              type="password"
              required
              minLength={8}
              autoComplete="off"
              className="input-field w-full"
              placeholder="Confirm master key"
              aria-label="Confirm master key"
              value={confirmKey}
              onChange={e => setConfirmKey(e.target.value)}
            />
          )}

          {error && (
            <p role="alert" className="text-red-600 text-sm">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? 'Working…' : needsSetup ? 'Create vault' : 'Unlock'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default VaultGate
