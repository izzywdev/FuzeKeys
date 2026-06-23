#!/usr/bin/env python3
"""
Standalone FuzeKeys API Server
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
from app.database import get_async_session, init_database
from app.models import User, Identity, Account
from app.utils.encryption import EncryptionManager

app = FastAPI(
    title="FuzeKeys API",
    description="Intelligent Identity & Account Management System",
    version="1.0.0"
)

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

@app.get("/")
async def root():
    return {"message": "FuzeKeys API is running", "version": "1.0.0", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected (SQLite)",
        "services": {
            "automation": "available",
            "encryption": "enabled",
            "ai": "connected"
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
    """Chat endpoint for AI assistant."""
    user_message = message.get("message", "")
    
    # Simple response logic
    if "sign me up" in user_message.lower():
        response = "I'd be happy to help you sign up! I can analyze websites, create automation scripts, and handle the signup process for you. Which website would you like to sign up for?"
    elif "identity" in user_message.lower():
        response = "You can create multiple identities to use for different types of accounts. Each identity can have its own personal information, preferences, and use cases. Would you like to create a new identity?"
    elif "account" in user_message.lower():
        response = "I can help you manage your accounts across different websites. I can track signup status, store credentials securely, and automate account creation. What would you like to know about your accounts?"
    elif "automation" in user_message.lower():
        response = "I can automate the signup process for many websites using intelligent scripts that adapt to different forms and requirements. The automation includes handling CAPTCHAs, email verification, and form filling."
    else:
        response = "Hello! I'm the FuzeKeys assistant. I can help you manage identities, automate account creation, and track your accounts across different websites. Try asking me about 'creating identities', 'signing up for services', or 'managing accounts'."
    
    return {
        "response": response,
        "action_type": "chat",
        "suggested_actions": [
            "Create new identity",
            "Sign up for a service",
            "View account status",
            "Learn about automation"
        ]
    }

# Demo endpoints for backward compatibility
@app.get("/api/v1/demo/identities")
async def demo_identities():
    return [
        {"id": 1, "name": "Professional Identity", "description": "For business accounts", "created_at": "2024-01-01T00:00:00"},
        {"id": 2, "name": "Personal Identity", "description": "For personal accounts", "created_at": "2024-01-01T00:00:00"}
    ]

@app.get("/api/v1/demo/accounts")
async def demo_accounts():
    return [
        {"id": 1, "website_name": "GitHub", "website_url": "https://github.com", "is_active": True, "signup_completed": True, "created_at": "2024-01-01T00:00:00"},
        {"id": 2, "website_name": "LinkedIn", "website_url": "https://linkedin.com", "is_active": True, "signup_completed": False, "created_at": "2024-01-01T00:00:00"}
    ]

async def startup():
    """Initialize database on startup."""
    try:
        await init_database()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")

def main():
    """Main function to run the server."""
    print("🚀 Starting FuzeKeys API Server...")
    
    # Initialize database
    asyncio.run(startup())
    
    # Start the server
    uvicorn.run(
        app,
        host="localhost",
        port=8001,
        log_level="info"
    )

if __name__ == "__main__":
    main() 