# FuzeKeys Background Services

## Overview

FuzeKeys includes powerful background services that automate the account creation process with advanced capabilities:

- 📧 **Email Verification Monitoring**: Automatically monitor email accounts and handle verification links
- 🔍 **AI-Powered Captcha Solving**: Use OpenAI's vision capabilities to solve various types of captchas
- 🤖 **Automated Signup Workflows**: Complete signup processes with intelligent form filling
- 📊 **Task Management**: Queue-based task processing with retry logic and state persistence

## Architecture

### Services

1. **EmailVerificationService**: Monitors email accounts via IMAP and extracts verification links
2. **CaptchaSolverService**: Uses OpenAI GPT-4 Vision to solve captchas
3. **BackgroundServiceManager**: Orchestrates all background tasks and automation jobs
4. **CaptchaHandler**: Detects and solves captchas during web automation

### Components

- **Email Monitoring**: Real-time IMAP monitoring with smart filtering
- **Captcha Detection**: Automatic detection of reCAPTCHA, hCAPTCHA, and text captchas
- **Task Queue**: Async task processing with configurable retry logic
- **State Persistence**: Resume operations after server restarts

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the backend directory:

```env
# Required: OpenAI API Key for captcha solving
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Email monitoring configuration
EMAIL_ACCOUNTS='{"gmail": {"email": "your@gmail.com", "password": "app_password", "provider": "gmail"}}'

# Database (default SQLite)
DATABASE_URL_ASYNC=sqlite+aiosqlite:///./data/fuzekeys.db

# Security
ENCRYPTION_KEY=your_encryption_key_here
```

### 3. Install Browser Dependencies

```bash
playwright install chromium
```

## Usage

### Starting the Server

The background services start automatically when you run the server:

```bash
python working_server.py
```

### API Endpoints

#### Email Configuration

**Add Email Account for Monitoring:**
```http
POST /api/v1/background/email-config
Content-Type: application/json

{
  "email_address": "your@gmail.com",
  "password": "app_password_here",
  "provider": "gmail"
}
```

**List Email Accounts:**
```http
GET /api/v1/background/email-configs
```

#### Automation Jobs

**Create Automation Job:**
```http
POST /api/v1/background/automation-job
Content-Type: application/json

{
  "website": "github",
  "identity_id": 1,
  "email_account": "your@gmail.com",
  "signup_data": {
    "email": "signup@example.com",
    "username": "myusername",
    "password": "mypassword",
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

**Get Job Status:**
```http
GET /api/v1/background/automation-job/{job_id}
```

**List All Jobs:**
```http
GET /api/v1/background/automation-jobs?status=pending&limit=10
```

#### Captcha Solving

**Solve Captcha:**
```http
POST /api/v1/background/solve-captcha
Content-Type: application/json

{
  "image_url": "https://example.com/captcha.png",
  "captcha_type": "text",
  "question": "Enter the text shown in the image"
}
```

#### Service Management

**Get Service Status:**
```http
GET /api/v1/background/status
```

**Start/Stop Services:**
```http
POST /api/v1/background/start
POST /api/v1/background/stop
```

## Email Providers

### Gmail Setup

1. Enable 2-factor authentication
2. Generate an App Password:
   - Google Account → Security → 2-Step Verification → App passwords
3. Use the app password (not your regular password)

### Outlook/Hotmail Setup

1. Enable 2-factor authentication
2. Generate an App Password:
   - Microsoft Account → Security → Advanced security options → App passwords
3. Use the app password

### Yahoo Setup

1. Enable 2-factor authentication  
2. Generate an App Password:
   - Yahoo Account → Account Security → Generate app password
3. Use the app password

## Captcha Types Supported

### Text Captchas
- Distorted text recognition
- Mathematical problems
- Simple word recognition

### Image Selection Captchas
- "Select all traffic lights"
- "Select all crosswalks"
- Object identification in grid layouts

### reCAPTCHA
- Checkbox verification
- Image challenges
- Audio challenges (limited)

### hCaptcha
- Similar to reCAPTCHA
- Image-based challenges

## Security Features

### Encrypted Storage
- All email credentials are encrypted using AES-256
- Master key protection for encryption keys
- No plaintext passwords stored

### Secure Communication
- IMAP/SMTP connections use SSL/TLS
- HTTP requests use secure headers
- Rate limiting to prevent abuse

### Privacy Protection
- Email monitoring is read-only
- No email content is stored permanently
- Only verification-related emails are processed

## Monitoring & Logging

### Service Status Monitoring
```python
# Check if services are running
status = await background_manager.get_service_status()
print(f"Email monitoring: {status.email_monitoring}")
print(f"Active jobs: {status.automation_jobs}")
```

### Task Tracking
```python
# List all tasks
tasks = await background_manager.list_tasks()
for task in tasks:
    print(f"Task {task.task_id}: {task.status}")
