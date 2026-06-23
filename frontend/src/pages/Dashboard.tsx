import React from 'react';
import { Link } from 'react-router-dom';

const Dashboard: React.FC = () => {
  return (
    <div className="px-4 py-6 sm:px-0">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Welcome to FuzeKeys</h1>
        <p className="text-gray-600 text-lg">Your intelligent identity and account management system</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {/* Quick Stats */}
        <Link to="/identities" className="card hover:shadow-lg transition-shadow duration-200 cursor-pointer group">
          <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-primary-600">Identities</h3>
          <p className="text-3xl font-bold text-primary-600 mb-2">2</p>
          <p className="text-gray-600 text-sm">Digital identities ready to use</p>
          <div className="mt-2 text-xs text-primary-600 opacity-0 group-hover:opacity-100 transition-opacity">
            Click to view all identities →
          </div>
        </Link>
        
        <Link to="/accounts" className="card hover:shadow-lg transition-shadow duration-200 cursor-pointer group">
          <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-primary-600">Accounts</h3>
          <p className="text-3xl font-bold text-primary-600 mb-2">2</p>
          <p className="text-gray-600 text-sm">Automated accounts created</p>
          <div className="mt-2 text-xs text-primary-600 opacity-0 group-hover:opacity-100 transition-opacity">
            Click to view all accounts →
          </div>
        </Link>
        
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Success Rate</h3>
          <p className="text-3xl font-bold text-green-600 mb-2">95%</p>
          <p className="text-gray-600 text-sm">Automation success rate</p>
        </div>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="card">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">🤖 AI-Powered Automation</h3>
          <p className="text-gray-600 mb-4">
            Our intelligent system learns website signup processes and creates reusable automation scripts.
          </p>
          <Link to="/chat" className="btn-primary inline-block">
            Try Chat Assistant
          </Link>
        </div>
        
        <div className="card">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">🔐 Secure Identity Management</h3>
          <p className="text-gray-600 mb-4">
            Create and manage multiple digital identities with end-to-end encryption for all sensitive data.
          </p>
          <Link to="/identities" className="btn-primary inline-block">
            Manage Identities
          </Link>
        </div>
      </div>

      {/* Demo Notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-2">🎮 Demo Mode</h3>
        <p className="text-blue-800 mb-4">
          You're currently viewing a demonstration of FuzeKeys. In the full version, you would:
        </p>
        <ul className="list-disc list-inside text-blue-800 space-y-1">
          <li>Set up secure authentication with master key encryption</li>
          <li>Create real automation scripts for website signups</li>
          <li>Store encrypted account credentials and API keys</li>
          <li>Use AI-powered web scraping for signup analysis</li>
        </ul>
      </div>
    </div>
  );
};

export default Dashboard; 