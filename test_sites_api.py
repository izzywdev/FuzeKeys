"""
Test script to demonstrate the FuzeKeys Sites API functionality.
This script tests various API endpoints and shows how to interact with the sites database.
"""

import sqlite3
import json
from datetime import datetime

def test_database_queries():
    """Test direct database queries."""
    print("🔍 === Testing Direct Database Queries ===\n")
    
    try:
        # Connect to SQLite database
        conn = sqlite3.connect('sites.db')
        cursor = conn.cursor()
        
        # Test 1: Get total count
        cursor.execute("SELECT COUNT(*) FROM sites")
        total_sites = cursor.fetchone()[0]
        print(f"📊 Total sites in database: {total_sites}")
        
        # Test 2: Get top priority sites
        cursor.execute("""
            SELECT name, display_name, category, priority, signup_difficulty 
            FROM sites 
            WHERE priority >= 80 
            ORDER BY priority DESC 
            LIMIT 10
        """)
        
        top_sites = cursor.fetchall()
        print(f"\n🏆 Top {len(top_sites)} Priority Sites:")
        for site in top_sites:
            name, display_name, category, priority, difficulty = site
            print(f"  • {display_name} ({category}) - Priority: {priority}, Difficulty: {difficulty}")
        
        # Test 3: Category breakdown
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM sites 
            GROUP BY category 
            ORDER BY count DESC
        """)
        
        categories = cursor.fetchall()
        print(f"\n📂 Categories ({len(categories)} total):")
        for category, count in categories:
            print(f"  • {category}: {count} sites")
        
        # Test 4: Find sites requiring phone verification
        cursor.execute("""
            SELECT name, display_name, category 
            FROM sites 
            WHERE requires_phone_verification = 1
            ORDER BY priority DESC
        """)
        
        phone_sites = cursor.fetchall()
        print(f"\n📱 Sites requiring phone verification ({len(phone_sites)} total):")
        for site in phone_sites[:10]:  # Show first 10
            name, display_name, category = site
            print(f"  • {display_name} ({category})")
        
        # Test 5: Find sites with CAPTCHA
        cursor.execute("""
            SELECT name, display_name, category, captcha_type 
            FROM sites 
            WHERE has_captcha = 1
            ORDER BY priority DESC
        """)
        
        captcha_sites = cursor.fetchall()
        print(f"\n🤖 Sites with CAPTCHA ({len(captcha_sites)} total):")
        for site in captcha_sites:
            name, display_name, category, captcha_type = site
            captcha_info = f" ({captcha_type})" if captcha_type else ""
            print(f"  • {display_name} ({category}){captcha_info}")
        
        # Test 6: Difficulty distribution
        cursor.execute("""
            SELECT signup_difficulty, COUNT(*) as count 
            FROM sites 
            GROUP BY signup_difficulty 
            ORDER BY 
                CASE signup_difficulty 
                    WHEN 'easy' THEN 1 
                    WHEN 'medium' THEN 2 
                    WHEN 'hard' THEN 3 
                    WHEN 'extreme' THEN 4 
                END
        """)
        
        difficulties = cursor.fetchall()
        print(f"\n📈 Signup Difficulty Distribution:")
        total_sites_with_difficulty = sum(count for _, count in difficulties)
        for difficulty, count in difficulties:
            percentage = (count / total_sites_with_difficulty) * 100
            print(f"  • {difficulty.capitalize()}: {count} sites ({percentage:.1f}%)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database query error: {e}")

def generate_api_examples():
    """Generate example API requests."""
    print("\n🚀 === API Usage Examples ===\n")
    
    base_url = "http://localhost:8000/api/v1/sites"
    
    examples = [
        {
            "title": "List all sites",
            "method": "GET",
            "url": f"{base_url}",
            "description": "Get all sites with default pagination"
        },
        {
            "title": "List high-priority sites",
            "method": "GET", 
            "url": f"{base_url}?priority_min=80&limit=20",
            "description": "Get sites with priority 80 or higher"
        },
        {
            "title": "List cloud providers",
            "method": "GET",
            "url": f"{base_url}?category=cloud-provider",
            "description": "Get all cloud provider sites"
        },
        {
            "title": "Search for Google sites",
            "method": "GET",
            "url": f"{base_url}?search=google",
            "description": "Search for sites containing 'google'"
        },
        {
            "title": "Get site by name", 
            "method": "GET",
            "url": f"{base_url}/name/google",
            "description": "Get Google site details"
        },
        {
            "title": "List hard difficulty sites",
            "method": "GET",
            "url": f"{base_url}?difficulty=hard&sort_by=priority&sort_order=desc",
            "description": "Get sites with hard difficulty, sorted by priority"
        },
        {
            "title": "Get statistics",
            "method": "GET",
            "url": f"{base_url}/stats/overview",
            "description": "Get database statistics and overview"
        },
        {
            "title": "Get categories",
            "method": "GET",
            "url": f"{base_url}/categories",
            "description": "Get list of all categories with counts"
        }
    ]
    
    print("📝 cURL Examples:")
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['title']}:")
        print(f"   {example['description']}")
        print(f"   curl \"{example['url']}\"")
    
    print("\n🐍 Python Examples:")
    print("""
