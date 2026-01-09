/**
 * Test simple de recherche - détection automatique des éléments
 */

const puppeteer = require('puppeteer');

async function testSearch() {
    console.log('='.repeat(70));
    console.log('Test de Recherche Sémantique');
    console.log('='.repeat(70));

    const browser = await puppeteer.launch({
        headless: false,
        defaultViewport: { width: 1280, height: 800 }
    });

    try {
        const page = await browser.newPage();

        // 1. Aller à la page de recherche
        console.log('\n1. Navigation vers /search...');
        await page.goto('http://localhost:5000/search', { waitUntil: 'networkidle2' });
        console.log('   ✓ Page chargée');

        // 2. Prendre un screenshot de la page initiale
        await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\search_page.png' });
        console.log('   ✓ Screenshot initial sauvegardé');

        // 3. Trouver le champ de recherche
        console.log('\n2. Recherche du champ de saisie...');

        // Essayer plusieurs sélecteurs possibles
        const possibleSelectors = [
            'input[name="query"]',
            'input[type="text"]',
            'input[placeholder*="recherche"]',
            'input[placeholder*="search"]',
            '#query',
            '.search-input',
            'input.form-control'
        ];

        let queryInput = null;
        for (const selector of possibleSelectors) {
            try {
                await page.waitForSelector(selector, { timeout: 2000 });
                queryInput = selector;
                console.log(`   ✓ Champ trouvé avec sélecteur: ${selector}`);
                break;
            } catch (e) {
                // Continuer avec le prochain sélecteur
            }
        }

        if (!queryInput) {
            throw new Error('Impossible de trouver le champ de recherche');
        }

        // 4. Saisir la requête
        const searchQuery = 'Turing machine computation';
        console.log(`\n3. Saisie de la requête: "${searchQuery}"`);
        await page.type(queryInput, searchQuery);
        console.log('   ✓ Requête saisie');

        // 5. Trouver et cliquer sur le bouton de soumission
        console.log('\n4. Soumission de la recherche...');
        const submitButton = await page.$('button[type="submit"]') || await page.$('input[type="submit"]');

        if (submitButton) {
            await Promise.all([
                submitButton.click(),
                page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 })
            ]);
            console.log('   ✓ Recherche soumise');
        } else {
            // Essayer de soumettre avec Enter
            await page.keyboard.press('Enter');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 });
            console.log('   ✓ Recherche soumise (Enter)');
        }

        // 6. Attendre un peu pour les résultats
        await new Promise(resolve => setTimeout(resolve, 2000));

        // 7. Vérifier si des résultats sont affichés
        console.log('\n5. Vérification des résultats...');
        const pageContent = await page.content();

        // Chercher des indicateurs de résultats
        const hasResults = pageContent.includes('résultat') ||
                          pageContent.includes('result') ||
                          pageContent.includes('chunk') ||
                          pageContent.includes('distance');

        if (hasResults) {
            console.log('   ✓ Résultats détectés dans la page');

            // Essayer d'extraire quelques informations
            const resultCount = await page.evaluate(() => {
                const elements = document.querySelectorAll('[class*="result"], [class*="chunk"], .passage');
                return elements.length;
            });

            console.log(`   ✓ Nombre d'éléments de résultats: ${resultCount}`);
        } else {
            console.log('   ⚠ Pas de résultats évidents trouvés');
        }

        // 8. Screenshot final
        await page.screenshot({
            path: 'C:\\GitHub\\linear_coding_library_rag\\search_results.png',
            fullPage: true
        });
        console.log('\n6. Screenshot des résultats sauvegardé');

        // 9. Vérifier les logs réseau pour la vectorisation
        console.log('\n7. Vérification de l\'utilisation du GPU embedder:');
        console.log('   → Vérifier les logs Flask pour "GPU embedder ready"');
        console.log('   → Vérifier "embed_single" dans les logs');

        console.log('\n' + '='.repeat(70));
        console.log('✓ Test terminé - Vérifiez les screenshots et logs Flask');
        console.log('='.repeat(70));

        // Garder le navigateur ouvert 5 secondes pour voir le résultat
        await new Promise(resolve => setTimeout(resolve, 5000));

        return { success: true };

    } catch (error) {
        console.error('\n✗ Erreur:', error.message);
        return { success: false, error: error.message };
    } finally {
        await browser.close();
    }
}

testSearch()
    .then(result => {
        process.exit(result.success ? 0 : 1);
    })
    .catch(err => {
        console.error('Erreur fatale:', err);
        process.exit(1);
    });
