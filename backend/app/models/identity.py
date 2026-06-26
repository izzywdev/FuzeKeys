from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Identity(Base):
    """Identity model for storing digital identities."""
    
    __tablename__ = "identities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Identity-vault (Phase 1): tenant + handle to the Vaultwarden collection
    # holding this persona's encrypted PII / cards / logins. No secrets here.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    vault_collection_ref = Column(String(255), nullable=True, index=True)

    # Identity metadata
    name = Column(String(200), nullable=False)  # Display name for this identity
    description = Column(Text)  # Description of when to use this identity
    
    # Encrypted personal information
    encrypted_first_name = Column(Text)
    encrypted_last_name = Column(Text)
    encrypted_email = Column(Text)
    encrypted_phone = Column(Text)
    encrypted_date_of_birth = Column(Text)
    
    # Encrypted address information
    encrypted_address_line1 = Column(Text)
    encrypted_address_line2 = Column(Text)
    encrypted_city = Column(Text)
    encrypted_state = Column(Text)
    encrypted_zip_code = Column(Text)
    encrypted_country = Column(Text)
    
    # Encrypted additional information
    encrypted_profession = Column(Text)
    encrypted_company = Column(Text)
    encrypted_bio = Column(Text)
    encrypted_gender = Column(Text)  # Added for platform-specific requirements
    
    # Custom fields (encrypted JSON)
    encrypted_custom_fields = Column(Text)  # JSON string of custom fields
    
    # Preferences
    preferred_username_pattern = Column(String(100))  # Pattern for generating usernames
    password_preferences = Column(JSON)  # Password generation preferences
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="identities")
    accounts = relationship("Account", back_populates="identity", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Identity(id={self.id}, name='{self.name}', user_id={self.user_id})>" 
        return f"<Identity(id={self.id}, name='{self.name}', user_id={self.user_id})>" 