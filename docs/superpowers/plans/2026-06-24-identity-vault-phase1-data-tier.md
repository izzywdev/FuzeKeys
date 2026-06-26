# Identity Vault — Phase 1: Data-Tier Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the relational tenancy/agent/approval/audit tables and vault-handle columns that the identity-vault subsystem needs, as an **additive** schema change (no renames, no secret-column removal yet).

**Architecture:** New SQLAlchemy models under `backend/app/models/` plus one Alembic migration. Postgres stores only non-secret metadata + handles (Vaultwarden collection/item refs, OpenBao paths). Personas remain private to their owning user. The disruptive rename (`accounts`→`site_logins`) and Fernet-column removal are deferred to Phase 6 to keep this phase low-risk and reversible.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x (DeclarativeBase via `app.database.Base`), Alembic, pytest. Tests use in-memory SQLite + `Base.metadata.create_all` and import only model modules (NOT `app.main`, which has a pre-existing `cv2`/numpy import break).

## Global Constraints

- No secret material in Postgres — only metadata + handles (`vault_collection_ref`, `vault_item_ref`, `openbao_path`). Copied verbatim from spec §3 (decision 3) and §5.
- Personas are private to their owning user: every `identities` row has `owner_user_id` (FK `users.id`, NOT NULL). (spec §3 decision 7)
- Agent tokens are stored **hashed**, never in plaintext (column `token_hash`). (spec §7)
- Additive only this phase: do NOT rename `accounts`, do NOT drop any existing column. (spec §8 migration, deferred)
- Match existing model style: `from app.database import Base`, `Column(...)`, `server_default=func.now()` for timestamps, `relationship(...)` with `back_populates`. (see `backend/app/models/identity.py`, `account.py`)
- Tests must not import `app.main` (pre-existing cv2 break); build a local SQLite engine in the test module.

---

## File Structure

- Create `backend/app/models/organization.py` — `Organization`, `OrganizationMember`.
- Create `backend/app/models/agent.py` — `Agent`, `AgentScope`.
- Create `backend/app/models/approval.py` — `ApprovalRequest`, `AuditLog`.
- Create `backend/app/models/vault_assets.py` — `IdentityCard`, `ApiCredential`.
- Modify `backend/app/models/identity.py` — add `org_id`, `vault_collection_ref` (keep existing `user_id` as owner).
- Modify `backend/app/models/account.py` — add `vault_item_ref` column (no rename).
- Modify `backend/app/models/__init__.py` — export the new models so Alembic autogenerate sees them.
- Create `backend/alembic/versions/e4a1f0b21c01_identity_vault_phase1.py` — the migration.
- Create `backend/tests/test_identity_vault_models.py` — model tests (SQLite, no `app.main`).

---

### Task 1: Test scaffolding + `Organization` model

**Files:**
- Create: `backend/app/models/organization.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_identity_vault_models.py`

