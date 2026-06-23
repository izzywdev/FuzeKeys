# SignMeUp Mobile SMS Interceptor

## Overview

The SignMeUp Mobile SMS Interceptor is an Android app that automatically detects OTP codes from SMS messages and forwards them to your SignMeUp server. This enables seamless automatic sign-in/sign-up processes without manual OTP entry.

## Roadmap

### 🚀 Planned Advanced Automation Features

#### Phase 2: UI Interaction Automation
- **Automatic "Yes, it's me" Prompts**: 
  - Detect and automatically click confirmation prompts during sign-in flows
  - Handle security verification dialogs (e.g., "Is this you trying to sign in?")
  - Support for various prompt patterns across different services
  - Configurable prompt recognition with service-specific rules

- **Round Number Button Handling**:
  - Automatically detect and interact with circular number selection interfaces
  - Handle security prompts that require selecting specific numbers from a grid
  - Support for various number button layouts and styles
  - Pattern recognition for number-based security challenges

#### Phase 3: Authenticator App Integration
- **Google Authenticator Integration**:
  - Automatically fetch TOTP codes from Google Authenticator
  - Support for multiple accounts and services
  - Real-time code extraction without user intervention
  - Secure integration using Android's accessibility services

- **Microsoft Authenticator Integration**:
  - Automatic retrieval of verification codes from Microsoft Authenticator
  - Handle both TOTP codes and push notification approvals
  - Support for work/school accounts and personal Microsoft accounts
  - Integration with Microsoft's authentication flow

#### Phase 4: Advanced Security Handling
- **Biometric Automation**:
  - Integrate with device biometric authentication
  - Automatic fingerprint/face unlock for authenticator apps
  - Secure storage of biometric preferences per service

- **Backup Codes Management**:
  - Automatically detect and store backup codes during setup
  - Smart usage of backup codes when primary methods fail
  - Secure encrypted storage of backup authentication methods

#### Phase 5: API Key Creation & Per-Site Integrations
- **API Key Automation**:
  - Automatic creation of API keys for supported services
  - Navigate through developer portals and API management interfaces
  - Handle API key generation, naming, and permission configuration
  - Secure storage and management of created API keys

- **Per-Site Integration Architecture**:
  - Modular integration system for each supported service
  - Site-specific automation logic for signup, signin, and API creation
  - Configurable workflows per service type
  - Version management for site changes and updates

### 🔧 Technical Implementation Notes

#### UI Automation Architecture
```
┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│  Accessibility      │    │   Pattern Matcher   │    │  Action Executor │
│  Service Monitor    │───►│   & UI Analyzer     │───►│  & Click Handler │
└─────────────────────┘    └─────────────────────┘    └──────────────────┘
```

#### Per-Site Integration Architecture Options

**Option 1: Folder-Based Structure (Recommended)**
```
integrations/
├── google/
│   ├── signup/
│   │   ├── flow.json          # Automation steps
│   │   ├── selectors.json     # UI element selectors
│   │   └── handler.py         # Custom logic (server-side)
│   ├── signin/
│   │   ├── flow.json
│   │   ├── selectors.json
│   │   └── handler.py
│   └── apikeycreator/
│       ├── flow.json
│       ├── selectors.json
│       ├── handler.py
│       └── permissions.json   # API permission configs
├── facebook/
│   ├── signup/
│   ├── signin/
│   └── apikeycreator/
├── github/
│   ├── signup/
│   ├── signin/
│   └── apikeycreator/
└── common/
    ├── interfaces/            # Common interfaces
    ├── base_handlers/         # Base automation classes (Python)
    └── utilities/             # Shared utilities (Python)
```

**Option 2: Plugin-Based Architecture**
```
plugins/
├── google_plugin/
│   ├── plugin.json           # Plugin metadata
│   ├── GoogleIntegration.py  # Main plugin class (server-side)
│   └── resources/
├── facebook_plugin/
└── core/
    ├── PluginManager.py      # Plugin loader (server-side)
    ├── IntegrationInterface.py
    └── FlowExecutor.py
```

**Option 3: Declarative Configuration**
```
integrations/
├── configs/
│   ├── google.yaml           # Complete site definition
│   ├── facebook.yaml
│   └── github.yaml
├── engines/
│   ├── FlowEngine.py         # Executes YAML flows (server-side)
│   ├── SelectorEngine.py     # Handles UI selection (server-side)
│   └── ActionEngine.py       # Performs actions (server-side)
└── templates/
    ├── oauth_flow.yaml       # Reusable flow templates
    └── api_creation.yaml
```

