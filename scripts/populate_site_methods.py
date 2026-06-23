#!/usr/bin/env python3
"""
Populate site automation methods for existing sites.

This script updates the database with method availability information
for sites that already exist in the system.
"""

import sys
import os
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_async_session
from app.models.site import Site, AutomationMethod, AutomationFramework

# Site method configurations based on current implementation
SITE_METHOD_CONFIGS = {
    'google': {
        'signup_methods': ['scraping'],
        'signin_methods': ['scraping'],
        'apikey_methods': [],  # Not implemented yet
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.SCRAPING,
        'apikey_preferred_method': AutomationMethod.API,
        'automation_framework': AutomationFramework.SELENIUM,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': False,
        'requires_user_agent_rotation': True,
        'api_base_url': 'https://accounts.google.com',
        'api_authentication_method': 'oauth'
    },
    'permit.io': {
        'signup_methods': ['scraping'],
        'signin_methods': ['scraping'],
        'apikey_methods': ['scraping'],
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.SCRAPING,
        'apikey_preferred_method': AutomationMethod.SCRAPING,
        'automation_framework': AutomationFramework.PLAYWRIGHT,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': False,
        'requires_user_agent_rotation': False,
        'api_base_url': 'https://app.permit.io',
        'api_authentication_method': 'session'
    },
    'github': {
        'signup_methods': ['scraping', 'api'],
        'signin_methods': ['scraping', 'api'],
        'apikey_methods': ['api'],
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.API,
        'apikey_preferred_method': AutomationMethod.API,
        'automation_framework': AutomationFramework.SELENIUM,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': False,
        'requires_user_agent_rotation': False,
        'api_base_url': 'https://api.github.com',
        'api_signup_endpoint': None,  # GitHub doesn't allow API signup
        'api_signin_endpoint': 'https://github.com/login/oauth/access_token',
        'api_key_endpoint': 'https://api.github.com/user/keys',
        'api_authentication_method': 'oauth'
    },
    'openai': {
        'signup_methods': ['scraping'],
        'signin_methods': ['scraping'],
        'apikey_methods': ['scraping'],
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.SCRAPING,
        'apikey_preferred_method': AutomationMethod.SCRAPING,
        'automation_framework': AutomationFramework.PLAYWRIGHT,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': False,
        'requires_user_agent_rotation': False,
        'api_base_url': 'https://api.openai.com',
        'api_key_endpoint': 'https://platform.openai.com/api-keys',
        'api_authentication_method': 'api_key'
    },
    # Add more sites as they are implemented
    'aws': {
        'signup_methods': ['scraping'],
        'signin_methods': ['scraping'],
        'apikey_methods': ['scraping'],
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.SCRAPING,
        'apikey_preferred_method': AutomationMethod.SCRAPING,
        'automation_framework': AutomationFramework.SELENIUM,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': True,  # AWS has strong anti-bot measures
        'requires_user_agent_rotation': True,
        'api_base_url': 'https://aws.amazon.com',
        'api_authentication_method': 'iam'
    },
    'azure': {
        'signup_methods': ['scraping'],
        'signin_methods': ['scraping', 'api'],
        'apikey_methods': ['scraping'],
        'signup_preferred_method': AutomationMethod.SCRAPING,
        'signin_preferred_method': AutomationMethod.API,
        'apikey_preferred_method': AutomationMethod.SCRAPING,
        'automation_framework': AutomationFramework.SELENIUM,
        'requires_javascript': True,
        'requires_browser_automation': True,
        'requires_proxy': False,
        'requires_user_agent_rotation': False,
        'api_base_url': 'https://login.microsoftonline.com',
        'api_authentication_method': 'oauth'
    }
}

