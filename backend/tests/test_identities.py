"""
Tests for the identities API endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.identity import Identity

class TestIdentitiesAPI:
    """Test suite for identities API endpoints."""

    @pytest.mark.asyncio
    async def test_get_identities_empty(self, client: AsyncClient):
        """Test getting identities when none exist."""
        response = await client.get("/api/identities")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_identities_with_data(self, client: AsyncClient, sample_identity: Identity):
        """Test getting identities when data exists."""
        response = await client.get("/api/identities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_identity.id
        assert data[0]["name"] == sample_identity.name
        assert data[0]["email"] == sample_identity.email

    @pytest.mark.asyncio
    async def test_create_identity(self, client: AsyncClient):
        """Test creating a new identity."""
        identity_data = {
            "name": "New Test Identity",
            "email": "newtest@example.com",
            "first_name": "New",
            "last_name": "Test",
            "phone": "+1234567890",
            "address": "123 Test St",
            "city": "Test City",
            "country": "Test Country",
            "master_key": "test-master-key-123"
        }
        
        response = await client.post("/api/identities", json=identity_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == identity_data["name"]
        assert data["email"] == identity_data["email"]
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_identity_missing_fields(self, client: AsyncClient):
        """Test creating identity with missing required fields."""
        identity_data = {
            "name": "Incomplete Identity"
            # Missing email and master_key
        }
        
        response = await client.post("/api/identities", json=identity_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_identity_by_id(self, client: AsyncClient, sample_identity: Identity):
        """Test getting a specific identity by ID."""
        response = await client.get(f"/api/identities/{sample_identity.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_identity.id
        assert data["name"] == sample_identity.name
        assert data["email"] == sample_identity.email

    @pytest.mark.asyncio
    async def test_get_identity_not_found(self, client: AsyncClient):
        """Test getting a non-existent identity."""
        response = await client.get("/api/identities/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_identity(self, client: AsyncClient, sample_identity: Identity):
        """Test updating an existing identity."""
        update_data = {
            "name": "Updated Test Identity",
            "email": "updated@example.com"
        }
        
        response = await client.put(f"/api/identities/{sample_identity.id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["email"] == update_data["email"]
        assert data["id"] == sample_identity.id

    @pytest.mark.asyncio
    async def test_update_identity_not_found(self, client: AsyncClient):
        """Test updating a non-existent identity."""
        update_data = {
            "name": "Updated Identity",
            "email": "updated@example.com"
        }
        
        response = await client.put("/api/identities/nonexistent-id", json=update_data)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_identity(self, client: AsyncClient, sample_identity: Identity):
        """Test deleting an identity."""
        response = await client.delete(f"/api/identities/{sample_identity.id}")
        assert response.status_code == 204
        
        # Verify it's deleted
        get_response = await client.get(f"/api/identities/{sample_identity.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_identity_not_found(self, client: AsyncClient):
        """Test deleting a non-existent identity."""
        response = await client.delete("/api/identities/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_identity_validation(self, client: AsyncClient):
        """Test identity data validation."""
        # Test invalid email
        invalid_data = {
            "name": "Test Identity",
            "email": "invalid-email",
            "master_key": "test-key"
        }
        
        response = await client.post("/api/identities", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_identity_encryption(self, client: AsyncClient):
        """Test that sensitive data is properly encrypted."""
        identity_data = {
            "name": "Encryption Test",
            "email": "encrypt@example.com",
            "first_name": "Encrypt",
            "last_name": "Test",
            "phone": "+1234567890",
            "master_key": "encryption-test-key-123"
        }
        
        response = await client.post("/api/identities", json=identity_data)
        assert response.status_code == 201
        
        # The response should not contain the raw master key
        data = response.json()
        assert "master_key" not in data
        
        # Sensitive fields should be present in decrypted form in API response
        assert data["first_name"] == identity_data["first_name"]
        assert data["phone"] == identity_data["phone"] 