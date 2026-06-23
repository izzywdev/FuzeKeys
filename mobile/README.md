# SignMeUp SMS Interceptor Android App

This Android app automatically detects OTP codes from SMS messages and forwards them to your SignMeUp server for seamless automatic sign-in/sign-up processes.

## Features

- **Automatic SMS Interception**: Monitors incoming SMS messages for OTP codes
- **Smart OTP Detection**: Uses advanced pattern matching to identify OTP codes with high accuracy
- **Server Integration**: Seamlessly communicates with your SignMeUp backend server
- **Real-time WebSocket Communication**: Maintains persistent connection with server
- **Background Service**: Continues working even when app is closed
- **Privacy Focused**: Only processes messages locally to extract OTP codes
- **Modern UI**: Clean Material Design interface with easy configuration

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

#### Supported Services
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

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   SMS Messages  │───►│  OTP Extractor   │───►│ Server API Call │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Pattern Matcher │
                       │  • Regex Patterns│
                       │  • Confidence    │
                       │  • Context       │
                       └──────────────────┘
```

## Setup Instructions

### Prerequisites

- Android Studio Arctic Fox (2020.3.1) or later
- Android SDK API level 23 or higher
- Kotlin 1.9.22 or later
- Your SignMeUp server running and accessible

### Installation

1. **Clone and Build**:
   ```bash
   cd mobile/android
   ./gradlew assembleDebug
   ```

2. **Install APK**:
   ```bash
   adb install app/build/outputs/apk/debug/app-debug.apk
   ```

3. **Configure Server**:
   - Open the app
   - Enter your SignMeUp server URL (e.g., `http://your-server.com:8000`)
   - Save settings and test connection

4. **Grant Permissions**:
   - Allow SMS read/receive permissions
   - Enable background app refresh
   - Allow notifications

### Server Integration

The app communicates with your SignMeUp server via these endpoints:

- **POST** `/api/sms/otp` - Send detected OTP codes
- **GET** `/api/sms/requests/{deviceId}` - Get pending OTP requests
- **WebSocket** `/ws/sms-interceptor` - Real-time communication

### API Payload Format

```json
{
  "otp": "123456",
  "sender": "+1234567890",
  "messageBody": "Your verification code is 123456",
  "timestamp": 1642123456789,
  "deviceId": "unique-device-id",
  "confidence": 0.95
}
```

## Usage

1. **Enable Service**: Toggle the SMS interception service in the app
2. **Monitor Status**: Check the status indicator for connection health
3. **View Statistics**: See how many OTPs have been processed
4. **Automatic Operation**: The app works in the background once configured

## OTP Detection Patterns

The app uses sophisticated pattern matching to detect OTPs:

### Supported Patterns
- **Numeric**: 4-8 digit codes (`123456`)
- **Alphanumeric**: Mixed character codes (`AB12CD`)
- **Contextual**: Codes with keywords (`Your code: 123456`)
- **Service Specific**: WhatsApp, Google, Facebook, etc.
- **Banking**: Financial service OTPs

### Confidence Scoring
- **High (0.8-1.0)**: Clear OTP keywords + known sender
- **Medium (0.6-0.8)**: Partial indicators
- **Low (0.4-0.6)**: Pattern match only

## Security Considerations

⚠️ **Important Security Notes**:

- Only use with trusted servers
- OTP codes are transmitted over HTTPS
- No SMS content is stored locally
- App only processes messages for OTP extraction
- Implements certificate pinning for secure communication

### Future Security Enhancements
- **Accessibility Service Security**: Careful permission management for UI automation
- **Authenticator App Access**: Secure inter-app communication protocols
- **Biometric Integration**: Proper handling of device security features
- **Enterprise Compliance**: Support for corporate security policies

## Troubleshooting

### Common Issues

1. **No OTPs Detected**:
   - Check SMS permissions are granted
   - Verify service is enabled
   - Test with known OTP message formats

2. **Server Connection Failed**:
   - Verify server URL is correct
   - Check network connectivity
   - Ensure server is running and accessible

3. **Background Service Stopped**:
   - Disable battery optimization for the app
   - Check Android's background app restrictions
   - Restart the service in the app

### Debug Mode

Enable debug logging in the app to see detailed OTP detection:

```kotlin
// In OtpExtractor.kt
private const val DEBUG = true
```

## Development

### Project Structure

```
mobile/android/
├── app/
│   ├── src/main/java/com/signmeup/smsinterceptor/
│   │   ├── MainActivity.kt              # Main UI activity
│   │   ├── receivers/
│   │   │   ├── SmsReceiver.kt          # SMS interception
│   │   │   └── BootReceiver.kt         # Auto-start after reboot
│   │   ├── services/
│   │   │   └── ServerCommunicationService.kt  # Background service
│   │   ├── utils/
│   │   │   ├── OtpExtractor.kt         # Pattern matching logic
│   │   │   └── PreferenceManager.kt    # Settings storage
│   │   └── api/
│   │       └── ApiClient.kt            # Server communication
│   └── src/main/res/                   # Resources and layouts
├── build.gradle                        # App dependencies
└── README.md                          # This file
```

### Adding New OTP Patterns

To add support for new OTP formats:

1. **Add Pattern** in `OtpExtractor.kt`:
   ```kotlin
   Pattern.compile("(?i)yourservice.*?(\\d{6})")
   ```

2. **Add Sender** to common senders list:
   ```kotlin
   "yourservice", "yourbank"
   ```

3. **Test** with sample messages

### Building Release APK

```bash
./gradlew assembleRelease
```

**Note**: Configure signing keys in `app/build.gradle` for production builds.

## Performance

- **Memory Usage**: ~15MB background service
- **Battery Impact**: Minimal (uses efficient broadcast receivers)
- **Network Usage**: ~1KB per OTP transmission
- **CPU Usage**: Low (pattern matching only on SMS receive)

### Future Performance Optimizations
- **ML Model Optimization**: Efficient on-device inference for UI recognition
- **Battery Management**: Advanced power optimization for accessibility services
- **Memory Efficiency**: Optimized caching for authenticator app integration

## Compatibility

- **Android Version**: 6.0 (API 23) and higher
- **Architecture**: ARM64, ARM32, x86_64
- **RAM**: Minimum 2GB recommended
- **Storage**: ~50MB app size

### Future Compatibility Requirements
- **Android 8.0+**: Required for advanced accessibility features (Phase 2+)
- **Biometric Hardware**: For fingerprint/face unlock integration
- **High-end Devices**: Recommended for ML-powered UI recognition

## License

This project is part of the SignMeUp suite. See the main project LICENSE file.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review server logs for API errors
3. Enable debug mode for detailed logging
4. Create an issue in the main SignMeUp repository

---

**Privacy Notice**: This app processes SMS messages locally to extract OTP codes. No full message content is transmitted or stored. Only extracted OTP codes and metadata are sent to your configured server.

**Future Privacy Considerations**: Advanced features will require additional permissions (Accessibility Service, Device Admin) with comprehensive privacy protections and user consent mechanisms. 