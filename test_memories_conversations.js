/**
 * Test des pages Memories et Conversations - Debug NetworkError
 */

const puppeteer = require('puppeteer');

async function testMemoriesAndConversations() {
    console.log('='.repeat(70));
    console.log('Test Memories et Conversations - Debug NetworkError');
    console.log('='.repeat(70));

    const browser = await puppeteer.launch({
        headless: false,
        defaultViewport: { width: 1280, height: 900 }
    });

    try {
        const page = await browser.newPage();

        // Intercepter les erreurs réseau
        page.on('response', response => {
            const status = response.status();
            const url = response.url();
            if (status >= 400) {
                console.log(`   ⚠ HTTP ${status}: ${url}`);
            }
        });

        page.on('pageerror', error => {
            console.log(`   ⚠ Page Error: ${error.message}`);
        });

        page.on('console', msg => {
            const type = msg.type();
            if (type === 'error') {
                console.log(`   ⚠ Console Error: ${msg.text()}`);
            }
        });

        // ===== TEST 1: Page Memories =====
        console.log('\n1. Test de la page /memories...');

        try {
            await page.goto('http://localhost:5000/memories', {
                waitUntil: 'networkidle2',
                timeout: 10000
            });
            console.log('   ✓ Page /memories chargée');

            await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\memories_page.png' });
            console.log('   ✓ Screenshot sauvegardé: memories_page.png');

            // Attendre un peu pour voir si des requêtes échouent
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Vérifier si des erreurs sont affichées
            const hasError = await page.evaluate(() => {
                const bodyText = document.body.innerText;
                return bodyText.includes('Error') ||
                       bodyText.includes('error') ||
                       bodyText.includes('NetworkError') ||
                       bodyText.includes('Failed');
            });

            if (hasError) {
                console.log('   ⚠ Erreur détectée dans la page');
            } else {
                console.log('   ✓ Pas d\'erreur visible dans la page');
            }

        } catch (error) {
            console.log(`   ✗ Erreur lors du chargement: ${error.message}`);
            await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\memories_error.png' });
        }

        // ===== TEST 2: Page Conversations =====
        console.log('\n2. Test de la page /conversations...');

        try {
            await page.goto('http://localhost:5000/conversations', {
                waitUntil: 'networkidle2',
                timeout: 10000
            });
            console.log('   ✓ Page /conversations chargée');

            await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\conversations_page.png' });
            console.log('   ✓ Screenshot sauvegardé: conversations_page.png');

            // Attendre un peu pour voir si des requêtes échouent
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Vérifier si des erreurs sont affichées
            const hasError = await page.evaluate(() => {
                const bodyText = document.body.innerText;
                return bodyText.includes('Error') ||
                       bodyText.includes('error') ||
                       bodyText.includes('NetworkError') ||
                       bodyText.includes('Failed');
            });

            if (hasError) {
                console.log('   ⚠ Erreur détectée dans la page');
            } else {
                console.log('   ✓ Pas d\'erreur visible dans la page');
            }

        } catch (error) {
            console.log(`   ✗ Erreur lors du chargement: ${error.message}`);
            await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\conversations_error.png' });
        }

        // ===== TEST 3: Tester la recherche sur Memories =====
        console.log('\n3. Test de recherche sur /memories...');

        try {
            await page.goto('http://localhost:5000/memories', {
                waitUntil: 'networkidle2',
                timeout: 10000
            });

            // Chercher un input de recherche
            const searchInput = await page.$('input[type="text"]') ||
                              await page.$('input[placeholder*="search"]') ||
                              await page.$('textarea');

            if (searchInput) {
                console.log('   ✓ Champ de recherche trouvé');

                // Taper une requête
                await searchInput.type('test search');
                console.log('   ✓ Requête saisie: "test search"');

                // Chercher le bouton de recherche
                const searchButton = await page.$('button[type="submit"]') ||
                                   await page.$('button.search-button') ||
                                   await page.$('button');

                if (searchButton) {
                    console.log('   ✓ Bouton de recherche trouvé');
                    await searchButton.click();
                    console.log('   ✓ Recherche lancée');

                    // Attendre la réponse
                    await new Promise(resolve => setTimeout(resolve, 3000));

                    await page.screenshot({
                        path: 'C:\\GitHub\\linear_coding_library_rag\\memories_search_results.png',
                        fullPage: true
                    });
                    console.log('   ✓ Screenshot résultats sauvegardé');
                } else {
                    console.log('   ⚠ Bouton de recherche non trouvé');
                }
            } else {
                console.log('   ℹ Pas de champ de recherche détecté');
            }

        } catch (error) {
            console.log(`   ✗ Erreur lors de la recherche: ${error.message}`);
        }

        // ===== TEST 4: Tester la recherche sur Conversations =====
        console.log('\n4. Test de recherche sur /conversations...');

        try {
            await page.goto('http://localhost:5000/conversations', {
                waitUntil: 'networkidle2',
                timeout: 10000
            });

            // Chercher un input de recherche
            const searchInput = await page.$('input[type="text"]') ||
                              await page.$('input[placeholder*="search"]') ||
                              await page.$('textarea');

            if (searchInput) {
                console.log('   ✓ Champ de recherche trouvé');

                // Taper une requête
                await searchInput.type('test conversation');
                console.log('   ✓ Requête saisie: "test conversation"');

                // Chercher le bouton de recherche
                const searchButton = await page.$('button[type="submit"]') ||
                                   await page.$('button.search-button') ||
                                   await page.$('button');

                if (searchButton) {
                    console.log('   ✓ Bouton de recherche trouvé');
                    await searchButton.click();
                    console.log('   ✓ Recherche lancée');

                    // Attendre la réponse
                    await new Promise(resolve => setTimeout(resolve, 3000));

                    await page.screenshot({
                        path: 'C:\\GitHub\\linear_coding_library_rag\\conversations_search_results.png',
                        fullPage: true
                    });
                    console.log('   ✓ Screenshot résultats sauvegardé');
                } else {
                    console.log('   ⚠ Bouton de recherche non trouvé');
                }
            } else {
                console.log('   ℹ Pas de champ de recherche détecté');
            }

        } catch (error) {
            console.log(`   ✗ Erreur lors de la recherche: ${error.message}`);
        }

        console.log('\n' + '='.repeat(70));
        console.log('✓ Tests terminés');
        console.log('Screenshots sauvegardés pour analyse');
        console.log('='.repeat(70));

        // Garder le navigateur ouvert 10 secondes
        await new Promise(resolve => setTimeout(resolve, 10000));

        return { success: true };

    } catch (error) {
        console.error('\n✗ Erreur:', error.message);
        return { success: false, error: error.message };
    } finally {
        await browser.close();
    }
}

testMemoriesAndConversations()
    .then(result => {
        process.exit(result.success ? 0 : 1);
    })
    .catch(err => {
        console.error('Erreur fatale:', err);
        process.exit(1);
    });