#### Planned Technical Components
- **AccessibilityService**: For UI interaction and element detection
- **UIAutomator Framework**: For cross-app automation capabilities
- **OCR Engine**: For text recognition in complex UI elements
- **ML Model**: For intelligent prompt and button recognition
- **Secure Keystore**: For storing sensitive automation preferences
- **Integration Manager**: Loads and manages per-site automation logic
- **Flow Executor**: Executes site-specific automation sequences
- **API Key Vault**: Secure storage and management of generated API keys

#### Site Integration Components
- **Flow Definition**: Step-by-step automation sequences
- **Selector Manager**: UI element identification and interaction
- **Custom Handlers**: Site-specific logic for complex scenarios
- **Validation Engine**: Verify successful completion of flows
- **Error Recovery**: Handle failures and retry mechanisms
- **Rate Limiting**: Respect site-specific rate limits and delays

#### Security Considerations
- **Permission Escalation**: Requires Accessibility Service permissions
- **App-to-App Communication**: Secure inter-app data exchange protocols
- **Biometric Integration**: Proper handling of device security features
- **Privacy Protection**: Ensure no sensitive data logging or transmission
- **API Key Security**: Encrypted storage with proper access controls
- **Site Authentication**: Secure handling of credentials per integration

#### Compatibility Requirements
- **Android 8.0+**: Required for advanced accessibility features
- **Root Access**: Optional, for enhanced authenticator app integration
- **Device Admin**: May be required for certain enterprise features
- **Special Permissions**: Accessibility, Device Admin, possibly SYSTEM_ALERT_WINDOW
- **Browser Integration**: Support for multiple browser apps and WebView
- **Network Requirements**: Stable internet for API interactions

### 📋 Implementation Phases

#### Phase 2 - UI Automation (Q2 2024)
- [ ] Accessibility Service implementation
- [ ] Basic prompt detection and clicking
- [ ] Round number button recognition
- [ ] Configuration UI for automation rules
- [ ] Testing framework for UI interactions

#### Phase 3 - Authenticator Integration (Q3 2024)
- [ ] Google Authenticator API integration
- [ ] Microsoft Authenticator support
- [ ] Secure TOTP code extraction
- [ ] Multi-account management
- [ ] Fallback mechanisms

#### Phase 4 - Advanced Features (Q4 2024)
- [ ] Machine learning for prompt recognition
- [ ] Biometric integration
- [ ] Backup codes management
- [ ] Enterprise security features
- [ ] Advanced analytics and monitoring

#### Phase 5 - API Key Creation & Site Integrations (Q1 2025)
- [ ] Integration architecture design and implementation
- [ ] Core integration framework
- [ ] Priority site integrations (Google, GitHub, AWS)
- [ ] API key vault and management system
- [ ] Flow validation and testing framework
- [ ] Error handling and recovery mechanisms
- [ ] Rate limiting and throttling
- [ ] Integration marketplace/plugin system

### 🎯 Use Cases

#### Complete Automation Flow
```
1. SignMeUp initiates sign-in process
2. Mobile app detects OTP from SMS
3. App automatically clicks "Yes, it's me" prompt
4. App handles round number security challenge
5. App fetches TOTP from authenticator if needed
6. Sign-in completes fully automated
7. App navigates to developer portal
8. App creates API key with specified permissions
9. API key is securely stored and returned to SignMeUp
```

#### API Key Creation Examples
```
Google Cloud Platform:
1. Navigate to Google Cloud Console
2. Select or create project
3. Enable required APIs
4. Navigate to Credentials
5. Create API key with restrictions
6. Configure permissions and quotas
7. Store key securely

GitHub:
1. Navigate to Settings > Developer settings
2. Generate new personal access token
3. Select required scopes
4. Create and copy token
5. Store securely with metadata

AWS:
1. Navigate to IAM console
2. Create new programmatic user
3. Attach policies/permissions
4. Generate access keys
5. Store access key ID and secret
```

#### Supported Services (Future)
- **Social Media**: Facebook, Twitter, Instagram, LinkedIn
- **Cloud Services**: Google, Microsoft, Dropbox, iCloud
- **Financial**: Banks, PayPal, Crypto exchanges
- **Enterprise**: Office 365, Slack, Zoom, Teams
- **E-commerce**: Amazon, eBay, Shopify
- **Developer Services**: GitHub, GitLab, Bitbucket
- **Cloud Platforms**: AWS, Azure, GCP, Digital Ocean
- **API Services**: Stripe, Twilio, SendGrid, Mailchimp

### 🏗️ Integration Development Workflow

#### Adding New Site Integration
1. **Analysis Phase**:
   - Study site's signup/signin flows
   - Identify API creation process
   - Document UI elements and patterns
   - Test authentication requirements

