"""
Database configuration and utilities for FuzeKeys.
Modified to use PostgreSQL for production-ready deployment.
"""
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import os
from pathlib import Path

# PostgreSQL database URL - FuzeKeys database on FuzeInfra
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://fuzekeys_user:fuzekeys_password@localhost:5432/fuzekeys"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    pool_pre_ping=True,
    pool_recycle=300,
)

# Create session maker
async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for backward compatibility
get_db = get_async_session


async def create_tables():
    """Create all database tables."""
    try:
        from app.models import User, Identity, Account, AccountStage, SignupScript, ApiKey
        
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Database tables created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        raise


async def init_database():
    """Initialize database with sample data."""
    try:
        await create_tables()
        
        # Add sample data for demo
        async with async_session_maker() as session:
            from app.models import User, Identity, Account, AccountStage, StageType, StageStatus
            from app.utils.encryption import EncryptionManager
            import hashlib
            from datetime import datetime
            
            # Check if data already exists
            existing_user = await session.get(User, 1)
            if existing_user:
                print("✅ Database already initialized with sample data")
                return
            
            # Create demo user
            demo_user = User(
                email="demo@fuzekeys.com",
                username="demo_user",
                hashed_password=hashlib.sha256("demo123".encode()).hexdigest(),
                master_key_hash=hashlib.sha256("masterkey123".encode()).hexdigest(),
                is_active=True
            )
            session.add(demo_user)
            await session.flush()  # Get the user ID
            
            # Initialize encryption manager with a demo master key
            demo_master_key = "demo_master_key_123"
            encryption_manager = EncryptionManager(demo_master_key)
            
            # Create demo identities with simple data structure
            professional_identity = Identity(
                user_id=demo_user.id,
                name="Professional Identity",
                description="For business and professional accounts",
                encrypted_first_name=encryption_manager.encrypt("Alex"),
                encrypted_last_name=encryption_manager.encrypt("Johnson"),
                encrypted_email=encryption_manager.encrypt("alex.johnson.pro@email.com"),
                encrypted_phone=encryption_manager.encrypt("+1-555-0123"),
                encrypted_address_line1=encryption_manager.encrypt("123 Tech Street"),
                encrypted_city=encryption_manager.encrypt("San Francisco"),
                encrypted_state=encryption_manager.encrypt("CA"),
                encrypted_zip_code=encryption_manager.encrypt("94105"),
                encrypted_country=encryption_manager.encrypt("USA"),
                encrypted_profession=encryption_manager.encrypt("Software Developer"),
                encrypted_company=encryption_manager.encrypt("TechCorp Inc."),
                encrypted_bio=encryption_manager.encrypt("Experienced software developer specializing in full-stack applications")
            )
            
            personal_identity = Identity(
                user_id=demo_user.id,
                name="Personal Identity", 
                description="For social media and personal accounts",
                encrypted_first_name=encryption_manager.encrypt("Alex"),
                encrypted_last_name=encryption_manager.encrypt("J"),
                encrypted_email=encryption_manager.encrypt("alexj.personal@email.com"),
                encrypted_phone=encryption_manager.encrypt("+1-555-0124"),
                encrypted_address_line1=encryption_manager.encrypt("California, USA"),
                encrypted_profession=encryption_manager.encrypt("Tech Enthusiast"),
                encrypted_bio=encryption_manager.encrypt("Tech enthusiast who loves exploring new technologies")
            )
            
            session.add_all([professional_identity, personal_identity])
            await session.flush()
            
            # Create demo accounts with stages
            accounts_data = [
                {
                    "identity": professional_identity,
                    "website": "GitHub",
                    "url": "https://github.com",
                    "domain": "github.com",
                    "username": "alex_johnson_dev",
                    "email": "alex.johnson.pro@email.com",
                    "password": "SecurePass123!",
                    "completed": True,
                    "notes": "Used for software development projects"
                },
                {
                    "identity": professional_identity,
                    "website": "LinkedIn",
                    "url": "https://linkedin.com",
                    "domain": "linkedin.com",
                    "username": "alex-johnson-dev",
                    "email": "alex.johnson.pro@email.com",
                    "password": "LinkedInPass456!",
                    "completed": True,
                    "notes": "Professional networking account"
                },
                {
                    "identity": personal_identity,
                    "website": "Twitter",
                    "url": "https://twitter.com",
                    "domain": "twitter.com",
                    "username": "alexj_tech",
                    "email": "alexj.personal@email.com",
                    "password": "TwitterPass789!",
                    "completed": False,
                    "notes": "Phone verification pending"
                },
                {
                    "identity": personal_identity,
                    "website": "Instagram",
                    "url": "https://instagram.com",
                    "domain": "instagram.com",
                    "username": "alexj_photo",
                    "email": "alexj.personal@email.com",
                    "password": "InstaPass101!",
                    "completed": False,
                    "notes": "Human verification required"
                }
            ]
            
            for account_data in accounts_data:
                # Create the account
                account = Account(
                    identity_id=account_data["identity"].id,
                    website_name=account_data["website"],
                    website_url=account_data["url"],
                    website_domain=account_data["domain"],
                    encrypted_username=encryption_manager.encrypt(account_data["username"]),
                    encrypted_email=encryption_manager.encrypt(account_data["email"]),
                    encrypted_password=encryption_manager.encrypt(account_data["password"]),
                    is_active=True,
                    signup_completed=account_data["completed"],
                    signup_method="automated",
                    encrypted_notes=encryption_manager.encrypt(account_data["notes"])
                )
                session.add(account)
                await session.flush()
                
                # Create stages for the account
                stages_config = {
                    "GitHub": [
                        (StageType.EMAIL_VERIFICATION, "Email Verification", StageStatus.COMPLETED),
                        (StageType.PROFILE_SETUP, "Profile Setup", StageStatus.COMPLETED),
                        (StageType.TERMS_ACCEPTANCE, "Terms Acceptance", StageStatus.COMPLETED),
                        (StageType.ACCOUNT_ACTIVATION, "Account Activation", StageStatus.COMPLETED),
                    ],
                    "LinkedIn": [
                        (StageType.EMAIL_VERIFICATION, "Email Verification", StageStatus.COMPLETED),
                        (StageType.PROFILE_SETUP, "Profile Setup", StageStatus.COMPLETED),
                        (StageType.TERMS_ACCEPTANCE, "Terms Acceptance", StageStatus.COMPLETED),
                        (StageType.ACCOUNT_ACTIVATION, "Account Activation", StageStatus.COMPLETED),
                    ],
                    "Twitter": [
                        (StageType.EMAIL_VERIFICATION, "Email Verification", StageStatus.COMPLETED),
                        (StageType.PHONE_VERIFICATION, "Phone Verification", StageStatus.FAILED),
                        (StageType.PROFILE_SETUP, "Profile Setup", StageStatus.PENDING),
                        (StageType.TERMS_ACCEPTANCE, "Terms Acceptance", StageStatus.PENDING),
                        (StageType.ACCOUNT_ACTIVATION, "Account Activation", StageStatus.PENDING),
                    ],
                    "Instagram": [
                        (StageType.EMAIL_VERIFICATION, "Email Verification", StageStatus.COMPLETED),
                        (StageType.PHONE_VERIFICATION, "Phone Verification", StageStatus.IN_PROGRESS),
                        (StageType.HUMAN_VERIFICATION, "Human Verification", StageStatus.PENDING),
                        (StageType.PROFILE_SETUP, "Profile Setup", StageStatus.PENDING),
                        (StageType.TERMS_ACCEPTANCE, "Terms Acceptance", StageStatus.PENDING),
                        (StageType.ACCOUNT_ACTIVATION, "Account Activation", StageStatus.PENDING),
                    ]
                }
                
                website_stages = stages_config.get(account_data["website"], [])
                for stage_type, stage_name, status in website_stages:
                    stage = AccountStage(
                        account_id=account.id,
                        stage_type=stage_type,
                        stage_name=stage_name,
                        status=status,
                        attempts=1 if status != StageStatus.PENDING else 0,
                        started_at=datetime.utcnow() if status in [StageStatus.COMPLETED, StageStatus.IN_PROGRESS, StageStatus.FAILED] else None,
                        completed_at=datetime.utcnow() if status == StageStatus.COMPLETED else None,
                        error_message="Phone number verification timeout" if stage_type == StageType.PHONE_VERIFICATION and status == StageStatus.FAILED else None
                    )
                    session.add(stage)
            
            await session.commit()
            print("✅ Sample data created successfully!")
            
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        raise


async def check_connection():
    """Check database connection."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(init_database()) 