import requests

# Get high-priority sites
response = requests.get(
    "http://localhost:8000/api/v1/sites",
    params={"priority_min": 80, "limit": 10}
)
sites = response.json()
print(f"Found {len(sites)} high-priority sites")

# Get specific site
google_site = requests.get(
    "http://localhost:8000/api/v1/sites/name/google"
).json()
print(f"Google difficulty: {google_site['signup_difficulty']}")

# Get statistics
stats = requests.get(
    "http://localhost:8000/api/v1/sites/stats/overview"
).json()
print(f"Total sites: {stats['total_sites']}")
""")

def show_integration_examples():
    """Show examples of integrating with the sites database."""
    print("\n🔧 === Integration Examples ===\n")
    
    print("1. Site Selection for Automation:")
    print("""
# Select sites for automation based on criteria
SELECT name, display_name, priority, estimated_hours
FROM sites 
WHERE priority >= 70 
  AND signup_difficulty IN ('easy', 'medium')
  AND has_captcha = 0
  AND requires_phone_verification = 0
ORDER BY priority DESC, estimated_hours ASC
LIMIT 10;
""")
    
    print("2. Track Implementation Progress:")
    print("""
# Update site implementation status
UPDATE sites 
SET signup_status = 'completed',
    signin_status = 'in_progress',
    notes = 'Playwright automation successful',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'permit_io';
""")
    
    print("3. Find Sites Needing Attention:")
    print("""
# Find high-priority sites not yet started
SELECT name, display_name, category, priority, estimated_hours
FROM sites
WHERE priority >= 80 
  AND signup_status = 'not_started'
  AND signin_status = 'not_started'
  AND apikey_status = 'not_started'
ORDER BY priority DESC;
""")
    
    print("4. Anti-Bot Technique Analysis:")
    print("""
# Sites with multiple anti-bot techniques (PostgreSQL/SQLite JSON functions)
SELECT name, display_name, anti_bot_techniques
FROM sites
WHERE json_array_length(anti_bot_techniques) > 2
ORDER BY priority DESC;
""")

def main():
    """Main function to run all tests."""
    print("🎯 === FuzeKeys Sites Database Test Suite ===\n")
    
    # Test direct database access
    test_database_queries()
    
    # Show API examples
    generate_api_examples()
    
    # Show integration examples  
    show_integration_examples()
    
    print("\n✅ === Test Suite Complete ===")
    print("💡 To start the API server and test these endpoints:")
    print("   cd backend && python -m uvicorn app.main:app --reload")
    print("🌐 Then visit: http://localhost:8000/docs")

if __name__ == "__main__":
    main() 