"""
Prompt templates for LLM-driven scraper generation
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class SiteInfo:
    name: str
    url: str
    action_type: str  # "signup", "signin", "apikey_creation"
    patterns: Dict[str, Any]
    previous_attempts: List[Dict[str, Any]]
    test_data: Dict[str, Any]

class PromptTemplates:
    """Collection of prompt templates for scraper generation"""
    
    INFRASTRUCTURE_CONTEXT = """
AVAILABLE INFRASTRUCTURE APIS:

1. SMS Verification:
   - request_sms_verification(site, phone_number, timeout=300) -> request_id
   - wait_for_sms_code(request_id, poll_interval=5) -> verification_code
   
2. Email Verification:
   - setup_email_monitoring(email, sender_patterns, subject_patterns) -> monitor_id
   - get_verification_email(monitor_id) -> email_content
   
3. Mobile Communication:
   - send_mobile_command(command_type, parameters) -> command_id
   - Available commands: "click_prompt", "extract_totp", "handle_buttons"
   
4. Error Reporting:
   - report_error(scraper_id, error_data) -> success
   - report_success(scraper_id, success_data) -> success

HELPER FUNCTIONS (import these):
```python
import requests
import time
import asyncio
from infrastructure_api import InfrastructureAPI

async def request_sms_verification(site: str, phone_number: str, timeout: int = 300) -> str:
    response = requests.post("http://localhost:8000/api/infrastructure/sms/request-verification", 
                           json={"site": site, "phone_number": phone_number, "timeout_seconds": timeout})
    return response.json()["request_id"]

async def wait_for_sms_code(request_id: str, poll_interval: int = 5, max_wait: int = 300) -> str:
    start_time = time.time()
    while time.time() - start_time < max_wait:
        response = requests.get(f"http://localhost:8000/api/infrastructure/sms/get-verification/{request_id}")
        data = response.json()
        if data["status"] == "completed":
            return data["code"]
        elif data["status"] in ["timeout", "failed"]:
            raise Exception(f"SMS verification failed: {data.get('error_message', 'Unknown error')}")
        await asyncio.sleep(poll_interval)
    raise Exception("SMS verification timeout")

async def setup_email_monitoring(email: str, sender_patterns: List[str], subject_patterns: List[str]) -> str:
    response = requests.post("http://localhost:8000/api/infrastructure/email/setup-monitoring",
                           json={"email": email, "sender_patterns": sender_patterns, "subject_patterns": subject_patterns})
    return response.json()["monitor_id"]

async def send_mobile_command(command_type: str, parameters: Dict[str, Any]) -> str:
    response = requests.post("http://localhost:8000/api/infrastructure/mobile/send-command",
                           json={"command_type": command_type, "parameters": parameters})
    return response.json()["command_id"]
```
"""

    BASE_SCRAPER_TEMPLATE = """
You are an expert web automation engineer creating a production-ready scraper for {site_name}.

TASK: Create a {action_type} scraper

{infrastructure_context}

REQUIREMENTS:
1. Use Selenium WebDriver with Chrome/ChromeDriver
2. Handle common edge cases (timeouts, popup modals, CAPTCHA detection)
3. Implement proper error handling and detailed logging
4. Use explicit waits instead of time.sleep()
5. Handle dynamic content loading
6. Implement retry logic for network issues
7. Clean up resources properly
8. Return structured results

SITE INFORMATION:
- URL: {site_url}
- Known patterns: {known_patterns}
- Previous attempts: {previous_attempts}

