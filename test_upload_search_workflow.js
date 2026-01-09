/**
 * Full PDF Upload and Search Workflow Test
 *
 * Tests the complete pipeline:
 * 1. Upload PDF via web interface
 * 2. Wait for processing completion (SSE stream)
 * 3. Verify document in database
 * 4. Search for content from the document
 * 5. Verify search results
 */

const puppeteer = require('puppeteer');
const path = require('path');

const FLASK_URL = 'http://localhost:5000';
const TEST_PDF = path.join(__dirname, 'generations', 'library_rag', 'input', 'On_a_New_List_of_Categories.pdf');
const SEARCH_QUERY = 'categories'; // Term that should be in the document
const TIMEOUT = 300000; // 5 minutes for full processing

async function testUploadSearchWorkflow() {
  console.log('🚀 Starting Full Upload & Search Workflow Test\n');

  const browser = await puppeteer.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Track console messages and errors
  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    logs.push(text);
    if (text.includes('error') || text.includes('Error')) {
      console.log('❌ Console error:', text);
    }
  });

  page.on('pageerror', error => {
    console.log('❌ Page error:', error.message);
  });

  try {
    // ====================
    // STEP 1: Navigate to Upload Page
    // ====================
    console.log('📄 Step 1: Navigating to upload page...');
    const uploadResponse = await page.goto(`${FLASK_URL}/upload`, {
      waitUntil: 'networkidle0',
      timeout: 30000
    });

    if (uploadResponse.status() !== 200) {
      throw new Error(`Upload page returned status ${uploadResponse.status()}`);
    }

    await page.screenshot({ path: 'test_screenshot_01_upload_page.png' });
    console.log('✅ Upload page loaded (screenshot: test_screenshot_01_upload_page.png)\n');

    // ====================
    // STEP 2: Fill Upload Form
    // ====================
    console.log('📝 Step 2: Filling upload form...');

    // Upload file
    const fileInput = await page.$('input[type="file"]');
    if (!fileInput) {
      throw new Error('File input not found');
    }
    await fileInput.uploadFile(TEST_PDF);
    console.log(`✅ File selected: ${TEST_PDF}`);

    // Select LLM provider (Ollama for free local processing)
    const providerSelect = await page.$('select[name="llm_provider"]');
    if (providerSelect) {
      await page.select('select[name="llm_provider"]', 'ollama');
      console.log('✅ Selected LLM provider: ollama');
    }

    // Note: use_semantic_chunking checkbox doesn't exist in the form
    // The form has use_llm and ingest_weaviate checked by default

    await page.screenshot({ path: 'test_screenshot_02_form_filled.png' });
    console.log('✅ Form filled (screenshot: test_screenshot_02_form_filled.png)\n');

    // ====================
    // STEP 3: Submit and Wait for Processing
    // ====================
    console.log('⏳ Step 3: Submitting form and waiting for processing...');
    console.log(`   (Timeout: ${TIMEOUT / 1000}s)\n`);

    // Click submit button
    const submitButton = await page.$('button[type="submit"]');
    if (!submitButton) {
      throw new Error('Submit button not found');
    }

    // Click and wait for URL change or page content change
    await submitButton.click();
    console.log('✅ Submit button clicked, waiting for response...');

    // Wait for either URL change or page content to indicate progress page loaded
    await page.waitForFunction(
      () => {
        return window.location.href.includes('/upload/progress') ||
               document.body.innerText.includes('Progress') ||
               document.body.innerText.includes('Traitement en cours');
      },
      { timeout: 30000 }
    );

    console.log('✅ Form submitted, progress page loaded');
    await page.screenshot({ path: 'test_screenshot_03_progress_start.png' });

    // Wait for processing completion by checking for success message
    console.log('⏳ Waiting for processing to complete...');

    try {
      // Wait for success indicator (could be "Processing complete", "Success", etc.)
      await page.waitForFunction(
        () => {
          const bodyText = document.body.innerText;
          return bodyText.includes('Processing complete') ||
                 bodyText.includes('Success') ||
                 bodyText.includes('completed successfully') ||
                 bodyText.includes('Ingestion: Success');
        },
        { timeout: TIMEOUT }
      );

      console.log('✅ Processing completed successfully!');
      await page.screenshot({ path: 'test_screenshot_04_progress_complete.png' });

      // Extract processing results
      const results = await page.evaluate(() => {
        const text = document.body.innerText;
        const chunksMatch = text.match(/(\d+)\s+chunks?/i);
        const costMatch = text.match(/€([\d.]+)/);

        return {
          pageText: text,
          chunks: chunksMatch ? parseInt(chunksMatch[1]) : null,
          cost: costMatch ? parseFloat(costMatch[1]) : null
        };
      });

      console.log(`\n📊 Processing Results:`);
      console.log(`   - Chunks created: ${results.chunks || 'unknown'}`);
      console.log(`   - Total cost: €${results.cost || 'unknown'}`);

    } catch (error) {
      console.log('⚠️  Processing timeout or error:', error.message);
      await page.screenshot({ path: 'test_screenshot_04_progress_timeout.png' });
      throw error;
    }

    // ====================
    // STEP 4: Verify Document in Database
    // ====================
    console.log('\n📚 Step 4: Verifying document in database...');

    await page.goto(`${FLASK_URL}/documents`, {
      waitUntil: 'networkidle0',
      timeout: 30000
    });

    const documentFound = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('On_a_New_List_of_Categories') ||
             text.includes('Categories');
    });

    if (documentFound) {
      console.log('✅ Document found in /documents page');
      await page.screenshot({ path: 'test_screenshot_05_documents.png' });
    } else {
      console.log('⚠️  Document not found in /documents page');
      await page.screenshot({ path: 'test_screenshot_05_documents_notfound.png' });
    }

    // ====================
    // STEP 5: Search for Content
    // ====================
    console.log(`\n🔍 Step 5: Searching for "${SEARCH_QUERY}"...`);

    await page.goto(`${FLASK_URL}/search`, {
      waitUntil: 'networkidle0',
      timeout: 30000
    });

    // Enter search query
    await page.type('input[name="q"]', SEARCH_QUERY);
    console.log(`✅ Entered query: "${SEARCH_QUERY}"`);

    // Select search mode (simple)
    const modeSelect = await page.$('select[name="mode"]');
    if (modeSelect) {
      await page.select('select[name="mode"]', 'simple');
      console.log('✅ Selected mode: simple');
    }

    await page.screenshot({ path: 'test_screenshot_06_search_form.png' });

    // Submit search
    const searchButton = await page.$('button[type="submit"]');
    if (searchButton) {
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 30000 }),
        searchButton.click()
      ]);
      console.log('✅ Search submitted');
    }

    await page.screenshot({ path: 'test_screenshot_07_search_results.png' });

    // ====================
    // STEP 6: Analyze Search Results
    // ====================
    console.log('\n📊 Step 6: Analyzing search results...');

    const searchResults = await page.evaluate(() => {
      const resultsDiv = document.querySelector('.results') || document.body;
      const text = resultsDiv.innerText;

      // Count results
      const resultItems = document.querySelectorAll('.result-item, .chunk, .passage');

      // Check for our document
      const hasOurDocument = text.includes('On_a_New_List_of_Categories') ||
                             text.includes('Categories');

      // Check for "no results" message
      const noResults = text.includes('No results') ||
                       text.includes('0 results') ||
                       text.includes('Aucun résultat');

      return {
        resultCount: resultItems.length,
        hasOurDocument,
        noResults,
        snippet: text.substring(0, 500)
      };
    });

    console.log(`\n📋 Search Results Summary:`);
    console.log(`   - Results found: ${searchResults.resultCount}`);
    console.log(`   - Contains our document: ${searchResults.hasOurDocument ? 'YES ✅' : 'NO ❌'}`);
    console.log(`   - No results message: ${searchResults.noResults ? 'YES ⚠️' : 'NO'}`);

    if (searchResults.resultCount > 0) {
      console.log(`\n   First 500 chars of results:`);
      console.log(`   ${searchResults.snippet.substring(0, 200)}...`);
    }

    // ====================
    // FINAL SUMMARY
    // ====================
    console.log('\n' + '='.repeat(60));
    console.log('🎯 TEST SUMMARY');
    console.log('='.repeat(60));

    const allTestsPassed =
      documentFound &&
      searchResults.resultCount > 0 &&
      !searchResults.noResults;

    if (allTestsPassed) {
      console.log('✅ ALL TESTS PASSED');
      console.log('   ✓ PDF uploaded successfully');
      console.log('   ✓ Processing completed');
      console.log('   ✓ Document appears in database');
      console.log('   ✓ Search returns results');
    } else {
      console.log('⚠️  SOME TESTS FAILED');
      if (!documentFound) console.log('   ✗ Document not found in database');
      if (searchResults.noResults) console.log('   ✗ Search returned no results');
      if (searchResults.resultCount === 0) console.log('   ✗ No search result items found');
    }

    console.log('='.repeat(60));
    console.log('\n📸 Screenshots saved:');
    console.log('   - test_screenshot_01_upload_page.png');
    console.log('   - test_screenshot_02_form_filled.png');
    console.log('   - test_screenshot_03_progress_start.png');
    console.log('   - test_screenshot_04_progress_complete.png');
    console.log('   - test_screenshot_05_documents.png');
    console.log('   - test_screenshot_06_search_form.png');
    console.log('   - test_screenshot_07_search_results.png');

  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message);
    await page.screenshot({ path: 'test_screenshot_error.png' });
    console.log('📸 Error screenshot saved: test_screenshot_error.png');
    throw error;
  } finally {
    await browser.close();
    console.log('\n🏁 Test completed\n');
  }
}

// Run test
testUploadSearchWorkflow().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
