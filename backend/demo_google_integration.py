#!/usr/bin/env python3
"""
Demo script for Google Integration.

This script demonstrates the Google signup functionality including:
1. Testing identity conversion
2. Manual Google signup (with fake data for testing)
3. Configuration options

Run this script to test the Google integration without needing the full web interface.
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.integrations.google.backend.signup import GoogleSignupService
from app.integrations.google.backend.models import GoogleSignupData, GoogleSignupConfig


async def test_manual_signup():
    """Test Google signup with manual data."""
    print("🧪 Testing Google Signup with Manual Data")
    print("=" * 50)
    
    # Create test signup data
    test_data = GoogleSignupData(
        first_name="John",
        last_name="Doe",
        username="testuser12345",  # Use a unique username
        password="TestPassword123!",
        phone_number="+1234567890",
        recovery_email="john.doe.recovery@example.com",
        skip_phone_verification=True  # Try to skip phone verification
    )
    
    # Create configuration for testing
    config = GoogleSignupConfig(
        headless=False,  # Set to False to see the browser in action
        timeout=60,  # Shorter timeout for testing
        retry_attempts=1,  # Only one attempt for demo
        use_mobile_user_agent=False,
        prefer_phone_verification=False,  # Try to avoid phone verification
        auto_handle_captcha=False
    )
    
    print(f"📝 Test Data:")
    print(f"   Name: {test_data.first_name} {test_data.last_name}")
    print(f"   Username: {test_data.username}")
    print(f"   Phone: {test_data.phone_number}")
    print(f"   Recovery Email: {test_data.recovery_email}")
    print(f"   Skip Phone Verification: {test_data.skip_phone_verification}")
    print()
    
    print(f"⚙️ Configuration:")
    print(f"   Headless: {config.headless}")
    print(f"   Timeout: {config.timeout}s")
    print(f"   Retry Attempts: {config.retry_attempts}")
    print(f"   Mobile User Agent: {config.use_mobile_user_agent}")
    print()
    
    # Create the service
    service = GoogleSignupService(config)
    
    try:
        print("🚀 Starting Google signup process...")
        print("⏳ This may take a few minutes...")
        print()
        
        result = await service.signup(test_data)
        
        print("📊 Result:")
        print(f"   Success: {result.success}")
        print(f"   Message: {result.error_message}")
        
        if result.success:
            print(f"   Account Email: {result.account_email}")
            if result.account_id:
                print(f"   Account ID: {result.account_id}")
        
        if result.verification_required:
            print(f"   Verification Required: {result.verification_type}")
            print("   📱 You may need to complete verification manually")
        
        if result.additional_data:
            print(f"   Additional Data: {result.additional_data}")
            
    except Exception as e:
        print(f"❌ Error during signup: {str(e)}")
        return False
    
    return result.success if 'result' in locals() else False


async def test_identity_conversion():
    """Test identity to signup data conversion."""
    print("\n🔄 Testing Identity Conversion")
    print("=" * 50)
    
    # This would normally use a real identity from the database
    # For demo purposes, we'll show what the conversion logic looks like
    
    print("📝 Note: This test requires a real identity from the database.")
    print("   In a real scenario, you would:")
    print("   1. Load an identity from the database")
    print("   2. Call service._identity_to_signup_data(identity)")
    print("   3. Review the generated signup data")
    print()
    
    print("💡 To test this functionality:")
    print("   1. Create identities using the web interface")
    print("   2. Use the test endpoint: POST /api/google/test/identity-conversion/{identity_id}")
    print("   3. Or use the GoogleIntegrationPage frontend component")


def test_configuration_options():
    """Show available configuration options."""
    print("\n⚙️ Configuration Options")
    print("=" * 50)
    
    default_config = GoogleSignupConfig()
    
    print("🔧 Default Configuration:")
    print(f"   headless: {default_config.headless}")
    print(f"   timeout: {default_config.timeout}s")
    print(f"   retry_attempts: {default_config.retry_attempts}")
    print(f"   use_mobile_user_agent: {default_config.use_mobile_user_agent}")
    print(f"   prefer_phone_verification: {default_config.prefer_phone_verification}")
    print(f"   auto_handle_captcha: {default_config.auto_handle_captcha}")
    print(f"   use_proxy: {default_config.use_proxy}")
    print(f"   save_cookies: {default_config.save_cookies}")
    print()
    
    print("🎛️ Customizable Options:")
    print("   • headless: Run browser in background (faster but less debuggable)")
    print("   • timeout: Maximum time to wait for signup completion")
    print("   • retry_attempts: Number of retry attempts on failure")
    print("   • use_mobile_user_agent: Use mobile browser signature")
    print("   • prefer_phone_verification: Use phone verification when available")
    print("   • auto_handle_captcha: Attempt automatic CAPTCHA solving (experimental)")
    print("   • use_proxy: Route traffic through proxy server")
    print("   • proxy_config: Proxy server configuration")
    print("   • custom_user_agent: Custom browser user agent string")


async def main():
    """Main demo function."""
    print("🌟 Google Integration Demo")
    print("=" * 50)
    print()
    
    print("This demo will test the Google account creation functionality.")
    print("Make sure you have Chrome browser installed on your system.")
    print()
    
    # Show configuration options
    test_configuration_options()
    
    # Test identity conversion (informational)
    await test_identity_conversion()
    
    # Ask user if they want to run the actual signup test
    print("\n" + "=" * 50)
    response = input("Do you want to test actual Google signup? (y/N): ").strip().lower()
    
    if response == 'y' or response == 'yes':
        print("\n⚠️ WARNING: This will attempt to create a real Google account!")
        print("The test uses fake data, but Google may still detect automation.")
        print("Proceed only if you understand the risks.")
        confirm = input("Are you sure you want to continue? (y/N): ").strip().lower()
        
        if confirm == 'y' or confirm == 'yes':
            success = await test_manual_signup()
            
            if success:
                print("\n✅ Demo completed successfully!")
            else:
                print("\n❌ Demo completed with errors.")
        else:
            print("\n🛑 Signup test cancelled.")
    else:
        print("\n🛑 Signup test skipped.")
    
    print("\n📚 Next Steps:")
    print("   1. Set up the database and run migrations")
    print("   2. Start the FastAPI server: uvicorn app.main:app --reload")
    print("   3. Access the Google Integration page at: http://localhost:8000/docs")
    print("   4. Use the frontend at: http://localhost:3000/integrations/google")
    print("\n🎉 Thank you for testing the Google Integration!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc() 
"""
Demo script for Google Integration.

