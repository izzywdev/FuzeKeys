import React from 'react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import VaultGate from './components/VaultGate';
import { AuthProvider } from './contexts/AuthContext';
import Dashboard from './pages/Dashboard';
import Identities from './pages/Identities';
import Accounts from './pages/Accounts';
import Chat from './pages/Chat';
import SitesDatabase from './components/SitesDatabase';
import { GoogleIntegrationPage } from './integrations/google';
import './index.css';

// MFE entry point — loaded by FuzeFront via module federation.
// Uses MemoryRouter so nested routes work without conflicting with the host's BrowserRouter.
// FuzeFront provides chrome (nav, topbar); this renders only the content area.
//
// There is deliberately NO sign-in route here. In portal mode the user is
// already authenticated by the FuzeFront host and the session token is read via
// the FuzeFront Security API (`GET /v1/security/session`) on the same-origin
// API base. A remote that renders its own login screen inside an already
// authenticated shell is a bug, not a feature.
//
// `VaultGate` still applies: the master key decrypts FuzeKeys' store and is a
// FuzeKeys concern, entirely separate from who the signed-in user is.
export default function MfeApp() {
  return (
    <AuthProvider>
      <MemoryRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: { background: '#363636', color: '#fff' },
          }}
        />
        <VaultGate>
          <Routes>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/identities" element={<Identities />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/sites" element={<SitesDatabase />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/integrations/google" element={<GoogleIntegrationPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </VaultGate>
      </MemoryRouter>
    </AuthProvider>
  );
}
