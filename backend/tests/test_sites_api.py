"""
Tests for Sites API endpoints.

This module tests all the sites-related API endpoints including:
- List sites with pagination and filtering
- Get site by ID and name
- Create, update, and delete sites
- Import sites from CSV
- Get statistics and categories
"""

import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from app.main import app
from app.database import get_db
from app.models.site import Site, DifficultyLevel, ImplementationStatus

client = TestClient(app)

# Test data
SAMPLE_SITE_DATA = {
    "name": "test_site",
    "display_name": "Test Site",
    "url": "https://test.com",
    "category": "test",
    "description": "A test site for automation",
    "signup_difficulty": "medium",
    "signin_difficulty": "easy",
    "apikey_difficulty": "hard",
    "priority": 75,
    "estimated_hours": 10,
    "has_official_api": True,
    "requires_email_verification": True,
    "requires_phone_verification": False,
    "has_captcha": True,
    "captcha_type": "recaptcha",
    "anti_bot_techniques": ["fingerprinting", "behavioral_analysis"],
    "notes": "Test site for API testing"
}

SAMPLE_SITE_UPDATE = {
    "display_name": "Updated Test Site",
    "description": "Updated description",
    "signup_status": "completed",
    "priority": 85
}

class TestSitesAPI:
    """Test sites REST API endpoints."""

    def setup_method(self):
        """Set up test data before each test."""
        # Mock database session
        self.mock_db = MagicMock(spec=Session)
        
        # Mock site object
        self.mock_site = MagicMock(spec=Site)
        self.mock_site.id = 1
        self.mock_site.name = "test_site"
        self.mock_site.display_name = "Test Site"
        self.mock_site.url = "https://test.com"
        self.mock_site.category = "test"
        self.mock_site.description = "A test site"
        self.mock_site.signup_difficulty = DifficultyLevel.MEDIUM
        self.mock_site.signin_difficulty = DifficultyLevel.EASY
        self.mock_site.apikey_difficulty = DifficultyLevel.HARD
        self.mock_site.priority = 75
        self.mock_site.estimated_hours = 10
        self.mock_site.has_official_api = True
        self.mock_site.signup_status = ImplementationStatus.NOT_STARTED
        self.mock_site.signin_status = ImplementationStatus.NOT_STARTED
        self.mock_site.apikey_status = ImplementationStatus.NOT_STARTED
        self.mock_site.implementation_progress = 0.0
        self.mock_site.created_at = "2024-01-01T00:00:00"
        self.mock_site.updated_at = "2024-01-01T00:00:00"
        
        # Mock to_dict method
        self.mock_site.to_dict.return_value = {
            "id": 1,
            "name": "test_site",
            "display_name": "Test Site",
            "url": "https://test.com",
            "logo_url": None,
            "category": "test",
            "description": "A test site",
            "signup_difficulty": "medium",
            "signin_difficulty": "easy",
            "apikey_difficulty": "hard",
            "overall_difficulty": "medium",
            "requires_email_verification": True,
            "requires_phone_verification": False,
            "requires_sms_verification": False,
            "requires_authenticator": False,
            "has_captcha": True,
            "captcha_type": "recaptcha",
            "anti_bot_techniques": ["fingerprinting"],
            "signup_status": "not_started",
            "signin_status": "not_started",
            "apikey_status": "not_started",
            "implementation_progress": 0.0,
            "priority": 75,
            "estimated_hours": 10,
            "has_official_api": True,
            "api_documentation_url": None,
            "api_rate_limits": None,
            "notes": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }

    @patch('app.routers.sites.get_db')
    def test_list_sites_success(self, mock_get_db):
        """Test successful listing of sites with pagination."""
        mock_get_db.return_value = self.mock_db
        
        # Mock query chain
        mock_query = MagicMock()
        mock_query.offset.return_value.limit.return_value.all.return_value = [self.mock_site]
        self.mock_db.query.return_value = mock_query
        
        response = client.get("/api/v1/sites/?skip=0&limit=20")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test_site"
        assert data[0]["display_name"] == "Test Site"

    @patch('app.routers.sites.get_db')
    def test_list_sites_with_filters(self, mock_get_db):
        """Test listing sites with various filters."""
        mock_get_db.return_value = self.mock_db
        
        # Mock query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value.limit.return_value.all.return_value = [self.mock_site]
        self.mock_db.query.return_value = mock_query
        
        response = client.get(
            "/api/v1/sites/?category=test&difficulty=medium&search=test&priority_min=70&sort_by=priority&sort_order=desc"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @patch('app.routers.sites.get_db')
    def test_list_sites_pagination(self, mock_get_db):
        """Test pagination parameters."""
        mock_get_db.return_value = self.mock_db
        
        # Mock query chain
        mock_query = MagicMock()
        mock_query.offset.return_value.limit.return_value.all.return_value = []
        self.mock_db.query.return_value = mock_query
        
        response = client.get("/api/v1/sites/?skip=20&limit=10")
        
        assert response.status_code == 200
        # Verify offset and limit were called with correct values
        mock_query.offset.assert_called_with(20)
        mock_query.offset.return_value.limit.assert_called_with(10)

    @patch('app.routers.sites.get_db')
    def test_get_site_by_id_success(self, mock_get_db):
        """Test successful retrieval of site by ID."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_site
        
        response = client.get("/api/v1/sites/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "test_site"

    @patch('app.routers.sites.get_db')
    def test_get_site_by_id_not_found(self, mock_get_db):
        """Test retrieval of non-existent site by ID."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.get("/api/v1/sites/999")
        
        assert response.status_code == 404
        assert "Site not found" in response.json()["detail"]

    @patch('app.routers.sites.get_db')
    def test_get_site_by_name_success(self, mock_get_db):
        """Test successful retrieval of site by name."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_site
        
        response = client.get("/api/v1/sites/name/test_site")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_site"

    @patch('app.routers.sites.get_db')
    def test_get_site_by_name_not_found(self, mock_get_db):
        """Test retrieval of non-existent site by name."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.get("/api/v1/sites/name/nonexistent")
        
        assert response.status_code == 404
        assert "Site not found" in response.json()["detail"]

    @patch('app.routers.sites.get_db')
    def test_create_site_success(self, mock_get_db):
        """Test successful site creation."""
        mock_get_db.return_value = self.mock_db
        
        # Mock that site doesn't exist
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Mock successful creation
        self.mock_db.add = MagicMock()
        self.mock_db.commit = MagicMock()
        self.mock_db.refresh = MagicMock()
        
        response = client.post("/api/v1/sites/", json=SAMPLE_SITE_DATA)
        
        assert response.status_code == 200
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()

    @patch('app.routers.sites.get_db')
    def test_create_site_duplicate_name(self, mock_get_db):
        """Test creation of site with duplicate name."""
        mock_get_db.return_value = self.mock_db
        
        # Mock that site already exists
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_site
        
        response = client.post("/api/v1/sites/", json=SAMPLE_SITE_DATA)
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @patch('app.routers.sites.get_db')
    def test_update_site_success(self, mock_get_db):
        """Test successful site update."""
        mock_get_db.return_value = self.mock_db
        
        # Mock site exists
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_site
        self.mock_db.commit = MagicMock()
        self.mock_db.refresh = MagicMock()
        
        response = client.put("/api/v1/sites/1", json=SAMPLE_SITE_UPDATE)
        
        assert response.status_code == 200
        self.mock_db.commit.assert_called_once()

    @patch('app.routers.sites.get_db')
    def test_update_site_not_found(self, mock_get_db):
        """Test update of non-existent site."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.put("/api/v1/sites/999", json=SAMPLE_SITE_UPDATE)
        
        assert response.status_code == 404
        assert "Site not found" in response.json()["detail"]

    @patch('app.routers.sites.get_db')
    def test_delete_site_success(self, mock_get_db):
        """Test successful site deletion."""
        mock_get_db.return_value = self.mock_db
        
        # Mock site exists
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_site
        self.mock_db.delete = MagicMock()
        self.mock_db.commit = MagicMock()
        
        response = client.delete("/api/v1/sites/1")
        
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]
        self.mock_db.delete.assert_called_once()

    @patch('app.routers.sites.get_db')
    def test_delete_site_not_found(self, mock_get_db):
        """Test deletion of non-existent site."""
        mock_get_db.return_value = self.mock_db
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        response = client.delete("/api/v1/sites/999")
        
        assert response.status_code == 404
        assert "Site not found" in response.json()["detail"]

    @patch('app.routers.sites.get_db')
    def test_get_sites_overview_success(self, mock_get_db):
        """Test successful retrieval of sites overview statistics."""
        mock_get_db.return_value = self.mock_db
        
        # Mock count queries
        self.mock_db.query.return_value.count.return_value = 10
        self.mock_db.query.return_value.group_by.return_value.all.return_value = [
            ("test", 5), ("production", 5)
        ]
        self.mock_db.query.return_value.filter.return_value.count.return_value = 3
        self.mock_db.query.return_value.filter.return_value.all.return_value = [self.mock_site]
        
        # Mock scalar for sum
        self.mock_db.query.return_value.scalar.return_value = 100
        
        response = client.get("/api/v1/sites/stats/overview")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_sites" in data
        assert "categories" in data
        assert "implementation_progress" in data
        assert "difficulty_distribution" in data
        assert "estimated_total_hours" in data

    @patch('app.routers.sites.get_db')
    def test_list_categories_success(self, mock_get_db):
        """Test successful listing of categories."""
        mock_get_db.return_value = self.mock_db
        
        # Mock category query
        self.mock_db.query.return_value.group_by.return_value.all.return_value = [
            ("test", 5), ("production", 3)
        ]
        
        response = client.get("/api/v1/sites/categories")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "test"
        assert data[0]["count"] == 5

    def test_create_site_invalid_data(self):
        """Test site creation with invalid data."""
        invalid_data = {
            "name": "",  # Empty name
            "display_name": "Test",
            "url": "invalid-url",  # Invalid URL format
            "category": "test"
        }
        
        response = client.post("/api/v1/sites/", json=invalid_data)
        
        # Should return validation error
        assert response.status_code == 422

    def test_list_sites_invalid_parameters(self):
        """Test listing sites with invalid parameters."""
        response = client.get("/api/v1/sites/?skip=-1&limit=0")
        
        # Should return validation error for negative skip and zero limit
        assert response.status_code == 422

    def test_list_sites_large_limit(self):
        """Test listing sites with limit exceeding maximum."""
        response = client.get("/api/v1/sites/?limit=2000")
        
        # Should return validation error for limit > 1000
        assert response.status_code == 422

    @patch('app.routers.sites.get_db')
    def test_database_error_handling(self, mock_get_db):
        """Test handling of database errors."""
        mock_get_db.return_value = self.mock_db
        
        # Mock database error
        self.mock_db.query.side_effect = Exception("Database connection failed")
        
        response = client.get("/api/v1/sites/")
        
        assert response.status_code == 500
        assert "Failed to list sites" in response.json()["detail"]

    def test_health_check_endpoint(self):
        """Test that the health endpoint is accessible."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

class TestSitesAPIIntegration:
    """Integration tests for sites API with real database operations."""
    
    @pytest.mark.integration
    def test_sites_endpoint_returns_200(self):
        """Test that sites endpoint returns 200 OK."""
        response = client.get("/api/v1/sites/")
        
        # Should return 200 even if no sites exist
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.integration
    def test_sites_stats_endpoint_returns_200(self):
        """Test that sites stats endpoint returns 200 OK."""
        response = client.get("/api/v1/sites/stats/overview")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_sites" in data
        assert "categories" in data
        assert "implementation_progress" in data

    @pytest.mark.integration
    def test_sites_categories_endpoint_returns_200(self):
        """Test that sites categories endpoint returns 200 OK."""
        response = client.get("/api/v1/sites/categories")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.integration
    def test_sites_pagination_works(self):
        """Test that pagination parameters work correctly."""
        # Test first page
        response1 = client.get("/api/v1/sites/?skip=0&limit=5")
        assert response1.status_code == 200
        
        # Test second page
        response2 = client.get("/api/v1/sites/?skip=5&limit=5")
        assert response2.status_code == 200
        
        # Both should return valid data
        data1 = response1.json()
        data2 = response2.json()
        assert isinstance(data1, list)
        assert isinstance(data2, list)

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 