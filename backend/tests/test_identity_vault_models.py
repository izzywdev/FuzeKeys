"""
Phase 1 data-tier model tests for the identity-vault subsystem.

These import ONLY model modules (never app.main, which has a pre-existing cv2
import break) and run against in-memory SQLite.
"""
import pytest
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401  registers every table on Base.metadata
from app.models import (
    Organization, OrganizationMember, Identity, IdentityCard, ApiCredential,
    Account, Agent, AgentScope, ApprovalRequest, AuditLog, User,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make_user(session, email="john@acme.test", username="john"):
    user = User(email=email, username=username, hashed_password="x",
                master_key_hash="y")
    session.add(user)
    session.commit()
    return user


# --- Task 1 --------------------------------------------------------------
def test_organization_row_roundtrips(session):
    org = Organization(name="Acme Corp", slug="acme")
    session.add(org)
    session.commit()
    fetched = session.query(Organization).filter_by(slug="acme").one()
    assert fetched.id is not None
    assert fetched.name == "Acme Corp"


# --- Task 2 --------------------------------------------------------------
def test_org_member_defaults_to_member_and_is_unique(session):
    user = _make_user(session)
    org = Organization(name="Acme", slug="acme2")
    session.add(org)
    session.commit()

    m = OrganizationMember(organization_id=org.id, user_id=user.id)
    session.add(m)
    session.commit()
    assert m.role == "member"

    dup = OrganizationMember(organization_id=org.id, user_id=user.id)
    session.add(dup)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        session.commit()
    session.rollback()


# --- Task 3 --------------------------------------------------------------
def test_identity_has_org_and_vault_ref(session):
    org = Organization(name="Acme", slug="acme3")
    session.add(org)
    session.commit()
    ident = Identity(name="Alice Smith", user_id=1, org_id=org.id,
                     vault_collection_ref="col_abc123")
    session.add(ident)
    session.commit()
    got = session.query(Identity).filter_by(vault_collection_ref="col_abc123").one()
    assert got.org_id == org.id


# --- Task 4 --------------------------------------------------------------
def test_card_and_api_credential_store_only_handles(session):
    ident = Identity(name="Bob", user_id=1)
    session.add(ident)
    session.commit()
    card = IdentityCard(identity_id=ident.id, brand="visa", last4="4242",
                        exp_month=12, exp_year=2030, vault_item_ref="item_card1")
    tok = ApiCredential(identity_id=ident.id, service="github", name="ci-token",
                        openbao_path="kv/identities/1/github/ci-token")
    session.add_all([card, tok])
    session.commit()
    assert session.query(IdentityCard).one().last4 == "4242"
    assert session.query(ApiCredential).one().openbao_path.startswith("kv/")
    assert not hasattr(IdentityCard, "number")
    assert not hasattr(ApiCredential, "token_value")


# --- Task 5 --------------------------------------------------------------
def test_account_has_vault_item_ref(session):
    ident = Identity(name="Carol", user_id=1)
    session.add(ident)
    session.commit()
    acct = Account(identity_id=ident.id, website_name="twitter",
                   website_url="https://twitter.com", vault_item_ref="item_login1")
    session.add(acct)
    session.commit()
    assert session.query(Account).one().vault_item_ref == "item_login1"


# --- Task 6 --------------------------------------------------------------
def test_agent_binds_to_user_and_stores_hashed_token(session):
    agent = Agent(name="signup-bot", user_id=1, token_hash="sha256:deadbeef")
    session.add(agent)
    session.commit()
    scope = AgentScope(agent_id=agent.id, scope_type="identity", scope_ref="42")
    session.add(scope)
    session.commit()
    got = session.query(Agent).one()
    assert got.user_id == 1
    assert got.token_hash == "sha256:deadbeef"
    assert not hasattr(Agent, "token")
    assert got.is_active is True
    assert session.query(AgentScope).one().scope_type == "identity"


# --- Task 7 --------------------------------------------------------------
def test_approval_defaults_pending_and_audit_has_no_secret_column(session):
    req = ApprovalRequest(agent_id=1, resource_ref="identity:42:card:7")
    session.add(req)
    session.commit()
    assert req.status == "pending"

    entry = AuditLog(agent_id=1, on_behalf_user_id=1, identity_id=42,
                     resource_ref="identity:42:login:twitter", decision="auto_release")
    session.add(entry)
    session.commit()
    assert session.query(AuditLog).one().decision == "auto_release"
    assert not hasattr(AuditLog, "secret_value")
