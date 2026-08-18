from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ApiKey(Base):
    """ApiKey model for storing API keys and tokens."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    # API Key information
    key_name = Column(String(200), nullable=False)  # Name/description of the key
    key_type = Column(
        String(100), nullable=False
    )  # api_key, access_token, bearer_token, etc.

    # Encrypted key data
    encrypted_key_value = Column(Text, nullable=False)  # The actual key/token
    encrypted_secret = Column(Text)  # Secret key if applicable (OAuth)

    # Key metadata
    scopes = Column(JSON)  # Permissions/scopes for this key
    permissions = Column(JSON)  # Detailed permissions
    environment = Column(String(50), default="production")  # production, sandbox, test

    # Expiration and rotation
    expires_at = Column(DateTime(timezone=True))
    auto_rotate = Column(Boolean, default=False)
    rotation_interval_days = Column(Integer)  # Auto-rotation interval

    # Usage tracking
    last_used = Column(DateTime(timezone=True))
    usage_count = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime(timezone=True))
    revoke_reason = Column(String(500))

    # Additional encrypted data
    encrypted_additional_data = Column(Text)  # JSON of additional key-related data
    encrypted_notes = Column(Text)  # Private notes about this key

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    account = relationship("Account", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey(id={self.id}, name='{self.key_name}', type='{self.key_type}', account_id={self.account_id})>"

    def is_expired(self):
        """Check if the API key is expired."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone

        return datetime.now(timezone.utc) > self.expires_at

    def needs_rotation(self):
        """Check if the API key needs rotation."""
        if not self.auto_rotate or self.rotation_interval_days is None:
            return False

        from datetime import datetime, timedelta, timezone

        rotation_due = self.created_at + timedelta(days=self.rotation_interval_days)
        return datetime.now(timezone.utc) > rotation_due
