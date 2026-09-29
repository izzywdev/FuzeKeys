/**
 * Regression tests for the shared API client.
 *
 * Three callers independently got the base URL wrong and all three shipped:
 * authService used the bare REACT_APP_API_URL as its base (so the Module
 * Federation build posted to `<host>/auth/login`, with no `/api/v1`), while
 * Accounts.tsx and googleApi.ts requested un-versioned `/api/accounts` and
 * `/api/identities`, which the backend answers with 404. Nothing asserted the
 * prefix, so nothing caught it.
 */

import { vi as jest } from 'vitest';

describe('apiClient base URL', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...ORIGINAL_ENV };
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  const loadBase = async (): Promise<typeof import('../apiClient')> => import('../apiClient');

  it('appends the /api/v1 prefix to the configured origin', async () => {
    process.env.REACT_APP_API_URL = 'https://api.keys.prod.fuzefront.com';
    expect((await loadBase()).API_BASE_URL).toBe('https://api.keys.prod.fuzefront.com/api/v1');
  });

  it('falls back to the local backend origin, still versioned', async () => {
    delete process.env.REACT_APP_API_URL;
    expect((await loadBase()).API_BASE_URL).toBe('http://localhost:8002/api/v1');
  });

  it('does not double up the slash when the origin has a trailing one', async () => {
    process.env.REACT_APP_API_URL = 'https://api.keys.prod.fuzefront.com/';
    expect((await loadBase()).API_BASE_URL).toBe('https://api.keys.prod.fuzefront.com/api/v1');
  });

  it('exposes the un-versioned origin separately for legacy routers', async () => {
    // Eight backend routers are still mounted without the prefix (/api/google,
    // /api/sms, ...). Their callers need the bearer token but cannot use the
    // versioned base. This stays a distinct export so the un-versioned surface
    // remains countable, and shrinks as routers migrate.
    process.env.REACT_APP_API_URL = 'https://api.keys.prod.fuzefront.com';
    const { LEGACY_API_BASE_URL, API_BASE_URL } = await loadBase();
    expect(LEGACY_API_BASE_URL).toBe('https://api.keys.prod.fuzefront.com');
    expect(API_BASE_URL).toBe(`${LEGACY_API_BASE_URL}/api/v1`);
  });

  it('always ends in /api/v1 whatever the origin', async () => {
    for (const origin of [
      'http://localhost:8002',
      'https://api.keys.prod.fuzefront.com',
      'https://example.test/',
    ]) {
      jest.resetModules();
      process.env.REACT_APP_API_URL = origin;
      expect((await loadBase()).API_BASE_URL).toMatch(/\/api\/v1$/);
    }
  });
});
