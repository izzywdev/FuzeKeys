#!/usr/bin/env python3
"""
Working FuzeKeys API Server with Database and Background Services
"""
import asyncio
import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uvicorn

# Import our models and database
from app.database import get_async_session
from app.models import User, Identity, Account
from app.utils.encryption import EncryptionManager

# Import background services
from app.services.background_service import initialize_background_manager, get_background_manager
from app.routers.background import router as background_router

app = FastAPI(title="FuzeKeys API with Background Services")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global encryption manager for demo
demo_encryption = EncryptionManager("demo_master_key_123")

# Include background services router
app.include_router(background_router)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    print("🔧 Initializing background services...")
    try:
        # Initialize background services with demo OpenAI key
        openai_key = os.getenv("OPENAI_API_KEY", "demo_key")
        if openai_key == "demo_key":
            print("⚠️  Warning: Using demo OpenAI key. Set OPENAI_API_KEY environment variable for full functionality.")
        
        await initialize_background_manager(openai_key, demo_encryption)
        print("✅ Background services initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing background services: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 Shutting down background services...")
    try:
        manager = await get_background_manager()
        await manager.stop()
        print("✅ Background services stopped successfully")
    except Exception as e:
        print(f"❌ Error stopping background services: {e}")

@app.get("/")
async def root():
    return {
        "message": "FuzeKeys API is running", 
        "version": "1.0.0", 
        "status": "healthy",
        "features": [
            "Identity Management",
            "Account Tracking", 
            "Email Verification Monitoring",
            "AI-Powered Captcha Solving",
            "Automated Signup",
            "Background Task Processing"
        ]
    }

@app.get("/health")
async def health_check():
    """Enhanced health check including background services"""
    try:
        manager = await get_background_manager()
        background_status = {
            "email_monitoring": manager.email_service is not None and manager.running,
            "captcha_solving": True,
            "automation_jobs": len(manager.automation_jobs),
            "pending_tasks": sum(1 for task in manager.tasks.values() if task.status == 'pending'),
            "email_accounts": len(manager.email_configs)
        }
    except Exception:
        background_status = {
            "email_monitoring": False,
            "captcha_solving": False,
            "automation_jobs": 0,
            "pending_tasks": 0,
            "email_accounts": 0
        }
    
    return {
        "status": "healthy",
        "database": "connected (SQLite)",
        "services": {
            "automation": "available",
            "encryption": "enabled",
            "ai": "connected",
            "background_services": background_status
        }
    }

@app.get("/api/v1/identities")
async def get_identities(db: AsyncSession = Depends(get_async_session)):
    """Get all identities for the demo user."""
    try:
        result = await db.execute(select(Identity).where(Identity.user_id == 1))
        identities = result.scalars().all()
        
        identity_list = []
        for identity in identities:
            # Decrypt some fields for display
            first_name = demo_encryption.decrypt(identity.encrypted_first_name) if identity.encrypted_first_name else ""
            last_name = demo_encryption.decrypt(identity.encrypted_last_name) if identity.encrypted_last_name else ""
            email = demo_encryption.decrypt(identity.encrypted_email) if identity.encrypted_email else ""
            
            identity_list.append({
                "id": identity.id,
                "name": identity.name,
                "description": identity.description,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "created_at": identity.created_at.isoformat() if identity.created_at else None
            })
        
        return identity_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching identities: {str(e)}")

@app.get("/api/v1/accounts")
async def get_accounts(db: AsyncSession = Depends(get_async_session)):
    """Get all accounts for the demo user."""
    try:
        # Get accounts with their associated identities
        result = await db.execute(
            select(Account, Identity)
            .join(Identity, Account.identity_id == Identity.id)
            .where(Identity.user_id == 1)
        )
        account_identity_pairs = result.all()
        
        account_list = []
        for account, identity in account_identity_pairs:
            # Decrypt credentials for display
            username = demo_encryption.decrypt(account.encrypted_username) if account.encrypted_username else ""
            email = demo_encryption.decrypt(account.encrypted_email) if account.encrypted_email else ""
            notes = demo_encryption.decrypt(account.encrypted_notes) if account.encrypted_notes else ""
            
            account_list.append({
                "id": account.id,
                "website_name": account.website_name,
                "website_url": account.website_url,
                "website_domain": account.website_domain,
                "username": username,
                "email": email,
                "is_active": account.is_active,
                "is_verified": account.is_verified,
                "signup_completed": account.signup_completed,
                "signup_method": account.signup_method,
                "notes": notes,
                "identity_name": identity.name,
                "created_at": account.created_at.isoformat() if account.created_at else None
            })
        
        return account_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching accounts: {str(e)}")

