"""
Demo script for FuzeKeys Site Integrations

This script demonstrates how to use the site integrations system
for automated account management.
"""

import asyncio
import sys
import os

# Add the backend to the path so we can import the integrations
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.integrations.site.permit_io import PermitIOIntegration
from app.integrations.site.permit_io.models import PermitIOCredentials
from app.integrations.site import get_available_sites, get_site_capabilities

async def demo_site_discovery():
    """Demo the site discovery functionality."""
    print("🔍 Site Discovery Demo")
    print("=" * 50)
    
    # Get available sites
    sites = get_available_sites()
    print(f"Available sites: {sites}")
    
    # Get capabilities for each site
    for site in sites:
        capabilities = get_site_capabilities(site)
        print(f"\n{site} capabilities:")
        for cap, available in capabilities.items():
            status = "✅" if available else "❌"
            print(f"  {status} {cap}")
    
    print("\n")

async def demo_permit_io_integration():
    """Demo the permit.io integration functionality."""
    print("🔧 Permit.io Integration Demo")
    print("=" * 50)
    
    # Sample credentials (using fake data for demo)
    credentials = PermitIOCredentials(
        email="demo@example.com",
        password="DemoPassword123!",
        first_name="Demo",
        last_name="User",
        company_name="Demo Company"
    )
    
    print(f"Demo credentials: {credentials.email}")
    print("Note: This demo uses fake credentials and runs in headless mode\n")
    
    # Create integration instance
    integration = PermitIOIntegration(headless=True)
    
    # Demo signup (will fail with fake credentials, but shows the workflow)
    print("1. 📝 Signup Demo")
    print("-" * 30)
    try:
        result = await integration.signup_account(credentials)
        print(f"Signup result: {result.success}")
        print(f"Message: {result.message}")
        if result.error:
            print(f"Error: {result.error}")
        if result.data:
            print(f"Data: {result.data}")
    except Exception as e:
        print(f"Signup demo error (expected with fake credentials): {str(e)}")
    
    print("\n2. 🔐 Signin Demo")
    print("-" * 30)
    try:
        result = await integration.signin_account(credentials.email, credentials.password)
        print(f"Signin result: {result.success}")
        print(f"Message: {result.message}")
        if result.error:
            print(f"Error: {result.error}")
    except Exception as e:
        print(f"Signin demo error (expected with fake credentials): {str(e)}")
    
    print("\n3. 🔑 API Key Creation Demo")
    print("-" * 30)
    try:
        result = await integration.create_api_key(
            credentials.email, 
            credentials.password, 
            "Demo-Key"
        )
        print(f"API Key creation result: {result.success}")
        print(f"Message: {result.message}")
        if result.error:
            print(f"Error: {result.error}")
    except Exception as e:
        print(f"API Key demo error (expected with fake credentials): {str(e)}")
    
    print("\n")

async def demo_api_usage():
    """Demo how to use the REST API endpoints."""
    print("🌐 REST API Usage Demo")
    print("=" * 50)
    
    print("The site integrations are available via REST API:")
    print("\n1. List available sites:")
    print("   GET /api/v1/integrations/sites")
    
    print("\n2. Get site capabilities:")
    print("   GET /api/v1/integrations/sites/permit.io/capabilities")
    
    print("\n3. Create account:")
    print("   POST /api/v1/integrations/signup")
    print("   Body: {")
    print('     "site": "permit.io",')
    print('     "email": "user@example.com",')
    print('     "password": "secure_password",')
    print('     "first_name": "John",')
    print('     "last_name": "Doe"')
    print("   }")
    
    print("\n4. Sign in:")
    print("   POST /api/v1/integrations/signin")
    print("   Body: {")
    print('     "site": "permit.io",')
    print('     "email": "user@example.com",')
    print('     "password": "secure_password"')
    print("   }")
    
    print("\n5. Create API key:")
    print("   POST /api/v1/integrations/apikey")
    print("   Body: {")
    print('     "site": "permit.io",')
    print('     "email": "user@example.com",')
    print('     "password": "secure_password",')
    print('     "key_name": "MyAPIKey"')
    print("   }")
    
    print("\n")

def print_architecture():
    """Print the site integrations architecture."""
    print("🏗️ Site Integrations Architecture")
    print("=" * 50)
    
    architecture = """
backend/app/integrations/site/
├── __init__.py                 # Integration discovery and management
├── permit_io/                  # Permit.io integration
│   ├── __init__.py            # Main integration class
│   ├── models.py              # Data models (credentials, results)
│   ├── config.py              # Site-specific configuration
│   ├── signup.py              # Account creation automation
│   ├── signin.py              # Authentication automation
│   └── apikey.py              # API key creation automation
└── [future_sites]/            # Templates for additional integrations

Key Features:
• 🤖 Automated account creation, authentication, and API key generation
• 🎯 Site-specific configuration and form detection
• 📸 Screenshot debugging and error reporting  
• 🔒 Session management and credential handling
• 🔧 Extensible architecture for new site integrations
• 🌐 REST API endpoints for all operations
    """
    
    print(architecture)
    print("\n")

async def main():
    """Run all demos."""
    print("🚀 FuzeKeys Site Integrations Demo")
    print("=" * 60)
    print("This demo showcases the site integration capabilities of FuzeKeys")
    print("for automated account management across various platforms.\n")
    
    # Print architecture first
    print_architecture()
    
    # Run demos
    await demo_site_discovery()
    await demo_permit_io_integration()
    await demo_api_usage()
    
    print("✅ Demo completed!")
    print("=" * 60)
    print("To use with real credentials:")
    print("1. Update the credentials in this script")
    print("2. Set headless=False to see the browser automation")
    print("3. Check the screenshots generated for debugging")
    print("4. Use the REST API endpoints in your applications")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        print("Note: This is expected when using fake credentials") 