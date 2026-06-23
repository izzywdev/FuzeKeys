#!/usr/bin/env python3
"""
Adaptive Google signup test that analyzes page structure first.
"""

import asyncio
import sys
import os
from datetime import date

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import only the necessary modules
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import time
import random


class AdaptiveGoogleSignup:
    """Adaptive Google signup that analyzes page structure."""
    
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.wait = None
    
    def setup_driver(self):
        """Setup Chrome WebDriver."""
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # Set Chrome binary path explicitly for Windows
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if os.path.exists(chrome_path):
            options.binary_location = chrome_path
        
        try:
            print("📥 Installing/updating ChromeDriver...")
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"⚠️ ChromeDriver auto-install failed: {e}")
            print("🔄 Trying with system ChromeDriver...")
            try:
                self.driver = webdriver.Chrome(options=options)
            except Exception as e2:
                print(f"❌ System ChromeDriver also failed: {e2}")
                raise Exception(f"Could not initialize Chrome WebDriver. Original error: {e}")
        
        self.wait = WebDriverWait(self.driver, 15)
        
        # Remove automation markers
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    def human_type(self, element, text, delay_range=(0.05, 0.15)):
        """Type like a human with random delays."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(*delay_range))
    
    def analyze_page_structure(self, page_name="current"):
        """Analyze and log all interactive elements on the current page."""
        print(f"\n🔍 ANALYZING {page_name.upper()} PAGE STRUCTURE")
        print("=" * 60)
        
        try:
            # Get page info
            current_url = self.driver.current_url
            page_title = self.driver.title
            print(f"📍 URL: {current_url}")
            print(f"📄 Title: {page_title}")
            
            # Find all interactive elements
            elements = {
                'inputs': self.driver.find_elements(By.TAG_NAME, "input"),
                'selects': self.driver.find_elements(By.TAG_NAME, "select"),
                'buttons': self.driver.find_elements(By.TAG_NAME, "button"),
                'comboboxes': self.driver.find_elements(By.XPATH, "//div[@role='combobox']"),
                'listboxes': self.driver.find_elements(By.XPATH, "//div[@role='listbox']"),
                'options': self.driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']"),
                'clickable_divs': self.driver.find_elements(By.XPATH, "//div[@role='button'] | //div[contains(@class, 'click')]")
            }
            
            for element_type, element_list in elements.items():
                print(f"\n📋 {element_type.upper()} ({len(element_list)} found):")
                
                for i, elem in enumerate(element_list[:10]):  # Show first 10 of each type
                    try:
                        elem_id = elem.get_attribute("id") or "no-id"
                        elem_name = elem.get_attribute("name") or "no-name"
                        elem_type = elem.get_attribute("type") or "no-type"
                        elem_aria_label = elem.get_attribute("aria-label") or "no-aria-label"
                        elem_text = elem.text.strip()[:50] or "no-text"
                        elem_class = elem.get_attribute("class") or "no-class"
                        elem_visible = elem.is_displayed()
                        elem_enabled = elem.is_enabled()
                        
                        if element_type == "options":
                            elem_data_value = elem.get_attribute("data-value") or "no-data-value"
                            print(f"  {i}: id='{elem_id}', text='{elem_text}', data-value='{elem_data_value}', visible={elem_visible}")
                        else:
                            print(f"  {i}: id='{elem_id}', name='{elem_name}', type='{elem_type}', text='{elem_text}', visible={elem_visible}")
                        
                        if elem_aria_label != "no-aria-label":
                            print(f"      aria-label='{elem_aria_label}'")
                        
                        if "month" in elem_text.lower() or "gender" in elem_text.lower() or "month" in elem_aria_label.lower() or "gender" in elem_aria_label.lower():
                            print(f"      🎯 POTENTIALLY RELEVANT FOR BIRTH DATE/GENDER!")
                            
                    except Exception as e:
                        print(f"  {i}: Error analyzing element - {e}")
                
                if len(element_list) > 10:
                    print(f"  ... and {len(element_list) - 10} more")
            
            # Take screenshot for reference
            screenshot_name = f"page_analysis_{page_name}.png"
            self.driver.save_screenshot(screenshot_name)
            print(f"\n📸 Screenshot saved: {screenshot_name}")
            
            return elements
            
        except Exception as e:
            print(f"❌ Error analyzing page structure: {e}")
            return {}
    
    def find_and_fill_element(self, target_type, target_value, element_info=None):
        """Find and fill an element based on various strategies."""
        print(f"\n🎯 FINDING AND FILLING {target_type.upper()}")
        print("=" * 40)
        
        strategies = []
        
        if target_type == "month":
            strategies = [
                # Strategy 1: Look for combobox with "Month" text
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox' and contains(text(), 'Month')]"),
                # Strategy 2: Look for combobox with month aria-label
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox' and contains(@aria-label, 'Month')]"),
                # Strategy 3: Look for select with month in name/id
                lambda: self.driver.find_elements(By.XPATH, "//select[contains(@name, 'month') or contains(@id, 'month')]"),
                # Strategy 4: First combobox (month often comes first)
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox']")[:1],
            ]
        elif target_type == "gender":
            strategies = [
                # Strategy 1: Look for combobox with "Gender" text
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox' and contains(text(), 'Gender')]"),
                # Strategy 2: Look for combobox with gender aria-label
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox' and contains(@aria-label, 'Gender')]"),
                # Strategy 3: Second combobox (gender often comes after month)
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox']")[1:2],
                # Strategy 4: Any remaining combobox
                lambda: self.driver.find_elements(By.XPATH, "//div[@role='combobox']"),
            ]
        elif target_type == "day":
            strategies = [
                lambda: self.driver.find_elements(By.ID, "day"),
                lambda: self.driver.find_elements(By.XPATH, "//input[contains(@aria-label, 'Day') or contains(@placeholder, 'Day')]"),
            ]
        elif target_type == "year":
            strategies = [
                lambda: self.driver.find_elements(By.ID, "year"),
                lambda: self.driver.find_elements(By.XPATH, "//input[contains(@aria-label, 'Year') or contains(@placeholder, 'Year')]"),
            ]
        
        element = None
        for i, strategy in enumerate(strategies):
            try:
                candidates = strategy()
                if candidates:
                    element = candidates[0]
                    print(f"✅ Found {target_type} using strategy {i+1}")
                    break
            except Exception as e:
                print(f"⚠️ Strategy {i+1} failed: {e}")
                continue
        
        if not element:
            print(f"❌ Could not find {target_type} element")
            return False
        
        # Now try to interact with the element
        try:
            if target_type in ["month", "gender"]:
                return self.handle_dropdown(element, target_type, target_value)
            else:
                # Handle regular input fields
                element.click()
                element.clear()
                self.human_type(element, str(target_value))
                print(f"✅ Filled {target_type}: {target_value}")
                return True
                
        except Exception as e:
            print(f"❌ Error interacting with {target_type}: {e}")
            return False
    
    def handle_dropdown(self, dropdown_element, dropdown_type, target_value):
        """Handle dropdown interaction (combobox)."""
        print(f"🔽 Opening {dropdown_type} dropdown...")
        
        try:
            # Scroll into view
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", dropdown_element)
            time.sleep(0.5)
            
            # Click to open
            dropdown_element.click()
            time.sleep(3)  # Wait for dropdown to open
            
            # Find options
            options = self.driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']")
            print(f"Found {len(options)} dropdown options")
            
            if not options:
                print("❌ No dropdown options found")
                return False
            
            # Log all options for debugging
            for i, option in enumerate(options[:10]):
                option_text = option.text.strip()
                option_data_value = option.get_attribute("data-value") or "no-data-value"
                print(f"  Option {i}: text='{option_text}', data-value='{option_data_value}'")
            
            # Try to select the target option
            target_option = None
            
            if dropdown_type == "month":
                # For month, target_value is "5" for May
                month_names = ["January", "February", "March", "April", "May", "June", 
                             "July", "August", "September", "October", "November", "December"]
                target_month_name = month_names[int(target_value) - 1]
                
                # Try by data-value first
                for option in options:
                    if option.get_attribute("data-value") == target_value:
                        target_option = option
                        print(f"🎯 Found month option by data-value: {target_value}")
                        break
                
                # Try by text if data-value didn't work
                if not target_option:
                    for option in options:
                        if target_month_name.lower() in option.text.lower():
                            target_option = option
                            print(f"🎯 Found month option by text: {target_month_name}")
                            break
                            
            elif dropdown_type == "gender":
                # For gender, target_value might be "Male" or "1"
                if target_value.lower() == "male":
                    target_data_value = "1"
                elif target_value.lower() == "female":
                    target_data_value = "2"
                else:
                    target_data_value = target_value
                
                # Try by data-value
                for option in options:
                    if option.get_attribute("data-value") == target_data_value:
                        target_option = option
                        print(f"🎯 Found gender option by data-value: {target_data_value}")
                        break
                
                # Try by text if data-value didn't work
                if not target_option:
                    for option in options:
                        if target_value.lower() in option.text.lower():
                            target_option = option
                            print(f"🎯 Found gender option by text: {target_value}")
                            break
            
            if not target_option:
                print(f"❌ Could not find target option for {dropdown_type}: {target_value}")
                # Try first option as fallback
                if options:
                    target_option = options[0]
                    print(f"🔄 Using first option as fallback")
            
            if target_option:
                # Try multiple click methods
                click_methods = ["regular", "javascript", "action_chain"]
                
                for method in click_methods:
                    try:
                        if method == "regular":
                            target_option.click()
                        elif method == "javascript":
                            self.driver.execute_script("arguments[0].click();", target_option)
                        elif method == "action_chain":
                            ActionChains(self.driver).move_to_element(target_option).click().perform()
                        
                        print(f"✅ Clicked {dropdown_type} option using {method}")
                        time.sleep(2)
                        
                        # Verify selection
                        current_text = dropdown_element.text.strip()
                        if current_text and current_text not in [dropdown_type.title(), ""]:
                            print(f"✅ {dropdown_type} selection verified: '{current_text}'")
                            # Close dropdown
                            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                            time.sleep(1)
                            return True
                        else:
                            print(f"⚠️ {method} click executed but selection not verified")
                            
                    except Exception as e:
                        print(f"⚠️ {method} click failed: {e}")
                        continue
            
            print(f"❌ Failed to select {dropdown_type}")
            return False
            
        except Exception as e:
            print(f"❌ Error handling {dropdown_type} dropdown: {e}")
            return False
    
    async def test_adaptive_signup(self):
        """Run adaptive signup test."""
        try:
            print("🚀 Starting Adaptive Google Signup Test...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
            # Analyze first page
            self.analyze_page_structure("name_page")
            
            # Fill first name
            print("✍️ Filling first name...")
            first_name_field = self.wait.until(EC.element_to_be_clickable((By.ID, "firstName")))
            self.human_type(first_name_field, "Smart")
            time.sleep(2)
            
            # Fill last name
            print("✍️ Filling last name...")
            last_name_field = self.wait.until(EC.element_to_be_clickable((By.ID, "lastName")))
            self.human_type(last_name_field, "Shopper")
            time.sleep(2)
            
            # Click Next
            print("👆 Clicking Next...")
            next_button = self.wait.until(EC.element_to_be_clickable((By.ID, "collectNameNext")))
            next_button.click()
            time.sleep(5)
            
            # Analyze birth date page
            self.analyze_page_structure("birth_date_page")
            
            # Fill birth date fields
            print("📅 Filling birth date fields...")
            
            # Month
            if self.find_and_fill_element("month", "5"):  # May
                time.sleep(2)
            
            # Day
            if self.find_and_fill_element("day", "15"):
                time.sleep(2)
            
            # Year
            if self.find_and_fill_element("year", "1990"):
                time.sleep(2)
            
            # Gender
            if self.find_and_fill_element("gender", "Male"):
                time.sleep(2)
            
            # Take screenshot before trying Next
            self.driver.save_screenshot("before_next_button.png")
            print("📸 Screenshot saved: before_next_button.png")
            
            # Try to find and click Next button
            print("👆 Looking for Next button...")
            next_selectors = [
                (By.ID, "birthdaygenderNext"),
                (By.XPATH, "//span[text()='Next']/.."),
                (By.XPATH, "//button[contains(text(), 'Next')]"),
                (By.XPATH, "//div[@role='button' and contains(text(), 'Next')]")
            ]
            
            next_button = None
            for selector in next_selectors:
                try:
                    next_button = self.wait.until(EC.element_to_be_clickable(selector))
                    print(f"✅ Found Next button")
                    break
                except:
                    continue
            
            if next_button:
                next_button.click()
                print("👆 Clicked Next button")
                time.sleep(5)
                
                # Analyze next page
                current_url = self.driver.current_url
                print(f"📍 Current URL: {current_url}")
                
                self.analyze_page_structure("after_birth_date")
                
                if "username" in current_url or any(word in current_url for word in ["email", "gmail", "account"]):
                    print("🎉 SUCCESS: Reached email/username setup page!")
                    
                    # Try to fill username if field is available
                    try:
                        username_field = self.driver.find_element(By.ID, "username")
                        self.human_type(username_field, "smarthubshopper")
                        print("✍️ Filled username: smarthubshopper")
                    except:
                        print("📧 No username field found - Google might auto-generate email")
                    
                    return {"success": True, "status": "reached_email_setup", "url": current_url}
                else:
                    print("⚠️ Unexpected page after birth date")
                    return {"success": False, "status": "unexpected_page", "url": current_url}
            else:
                print("❌ Could not find Next button")
                return {"success": False, "status": "next_button_not_found"}
                
        except Exception as e:
            print(f"❌ Error during adaptive signup: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("adaptive_signup_error.png")
                print("📸 Error screenshot saved: adaptive_signup_error.png")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Test complete. Browser will stay open for inspection...")
                input("Press Enter to close the browser...")
                self.driver.quit()


async def main():
    """Main test function."""
    print("🌟 Adaptive Google Signup Test")
    print("=" * 50)
    print("🧠 This test analyzes the page structure and adapts to changes")
    print("📊 It provides detailed logging of all elements found")
    print()
    
    # Run the adaptive test
    test = AdaptiveGoogleSignup(headless=False)
    result = await test.test_adaptive_signup()
    
    print("\n📊 Test Result:")
    print(f"Success: {result.get('success', False)}")
    print(f"Status: {result.get('status', 'unknown')}")
    if 'error' in result:
        print(f"Error: {result['error']}")
    if 'url' in result:
        print(f"Final URL: {result['url']}")
    
    print("\n📚 Analysis Notes:")
    print("1. Check the page analysis screenshots for structure changes")
    print("2. Review the console output for detailed element information")
    print("3. This adaptive approach should handle Google's UI changes better")
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 