@app.post("/api/v1/chat")
async def chat_endpoint(message: dict):
    """Enhanced chat endpoint with background service integration."""
    user_message = message.get("message", "")
    
    # Enhanced response logic with background service context
    if "sign me up" in user_message.lower():
        response = """I'd be happy to help you sign up! I can:
        
🤖 **Automated Signup**: Create accounts automatically using intelligent scripts
📧 **Email Verification**: Monitor your email and handle verification links automatically  
🔍 **Captcha Solving**: Use AI to solve text and image captchas
🛡️ **Secure Storage**: Store credentials with encryption
        
Which website would you like to sign up for? I can handle popular sites like GitHub, LinkedIn, Twitter, and more."""
        
    elif "email" in user_message.lower() and "verification" in user_message.lower():
        response = """I can automatically handle email verification for you! Here's how:
        
📨 **Email Monitoring**: I monitor your email accounts for verification emails
🔗 **Auto-Verification**: Automatically click verification links when detected
⚡ **Real-time Processing**: Handle verifications within minutes of receiving them
🔒 **Secure**: Your email credentials are encrypted and never stored in plain text
        
To set this up, use the background services API to add your email configuration."""
        
    elif "captcha" in user_message.lower():
        response = """I can solve captchas using advanced AI! Supported types:
        
📝 **Text Captchas**: Read distorted text using vision AI
🖼️ **Image Selection**: "Select all traffic lights" style challenges  
🤖 **reCAPTCHA**: Handle both checkbox and image challenges
🛡️ **hCaptcha**: Similar to reCAPTCHA with different styling
        
The AI has high success rates and can handle most common captcha types automatically."""
        
    elif "automation" in user_message.lower() or "background" in user_message.lower():
        response = """Background automation is running! Current capabilities:
        
🔄 **Task Queue**: Process multiple signup jobs simultaneously
📊 **Job Tracking**: Monitor progress of all automation tasks
🔁 **Auto-Retry**: Automatically retry failed operations
💾 **State Persistence**: Resume tasks after restarts
        
Check `/api/v1/background/status` for current service status."""
        
    elif "identity" in user_message.lower():
        response = """Manage multiple digital identities for different use cases:
        
👤 **Professional Identity**: For LinkedIn, GitHub, work-related accounts
🏠 **Personal Identity**: For social media, entertainment, shopping
🎓 **Academic Identity**: For educational platforms, courses
🔒 **All Encrypted**: Personal information is securely encrypted
        
Each identity can have different names, emails, and preferences."""
        
    else:
        response = """Hello! I'm the FuzeKeys AI assistant with advanced automation capabilities:
        
🤖 **Automated Signups**: I can create accounts automatically
📧 **Email Verification**: Monitor and handle email confirmations  
🔍 **Captcha Solving**: AI-powered captcha solving
👤 **Identity Management**: Manage multiple digital identities
📊 **Real-time Tracking**: Monitor all automation jobs
        
Try asking about 'automated signups', 'email verification', 'captcha solving', or 'background services'."""
    
    return {
        "response": response,
        "action_type": "chat",
        "suggested_actions": [
            "Start automated signup",
            "Configure email monitoring",
            "Test captcha solving",
            "View automation status",
            "Create new identity"
        ]
    }

if __name__ == "__main__":
    print("🚀 Starting FuzeKeys API Server with Background Services on port 8002...")
    print("✨ Features: Email Verification, Captcha Solving, Automated Signup")
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info") 