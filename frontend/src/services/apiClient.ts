import axios from 'axios';

/**
 * The single configured HTTP client for the FuzeKeys API.
 *
 * Every FuzeKeys route is served under `/api/v1` (see the family API-versioning
 * standard). `REACT_APP_API_URL` carries the *origin only* -- docker-compose sets
 * it to `http://localhost:8002`, and the MFE build defines it as the prod API
 * host -- so the version prefix is appended here, exactly once, in one place.
 *
 * This module exists because it was previously done three different ways:
 * authService used the bare env value as its base (so in the Module Federation
 * build it posted to `<host>/auth/login`, missing the prefix entirely), while
 * SitesDatabase appended `/api/v1` itself and two other callers used the old
 * un-versioned `/api/*` paths. Callers now pass resource-relative paths only --
 * `apiClient.get('/accounts/')` -- and never spell the prefix themselves.
 */
const DEFAULT_ORIGIN = 'http://localhost:8002';

const origin = (process.env.REACT_APP_API_URL || DEFAULT_ORIGIN).replace(/\/+$/, '');

export const API_BASE_URL = `${origin}/api/v1`;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach the bearer token when one is stored. The endpoints below are gated by
// get_current_user, so without this a corrected path returns 403 instead of 404.
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle token expiration
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
