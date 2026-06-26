from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class StageType(enum.Enum):
    """Enum for different account creation stages."""
    EMAIL_VERIFICATION = "email_verification"
    PHONE_VERIFICATION = "phone_verification" 
    PROFILE_SETUP = "profile_setup"
    TWO_FACTOR_AUTH = "two_factor_auth"
    DOCUMENT_VERIFICATION = "document_verification"
    CAPTCHA = "captcha"
    HUMAN_VERIFICATION = "human_verification"
    TERMS_ACCEPTANCE = "terms_acceptance"
    EMAIL_CONFIRMATION = "email_confirmation"
    ACCOUNT_ACTIVATION = "account_activation"


class StageStatus(enum.Enum):
    """Enum for stage completion status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_REQUIRED = "not_required"


class AccountStage(Base):
    """Model for tracking account creation stages."""
    
    __tablename__ = "account_stages"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    
    # Stage information
    stage_type = Column(Enum(StageType), nullable=False)
    stage_name = Column(String(100), nullable=False)  # Display name
    stage_description = Column(Text)  # Description of what this stage involves
    
    # Status tracking
    status = Column(Enum(StageStatus), default=StageStatus.PENDING)
    attempts = Column(Integer, default=0)
    
    # Stage-specific data (encrypted)
    encrypted_stage_data = Column(Text)  # JSON blob for stage-specific information
    error_message = Column(Text)  # Error details if failed
    
    # Timestamps
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    account = relationship("Account", back_populates="stages")
    
    def __repr__(self):
        return f"<AccountStage(id={self.id}, account_id={self.account_id}, stage={self.stage_type.value}, status={self.status.value})>"


class Account(Base):
    """Account model for storing website accounts."""
    
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    identity_id = Column(Integer, ForeignKey("identities.id"), nullable=False)
    
    # Website information
    website_name = Column(String(200), nullable=False)
    website_url = Column(String(500), nullable=False)
    website_domain = Column(String(200), index=True)  # For easy searching
    
    # Account credentials (encrypted)
    encrypted_username = Column(Text)
    encrypted_email = Column(Text)
    encrypted_password = Column(Text)
    
    # Comprehensive encrypted credentials (for API access)
    encrypted_credentials = Column(Text)  # JSON blob of all credentials

    # Identity-vault (Phase 1): handle to the Vaultwarden Login item. The
    # encrypted_* columns stay for now; Phase 6 migrates values out and drops them.
    vault_item_ref = Column(String(255), nullable=True, index=True)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    signup_completed = Column(Boolean, default=False)
    
    # Account metadata
    account_type = Column(String(100))  # free, premium, etc.
    signup_method = Column(String(50))  # manual, automated
    
    # Additional encrypted information
    encrypted_security_questions = Column(Text)  # JSON of security Q&A
    encrypted_notes = Column(Text)  # Additional notes
    
    # Automation information
    signup_script_id = Column(Integer, ForeignKey("signup_scripts.id"))
    signup_attempts = Column(Integer, default=0)
    last_signup_attempt = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_accessed = Column(DateTime(timezone=True))
    
    # Relationships
    identity = relationship("Identity", back_populates="accounts")
    signup_script = relationship("SignupScript", back_populates="accounts")
    api_keys = relationship("ApiKey", back_populates="account", cascade="all, delete-orphan")
    stages = relationship("AccountStage", back_populates="account", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Account(id={self.id}, website='{self.website_name}', identity_id={self.identity_id})>" 