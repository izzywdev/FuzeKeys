# Credentials API Guide

## Overview

The Credentials API provides secure credential management and retrieval for microservices in the FuzeKeys system. It allows different services (scrapers, mobile apps, automation tools) to:

- Request generated credentials for identities to sign up for new sites
- Store credentials after successful account creation
- Retrieve stored credentials for existing accounts
- Validate credential formats for different sites
- Manage credentials securely with encryption

## Authentication

All API endpoints require authentication using an API key in the `X-API-Key` header.

### Supported Services

| Service | API Key Environment Variable | Default Key |
|---------|------------------------------|-------------|
| Scraper Service | `SCRAPER_API_KEY` | `scraper-key-12345` |
| Mobile Service | `MOBILE_API_KEY` | `mobile-key-12345` |
| Automation Service | `AUTOMATION_API_KEY` | `automation-key-12345` |

### Example Request
```bash
curl -X POST "http://localhost:8000/api/credentials/request-identity-credentials" \
  -H "X-API-Key: scraper-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"identity_id": 1, "site_name": "github", "action_type": "signup", "credential_types": ["email", "password", "username"]}'
```

## API Endpoints

### 1. Request Identity Credentials

Generate credentials for an identity to sign up for a specific site.

**Endpoint:** `POST /api/credentials/request-identity-credentials`

**Request Body:**
```json
{
  "identity_id": 1,
  "site_name": "github",
  "action_type": "signup",
  "credential_types": ["email", "password", "username", "name", "phone"]
}
```

**Response:**
```json
{
  "identity_id": 1,
  "site_name": "github",
  "credentials": {
    "email": "john.doe.1703123456@example.com",
    "password": "JohnDoePass123!",
    "username": "johndoe_a1b2",
    "name": "John Doe",
    "first_name": "John",
    "last_name": "Doe",
    "phone": "+1234567890"
  },
  "metadata": {
    "requested_by": "scraper-service",
    "requested_at": "2024-01-01T12:00:00Z",
    "action_type": "signup",
    "credential_types": ["email", "password", "username", "name"]
  }
}
```

### 2. Store Account Credentials

Store credentials after successful account creation.

**Endpoint:** `POST /api/credentials/store-account-credentials`

**Request Body:**
```json
{
  "account_id": 1,
  "credentials": {
    "email": "john.doe.1703123456@example.com",
    "password": "JohnDoePass123!",
    "username": "johndoe_a1b2",
    "api_key": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "two_factor_backup_codes": ["123456", "789012", "345678"]
  },
  "metadata": {
    "signup_date": "2024-01-01T12:00:00Z",
    "verification_method": "email",
    "account_type": "free"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Credentials stored for account 1",
  "account_id": 1
}
```

### 3. Request Account Credentials

Retrieve stored credentials for an existing account.

**Endpoint:** `POST /api/credentials/request-account-credentials`

**Request Body:**
```json
{
  "account_id": 1,
  "credential_types": ["email", "password", "api_key"]
}
```

**Response:**
```json
{
  "account_id": 1,
  "site_name": "github",
  "credentials": {
    "email": "john.doe.1703123456@example.com",
    "password": "JohnDoePass123!",
    "api_key": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  "last_used": "2024-01-01T12:00:00Z"
}
```

### 4. Get Account Credentials (GET)

Alternative GET endpoint for retrieving account credentials.

**Endpoint:** `GET /api/credentials/account/{account_id}/credentials`

**Query Parameters:**
- `credential_types` (optional): Comma-separated list of credential types

**Example:**
```bash
GET /api/credentials/account/1/credentials?credential_types=email,password,api_key
```

### 5. Get Identity Accounts

List all accounts for a specific identity.

**Endpoint:** `GET /api/credentials/identity/{identity_id}/accounts`

**Response:**
```json
{
  "identity_id": 1,
  "identity_name": "John Doe",
  "accounts": [
    {
      "account_id": 1,
      "site_name": "github",
      "site_url": "https://github.com",
      "is_active": true,
      "signup_completed": true,
      "created_at": "2024-01-01T12:00:00Z",
      "last_accessed": "2024-01-01T12:00:00Z",
      "has_stored_credentials": true
    }
  ],
  "total_accounts": 1
}
```

### 6. Validate Credentials

Validate credential format for a specific site.

**Endpoint:** `POST /api/credentials/validate-credentials`

**Query Parameters:**
- `site_name`: Name of the site to validate against

**Request Body:**
```json
{
  "email": "test@example.com",
  "password": "SecurePass123!",
  "username": "test_user_123"
}
```

**Response:**
```json
{
  "valid": true,
  "missing_fields": [],
  "invalid_fields": [],
  "warnings": []
}
```

### 7. Health Check

Check the health of the credentials service.

