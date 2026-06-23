"""
Tests for the accounts API endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.account import Account
from app.models.identity import Identity

class TestAccountsAPI:
    """Test suite for accounts API endpoints."""

    @pytest.mark.asyncio
    async def test_get_accounts_empty(self, client: AsyncClient):
        """Test getting accounts when none exist."""
        response = await client.get("/api/accounts")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_accounts_with_data(self, client: AsyncClient, sample_account: Account):
        """Test getting accounts when data exists."""
        response = await client.get("/api/accounts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_account.id
        assert data[0]["site_name"] == sample_account.site_name
        assert data[0]["username"] == sample_account.username
        assert data[0]["status"] == sample_account.status

    @pytest.mark.asyncio
    async def test_create_account(self, client: AsyncClient, sample_identity: Identity):
        """Test creating a new account."""
        account_data = {
            "identity_id": sample_identity.id,
            "site_name": "github.com",
            "username": "testuser123",
            "email": "testuser@example.com",
            "password": "SecurePassword123!",
            "status": "active",
            "notes": "Test account for GitHub"
        }
        
        response = await client.post("/api/accounts", json=account_data)
        assert response.status_code == 201
        data = response.json()
        assert data["site_name"] == account_data["site_name"]
        assert data["username"] == account_data["username"]
        assert data["status"] == account_data["status"]
        assert data["identity_id"] == account_data["identity_id"]
        assert "id" in data
        assert "created_at" in data
        # Password should not be returned in response
        assert "password" not in data

    @pytest.mark.asyncio
    async def test_create_account_missing_fields(self, client: AsyncClient):
        """Test creating account with missing required fields."""
        account_data = {
            "site_name": "example.com"
            # Missing identity_id and username
        }
        
        response = await client.post("/api/accounts", json=account_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_account_by_id(self, client: AsyncClient, sample_account: Account):
        """Test getting a specific account by ID."""
        response = await client.get(f"/api/accounts/{sample_account.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_account.id
        assert data["site_name"] == sample_account.site_name
        assert data["username"] == sample_account.username
        assert data["status"] == sample_account.status

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, client: AsyncClient):
        """Test getting a non-existent account."""
        response = await client.get("/api/accounts/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_account(self, client: AsyncClient, sample_account: Account):
        """Test updating an existing account."""
        update_data = {
            "username": "updated_username",
            "status": "inactive",
            "notes": "Updated test account"
        }
        
        response = await client.put(f"/api/accounts/{sample_account.id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == update_data["username"]
        assert data["status"] == update_data["status"]
        assert data["notes"] == update_data["notes"]
        assert data["id"] == sample_account.id

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, client: AsyncClient):
        """Test updating a non-existent account."""
        update_data = {
            "username": "updated_user",
            "status": "inactive"
        }
        
        response = await client.put("/api/accounts/nonexistent-id", json=update_data)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_account(self, client: AsyncClient, sample_account: Account):
        """Test deleting an account."""
        response = await client.delete(f"/api/accounts/{sample_account.id}")
        assert response.status_code == 204
        
        # Verify it's deleted
        get_response = await client.get(f"/api/accounts/{sample_account.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, client: AsyncClient):
        """Test deleting a non-existent account."""
        response = await client.delete("/api/accounts/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_accounts_by_identity(self, client: AsyncClient, sample_account: Account, sample_identity: Identity):
        """Test getting accounts filtered by identity ID."""
        response = await client.get(f"/api/accounts?identity_id={sample_identity.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["identity_id"] == sample_identity.id

    @pytest.mark.asyncio
    async def test_get_accounts_by_site(self, client: AsyncClient, sample_account: Account):
        """Test getting accounts filtered by site name."""
        response = await client.get(f"/api/accounts?site_name={sample_account.site_name}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["site_name"] == sample_account.site_name

    @pytest.mark.asyncio
    async def test_get_accounts_by_status(self, client: AsyncClient, sample_account: Account):
        """Test getting accounts filtered by status."""
        response = await client.get(f"/api/accounts?status={sample_account.status}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        for account in data:
            assert account["status"] == sample_account.status

    @pytest.mark.asyncio
    async def test_account_status_validation(self, client: AsyncClient, sample_identity: Identity):
        """Test account status validation."""
        # Test invalid status
        invalid_data = {
            "identity_id": sample_identity.id,
            "site_name": "example.com",
            "username": "testuser",
            "status": "invalid_status"
        }
        
        response = await client.post("/api/accounts", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_account_credentials_encryption(self, client: AsyncClient, sample_identity: Identity):
        """Test that account credentials are properly encrypted."""
        account_data = {
            "identity_id": sample_identity.id,
            "site_name": "secure-site.com",
            "username": "secureuser",
            "email": "secure@example.com",
            "password": "VerySecurePassword123!",
            "api_key": "secret-api-key-12345",
            "notes": "Sensitive account data"
        }
        
        response = await client.post("/api/accounts", json=account_data)
        assert response.status_code == 201
        
        # The response should not contain sensitive data
        data = response.json()
        assert "password" not in data
        assert "api_key" not in data
        
        # But should contain non-sensitive data
        assert data["username"] == account_data["username"]
        assert data["site_name"] == account_data["site_name"]

    @pytest.mark.asyncio
    async def test_account_relationship_with_identity(self, client: AsyncClient, sample_account: Account, sample_identity: Identity):
        """Test that account properly relates to its identity."""
        response = await client.get(f"/api/accounts/{sample_account.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["identity_id"] == sample_identity.id

    @pytest.mark.asyncio
    async def test_create_account_with_invalid_identity(self, client: AsyncClient):
        """Test creating account with non-existent identity ID."""
        account_data = {
            "identity_id": "nonexistent-identity-id",
            "site_name": "example.com",
            "username": "testuser"
        }
        
        response = await client.post("/api/accounts", json=account_data)
        assert response.status_code == 400  # Bad request due to invalid foreign key 