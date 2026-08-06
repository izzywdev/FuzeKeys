/**
 * Standalone FuzeKeys app (not the Module-Federation remote — see MfeApp.tsx).
 *
 * Session state comes from `AuthProvider`, which reads the FuzeFront Security
 * API. FuzeKeys renders no credential form of its own: `/login` and `/register`
 * hand off to FuzeFront's sign-in and sign-up surfaces.
 *
 * `VaultGate` sits between authentication and the app content because they are
 * genuinely different gates — being signed in tells you who you are; the master
 * key is what decrypts the vault.
 */

import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Layout from './components/Layout';
import VaultGate from './components/VaultGate';
import { AuthProvider } from './contexts/AuthContext';
import Dashboard from './pages/Dashboard';
import Identities from './pages/Identities';
import Accounts from './pages/Accounts';
import Chat from './pages/Chat';
import Login from './pages/Login';
import Register from './pages/Register';
import SitesDatabase from './components/SitesDatabase';
import { GoogleIntegrationPage } from './integrations/google';
import './index.css';

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="App">
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: '#363636',
                color: '#fff',
              },
            }}
          />

          <Routes>
            {/* Hand-off surfaces — these redirect to FuzeFront, they are not forms. */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            <Route
              path="/"
              element={
                <VaultGate>
                  <Layout />
                </VaultGate>
              }
            >
              <Route index element={<Navigate to="/dashboard" />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="identities" element={<Identities />} />
              <Route path="accounts" element={<Accounts />} />
              <Route path="sites" element={<SitesDatabase />} />
              <Route path="chat" element={<Chat />} />
              <Route path="integrations/google" element={<GoogleIntegrationPage />} />
            </Route>

            {/* Catch all route */}
            <Route path="*" element={<Navigate to="/dashboard" />} />
          </Routes>
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;