```

### Log Levels
- INFO: Service status and job completion
- WARNING: Failed attempts and retries
- ERROR: Critical errors requiring attention

## Configuration Options

### Email Monitoring
```python
EMAIL_CHECK_INTERVAL = 30  # seconds between checks
MAX_EMAIL_AGE = 3600      # only process emails from last hour
VERIFICATION_TIMEOUT = 300 # timeout for verification links
```

### Captcha Solving
```python
CAPTCHA_CONFIDENCE_THRESHOLD = 0.7  # minimum confidence score
CAPTCHA_RETRY_ATTEMPTS = 3          # max retry attempts
VISION_MODEL = "gpt-4-vision-preview" # OpenAI model to use
```

### Browser Automation
```python
BROWSER_HEADLESS = True      # run browser in headless mode
BROWSER_TIMEOUT = 30000      # page load timeout (ms)
SLOW_MO = 0                  # slow down actions for debugging
```

## Troubleshooting

### Common Issues

**Email Authentication Failed:**
- Verify app password is correct
- Ensure 2FA is enabled
- Check IMAP is enabled for the account

**Captcha Solving Failed:**
- Verify OpenAI API key is valid
- Check internet connectivity
- Ensure sufficient API credits

**Jobs Stuck in Pending:**
- Check service status: `GET /api/v1/background/status`
- Restart services if needed
- Review error logs

### Debug Mode

Enable debug logging:
```python
import logging
logging.getLogger('app.services').setLevel(logging.DEBUG)
```

### Performance Tuning

For high-volume usage:
```python
# Increase worker threads
TASK_WORKERS = 5

# Batch email processing
EMAIL_BATCH_SIZE = 10

# Optimize database connections
DB_POOL_SIZE = 20
```

## API Integration Examples

### Python Client
```python
import aiohttp

async def create_automation_job():
    async with aiohttp.ClientSession() as session:
        data = {
            "website": "github",
            "identity_id": 1,
            "email_account": "test@gmail.com",
            "signup_data": {
                "email": "new@example.com",
                "username": "newuser",
                "password": "securepass"
            }
        }
        
        async with session.post(
            "http://localhost:8002/api/v1/background/automation-job",
            json=data
        ) as response:
            result = await response.json()
            print(f"Created job: {result['job_id']}")
```

### JavaScript/Node.js Client
```javascript
const axios = require('axios');

async function createAutomationJob() {
    const response = await axios.post(
        'http://localhost:8002/api/v1/background/automation-job',
        {
            website: 'github',
            identity_id: 1,
            email_account: 'test@gmail.com',
            signup_data: {
                email: 'new@example.com',
                username: 'newuser',
                password: 'securepass'
            }
        }
    );
    
    console.log(`Created job: ${response.data.job_id}`);
}
```

## Development

### Adding New Captcha Types

1. Extend `CaptchaChallenge` dataclass
2. Add detection logic in `CaptchaDetector`
3. Implement solving logic in `CaptchaSolverService`
4. Add application logic in `CaptchaHandler`

### Adding New Email Providers

1. Add provider configuration to `COMMON_EMAIL_CONFIGS`
2. Test IMAP/SMTP connectivity
3. Update documentation

### Custom Automation Scripts

Create custom signup scripts by extending `BackgroundServiceManager`:

```python
class CustomAutomation(BackgroundServiceManager):
    async def custom_signup_flow(self, website: str, data: dict):
        # Custom implementation
        pass
```

## Production Deployment

### Docker Setup
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Set Playwright browser path
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/chromium

# Copy application
COPY . /app
WORKDIR /app

# Install Python dependencies
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

CMD ["python", "working_server.py"]
```

### Environment Variables
```bash
export OPENAI_API_KEY="your-api-key"
export DATABASE_URL_ASYNC="postgresql+asyncpg://user:pass@db:5432/fuzekeys"
export ENCRYPTION_KEY="production-encryption-key"
```

### Health Checks
```bash
# Check service health
curl http://localhost:8002/health

# Check background services
curl http://localhost:8002/api/v1/background/status
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

### Testing

```bash
# Run tests
pytest tests/

# Test specific service
pytest tests/test_email_service.py

# Test with coverage
pytest --cov=app/services tests/
``` 