**Interfaces:**
- Consumes: `app.database.Base`; existing `User` (`app.models.user.User`, table `users`).
- Produces: `Organization` (table `organizations`, cols: `id:int pk`, `name:str`, `slug:str unique`, `created_at`), relationship `members -> OrganizationMember`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_identity_vault_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
# Import every model module so all tables register on Base.metadata.
import app.models.user  # noqa: F401
import app.models.identity  # noqa: F401
import app.models.account  # noqa: F401
import app.models.organization as org_models


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_organization_row_roundtrips(session):
    org = org_models.Organization(name="Acme Corp", slug="acme")
    session.add(org)
    session.commit()
    fetched = session.query(org_models.Organization).filter_by(slug="acme").one()
    assert fetched.id is not None
    assert fetched.name == "Acme Corp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_organization_row_roundtrips -v --noconftest -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.organization'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/organization.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Organization(Base):
    """Top-level tenant (a company)."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("OrganizationMember", back_populates="organization",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.id}, slug='{self.slug}')>"


class OrganizationMember(Base):
    """M:N membership of a user in an organization, with a role."""
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id",
                                       name="uq_org_member"),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, default="member")  # owner|admin|member
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="members")

    def __repr__(self):
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role={self.role})>"
```

Then add to `backend/app/models/__init__.py` (append, keep existing exports):

```python
from app.models.organization import Organization, OrganizationMember  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_organization_row_roundtrips -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/organization.py backend/app/models/__init__.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add Organization + OrganizationMember models"
```

---

### Task 2: `OrganizationMember` role + uniqueness behavior

**Files:**
- Test: `backend/tests/test_identity_vault_models.py` (add tests)

**Interfaces:**
- Consumes: `Organization`, `OrganizationMember` from Task 1; existing `User`.
- Produces: no new symbols (behavioral coverage only).

- [ ] **Step 1: Write the failing test**

```python
import app.models.organization as org_models
from app.models.user import User


def test_org_member_defaults_to_member_and_is_unique(session):
    user = User(email="john@acme.test", hashed_password="x")  # adjust kwargs to User's actual NOT NULL cols
    org = org_models.Organization(name="Acme", slug="acme2")
    session.add_all([user, org]); session.commit()

    m = org_models.OrganizationMember(organization_id=org.id, user_id=user.id)
    session.add(m); session.commit()
    assert m.role == "member"

    dup = org_models.OrganizationMember(organization_id=org.id, user_id=user.id)
    session.add(dup)
    import pytest, sqlalchemy
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        session.commit()
    session.rollback()
```

- [ ] **Step 2: Run test to verify it fails (or errors on User kwargs)**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_org_member_defaults_to_member_and_is_unique -v --noconftest -p no:cacheprovider`
Expected: FAIL. If it fails on `User(...)` kwargs, open `backend/app/models/user.py`, read the NOT NULL columns, and fix the `User(...)` constructor in the test to supply them. Re-run until the failure is the assertion/IntegrityError path, not a User construction error.

- [ ] **Step 3: Implementation**

No model change needed — the `default="member"` and `UniqueConstraint` from Task 1 satisfy this. If the test revealed a missing default/constraint, add it to `organization.py` now.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_org_member_defaults_to_member_and_is_unique -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_identity_vault_models.py backend/app/models/organization.py
git commit -m "test(data): cover org-member role default + uniqueness"
```

---

### Task 3: Extend `Identity` with org + vault handle

**Files:**
- Modify: `backend/app/models/identity.py`
- Test: `backend/tests/test_identity_vault_models.py` (add test)

**Interfaces:**
- Consumes: existing `Identity` (table `identities`, has `user_id` FK = owner); `Organization`.
- Produces: `Identity.org_id` (FK `organizations.id`, nullable for back-compat), `Identity.vault_collection_ref` (String, nullable). `Identity.user_id` is treated as `owner_user_id` semantically (no rename this phase).

- [ ] **Step 1: Write the failing test**

```python
from app.models.identity import Identity


def test_identity_has_org_and_vault_ref(session):
    org = org_models.Organization(name="Acme", slug="acme3")
    session.add(org); session.commit()
    ident = Identity(name="Alice Smith", user_id=1, org_id=org.id,
                     vault_collection_ref="col_abc123")
    session.add(ident); session.commit()
    got = session.query(Identity).filter_by(vault_collection_ref="col_abc123").one()
    assert got.org_id == org.id
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_identity_has_org_and_vault_ref -v --noconftest -p no:cacheprovider`
Expected: FAIL — `TypeError: 'org_id' is an invalid keyword argument for Identity`

- [ ] **Step 3: Implementation — add two columns to `Identity`**

In `backend/app/models/identity.py`, inside the `Identity` class (after the existing `user_id` column), add:

```python
    # Identity-vault (Phase 1): tenant + handle to the Vaultwarden collection
    # holding this persona's encrypted PII / cards / logins. No secrets here.
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    vault_collection_ref = Column(String(255), nullable=True, index=True)
```

(Ensure `ForeignKey` and `String` are imported at the top of the file; they already import `Column, Integer` — add `String, ForeignKey` if missing.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_identity_has_org_and_vault_ref -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/identity.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add org_id + vault_collection_ref to Identity"
```

---

### Task 4: `IdentityCard` + `ApiCredential` (vault asset metadata)

**Files:**
- Create: `backend/app/models/vault_assets.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_identity_vault_models.py`

**Interfaces:**
- Consumes: `Identity`.
- Produces:
  - `IdentityCard` (table `identity_cards`: `id`, `identity_id` FK, `brand:str`, `last4:str(4)`, `exp_month:int`, `exp_year:int`, `vault_item_ref:str`, `created_at`).
  - `ApiCredential` (table `api_credentials`: `id`, `identity_id` FK, `service:str`, `name:str`, `openbao_path:str`, `created_at`).

- [ ] **Step 1: Write the failing test**

```python
import app.models.vault_assets as va


def test_card_and_api_credential_store_only_handles(session):
    ident = Identity(name="Bob", user_id=1)
    session.add(ident); session.commit()
    card = va.IdentityCard(identity_id=ident.id, brand="visa", last4="4242",
                           exp_month=12, exp_year=2030, vault_item_ref="item_card1")
    tok = va.ApiCredential(identity_id=ident.id, service="github", name="ci-token",
                           openbao_path="kv/identities/1/github/ci-token")
    session.add_all([card, tok]); session.commit()
    assert session.query(va.IdentityCard).one().last4 == "4242"
    assert session.query(va.ApiCredential).one().openbao_path.startswith("kv/")
    # No secret columns exist:
    assert not hasattr(va.IdentityCard, "number")
    assert not hasattr(va.ApiCredential, "token_value")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_card_and_api_credential_store_only_handles -v --noconftest -p no:cacheprovider`
Expected: FAIL — `No module named 'app.models.vault_assets'`

- [ ] **Step 3: Implementation**

```python
# backend/app/models/vault_assets.py
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
```

Append to `backend/app/models/__init__.py`:

```python
from app.models.vault_assets import IdentityCard, ApiCredential  # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_card_and_api_credential_store_only_handles -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/vault_assets.py backend/app/models/__init__.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add IdentityCard + ApiCredential handle models"
```

---

### Task 5: Add `vault_item_ref` to existing `Account` (no rename)

**Files:**
- Modify: `backend/app/models/account.py:66-114` (the `Account` class body)
- Test: `backend/tests/test_identity_vault_models.py`

**Interfaces:**
- Consumes: existing `Account` (table `accounts`).
- Produces: `Account.vault_item_ref` (String(255), nullable) — handle to the Vaultwarden Login item that will hold the actual username/password/TOTP after Phase 6 migration.

- [ ] **Step 1: Write the failing test**

```python
from app.models.account import Account


def test_account_has_vault_item_ref(session):
    ident = Identity(name="Carol", user_id=1)
    session.add(ident); session.commit()
    acct = Account(identity_id=ident.id, website_name="twitter",
                   website_url="https://twitter.com", vault_item_ref="item_login1")
    session.add(acct); session.commit()
    assert session.query(Account).one().vault_item_ref == "item_login1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_account_has_vault_item_ref -v --noconftest -p no:cacheprovider`
Expected: FAIL — `TypeError: 'vault_item_ref' is an invalid keyword argument for Account`

- [ ] **Step 3: Implementation**

In `backend/app/models/account.py`, inside the `Account` class (after `encrypted_credentials`), add:

```python
    # Identity-vault (Phase 1): handle to the Vaultwarden Login item. The
    # encrypted_* columns stay for now; Phase 6 migrates values out and drops them.
    vault_item_ref = Column(String(255), nullable=True, index=True)
```

(`Column` and `String` are already imported in this file.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_account_has_vault_item_ref -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/account.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add vault_item_ref handle to Account (additive)"
```

---

### Task 6: `Agent` + `AgentScope` (MCP machine identities)

**Files:**
- Create: `backend/app/models/agent.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_identity_vault_models.py`

**Interfaces:**
- Consumes: `User`.
- Produces:
  - `Agent` (table `agents`: `id`, `name:str`, `user_id` FK = the user the agent acts for, `token_hash:str`, `is_active:bool`, `created_at`).
  - `AgentScope` (table `agent_scopes`: `id`, `agent_id` FK, `scope_type:str` in {identity,site,secret_type}, `scope_ref:str`).

- [ ] **Step 1: Write the failing test**

```python
import app.models.agent as ag


def test_agent_binds_to_user_and_stores_hashed_token(session):
    agent = ag.Agent(name="signup-bot", user_id=1, token_hash="sha256:deadbeef")
    session.add(agent); session.commit()
    scope = ag.AgentScope(agent_id=agent.id, scope_type="identity", scope_ref="42")
    session.add(scope); session.commit()
    got = session.query(ag.Agent).one()
    assert got.user_id == 1
    assert got.token_hash == "sha256:deadbeef"
    assert not hasattr(ag.Agent, "token")          # never store plaintext token
    assert got.is_active is True
    assert session.query(ag.AgentScope).one().scope_type == "identity"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_agent_binds_to_user_and_stores_hashed_token -v --noconftest -p no:cacheprovider`
Expected: FAIL — `No module named 'app.models.agent'`

- [ ] **Step 3: Implementation**

```python
# backend/app/models/agent.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Agent(Base):
    """An MCP machine identity, bound to the user it acts on behalf of."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)  # hashed, never plaintext
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scopes = relationship("AgentScope", back_populates="agent",
                          cascade="all, delete-orphan")


