"""
Tests for site integrations functionality.

This module tests the site integration system including:
- Site discovery and capabilities
- Permit.io integration (signup, signin, API key creation)
- REST API endpoints
- Error handling and validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app
from app.integrations.site import get_available_sites, get_site_capabilities
from app.integrations.site.permit_io.models import (
    PermitIOCredentials, 
    PermitIOResult, 
    PermitIOApiKey,
    PermitIOSessionInfo
)
from app.integrations.site.permit_io import PermitIOIntegration
from app.integrations.site.permit_io.config import PermitIOConfig

client = TestClient(app)

# Test data
@pytest.fixture
def sample_credentials():
    """Sample credentials for testing."""
    return PermitIOCredentials(
        email="test@example.com",
        password="TestPassword123!",
        first_name="Test",
        last_name="User",
        company_name="Test Company",
        phone="+1234567890"
    )

@pytest.fixture
def sample_success_result():
    """Sample successful result for testing."""
    return PermitIOResult(
        success=True,
        message="Operation completed successfully",
        data={"test_key": "test_value"},
        timestamp=datetime.utcnow()
    )

@pytest.fixture
def sample_error_result():
    """Sample error result for testing."""
    return PermitIOResult(
        success=False,
        message="Operation failed",
        error="Test error message",
        timestamp=datetime.utcnow()
    )

@pytest.fixture
def sample_api_key():
    """Sample API key for testing."""
    return PermitIOApiKey(
        key_id="test_key_123",
        name="Test Key",
        key_value="permit_test_key_123456789",
        is_active=True
    )

@pytest.fixture
def sample_session_info():
    """Sample session info for testing."""
    return PermitIOSessionInfo(
        session_id="test_session_123",
        user_id="test_user_456",
        workspace_id="test_workspace_789",
        cookies={"session": "test_session_value"}
    )

class TestSiteDiscovery:
    """Test site discovery functionality."""
    
    def test_get_available_sites(self):
        """Test getting list of available sites."""
        sites = get_available_sites()
        assert isinstance(sites, list)
        assert "permit_io" in sites
    
    def test_get_site_capabilities(self):
        """Test getting site capabilities."""
        capabilities = get_site_capabilities("permit_io")
        assert isinstance(capabilities, dict)
        assert "signup" in capabilities
        assert "signin" in capabilities
        assert "apikey" in capabilities
        assert capabilities["signup"] is True
        assert capabilities["signin"] is True
        assert capabilities["apikey"] is True
    
    def test_get_site_capabilities_unknown_site(self):
        """Test getting capabilities for unknown site."""
        capabilities = get_site_capabilities("unknown_site")
        assert isinstance(capabilities, dict)
        assert capabilities["signup"] is False
        assert capabilities["signin"] is False
        assert capabilities["apikey"] is False

class TestPermitIOModels:
    """Test Permit.io data models."""
    
    def test_permit_io_credentials(self, sample_credentials):
        """Test PermitIOCredentials model."""
        assert sample_credentials.email == "test@example.com"
        assert sample_credentials.password == "TestPassword123!"
        assert sample_credentials.first_name == "Test"
        assert sample_credentials.last_name == "User"
        assert sample_credentials.company_name == "Test Company"
        assert sample_credentials.phone == "+1234567890"
    
    def test_permit_io_result(self, sample_success_result):
        """Test PermitIOResult model."""
        assert sample_success_result.success is True
        assert sample_success_result.message == "Operation completed successfully"
        assert sample_success_result.data == {"test_key": "test_value"}
        assert sample_success_result.error is None
        assert isinstance(sample_success_result.timestamp, datetime)
    
    def test_permit_io_api_key(self, sample_api_key):
        """Test PermitIOApiKey model."""
        assert sample_api_key.key_id == "test_key_123"
        assert sample_api_key.name == "Test Key"
        assert sample_api_key.key_value == "permit_test_key_123456789"
        assert sample_api_key.is_active is True
    
    def test_permit_io_session_info(self, sample_session_info):
        """Test PermitIOSessionInfo model."""
        assert sample_session_info.session_id == "test_session_123"
        assert sample_session_info.user_id == "test_user_456"
        assert sample_session_info.workspace_id == "test_workspace_789"
        assert sample_session_info.cookies == {"session": "test_session_value"}

class TestPermitIOConfig:
    """Test Permit.io configuration."""
    
    def test_config_urls(self):
        """Test configuration URLs."""
        config = PermitIOConfig()
        assert config.BASE_URL == "https://app.permit.io"
        assert config.SIGNUP_URL == "https://app.permit.io/signup"
        assert config.SIGNIN_URL == "https://app.permit.io/signin"
        assert config.DASHBOARD_URL == "https://app.permit.io/dashboard"
        assert config.API_KEYS_URL == "https://app.permit.io/settings/api-keys"
    
    def test_config_timeouts(self):
        """Test configuration timeouts."""
        config = PermitIOConfig()
        assert config.DEFAULT_TIMEOUT == 30000
        assert config.NAVIGATION_TIMEOUT == 60000
        assert config.ELEMENT_TIMEOUT == 10000
        
        assert config.get_timeout('default') == 30000
        assert config.get_timeout('navigation') == 60000
        assert config.get_timeout('element') == 10000
        assert config.get_timeout('unknown') == 30000
    
    def test_config_selectors(self):
        """Test configuration selectors."""
        config = PermitIOConfig()
        email_selectors = config.get_selectors('email')
        assert isinstance(email_selectors, list)
        assert len(email_selectors) > 0
        assert 'input[type="email"]' in email_selectors
        
        password_selectors = config.get_selectors('password')
        assert isinstance(password_selectors, list)
        assert 'input[type="password"]' in password_selectors

class TestPermitIOIntegration:
    """Test Permit.io integration class."""
    
    @pytest.mark.asyncio
    async def test_integration_init(self):
        """Test integration initialization."""
        integration = PermitIOIntegration(headless=True)
        assert integration.headless is True
        assert isinstance(integration.config, PermitIOConfig)
    
    @pytest.mark.asyncio
    @patch('app.integrations.site.permit_io.signup.create_account')
    async def test_signup_account(self, mock_signup, sample_credentials, sample_success_result):
        """Test signup account functionality."""
        mock_signup.return_value = sample_success_result
        
        integration = PermitIOIntegration(headless=True)
        result = await integration.signup_account(sample_credentials)
        
        assert result.success is True
        assert result.message == "Operation completed successfully"
        mock_signup.assert_called_once_with(sample_credentials, headless=True)
    
    @pytest.mark.asyncio
    @patch('app.integrations.site.permit_io.signin.authenticate')
    async def test_signin_account(self, mock_signin, sample_success_result):
        """Test signin account functionality."""
        mock_signin.return_value = sample_success_result
        
        integration = PermitIOIntegration(headless=True)
        result = await integration.signin_account("test@example.com", "password")
        
        assert result.success is True
        mock_signin.assert_called_once_with("test@example.com", "password", headless=True)
    
    @pytest.mark.asyncio
    @patch('app.integrations.site.permit_io.apikey.create_key')
    async def test_create_api_key(self, mock_apikey, sample_success_result):
        """Test API key creation functionality."""
        mock_apikey.return_value = sample_success_result
        
        integration = PermitIOIntegration(headless=True)
        result = await integration.create_api_key("test@example.com", "password", "TestKey")
        
        assert result.success is True
        mock_apikey.assert_called_once_with("test@example.com", "password", "TestKey", headless=True)

class TestSiteIntegrationsAPI:
    """Test site integrations REST API endpoints."""
    
    def test_list_available_sites(self):
        """Test listing available sites endpoint."""
        response = client.get("/api/v1/integrations/sites")
        assert response.status_code == 200
        
        data = response.json()
        assert "sites" in data
        assert "count" in data
        assert isinstance(data["sites"], list)
        assert "permit_io" in data["sites"]
    
    def test_get_site_capabilities(self):
        """Test getting site capabilities endpoint."""
        response = client.get("/api/v1/integrations/sites/permit.io/capabilities")
        assert response.status_code == 200
        
        data = response.json()
        assert "site" in data
        assert "capabilities" in data
        assert data["site"] == "permit.io"
        assert data["capabilities"]["signup"] is True
        assert data["capabilities"]["signin"] is True
        assert data["capabilities"]["apikey"] is True
    
    def test_get_unknown_site_capabilities(self):
        """Test getting capabilities for unknown site."""
        response = client.get("/api/v1/integrations/sites/unknown/capabilities")
        assert response.status_code == 404
    
    @patch('app.routers.site_integrations.handle_permit_io_signup')
    def test_signup_endpoint(self, mock_handler):
        """Test signup endpoint."""
        mock_handler.return_value = {
            "success": True,
            "message": "Account created successfully",
            "site": "permit.io"
        }
        
        signup_data = {
            "site": "permit.io",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "first_name": "Test",
            "last_name": "User"
        }
        
        response = client.post("/api/v1/integrations/signup", json=signup_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["site"] == "permit.io"
    
    def test_health_check(self):
        """Test integrations health check endpoint."""
        response = client.get("/api/v1/integrations/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "available_sites" in data
        assert "timestamp" in data
        assert data["status"] == "healthy"

class TestErrorHandling:
    """Test error handling in site integrations."""
    
    def test_invalid_email(self):
        """Test signup with invalid email."""
        signup_data = {
            "site": "permit.io",
            "email": "invalid-email",
            "password": "TestPassword123!",
            "first_name": "Test",
            "last_name": "User"
        }
        
        response = client.post("/api/v1/integrations/signup", json=signup_data)
        assert response.status_code == 422  # Validation error
    
    def test_missing_required_fields(self):
        """Test signup with missing required fields."""
        signup_data = {
            "site": "permit.io",
            "email": "test@example.com"
            # Missing password, first_name, last_name
        }
        
        response = client.post("/api/v1/integrations/signup", json=signup_data)
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    @patch('app.integrations.site.permit_io.signup.create_account')
    async def test_signup_exception_handling(self, mock_signup, sample_credentials):
        """Test exception handling in signup."""
        mock_signup.side_effect = Exception("Test exception")
        
        integration = PermitIOIntegration(headless=True)
        result = await integration.signup_account(sample_credentials)
        
        # Should not raise exception, should return error result
        assert result.success is False
        assert "Test exception" in str(result.error)

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 