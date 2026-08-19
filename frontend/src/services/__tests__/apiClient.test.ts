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

describe('apiClient base URL', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...ORIGINAL_ENV };
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  const loadBase = (): string => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require('../apiClient').API_BASE_URL;
  };

  it('appends the /api/v1 prefix to the configured origin', () => {
    process.env.REACT_APP_API_URL = 'https://api.keys.prod.fuzefront.com';
    expect(loadBase()).toBe('https://api.keys.prod.fuzefront.com/api/v1');
  });

  it('falls back to the local backend origin, still versioned', () => {
    delete process.env.REACT_APP_API_URL;
    expect(loadBase()).toBe('http://localhost:8002/api/v1');
  });

  it('does not double up the slash when the origin has a trailing one', () => {
    process.env.REACT_APP_API_URL = 'https://api.keys.prod.fuzefront.com/';
    expect(loadBase()).toBe('https://api.keys.prod.fuzefront.com/api/v1');
  });

  it('always ends in /api/v1 whatever the origin', () => {
    for (const origin of [
      'http://localhost:8002',
      'https://api.keys.prod.fuzefront.com',
      'https://example.test/',
    ]) {
      jest.resetModules();
      process.env.REACT_APP_API_URL = origin;
      expect(loadBase()).toMatch(/\/api\/v1$/);
    }
  });
});
