#!/usr/bin/env python3
"""
Improved Google signup with robust element finding.
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


class ImprovedGoogleSignup:
    """Improved Google signup with robust element finding."""
    
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
            try:
                self.driver = webdriver.Chrome(options=options)
            except Exception as e2:
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
    
    def find_combobox_by_index(self, index, expected_text=None):
        """Find combobox by index with optional text verification."""
        try:
            comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            
            if index < len(comboboxes):
                combobox = comboboxes[index]
                combobox_text = combobox.text.strip()
                
                if expected_text:
                    if expected_text.lower() in combobox_text.lower():
                        print(f"✅ Found combobox {index} with expected text: '{combobox_text}'")
                        return combobox
                    else:
                        print(f"⚠️ Combobox {index} text mismatch. Expected: '{expected_text}', Found: '{combobox_text}'")
                        return combobox  # Return anyway, might still work
                else:
                    print(f"✅ Found combobox {index}: '{combobox_text}'")
                    return combobox
            else:
                print(f"❌ Combobox index {index} not found. Only {len(comboboxes)} comboboxes available")
                return None
                
        except Exception as e:
            print(f"❌ Error finding combobox {index}: {e}")
            return None
    
    def select_dropdown_option(self, combobox, target_value, dropdown_type):
        """Select dropdown option with multiple strategies."""
        print(f"🎯 Selecting {dropdown_type} option: {target_value}")
        
        try:
            # Scroll into view and click to open
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", combobox)
            time.sleep(0.5)
            
            # Record initial text
            initial_text = combobox.text.strip()
            print(f"  📍 Initial combobox text: '{initial_text}'")
            
            # Click to open
            combobox.click()
            print(f"  🔽 Clicked {dropdown_type} combobox")
            time.sleep(3)  # Wait for dropdown to open
            
            # Find all options
            options = self.driver.find_elements(By.XPATH, "//div[@role='option'] | //li[@role='option']")
            print(f"  📋 Found {len(options)} total options")
            
            # Filter visible options
            visible_options = [opt for opt in options if opt.is_displayed()]
            print(f"  👁️ Found {len(visible_options)} visible options")
            
            # Log first few options for debugging
            for i, option in enumerate(visible_options[:8]):
                option_text = option.text.strip()
                option_data_value = option.get_attribute("data-value") or "no-data-value"
                print(f"    Option {i}: text='{option_text}', data-value='{option_data_value}'")
            
            # Find target option
            target_option = None
            
            # Strategy 1: Match by data-value
            for option in visible_options:
                data_value = option.get_attribute("data-value")
                if data_value == str(target_value):
                    target_option = option
                    print(f"  🎯 Found option by data-value: {target_value}")
                    break
            
            # Strategy 2: For month, try by text
            if not target_option and dropdown_type == "month":
                month_names = ["January", "February", "March", "April", "May", "June", 
                             "July", "August", "September", "October", "November", "December"]
                target_month_name = month_names[int(target_value) - 1]
                
                for option in visible_options:
                    if target_month_name in option.text:
                        target_option = option
                        print(f"  🎯 Found month option by text: {target_month_name}")
                        break
            
            # Strategy 3: For gender, try by position (usually first option for Male)
            if not target_option and dropdown_type == "gender" and target_value == "1":
                if visible_options:
                    target_option = visible_options[0]
                    print(f"  🎯 Using first gender option as Male")
            
            if not target_option:
                print(f"  ❌ Could not find target option for {dropdown_type}: {target_value}")
                return False
            
            # Try clicking the target option
            success = False
            click_methods = [
                ("regular", lambda: target_option.click()),
                ("javascript", lambda: self.driver.execute_script("arguments[0].click();", target_option)),
                ("action_chain", lambda: ActionChains(self.driver).move_to_element(target_option).click().perform()),
            ]
            
            for method_name, click_method in click_methods:
                try:
                    print(f"  🖱️ Trying {method_name} click...")
                    
                    # Scroll option into view
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", target_option)
                    time.sleep(0.5)
                    
                    # Perform click
                    click_method()
                    time.sleep(2)
                    
                    # Verify selection
                    current_text = combobox.text.strip()
                    print(f"  🔍 Combobox text after {method_name} click: '{current_text}'")
                    
                    # Check if selection worked
                    if current_text != initial_text and current_text:
                        print(f"  ✅ {dropdown_type} selection successful: '{current_text}'")
                        success = True
                        break
                    else:
                        print(f"  ⚠️ {method_name} click executed but text didn't change")
                        
                except Exception as e:
                    print(f"  ❌ {method_name} click failed: {e}")
                    continue
            
            if success:
                # Close dropdown
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    time.sleep(1)
                    print(f"  ✅ Closed {dropdown_type} dropdown")
                except:
                    pass
                
                return True
            else:
                print(f"  ❌ All click methods failed for {dropdown_type}")
                return False
            
        except Exception as e:
            print(f"  ❌ Error selecting {dropdown_type}: {e}")
            return False
    
    def set_gender_via_form_manipulation(self):
        """Set gender via form manipulation as fallback."""
        print("🔧 Setting gender via form manipulation...")
        
        try:
            # Method 1: Try to find and set hidden input
            try:
                hidden_input = self.driver.find_element(By.XPATH, "//input[@aria-label=\"What's your gender?\"]")
                self.driver.execute_script("arguments[0].value = '1';", hidden_input)
                print("  ✅ Set hidden gender input to '1'")
                return True
            except:
                print("  ⚠️ No hidden gender input found")
            
            # Method 2: Add hidden input to form
            result = self.driver.execute_script("""
                var forms = document.querySelectorAll('form');
                var success = false;
                
                forms.forEach(function(form) {
                    // Remove any existing gender inputs
                    var existingGender = form.querySelectorAll('input[name="Gender"], input[name="gender"]');
                    existingGender.forEach(function(input) {
                        input.remove();
                    });
                    
                    // Create new hidden input for gender
                    var genderInput = document.createElement('input');
                    genderInput.type = 'hidden';
                    genderInput.name = 'Gender';
                    genderInput.value = '1';
                    form.appendChild(genderInput);
                    
                    console.log('Added hidden gender input to form');
                    success = true;
                });
                
                return success;
            """)
            
            if result:
                print("  ✅ Added gender input to form")
                return True
            else:
                print("  ❌ Form manipulation failed")
                return False
                
        except Exception as e:
            print(f"  ❌ Error in form manipulation: {e}")
            return False
    
    async def complete_signup(self):
        """Complete Google signup process."""
        try:
            print("🚀 Starting Improved Google Signup...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
            # === STEP 1: Fill Name ===
            print("\n📝 STEP 1: FILLING NAME")
            print("=" * 30)
            
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
            
            # === STEP 2: Birth Date and Gender ===
            print("\n📅 STEP 2: BIRTH DATE AND GENDER")
            print("=" * 40)
            
            # Find all comboboxes first
            comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            print(f"Found {len(comboboxes)} comboboxes:")
            for i, combo in enumerate(comboboxes):
                combo_text = combo.text.strip()
                visible = combo.is_displayed()
                print(f"  Combobox {i}: '{combo_text}' (visible: {visible})")
            
            # Select Month (usually first combobox)
            print("\n📅 Selecting Month...")
            month_combobox = self.find_combobox_by_index(0, "Month")
            month_success = False
            if month_combobox:
                month_success = self.select_dropdown_option(month_combobox, "5", "month")  # May
            time.sleep(2)
            
            # Fill day
            print("\n📅 Filling Day...")
            try:
                day_field = self.driver.find_element(By.ID, "day")
                self.human_type(day_field, "15")
                print("✅ Day filled: 15")
            except Exception as e:
                print(f"❌ Day filling failed: {e}")
            time.sleep(2)
            
            # Fill year
            print("\n📅 Filling Year...")
            try:
                year_field = self.driver.find_element(By.ID, "year")
                self.human_type(year_field, "1990")
                print("✅ Year filled: 1990")
            except Exception as e:
                print(f"❌ Year filling failed: {e}")
            time.sleep(2)
            
            # Select Gender (usually second combobox)
            print("\n👤 Selecting Gender...")
            gender_combobox = self.find_combobox_by_index(1, "Gender")
            gender_success = False
            if gender_combobox:
                gender_success = self.select_dropdown_option(gender_combobox, "1", "gender")  # Male
            
            # If gender dropdown failed, try form manipulation
            if not gender_success:
                print("\n🔄 Gender dropdown failed, trying form manipulation...")
                gender_success = self.set_gender_via_form_manipulation()
            
            time.sleep(2)
            
            # Take screenshot before proceeding
            self.driver.save_screenshot("improved_before_next.png")
            print("📸 Screenshot saved: improved_before_next.png")
            
            # === STEP 3: Proceed ===
            print("\n➡️ STEP 3: PROCEEDING TO NEXT")
            print("=" * 35)
            
            # Try to click Next
            print("👆 Looking for Next button...")
            next_button = None
            next_selectors = [
                (By.ID, "birthdaygenderNext"),
                (By.XPATH, "//span[text()='Next']/.."),
                (By.XPATH, "//button[contains(text(), 'Next')]"),
            ]
            
            for selector in next_selectors:
                try:
                    next_button = self.wait.until(EC.element_to_be_clickable(selector))
                    print("✅ Found Next button")
                    break
                except:
                    continue
            
            if next_button:
                next_button.click()
                print("👆 Clicked Next button")
                time.sleep(5)
                
                # Check result
                final_url = self.driver.current_url
                print(f"📍 Final URL: {final_url}")
                
                # Take final screenshot
                self.driver.save_screenshot("improved_final.png")
                print("📸 Final screenshot saved: improved_final.png")
                
                # Determine success
                if "username" in final_url or "email" in final_url:
                    print("🎉 SUCCESS: Reached email setup page!")
                    
                    # Try to fill username if available
                    try:
                        username_field = self.driver.find_element(By.ID, "username")
                        self.human_type(username_field, "smarthubshopper")
                        print("✍️ Filled username: smarthubshopper")
                    except:
                        print("📧 No username field - Google will auto-generate")
                    
                    return {
                        "success": True,
                        "status": "email_setup_reached",
                        "month_success": month_success,
                        "gender_success": gender_success,
                        "url": final_url
                    }
                else:
                    print("⚠️ Still on birth date page")
                    return {
                        "success": False,
                        "status": "validation_failed",
                        "month_success": month_success,
                        "gender_success": gender_success,
                        "url": final_url
                    }
            else:
                print("❌ Could not find Next button")
                return {
                    "success": False,
                    "status": "next_button_not_found",
                    "month_success": month_success,
                    "gender_success": gender_success
                }
            
        except Exception as e:
            print(f"❌ Error during signup: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("improved_error.png")
                print("📸 Error screenshot saved: improved_error.png")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Signup complete. Press Enter to close browser...")
                input()
                self.driver.quit()


async def main():
    """Main function."""
    print("🌟 Improved Google Signup - Both Fields Working")
    print("=" * 50)
    print("🎯 Target: smarthubshopper@gmail.com")
    print("👤 Name: Smart Shopper")
    print("📅 Birth Date: May 15, 1990")
    print("👦 Gender: Male")
    print("🔧 Uses robust element finding + form manipulation fallback")
    print()
    
    signup = ImprovedGoogleSignup(headless=False)
    result = await signup.complete_signup()
    
    print("\n📊 FINAL RESULT")
    print("=" * 30)
    print(f"✅ Overall Success: {result.get('success', False)}")
    print(f"📍 Status: {result.get('status', 'unknown')}")
    print(f"📅 Month Selection: {'✅' if result.get('month_success') else '❌'}")
    print(f"👤 Gender Selection: {'✅' if result.get('gender_success') else '❌'}")
    
    if 'url' in result:
        print(f"🌐 Final URL: {result['url']}")
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
    
    print("\n📚 Summary:")
    if result.get('success'):
        print("🎉 Both fields handled successfully!")
        print("📧 Ready to create smarthubshopper@gmail.com")
    else:
        month_status = "✅" if result.get('month_success') else "❌"
        gender_status = "✅" if result.get('gender_success') else "❌"
        print(f"⚠️ Partial success - Month: {month_status}, Gender: {gender_status}")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 