This script demonstrates the Google signup functionality including:
1. Testing identity conversion
2. Manual Google signup (with fake data for testing)
3. Configuration options

Run this script to test the Google integration without needing the full web interface.
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.integrations.google.backend.signup import GoogleSignupService
from app.integrations.google.backend.models import GoogleSignupData, GoogleSignupConfig


async def test_manual_signup():
    """Test Google signup with manual data."""
    print("🧪 Testing Google Signup with Manual Data")
    print("=" * 50)
    
    # Create test signup data
    test_data = GoogleSignupData(
        first_name="John",
        last_name="Doe",
        username="testuser12345",  # Use a unique username
        password="TestPassword123!",
        phone_number="+1234567890",
        recovery_email="john.doe.recovery@example.com",
        skip_phone_verification=True  # Try to skip phone verification
    )
    
    # Create configuration for testing
    config = GoogleSignupConfig(
        headless=False,  # Set to False to see the browser in action
        timeout=60,  # Shorter timeout for testing
        retry_attempts=1,  # Only one attempt for demo
        use_mobile_user_agent=False,
        prefer_phone_verification=False,  # Try to avoid phone verification
        auto_handle_captcha=False
    )
    
    print(f"📝 Test Data:")
    print(f"   Name: {test_data.first_name} {test_data.last_name}")
    print(f"   Username: {test_data.username}")
    print(f"   Phone: {test_data.phone_number}")
    print(f"   Recovery Email: {test_data.recovery_email}")
    print(f"   Skip Phone Verification: {test_data.skip_phone_verification}")
    print()
    
    print(f"⚙️ Configuration:")
    print(f"   Headless: {config.headless}")
    print(f"   Timeout: {config.timeout}s")
    print(f"   Retry Attempts: {config.retry_attempts}")
    print(f"   Mobile User Agent: {config.use_mobile_user_agent}")
    print()
    
    # Create the service
    service = GoogleSignupService(config)
    
    try:
        print("🚀 Starting Google signup process...")
        print("⏳ This may take a few minutes...")
        print()
        
        result = await service.signup(test_data)
        
        print("📊 Result:")
        print(f"   Success: {result.success}")
        print(f"   Message: {result.error_message}")
        
        if result.success:
            print(f"   Account Email: {result.account_email}")
            if result.account_id:
                print(f"   Account ID: {result.account_id}")
        
        if result.verification_required:
            print(f"   Verification Required: {result.verification_type}")
            print("   📱 You may need to complete verification manually")
        
        if result.additional_data:
            print(f"   Additional Data: {result.additional_data}")
            
    except Exception as e:
        print(f"❌ Error during signup: {str(e)}")
        return False
    
    return result.success if 'result' in locals() else False


