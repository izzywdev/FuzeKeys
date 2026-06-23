# Google Integration

This module provides automated Google account creation functionality for the FuzeKeys platform. It enables creating Google accounts using identity data with advanced verification handling and SMS integration.

## Features

- ✅ **Automated Account Creation**: Create Google accounts programmatically
- ✅ **Identity Integration**: Use stored identity data for account creation
- ✅ **Manual Data Support**: Create accounts with custom data
- ✅ **Verification Handling**: Smart handling of phone/email verification
- ✅ **Configurable Options**: Customizable browser and automation settings
- ✅ **SMS Integration**: Works with mobile SMS interception
- ✅ **Retry Logic**: Automatic retry on failures
- ✅ **Security Features**: Proxy support, user agent customization

## Architecture

```
Google Integration
├── backend/                    # Python automation services
│   ├── signup.py              # Main signup automation service
│   ├── models.py              # Data models and validation
│   └── __init__.py            # Module exports
├── frontend/                  # React components and services
│   ├── components/
│   │   └── GoogleSignupForm.tsx
│   ├── services/
│   │   └── googleApi.ts
│   └── GoogleIntegrationPage.tsx
└── README.md                  # This file
```

## Backend Components

### GoogleSignupService

The main service class that handles Google account creation automation.

```python
from app.integrations.google.backend.signup import GoogleSignupService
from app.integrations.google.backend.models import GoogleSignupConfig

# Create service with custom configuration
config = GoogleSignupConfig(
    headless=True,
    timeout=120,
    retry_attempts=3
)
service = GoogleSignupService(config)

# Create account with identity
result = await service.signup_with_identity(identity_id=1)

# Create account with manual data
signup_data = GoogleSignupData(
    first_name="John",
    last_name="Doe",
    username="john.doe.2024",
    password="SecurePassword123!"
)
result = await service.signup(signup_data)
```

### Data Models

#### GoogleSignupData
```python
{
    "first_name": "John",
    "last_name": "Doe", 
    "username": "john.doe.2024",
    "password": "SecurePassword123!",
    "phone_number": "+1234567890",  # Optional
    "recovery_email": "john@example.com",  # Optional
    "birth_date": "1990-01-01",  # Optional
    "gender": "Male",  # Optional
    "skip_phone_verification": false
}
```

#### GoogleSignupConfig
```python
{
    "headless": true,
    "timeout": 120,
    "retry_attempts": 3,
    "use_mobile_user_agent": false,
    "prefer_phone_verification": true,
    "auto_handle_captcha": false,
    "use_proxy": false,
    "proxy_config": {
        "host": "proxy.example.com",
        "port": "8080"
    }
}
```

#### GoogleSignupResult
```python
{
    "success": true,
    "account_email": "john.doe.2024@gmail.com",
    "account_id": "google_account_123",
    "verification_required": false,
    "verification_type": null,
    "error_message": null,
    "additional_data": {}
}
```

## API Endpoints

### POST `/api/google/signup/{identity_id}`
Create Google account using stored identity data.

**Request:**
```json
{
    "headless": true,
    "timeout": 120,
    "retry_attempts": 3
}
```

**Response:**
```json
{
    "success": true,
    "message": "Google account created successfully",
    "account_id": 123,
    "account_email": "user@gmail.com",
    "verification_required": false
}
```

### POST `/api/google/signup/manual`
Create Google account with manual data.

**Request:**
```json
{
    "first_name": "John",
    "last_name": "Doe",
    "username": "john.doe.2024",
    "password": "SecurePassword123!",
    "phone_number": "+1234567890",
    "skip_phone_verification": false
}
```

### POST `/api/google/test/identity-conversion/{identity_id}`
Test identity conversion without creating account.

**Response:**
```json
{
    "success": true,
    "message": "Identity conversion successful",
    "signup_data": {
        "first_name": "John",
        "last_name": "Doe",
        "username": "john.doe.1234",
        "has_password": true,
        "phone_number": "+1234567890"
    }
}
```

### GET `/api/google/accounts/{identity_id}`
Get Google accounts for an identity.

### GET `/api/google/config/default`
Get default configuration.

## Frontend Components

### GoogleIntegrationPage
Complete page component with tabs for:
- **Create Account**: Account creation form
- **Account Management**: View and manage created accounts
- **Testing Tools**: Test identity conversion

### GoogleSignupForm
Reusable form component with:
- Identity selection or manual data entry
- Advanced configuration options
- Real-time validation
- Progress tracking

### googleApiService
API service for backend communication:
```typescript
import { googleApiService } from './services/googleApi';

// Create account with identity
const result = await googleApiService.signupWithIdentity(1, config);

// Create account with manual data
const result = await googleApiService.signupWithManualData(data, config);

// Test identity conversion
const test = await googleApiService.testIdentityConversion(1);
```

## Installation & Setup

### Prerequisites
- Chrome browser installed
- Python 3.8+
- Node.js 16+ (for frontend)