SCRAPER STRUCTURE:
```python
import asyncio
import logging
import time
from typing import Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests

# Infrastructure API imports
{infrastructure_imports}

logger = logging.getLogger(__name__)

class {site_class_name}Scraper:
    def __init__(self, headless: bool = True, timeout: int = 30):
        self.timeout = timeout
        self.driver = None
        self.setup_driver(headless)
    
    def setup_driver(self, headless: bool):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
    
    async def {action_method}(self, **kwargs) -> Dict[str, Any]:
        \"\"\"
        Main scraper method for {action_type}
        \"\"\"
        try:
            logger.info(f"Starting {action_type} for {site_name}")
            
            # Navigate to site
            self.driver.get("{site_url}")
            
            # Wait for page load
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # TODO: Implement {action_type} logic here
            
            result = {{
                "success": True,
                "message": "{action_type} completed successfully",
                "data": {{}}
            }}
            
            logger.info(f"{action_type} completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"{action_type} failed: {{e}}")
            await self.report_error(str(e))
            return {{
                "success": False,
                "error": str(e),
                "data": {{}}
            }}
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        if self.driver:
            self.driver.quit()
    
    async def report_error(self, error_message: str):
        try:
            requests.post("http://localhost:8000/api/infrastructure/scraper/report-error",
                         json={{"scraper_id": "{site_name}_{action_type}", "error_data": {{"error": error_message}}}})
        except:
            pass
    
    async def report_success(self, success_data: Dict[str, Any]):
        try:
            requests.post("http://localhost:8000/api/infrastructure/scraper/report-success",
                         json={{"scraper_id": "{site_name}_{action_type}", "success_data": success_data}})
        except:
            pass

# Main execution function
async def main(**kwargs):
    scraper = {site_class_name}Scraper()
    return await scraper.{action_method}(**kwargs)

if __name__ == "__main__":
    import sys
    result = asyncio.run(main())
    print(result)
    sys.exit(0 if result["success"] else 1)
```

Generate the complete scraper code with the specific implementation for {site_name} {action_type}.
Focus on the actual automation steps needed for this specific site.
"""

    ITERATION_TEMPLATE = """
The previous scraper attempt failed. Analyze the error and generate an improved version.

PREVIOUS SCRAPER CODE:
```python
{previous_code}
```

EXECUTION RESULTS:
- Success: {success}
- Error: {error_message}
- Screenshots: {screenshot_analysis}
- HTML Context: {html_context}
- Logs: {execution_logs}

FAILURE ANALYSIS:
{failure_analysis}

IMPROVEMENT INSTRUCTIONS:
1. Analyze the specific error that occurred
2. Identify the root cause (selector issues, timing problems, unexpected UI changes)
3. Implement targeted fixes for the identified issues
4. Add better error handling for similar scenarios
5. Improve selector strategies (use multiple fallback selectors)
6. Add more robust waiting conditions
7. Handle edge cases that weren't considered before

Generate the complete improved scraper code that addresses these specific issues:
"""

    SIGNUP_SPECIFIC_TEMPLATE = """
SIGNUP SCRAPER SPECIFIC REQUIREMENTS:

1. Form Field Handling:
   - Detect and fill all required fields (email, password, name, etc.)
   - Handle password confirmation fields
   - Deal with terms of service checkboxes
   - Handle newsletter subscription options

2. Verification Handling:
   - Email verification: Use setup_email_monitoring() and wait for verification email
   - SMS verification: Use request_sms_verification() and wait_for_sms_code()
   - Phone verification: Use mobile commands if needed

3. Success Detection:
   - Look for welcome messages
   - Check for dashboard redirects
   - Verify account creation confirmation
   - Handle post-signup flows (profile setup, etc.)

4. Common Challenges:
   - CAPTCHA detection and handling
   - Rate limiting and retry logic
   - Dynamic form fields
   - Multi-step signup processes
   - Social login options (skip these)

EXAMPLE SIGNUP FLOW:
```python
async def signup(self, email: str, password: str, **kwargs) -> Dict[str, Any]:
    # Navigate to signup page
    # Fill form fields
    # Handle verification if needed
    # Submit form
    # Wait for success confirmation
    # Return result
```
"""

    SIGNIN_SPECIFIC_TEMPLATE = """
SIGNIN SCRAPER SPECIFIC REQUIREMENTS:

1. Authentication Handling:
   - Standard email/password login
   - Username/password combinations
   - Handle "Remember Me" options
   - Deal with login form variations

2. Two-Factor Authentication:
   - SMS-based 2FA: Use request_sms_verification()
   - Email-based 2FA: Use setup_email_monitoring()
   - Authenticator app 2FA: Use send_mobile_command("extract_totp")
   - Backup codes handling

