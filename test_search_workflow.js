/**
 * Search Workflow Test (Without Upload)
 *
 * Tests search functionality on existing documents:
 * 1. Navigate to search page
 * 2. Perform search with different modes
 * 3. Verify results
 * 4. Test filtering by work/author
 */

const puppeteer = require('puppeteer');

const FLASK_URL = 'http://localhost:5000';
const SEARCH_QUERIES = [
  { query: 'Turing', mode: 'simple', expectedKeywords: ['Turing', 'machine', 'computation'] },
  { query: 'conscience et intelligence', mode: 'hierarchical', expectedKeywords: ['conscience', 'intelligence'] },
  { query: 'categories', mode: 'summaries', expectedKeywords: ['categor'] }
];

async function testSearchWorkflow() {
  console.log('🔍 Starting Search Workflow Test\n');

  const browser = await puppeteer.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Track console errors
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('error') || text.includes('Error')) {
      console.log('❌ Console error:', text);
    }
  });

  page.on('pageerror', error => {
    console.log('❌ Page error:', error.message);
  });

  try {
    // ====================
    // STEP 1: Check Database Content
    // ====================
    console.log('📊 Step 1: Checking database content...');

    await page.goto(`${FLASK_URL}/`, {
      waitUntil: 'networkidle0',
      timeout: 30000
    });

    const stats = await page.evaluate(() => {
      const text = document.body.innerText;
      const chunksMatch = text.match(/(\d+)\s+chunks?/i);
      const worksMatch = text.match(/(\d+)\s+works?/i);

      return {
        chunks: chunksMatch ? parseInt(chunksMatch[1]) : 0,
        works: worksMatch ? parseInt(worksMatch[1]) : 0,
        pageText: text.substring(0, 500)
      };
    });

    console.log(`✅ Database stats:`);
    console.log(`   - Chunks: ${stats.chunks}`);
    console.log(`   - Works: ${stats.works}`);

    if (stats.chunks === 0) {
      console.log('\n⚠️  WARNING: No chunks in database!');
      console.log('   Please run upload workflow first or ensure database has data.');
    }

    await page.screenshot({ path: 'test_search_01_homepage.png' });

    // ====================
    // STEP 2: Test Multiple Search Modes
    // ====================
    const results = [];

    for (let i = 0; i < SEARCH_QUERIES.length; i++) {
      const { query, mode, expectedKeywords } = SEARCH_QUERIES[i];

      console.log(`\n🔍 Step ${i + 2}: Testing search - "${query}" (${mode})`);

      await page.goto(`${FLASK_URL}/search`, {
        waitUntil: 'networkidle0',
        timeout: 30000
      });

      // Fill search form
      await page.type('input[name="q"]', query);
      await page.select('select[name="mode"]', mode);

      console.log(`   ✓ Query entered: "${query}"`);
      console.log(`   ✓ Mode selected: ${mode}`);

      // Submit search
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 30000 }),
        page.click('button[type="submit"]')
      ]);

      await page.screenshot({ path: `test_search_${String(i + 2).padStart(2, '0')}_${mode}.png` });

      // Analyze results
      const searchResult = await page.evaluate((keywords) => {
        const resultsDiv = document.querySelector('.results') || document.body;
        const text = resultsDiv.innerText;

        // Count results
        const resultItems = document.querySelectorAll('.passage, .result-item, .chunk-result, .summary-result');

        // Check for keywords
        const foundKeywords = keywords.filter(kw =>
          text.toLowerCase().includes(kw.toLowerCase())
        );

        // Check for "no results"
        const noResults = text.includes('No results') ||
                         text.includes('0 results') ||
                         text.includes('Aucun résultat');

        // Extract first result snippet
        const firstResult = resultItems[0] ? resultItems[0].innerText.substring(0, 200) : '';

        return {
          resultCount: resultItems.length,
          foundKeywords,
          noResults,
          firstResult
        };
      }, expectedKeywords);

      results.push({
        query,
        mode,
        ...searchResult
      });

      console.log(`   📋 Results:`);
      console.log(`      - Count: ${searchResult.resultCount}`);
      console.log(`      - Keywords found: ${searchResult.foundKeywords.join(', ') || 'none'}`);
      console.log(`      - No results: ${searchResult.noResults ? 'YES ⚠️' : 'NO'}`);

      if (searchResult.firstResult) {
        console.log(`      - First result: "${searchResult.firstResult.substring(0, 100)}..."`);
      }
    }

    // ====================
    // STEP 3: Test Filtering
    // ====================
    console.log(`\n🎯 Step ${SEARCH_QUERIES.length + 2}: Testing work/author filtering...`);

    await page.goto(`${FLASK_URL}/search`, {
      waitUntil: 'networkidle0',
      timeout: 30000
    });

    // Get available works for filtering
    const works = await page.evaluate(() => {
      const workOptions = Array.from(document.querySelectorAll('select[name="work_filter"] option'));
      return workOptions
        .filter(opt => opt.value && opt.value !== '')
        .map(opt => ({ value: opt.value, text: opt.text }))
        .slice(0, 2); // Test with first 2 works
    });

    console.log(`   Found ${works.length} works to test:`, works.map(w => w.text).join(', '));

    if (works.length > 0) {
      const testWork = works[0];

      await page.type('input[name="q"]', 'intelligence');
      await page.select('select[name="work_filter"]', testWork.value);

      console.log(`   ✓ Testing filter: ${testWork.text}`);

      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 30000 }),
        page.click('button[type="submit"]')
      ]);

      await page.screenshot({ path: `test_search_${String(SEARCH_QUERIES.length + 2).padStart(2, '0')}_filtered.png` });

      const filteredResults = await page.evaluate(() => {
        const resultItems = document.querySelectorAll('.passage, .result-item, .chunk-result');
        return resultItems.length;
      });

      console.log(`   📋 Filtered results: ${filteredResults}`);
    }

    // ====================
    // FINAL SUMMARY
    // ====================
    console.log('\n' + '='.repeat(60));
    console.log('🎯 TEST SUMMARY');
    console.log('='.repeat(60));

    let allPassed = true;

    results.forEach((result, i) => {
      const passed = result.resultCount > 0 && !result.noResults;
      const status = passed ? '✅' : '❌';

      console.log(`${status} Query ${i + 1}: "${result.query}" (${result.mode})`);
      console.log(`   - Results: ${result.resultCount}`);
      console.log(`   - Keywords: ${result.foundKeywords.length}/${SEARCH_QUERIES[i].expectedKeywords.length}`);

      if (!passed) allPassed = false;
    });

    console.log('='.repeat(60));

    if (allPassed) {
      console.log('✅ ALL SEARCH TESTS PASSED');
    } else {
      console.log('⚠️  SOME SEARCH TESTS FAILED');
    }

    console.log('\n📸 Screenshots saved:');
    console.log('   - test_search_01_homepage.png');
    for (let i = 0; i < SEARCH_QUERIES.length; i++) {
      console.log(`   - test_search_${String(i + 2).padStart(2, '0')}_${SEARCH_QUERIES[i].mode}.png`);
    }
    if (works.length > 0) {
      console.log(`   - test_search_${String(SEARCH_QUERIES.length + 2).padStart(2, '0')}_filtered.png`);
    }

  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message);
    await page.screenshot({ path: 'test_search_error.png' });
    console.log('📸 Error screenshot saved: test_search_error.png');
    throw error;
  } finally {
    await browser.close();
    console.log('\n🏁 Test completed\n');
  }
}

// Run test
testSearchWorkflow().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
