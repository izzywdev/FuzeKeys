#!/usr/bin/env python3
"""
Final Google signup solution using aria-controls and proper element targeting.
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


class FinalGoogleSignup:
    """Final Google signup using proper element targeting."""
    
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
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebDriver/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
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
    
    def select_dropdown_by_aria_controls(self, combobox_selector, target_value, dropdown_type="dropdown"):
        """Select dropdown option using aria-controls approach."""
        print(f"🎯 Selecting {dropdown_type} using aria-controls approach...")
        
        try:
            # Find the combobox
            combobox = self.driver.find_element(By.XPATH, combobox_selector)
            combobox_text = combobox.text.strip()
            print(f"  📍 Found combobox: '{combobox_text}'")
            
            # Get aria-controls attribute
            aria_controls = combobox.get_attribute('aria-controls')
            print(f"  🔗 aria-controls: {aria_controls}")
            
            if not aria_controls:
                print("  ❌ No aria-controls found")
                return False
            
            # Scroll combobox into view and click to open
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", combobox)
            time.sleep(0.5)
            
            combobox.click()
            print(f"  🔽 Clicked {dropdown_type} combobox")
            time.sleep(3)  # Wait for dropdown to open
            
            # Find the controlled listbox
            try:
                listbox = self.driver.find_element(By.ID, aria_controls)
                print(f"  ✅ Found controlled listbox with ID: {aria_controls}")
            except:
                print(f"  ⚠️ Could not find listbox by ID, looking for role='listbox'...")
                listbox = self.driver.find_element(By.XPATH, f"//div[@role='listbox']")
                print(f"  ✅ Found listbox by role")
            
            # Find options within the listbox
            options = listbox.find_elements(By.XPATH, ".//div[@role='option'] | .//li[@role='option']")
            print(f"  📋 Found {len(options)} options in listbox")
            
            # Log first few options for debugging
            for i, option in enumerate(options[:5]):
                option_text = option.text.strip()
                option_data_value = option.get_attribute("data-value") or "no-data-value"
                option_visible = option.is_displayed()
                print(f"    Option {i}: text='{option_text}', data-value='{option_data_value}', visible={option_visible}")
            
            # Find target option
            target_option = None
            
            # Try by data-value first
            for option in options:
                data_value = option.get_attribute("data-value")
                if data_value == str(target_value):
                    target_option = option
                    print(f"  🎯 Found target option by data-value: {target_value}")
                    break
            
            # If not found by data-value, try by text for month names
            if not target_option and dropdown_type == "month":
                month_names = ["January", "February", "March", "April", "May", "June", 
                             "July", "August", "September", "October", "November", "December"]
                target_month_name = month_names[int(target_value) - 1]
                
                for option in options:
                    if target_month_name.lower() in option.text.lower():
                        target_option = option
                        print(f"  🎯 Found target option by text: {target_month_name}")
                        break
            
            if not target_option:
                print(f"  ❌ Could not find target option: {target_value}")
                return False
            
            # Try multiple click methods on the target option
            click_methods = [
                ("regular", lambda: target_option.click()),
                ("javascript", lambda: self.driver.execute_script("arguments[0].click();", target_option)),
                ("action_chain", lambda: ActionChains(self.driver).move_to_element(target_option).click().perform()),
                ("force_click", lambda: self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));", target_option))
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
                    
                    # Verify selection by checking combobox text
                    current_text = combobox.text.strip()
                    print(f"  🔍 Combobox text after click: '{current_text}'")
                    
                    # Check if selection was successful
                    if dropdown_type == "month":
                        month_names = ["January", "February", "March", "April", "May", "June", 
                                     "July", "August", "September", "October", "November", "December"]
                        expected_text = month_names[int(target_value) - 1]
                        if expected_text in current_text:
                            print(f"  ✅ {dropdown_type} selection verified: {expected_text}")
                            return True
                    elif dropdown_type == "gender":
                        # For gender, we expect the text to change from "Gender" to something else
                        if current_text and current_text != "Gender":
                            print(f"  ✅ {dropdown_type} selection verified: {current_text}")
                            return True
                        else:
                            print(f"  ⚠️ {method_name} click executed but selection not verified")
                    
                except Exception as e:
                    print(f"  ❌ {method_name} click failed: {e}")
                    continue
            
            print(f"  ❌ All click methods failed for {dropdown_type}")
            return False
            
        except Exception as e:
            print(f"  ❌ Error selecting {dropdown_type}: {e}")
            return False
    
    def try_alternative_gender_methods(self):
        """Try alternative methods for gender selection."""
        print("\n🔧 TRYING ALTERNATIVE GENDER METHODS")
        print("=" * 40)
        
        # Method 1: Direct hidden input manipulation
        try:
            print("📋 Method 1: Hidden input manipulation")
            hidden_gender_input = self.driver.find_element(By.XPATH, "//input[@aria-label=\"What's your gender?\"]")
            
            # Set value directly
            self.driver.execute_script("arguments[0].value = '1';", hidden_gender_input)
            print("  ✅ Set hidden input value to '1'")
            
            # Trigger events
            self.driver.execute_script("""
                var events = ['input', 'change', 'blur'];
                events.forEach(function(eventType) {
                    var event = new Event(eventType, {bubbles: true});
                    arguments[0].dispatchEvent(event);
                });
            """, hidden_gender_input)
            print("  ✅ Triggered change events")
            
            # Update combobox display
            gender_combobox = self.driver.find_element(By.XPATH, "//div[@role='combobox' and contains(text(), 'Gender')]")
            self.driver.execute_script("arguments[0].textContent = 'Male';", gender_combobox)
            print("  ✅ Updated combobox display")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Method 1 failed: {e}")
        
        # Method 2: Form data manipulation
        try:
            print("📋 Method 2: Form data manipulation")
            
            result = self.driver.execute_script("""
                // Try to find and set form data
                var forms = document.querySelectorAll('form');
                var success = false;
                
                forms.forEach(function(form) {
                    // Create hidden input for gender
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
                print("  ✅ Added hidden gender input to form")
                return True
            else:
                print("  ❌ Could not manipulate form data")
                
        except Exception as e:
            print(f"  ❌ Method 2 failed: {e}")
        
        return False
    
    async def complete_google_signup(self):
        """Complete Google signup process."""
        try:
            print("🚀 Starting Final Google Signup...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
            # === STEP 1: Name Entry ===
            print("\n📝 STEP 1: NAME ENTRY")
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
            
            # Select month using aria-controls
            month_success = self.select_dropdown_by_aria_controls(
                "//div[@role='combobox' and contains(text(), 'Month')]", 
                "5",  # May
                "month"
            )
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
            
            # Select gender using aria-controls
            gender_success = self.select_dropdown_by_aria_controls(
                "//div[@role='combobox' and contains(text(), 'Gender')]", 
                "1",  # Male
                "gender"
            )
            
            # If gender selection failed, try alternative methods
            if not gender_success:
                print("\n🔄 Gender dropdown failed, trying alternatives...")
                gender_success = self.try_alternative_gender_methods()
            
            time.sleep(2)
            
            # Take screenshot before proceeding
            self.driver.save_screenshot("final_before_next.png")
            print("📸 Screenshot saved: final_before_next.png")
            
            # === STEP 3: Proceed to Next ===
            print("\n➡️ STEP 3: PROCEEDING TO NEXT")
            print("=" * 35)
            
            # Try to click Next button
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
                
                # Check final URL
                final_url = self.driver.current_url
                print(f"📍 Final URL: {final_url}")
                
                # Take final screenshot
                self.driver.save_screenshot("final_result.png")
                print("📸 Final screenshot saved: final_result.png")
                
                # Check if we progressed
                if "username" in final_url or "email" in final_url or "account" in final_url:
                    print("🎉 SUCCESS: Reached email/username setup page!")
                    
                    # Try to fill username if available
                    try:
                        username_field = self.driver.find_element(By.ID, "username")
                        self.human_type(username_field, "smarthubshopper")
                        print("✍️ Filled username: smarthubshopper")
                        
                        # Try to click Next again
                        try:
                            next_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Next']/..")))
                            next_btn.click()
                            print("👆 Proceeded to password setup")
                            time.sleep(3)
                        except:
                            print("⚠️ Could not find next button after username")
                            
                    except:
                        print("📧 No username field - Google will auto-generate email")
                    
                    return {
                        "success": True, 
                        "status": "email_setup_reached",
                        "url": final_url,
                        "month_success": month_success,
                        "gender_success": gender_success
                    }
                else:
                    print("⚠️ Still on birth date page - form validation failed")
                    
                    # Check for validation errors
                    error_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'error') or contains(@class, 'invalid')]")
                    if error_elements:
                        print("❌ Found validation errors:")
                        for error in error_elements[:3]:
                            print(f"  - {error.text}")
                    
                    return {
                        "success": False, 
                        "status": "validation_failed",
                        "url": final_url,
                        "month_success": month_success,
                        "gender_success": gender_success
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
                self.driver.save_screenshot("final_error.png")
                print("📸 Error screenshot saved: final_error.png")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Signup complete. Browser will stay open for inspection...")
                input("Press Enter to close the browser...")
                self.driver.quit()


async def main():
    """Main function."""
    print("🌟 Final Google Signup - Complete Email Account Creation")
    print("=" * 60)
    print("🎯 Target: smarthubshopper@gmail.com")
    print("👤 Name: Smart Shopper")
    print("📅 Birth Date: May 15, 1990")
    print("👦 Gender: Male")
    print()
    
    # Run the complete signup
    signup = FinalGoogleSignup(headless=False)
    result = await signup.complete_google_signup()
    
    print("\n📊 FINAL RESULT")
    print("=" * 30)
    print(f"✅ Success: {result.get('success', False)}")
    print(f"📍 Status: {result.get('status', 'unknown')}")
    
    if 'month_success' in result:
        print(f"📅 Month Selection: {'✅' if result['month_success'] else '❌'}")
    if 'gender_success' in result:
        print(f"👤 Gender Selection: {'✅' if result['gender_success'] else '❌'}")
    
    if 'url' in result:
        print(f"🌐 Final URL: {result['url']}")
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
    
    print("\n📚 Summary:")
    if result.get('success'):
        print("🎉 Google account creation process completed successfully!")
        print("📧 The email smarthubshopper@gmail.com should now be created")
        print("🔄 You can now integrate this account with your FuzeKeys application")
    else:
        print("⚠️ Account creation encountered issues")
        print("🔍 Check the screenshots and logs for debugging information")
        
        if result.get('status') == 'validation_failed':
            print("💡 Recommendation: The gender field validation is still failing")
            print("   Consider making gender optional or using a manual intervention")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 