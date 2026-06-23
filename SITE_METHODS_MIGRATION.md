# Site Automation Methods Migration

This migration adds comprehensive method tracking capabilities to the FuzeKeys database, allowing you to store and query information about how each site supports automation for signup, signin, and API key operations.

## 🎯 What's Added

### New Database Fields

#### **Method Availability Tracking**
- `signup_methods` (JSON) - Available methods: `["api", "scraping", "manual"]`
- `signin_methods` (JSON) - Available methods: `["api", "scraping", "manual"]`
- `apikey_methods` (JSON) - Available methods: `["api", "scraping", "manual"]`

#### **Preferred Method Order**
- `signup_preferred_method` - First method to try (enum: `api`, `scraping`, `manual`, `hybrid`)
- `signin_preferred_method` - First method to try
- `apikey_preferred_method` - First method to try

#### **Automation Technology Requirements**
- `automation_framework` - Required framework (enum: `selenium`, `playwright`, `requests`, `puppeteer`, `api_only`)
- `requires_javascript` (boolean) - Whether JavaScript execution is needed
- `requires_browser_automation` (boolean) - Whether full browser automation is needed
- `requires_proxy` (boolean) - Whether proxy rotation is recommended
- `requires_user_agent_rotation` (boolean) - Whether user agent rotation is needed

#### **API Method Details**
- `api_base_url` - Base URL for API calls
- `api_signup_endpoint` - Specific endpoint for signup (if available)
- `api_signin_endpoint` - Specific endpoint for signin (if available) 
- `api_key_endpoint` - Specific endpoint for API key management
- `api_authentication_method` - How to authenticate (`oauth`, `api_key`, `basic_auth`, etc.)

### New Enum Types
- `AutomationMethod` - Available automation approaches
- `AutomationFramework` - Supported automation technologies

## 🚀 Running the Migration

### Step 1: Apply Database Migration

```bash
cd backend
alembic upgrade head
```

### Step 2: Populate Method Data

```bash
cd backend
python scripts/populate_site_methods.py
```

## 📊 What Gets Populated

### Existing Sites

The population script updates these sites with known method information:

#### **Google** 
- **Methods**: Scraping (Selenium-based)
- **Status**: Signup implemented, signin partial
- **Framework**: Selenium with user-agent rotation

#### **Permit.io**
- **Methods**: Complete scraping implementation  
- **Status**: All operations implemented
- **Framework**: Playwright-based

#### **GitHub**
- **Methods**: Hybrid (API + scraping)
- **Status**: API for signin/keys, scraping for signup
- **Framework**: Selenium + GitHub API

#### **OpenAI** 
- **Methods**: Scraping for all operations
- **Status**: Configured but not implemented
- **Framework**: Playwright-based

### Sample Sites

The script also creates sample sites:
- **Stripe** - Payment platform
- **Discord** - Communication platform

## 🔍 How to Use the New Fields

### Query Available Methods

```python
from app.models.site import Site

# Get sites that support API signup
api_signup_sites = session.query(Site).filter(
    Site.signup_methods.contains(['api'])
).all()

# Get sites that require browser automation
browser_sites = session.query(Site).filter(
    Site.requires_browser_automation == True
).all()

# Get preferred method for a site
site = session.query(Site).filter(Site.name == 'github').first()
preferred_signin = site.get_preferred_method('signin')
```

### Check Method Availability

```python
site = session.query(Site).filter(Site.name == 'github').first()

# Check if specific method is available
if site.has_method('signin', 'api'):
    # Use API signin
    pass
elif site.has_method('signin', 'scraping'):
    # Use scraping signin
    pass

# Get all available methods
available_methods = site.get_available_methods('apikey')
# Returns: ['api'] for GitHub
```

### Automation Framework Selection

```python
site = session.query(Site).filter(Site.name == 'google').first()

if site.automation_framework == AutomationFramework.SELENIUM:
    # Use Selenium
    from selenium import webdriver
    driver = webdriver.Chrome()
elif site.automation_framework == AutomationFramework.PLAYWRIGHT:
    # Use Playwright
    from playwright.async_api import async_playwright
    playwright = await async_playwright().start()
```

## 🎛️ API Changes

### Updated Site Response Model

The API now returns additional method information:

```json
{
  "id": 1,
  "name": "github",
  "display_name": "GitHub",
  "signup_methods": ["scraping"],
  "signin_methods": ["scraping", "api"],
  "apikey_methods": ["api"],
  "signup_preferred_method": "scraping",
  "signin_preferred_method": "api", 
  "apikey_preferred_method": "api",
  "automation_framework": "selenium",
  "requires_javascript": true,
  "requires_browser_automation": true,
  "requires_proxy": false,
  "requires_user_agent_rotation": false,
  "api_base_url": "https://api.github.com",
  "api_signin_endpoint": "https://github.com/login/oauth/access_token",
  "api_key_endpoint": "https://api.github.com/user/keys",
  "api_authentication_method": "oauth"
}
```

### Site Creation/Update APIs

You can now create/update sites with method information:

```bash
POST /api/v1/sites
{
  "name": "newsite",
  "display_name": "New Site",
  "url": "https://newsite.com",
  "category": "cloud",
  "signup_methods": ["scraping"],
  "signin_methods": ["scraping", "api"],
  "apikey_methods": ["api"],
  "automation_framework": "playwright",
  "requires_proxy": true
}
```

## 🔧 Automation Integration

### Method Selection Logic

```python
def select_automation_method(site: Site, operation: str):
    """Select the best automation method for a site operation."""
    
    # Get preferred method
    preferred = site.get_preferred_method(operation)
    available = site.get_available_methods(operation)
    
    if preferred.value in available:
        return preferred.value
    elif 'api' in available:
        return 'api'
    elif 'scraping' in available:
        return 'scraping'
    else:
        return 'manual'

# Usage
method = select_automation_method(site, 'signin')
if method == 'api':
    # Use API integration
    pass
elif method == 'scraping':
    # Use web scraping
    pass
```

### Framework Configuration

```python
def configure_automation(site: Site):
    """Configure automation based on site requirements."""
    
    config = {
        'framework': site.automation_framework.value,
        'headless': not site.requires_javascript,
        'proxy': site.requires_proxy,
        'user_agent_rotation': site.requires_user_agent_rotation
    }
    
    if site.automation_framework == AutomationFramework.SELENIUM:
        # Configure Selenium
        options = webdriver.ChromeOptions()
        if config['headless']:
            options.add_argument('--headless')
        if config['proxy']:
            options.add_argument(f'--proxy-server={proxy_url}')
    
    return config
```

## 📈 Benefits

1. **Intelligent Method Selection** - Automatically choose the best automation approach
2. **Framework Optimization** - Use the right tool for each site
3. **Scalable Configuration** - Easily add new sites with complete method info
4. **Performance Tuning** - Configure automation based on site requirements
5. **API Transparency** - Clear visibility into what methods are available

## 🔮 Future Enhancements

- **Success Rate Tracking** - Monitor which methods work best for each site
- **Dynamic Method Detection** - Automatically detect available methods
- **Cost Optimization** - Choose methods based on resource usage
- **Fallback Chains** - Automatically try backup methods on failure

---

This migration provides the foundation for intelligent, scalable site automation in FuzeKeys! 🎉 