2. **Development Phase**:
   - Create site folder structure
   - Define flow configurations
   - Implement custom handlers
   - Add UI selectors
   - Configure permissions

3. **Testing Phase**:
   - Unit tests for individual components
   - Integration tests for complete flows
   - Error scenario testing
   - Rate limiting validation

4. **Deployment Phase**:
   - Integration validation
   - Documentation updates
   - Version control and rollback
   - Monitoring and analytics

#### Integration Maintenance
- **Site Updates**: Automatic detection of UI changes
- **Flow Validation**: Regular testing of automation flows
- **Version Management**: Handle multiple site versions
- **Error Reporting**: Detailed failure analysis and reporting
- **Performance Monitoring**: Track success rates and timing

## How It Works

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your Phone    │    │   SignMeUp App   │    │  SignMeUp Web   │
│                 │    │                  │    │                 │
│ 1. SMS arrives  │───►│ 2. OTP detected  │───►│ 3. Auto sign-in │
│    with OTP     │    │    and sent      │    │    completed    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Process Flow

1. **OTP Request**: Your SignMeUp web app requests an OTP for a service
2. **SMS Monitoring**: The mobile app monitors incoming SMS messages
3. **Pattern Matching**: Advanced regex patterns detect OTP codes
4. **Server Communication**: Detected OTPs are sent to your server via API
5. **Automatic Completion**: Your web app receives the OTP and completes sign-in

## Features

### 🔍 Smart OTP Detection
- **Multiple Patterns**: Detects 4-8 digit codes, alphanumeric codes, and contextual patterns
- **Service-Specific**: Recognizes patterns from Google, Facebook, WhatsApp, banks, etc.
- **Confidence Scoring**: Rates detection accuracy to avoid false positives
- **Context Analysis**: Uses keywords and sender information for better accuracy

### 🔒 Privacy & Security
- **Local Processing**: SMS content is only processed locally on your device
- **No Storage**: Full message content is never stored or transmitted
- **HTTPS Communication**: All server communication is encrypted
- **Minimal Data**: Only OTP codes and metadata are sent to your server

### 🚀 Performance
- **Background Service**: Works even when app is closed
- **Low Battery Impact**: Efficient broadcast receivers minimize power usage
- **Real-time Communication**: WebSocket connection for instant OTP delivery
- **Auto-restart**: Service automatically restarts after device reboot

## Installation & Setup

### Prerequisites
- Android 6.0 (API 23) or higher
- SMS read/receive permissions
- Internet connection
- Your SignMeUp server running

### Quick Setup

1. **Install the APK**:
   ```bash
   cd mobile/android
   ./gradlew assembleDebug
   adb install app/build/outputs/apk/debug/app-debug.apk
   ```

2. **Configure the App**:
   - Open the app
   - Enter your server URL (e.g., `http://your-server.com:8000`)
   - Grant SMS permissions when prompted
   - Enable the SMS interception service

3. **Test the Connection**:
   - Use the "Test Connection" button
   - Check the status indicator shows "✅ Service running"

## API Integration

### Server Endpoints

Your SignMeUp server now includes these SMS-related endpoints:

```
POST /api/sms/otp                    # Receive OTP from mobile app
POST /api/sms/register-device        # Register mobile device
GET  /api/sms/requests/{device_id}   # Get pending OTP requests
POST /api/sms/request-otp            # Request OTP for a service
GET  /api/sms/request-status/{id}    # Check OTP request status
GET  /api/sms/devices                # List registered devices
GET  /api/sms/health                 # Health check
WS   /ws/sms-interceptor             # WebSocket for real-time communication
```

### Using in Your Web App

To request an OTP in your SignMeUp web application:

```javascript
// Request an OTP for a service
const response = await fetch('/api/sms/request-otp', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    service: 'google',
    timeout_seconds: 300
  })
});

const { request_id } = await response.json();

// Poll for OTP or use WebSocket for real-time updates
const checkStatus = async () => {
  const statusResponse = await fetch(`/api/sms/request-status/${request_id}`);
  const status = await statusResponse.json();
  
  if (status.status === 'completed') {
    console.log('OTP received:', status.otp_code);
    // Use the OTP to complete sign-in
    return status.otp_code;
  }
};
```

### WebSocket Integration

For real-time OTP delivery:

```javascript
const ws = new WebSocket('ws://your-server.com:8000/ws/sms-interceptor');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'otp_received') {
    console.log('OTP received:', message.otp);
    // Automatically fill OTP in your form
    document.getElementById('otp-input').value = message.otp;
  }
};
```

## Configuration

### App Settings

The mobile app stores these settings:

- **Server URL**: Your SignMeUp server endpoint
- **Service Status**: Whether SMS interception is enabled
- **Device ID**: Unique identifier for this device
- **Statistics**: Count of OTPs processed

