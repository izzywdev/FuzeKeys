#!/usr/bin/env python3
"""
Diagnostic script to understand Google form structure.
"""

import asyncio
import sys
import os
from datetime import date
import json

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import only the necessary modules
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time


class GoogleFormDebugger:
    """Debug Google form structure."""
    
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
    
    def human_type(self, element, text):
        """Type like a human."""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(0.05)
    
    def capture_form_structure(self, page_name):
        """Capture detailed form structure."""
        print(f"\n🔍 CAPTURING {page_name.upper()} FORM STRUCTURE")
        print("=" * 60)
        
        # Save full page source
        page_source = self.driver.page_source
        with open(f"{page_name}_page_source.html", "w", encoding="utf-8") as f:
            f.write(page_source)
        print(f"💾 Saved full page source to {page_name}_page_source.html")
        
        # Extract specific form data via JavaScript
        form_data = self.driver.execute_script("""
            var formData = {
                'url': window.location.href,
                'title': document.title,
                'comboboxes': [],
                'inputs': [],
                'hiddenInputs': [],
                'formElements': []
            };
            
            // Get all comboboxes with detailed info
            var comboboxes = document.querySelectorAll('[role="combobox"]');
            comboboxes.forEach(function(combo, index) {
                var rect = combo.getBoundingClientRect();
                formData.comboboxes.push({
                    'index': index,
                    'text': combo.textContent.trim(),
                    'id': combo.id || '',
                    'className': combo.className || '',
                    'ariaLabel': combo.getAttribute('aria-label') || '',
                    'ariaExpanded': combo.getAttribute('aria-expanded') || '',
                    'ariaHaspopup': combo.getAttribute('aria-haspopup') || '',
                    'visible': rect.width > 0 && rect.height > 0,
                    'position': {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    'outerHTML': combo.outerHTML.substring(0, 500)
                });
            });
            
            // Get all inputs
            var inputs = document.querySelectorAll('input');
            inputs.forEach(function(input, index) {
                var rect = input.getBoundingClientRect();
                formData.inputs.push({
                    'index': index,
                    'type': input.type,
                    'name': input.name || '',
                    'id': input.id || '',
                    'value': input.value || '',
                    'placeholder': input.placeholder || '',
                    'ariaLabel': input.getAttribute('aria-label') || '',
                    'visible': rect.width > 0 && rect.height > 0,
                    'position': {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                });
                
                if (input.type === 'hidden') {
                    formData.hiddenInputs.push({
                        'name': input.name || '',
                        'value': input.value || '',
                        'id': input.id || ''
                    });
                }
            });
            
            // Get form elements
            var forms = document.querySelectorAll('form');
            forms.forEach(function(form, index) {
                formData.formElements.push({
                    'index': index,
                    'action': form.action || '',
                    'method': form.method || '',
                    'id': form.id || '',
                    'className': form.className || ''
                });
            });
            
            return formData;
        """)
        
        # Save form data as JSON
        with open(f"{page_name}_form_data.json", "w", encoding="utf-8") as f:
            json.dump(form_data, f, indent=2)
        print(f"💾 Saved form data to {page_name}_form_data.json")
        
        # Print summary
        print(f"📊 Found {len(form_data['comboboxes'])} comboboxes:")
        for combo in form_data['comboboxes']:
            print(f"  - '{combo['text']}' (visible: {combo['visible']}, aria-label: '{combo['ariaLabel']}')")
        
        print(f"📊 Found {len(form_data['inputs'])} inputs:")
        for inp in form_data['inputs'][:10]:  # Show first 10
            visibility = "visible" if inp['visible'] else "hidden"
            print(f"  - {inp['type']} '{inp['id']}' (name: '{inp['name']}', {visibility})")
        
        print(f"📊 Found {len(form_data['hiddenInputs'])} hidden inputs:")
        for hidden in form_data['hiddenInputs'][:5]:  # Show first 5
            print(f"  - '{hidden['name']}' = '{hidden['value'][:50]}...'")
        
        return form_data
    
    def try_alternative_gender_approaches(self):
        """Try alternative approaches to set gender."""
        print("\n🔧 TRYING ALTERNATIVE GENDER APPROACHES")
        print("=" * 50)
        
        approaches = [
            self.approach_1_hidden_input,
            self.approach_2_form_submission,
            self.approach_3_aria_controls,
            self.approach_4_parent_manipulation
        ]
        
        for i, approach in enumerate(approaches, 1):
            print(f"\n📋 Approach {i}: {approach.__name__}")
            try:
                result = approach()
                if result:
                    print(f"✅ Approach {i} succeeded!")
                    return True
                else:
                    print(f"❌ Approach {i} failed")
            except Exception as e:
                print(f"❌ Approach {i} error: {e}")
        
        return False
    
    def approach_1_hidden_input(self):
        """Try to set gender via hidden input."""
        try:
            # Look for gender-related hidden inputs
            hidden_inputs = self.driver.find_elements(By.XPATH, "//input[@type='hidden' and (contains(@name, 'gender') or contains(@name, 'Gender'))]")
            
            if hidden_inputs:
                for hidden in hidden_inputs:
                    name = hidden.get_attribute('name')
                    print(f"  Found hidden input: {name}")
                    
                    # Try to set value
                    self.driver.execute_script("arguments[0].value = '1';", hidden)
                    print(f"  Set {name} to '1'")
                
                return True
            else:
                print("  No gender-related hidden inputs found")
                return False
                
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    def approach_2_form_submission(self):
        """Try to set gender via form data manipulation."""
        try:
            # Get the form and try to set gender data directly
            result = self.driver.execute_script("""
                // Find any form elements that might contain gender
                var forms = document.querySelectorAll('form');
                var success = false;
                
                forms.forEach(function(form) {
                    var formData = new FormData(form);
                    
                    // Try to set gender in form data
                    formData.set('Gender', '1');
                    formData.set('gender', '1');
                    formData.set('birthdaygender', '1');
                    
                    console.log('Set gender data in form');
                    success = true;
                });
                
                return success;
            """)
            
            if result:
                print("  Set gender data in form")
                return True
            else:
                print("  No forms found or manipulation failed")
                return False
                
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    def approach_3_aria_controls(self):
        """Try to find gender dropdown via aria-controls."""
        try:
            # Find gender combobox and check its aria-controls
            gender_combobox = self.driver.find_element(By.XPATH, "//div[@role='combobox' and contains(text(), 'Gender')]")
            aria_controls = gender_combobox.get_attribute('aria-controls')
            
            if aria_controls:
                print(f"  Gender combobox controls: {aria_controls}")
                
                # Try to find the controlled element
                controlled_element = self.driver.find_element(By.ID, aria_controls)
                
                if controlled_element:
                    print("  Found controlled element")
                    
                    # Look for options within it
                    options = controlled_element.find_elements(By.XPATH, ".//div[@role='option'] | .//li[@role='option']")
                    
                    for option in options:
                        data_value = option.get_attribute('data-value')
                        if data_value == '1':
                            # Force click
                            self.driver.execute_script("arguments[0].click();", option)
                            print(f"  Clicked option with data-value=1")
                            return True
                
            print("  No aria-controls found or controlled element not accessible")
            return False
            
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    def approach_4_parent_manipulation(self):
        """Try to manipulate the parent container."""
        try:
            # Find gender combobox and its parent
            gender_combobox = self.driver.find_element(By.XPATH, "//div[@role='combobox' and contains(text(), 'Gender')]")
            parent = gender_combobox.find_element(By.XPATH, "./..")
            
            # Try to find any inputs within the parent
            inputs = parent.find_elements(By.TAG_NAME, "input")
            
            for inp in inputs:
                inp_type = inp.get_attribute('type')
                inp_name = inp.get_attribute('name') or ''
                
                if inp_type in ['hidden', 'text'] and 'gender' in inp_name.lower():
                    print(f"  Found input in parent: {inp_type} {inp_name}")
                    
                    # Try to set its value
                    self.driver.execute_script("arguments[0].value = '1';", inp)
                    
                    # Trigger events
                    self.driver.execute_script("""
                        var events = ['input', 'change', 'blur'];
                        events.forEach(function(eventType) {
                            var event = new Event(eventType, {bubbles: true});
                            arguments[0].dispatchEvent(event);
                        });
                    """, inp)
                    
                    print(f"  Set {inp_name} and triggered events")
                    return True
            
            print("  No suitable inputs found in parent")
            return False
            
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    def verify_form_values(self):
        """Verify what values are actually set in the form."""
        print("\n✅ VERIFYING FORM VALUES")
        print("=" * 30)
        
        # Check all form values
        form_values = self.driver.execute_script("""
            var values = {};
            
            // Check all inputs
            var inputs = document.querySelectorAll('input');
            inputs.forEach(function(input) {
                if (input.name) {
                    values[input.name] = input.value;
                }
            });
            
            // Check combobox states
            var comboboxes = document.querySelectorAll('[role="combobox"]');
            values['combobox_states'] = [];
            comboboxes.forEach(function(combo, index) {
                values['combobox_states'].push({
                    'index': index,
                    'text': combo.textContent.trim(),
                    'aria_expanded': combo.getAttribute('aria-expanded')
                });
            });
            
            return values;
        """)
        
        print("📊 Current form values:")
        for key, value in form_values.items():
            if key != 'combobox_states':
                if value:
                    print(f"  {key}: {value}")
        
        print("📊 Combobox states:")
        for combo in form_values.get('combobox_states', []):
            print(f"  Combobox {combo['index']}: '{combo['text']}' (expanded: {combo['aria_expanded']})")
        
        return form_values
    
    async def debug_google_form(self):
        """Main debug function."""
        try:
            print("🚀 Starting Google Form Debug...")
            self.setup_driver()
            
            # Navigate to Google signup page
            print("📱 Navigating to Google signup page...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)
            
            # Capture initial form structure
            self.capture_form_structure("initial")
            
            # Fill first name
            print("✍️ Filling first name...")
            first_name_field = self.wait.until(EC.element_to_be_clickable((By.ID, "firstName")))
            self.human_type(first_name_field, "Smart")
            time.sleep(1)
            
            # Fill last name
            print("✍️ Filling last name...")
            last_name_field = self.wait.until(EC.element_to_be_clickable((By.ID, "lastName")))
            self.human_type(last_name_field, "Shopper")
            time.sleep(1)
            
            # Click Next
            print("👆 Clicking Next...")
            next_button = self.wait.until(EC.element_to_be_clickable((By.ID, "collectNameNext")))
            next_button.click()
            time.sleep(5)
            
            # Capture birth date form structure
            birth_data = self.capture_form_structure("birth_date")
            
            # Fill month (working approach)
            print("📅 Filling month...")
            month_combobox = self.driver.find_element(By.XPATH, "//div[@role='combobox' and contains(text(), 'Month')]")
            month_combobox.click()
            time.sleep(2)
            
            month_options = self.driver.find_elements(By.XPATH, "//div[@role='option']")
            for option in month_options:
                if option.get_attribute("data-value") == "5":
                    option.click()
                    break
            time.sleep(2)
            
            # Fill day and year
            print("📅 Filling day and year...")
            day_field = self.driver.find_element(By.ID, "day")
            self.human_type(day_field, "15")
            
            year_field = self.driver.find_element(By.ID, "year")
            self.human_type(year_field, "1990")
            time.sleep(2)
            
            # Capture form structure after filling basic fields
            self.capture_form_structure("after_basic_fields")
            
            # Try alternative gender approaches
            self.try_alternative_gender_approaches()
            
            # Verify final form state
            final_values = self.verify_form_values()
            
            # Take final screenshot
            self.driver.save_screenshot("debug_final_state.png")
            print("📸 Final screenshot saved: debug_final_state.png")
            
            # Try to proceed anyway
            print("👆 Trying to proceed to next step...")
            try:
                next_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Next']/..")))
                next_button.click()
                time.sleep(5)
                
                final_url = self.driver.current_url
                print(f"📍 Final URL: {final_url}")
                
                if final_url != birth_data['url']:
                    print("✅ Successfully proceeded to next page!")
                    return {"success": True, "final_url": final_url}
                else:
                    print("⚠️ Still on birth date page - form validation likely failed")
                    return {"success": False, "reason": "form_validation_failed"}
                    
            except Exception as e:
                print(f"❌ Could not proceed: {e}")
                return {"success": False, "reason": "cannot_proceed"}
            
        except Exception as e:
            print(f"❌ Error during debug: {str(e)}")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                print("\n🧹 Debug complete. Browser will stay open for inspection...")
                input("Press Enter to close the browser...")
                self.driver.quit()


async def main():
    """Main function."""
    print("🌟 Google Form Debug Session")
    print("=" * 50)
    print("🔍 This will capture detailed form structure and try alternative approaches")
    print("💾 HTML source and JSON data will be saved for analysis")
    print()
    
    debugger = GoogleFormDebugger()
    result = await debugger.debug_google_form()
    
    print("\n📊 Debug Result:")
    print(f"Success: {result.get('success', False)}")
    if 'final_url' in result:
        print(f"Final URL: {result['final_url']}")
    if 'reason' in result:
        print(f"Reason: {result['reason']}")
    if 'error' in result:
        print(f"Error: {result['error']}")
    
    print("\n📚 Files Created:")
    print("- initial_page_source.html")
    print("- initial_form_data.json")
    print("- birth_date_page_source.html")
    print("- birth_date_form_data.json")
    print("- after_basic_fields_page_source.html")
    print("- after_basic_fields_form_data.json")
    print("- debug_final_state.png")
    
    print("\n🎉 Debug complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Debug interrupted by user.")
    except Exception as e:
        print(f"\n❌ Debug failed: {e}") 