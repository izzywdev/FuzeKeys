#!/usr/bin/env python3
"""
Database initialization script for testing
Populates the database with sample sites data
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.database import get_db, engine
from app.models.site import Site
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def init_database():
    """Initialize database with sample data"""
    print("🔧 Initializing test database...")
    
    # Create tables
    try:
        from app.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False
    
    # Load sample sites data
    sites_file = Path(__file__).parent / "app" / "site_directory" / "supported_sites.json"
    if not sites_file.exists():
        print(f"❌ Sites data file not found: {sites_file}")
        return False
    
    with open(sites_file, 'r') as f:
        sites_data = json.load(f)
    
    # Insert sample sites
    async with AsyncSession(engine) as session:
        # Check if sites already exist
        result = await session.execute(text("SELECT COUNT(*) FROM sites"))
        count = result.scalar()
        
        if count > 0:
            print(f"ℹ️  Database already has {count} sites, skipping initialization")
            return True
        
        print("📝 Adding sample sites...")
        sites_to_add = []
        
        for site_key, site_data in sites_data["sites"].items():
            site = Site(
                name=site_key,
                display_name=site_data["name"],
                url=site_data["url"],
                logo_url=f"https://www.google.com/s2/favicons?domain={site_data['url']}",
                category=_get_category_from_url(site_data["url"]),
                description=f"{site_data['name']} - {', '.join(site_data['supported_actions'])}",
                signup_difficulty=_get_random_difficulty(),
                signin_difficulty=_get_random_difficulty(),
                apikey_difficulty=_get_random_difficulty() if "apikey_creation" in site_data.get("supported_actions", []) else "not_applicable",
                overall_difficulty=_get_random_difficulty(),
                requires_email_verification=True,
                requires_phone_verification=site_key == "google",  # Google requires phone
                requires_sms_verification=False,
                requires_authenticator=site_key in ["google", "github"],
                has_captcha=site_key == "google",
                captcha_type="recaptcha" if site_key == "google" else None,
                anti_bot_techniques=_get_anti_bot_techniques_by_site(site_key),
                signup_status="in_progress" if site_key == "google" else "not_started",
                signin_status="completed" if site_key == "github" else "in_progress",
                apikey_status="completed" if site_key == "openai" else "not_started",
                implementation_progress=_get_progress_by_site(site_key),
                priority=_get_priority_by_site(site_key),
                estimated_hours=_get_estimated_hours_by_site(site_key),
                has_official_api=True,
                api_documentation_url=_get_api_docs_url(site_data["url"]),
                api_rate_limits=_get_rate_limits_by_site(site_key),
                notes=f"Generated test data for {site_data['name']}",
                created_at=datetime.utcnow()
            )
            sites_to_add.append(site)
        
        # Add additional test sites for variety
        additional_sites = [
            {
                "name": "linkedin",
                "display_name": "LinkedIn",
                "url": "https://linkedin.com",
                "category": "social",
                "description": "Professional networking platform",
                "priority": 75,
                "progress": 25.0,
                "difficulty": "hard"
            },
            {
                "name": "twitter",
                "display_name": "Twitter/X",
                "url": "https://twitter.com",
                "category": "social",
                "description": "Social media platform",
                "priority": 60,
                "progress": 80.0,
                "difficulty": "medium"
            },
            {
                "name": "facebook",
                "display_name": "Facebook",
                "url": "https://facebook.com",
                "category": "social",
                "description": "Social networking service",
                "priority": 50,
                "progress": 100.0,
                "difficulty": "extreme"
            },
            # Add more sites to test pagination
            {
                "name": "amazon",
                "display_name": "Amazon",
                "url": "https://amazon.com",
                "category": "e-commerce",
                "description": "Online marketplace and cloud platform",
                "priority": 85,
                "progress": 45.0,
                "difficulty": "hard"
            },
            {
                "name": "microsoft",
                "display_name": "Microsoft",
                "url": "https://microsoft.com",
                "category": "tech-giant",
                "description": "Technology and cloud services",
                "priority": 90,
                "progress": 60.0,
                "difficulty": "extreme"
            },
            {
                "name": "netflix",
                "display_name": "Netflix",
                "url": "https://netflix.com",
                "category": "entertainment",
                "description": "Streaming service platform",
                "priority": 40,
                "progress": 90.0,
                "difficulty": "medium"
            },
            {
                "name": "spotify",
                "display_name": "Spotify",
                "url": "https://spotify.com",
                "category": "entertainment",
                "description": "Music streaming platform",
                "priority": 35,
                "progress": 100.0,
                "difficulty": "easy"
            },
            {
                "name": "slack",
                "display_name": "Slack",
                "url": "https://slack.com",
                "category": "productivity",
                "description": "Team communication platform",
                "priority": 70,
                "progress": 75.0,
                "difficulty": "medium"
            },
            {
                "name": "discord",
                "display_name": "Discord",
                "url": "https://discord.com",
                "category": "social",
                "description": "Gaming and community platform",
                "priority": 55,
                "progress": 30.0,
                "difficulty": "hard"
            },
            {
                "name": "stripe",
                "display_name": "Stripe",
                "url": "https://stripe.com",
                "category": "fintech",
                "description": "Payment processing platform",
                "priority": 80,
                "progress": 20.0,
                "difficulty": "extreme"
            }
        ]
        
        for site_data in additional_sites:
            site = Site(
                name=site_data["name"],
                display_name=site_data["display_name"],
                url=site_data["url"],
                logo_url=f"https://www.google.com/s2/favicons?domain={site_data['url']}",
                category=site_data["category"],
                description=site_data["description"],
                signup_difficulty=site_data.get("difficulty", "medium"),
                signin_difficulty="easy" if site_data.get("difficulty") == "easy" else "medium",
                apikey_difficulty="not_applicable",
                overall_difficulty=site_data.get("difficulty", "medium"),
                requires_email_verification=True,
                requires_phone_verification=False,
                requires_sms_verification=False,
                requires_authenticator=False,
                has_captcha=True,
                captcha_type="recaptcha",
                anti_bot_techniques=_get_anti_bot_techniques_by_site(site_data["name"]),
                signup_status="completed" if site_data["progress"] == 100.0 else "in_progress",
                signin_status="completed",
                apikey_status="not_applicable",
                implementation_progress=site_data["progress"],
                priority=site_data["priority"],
                estimated_hours=20,
                has_official_api=True,
                api_documentation_url=f"{site_data['url']}/developers",
                api_rate_limits="Standard rate limits apply",
                notes=f"Test data for {site_data['display_name']}",
                created_at=datetime.utcnow()
            )
            sites_to_add.append(site)
        
        # Add all sites to the session
        for site in sites_to_add:
            session.add(site)
        
        await session.commit()
        print(f"✅ Added {len(sites_to_add)} sites to database")
        
        # Verify the data
        result = await session.execute(text("SELECT COUNT(*) FROM sites"))
        final_count = result.scalar()
        print(f"📊 Total sites in database: {final_count}")
        
        return True

def _get_category_from_url(url: str) -> str:
    """Get category based on URL"""
    if "google" in url:
        return "tech-giant"
    elif "github" in url:
        return "developer-tools"
    elif "openai" in url:
        return "ai-platform"
    elif any(social in url for social in ["linkedin", "twitter", "facebook"]):
        return "social"
    else:
        return "general"

def _get_random_difficulty() -> str:
    """Get a reasonable difficulty level"""
    import random
    return random.choice(["easy", "medium", "hard", "extreme"])

def _get_progress_by_site(site_key: str) -> float:
    """Get progress based on site"""
    progress_map = {
        "google": 33.3,
        "github": 100.0,
        "openai": 66.7
    }
    return progress_map.get(site_key, 0.0)

def _get_priority_by_site(site_key: str) -> int:
    """Get priority based on site"""
    priority_map = {
        "google": 100,
        "github": 85,
        "openai": 90
    }
    return priority_map.get(site_key, 50)

def _get_estimated_hours_by_site(site_key: str) -> int:
    """Get estimated hours based on site"""
    hours_map = {
        "google": 40,
        "github": 8,
        "openai": 25
    }
    return hours_map.get(site_key, 15)

def _get_api_docs_url(base_url: str) -> str:
    """Generate API docs URL"""
    domain_to_docs = {
        "google.com": "https://developers.google.com",
        "github.com": "https://docs.github.com/en/rest",
        "openai.com": "https://platform.openai.com/docs/api-reference"
    }
    
    for domain, docs_url in domain_to_docs.items():
        if domain in base_url:
            return docs_url
    
    return f"{base_url}/api/docs"

def _get_rate_limits_by_site(site_key: str) -> str:
    """Get rate limits based on site"""
    limits_map = {
        "google": "Varies by service",
        "github": "5000 requests/hour",
        "openai": "Rate limits vary by model"
    }
    return limits_map.get(site_key, "Standard rate limits")

def _get_anti_bot_techniques_by_site(site_key: str) -> list:
    """Get anti-bot techniques based on site and difficulty"""
    techniques_map = {
        "google": [
            "fingerprinting",
            "behavioral_analysis", 
            "javascript_challenges",
            "canvas_fingerprinting",
            "timing_analysis",
            "session_validation",
            "csrf_tokens",
            "dynamic_selectors"
        ],
        "github": [
            "rate_limiting",
            "csrf_tokens",
            "user_agent_detection"
        ],
        "openai": [
            "rate_limiting",
            "session_validation",
            "csrf_tokens",
            "ip_reputation"
        ],
        "linkedin": [
            "fingerprinting",
            "behavioral_analysis",
            "javascript_challenges",
            "session_validation"
        ],
        "twitter": [
            "rate_limiting",
            "fingerprinting",
            "hidden_fields",
            "csrf_tokens"
        ],
        "facebook": [
            "fingerprinting",
            "behavioral_analysis",
            "javascript_challenges",
            "dynamic_selectors",
            "obfuscated_javascript"
        ],
        "amazon": [
            "fingerprinting",
            "behavioral_analysis",
            "rate_limiting",
            "session_validation",
            "csrf_tokens"
        ],
        "microsoft": [
            "fingerprinting",
            "behavioral_analysis",
            "javascript_challenges",
            "canvas_fingerprinting",
            "session_validation",
            "csrf_tokens"
        ],
        "netflix": [
            "rate_limiting",
            "session_validation",
            "csrf_tokens"
        ],
        "spotify": [
            "rate_limiting"
        ],
        "slack": [
            "rate_limiting",
            "csrf_tokens",
            "session_validation"
        ],
        "discord": [
            "fingerprinting",
            "rate_limiting",
            "csrf_tokens",
            "session_validation"
        ],
        "stripe": [
            "fingerprinting",
            "behavioral_analysis",
            "javascript_challenges",
            "csrf_tokens",
            "session_validation",
            "ip_reputation"
        ]
    }
    return techniques_map.get(site_key, ["rate_limiting"])

async def main():
    """Main function"""
    try:
        success = await init_database()
        if success:
            print("🎉 Database initialization completed successfully!")
            return 0
        else:
            print("❌ Database initialization failed!")
            return 1
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 