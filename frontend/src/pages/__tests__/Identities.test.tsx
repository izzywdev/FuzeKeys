/**
 * Identities page: live against /api/v1/identities (FKY-5).
 *
 * apiClient is mocked at the module boundary, so these tests pin the exact
 * resource paths/bodies the page sends and the states it renders for each
 * outcome (loading, empty, error + retry, create, edit, delete).
 */

import React from 'react';
import { vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';

const { get, post, put, del } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

vi.mock('../../services/apiClient', () => ({
  default: { get, post, put, delete: del },
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import Identities from '../Identities';

const summary = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: 'Work Persona',
  description: 'Professional signups',
  created_at: '2026-01-15T10:00:00Z',
  accounts_count: 3,
  ...over,
});

const detail = {
  id: 1,
  name: 'Work Persona',
  description: 'Professional signups',
  first_name: 'Ada',
  last_name: 'Lovelace',
  email: 'ada@example.com',
  phone: '+15555550111',
  date_of_birth: null,
  address_line1: null,
  address_line2: null,
  city: 'London',
  state: null,
  zip_code: null,
  country: 'UK',
  profession: 'Mathematician',
  company: null,
  bio: null,
  created_at: '2026-01-15T10:00:00Z',
  updated_at: null,
};

const page = (items: unknown[], next_offset: number | null = null) => ({
  data: { items, page: { offset: 0, limit: 100, total: items.length, next_offset } },
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <Identities />
    </MemoryRouter>
  );

const axiosError = (status?: number) =>
  Object.assign(new Error('boom'), {
    isAxiosError: true,
    response: status ? { status, data: {} } : undefined,
  });

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
  del.mockReset();
});

describe('Identities page', () => {
  it('shows a loading state, then the live identities with no demo banner', async () => {
    get.mockResolvedValueOnce(page([summary()]));
    renderPage();

    expect(screen.getByRole('status')).toHaveTextContent(/loading identities/i);
    expect(await screen.findByText('Work Persona')).toBeInTheDocument();
    expect(screen.getByText('3 accounts')).toBeInTheDocument();
    expect(screen.queryByText(/demo mode/i)).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/identities/', { params: { limit: 100, offset: 0 } });
  });

  it('follows next_offset until the collection is exhausted', async () => {
    get
      .mockResolvedValueOnce(page([summary({ id: 1, name: 'First' })], 100))
      .mockResolvedValueOnce(page([summary({ id: 2, name: 'Second' })], null));
    renderPage();

    expect(await screen.findByText('First')).toBeInTheDocument();
    expect(await screen.findByText('Second')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith('/identities/', { params: { limit: 100, offset: 100 } });
  });

  it('renders an empty state with a create call-to-action', async () => {
    get.mockResolvedValueOnce(page([]));
    renderPage();

    expect(await screen.findByText(/no identities yet/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /create your first identity/i }));
    expect(screen.getByRole('dialog', { name: /create new identity/i })).toBeInTheDocument();
  });

  it('shows an inline error with Retry on a 5xx, and recovers on retry', async () => {
    get.mockRejectedValueOnce(axiosError(500)).mockResolvedValueOnce(page([summary()]));
    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/could not load/i);

    await userEvent.click(within(alert).getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('Work Persona')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('creates an identity via POST /identities/ omitting empty optional fields, then reloads', async () => {
    get.mockResolvedValueOnce(page([])).mockResolvedValueOnce(page([summary({ name: 'New One' })]));
    post.mockResolvedValueOnce({ data: { ...detail, id: 9, name: 'New One' } });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /^\+ create identity$/i }));
    const dialog = screen.getByRole('dialog', { name: /create new identity/i });
    await userEvent.type(within(dialog).getByLabelText(/identity name/i), 'New One');
    await userEvent.type(within(dialog).getByLabelText(/first name/i), 'Ada');
    await userEvent.type(within(dialog).getByLabelText(/last name/i), 'Lovelace');
    await userEvent.type(within(dialog).getByLabelText(/^email/i), 'ada@example.com');
    await userEvent.click(within(dialog).getByRole('button', { name: /create identity/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/identities/', {
        name: 'New One',
        first_name: 'Ada',
        last_name: 'Lovelace',
        email: 'ada@example.com',
      })
    );
    expect(await screen.findByText('New One')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps the form open and shows the error when create fails', async () => {
    get.mockResolvedValueOnce(page([]));
    post.mockRejectedValueOnce(axiosError(500));
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /^\+ create identity$/i }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/identity name/i), 'X');
    await userEvent.type(within(dialog).getByLabelText(/first name/i), 'A');
    await userEvent.type(within(dialog).getByLabelText(/last name/i), 'B');
    await userEvent.type(within(dialog).getByLabelText(/^email/i), 'a@b.co');
    await userEvent.click(within(dialog).getByRole('button', { name: /create identity/i }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/could not create/i);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows decrypted details from GET /identities/{id}', async () => {
    get.mockResolvedValueOnce(page([summary()])).mockResolvedValueOnce({ data: detail });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /view details for work persona/i }));
    const dialog = await screen.findByRole('dialog', { name: 'Work Persona' });
    expect(await within(dialog).findByText('ada@example.com')).toBeInTheDocument();
    expect(within(dialog).getByText('Ada Lovelace')).toBeInTheDocument();
    expect(get).toHaveBeenLastCalledWith('/identities/1');
  });

  it('edits an identity via PUT /identities/{id}, sending "" for cleared optional fields', async () => {
    get
      .mockResolvedValueOnce(page([summary()]))
      .mockResolvedValueOnce({ data: detail })
      .mockResolvedValueOnce(page([summary({ name: 'Renamed' })]));
    put.mockResolvedValueOnce({ data: { ...detail, name: 'Renamed' } });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /^edit work persona$/i }));
    const dialog = await screen.findByRole('dialog', { name: /edit identity/i });
    const name = within(dialog).getByLabelText(/identity name/i);
    expect(name).toHaveValue('Work Persona');
    await userEvent.clear(name);
    await userEvent.type(name, 'Renamed');
    await userEvent.clear(within(dialog).getByLabelText(/phone number/i));
    await userEvent.click(within(dialog).getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    const [path, body] = put.mock.calls[0];
    expect(path).toBe('/identities/1');
    expect(body).toMatchObject({ name: 'Renamed', phone: '', city: 'London', first_name: 'Ada' });
    expect(await screen.findByText('Renamed')).toBeInTheDocument();
  });

  it('deletes only after confirmation, via DELETE /identities/{id}', async () => {
    get.mockResolvedValueOnce(page([summary()]));
    del.mockResolvedValueOnce({ data: { message: 'Identity deleted successfully' } });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /delete work persona/i }));
    const dialog = screen.getByRole('dialog', { name: /delete identity/i });
    expect(dialog).toHaveTextContent(/3 linked accounts/i);
    expect(del).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/identities/1'));
    expect(await screen.findByText(/no identities yet/i)).toBeInTheDocument();
  });

  it('keeps the identity and shows an error when delete fails', async () => {
    get.mockResolvedValueOnce(page([summary()]));
    del.mockRejectedValueOnce(axiosError(500));
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: /delete work persona/i }));
    const dialog = screen.getByRole('dialog', { name: /delete identity/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/could not delete/i);
    expect(screen.getByRole('heading', { name: 'Work Persona', level: 3 })).toBeInTheDocument();
    expect(del).toHaveBeenCalledTimes(1);
  });
});
