/**
 * Puppeteer test for /test-chat-backend page
 * Tests the RAG chat functionality with streaming SSE responses
 *
 * Usage: node test_chat_backend.js
 */

const puppeteer = require('puppeteer');

const BASE_URL = 'http://localhost:5000';
const TIMEOUT = 120000; // 2 minutes for LLM response

async function testChatBackend() {
    console.log('=== Test Chat Backend RAG ===\n');

    let browser;
    try {
        // Launch browser
        console.log('1. Launching browser...');
        browser = await puppeteer.launch({
            headless: false, // Set to true for CI
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        const page = await browser.newPage();
        page.setDefaultTimeout(TIMEOUT);

        // Enable console logging from the page
        page.on('console', msg => {
            if (msg.type() === 'error') {
                console.log('  [Browser Error]', msg.text());
            }
        });

        // Navigate to test page
        console.log('2. Navigating to /test-chat-backend...');
        await page.goto(`${BASE_URL}/test-chat-backend`, {
            waitUntil: 'networkidle0',
            timeout: 30000
        });
        console.log('   OK - Page loaded');

        // Fill in the question
        console.log('3. Filling in the form...');
        const question = "What is a Turing machine?";
        await page.evaluate((q) => {
            document.getElementById('question').value = q;
        }, question);
        console.log(`   Question: "${question}"`);

        // Select provider (Mistral by default)
        const provider = 'mistral';
        await page.select('#provider', provider);
        console.log(`   Provider: ${provider}`);

        // Select model
        const model = 'mistral-small-latest';
        await page.select('#model', model);
        console.log(`   Model: ${model}`);

        // Set limit
        await page.evaluate(() => {
            document.getElementById('limit').value = '3';
        });
        console.log('   Limit: 3');

        // Click send button
        console.log('4. Sending question...');
        await page.click('#sendBtn');

        // Wait for output section to appear
        await page.waitForSelector('#output[style*="block"]', { timeout: 10000 });
        console.log('   OK - Output section visible');

        // Wait for session ID to appear in log
        console.log('5. Waiting for session creation...');
        await page.waitForFunction(() => {
            const log = document.getElementById('log');
            return log && log.textContent.includes('Session:');
        }, { timeout: 15000 });

        const sessionInfo = await page.evaluate(() => {
            return document.getElementById('log').textContent;
        });
        console.log(`   ${sessionInfo.trim()}`);

        // Wait for context (RAG results) or error
        console.log('6. Waiting for RAG context...');
        try {
            await page.waitForSelector('#contextSection[style*="block"]', { timeout: 30000 });

            const contextCount = await page.evaluate(() => {
                const items = document.querySelectorAll('.context-item');
                return items.length;
            });
            console.log(`   OK - Received ${contextCount} context chunks`);

            // Get context details
            const contexts = await page.evaluate(() => {
                const items = document.querySelectorAll('.context-item');
                return Array.from(items).map(item => {
                    const text = item.textContent;
                    const match = text.match(/Passage (\d+).*?(\d+)%.*?-\s*([^-]+)\s*-\s*([^\n]+)/);
                    if (match) {
                        return {
                            passage: match[1],
                            similarity: match[2],
                            author: match[3].trim(),
                            work: match[4].trim()
                        };
                    }
                    return { raw: text.substring(0, 100) };
                });
            });

            contexts.forEach(ctx => {
                if (ctx.similarity) {
                    console.log(`     - Passage ${ctx.passage}: ${ctx.similarity}% - ${ctx.author} - ${ctx.work}`);
                }
            });

        } catch (e) {
            // Check if there's an error
            const hasError = await page.evaluate(() => {
                const log = document.getElementById('log');
                return log && log.textContent.includes('status-error');
            });

            if (hasError) {
                const errorMsg = await page.evaluate(() => {
                    return document.getElementById('log').textContent;
                });
                console.log(`   ERROR: ${errorMsg}`);
                throw new Error(`Chat failed: ${errorMsg}`);
            }

            console.log('   WARNING: Context section not shown (might be empty results)');
        }

        // Wait for response streaming
        console.log('7. Waiting for LLM response...');
        try {
            await page.waitForSelector('#responseSection[style*="block"]', { timeout: 60000 });
            console.log('   OK - Response section visible');

            // Wait for streaming to complete
            await page.waitForFunction(() => {
                const log = document.getElementById('log');
                return log && (log.textContent.includes('Terminé') || log.textContent.includes('error'));
            }, { timeout: 90000 });

            // Get final status
            const finalStatus = await page.evaluate(() => {
                return document.getElementById('log').textContent;
            });

            if (finalStatus.includes('Terminé')) {
                console.log('   OK - Response complete');
            } else {
                console.log(`   Status: ${finalStatus}`);
            }

            // Get response length
            const responseLength = await page.evaluate(() => {
                const response = document.getElementById('response');
                return response ? response.textContent.length : 0;
            });
            console.log(`   Response length: ${responseLength} characters`);

            // Get first 200 chars of response
            const responsePreview = await page.evaluate(() => {
                const response = document.getElementById('response');
                return response ? response.textContent.substring(0, 200) : '';
            });
            console.log(`   Preview: "${responsePreview}..."`);

        } catch (e) {
            const errorMsg = await page.evaluate(() => {
                return document.getElementById('log')?.textContent || 'Unknown error';
            });
            console.log(`   ERROR waiting for response: ${errorMsg}`);
            throw e;
        }

        // Final verification
        console.log('\n8. Final verification...');
        const results = await page.evaluate(() => {
            return {
                hasContext: document.getElementById('contextSection').style.display !== 'none',
                hasResponse: document.getElementById('responseSection').style.display !== 'none',
                contextItems: document.querySelectorAll('.context-item').length,
                responseLength: document.getElementById('response')?.textContent?.length || 0,
                status: document.getElementById('log')?.textContent || ''
            };
        });

        console.log(`   Context shown: ${results.hasContext}`);
        console.log(`   Context items: ${results.contextItems}`);
        console.log(`   Response shown: ${results.hasResponse}`);
        console.log(`   Response length: ${results.responseLength}`);
        console.log(`   Final status: ${results.status.trim()}`);

        // Determine test result
        const success = results.hasResponse && results.responseLength > 100 && results.status.includes('Terminé');

        console.log('\n' + '='.repeat(50));
        if (success) {
            console.log('TEST PASSED - Chat backend working correctly');
        } else {
            console.log('TEST FAILED - Check the results above');
        }
        console.log('='.repeat(50));

        // Keep browser open for 5 seconds to see result
        await new Promise(resolve => setTimeout(resolve, 5000));

        return success;

    } catch (error) {
        console.error('\nTEST ERROR:', error.message);
        return false;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

// Run test
testChatBackend()
    .then(success => {
        process.exit(success ? 0 : 1);
    })
    .catch(err => {
        console.error('Unexpected error:', err);
        process.exit(1);
    });