**Endpoint:** `GET /api/credentials/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "credentials-api",
  "encryption": "enabled",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Credential Generation Rules

### Email Generation
- **Signup**: `{identity_name}.{timestamp}@example.com`
- **Signin**: `{identity_name}@example.com`

### Password Generation
- Pattern: `{IdentityName}Pass123!`
- Minimum 8 characters with uppercase, lowercase, numbers, and symbols

### Username Generation
- Default: `{identity_name_lowercase_underscored}`
- GitHub: `{identity_name_lowercase}{random_hex}`
- Customizable per site

### Site-Specific Customizations

#### GitHub
- Username includes random hex suffix
- Validates username pattern: `^[a-zA-Z0-9_-]+$`

#### Google
- Includes recovery email field
- Minimum 8-character password requirement

## Security Features

### Encryption
- All stored credentials are encrypted using Fernet (AES 128)
- Encryption key configurable via `CREDENTIAL_ENCRYPTION_KEY` environment variable
- Individual field encryption and full credential blob encryption

### API Authentication
- Service-based API key authentication
- Configurable API keys per microservice
- Request logging and audit trails

### Access Control
- Service identity tracking in metadata
- Credential access logging
- Last accessed timestamp updates

## Usage Examples

### Scraper Service Flow

1. **Request credentials for signup:**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/credentials/request-identity-credentials",
    headers={"X-API-Key": "scraper-key-12345"},
    json={
        "identity_id": 1,
        "site_name": "github",
        "action_type": "signup",
        "credential_types": ["email", "password", "username"]
    }
)
credentials = response.json()["credentials"]
```

2. **Use credentials in scraper:**
```python
# Use the generated credentials in your scraper
email = credentials["email"]
password = credentials["password"]
username = credentials["username"]

# Perform signup automation...
```

3. **Store successful credentials:**
```python
# After successful signup, store additional credentials
requests.post(
    "http://localhost:8000/api/credentials/store-account-credentials",
    headers={"X-API-Key": "scraper-key-12345"},
    json={
        "account_id": account_id,
        "credentials": {
            **credentials,
            "api_key": "obtained_api_key",
            "two_factor_backup_codes": ["123456", "789012"]
        }
    }
)
```

### Mobile Service Flow

1. **Get stored credentials for signin:**
```python
response = requests.post(
    "http://localhost:8000/api/credentials/request-account-credentials",
    headers={"X-API-Key": "mobile-key-12345"},
    json={
        "account_id": 1,
        "credential_types": ["email", "password"]
    }
)
credentials = response.json()["credentials"]
```

2. **Use for mobile app authentication:**
```python
# Use credentials for mobile app signin
await mobile_signin(
    email=credentials["email"],
    password=credentials["password"]
)
```

## Integration with LLM Scraper System

The credentials API integrates seamlessly with the LLM-driven scraper generation system:

1. **Scraper Generation**: LLM generates scrapers that call the credentials API
2. **Execution**: Scrapers use credentials API during execution
3. **Storage**: Successful scrapers store obtained credentials
4. **Reuse**: Stored credentials used for subsequent operations

### Example Generated Scraper Code

```python
async def github_signup(identity_id: int):
    # Request credentials from API
    credentials = await request_identity_credentials(
        identity_id=identity_id,
        site_name="github",
        action_type="signup",
        credential_types=["email", "password", "username"]
    )
    
    # Use credentials in automation
    driver.find_element(By.ID, "user_email").send_keys(credentials["email"])
    driver.find_element(By.ID, "user_password").send_keys(credentials["password"])
    driver.find_element(By.ID, "user_login").send_keys(credentials["username"])
    
    # ... perform signup ...
    
    # Store credentials after success
    await store_account_credentials(
        account_id=account_id,
        credentials=credentials
    )
```

## Environment Configuration

```bash
# Encryption
CREDENTIAL_ENCRYPTION_KEY=your-32-byte-base64-key

# API Keys
SCRAPER_API_KEY=your-scraper-service-key
MOBILE_API_KEY=your-mobile-service-key
AUTOMATION_API_KEY=your-automation-service-key

# Database
DATABASE_URL=sqlite:///fuzekeys.db
```

## Error Handling

### Common Error Responses

```json
{
  "detail": "Identity not found"
}
```

```json
{
  "detail": "Invalid API key"
}
```

```json
{
  "detail": "Failed to generate credentials"
}
```

### HTTP Status Codes
- `200`: Success
- `401`: Invalid API key
- `404`: Resource not found (identity, account)
- `422`: Validation error
- `500`: Internal server error

## Demo Script

Run the complete credentials API demo:

```bash
python demo_credentials_api.py
```

This demo showcases:
- Identity credential generation
- Credential storage and retrieval
- Multi-service authentication
- Validation capabilities
- Complete workflow examples

## Best Practices

1. **Use specific credential types**: Only request the credentials you need
2. **Store after success**: Always store credentials after successful operations
3. **Validate before use**: Use the validation endpoint for critical operations
4. **Handle errors gracefully**: Implement proper error handling and retries
5. **Secure API keys**: Store API keys securely and rotate regularly
6. **Monitor access**: Log and monitor credential access for security

## Monitoring and Observability

- All credential requests are logged with service identity
- Access patterns tracked for security monitoring
- Health check endpoint for service monitoring
- Audit trail for credential access and modifications 