### Backend Setup
1. Install dependencies:
```bash
pip install selenium webdriver-manager
```

2. The Chrome driver will be automatically downloaded by webdriver-manager.

3. Import the integration in your main app:
```python
from app.integrations.google.backend.signup import GoogleSignupService
```

### Frontend Setup
1. The components are already integrated into the main React app.

2. Access the Google integration page:
```
http://localhost:3000/integrations/google
```

## Configuration Options

### Browser Options
- `headless`: Run browser in background (faster, less debuggable)
- `timeout`: Maximum time to wait for operations
- `use_mobile_user_agent`: Use mobile browser signature
- `custom_user_agent`: Custom user agent string

### Automation Options
- `retry_attempts`: Number of retry attempts on failure
- `prefer_phone_verification`: Use phone verification when available
- `auto_handle_captcha`: Attempt automatic CAPTCHA solving (experimental)

### Network Options
- `use_proxy`: Route traffic through proxy
- `proxy_config`: Proxy server configuration
- `save_cookies`: Save browser cookies between sessions

## Identity Integration

The Google integration automatically maps identity fields to Google requirements:

| Identity Field | Google Field | Notes |
|---------------|--------------|-------|
| `encrypted_first_name` | `first_name` | Required |
| `encrypted_last_name` | `last_name` | Required |
| `encrypted_email` | `recovery_email` | Optional |
| `encrypted_phone` | `phone_number` | Optional |
| `encrypted_date_of_birth` | `birth_date` | Required in some regions |
| `encrypted_gender` | `gender` | Optional |
| `preferred_username_pattern` | `username` | Generated if not provided |
| `password_preferences` | `password` | Generated based on preferences |

### Username Generation
If no username pattern is provided, usernames are generated using:
1. Identity pattern (e.g., `{first}{last}{random}`)
2. Email prefix (if available)
3. Default: `{firstname}{lastname}{4-digit-random}`

### Password Generation
Passwords are generated based on identity preferences:
- Minimum 8 characters (Google requirement)
- At least one letter and one number
- Optional symbols based on preferences

## SMS Integration

The Google integration works seamlessly with the SMS system:

1. **Phone Verification**: When Google requires phone verification, the system can use registered mobile devices to receive and process OTP codes automatically.

2. **OTP Extraction**: The mobile app extracts OTP codes from SMS messages and sends them back to the server.

3. **Automatic Completion**: The signup process waits for OTP codes and completes verification automatically.

## Error Handling

Common scenarios and handling:

### Username Unavailable
- Automatically tries suggested usernames
- Falls back to modified versions with numbers
- Reports final username in result

### Phone Verification Required
- Returns `verification_required: true`
- Provides `verification_type: "phone"`
- Can integrate with SMS system for automatic completion

### CAPTCHA Challenges
- Can attempt automatic solving (experimental)
- Provides user-friendly error messages
- Supports manual intervention

### Rate Limiting
- Implements retry logic with exponential backoff
- Supports proxy rotation
- Provides detailed error reporting

## Testing

### Demo Script
Run the demo script to test functionality:
```bash
cd backend
python demo_google_integration.py
```

### Unit Tests
```bash
pytest app/integrations/google/tests/
```

### Manual Testing
1. Use the frontend interface at `/integrations/google`
2. Test with various identity configurations
3. Verify SMS integration with mobile devices

## Security Considerations

### Data Protection
- All identity data is encrypted at rest
- Passwords are not stored in account records
- Sensitive data is only decrypted during signup

### Automation Detection
- Uses human-like typing delays
- Randomizes timing between actions
- Supports proxy rotation
- Custom user agent configuration

### Rate Limiting
- Respects Google's rate limits
- Implements exponential backoff
- Supports distributed execution

## Troubleshooting

### Chrome Driver Issues
The integration uses `webdriver-manager` which automatically downloads and manages Chrome drivers. If you encounter issues:

1. Update Chrome browser
2. Clear webdriver cache: `rm -rf ~/.wdm`
3. Reinstall webdriver-manager

### Selenium Issues
- Ensure Chrome browser is installed
- Check firewall settings
- Verify no other processes are using the browser

### Verification Problems
- Check SMS device connectivity
- Verify phone number format
- Ensure email access for recovery emails

### Performance Optimization
- Use headless mode for production
- Implement connection pooling
- Use distributed execution for scale

## Future Enhancements

- [ ] **Two-Factor Authentication**: Handle 2FA setup during account creation
- [ ] **Account Recovery**: Automated account recovery processes  
- [ ] **Bulk Creation**: Batch processing for multiple accounts
- [ ] **Advanced CAPTCHA**: Better CAPTCHA solving capabilities
- [ ] **Account Verification**: Post-creation account verification
- [ ] **Profile Customization**: Set up Google profiles and preferences
- [ ] **API Key Integration**: Generate and manage Google API keys

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs in the backend console
3. Test with the demo script
4. Submit issues with detailed error messages and configurations used 