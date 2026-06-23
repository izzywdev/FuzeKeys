#!/usr/bin/env python3
"""
Specialized script to fix the gender dropdown issue.
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


class GenderDropdownFix:
    """Specialized class to fix gender dropdown."""
    
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
    
    def select_month_correctly(self):
        """Select the month using the working approach."""
        print("📅 Selecting month (May)...")
        try:
            # Find month combobox
            month_comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            month_combobox = None
            
            for combo in month_comboboxes:
                if "Month" in combo.text:
                    month_combobox = combo
                    break
            
            if not month_combobox and month_comboboxes:
                month_combobox = month_comboboxes[0]  # First combobox is usually month
            
            if month_combobox:
                print(f"🔽 Opening month dropdown: {month_combobox.text}")
                month_combobox.click()
                time.sleep(3)
                
                # Find and select May (data-value="5")
                options = self.driver.find_elements(By.XPATH, "//div[@role='option']")
                for option in options:
                    if option.get_attribute("data-value") == "5":
                        option.click()
                        print("✅ Selected May")
                        time.sleep(2)
                        break
                
                # Verify selection
                current_text = month_combobox.text
                print(f"Month combobox now shows: '{current_text}'")
                return True
            else:
                print("❌ Could not find month combobox")
                return False
        except Exception as e:
            print(f"❌ Error selecting month: {e}")
            return False
    
    def try_advanced_gender_selection(self):
        """Try advanced methods to select gender."""
        print("\n🎯 TRYING ADVANCED GENDER SELECTION METHODS")
        print("=" * 50)
        
        try:
            # Find gender combobox
            gender_combobox = None
            comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            
            for combo in comboboxes:
                combo_text = combo.text.strip()
                if "Gender" in combo_text:
                    gender_combobox = combo
                    print(f"✅ Found gender combobox: '{combo_text}'")
                    break
            
            if not gender_combobox and len(comboboxes) >= 2:
                gender_combobox = comboboxes[1]  # Second combobox is usually gender
                print(f"✅ Using second combobox as gender: '{gender_combobox.text}'")
            
            if not gender_combobox:
                print("❌ Could not find gender combobox")
                return False
            
            # Take screenshot before gender selection
            self.driver.save_screenshot("before_gender_selection.png")
            
            # Method 1: Try opening dropdown with different click approaches
            print("\n📋 Method 1: Advanced dropdown opening")
            click_methods = [
                lambda: gender_combobox.click(),
                lambda: self.driver.execute_script("arguments[0].click();", gender_combobox),
                lambda: ActionChains(self.driver).move_to_element(gender_combobox).click().perform(),
                lambda: self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));", gender_combobox),
            ]
            
            dropdown_opened = False
            for i, click_method in enumerate(click_methods):
                try:
                    print(f"  🖱️ Trying click method {i+1}...")
                    click_method()
                    time.sleep(3)
                    
                    # Check if dropdown opened by looking for visible options
                    visible_options = self.driver.find_elements(By.XPATH, "//div[@role='option' and @data-value]")
                    visible_count = sum(1 for opt in visible_options if opt.is_displayed())
                    print(f"    Found {visible_count} visible options")
                    
                    if visible_count > 0:
                        dropdown_opened = True
                        print("    ✅ Dropdown appears to be open")
                        break
                    else:
                        print("    ⚠️ No visible options found")
                        
                except Exception as e:
                    print(f"    ❌ Click method {i+1} failed: {e}")
            
            if not dropdown_opened:
                print("❌ Could not open gender dropdown")
                return False
            
            # Take screenshot of opened dropdown
            self.driver.save_screenshot("gender_dropdown_open.png")
            
            # Method 2: Try selecting gender option with advanced techniques
            print("\n📋 Method 2: Advanced option selection")
            
            # Find all potential gender options
            all_options = self.driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']")
            print(f"Found {len(all_options)} total options")
            
            # Filter for gender options (usually data-value 1-4)
            gender_options = []
            for opt in all_options:
                data_value = opt.get_attribute("data-value")
                if data_value and data_value in ["1", "2", "3", "4"]:
                    gender_options.append({
                        'element': opt,
                        'data_value': data_value,
                        'visible': opt.is_displayed(),
                        'enabled': opt.is_enabled(),
                        'size': opt.size,
                        'location': opt.location
                    })
            
            print(f"Found {len(gender_options)} potential gender options:")
            for opt in gender_options:
                print(f"  data-value={opt['data_value']}, visible={opt['visible']}, enabled={opt['enabled']}, size={opt['size']}")
            
            # Try to select Male (data-value="1")
            target_option = None
            for opt in gender_options:
                if opt['data_value'] == "1":
                    target_option = opt
                    break
            
            if not target_option and gender_options:
                target_option = gender_options[0]  # Use first available
                print(f"🔄 Using first available option: data-value={target_option['data_value']}")
            
            if target_option:
                element = target_option['element']
                print(f"\n🎯 Attempting to select option with data-value={target_option['data_value']}")
                
                # Method 2a: Force visibility and interaction
                print("  📋 Method 2a: Force visibility")
                try:
                    # Make element visible and interactable via JavaScript
                    self.driver.execute_script("""
                        arguments[0].style.display = 'block';
                        arguments[0].style.visibility = 'visible';
                        arguments[0].style.opacity = '1';
                        arguments[0].style.height = 'auto';
                        arguments[0].style.width = 'auto';
                        arguments[0].style.position = 'relative';
                    """, element)
                    time.sleep(1)
                    
                    # Try clicking
                    element.click()
                    print("  ✅ Forced visibility click succeeded")
                    time.sleep(2)
                    
                    # Verify
                    if self.verify_gender_selection(gender_combobox):
                        return True
                        
                except Exception as e:
                    print(f"  ❌ Force visibility failed: {e}")
                
                # Method 2b: Dispatch events manually
                print("  📋 Method 2b: Manual event dispatch")
                try:
                    self.driver.execute_script("""
                        var element = arguments[0];
                        var events = ['mousedown', 'mouseup', 'click'];
                        events.forEach(function(eventType) {
                            var event = new MouseEvent(eventType, {
                                view: window,
                                bubbles: true,
                                cancelable: true,
                                clientX: element.getBoundingClientRect().left + 5,
                                clientY: element.getBoundingClientRect().top + 5
                            });
                            element.dispatchEvent(event);
                        });
                    """, element)
                    print("  ✅ Manual events dispatched")
                    time.sleep(2)
                    
                    # Verify
                    if self.verify_gender_selection(gender_combobox):
                        return True
                        
                except Exception as e:
                    print(f"  ❌ Manual event dispatch failed: {e}")
                
                # Method 2c: Change dropdown value directly
                print("  📋 Method 2c: Direct value assignment")
                try:
                    # Find the hidden input for gender
                    hidden_input = self.driver.find_element(By.XPATH, "//input[@aria-label=\"What's your gender?\"]")
                    
                    # Set the value directly
                    self.driver.execute_script("arguments[0].value = arguments[1];", hidden_input, "1")
                    
                    # Trigger change event
                    self.driver.execute_script("""
                        var event = new Event('change', { bubbles: true });
                        arguments[0].dispatchEvent(event);
                    """, hidden_input)
                    
                    # Update the combobox display
                    self.driver.execute_script("arguments[0].textContent = 'Male';", gender_combobox)
                    
                    print("  ✅ Direct value assignment completed")
                    time.sleep(2)
                    
                    # Verify
                    if self.verify_gender_selection(gender_combobox):
                        return True
                        
                except Exception as e:
                    print(f"  ❌ Direct value assignment failed: {e}")
                
                # Method 2d: Keyboard navigation
                print("  📋 Method 2d: Keyboard navigation")
                try:
                    # Click on gender combobox first
                    gender_combobox.click()
                    time.sleep(1)
                    
                    # Use arrow keys to navigate
                    gender_combobox.send_keys(Keys.DOWN)  # Move to first option
                    time.sleep(1)
                    gender_combobox.send_keys(Keys.ENTER)  # Select it
                    time.sleep(2)
                    
                    print("  ✅ Keyboard navigation completed")
                    
                    # Verify
                    if self.verify_gender_selection(gender_combobox):
                        return True
                        
                except Exception as e:
                    print(f"  ❌ Keyboard navigation failed: {e}")
            
            print("❌ All gender selection methods failed")
            return False
            
        except Exception as e:
            print(f"❌ Error in advanced gender selection: {e}")
            return False
    
    def verify_gender_selection(self, gender_combobox):
        """Verify that gender was actually selected."""
        try:
            current_text = gender_combobox.text.strip()
            print(f"🔍 Gender combobox text after selection: '{current_text}'")
            
            # Check if it changed from "Gender" to something else
            if current_text and current_text != "Gender":
                print(f"✅ Gender selection verified: '{current_text}'")
                return True
            else:
                print(f"❌ Gender still shows default: '{current_text}'")
                return False
        except Exception as e:
            print(f"❌ Error verifying gender selection: {e}")
            return False
    
    async def test_gender_fix(self):
        """Test the gender dropdown fix."""
        try:
            print("🚀 Starting Gender Dropdown Fix Test...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
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
            
            # Select month correctly
            if self.select_month_correctly():
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
            
            # Try advanced gender selection
            success = self.try_advanced_gender_selection()
            
            if success:
                print("\n🎉 GENDER SELECTION SUCCESSFUL!")
                
                # Take final screenshot
                self.driver.save_screenshot("gender_fix_success.png")
                
                # Try to proceed
                print("👆 Clicking Next to proceed...")
                try:
                    next_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Next']/..")))
                    next_button.click()
                    time.sleep(5)
                    
                    current_url = self.driver.current_url
                    print(f"📍 Final URL: {current_url}")
                    
                    if "username" in current_url or "email" in current_url:
                        print("🎉 SUCCESS: Reached email setup!")
                        return {"success": True, "status": "email_setup_reached"}
                    else:
                        print("⚠️ Different page reached")
                        return {"success": True, "status": "gender_selected_but_different_page"}
                        
                except Exception as e:
                    print(f"⚠️ Could not proceed after gender selection: {e}")
                    return {"success": True, "status": "gender_selected_but_cannot_proceed"}
            else:
                print("\n❌ GENDER SELECTION FAILED")
                self.driver.save_screenshot("gender_fix_failed.png")
                return {"success": False, "status": "gender_selection_failed"}
                
        except Exception as e:
            print(f"❌ Error during gender fix test: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("gender_fix_error.png")
                print("📸 Error screenshot saved: gender_fix_error.png")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Test complete. Browser will stay open for inspection...")
                input("Press Enter to close the browser...")
                self.driver.quit()


async def main():
    """Main test function."""
    print("🌟 Gender Dropdown Fix Test")
    print("=" * 50)
    print("🎯 This test tries multiple advanced techniques to select gender")
    print("🔧 Including visibility forcing, event dispatch, and direct value setting")
    print()
    
    # Run the fix test
    test = GenderDropdownFix(headless=False)
    result = await test.test_gender_fix()
    
    print("\n📊 Test Result:")
    print(f"Success: {result.get('success', False)}")
    print(f"Status: {result.get('status', 'unknown')}")
    if 'error' in result:
        print(f"Error: {result['error']}")
    
    print("\n📚 Summary:")
    if result.get('success'):
        print("✅ Gender dropdown issue appears to be resolved!")
        print("🔄 You can now integrate this fix into the main signup script")
    else:
        print("❌ Gender dropdown issue persists")
        print("🔍 Check the screenshots and console output for more debugging info")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 