from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """Local projection of a FuzeFront-authenticated principal.

    This is NOT a credential store. FuzeKeys does not authenticate anybody —
    the FuzeFront Security API does, and `app.security` resolves the caller's
    identity from it. This row exists so the integer `id` that every FuzeKeys
    foreign key points at (identities, accounts, vault assets) keeps working,
    and so profile fields render without a round trip per request.

    Deliberately absent: any password. It was removed in the FuzeFront Security
    migration — a product that stores user passwords has taken ownership of
    authentication, which is exactly what this repo must not do.

    `master_key_hash` stays. It is FuzeKeys' DOMAIN secret: the user-held key
    that unlocks the encrypted vault. It is not a login factor, and FuzeFront
    never sees it.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Stable FuzeFront subject id (`Identity.userId`) — the real identity key.
    # Nullable so a pre-migration row can be adopted on first sign-in.
    fuzefront_user_id = Column(String(255), unique=True, index=True, nullable=True)

    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)

    # Vault master-key verifier (FuzeKeys domain, NOT authentication).
    # Nullable: a freshly-provisioned user has not set up their vault yet.
    master_key_hash = Column(String(255), nullable=True)

    # Profile information
    first_name = Column(String(100))
    last_name = Column(String(100))
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    identities = relationship("Identity", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>" 