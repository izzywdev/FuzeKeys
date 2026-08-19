import apiClient, { API_BASE_URL } from './apiClient';

// Re-exported for callers that need the resolved base (and for tests).
export { API_BASE_URL };

export interface User {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterData {
  username: string;
  email: string;
  password: string;
  master_key: string;
  first_name?: string;
  last_name?: string;
}

export const authService = {
  async login(email: string, password: string, masterKey: string): Promise<LoginResponse> {
    const response = await apiClient.post('/auth/login', {
      email,
      password,
      master_key: masterKey,
    });
    return response.data;
  },

  async register(userData: RegisterData): Promise<User> {
    const response = await apiClient.post('/auth/register', userData);
    return response.data;
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },

  async logout(): Promise<void> {
    await apiClient.post('/auth/logout');
    localStorage.removeItem('token');
  },
}; 