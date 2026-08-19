import apiClient, { legacyApiClient } from '../../../../services/apiClient';
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
  async getIdentities(): Promise<Identity[]> {
    // Was fetch(`${baseUrl}/api/identities`) -- un-versioned, unauthenticated,
    // and 404 against the backend. It also swallowed the failure and returned
    // three hardcoded people ("John Doe", "Jane Smith", "Bob Johnson"), which is
    // why the 404 went unnoticed: an identity vault silently showed invented
    // identities. GoogleIntegrationPage.loadIdentities already surfaces errors
    // via notification.error, so the failure is now allowed to reach it.
    const { data } = await apiClient.get('/identities/');
    return data;
  }

  async getGoogleAccounts(identityId: number): Promise<GoogleAccountsResponse> {
    // The route is /accounts/{identity_id} -- a PATH parameter. This sent
    // ?identity_id=, which matched nothing and 404'd, and the failure was then
    // swallowed into an empty list that reads as "this identity has no Google
    // accounts". GoogleIntegrationPage.loadAccounts already raises
    // notification.error, so the failure is allowed to reach it.
    const { data } = await legacyApiClient.get(`/api/google/accounts/${identityId}`);
    return data;
  }

  async signupWithIdentity(identityId: number, config?: GoogleSignupConfig): Promise<GoogleSignupResult> {
    // Two mistakes here, not one. The route is /signup/{identity_id}, so the id
    // belongs in the PATH -- posting to the literal "/signup/identity" bound
    // identity_id="identity" and failed int validation. And the handler's only
    // body parameter is `config`, so the body is the config object itself; the
    // {identity_id, config} envelope was never the expected shape.
    const { data } = await legacyApiClient.post(
      `/api/google/signup/${identityId}`,
      config || {}
    );
    return data;
  }

  async signupWithManualData(data: GoogleSignupData, config?: GoogleSignupConfig): Promise<GoogleSignupResult> {
    // This one's path and body were already correct -- two Pydantic body params
    // means FastAPI embeds them as {signup_data, config}. It failed anyway,
    // because /signup/{identity_id} is declared first and shadowed it; that is
    // fixed on the backend in this change. The only thing missing here was auth.
    const { data: result } = await legacyApiClient.post('/api/google/signup/manual', {
      signup_data: data,
      config: config || {},
    });
    return result;
  }

  async testIdentityConversion(identityId: number): Promise<any> {
    // The route is /test/identity-conversion/{identity_id}, not /test/identity/,
    // and it takes no request body.
    const { data } = await legacyApiClient.post(
      `/api/google/test/identity-conversion/${identityId}`
    );
    return data;
  }
}

const googleApiService = new GoogleApiService();
export default googleApiService; 