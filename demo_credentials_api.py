#!/usr/bin/env python3
"""
Credentials API Demo

This script demonstrates how microservices can request and use credentials
for identities and accounts through the secure credentials API.

Usage: python demo_credentials_api.py
"""

import asyncio
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CredentialsAPIDemo:
    """Demo class for the credentials API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_keys = {
            "scraper-service": "scraper-key-12345",
            "mobile-service": "mobile-key-12345",
            "automation-service": "automation-key-12345"
        }
    
    def make_request(self, method: str, endpoint: str, service: str = "scraper-service", **kwargs):
        """Make authenticated API request"""
        
        headers = {
            "X-API-Key": self.api_keys[service],
            "Content-Type": "application/json"
        }
        
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
            del kwargs["headers"]
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None
    
    def demo_request_identity_credentials(self):
        """Demo requesting credentials for an identity to sign up for a site"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: REQUEST IDENTITY CREDENTIALS FOR SIGNUP")
        logger.info("="*60)
        
        # Demo request for GitHub signup
        request_data = {
            "identity_id": 1,
            "site_name": "github",
            "action_type": "signup",
            "credential_types": ["email", "password", "username", "name"]
        }
        
        logger.info(f"🚀 Requesting credentials for GitHub signup:")
        logger.info(f"   Identity ID: {request_data['identity_id']}")
        logger.info(f"   Site: {request_data['site_name']}")
        logger.info(f"   Action: {request_data['action_type']}")
        logger.info(f"   Requested types: {request_data['credential_types']}")
        
        response = self.make_request(
            "POST", 
            "/api/credentials/request-identity-credentials",
            json=request_data
        )
        
        if response:
            logger.info(f"✅ Credentials generated successfully!")
            logger.info(f"📧 Email: {response['credentials'].get('email', 'N/A')}")
            logger.info(f"🔒 Password: {response['credentials'].get('password', 'N/A')[:8]}...")
            logger.info(f"👤 Username: {response['credentials'].get('username', 'N/A')}")
            logger.info(f"📛 Name: {response['credentials'].get('name', 'N/A')}")
            logger.info(f"📊 Metadata: {response['metadata']['requested_by']}")
        else:
            logger.error("❌ Failed to get credentials")
        
        return response
    
    def demo_request_account_credentials(self):
        """Demo requesting stored credentials for an existing account"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: REQUEST STORED ACCOUNT CREDENTIALS")
        logger.info("="*60)
        
        request_data = {
            "account_id": 1,
            "credential_types": ["email", "password"]
        }
        
        logger.info(f"🔑 Requesting stored credentials:")
        logger.info(f"   Account ID: {request_data['account_id']}")
        logger.info(f"   Requested types: {request_data['credential_types']}")
        
        response = self.make_request(
            "POST",
            "/api/credentials/request-account-credentials", 
            json=request_data
        )
        
        if response:
            logger.info(f"✅ Stored credentials retrieved!")
            logger.info(f"🏷️  Site: {response['site_name']}")
            logger.info(f"📧 Email: {response['credentials'].get('email', 'N/A')}")
            logger.info(f"🔒 Password: {'*' * len(response['credentials'].get('password', ''))}")
            logger.info(f"🕒 Last used: {response.get('last_used', 'Never')}")
        else:
            logger.error("❌ Failed to get stored credentials")
        
        return response
    
    def demo_store_credentials(self):
        """Demo storing credentials after successful signup"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: STORE CREDENTIALS AFTER SIGNUP")
        logger.info("="*60)
        
        # Simulate successful signup credentials
        store_data = {
            "account_id": 1,
            "credentials": {
                "email": "john.doe.1703123456@example.com",
                "password": "JohnDoePass123!",
                "username": "johndoe_a1b2",
                "api_key": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "two_factor_backup_codes": ["123456", "789012", "345678"]
            },
            "metadata": {
                "signup_date": datetime.utcnow().isoformat(),
                "verification_method": "email",
                "account_type": "free"
            }
        }
        
        logger.info(f"💾 Storing credentials after successful signup:")
        logger.info(f"   Account ID: {store_data['account_id']}")
        logger.info(f"   Credentials stored: {list(store_data['credentials'].keys())}")
        
        response = self.make_request(
            "POST",
            "/api/credentials/store-account-credentials",
            json=store_data
        )
        
        if response:
            logger.info(f"✅ Credentials stored successfully!")
            logger.info(f"📄 Message: {response['message']}")
            logger.info(f"🆔 Account ID: {response['account_id']}")
        else:
            logger.error("❌ Failed to store credentials")
        
        return response
    
    def demo_get_account_credentials(self):
        """Demo getting credentials for a specific account"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: GET ACCOUNT CREDENTIALS (GET ENDPOINT)")
        logger.info("="*60)
        
        account_id = 1
        credential_types = "email,password,api_key"
        
        logger.info(f"🔍 Getting credentials via GET endpoint:")
        logger.info(f"   Account ID: {account_id}")
        logger.info(f"   Requested types: {credential_types}")
        
        response = self.make_request(
            "GET",
            f"/api/credentials/account/{account_id}/credentials?credential_types={credential_types}"
        )
        
        if response:
            logger.info(f"✅ Credentials retrieved!")
            logger.info(f"🏷️  Site: {response['site_name']}")
            credentials = response['credentials']
            for cred_type, value in credentials.items():
                if cred_type == "password":
                    logger.info(f"   {cred_type}: {'*' * len(str(value))}")
                elif cred_type == "api_key":
                    logger.info(f"   {cred_type}: {str(value)[:8]}...")
                else:
                    logger.info(f"   {cred_type}: {value}")
        else:
            logger.error("❌ Failed to get credentials")
        
        return response
    
    def demo_get_identity_accounts(self):
        """Demo getting all accounts for an identity"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: GET ALL ACCOUNTS FOR IDENTITY")
        logger.info("="*60)
        
        identity_id = 1
        
        logger.info(f"📋 Getting all accounts for identity:")
        logger.info(f"   Identity ID: {identity_id}")
        
        response = self.make_request(
            "GET",
            f"/api/credentials/identity/{identity_id}/accounts"
        )
        
        if response:
            logger.info(f"✅ Account list retrieved!")
            logger.info(f"👤 Identity: {response['identity_name']}")
            logger.info(f"📊 Total accounts: {response['total_accounts']}")
            
            for account in response['accounts']:
                status = "✅ Active" if account['is_active'] else "❌ Inactive"
                signup_status = "✅ Complete" if account['signup_completed'] else "⏳ Pending"
                creds_status = "🔑 Yes" if account['has_stored_credentials'] else "❌ No"
                
                logger.info(f"   📱 {account['site_name']}:")
                logger.info(f"      Status: {status}")
                logger.info(f"      Signup: {signup_status}")
                logger.info(f"      Stored Creds: {creds_status}")
                logger.info(f"      Created: {account['created_at'][:10]}")
        else:
            logger.error("❌ Failed to get accounts")
        
        return response
    
    def demo_validate_credentials(self):
        """Demo validating credentials format"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: VALIDATE CREDENTIALS FORMAT")
        logger.info("="*60)
        
        # Test valid credentials
        test_credentials = {
            "email": "test@example.com",
            "password": "SecurePass123!",
            "username": "test_user_123"
        }
        
        logger.info(f"🔍 Validating credentials for GitHub:")
        logger.info(f"   Email: {test_credentials['email']}")
        logger.info(f"   Password: {'*' * len(test_credentials['password'])}")
        logger.info(f"   Username: {test_credentials['username']}")
        
        response = self.make_request(
            "POST",
            "/api/credentials/validate-credentials",
            params={"site_name": "github"},
            json=test_credentials
        )
        
        if response:
            if response['valid']:
                logger.info(f"✅ Credentials are valid!")
            else:
                logger.error(f"❌ Credentials validation failed:")
                if response['missing_fields']:
                    logger.error(f"   Missing: {response['missing_fields']}")
                if response['invalid_fields']:
                    logger.error(f"   Invalid: {response['invalid_fields']}")
        else:
            logger.error("❌ Failed to validate credentials")
        
        # Test invalid credentials
        logger.info(f"\n🔍 Testing invalid credentials:")
        
        invalid_credentials = {
            "email": "invalid-email",
            "password": "short",
            "username": "user@invalid"
        }
        
        response = self.make_request(
            "POST",
            "/api/credentials/validate-credentials",
            params={"site_name": "github"},
            json=invalid_credentials
        )
        
        if response:
            if not response['valid']:
                logger.info(f"✅ Validation correctly identified issues:")
                if response['missing_fields']:
                    logger.info(f"   Missing: {response['missing_fields']}")
                if response['invalid_fields']:
                    logger.info(f"   Invalid: {response['invalid_fields']}")
            else:
                logger.error(f"❌ Validation should have failed!")
        
        return response
    
    def demo_multi_service_access(self):
        """Demo different services accessing the API"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: MULTI-SERVICE API ACCESS")
        logger.info("="*60)
        
        # Test different service access
        services = ["scraper-service", "mobile-service", "automation-service"]
        
        for service in services:
            logger.info(f"\n🔑 Testing access as {service}:")
            
            request_data = {
                "identity_id": 1,
                "site_name": "google",
                "action_type": "signin",
                "credential_types": ["email", "password"]
            }
            
            response = self.make_request(
                "POST",
                "/api/credentials/request-identity-credentials",
                service=service,
                json=request_data
            )
            
            if response:
                logger.info(f"   ✅ Access granted for {service}")
                logger.info(f"   📧 Email: {response['credentials'].get('email', 'N/A')}")
                logger.info(f"   🔄 Requested by: {response['metadata']['requested_by']}")
            else:
                logger.error(f"   ❌ Access denied for {service}")
    
    def demo_health_check(self):
        """Demo the health check endpoint"""
        
        logger.info("\n" + "="*60)
        logger.info("DEMO: CREDENTIALS API HEALTH CHECK")
        logger.info("="*60)
        
        response = self.make_request("GET", "/api/credentials/health")
        
        if response:
            logger.info(f"✅ Credentials API is healthy!")
            logger.info(f"   Status: {response['status']}")
            logger.info(f"   Service: {response['service']}")
            logger.info(f"   Encryption: {response['encryption']}")
            logger.info(f"   Timestamp: {response['timestamp']}")
        else:
            logger.error("❌ Health check failed")
        
        return response
    
    def run_complete_demo(self):
        """Run the complete credentials API demo"""
        
        logger.info("🚀 Starting Credentials API Demo")
        logger.info("=" * 80)
        
        try:
            # Health check
            self.demo_health_check()
            
            # Request credentials for identity
            self.demo_request_identity_credentials()
            
            # Store credentials after signup
            self.demo_store_credentials()
            
            # Request stored account credentials
            self.demo_request_account_credentials()
            
            # Get credentials via GET endpoint
            self.demo_get_account_credentials()
            
            # Get all accounts for identity
            self.demo_get_identity_accounts()
            
            # Validate credentials format
            self.demo_validate_credentials()
            
            # Multi-service access
            self.demo_multi_service_access()
            
            logger.info("\n" + "="*80)
            logger.info("✅ CREDENTIALS API DEMO COMPLETED SUCCESSFULLY!")
            logger.info("="*80)
            
        except Exception as e:
            logger.error(f"❌ Demo failed: {e}")
            import traceback
            traceback.print_exc()

def main():
    """Main demo function"""
    
    print("🔐 Credentials API Demo")
    print("=" * 50)
    print()
    print("This demo shows how microservices can securely:")
    print("1. Request credentials for identities (for signups)")
    print("2. Store credentials after successful signups")
    print("3. Retrieve stored credentials for existing accounts")
    print("4. Validate credential formats")
    print("5. Access via different service API keys")
    print()
    
    choice = input("Press Enter to start demo, or 'q' to quit: ").strip().lower()
    
    if choice == 'q':
        print("Demo cancelled.")
        return
    
    demo = CredentialsAPIDemo()
    demo.run_complete_demo()

if __name__ == "__main__":
    main() 