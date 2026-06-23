import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Identities from './pages/Identities';
import Accounts from './pages/Accounts';
import Chat from './pages/Chat';
import SitesDatabase from './components/SitesDatabase';
import { GoogleIntegrationPage } from './integrations/google';
import './index.css';

function App() {
  return (
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
          {/* Demo Routes - No Authentication Required */}
          <Route path="/" element={<Layout />}>
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
  );
}

export default App; 