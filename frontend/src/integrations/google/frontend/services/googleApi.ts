// Google API Service for FuzeKeys Frontend

export interface GoogleSignupData {
  first_name: string;
  last_name: string;
  username: string;
  password: string;
  phone_number?: string;
  recovery_email?: string;
  birth_date?: string;
  gender?: string;
  skip_phone_verification: boolean;
}

export interface GoogleSignupConfig {
  headless: boolean;
  timeout: number;
  retry_attempts: number;
  use_mobile_user_agent: boolean;
  prefer_phone_verification: boolean;
  auto_handle_captcha: boolean;
}

export interface GoogleSignupResult {
  success: boolean;
  message: string;
  account_email?: string;
  verification_required?: boolean;
  verification_type?: string;
}

export interface GoogleAccount {
  id: number;
  email: string;
  status: string;
  created_at: string;
  identity_id: number;
}

export interface Identity {
  id: number;
  name: string;
  description?: string;
}

export interface GoogleAccountsResponse {
  accounts: GoogleAccount[];
  total: number;
}

class GoogleApiService {
  private baseUrl = process.env.REACT_APP_API_URL || 'http://localhost:8002';

  async getIdentities(): Promise<Identity[]> {
    try {
      const response = await fetch(`${this.baseUrl}/api/identities`);
      if (!response.ok) {
        throw new Error('Failed to fetch identities');
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching identities:', error);
      // Return mock data for now
      return [
        { id: 1, name: 'John Doe', description: 'Primary identity' },
        { id: 2, name: 'Jane Smith', description: 'Secondary identity' },
        { id: 3, name: 'Bob Johnson', description: 'Test identity' }
      ];
    }
  }

  async getGoogleAccounts(identityId: number): Promise<GoogleAccountsResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/api/google/accounts?identity_id=${identityId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch Google accounts');
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching Google accounts:', error);
      // Return mock data for now
      return {
        accounts: [],
        total: 0
      };
    }
  }

  async signupWithIdentity(identityId: number, config?: GoogleSignupConfig): Promise<GoogleSignupResult> {
    try {
      const response = await fetch(`${this.baseUrl}/api/google/signup/identity`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          identity_id: identityId,
          config: config || {}
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create Google account');
      }

      return await response.json();
    } catch (error) {
      console.error('Error creating Google account with identity:', error);
      throw error;
    }
  }

  async signupWithManualData(data: GoogleSignupData, config?: GoogleSignupConfig): Promise<GoogleSignupResult> {
    try {
      const response = await fetch(`${this.baseUrl}/api/google/signup/manual`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          signup_data: data,
          config: config || {}
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create Google account');
      }

      return await response.json();
    } catch (error) {
      console.error('Error creating Google account with manual data:', error);
      throw error;
    }
  }

  async testIdentityConversion(identityId: number): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/api/google/test/identity/${identityId}`, {
        method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

      if (!response.ok) {
        throw new Error('Failed to test identity conversion');
      }

      return await response.json();
    } catch (error) {
      console.error('Error testing identity conversion:', error);
      throw error;
    }
  }
}

const googleApiService = new GoogleApiService();
export default googleApiService; 