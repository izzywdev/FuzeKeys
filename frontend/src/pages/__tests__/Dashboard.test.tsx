import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import apiClient from '../../services/apiClient';
import Dashboard from '../Dashboard';

vi.mock('../../services/apiClient', () => ({
  default: { get: vi.fn() },
}));

const mockGet = vi.mocked(apiClient.get);

const renderDashboard = () =>
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );

describe('Dashboard', () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it('shows the real counts and success rate from /dashboard/stats', async () => {
    mockGet.mockResolvedValue({
      data: { identities: 5, accounts: 3, successRate: 66.7 },
    });

    renderDashboard();

    expect(await screen.findByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith('/dashboard/stats');
  });

  it('does not render the old hardcoded values or the demo notice', async () => {
    mockGet.mockResolvedValue({
      data: { identities: 7, accounts: 9, successRate: 40 },
    });

    renderDashboard();

    await screen.findByText('40%');
    expect(screen.queryByText('95%')).not.toBeInTheDocument();
    expect(screen.queryByText(/Demo Mode/i)).not.toBeInTheDocument();
  });

  it('shows zero counts and a 0% rate when there is no data', async () => {
    mockGet.mockResolvedValue({
      data: { identities: 0, accounts: 0, successRate: 0 },
    });

    renderDashboard();

    expect(await screen.findByText('0%')).toBeInTheDocument();
    expect(screen.getAllByText('0')).toHaveLength(2);
    expect(screen.queryByText('NaN%')).not.toBeInTheDocument();
  });

  it('marks the tiles unavailable but keeps the rest of the page when the call fails', async () => {
    mockGet.mockRejectedValue(new Error('network down'));

    renderDashboard();

    await waitFor(() => {
      expect(screen.getAllByText('Unavailable')).toHaveLength(3);
    });
    expect(screen.getAllByText('Could not load dashboard statistics.')).toHaveLength(3);
    expect(screen.getByText('Welcome to FuzeKeys')).toBeInTheDocument();
    expect(screen.getByText('Try Chat Assistant')).toBeInTheDocument();
  });

  it('treats a malformed response as unavailable instead of rendering NaN', async () => {
    mockGet.mockResolvedValue({ data: { identities: 'x' } });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getAllByText('Unavailable')).toHaveLength(3);
    });
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