### Server Configuration

Add these environment variables to your server:

```env
# SMS Service Configuration
SMS_ENABLED=true
SMS_TIMEOUT_DEFAULT=300
SMS_MAX_DEVICES=10
```

## Supported OTP Patterns

### Numeric Patterns
- `123456` - 6-digit codes (most common)
- `1234` - 4-digit codes
- `12345678` - 8-digit codes

### Contextual Patterns
- `Your verification code is 123456`
- `Code: 123456`
- `OTP 123456`
- `PIN: 1234`

### Service-Specific Patterns
- **Google**: `G-123456`
- **WhatsApp**: `WhatsApp code: 123-456`
- **Facebook**: `FB-123456`
- **Banking**: Various bank-specific formats

### Alphanumeric Patterns
- `AB12CD` - Mixed character codes
- `A1B2C3` - Alternating patterns

## Troubleshooting

### Common Issues

**❌ No OTPs Detected**
- Check SMS permissions are granted
- Verify service is enabled in app
- Test with known OTP message formats
- Check if sender is in common OTP senders list

**❌ Server Connection Failed**
- Verify server URL is correct and accessible
- Check network connectivity
- Ensure server is running and SMS endpoints are available
- Test with `/api/sms/health` endpoint

**❌ Background Service Stopped**
- Disable battery optimization for the app
- Check Android's background app restrictions
- Restart the service in the app
- Verify auto-start after reboot is working

### Debug Mode

Enable detailed logging:

1. In Android Studio, check Logcat for `SmsReceiver` and `ServerCommService` tags
2. Enable verbose logging in `OtpExtractor.kt`
3. Check server logs for SMS API calls

### Testing

Test OTP detection with sample messages:

```
Test Message: "Your verification code is 123456"
Expected: Detects "123456" with high confidence

Test Message: "Google verification code: G-789012"  
Expected: Detects "789012" with high confidence

Test Message: "Your order #1234 has been confirmed"
Expected: Should NOT detect "1234" (low confidence)
```

## Security Considerations

### Data Privacy
- ✅ Only OTP codes are transmitted, not full SMS content
- ✅ No SMS data is stored locally or on server
- ✅ All communication uses HTTPS encryption
- ✅ Device registration uses unique IDs

### Network Security
- ✅ Certificate pinning for server communication
- ✅ API key authentication for device registration
- ✅ WebSocket connections are secured
- ✅ Rate limiting on server endpoints

### Permissions
- ✅ Minimal required permissions (SMS read/receive only)
- ✅ Clear permission rationale shown to users
- ✅ No access to contacts, calls, or other sensitive data

## Development

### Building from Source

```bash
# Clone the repository
git clone <your-repo>
cd mobile/android

# Build debug APK
./gradlew assembleDebug

# Build release APK (requires signing configuration)
./gradlew assembleRelease

# Install on connected device
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Adding New OTP Patterns

To support new services:

1. **Add Pattern** in `OtpExtractor.kt`:
   ```kotlin
   Pattern.compile("(?i)yourservice.*?(\\d{6})")
   ```

2. **Add Sender** to known senders:
   ```kotlin
   "yourservice", "yourbank"
   ```

3. **Test** with sample messages

### Customization

The app can be customized for your specific needs:

- **Branding**: Update app name, colors, and icons
- **Patterns**: Add service-specific OTP patterns
- **Server**: Modify API endpoints and authentication
- **UI**: Customize the Material Design interface

## Production Deployment

### App Store Distribution

1. **Configure Signing**:
   ```gradle
   android {
       signingConfigs {
           release {
               storeFile file('your-keystore.jks')
               storePassword 'your-store-password'
               keyAlias 'your-key-alias'
               keyPassword 'your-key-password'
           }
       }
   }
   ```

2. **Build Release APK**:
   ```bash
   ./gradlew assembleRelease
   ```

3. **Upload to Play Store** or distribute as APK

### Server Deployment

1. **Database Migration**: Run Alembic migrations for SMS tables
2. **Environment Variables**: Configure SMS service settings
3. **WebSocket Support**: Ensure your server supports WebSocket connections
4. **Monitoring**: Set up logging and monitoring for SMS endpoints

## Support

For issues and questions:

1. **Check Logs**: Review Android Logcat and server logs
2. **Test Endpoints**: Use `/api/sms/health` to verify server status
3. **Debug Mode**: Enable verbose logging for detailed information
4. **Documentation**: Refer to this guide and code comments

---

**Note**: This app is designed for personal use with your own SignMeUp server. Only use with trusted servers and be aware of privacy implications when granting SMS permissions. 