class AgentScope(Base):
    """One grant: what an agent may reach (an identity, a site, or a secret type)."""
    __tablename__ = "agent_scopes"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False)  # identity|site|secret_type
    scope_ref = Column(String(120), nullable=False)

    agent = relationship("Agent", back_populates="scopes")
```

Append to `backend/app/models/__init__.py`:

```python
from app.models.agent import Agent, AgentScope  # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_agent_binds_to_user_and_stores_hashed_token -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/agent.py backend/app/models/__init__.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add Agent + AgentScope models"
```

---

### Task 7: `ApprovalRequest` + `AuditLog`

**Files:**
- Create: `backend/app/models/approval.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_identity_vault_models.py`

**Interfaces:**
- Consumes: `Agent`.
- Produces:
  - `ApprovalRequest` (table `approval_requests`: `id`, `agent_id` FK, `resource_ref:str`, `status:str` default "pending" in {pending,approved,denied,expired}, `requested_at`, `decided_by:int nullable`, `decided_at:datetime nullable`, `expires_at:datetime`).
  - `AuditLog` (table `audit_log`: `id`, `agent_id:int nullable`, `on_behalf_user_id:int nullable`, `identity_id:int nullable`, `resource_ref:str`, `decision:str`, `created_at`). No secret values ever stored.

- [ ] **Step 1: Write the failing test**

```python
import app.models.approval as ap


