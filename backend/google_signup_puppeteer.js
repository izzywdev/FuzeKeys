const puppeteer = require('puppeteer');

async function createGoogleAccount() {
    const browser = await puppeteer.launch({ 
        headless: false, // Set to true for headless mode
        slowMo: 50, // Slow down actions by 50ms
        defaultViewport: null,
        args: ['--start-maximized']
    });

    let page;
    try {
        page = await browser.newPage();
        
        console.log("🌐 Navigating to Google signup...");
        await page.goto('https://accounts.google.com/signup/v2/webcreateaccount', {
            waitUntil: 'networkidle2'
        });

        // Fill first name
        console.log("✍️ Filling first name...");
        await page.waitForSelector('#firstName', { timeout: 10000 });
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
        await page.waitForSelector('[data-value="1"]', { timeout: 15000 });
        await page.waitForTimeout(2000);

        // Handle Month dropdown with Puppeteer's better control
        console.log("📅 Selecting birth month...");
        
        // Click month dropdown
        const monthDropdown = await page.$('div[role="combobox"][aria-expanded="false"]:has(div[aria-live="polite"][data-value=""])');
        if (monthDropdown) {
            await monthDropdown.click();
            await page.waitForTimeout(1000);
            
            // Wait for and click May option
            try {
                await page.waitForSelector('[data-value="5"]', { timeout: 5000 });
                await page.click('[data-value="5"]');
                console.log("✅ Month selected: May");
                await page.waitForTimeout(2000);
            } catch (error) {
                console.log("⚠️ Month selection failed, trying alternative approach...");
                // Alternative: Use keyboard navigation
                await page.keyboard.press('ArrowDown');
                await page.keyboard.press('ArrowDown');
                await page.keyboard.press('ArrowDown');
                await page.keyboard.press('ArrowDown');
                await page.keyboard.press('ArrowDown'); // May is 5th option
                await page.keyboard.press('Enter');
                await page.waitForTimeout(2000);
            }
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

        // Handle Gender dropdown - try multiple approaches
        console.log("👤 Selecting gender...");
        
        try {
            // Approach 1: Direct click on gender dropdown
            const genderDropdown = await page.$('div[role="combobox"]:has(div[data-value=""]):not(:has(div[aria-live="polite"]))');
            if (genderDropdown) {
                await genderDropdown.click();
                await page.waitForTimeout(1000);
                
                // Click on "Male" option (data-value="1")
                await page.waitForSelector('[data-value="1"]', { timeout: 3000 });
                await page.click('[data-value="1"]');
                console.log("✅ Gender selected: Male");
                await page.waitForTimeout(2000);
            }
        } catch (error) {
            console.log("⚠️ Standard gender selection failed, trying JavaScript injection...");
            
            // Approach 2: JavaScript manipulation
            await page.evaluate(() => {
                // Find the form and add hidden gender input
                const form = document.querySelector('form');
                if (form) {
                    const genderInput = document.createElement('input');
                    genderInput.type = 'hidden';
                    genderInput.name = 'Gender';
                    genderInput.value = '1'; // Male
                    form.appendChild(genderInput);
                    
                    // Also try to set the combobox value
                    const genderCombobox = document.querySelector('div[role="combobox"]:not([aria-expanded]):not([aria-live])');
                    if (genderCombobox) {
                        const valueDiv = genderCombobox.querySelector('div[data-value=""]');
                        if (valueDiv) {
                            valueDiv.setAttribute('data-value', '1');
                            valueDiv.textContent = 'Male';
                        }
                    }
                }
            });
            console.log("✅ Gender set via JavaScript manipulation");
            await page.waitForTimeout(2000);
        }

        // Click Next to proceed
        console.log("▶️ Proceeding to next step...");
        await page.click('button[type="button"]:has(span:text("Next"))');
        
        // Wait for email selection page
        console.log("📧 Waiting for email setup page...");
        await page.waitForSelector('input[type="text"]', { timeout: 15000 });
        
        // Try to use the desired email
        const desiredEmail = 'smarthubshopper';
        console.log(`📧 Attempting to use email: ${desiredEmail}@gmail.com`);
        
        // Look for the email input field
        const emailInput = await page.$('input[type="text"][aria-label*="email" i], input[type="text"][name*="email" i], input[type="text"]');
        if (emailInput) {
            await emailInput.click();
            await page.type(emailInput, desiredEmail, { delay: 100 });
            await page.waitForTimeout(2000);
        }

        console.log("🎉 Reached email setup page successfully!");
        console.log("📧 Attempted to set email: smarthubshopper@gmail.com");
        
        // Wait for manual completion or further automation
        console.log("⏸️ Pausing for manual review...");
        await page.waitForTimeout(10000);

    } catch (error) {
        console.error("❌ Error during automation:", error.message);
        
        // Take screenshot for debugging if page exists
        try {
            if (page) {
                await page.screenshot({ 
                    path: 'google_signup_error.png', 
                    fullPage: true 
                });
                console.log("📸 Error screenshot saved as 'google_signup_error.png'");
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