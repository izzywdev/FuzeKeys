import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import apiClient from '../services/apiClient';

/** Mirrors the backend DashboardStats model (GET /api/v1/dashboard/stats). */
interface DashboardStats {
  identities: number;
  accounts: number;
  /** Percent, 0-100. 0 when no automation job has finished yet. */
  successRate: number;
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; stats: DashboardStats };

const isValidStats = (data: unknown): data is DashboardStats => {
  if (typeof data !== 'object' || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    Number.isFinite(d.identities) &&
    Number.isFinite(d.accounts) &&
    Number.isFinite(d.successRate)
  );
};

const formatRate = (rate: number): string => `${Number(rate.toFixed(1))}%`;

const UNAVAILABLE = 'Unavailable';

const Dashboard: React.FC = () => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<DashboardStats>('/dashboard/stats')
      .then((response) => {
        if (cancelled) return;
        setState(
          isValidStats(response.data)
            ? { status: 'ready', stats: response.data }
            : { status: 'error' }
        );
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const countValue = (pick: (s: DashboardStats) => number): string => {
    if (state.status === 'loading') return '…';
    if (state.status === 'error') return UNAVAILABLE;
    return String(pick(state.stats));
  };

  const rateValue = (): string => {
    if (state.status === 'loading') return '…';
    if (state.status === 'error') return UNAVAILABLE;
    return formatRate(state.stats.successRate);
  };

  const errorNote =
    state.status === 'error' ? (
      <p className="text-sm text-red-600 mb-2">Could not load dashboard statistics.</p>
    ) : null;

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
          {errorNote}
          <p className="text-3xl font-bold text-primary-600 mb-2">
            {countValue((s) => s.identities)}
          </p>
          <p className="text-gray-600 text-sm">Digital identities ready to use</p>
          <div className="mt-2 text-xs text-primary-600 opacity-0 group-hover:opacity-100 transition-opacity">
            Click to view all identities →
          </div>
        </Link>

        <Link to="/accounts" className="card hover:shadow-lg transition-shadow duration-200 cursor-pointer group">
          <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-primary-600">Accounts</h3>
          {errorNote}
          <p className="text-3xl font-bold text-primary-600 mb-2">
            {countValue((s) => s.accounts)}
          </p>
          <p className="text-gray-600 text-sm">Automated accounts created</p>
          <div className="mt-2 text-xs text-primary-600 opacity-0 group-hover:opacity-100 transition-opacity">
            Click to view all accounts →
          </div>
        </Link>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Success Rate</h3>
          {errorNote}
          <p className="text-3xl font-bold text-green-600 mb-2">{rateValue()}</p>
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
    </div>
  );
};

export default Dashboard;
