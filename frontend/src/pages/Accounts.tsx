import React, { useState, useEffect } from 'react';
import { PlusIcon, FunnelIcon } from '@heroicons/react/24/outline';
import SiteSelector from '../components/SiteSelector';

interface StageStatus {
  stage_type: string;
  stage_name: string;
  status: string;
  attempts: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

interface Account {
  id: number;
  website_name: string;
  website_url: string;
  identity_id: number;
  identity_name: string;
  is_active: boolean;
  signup_completed: boolean;
  created_at: string;
  stages: StageStatus[];
}

interface Site {
  id: string;
  name: string;
  url: string;
  icon: string;
  category: string;
  description: string;
  difficulty: 'Easy' | 'Medium' | 'Hard';
  features: string[];
}

const Accounts: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [showSiteSelector, setShowSiteSelector] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterIdentity, setFilterIdentity] = useState<string>('all');

  useEffect(() => {
    fetchAccounts();
  }, []);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/accounts');
      if (!response.ok) {
        throw new Error('Failed to fetch accounts');
      }
      const data = await response.json();
      setAccounts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (account: Account) => {
    if (account.signup_completed) {
      return <span className="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">Active</span>;
    } else if (account.is_active) {
      return <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">In Progress</span>;
    } else {
      return <span className="bg-red-100 text-red-800 px-2 py-1 rounded-full text-xs">Failed</span>;
    }
  };

  const getStageStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return <span className="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">✓</span>;
      case 'in_progress':
        return <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">⟳</span>;
      case 'failed':
        return <span className="bg-red-100 text-red-800 px-2 py-1 rounded-full text-xs">✗</span>;
      case 'pending':
        return <span className="bg-gray-100 text-gray-800 px-2 py-1 rounded-full text-xs">○</span>;
      case 'skipped':
        return <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full text-xs">—</span>;
      default:
        return <span className="bg-gray-100 text-gray-800 px-2 py-1 rounded-full text-xs">?</span>;
    }
  };

  const handleSiteSelect = (site: Site, identityId: number) => {
    console.log('Selected site:', site, 'with identity:', identityId);
    setShowSiteSelector(false);
    // TODO: Implement account creation logic
  };

  const filteredAccounts = accounts.filter(account => {
    if (filterStatus !== 'all') {
      const status = account.signup_completed ? 'active' : account.is_active ? 'in_progress' : 'failed';
      if (status !== filterStatus) return false;
    }
    if (filterIdentity !== 'all' && account.identity_name !== filterIdentity) {
      return false;
    }
    return true;
  });

  const uniqueIdentityNames = Array.from(new Set(accounts.map(account => account.identity_name)));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="text-red-600 mb-4">Error: {error}</div>
        <button onClick={fetchAccounts} className="btn-primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Accounts</h1>
          <p className="text-gray-600">Manage your automated accounts across different platforms</p>
        </div>
        <button
          onClick={() => setShowSiteSelector(true)}
          className="btn-primary flex items-center space-x-2"
        >
          <PlusIcon className="h-5 w-5" />
          <span>Create Account</span>
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-center space-x-4">
          <FunnelIcon className="h-5 w-5 text-gray-400" />
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Status:</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1 text-sm"
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="in_progress">In Progress</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Identity:</label>
            <select
              value={filterIdentity}
              onChange={(e) => setFilterIdentity(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1 text-sm"
            >
              <option value="all">All</option>
              {uniqueIdentityNames.map(identity => (
                <option key={identity} value={identity}>{identity}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Accounts Table */}
      <div className="bg-white shadow-sm rounded-lg border border-gray-200">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Website
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Identity
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredAccounts.map((account) => (
                <tr key={account.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="flex-shrink-0 h-8 w-8">
                        <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center">
                          <span className="text-primary-600 font-medium text-sm">
                            {account.website_name.charAt(0)}
                          </span>
                        </div>
                      </div>
                      <div className="ml-4">
                        <div className="text-sm font-medium text-gray-900">{account.website_name}</div>
                        <div className="text-sm text-gray-500">{account.website_url}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {account.identity_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getStatusBadge(account)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(account.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button
                      onClick={() => setSelectedAccount(account)}
                      className="text-primary-600 hover:text-primary-900 mr-3"
                    >
                      View
                    </button>
                    <button className="text-gray-600 hover:text-gray-900">
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Account Details Modal */}
      {selectedAccount && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">{selectedAccount.website_name} Account Details</h3>
            
            {/* Basic Account Info */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700">Website</label>
                <p className="text-gray-900">{selectedAccount.website_name}</p>
                <p className="text-sm text-gray-500">{selectedAccount.website_url}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Identity Used</label>
                <p className="text-gray-900">{selectedAccount.identity_name}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Status</label>
                {getStatusBadge(selectedAccount)}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Created</label>
                <p className="text-gray-900">{new Date(selectedAccount.created_at).toLocaleDateString()}</p>
              </div>
            </div>

            {/* Stages Details */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-3">Account Creation Stages</label>
              <div className="space-y-3">
                {selectedAccount.stages.map((stage, index) => (
                  <div key={index} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium text-gray-900">{stage.stage_name}</h4>
                      {getStageStatusBadge(stage.status)}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-gray-600">Attempts:</span> {stage.attempts}
                      </div>
                      {stage.started_at && (
                        <div>
                          <span className="text-gray-600">Started:</span> {new Date(stage.started_at).toLocaleString()}
                        </div>
                      )}
                      {stage.completed_at && (
                        <div>
                          <span className="text-gray-600">Completed:</span> {new Date(stage.completed_at).toLocaleString()}
                        </div>
                      )}
                    </div>
                    {stage.error_message && (
                      <div className="mt-2 text-sm text-red-600">
                        <span className="font-medium">Error:</span> {stage.error_message}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end space-x-3">
              <button 
                onClick={() => setSelectedAccount(null)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Close
              </button>
              <button className="btn-primary">
                Manage Account
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Site Selector Modal */}
      {showSiteSelector && (
        <SiteSelector 
          onSiteSelect={handleSiteSelect} 
          onClose={() => setShowSiteSelector(false)}
        />
      )}
    </div>
  );
};

export default Accounts; 