def test_approval_defaults_pending_and_audit_has_no_secret_column(session):
    req = ap.ApprovalRequest(agent_id=1, resource_ref="identity:42:card:7")
    session.add(req); session.commit()
    assert req.status == "pending"

    entry = ap.AuditLog(agent_id=1, on_behalf_user_id=1, identity_id=42,
                        resource_ref="identity:42:login:twitter", decision="auto_release")
    session.add(entry); session.commit()
    assert session.query(ap.AuditLog).one().decision == "auto_release"
    assert not hasattr(ap.AuditLog, "secret_value")  # audit never holds the value
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_approval_defaults_pending_and_audit_has_no_secret_column -v --noconftest -p no:cacheprovider`
Expected: FAIL — `No module named 'app.models.approval'`

- [ ] **Step 3: Implementation**

```python
# backend/app/models/approval.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ApprovalRequest(Base):
    """A pending human approval for a sensitive secret release."""
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    resource_ref = Column(String(300), nullable=False)  # e.g. identity:42:card:7
    status = Column(String(20), nullable=False, default="pending")  # pending|approved|denied|expired
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent")


class AuditLog(Base):
    """Append-only record of every access decision. Never stores the secret value."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=True, index=True)
    on_behalf_user_id = Column(Integer, nullable=True, index=True)
    identity_id = Column(Integer, nullable=True, index=True)
    resource_ref = Column(String(300), nullable=False)
    decision = Column(String(40), nullable=False)  # auto_release|approved|denied|scope_denied
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
```

Append to `backend/app/models/__init__.py`:

```python
from app.models.approval import ApprovalRequest, AuditLog  # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py::test_approval_defaults_pending_and_audit_has_no_secret_column -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/approval.py backend/app/models/__init__.py backend/tests/test_identity_vault_models.py
git commit -m "feat(data): add ApprovalRequest + AuditLog models"
```

---

### Task 8: Alembic migration for all Phase-1 schema

**Files:**
- Create: `backend/alembic/versions/e4a1f0b21c01_identity_vault_phase1.py`
- Test: `backend/tests/test_identity_vault_migration.py`

**Interfaces:**
- Consumes: all models from Tasks 1–7.
- Produces: a migration revision `e4a1f0b21c01` that creates the 8 new tables and adds the 3 new columns (`identities.org_id`, `identities.vault_collection_ref`, `accounts.vault_item_ref`).

- [ ] **Step 1: Determine the current head revision**

Run: `cd backend && python -m alembic heads`
Note the printed revision id; use it as `down_revision` below (replace `<DOWN_REVISION>`).

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_identity_vault_migration.py
import importlib


def test_phase1_migration_module_imports_and_has_ops():
    m = importlib.import_module(
        "alembic.versions.e4a1f0b21c01_identity_vault_phase1")
    assert m.revision == "e4a1f0b21c01"
    assert callable(m.upgrade) and callable(m.downgrade)
    src = open(m.__file__).read()
    for table in ["organizations", "organization_members", "identity_cards",
                  "api_credentials", "agents", "agent_scopes",
                  "approval_requests", "audit_log"]:
        assert f'create_table(\n        "{table}"' in src or f"create_table('{table}'" in src or f'create_table("{table}"' in src
    assert 'add_column("identities"' in src or "add_column('identities'" in src
    assert 'add_column("accounts"' in src or "add_column('accounts'" in src
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_identity_vault_migration.py -v --noconftest -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError` for the migration module.

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/e4a1f0b21c01_identity_vault_phase1.py
"""identity vault phase 1: tenancy, agents, approvals, audit, vault handles"""
from alembic import op
import sqlalchemy as sa

revision = "e4a1f0b21c01"
down_revision = "<DOWN_REVISION>"  # from Step 1
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )
    op.create_table(
        "identity_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_id", sa.Integer(), sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("brand", sa.String(length=40)),
        sa.Column("last4", sa.String(length=4)),
        sa.Column("exp_month", sa.Integer()),
        sa.Column("exp_year", sa.Integer()),
        sa.Column("vault_item_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_id", sa.Integer(), sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("service", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("openbao_path", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "agent_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.String(length=120), nullable=False),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("resource_ref", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("on_behalf_user_id", sa.Integer(), nullable=True),
        sa.Column("identity_id", sa.Integer(), nullable=True),
        sa.Column("resource_ref", sa.String(length=300), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("identities", sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True))
    op.add_column("identities", sa.Column("vault_collection_ref", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("vault_item_ref", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("accounts", "vault_item_ref")
    op.drop_column("identities", "vault_collection_ref")
    op.drop_column("identities", "org_id")
    for table in ["audit_log", "approval_requests", "agent_scopes", "agents",
                  "api_credentials", "identity_cards", "organization_members", "organizations"]:
        op.drop_table(table)
```

- [ ] **Step 5: Run the migration-module test**

Run: `cd backend && python -m pytest tests/test_identity_vault_migration.py -v --noconftest -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Apply the migration against a scratch SQLite/Postgres URL to confirm it runs**

Run: `cd backend && DATABASE_URL_ASYNC="sqlite+aiosqlite:///./_scratch_phase1.db" python -m alembic upgrade head && python -m alembic downgrade -1`
Expected: `upgrade` then `downgrade` complete without error. Delete the scratch DB: `rm -f backend/_scratch_phase1.db`.
(If the project's `alembic/env.py` requires the sync `DATABASE_URL`, set that variable instead — check `backend/alembic.ini`/`env.py` for the variable it reads.)

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/e4a1f0b21c01_identity_vault_phase1.py backend/tests/test_identity_vault_migration.py
git commit -m "feat(data): Alembic migration for identity-vault phase 1 schema"
```

---

### Task 9: Full-suite green check + PR

**Files:** none (verification + delivery)

- [ ] **Step 1: Run the whole new test module**

Run: `cd backend && python -m pytest tests/test_identity_vault_models.py tests/test_identity_vault_migration.py -v --noconftest -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 2: Confirm the existing security regression tests still pass (no model regressions)**

Run: `cd backend && python -m pytest tests/test_security_regressions.py --noconftest -p no:cacheprovider -q`
Expected: 18 passed.

- [ ] **Step 3: Open a PR into `master`**

```bash
git push -u origin feat/identity-vault-phase1-data-tier
gh pr create --base master --head feat/identity-vault-phase1-data-tier \
  --title "Identity vault Phase 1: data-tier foundation" \
  --body "Additive schema for the identity-vault subsystem (tenancy/agents/approvals/audit + vault handles). No renames, no secret-column removal. Implements docs/superpowers/plans/2026-06-24-identity-vault-phase1-data-tier.md."
```

---

## Self-Review

**Spec coverage (spec §5 data model):** organizations ✔(T1) · organization_members ✔(T1) · identities + handle ✔(T3) · site_logins handle (additive on `accounts`) ✔(T5; rename deferred to Phase 6 per §8) · identity_cards ✔(T4) · api_credentials ✔(T4) · agents ✔(T6) · agent_scopes ✔(T6) · approval_requests ✔(T7) · audit_log ✔(T7) · migration ✔(T8). "No secrets in Postgres" enforced by tests asserting absent secret columns (T4, T7).

**Placeholder scan:** the only intentional fill-ins are `<DOWN_REVISION>` (resolved in T8 Step 1) and the `User(...)` constructor kwargs (resolved in T2 Step 2 by reading `app/models/user.py`) — both have explicit resolution steps. No "TODO/handle edge cases" placeholders.

**Type consistency:** handle columns named consistently — `vault_collection_ref` (Identity), `vault_item_ref` (IdentityCard, Account), `openbao_path` (ApiCredential), `token_hash` (Agent). `resource_ref`/`decision`/`status` strings match across ApprovalRequest and AuditLog and the broker contract to be frozen in Phase 2.

**Scope:** This plan is self-contained and produces a tested, reversible schema migration with no behavior change to existing endpoints — safe to merge ahead of the broker work.
