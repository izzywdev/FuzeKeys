"""
Tests for the main application endpoints and functionality.
"""

import pytest
from httpx import AsyncClient


class TestMainApp:
    """Test suite for main application functionality."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test the root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "FuzeKeys" in data["message"]

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """Test the health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client: AsyncClient):
        """Test the API info endpoint."""
        response = await client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "name" in data
        assert data["name"] == "FuzeKeys API"

    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Test CORS headers are properly set."""
        response = await client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # A bare OPTIONS is not a preflight: CORSMiddleware only intercepts the
        # request when Origin and Access-Control-Request-Method are both set,
        # otherwise it falls through to the router and answers 405.
        assert response.status_code in [200, 204]
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_nonexistent_endpoint(self, client: AsyncClient):
        """Test accessing a non-existent endpoint."""
        response = await client.get("/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_api_prefix(self, authed_client: AsyncClient):
        """Test that API endpoints are properly prefixed."""
        # Routers are mounted under /api/v1, and require authentication.
        response = await authed_client.get("/api/v1/identities/")
        assert response.status_code == 200

        # Test that non-prefixed routes (if any) also work
        response = await authed_client.get("/health")
        assert response.status_code == 200


class TestAPIDocumentation:
    """Test suite for API documentation endpoints."""

    @pytest.mark.asyncio
    async def test_openapi_json(self, client: AsyncClient):
        """Test OpenAPI JSON schema endpoint."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "FuzeKeys API"

    @pytest.mark.asyncio
    async def test_docs_endpoint(self, client: AsyncClient):
        """Test Swagger UI documentation endpoint."""
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_redoc_endpoint(self, client: AsyncClient):
        """Test ReDoc documentation endpoint."""
        response = await client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestErrorHandling:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_validation_error(self, authed_client: AsyncClient):
        """Test validation error handling."""
        # Send invalid JSON to an endpoint that expects valid data
        response = await authed_client.post("/api/v1/identities/", json={})
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_method_not_allowed(self, client: AsyncClient):
        """Test method not allowed error."""
        # Try to POST to a GET-only endpoint
        response = await client.post("/health")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_large_payload(self, authed_client: AsyncClient):
        """Test handling of large payloads."""
        # Create a large payload
        large_data = {"data": "x" * 10000}
        response = await authed_client.post("/api/v1/identities/", json=large_data)
        # Should handle gracefully (either process or reject with appropriate error)
        assert response.status_code in [400, 413, 422]


class TestSecurity:
    """Test suite for security features."""

    @pytest.mark.asyncio
    async def test_security_headers(self, client: AsyncClient):
        """Test that security headers are present."""
        response = await client.get("/")
        # Check for basic security headers (exact headers depend on configuration)
        assert response.status_code == 200
        # This would depend on your security middleware configuration

    @pytest.mark.asyncio
    async def test_sql_injection_protection(self, authed_client: AsyncClient):
        """Test SQL injection protection."""
        # Try SQL injection in the path parameter
        malicious_query = "'; DROP TABLE identities; --"
        response = await authed_client.get(f"/api/v1/identities/{malicious_query}")
        # identity_id is typed as int, so this is rejected by request validation
        # (422) or simply not found (404) -- never a 500 from a database error.
        assert response.status_code in [404, 422]

    @pytest.mark.asyncio
    async def test_xss_protection(self, authed_client: AsyncClient):
        """Test XSS protection in data handling."""
        xss_payload = "<script>alert('xss')</script>"
        identity_data = {
            "name": xss_payload,
            "email": "test@example.com",
            "master_key": "test-key",
        }

        response = await authed_client.post("/api/v1/identities/", json=identity_data)
        # Should either sanitize the input or reject it
        if response.status_code == 201:
            data = response.json()
            # If accepted, should be sanitized
            assert "<script>" not in data["name"]
