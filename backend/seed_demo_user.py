#!/usr/bin/env python3
"""
Standalone seed script: creates the fuzekeys DB tables (via SQLAlchemy create_all)
and inserts the demo user (demo_user / demo123, sha256-hashed password).

Run from backend/ with:
    DATABASE_URL=postgresql://fuzekeys_user:fuzekeys_dev_password@localhost:5433/fuzekeys \
        python seed_demo_user.py

This script intentionally imports ONLY the data-tier modules so it is not blocked
by cv2/numpy/OpenAI import-time errors in routers or automation code.
"""
import asyncio
import hashlib
import os
import sys
from pathlib import Path

# Make app package importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure DATABASE_URL is set to the sync asyncpg variant before database.py is imported.
# seed_demo_user provides the sync psycopg2 URL via DATABASE_URL; database.py wraps it.
raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://fuzekeys_user:fuzekeys_dev_password@localhost:5433/fuzekeys",
)

# database.py picks up DATABASE_URL at import time — normalise it to asyncpg scheme here.
if raw_url.startswith("postgresql://") and "+asyncpg" not in raw_url:
    async_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgresql+asyncpg://"):
    async_url = raw_url
else:
    async_url = raw_url

os.environ["DATABASE_URL"] = async_url

# Import only the data-tier modules — never main.py / routers (cv2 lives there).
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models manually to avoid any router-level imports
from app.database import Base as AppBase, engine, async_session_maker
from app.models.user import User
from app.models.identity import Identity
from app.models.account import Account, AccountStage, StageType, StageStatus
from app.models.signup_script import SignupScript
from app.models.api_key import ApiKey
from app.utils.encryption import EncryptionManager


async def seed():
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    print("Tables created (or already exist).")

    async with async_session_maker() as session:
        existing = await session.get(User, 1)
        if existing:
            print(f"Demo user already exists: id={existing.id} username={existing.username}")
            # Verify password hash matches
            expected_hash = hashlib.sha256("demo123".encode()).hexdigest()
            if existing.hashed_password == expected_hash:
                print("Password hash matches demo123 — login will work.")
            else:
                print("WARNING: password hash does not match demo123!")
            return

        print("Seeding demo user...")
        demo_user = User(
            email="demo@fuzekeys.local",
            username="demo_user",
            hashed_password=hashlib.sha256("demo123".encode()).hexdigest(),
            master_key_hash=hashlib.sha256("masterkey123".encode()).hexdigest(),
            is_active=True,
        )
        session.add(demo_user)
        await session.flush()
        print(f"Created user id={demo_user.id}")

        # Minimal identities so the app doesn't break on an empty dataset
        enc = EncryptionManager("demo_master_key_123")
        professional = Identity(
            user_id=demo_user.id,
            name="Professional Identity",
            description="For business and professional accounts",
            encrypted_first_name=enc.encrypt("Alex"),
            encrypted_last_name=enc.encrypt("Johnson"),
            encrypted_email=enc.encrypt("alex.johnson@techcorp.example"),
            encrypted_phone=enc.encrypt("+1-555-0123"),
            encrypted_address_line1=enc.encrypt("123 Tech Street"),
            encrypted_city=enc.encrypt("San Francisco"),
            encrypted_state=enc.encrypt("CA"),
            encrypted_zip_code=enc.encrypt("94105"),
            encrypted_country=enc.encrypt("USA"),
            encrypted_profession=enc.encrypt("Software Developer"),
            encrypted_company=enc.encrypt("TechCorp Inc."),
            encrypted_bio=enc.encrypt("Experienced software developer specialising in full-stack apps"),
        )
        personal = Identity(
            user_id=demo_user.id,
            name="Personal Identity",
            description="For social media and personal accounts",
            encrypted_first_name=enc.encrypt("Alex"),
            encrypted_last_name=enc.encrypt("J"),
            encrypted_email=enc.encrypt("alexj.personal@example.com"),
            encrypted_phone=enc.encrypt("+1-555-0124"),
            encrypted_address_line1=enc.encrypt("California, USA"),
            encrypted_profession=enc.encrypt("Tech Enthusiast"),
            encrypted_bio=enc.encrypt("Tech enthusiast who loves exploring new technologies"),
        )
        session.add_all([professional, personal])
        await session.flush()
        print(f"Created identities id={professional.id}, id={personal.id}")

        await session.commit()
        print("Seed complete.")
        print()
        print("  username : demo_user")
        print("  password : demo123")
        print(f"  DB       : {async_url}")


if __name__ == "__main__":
    asyncio.run(seed())
