#!/usr/bin/env python3
"""
Simple test script to verify sites endpoints are working.
This script tests the sites API endpoints to ensure they return 200 OK.
"""

import requests
import json
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8002"
SITES_API = f"{BASE_URL}/api/v1/sites"

def test_endpoint(url: str, description: str) -> bool:
    """Test an endpoint and return True if successful."""
    try:
        print(f"Testing {description}...")
        response = requests.get(url, timeout=10)
        
        print(f"  Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  Response Type: {type(data)}")
                if isinstance(data, list):
                    print(f"  Items Count: {len(data)}")
                elif isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())}")
                print(f"  ✅ SUCCESS: {description}")
                return True
            except json.JSONDecodeError:
                print(f"  ⚠️  WARNING: Response is not valid JSON")
                print(f"  Response: {response.text[:200]}...")
                return False
        else:
            print(f"  ❌ FAILED: {description}")
            print(f"  Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  ❌ FAILED: {description}")
        print(f"  Connection Error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ FAILED: {description}")
        print(f"  Unexpected Error: {e}")
        return False

def test_health_endpoint() -> bool:
    """Test the health endpoint."""
    return test_endpoint(f"{BASE_URL}/health", "Health Check")

def test_sites_list() -> bool:
    """Test the sites list endpoint with pagination."""
    return test_endpoint(f"{SITES_API}/?skip=0&limit=10", "Sites List (Paginated)")

def test_sites_stats() -> bool:
    """Test the sites statistics endpoint."""
    return test_endpoint(f"{SITES_API}/stats/overview", "Sites Statistics")

def test_sites_categories() -> bool:
    """Test the sites categories endpoint."""
    return test_endpoint(f"{SITES_API}/categories", "Sites Categories")

def test_sites_with_filters() -> bool:
    """Test the sites endpoint with various filters."""
    filters = [
        ("category=tech-giant", "Category Filter"),
        ("difficulty=easy", "Difficulty Filter"),
        ("priority_min=80", "Priority Filter"),
        ("search=google", "Search Filter"),
        ("sort_by=priority&sort_order=desc", "Sorting")
    ]
    
    results = []
    for filter_param, description in filters:
        url = f"{SITES_API}/?{filter_param}&skip=0&limit=5"
        results.append(test_endpoint(url, f"Sites List - {description}"))
    
    return all(results)

def main():
    """Run all tests."""
    print("🚀 Starting Sites API Endpoint Tests")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health_endpoint),
        ("Sites List", test_sites_list),
        ("Sites Statistics", test_sites_stats),
        ("Sites Categories", test_sites_categories),
        ("Sites Filtering", test_sites_with_filters),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 30)
        result = test_func()
        results.append((test_name, result))
        print()
    
    # Summary
    print("=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal Tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Sites API is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Check the backend and database connection.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 