const puppeteer = require('puppeteer');

async function createGoogleAccount() {
    const browser = await puppeteer.launch({ 
        headless: false, // Set to true for headless mode
        slowMo: 100, // Slow down actions by 100ms
        defaultViewport: null,
        args: ['--start-maximized']
    });

    let page;
    try {
        page = await browser.newPage();
        
        console.log("🌐 Navigating to Google accounts...");
        await page.goto('https://accounts.google.com/', {
            waitUntil: 'networkidle2'
        });

        // Look for and click "Create account" link
        console.log("🔍 Looking for 'Create account' link...");
        try {
            // Wait for page to load and look for create account link
            await page.waitForTimeout(2000);
            
            // Try multiple selectors for create account
            const createAccountSelectors = [
                'a[href*="signup"]',
                '[data-action="create"]',
                'button:contains("Create account")',
                'a:contains("Create account")',
                '[role="button"]:contains("Create")'
            ];
            
            let createAccountClicked = false;
            
            // Try to find create account link by text content
            const links = await page.$$('a');
            for (let link of links) {
                const text = await page.evaluate(el => el.textContent, link);
                if (text && (text.toLowerCase().includes('create account') || text.toLowerCase().includes('create'))) {
                    console.log(`Found create account link: "${text}"`);
                    await link.click();
                    createAccountClicked = true;
                    break;
                }
            }
            
            if (!createAccountClicked) {
                // Try buttons too
                const buttons = await page.$$('button');
                for (let button of buttons) {
                    const text = await page.evaluate(el => el.textContent, button);
                    if (text && (text.toLowerCase().includes('create account') || text.toLowerCase().includes('create'))) {
                        console.log(`Found create account button: "${text}"`);
                        await button.click();
                        createAccountClicked = true;
                        break;
                    }
                }
            }
            
            if (createAccountClicked) {
                console.log("✅ Create account clicked, waiting for signup form...");
                await page.waitForTimeout(3000);
            } else {
                console.log("⚠️ Create account link not found, trying direct navigation...");
                await page.goto('https://accounts.google.com/signup/v2/webcreateaccount', {
                    waitUntil: 'networkidle2'
                });
            }
        } catch (error) {
            console.log("⚠️ Error finding create account link:", error.message);
            console.log("🔄 Trying direct signup URL...");
            await page.goto('https://accounts.google.com/signup/v2/webcreateaccount', {
                waitUntil: 'networkidle2'
            });
        }

        // Fill first name
        console.log("✍️ Filling first name...");
        await page.waitForSelector('#firstName', { timeout: 15000 });
        await page.type('#firstName', 'Smart', { delay: 100 });
        await page.waitForTimeout(2000);

        // Fill last name
        console.log("✍️ Filling last name...");
        await page.type('#lastName', 'Shopper', { delay: 100 });
        await page.waitForTimeout(2000);

        // Click Next button
        console.log("▶️ Clicking Next...");
        await page.click('#collectNameNext');
        
        // Wait for birth date page
        console.log("⏳ Waiting for birth date page...");
        await page.waitForSelector('#day', { timeout: 15000 });
        await page.waitForTimeout(2000);

        // Handle Month dropdown - simplified approach
        console.log("📅 Selecting birth month...");
        
        try {
            // Find month dropdown by role and click it
            const monthDropdowns = await page.$$('div[role="combobox"]');
            if (monthDropdowns.length > 0) {
                console.log(`Found ${monthDropdowns.length} combobox elements`);
                
                // Click the first combobox (should be month)
                await monthDropdowns[0].click();
                await page.waitForTimeout(1000);
                
                // Try to select May using keyboard navigation
                console.log("Using keyboard to select May...");
                for (let i = 0; i < 5; i++) {
                    await page.keyboard.press('ArrowDown');
                    await page.waitForTimeout(200);
                }
                await page.keyboard.press('Enter');
                console.log("✅ Month selection attempted");
                await page.waitForTimeout(2000);
            }
        } catch (error) {
            console.log("⚠️ Month selection failed:", error.message);
        }

        // Fill day
        console.log("📅 Filling birth day...");
        await page.click('#day');
        await page.type('#day', '15', { delay: 100 });
        await page.waitForTimeout(2000);

        // Fill year
        console.log("📅 Filling birth year...");
        await page.click('#year');
        await page.type('#year', '1990', { delay: 100 });
        await page.waitForTimeout(2000);

        // Handle Gender dropdown - multiple approaches
        console.log("👤 Selecting gender...");
        
        try {
            // Find all comboboxes and try the second one (gender)
            const allComboboxes = await page.$$('div[role="combobox"]');
            if (allComboboxes.length > 1) {
                console.log("Attempting to click gender dropdown...");
                await allComboboxes[1].click(); // Second combobox should be gender
                await page.waitForTimeout(1000);
                
                // Try to click the first option (Male)
                const options = await page.$$('[data-value="1"]');
                if (options.length > 0) {
                    await options[0].click();
                    console.log("✅ Gender selected via dropdown");
                    await page.waitForTimeout(2000);
                } else {
                    throw new Error("No gender options found");
                }
            } else {
                throw new Error("Gender dropdown not found");
            }
        } catch (error) {
            console.log("⚠️ Standard gender selection failed, trying JavaScript injection...");
            
            // Fallback: JavaScript manipulation
            await page.evaluate(() => {
                // Find the form and add hidden gender input
                const form = document.querySelector('form');
                if (form) {
                    // Remove any existing gender inputs first
                    const existingGender = form.querySelector('input[name="Gender"]');
                    if (existingGender) {
                        existingGender.remove();
                    }
                    
                    const genderInput = document.createElement('input');
                    genderInput.type = 'hidden';
                    genderInput.name = 'Gender';
                    genderInput.value = '1'; // Male
                    form.appendChild(genderInput);
                    
                    // Also try to manipulate the visible combobox
                    const genderComboboxes = document.querySelectorAll('div[role="combobox"]');
                    if (genderComboboxes.length > 1) {
                        const genderCombobox = genderComboboxes[1]; // Second one should be gender
                        const valueDiv = genderCombobox.querySelector('div[data-value=""]');
                        if (valueDiv) {
                            valueDiv.setAttribute('data-value', '1');
                            valueDiv.textContent = 'Male';
                        }
                    }
                    
                    console.log("Gender form manipulation completed");
                    return true;
                }
                return false;
            });
            console.log("✅ Gender set via JavaScript manipulation");
            await page.waitForTimeout(2000);
        }

        // Click Next to proceed
        console.log("▶️ Proceeding to next step...");
        
        // Find and click the Next button
        try {
            await page.waitForSelector('button', { timeout: 5000 });
            const buttons = await page.$$('button');
            
            // Look for Next button by text content
            for (let button of buttons) {
                const text = await page.evaluate(el => el.textContent, button);
                if (text && text.toLowerCase().includes('next')) {
                    await button.click();
                    console.log("✅ Next button clicked");
                    break;
                }
            }
        } catch (error) {
            console.log("⚠️ Next button click failed:", error.message);
        }
        
        // Wait for email selection page
        console.log("📧 Waiting for email setup page...");
        await page.waitForTimeout(5000);
        
        // Try to use the desired email
        const desiredEmail = 'smarthubshopper';
        console.log(`📧 Attempting to use email: ${desiredEmail}@gmail.com`);
        
        try {
            // Look for email input field
            await page.waitForSelector('input[type="text"]', { timeout: 10000 });
            const emailInput = await page.$('input[type="text"]');
            if (emailInput) {
                await emailInput.click();
                await page.type(emailInput, desiredEmail, { delay: 100 });
                await page.waitForTimeout(2000);
                console.log("✅ Email entered");
            }
        } catch (error) {
            console.log("⚠️ Email input failed:", error.message);
        }

        console.log("🎉 Automation completed!");
        console.log("📧 Attempted to set email: smarthubshopper@gmail.com");
        
        // Wait for manual completion
        console.log("⏸️ Pausing for manual review (30 seconds)...");
        await page.waitForTimeout(30000);

    } catch (error) {
        console.error("❌ Error during automation:", error.message);
        
        // Take screenshot for debugging
        try {
            if (page) {
                await page.screenshot({ 
                    path: 'puppeteer_error.png', 
                    fullPage: true 
                });
                console.log("📸 Error screenshot saved as 'puppeteer_error.png'");
            }
        } catch (screenshotError) {
            console.log("Could not take screenshot:", screenshotError.message);
        }
        
    } finally {
        // Keep browser open for manual review
        console.log("🔍 Browser will remain open for manual review...");
        // await browser.close(); // Uncomment to auto-close
    }
}

// Run the automation
createGoogleAccount().catch(console.error); 