const puppeteer = require('puppeteer');

// Helper function to wait
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function createGoogleAccount() {
    const browser = await puppeteer.launch({ 
        headless: false,
        slowMo: 100,
        defaultViewport: null,
        args: ['--start-maximized']
    });

    let page;
    try {
        page = await browser.newPage();
        
        console.log("🌐 Navigating to Google accounts page...");
        await page.goto('https://accounts.google.com/', {
            waitUntil: 'networkidle2'
        });
        
        await wait(2000);
        
        // Look for and click "Create account" link
        console.log("🔍 Looking for 'Create account' link...");
        let createAccountFound = false;
        
        try {
            // Method 1: Try to find by href containing signup
            const signupLinks = await page.$$('a[href*="signup"]');
            if (signupLinks.length > 0) {
                console.log("✅ Found signup link via href");
                await signupLinks[0].click();
                createAccountFound = true;
            }
        } catch (error) {
            console.log("⚠️ Method 1 failed:", error.message);
        }
        
        if (!createAccountFound) {
            try {
                // Method 2: Search all links for "Create" text
                console.log("🔍 Searching all links for 'Create' text...");
                const allLinks = await page.$$('a');
                console.log(`Found ${allLinks.length} links to search`);
                
                for (let i = 0; i < allLinks.length; i++) {
                    const text = await page.evaluate(el => el.textContent?.toLowerCase() || '', allLinks[i]);
                    if (text.includes('create')) {
                        console.log(`✅ Found create link: "${text}"`);
                        await allLinks[i].click();
                        createAccountFound = true;
                        break;
                    }
                }
            } catch (error) {
                console.log("⚠️ Method 2 failed:", error.message);
            }
        }
        
        if (!createAccountFound) {
            try {
                // Method 3: Try buttons
                console.log("🔍 Searching buttons for 'Create' text...");
                const allButtons = await page.$$('button');
                console.log(`Found ${allButtons.length} buttons to search`);
                
                for (let i = 0; i < allButtons.length; i++) {
                    const text = await page.evaluate(el => el.textContent?.toLowerCase() || '', allButtons[i]);
                    if (text.includes('create')) {
                        console.log(`✅ Found create button: "${text}"`);
                        await allButtons[i].click();
                        createAccountFound = true;
                        break;
                    }
                }
            } catch (error) {
                console.log("⚠️ Method 3 failed:", error.message);
            }
        }
        
        if (createAccountFound) {
            console.log("✅ Create account clicked! Waiting for signup form...");
            await wait(3000);
        } else {
            console.log("⚠️ Create account not found, trying direct URL...");
            await page.goto('https://accounts.google.com/signup/v2/webcreateaccount?flowName=GlifWebSignIn&flowEntry=SignUp', {
                waitUntil: 'networkidle2'
            });
            await wait(2000);
        }
        
        // Check what page we're on
        const currentUrl = page.url();
        console.log(`📍 Current URL: ${currentUrl}`);
        
        // Take a screenshot to see what we have
        await page.screenshot({ 
            path: 'current_page.png', 
            fullPage: true 
        });
        console.log("📸 Current page screenshot saved as 'current_page.png'");
        
        // Try to find firstName field with more flexible approach
        console.log("🔍 Looking for first name field...");
        
        const firstNameSelectors = [
            '#firstName',
            'input[name="firstName"]',
            'input[aria-label*="First"]',
            'input[placeholder*="First"]',
            'input[type="text"]'
        ];
        
        let firstNameFound = false;
        for (let selector of firstNameSelectors) {
            try {
                await page.waitForSelector(selector, { timeout: 3000 });
                console.log(`✅ Found first name field with selector: ${selector}`);
                await page.type(selector, 'Smart', { delay: 100 });
                firstNameFound = true;
                break;
            } catch (error) {
                console.log(`⚠️ Selector ${selector} not found`);
            }
        }
        
        if (!firstNameFound) {
            console.log("❌ Could not find first name field");
            console.log("🔍 Let's see what input fields are available...");
            
            const allInputs = await page.$$('input');
            console.log(`Found ${allInputs.length} input fields:`);
            
            for (let i = 0; i < Math.min(allInputs.length, 10); i++) {
                const input = allInputs[i];
                const type = await page.evaluate(el => el.type, input);
                const name = await page.evaluate(el => el.name, input);
                const id = await page.evaluate(el => el.id, input);
                const placeholder = await page.evaluate(el => el.placeholder, input);
                console.log(`  Input ${i}: type="${type}" name="${name}" id="${id}" placeholder="${placeholder}"`);
            }
            
            // Try the first text input
            if (allInputs.length > 0) {
                console.log("🔄 Trying first available input...");
                await allInputs[0].click();
                await page.type(allInputs[0], 'Smart', { delay: 100 });
                firstNameFound = true;
            }
        }
        
        if (firstNameFound) {
            await wait(2000);
            console.log("✅ First name entered!");
            
            // Continue with rest of the flow...
            console.log("⏸️ Pausing for manual review (10 seconds)...");
            await wait(10000);
        }
        
    } catch (error) {
        console.error("❌ Error during automation:", error.message);
        
        if (page) {
            await page.screenshot({ 
                path: 'error_page.png', 
                fullPage: true 
            });
            console.log("📸 Error screenshot saved");
        }
        
    } finally {
        console.log("🔍 Browser will remain open for manual review...");
        // Keep browser open
    }
}

createGoogleAccount().catch(console.error); 