import React from 'react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
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
export default function MfeApp() {
  return (
    <MemoryRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: { background: '#363636', color: '#fff' },
        }}
      />
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
    </MemoryRouter>
  );
}
