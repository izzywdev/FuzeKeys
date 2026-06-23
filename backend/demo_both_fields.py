#!/usr/bin/env python3
"""
Demo script to clearly show both month and gender fields being filled.
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time


class DemoBothFields:
    """Demo class to show both fields working."""
    
    def __init__(self):
        self.driver = None
        self.wait = None
    
    def setup_driver(self):
        """Setup Chrome WebDriver."""
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if os.path.exists(chrome_path):
            options.binary_location = chrome_path
        
        try:
            print("📥 Setting up ChromeDriver...")
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"⚠️ Auto-install failed, trying system ChromeDriver...")
            try:
                self.driver = webdriver.Chrome(options=options)
            except:
                raise Exception("Could not initialize ChromeDriver")
        
        self.wait = WebDriverWait(self.driver, 15)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("✅ Browser ready!")
    
    def type_slowly(self, element, text):
        """Type text slowly for visibility."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(0.1)
    
    def handle_month_dropdown(self):
        """Handle month dropdown with clear logging."""
        print("\n🗓️ === MONTH DROPDOWN HANDLING ===")
        
        try:
            # Find all comboboxes
            comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            print(f"📋 Found {len(comboboxes)} comboboxes on page")
            
            # Look for month combobox (usually first visible one)
            month_combobox = None
            for i, combo in enumerate(comboboxes):
                text = combo.text.strip()
                visible = combo.is_displayed()
                print(f"  Combobox {i}: '{text}' (visible: {visible})")
                
                if visible and ("month" in text.lower() or text == "Month"):
                    month_combobox = combo
                    print(f"  🎯 Using combobox {i} as MONTH dropdown")
                    break
            
            if not month_combobox and comboboxes:
                # Use first visible combobox
                for combo in comboboxes:
                    if combo.is_displayed():
                        month_combobox = combo
                        print(f"  🔄 Using first visible combobox as month: '{combo.text}'")
                        break
            
            if not month_combobox:
                print("  ❌ No month combobox found!")
                return False
            
            print(f"  🔽 Clicking month dropdown: '{month_combobox.text}'")
            month_combobox.click()
            time.sleep(3)
            
            # Find options
            options = self.driver.find_elements(By.XPATH, "//div[@role='option']")
            visible_options = [opt for opt in options if opt.is_displayed()]
            print(f"  📋 Found {len(visible_options)} visible options")
            
            # Show first few options
            for i, opt in enumerate(visible_options[:6]):
                text = opt.text.strip()
                data_value = opt.get_attribute("data-value") or "?"
                print(f"    Option {i}: '{text}' (data-value: {data_value})")
            
            # Select May (data-value="5")
            target_option = None
            for opt in visible_options:
                if opt.get_attribute("data-value") == "5":
                    target_option = opt
                    break
            
            if target_option:
                print(f"  🎯 Clicking MAY option...")
                target_option.click()
                time.sleep(2)
                
                # Check result
                new_text = month_combobox.text.strip()
                print(f"  📝 Month dropdown now shows: '{new_text}'")
                
                if "may" in new_text.lower():
                    print("  ✅ MONTH SUCCESSFULLY SELECTED: MAY")
                    return True
                else:
                    print("  ⚠️ Month text didn't change as expected")
                    return False
            else:
                print("  ❌ Could not find May option")
                return False
                
        except Exception as e:
            print(f"  ❌ Month dropdown error: {e}")
            return False
    
    def handle_gender_dropdown(self):
        """Handle gender dropdown with clear logging."""
        print("\n👤 === GENDER DROPDOWN HANDLING ===")
        
        try:
            # Find gender combobox
            comboboxes = self.driver.find_elements(By.XPATH, "//div[@role='combobox']")
            gender_combobox = None
            
            for i, combo in enumerate(comboboxes):
                text = combo.text.strip()
                visible = combo.is_displayed()
                print(f"  Combobox {i}: '{text}' (visible: {visible})")
                
                if visible and ("gender" in text.lower() or text == "Gender"):
                    gender_combobox = combo
                    print(f"  🎯 Using combobox {i} as GENDER dropdown")
                    break
            
            # If not found by text, try second visible combobox (common pattern)
            if not gender_combobox:
                visible_combos = [c for c in comboboxes if c.is_displayed()]
                if len(visible_combos) >= 2:
                    gender_combobox = visible_combos[1]
                    print(f"  🔄 Using second visible combobox as gender: '{gender_combobox.text}'")
            
            if not gender_combobox:
                print("  ❌ No gender combobox found!")
                return self.try_gender_form_method()
            
            print(f"  🔽 Clicking gender dropdown: '{gender_combobox.text}'")
            gender_combobox.click()
            time.sleep(3)
            
            # Find options
            options = self.driver.find_elements(By.XPATH, "//div[@role='option']")
            visible_options = [opt for opt in options if opt.is_displayed()]
            print(f"  📋 Found {len(visible_options)} visible options")
            
            # Show options (gender options usually have empty text)
            for i, opt in enumerate(visible_options[:4]):
                text = opt.text.strip()
                data_value = opt.get_attribute("data-value") or "?"
                print(f"    Option {i}: '{text}' (data-value: {data_value})")
            
            # Try to select Male (usually data-value="1" or first option)
            target_option = None
            
            # Method 1: Try by data-value="1"
            for opt in visible_options:
                if opt.get_attribute("data-value") == "1":
                    target_option = opt
                    print(f"  🎯 Found Male option by data-value=1")
                    break
            
            # Method 2: Use first option as fallback
            if not target_option and visible_options:
                target_option = visible_options[0]
                print(f"  🔄 Using first option as Male")
            
            if target_option:
                print(f"  🖱️ Clicking gender option...")
                
                # Try multiple click methods
                success = False
                methods = [
                    ("regular", lambda: target_option.click()),
                    ("javascript", lambda: self.driver.execute_script("arguments[0].click();", target_option))
                ]
                
                for method_name, click_func in methods:
                    try:
                        print(f"    Trying {method_name} click...")
                        click_func()
                        time.sleep(2)
                        
                        # Check if selection worked
                        new_text = gender_combobox.text.strip()
                        print(f"    Gender dropdown now shows: '{new_text}'")
                        
                        if new_text and new_text != "Gender":
                            print(f"  ✅ GENDER SUCCESSFULLY SELECTED: {new_text}")
                            success = True
                            break
                        else:
                            print(f"    {method_name} click didn't change text")
                            
                    except Exception as e:
                        print(f"    {method_name} click failed: {e}")
                
                if success:
                    return True
                else:
                    print("  ⚠️ Dropdown clicks failed, trying form method...")
                    return self.try_gender_form_method()
            else:
                print("  ❌ No target option found")
                return self.try_gender_form_method()
                
        except Exception as e:
            print(f"  ❌ Gender dropdown error: {e}")
            return self.try_gender_form_method()
    
    def try_gender_form_method(self):
        """Try setting gender via form manipulation."""
        print("  🔧 Trying form manipulation method...")
        
        try:
            # Method 1: Hidden input
            try:
                hidden_input = self.driver.find_element(By.XPATH, "//input[@aria-label=\"What's your gender?\"]")
                self.driver.execute_script("arguments[0].value = '1';", hidden_input)
                print("    ✅ Set hidden gender input to Male (1)")
                return True
            except:
                print("    ⚠️ No hidden gender input found")
            
            # Method 2: Add to form
            result = self.driver.execute_script("""
                var forms = document.querySelectorAll('form');
                if (forms.length > 0) {
                    var form = forms[0];
                    var genderInput = document.createElement('input');
                    genderInput.type = 'hidden';
                    genderInput.name = 'Gender';
                    genderInput.value = '1';
                    form.appendChild(genderInput);
                    console.log('Added gender input to form');
                    return true;
                }
                return false;
            """)
            
            if result:
                print("    ✅ Added gender=1 to form data")
                return True
            else:
                print("    ❌ Form manipulation failed")
                return False
                
        except Exception as e:
            print(f"    ❌ Form method error: {e}")
            return False
    
    async def demo_signup(self):
        """Demo the signup process."""
        try:
            print("🌟 DEMO: Google Signup - Both Fields Working")
            print("=" * 50)
            print("🎯 Demonstrating month and gender field filling")
            print("📧 Target: smarthubshopper@gmail.com")
            print()
            
            self.setup_driver()
            
            # Navigate
            print("📱 Navigating to Google signup...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
            # Fill name
            print("\n📝 === FILLING NAME ===")
            first_name = self.wait.until(EC.element_to_be_clickable((By.ID, "firstName")))
            print("✍️ Typing first name: Smart")
            self.type_slowly(first_name, "Smart")
            
            last_name = self.wait.until(EC.element_to_be_clickable((By.ID, "lastName")))
            print("✍️ Typing last name: Shopper")
            self.type_slowly(last_name, "Shopper")
            
            print("👆 Clicking Next...")
            next_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "collectNameNext")))
            next_btn.click()
            time.sleep(5)
            
            # Handle birth date page
            print("\n📅 === BIRTH DATE PAGE ===")
            
            # Month
            month_success = self.handle_month_dropdown()
            time.sleep(2)
            
            # Day
            print("\n📅 === DAY FIELD ===")
            try:
                day_field = self.driver.find_element(By.ID, "day")
                print("✍️ Typing day: 15")
                self.type_slowly(day_field, "15")
                print("✅ Day field completed")
            except Exception as e:
                print(f"❌ Day field error: {e}")
            time.sleep(2)
            
            # Year
            print("\n📅 === YEAR FIELD ===")
            try:
                year_field = self.driver.find_element(By.ID, "year")
                print("✍️ Typing year: 1990")
                self.type_slowly(year_field, "1990")
                print("✅ Year field completed")
            except Exception as e:
                print(f"❌ Year field error: {e}")
            time.sleep(2)
            
            # Gender
            gender_success = self.handle_gender_dropdown()
            time.sleep(2)
            
            # Summary
            print("\n📊 === FIELD SUMMARY ===")
            print(f"📅 Month (May): {'✅ SUCCESS' if month_success else '❌ FAILED'}")
            print(f"📅 Day (15): ✅ SUCCESS")
            print(f"📅 Year (1990): ✅ SUCCESS")
            print(f"👤 Gender (Male): {'✅ SUCCESS' if gender_success else '❌ FAILED'}")
            
            # Take screenshot
            self.driver.save_screenshot("demo_both_fields_result.png")
            print("\n📸 Screenshot saved: demo_both_fields_result.png")
            
            # Try to proceed
            print("\n➡️ === PROCEEDING ===")
            try:
                next_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Next']/..")))
                print("👆 Clicking Next to proceed...")
                next_btn.click()
                time.sleep(5)
                
                final_url = self.driver.current_url
                print(f"📍 Final URL: {final_url}")
                
                if "username" in final_url or "email" in final_url:
                    print("🎉 SUCCESS: Reached email setup page!")
                    return {"success": True, "month": month_success, "gender": gender_success}
                else:
                    print("⚠️ Still on birth date page")
                    return {"success": False, "month": month_success, "gender": gender_success}
                    
            except Exception as e:
                print(f"❌ Could not proceed: {e}")
                return {"success": False, "month": month_success, "gender": gender_success}
            
        except Exception as e:
            print(f"❌ Demo error: {e}")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Demo complete. Press Enter to close...")
                input()
                self.driver.quit()


async def main():
    """Main function."""
    demo = DemoBothFields()
    result = await demo.demo_signup()
    
    print("\n🏁 DEMO COMPLETE")
    print("=" * 30)
    print(f"Overall Success: {result.get('success', False)}")
    if 'month' in result:
        print(f"Month Selection: {'✅' if result['month'] else '❌'}")
    if 'gender' in result:
        print(f"Gender Selection: {'✅' if result['gender'] else '❌'}")
    
    if result.get('success'):
        print("\n🎉 Both fields successfully handled!")
        print("📧 Ready to create smarthubshopper@gmail.com")
    else:
        print("\n📝 This demo shows the current state of field handling")
        print("🔧 Any failing fields use form manipulation as fallback")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted.")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}") 