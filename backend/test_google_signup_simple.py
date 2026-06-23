#!/usr/bin/env python3
"""
Simple Google signup test script.
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
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
import time
import random


class SimpleGoogleSignupTest:
    """Simple Google signup test class."""
    
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
            # Try to install ChromeDriver automatically
            print("📥 Installing/updating ChromeDriver...")
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"⚠️ ChromeDriver auto-install failed: {e}")
            print("🔄 Trying with system ChromeDriver...")
            # Fallback to system ChromeDriver
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
    
    async def test_google_signup(self, signup_data):
        """Test Google signup process."""
        try:
            print("🚀 Starting Google signup test...")
            self.setup_driver()
            
            wait = WebDriverWait(self.driver, 20) # Increased wait time
            
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            
            print("✍️ Filling first and last name...")
            first_name_field = wait.until(EC.element_to_be_clickable((By.ID, "firstName")))
            self.human_type(first_name_field, signup_data['first_name'])
            
            last_name_field = wait.until(EC.element_to_be_clickable((By.ID, "lastName")))
            self.human_type(last_name_field, signup_data['last_name'])
            
            print("👆 Clicking Next...")
            next_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Next']]")))
            next_button.click()
            
            # --- BIRTH DATE AND GENDER PAGE ---
            print("\n📅 Waiting for birth date and gender page...")
            time.sleep(5)  # Give page time to load properly
            
            # Fill Month using the working aria-controls approach
            print("📅 Filling month using aria-controls approach...")
            try:
                # Find the month combobox
                month_combobox = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='combobox' and contains(text(), 'Month')]")))
                print(f"  📍 Found month combobox: '{month_combobox.text.strip()}'")
                
                # Get aria-controls attribute  
                aria_controls = month_combobox.get_attribute('aria-controls')
                print(f"  🔗 aria-controls: {aria_controls}")
                
                # Scroll into view and click to open
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", month_combobox)
                time.sleep(0.5)
                month_combobox.click()
                print("  🔽 Clicked month combobox")
                time.sleep(2)
                
                # Find the controlled listbox
                try:
                    if aria_controls:
                        listbox = self.driver.find_element(By.ID, aria_controls)
                        print(f"  ✅ Found controlled listbox with ID: {aria_controls}")
                    else:
                        listbox = self.driver.find_element(By.XPATH, "//div[@role='listbox']")
                        print("  ✅ Found listbox by role")
                except:
                    print("  ❌ Could not find listbox")
                    return
                
                # Find options within the listbox
                options = listbox.find_elements(By.XPATH, ".//div[@role='option'] | .//li[@role='option']")
                print(f"  📋 Found {len(options)} options in listbox")
                
                # Find target option by data-value
                target_option = None
                for option in options:
                    data_value = option.get_attribute("data-value")
                    if data_value == signup_data['birth_month_value']:
                        target_option = option
                        print(f"  🎯 Found target month option by data-value: {signup_data['birth_month_value']}")
                        break
                
                if target_option:
                    # Click the target option
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", target_option)
                    time.sleep(0.5)
                    target_option.click()
                    time.sleep(1)
                    print(f"  ✅ Selected month: {signup_data['birth_month']}")
                else:
                    print(f"  ❌ Could not find month option with data-value: {signup_data['birth_month_value']}")
                    
            except Exception as e:
                print(f"  ❌ Error selecting month: {e}")

            # Fill Day
            print("📅 Filling day...")
            day_field = wait.until(EC.element_to_be_clickable((By.ID, "day")))
            self.human_type(day_field, signup_data['birth_day'])

            # Fill Year
            print("📅 Filling year...")
            year_field = wait.until(EC.element_to_be_clickable((By.ID, "year")))
            self.human_type(year_field, signup_data['birth_year'])

            # Fill Gender - using coordinate-based click as requested
            print("\n🚻 Filling gender using coordinate-based clicks...")
            gender_dropdown = wait.until(EC.element_to_be_clickable((By.ID, "gender")))
            
            # Get the coordinates of the dropdown element (down arrow area)
            print("   📍 Getting coordinates of gender dropdown...")
            dropdown_location = gender_dropdown.location
            dropdown_size = gender_dropdown.size
            
            # Calculate click coordinates (center-right of the dropdown where arrow usually is)
            dropdown_x = dropdown_location['x'] + dropdown_size['width'] - 20  # 20px from right edge
            dropdown_y = dropdown_location['y'] + dropdown_size['height'] // 2  # Center vertically
            
            print(f"   🎯 Dropdown coordinates: x={dropdown_x}, y={dropdown_y}")
            print("   🔽 Clicking gender dropdown arrow at coordinates...")
            
            # Click at the specific coordinates
            actions = ActionChains(self.driver)
            actions.move_by_offset(dropdown_x, dropdown_y).click().perform()
            time.sleep(1)  # Wait 1 second as requested
            
            # Reset mouse position to avoid issues
            actions.move_by_offset(-dropdown_x, -dropdown_y).perform()

            print("   👨 Finding 'Male' option coordinates...")
            # Wait longer for dropdown animation/rendering
            print("   ⏳ Waiting for dropdown options to become visible...")
            time.sleep(3)
            
            # Look for Male option with multiple strategies
            male_option = None
            
            # Strategy 1: Try to find and use data-value="1" even if not visible
            print("   🎯 Strategy 1: Looking for data-value='1' option...")
            data_value_1_options = self.driver.find_elements(By.XPATH, "//div[@role='option' and @data-value='1']")
            if data_value_1_options:
                male_option = data_value_1_options[0]  # Use first one found
                print(f"   ✅ Found option with data-value='1' (visible={male_option.is_displayed()})")
            else:
                print("   ❌ No option with data-value='1' found")
            
            # Strategy 2: If still no option, look for any option with "Male" text
            if not male_option:
                print("   🎯 Strategy 2: Looking for 'Male' text...")
                male_text_options = self.driver.find_elements(By.XPATH, "//div[@role='option' and contains(text(), 'Male')]")
                if male_text_options:
                    male_option = male_text_options[0]
                    print("   ✅ Found option with 'Male' text")
                else:
                    print("   ❌ No option with 'Male' text found")
            
            # Strategy 3: Force click on the first option (often Male in gender dropdowns)
            if not male_option:
                print("   🎯 Strategy 3: Using first gender option as fallback...")
                all_gender_options = self.driver.find_elements(By.XPATH, "//div[@role='option' and @data-value]")
                
                # Filter to likely gender options (data-value 1-4)
                gender_candidates = []
                for opt in all_gender_options:
                    data_val = opt.get_attribute("data-value")
                    if data_val and data_val.isdigit() and int(data_val) <= 4:
                        gender_candidates.append(opt)
                
                print(f"   Found {len(gender_candidates)} gender candidates")
                
                if gender_candidates:
                    male_option = gender_candidates[0]  # Use first one (typically Male)
                    data_val = male_option.get_attribute("data-value")
                    print(f"   ✅ Using first gender candidate with data-value='{data_val}'")
                else:
                    print("   ❌ No gender candidates found")
            
            # Final debug if still no option
            if not male_option:
                print("   🔍 Final debug: All option details...")
                all_options = self.driver.find_elements(By.XPATH, "//div[@role='option']")[:5]  # First 5 only
                for i, option in enumerate(all_options):
                    try:
                        text = option.text.strip()
                        data_value = option.get_attribute("data-value")
                        visible = option.is_displayed()
                        enabled = option.is_enabled()
                        location = option.location
                        print(f"     Option {i}: text='{text}', data-value='{data_value}', visible={visible}, enabled={enabled}, location={location}")
                    except Exception as e:
                        print(f"     Option {i}: Error getting details - {e}")
                
                print("   ❌ Still no suitable Male option found")
                return

            # Get coordinates of the Male option
            male_location = male_option.location
            male_size = male_option.size
            
            # Calculate click coordinates (center of the Male option)
            male_x = male_location['x'] + male_size['width'] // 2
            male_y = male_location['y'] + male_size['height'] // 2
            
            print(f"   🎯 Male option coordinates: x={male_x}, y={male_y}")
            print("   🖱️ Clicking 'Male' option at coordinates...")
            
            # Click at the Male option coordinates
            actions = ActionChains(self.driver)
            actions.move_by_offset(male_x, male_y).click().perform()
            time.sleep(1)  # Wait another second as requested
            
            # Reset mouse position
            actions.move_by_offset(-male_x, -male_y).perform()

            # Verify selection by checking the text in the dropdown element
            try:
                selected_gender_text = gender_dropdown.text
                if "Male" in selected_gender_text:
                    print("   ✅ Gender 'Male' appears to be selected.")
                else:
                    print(f"   ⚠️ Gender dropdown text is '{selected_gender_text}', expected 'Male'. Selection might have failed.")
            except Exception as e:
                print(f"   ❓ Could not verify gender selection text: {e}")

            print("\n👆 Clicking Next to proceed...")
            # Find the 'Next' button again for this page.
            personal_details_next_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Next']]")))
            self.driver.execute_script("arguments[0].scrollIntoView(true);", personal_details_next_button)
            time.sleep(0.5)
            personal_details_next_button.click()

            print("\n⏳ Waiting for username suggestion page...")
            # Wait for a unique element on the next page, e.g., the email input field
            wait.until(EC.element_to_be_clickable((By.NAME, "Username")))
            print("✅ Successfully navigated to the username selection page!")
            print("✅ Test scenario completed successfully.")

        except Exception as e:
            print(f"❌ An error occurred during the signup test: {e.__class__.__name__}: {e}")
            screenshot_path = os.path.join(os.getcwd(), 'error_screenshot.png')
            try:
                self.driver.save_screenshot(screenshot_path)
                print(f"📸 Screenshot saved to {screenshot_path}")
            except Exception as se:
                print(f"Could not save screenshot: {se}")
        finally:
            if self.driver:
                print("🏁 Test finished. Closing driver.")
                self.driver.quit()


async def main():
    """Main function."""
    signup_data = {
        'first_name': 'Smart',
        'last_name': 'Shopper',
        'birth_month': 'May',
        'birth_month_value': '5',  # data-value for May
        'birth_day': '15',
        'birth_year': '1990',
        'gender': 'Male'
    }
    
    headless_mode = '--headless' in sys.argv
    test = SimpleGoogleSignupTest(headless=headless_mode)
    await test.test_google_signup(signup_data)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 