3. Success Detection:
   - Dashboard redirect detection
   - Profile/account page loading
   - Login success indicators
   - Session establishment verification

4. Error Handling:
   - Invalid credentials detection
   - Account locked/suspended handling
   - Rate limiting responses
   - CAPTCHA challenges

EXAMPLE SIGNIN FLOW:
```python
async def signin(self, email: str, password: str, **kwargs) -> Dict[str, Any]:
    # Navigate to signin page
    # Fill credentials
    # Handle 2FA if prompted
    # Wait for successful login
    # Return result with session info
```
"""

    APIKEY_SPECIFIC_TEMPLATE = """
API KEY CREATION SCRAPER SPECIFIC REQUIREMENTS:

1. Navigation:
   - Find API/Developer settings page
   - Navigate through account/settings menus
   - Handle different UI layouts for API sections

2. API Key Creation:
   - Locate "Create API Key" or similar buttons
   - Fill API key name/description fields
   - Select appropriate permissions/scopes
   - Handle key generation process

3. Key Extraction:
   - Capture the generated API key
   - Handle one-time display warnings
   - Save key securely
   - Extract any additional credentials (secret keys, etc.)

4. Verification:
   - Test API key functionality if possible
   - Verify key permissions
   - Confirm successful creation

EXAMPLE API KEY FLOW:
```python
async def create_api_key(self, key_name: str = "FuzeKeys Integration", **kwargs) -> Dict[str, Any]:
    # Navigate to API settings
    # Create new API key
    # Extract generated key
    # Verify key creation
    # Return key and metadata
```
"""

    @classmethod
    def build_generation_prompt(cls, site_info: SiteInfo) -> str:
        """Build the complete prompt for initial scraper generation"""
        
        # Determine action-specific template
        action_specific = ""
        if site_info.action_type == "signup":
            action_specific = cls.SIGNUP_SPECIFIC_TEMPLATE
        elif site_info.action_type == "signin":
            action_specific = cls.SIGNIN_SPECIFIC_TEMPLATE
        elif site_info.action_type == "apikey_creation":
            action_specific = cls.APIKEY_SPECIFIC_TEMPLATE
        
        # Generate class and method names
        site_class_name = ''.join(word.capitalize() for word in site_info.name.split())
        action_method = site_info.action_type.replace('_', '_')
        
        return cls.BASE_SCRAPER_TEMPLATE.format(
            site_name=site_info.name,
            action_type=site_info.action_type,
            infrastructure_context=cls.INFRASTRUCTURE_CONTEXT,
            site_url=site_info.url,
            known_patterns=site_info.patterns,
            previous_attempts=site_info.previous_attempts,
            site_class_name=site_class_name,
            action_method=action_method,
            infrastructure_imports="# Infrastructure API helper functions included above"
        ) + "\n\n" + action_specific
    
    @classmethod
    def build_iteration_prompt(cls, previous_code: str, execution_result: Dict[str, Any]) -> str:
        """Build prompt for scraper improvement iteration"""
        
        return cls.ITERATION_TEMPLATE.format(
            previous_code=previous_code,
            success=execution_result.get("success", False),
            error_message=execution_result.get("error_message", ""),
            screenshot_analysis=execution_result.get("screenshot_analysis", ""),
            html_context=execution_result.get("html_context", ""),
            execution_logs=execution_result.get("logs", ""),
            failure_analysis=execution_result.get("failure_analysis", "")
        )
    
    @classmethod
    def build_debugging_prompt(cls, code: str, error: str, context: Dict[str, Any]) -> str:
        """Build prompt for debugging specific issues"""
        
        return f"""
DEBUG AND FIX THE FOLLOWING SCRAPER CODE:

CODE:
```python
{code}
```

ERROR:
{error}

CONTEXT:
{context}

INSTRUCTIONS:
1. Identify the exact cause of the error
2. Provide a targeted fix
3. Explain what went wrong and why
4. Suggest preventive measures for similar issues

Generate the corrected code:
""" 