async def populate_site_methods():
    """Populate method information for existing sites."""
    print("🔄 Starting site method population...")
    
    async for session in get_async_session():
        try:
            # Get all existing sites
            result = await session.execute(select(Site))
            sites = result.scalars().all()
            
            updated_count = 0
            
            for site in sites:
                site_key = site.name.lower().replace(' ', '.').replace('-', '.')
                
                if site_key in SITE_METHOD_CONFIGS:
                    config = SITE_METHOD_CONFIGS[site_key]
                    
                    print(f"📝 Updating {site.display_name} ({site.name})...")
                    
                    # Update method availability
                    site.signup_methods = config.get('signup_methods', [])
                    site.signin_methods = config.get('signin_methods', [])
                    site.apikey_methods = config.get('apikey_methods', [])
                    
                    # Update preferred methods
                    site.signup_preferred_method = config.get('signup_preferred_method')
                    site.signin_preferred_method = config.get('signin_preferred_method')
                    site.apikey_preferred_method = config.get('apikey_preferred_method')
                    
                    # Update automation framework
                    site.automation_framework = config.get('automation_framework')
                    site.requires_javascript = config.get('requires_javascript', True)
                    site.requires_browser_automation = config.get('requires_browser_automation', True)
                    site.requires_proxy = config.get('requires_proxy', False)
                    site.requires_user_agent_rotation = config.get('requires_user_agent_rotation', False)
                    
                    # Update API details
                    site.api_base_url = config.get('api_base_url')
                    site.api_signup_endpoint = config.get('api_signup_endpoint')
                    site.api_signin_endpoint = config.get('api_signin_endpoint')
                    site.api_key_endpoint = config.get('api_key_endpoint')
                    site.api_authentication_method = config.get('api_authentication_method')
                    
                    # Set has_official_api based on available methods
                    has_api_methods = any(
                        'api' in methods for methods in [
                            site.signup_methods, 
                            site.signin_methods, 
                            site.apikey_methods
                        ]
                    )
                    site.has_official_api = has_api_methods
                    
                    updated_count += 1
                else:
                    print(f"⚠️  No configuration found for {site.display_name} ({site.name})")
                    
                    # Set default values for unknown sites
                    site.signup_methods = []
                    site.signin_methods = []
                    site.apikey_methods = []
                    site.automation_framework = AutomationFramework.SELENIUM
                    site.requires_javascript = True
                    site.requires_browser_automation = True
                    site.requires_proxy = False
                    site.requires_user_agent_rotation = False
            
            # Commit all changes
            await session.commit()
            
            print(f"✅ Successfully updated {updated_count} sites with method information")
            print(f"📊 Total sites processed: {len(sites)}")
            
        except Exception as e:
            print(f"❌ Error updating sites: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def create_sample_sites():
    """Create sample sites with method information for testing."""
    print("🏗️  Creating sample sites...")
    
    sample_sites = [
        {
            'name': 'stripe',
            'display_name': 'Stripe',
            'url': 'https://stripe.com',
            'category': 'payments',
            'description': 'Payment processing platform',
            'signup_methods': ['scraping'],
            'signin_methods': ['scraping'],
            'apikey_methods': ['scraping'],
            'automation_framework': AutomationFramework.PLAYWRIGHT,
            'api_base_url': 'https://api.stripe.com',
            'has_official_api': True
        },
        {
            'name': 'discord',
            'display_name': 'Discord',
            'url': 'https://discord.com',
            'category': 'social-media',
            'description': 'Chat and communication platform',
            'signup_methods': ['scraping'],
            'signin_methods': ['scraping'],
            'apikey_methods': ['scraping'],
            'automation_framework': AutomationFramework.SELENIUM,
            'api_base_url': 'https://discord.com/api',
            'has_official_api': True
        }
    ]
    
    async for session in get_async_session():
        try:
            created_count = 0
            
            for site_data in sample_sites:
                # Check if site already exists
                result = await session.execute(
                    select(Site).where(Site.name == site_data['name'])
                )
                existing_site = result.scalar_one_or_none()
                
                if not existing_site:
                    site = Site(**site_data)
                    session.add(site)
                    created_count += 1
                    print(f"✨ Created sample site: {site_data['display_name']}")
            
            await session.commit()
            print(f"✅ Created {created_count} sample sites")
            
        except Exception as e:
            print(f"❌ Error creating sample sites: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def main():
    """Main function to run the population script."""
    print("🚀 Site Method Population Script")
    print("=" * 50)
    
    try:
        await populate_site_methods()
        await create_sample_sites()
        print("\n🎉 Site method population completed successfully!")
        
    except Exception as e:
        print(f"\n💥 Script failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 