async def test_identity_conversion():
    """Test identity to signup data conversion."""
    print("\n🔄 Testing Identity Conversion")
    print("=" * 50)
    
    # This would normally use a real identity from the database
    # For demo purposes, we'll show what the conversion logic looks like
    
    print("📝 Note: This test requires a real identity from the database.")
    print("   In a real scenario, you would:")
    print("   1. Load an identity from the database")
    print("   2. Call service._identity_to_signup_data(identity)")
    print("   3. Review the generated signup data")
    print()
    
    print("💡 To test this functionality:")
    print("   1. Create identities using the web interface")
    print("   2. Use the test endpoint: POST /api/google/test/identity-conversion/{identity_id}")
    print("   3. Or use the GoogleIntegrationPage frontend component")


def test_configuration_options():
    """Show available configuration options."""
    print("\n⚙️ Configuration Options")
    print("=" * 50)
    
    default_config = GoogleSignupConfig()
    
    print("🔧 Default Configuration:")
    print(f"   headless: {default_config.headless}")
    print(f"   timeout: {default_config.timeout}s")
    print(f"   retry_attempts: {default_config.retry_attempts}")
    print(f"   use_mobile_user_agent: {default_config.use_mobile_user_agent}")
    print(f"   prefer_phone_verification: {default_config.prefer_phone_verification}")
    print(f"   auto_handle_captcha: {default_config.auto_handle_captcha}")
    print(f"   use_proxy: {default_config.use_proxy}")
    print(f"   save_cookies: {default_config.save_cookies}")
    print()
    
    print("🎛️ Customizable Options:")
    print("   • headless: Run browser in background (faster but less debuggable)")
    print("   • timeout: Maximum time to wait for signup completion")
    print("   • retry_attempts: Number of retry attempts on failure")
    print("   • use_mobile_user_agent: Use mobile browser signature")
    print("   • prefer_phone_verification: Use phone verification when available")
    print("   • auto_handle_captcha: Attempt automatic CAPTCHA solving (experimental)")
    print("   • use_proxy: Route traffic through proxy server")
    print("   • proxy_config: Proxy server configuration")
    print("   • custom_user_agent: Custom browser user agent string")


async def main():
    """Main demo function."""
    print("🌟 Google Integration Demo")
    print("=" * 50)
    print()
    
    print("This demo will test the Google account creation functionality.")
    print("Make sure you have Chrome browser installed on your system.")
    print()
    
    # Show configuration options
    test_configuration_options()
    
    # Test identity conversion (informational)
    await test_identity_conversion()
    
    # Ask user if they want to run the actual signup test
    print("\n" + "=" * 50)
    response = input("Do you want to test actual Google signup? (y/N): ").strip().lower()
    
    if response == 'y' or response == 'yes':
        print("\n⚠️ WARNING: This will attempt to create a real Google account!")
        print("The test uses fake data, but Google may still detect automation.")
        print("Proceed only if you understand the risks.")
        confirm = input("Are you sure you want to continue? (y/N): ").strip().lower()
        
        if confirm == 'y' or confirm == 'yes':
            success = await test_manual_signup()
            
            if success:
                print("\n✅ Demo completed successfully!")
            else:
                print("\n❌ Demo completed with errors.")
        else:
            print("\n🛑 Signup test cancelled.")
    else:
        print("\n🛑 Signup test skipped.")
    
    print("\n📚 Next Steps:")
    print("   1. Set up the database and run migrations")
    print("   2. Start the FastAPI server: uvicorn app.main:app --reload")
    print("   3. Access the Google Integration page at: http://localhost:8000/docs")
    print("   4. Use the frontend at: http://localhost:3000/integrations/google")
    print("\n🎉 Thank you for testing the Google Integration!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc() 