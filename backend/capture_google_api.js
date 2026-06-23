const puppeteer = require('puppeteer');
const fs = require('fs');

// Helper function to wait
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function captureGoogleSignupAPI() {
    const browser = await puppeteer.launch({ 
        headless: false,
        slowMo: 100,
        defaultViewport: null,
        args: ['--start-maximized']
    });

    let page;
    const requests = [];
    const responses = [];

    try {
        page = await browser.newPage();

        // Intercept all network requests
        await page.setRequestInterception(true);
        
        page.on('request', (request) => {
            const requestData = {
                url: request.url(),
                method: request.method(),
                headers: request.headers(),
                postData: request.postData(),
                timestamp: new Date().toISOString()
            };
            
            // Only log Google API calls
            if (request.url().includes('google') || request.url().includes('accounts')) {
                console.log(`📤 REQUEST: ${request.method()} ${request.url()}`);
                if (request.postData()) {
                    console.log(`   POST DATA: ${request.postData()}`);
                }
                requests.push(requestData);
            }
            
            // Continue the request
            request.continue();
        });

        page.on('response', async (response) => {
            // Only log Google API responses
            if (response.url().includes('google') || response.url().includes('accounts')) {
                try {
                    const responseData = {
                        url: response.url(),
                        status: response.status(),
                        headers: response.headers(),
                        body: await response.text(),
                        timestamp: new Date().toISOString()
                    };
                    
                    console.log(`📥 RESPONSE: ${response.status()} ${response.url()}`);
                    if (responseData.body && responseData.body.length < 1000) {
                        console.log(`   BODY: ${responseData.body.substring(0, 200)}...`);
                    }
                    responses.push(responseData);
                } catch (error) {
                    console.log(`   Error reading response body: ${error.message}`);
                }
            }
        });
        
        console.log("🌐 Navigating to Google accounts page...");
        await page.goto('https://accounts.google.com/', {
            waitUntil: 'networkidle2'
        });
        
        await wait(2000);
        
        // Look for and click "Create account" link
        console.log("🔍 Looking for 'Create account' link...");
        let createAccountFound = false;
        
        try {
            // Try multiple selectors for create account
            const selectors = [
                'a[href*="signup"]',
                'button:contains("Create account")',
                'a:contains("Create account")',
                '[data-action="signup"]'
            ];
            
            for (const selector of selectors) {
                try {
                    await page.waitForSelector(selector, { timeout: 2000 });
                    await page.click(selector);
                    console.log(`✅ Clicked create account using selector: ${selector}`);
                    createAccountFound = true;
                    break;
                } catch (e) {
                    // Try next selector
                }
            }
            
            // If no selector works, try clicking any element with "create" text
            if (!createAccountFound) {
                const elements = await page.$$('a, button');
                for (let element of elements) {
                    const text = await page.evaluate(el => el.textContent.toLowerCase(), element);
                    if (text.includes('create account') || text.includes('create')) {
                        await element.click();
                        console.log(`✅ Clicked element with text: ${text}`);
                        createAccountFound = true;
                        break;
                    }
                }
            }
            
        } catch (error) {
            console.log("⚠️ Error finding create account:", error.message);
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

        // Try to fill some basic form data to trigger more API calls
        console.log("🔍 Looking for form fields to trigger API calls...");
        
        try {
            // Look for first name field
            const firstNameSelectors = ['#firstName', 'input[name="firstName"]', 'input[autocomplete="given-name"]'];
            for (const selector of firstNameSelectors) {
                try {
                    await page.waitForSelector(selector, { timeout: 2000 });
                    await page.type(selector, 'Smart', { delay: 100 });
                    console.log(`✅ Filled first name using: ${selector}`);
                    await wait(1000);
                    break;
                } catch (e) {
                    // Try next selector
                }
            }
            
            // Look for last name field
            const lastNameSelectors = ['#lastName', 'input[name="lastName"]', 'input[autocomplete="family-name"]'];
            for (const selector of lastNameSelectors) {
                try {
                    await page.waitForSelector(selector, { timeout: 2000 });
                    await page.type(selector, 'Shopper', { delay: 100 });
                    console.log(`✅ Filled last name using: ${selector}`);
                    await wait(1000);
                    break;
                } catch (e) {
                    // Try next selector
                }
            }
            
        } catch (error) {
            console.log("⚠️ Error filling form fields:", error.message);
        }

        console.log("⏸️ Pausing to capture more network traffic (10 seconds)...");
        await wait(10000);

        // Save captured data to files
        fs.writeFileSync('google_requests.json', JSON.stringify(requests, null, 2));
        fs.writeFileSync('google_responses.json', JSON.stringify(responses, null, 2));
        
        console.log(`📊 Captured ${requests.length} requests and ${responses.length} responses`);
        console.log("📁 Data saved to google_requests.json and google_responses.json");

    } catch (error) {
        console.error("❌ Error during capture:", error.message);
        
        if (page) {
            await page.screenshot({ 
                path: 'google_api_capture_error.png', 
                fullPage: true 
            });
            console.log("📸 Error screenshot saved");
        }
        
    } finally {
        console.log("🔍 Browser will remain open for manual review...");
        // Keep browser open to see the current state
        // await browser.close(); // Uncomment to auto-close
    }
}

// Run the capture
captureGoogleSignupAPI().catch(console.error); 