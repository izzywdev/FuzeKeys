from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class IdentityCard(Base):
    """Metadata + Vaultwarden handle for a persona's stored card. No PAN/CVV here."""
    __tablename__ = "identity_cards"

    id = Column(Integer, primary_key=True, index=True)
    identity_id = Column(Integer, ForeignKey("identities.id"), nullable=False, index=True)
    brand = Column(String(40))
    last4 = Column(String(4))
    exp_month = Column(Integer)
    exp_year = Column(Integer)
    vault_item_ref = Column(String(255), nullable=False)  # Vaultwarden Card item id
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    identity = relationship("Identity")


class ApiCredential(Base):
    """Metadata + OpenBao path for a persona's API token / service secret. No value here."""
    __tablename__ = "api_credentials"

    id = Column(Integer, primary_key=True, index=True)
    identity_id = Column(Integer, ForeignKey("identities.id"), nullable=False, index=True)
    service = Column(String(120), nullable=False)
    name = Column(String(120), nullable=False)
    openbao_path = Column(String(300), nullable=False)  # KV v2 path; value lives in OpenBao
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    identity = relationship("Identity")
