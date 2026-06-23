#!/usr/bin/env python3
"""
Focused Google signup gender dropdown test.
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


class GenderDropdownTest:
    """Focused gender dropdown test class."""
    
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
    
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
        
        # Remove automation markers
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    def human_type(self, element, text, delay_range=(0.05, 0.15)):
        """Type like a human with random delays."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(*delay_range))
    
    def wait_and_get_element(self, by, value, timeout=10):
        """Wait for element and return it."""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except:
            return None
    
    def click_element_safely(self, element, method="regular"):
        """Try different click methods for stubborn elements."""
        try:
            if method == "regular":
                element.click()
                return True
            elif method == "javascript":
                self.driver.execute_script("arguments[0].click();", element)
                return True
            elif method == "action_chain":
                ActionChains(self.driver).move_to_element(element).click().perform()
                return True
            elif method == "force_javascript":
                self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));", element)
                return True
        except Exception as e:
            print(f"⚠️ Click method '{method}' failed: {e}")
            return False
    
    def analyze_gender_dropdown(self):
        """Analyze the gender dropdown structure in detail."""
        print("\n🔍 ANALYZING GENDER DROPDOWN STRUCTURE")
        print("=" * 50)
        
        # Find all comboboxes
        comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
        print(f"Found {len(comboboxes)} combobox elements:")
        
        gender_combobox = None
        for i, combo in enumerate(comboboxes):
            combo_text = combo.text.strip()
            combo_id = combo.get_attribute("id") or "no-id"
            combo_class = combo.get_attribute("class") or "no-class"
            combo_aria_label = combo.get_attribute("aria-label") or "no-aria-label"
            
            print(f"  Combobox {i}: text='{combo_text}', id='{combo_id}', aria-label='{combo_aria_label}'")
            print(f"    class='{combo_class[:100]}...' " if len(combo_class) > 100 else f"    class='{combo_class}'")
            
            # Check if this is the gender combobox
            if "gender" in combo_text.lower() or "gender" in combo_aria_label.lower():
                gender_combobox = combo
                print(f"  🎯 This appears to be the GENDER combobox!")
            elif combo_text == "Gender":
                gender_combobox = combo
                print(f"  🎯 This is definitely the GENDER combobox (exact text match)!")
        
        if not gender_combobox:
            # Look for it as second combobox if we have multiple
            if len(comboboxes) >= 2:
                gender_combobox = comboboxes[1]  # Usually month is first, gender is second
                print(f"  🎯 Assuming combobox 1 is gender (common pattern)")
        
        return gender_combobox
    
    def try_select_gender_option(self, target_gender_value="1"):
        """Try multiple methods to select gender option."""
        print(f"\n🎯 TRYING TO SELECT GENDER (data-value={target_gender_value})")
        print("=" * 50)
        
        # Look for all role='option' elements
        options = self.driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']")
        print(f"Found {len(options)} option elements:")
        
        gender_options = []
        for i, option in enumerate(options):
            option_text = option.text.strip()
            option_data_value = option.get_attribute("data-value") or "no-data-value"
            option_class = option.get_attribute("class") or "no-class"
            option_visible = option.is_displayed()
            option_enabled = option.is_enabled()
            
            print(f"  Option {i}: text='{option_text}', data-value='{option_data_value}', visible={option_visible}, enabled={option_enabled}")
            print(f"    class='{option_class[:80]}...' " if len(option_class) > 80 else f"    class='{option_class}'")
            
            # Check if this looks like a gender option
            if option_data_value in ["1", "2", "3", "4"]:  # Common gender data-values
                gender_options.append({
                    'element': option,
                    'data_value': option_data_value,
                    'text': option_text,
                    'index': i
                })
        
        print(f"\n📊 Identified {len(gender_options)} potential gender options:")
        for opt in gender_options:
            print(f"  - data-value='{opt['data_value']}', text='{opt['text']}'")
        
        # Try to select the target option
        target_option = None
        for opt in gender_options:
            if opt['data_value'] == target_gender_value:
                target_option = opt
                break
        
        if not target_option:
            print(f"❌ No option found with data-value='{target_gender_value}'")
            if gender_options:
                target_option = gender_options[0]  # Use first available
                print(f"🔄 Using first available option: data-value='{target_option['data_value']}'")
        
        if target_option:
            print(f"\n🎯 Attempting to click option with data-value='{target_option['data_value']}'")
            element = target_option['element']
            
            # Try different click methods
            click_methods = ["regular", "javascript", "action_chain", "force_javascript"]
            
            for method in click_methods:
                print(f"  🖱️ Trying {method} click...")
                
                # Scroll element into view first
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                    time.sleep(0.5)
                except:
                    pass
                
                # Try the click
                if self.click_element_safely(element, method):
                    print(f"  ✅ {method} click executed without error")
                    time.sleep(2)  # Wait for selection to register
                    
                    # Verify if selection worked
                    if self.verify_gender_selection():
                        print(f"  🎉 SUCCESS: Gender selection verified!")
                        return True
                    else:
                        print(f"  ⚠️ {method} click executed but selection not verified")
                else:
                    print(f"  ❌ {method} click failed")
                
                time.sleep(1)
        
        return False
    
    def verify_gender_selection(self):
        """Verify that gender selection actually worked."""
        print("\n✅ VERIFYING GENDER SELECTION")
        print("=" * 30)
        
        # Find the gender combobox again
        gender_combobox = self.analyze_gender_dropdown()
        
        if gender_combobox:
            current_text = gender_combobox.text.strip()
            print(f"Gender combobox current text: '{current_text}'")
            
            # Check if text changed from "Gender" to something else
            if current_text and current_text != "Gender":
                print(f"✅ Gender appears to be selected: '{current_text}'")
                return True
            else:
                print(f"❌ Gender still shows default text: '{current_text}'")
                return False
        else:
            print("❌ Could not find gender combobox for verification")
            return False
    
    async def test_gender_dropdown_focused(self):
        """Focus test just on the gender dropdown interaction."""
        try:
            print("🚀 Starting FOCUSED Google Gender Dropdown Test...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            
            wait = WebDriverWait(self.driver, 15)
            
            # Fill first name
            print("✍️ Filling first name...")
            first_name_field = wait.until(EC.element_to_be_clickable((By.ID, "firstName")))
            self.human_type(first_name_field, "Smart")
            
            # Fill last name
            print("✍️ Filling last name...")
            last_name_field = wait.until(EC.element_to_be_clickable((By.ID, "lastName")))
            self.human_type(last_name_field, "Shopper")
            
            # Click Next
            print("👆 Clicking Next...")
            next_button = wait.until(EC.element_to_be_clickable((By.ID, "collectNameNext")))
            next_button.click()
            
            # Wait for birth date page
            print("📅 Waiting for birth date page...")
            time.sleep(3)
            
            # Fill month first (we know this works)
            print("📅 Filling month (May)...")
            month_combobox = self.driver.find_element(By.XPATH, "//div[@role='combobox' and contains(text(), 'Month')]")
            month_combobox.click()
            time.sleep(2)
            
            # Select May (data-value="5")
            month_options = self.driver.find_elements(By.XPATH, "//div[@role='option']")
            for option in month_options:
                if option.get_attribute("data-value") == "5":
                    option.click()
                    print("✅ Selected May")
                    break
            time.sleep(2)
            
            # Fill day
            print("📅 Filling day...")
            day_field = self.driver.find_element(By.ID, "day")
            self.human_type(day_field, "15")
            time.sleep(2)
            
            # Fill year
            print("📅 Filling year...")
            year_field = self.driver.find_element(By.ID, "year")
            self.human_type(year_field, "1990")
            time.sleep(2)
            
            # Now focus on gender dropdown
            print("\n🎯 FOCUSING ON GENDER DROPDOWN")
            print("=" * 50)
            
            # Analyze the dropdown structure
            gender_combobox = self.analyze_gender_dropdown()
            
            if not gender_combobox:
                print("❌ Could not find gender combobox!")
                return {"success": False, "error": "Gender combobox not found"}
            
            # Take screenshot before clicking
            self.driver.save_screenshot("before_gender_click.png")
            print("📸 Screenshot saved: before_gender_click.png")
            
            # Click to open gender dropdown
            print("\n🔽 Opening gender dropdown...")
            if self.click_element_safely(gender_combobox, "regular"):
                print("✅ Gender dropdown opened")
                time.sleep(3)  # Give more time for dropdown to fully appear
            else:
                print("❌ Failed to open gender dropdown")
                return {"success": False, "error": "Could not open gender dropdown"}
            
            # Take screenshot of opened dropdown
            self.driver.save_screenshot("gender_dropdown_opened.png")
            print("📸 Screenshot saved: gender_dropdown_opened.png")
            
            # Try to select gender
            success = self.try_select_gender_option(target_gender_value="1")  # Male
            
            if success:
                print("\n🎉 GENDER SELECTION SUCCESS!")
                
                # Take screenshot of success
                self.driver.save_screenshot("gender_selection_success.png")
                print("📸 Screenshot saved: gender_selection_success.png")
                
                # Try to proceed to next step
                print("\n👆 Looking for Next button...")
                next_selectors = [
                    (By.ID, "birthdaygenderNext"),
                    (By.XPATH, "//span[text()='Next']/.."),
                    (By.XPATH, "//button[contains(text(), 'Next')]"),
                ]
                
                next_button = None
                for selector in next_selectors:
                    try:
                        next_button = wait.until(EC.element_to_be_clickable(selector))
                        print(f"✅ Found Next button")
                        break
                    except:
                        continue
                
                if next_button:
                    next_button.click()
                    print("👆 Clicked Next - proceeding to email setup!")
                    time.sleep(5)
                    
                    # Check if we reached email setup
                    current_url = self.driver.current_url
                    print(f"📍 Current URL: {current_url}")
                    
                    if "username" in current_url or "gmail" in current_url:
                        print("🎉 SUCCESS: Reached email setup page!")
                        return {"success": True, "status": "reached_email_setup"}
                    else:
                        print("⚠️ Next button clicked but didn't reach expected page")
                        return {"success": False, "status": "unexpected_page_after_gender"}
                else:
                    print("❌ Could not find Next button after gender selection")
                    return {"success": False, "error": "Next button not found after gender selection"}
            else:
                print("\n❌ GENDER SELECTION FAILED")
                
                # Take screenshot of failure
                self.driver.save_screenshot("gender_selection_failed.png")
                print("📸 Screenshot saved: gender_selection_failed.png")
                
                return {"success": False, "error": "Gender selection failed"}
                
        except Exception as e:
            print(f"❌ Error during test: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("gender_test_error.png")
                print("📸 Error screenshot saved: gender_test_error.png")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Test complete. Browser will stay open for inspection...")
                input("Press Enter to close the browser...")
                self.driver.quit()


async def main():
    """Main test function."""
    print("🌟 Focused Google Gender Dropdown Test")
    print("=" * 50)
    print("🎯 This test focuses specifically on the gender dropdown selection issue")
    print("📊 It will provide detailed analysis and try multiple approaches")
    print()
    
    # Run the focused test
    test = GenderDropdownTest(headless=False)
    result = await test.test_gender_dropdown_focused()
    
    print("\n📊 Test Result:")
    print(f"Success: {result.get('success', False)}")
    print(f"Status: {result.get('status', 'unknown')}")
    if 'error' in result:
        print(f"Error: {result['error']}")
    
    print("\n📚 Analysis Notes:")
    print("1. Check the screenshots for visual debugging")
    print("2. Look at the console output for detailed element analysis")
    print("3. If gender selection fails, we may need to try different strategies")
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 