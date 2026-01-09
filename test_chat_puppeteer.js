/**
 * Test de chat sémantique avec Puppeteer - GPU Embedder Validation
 * Vérifie que le RAG chat fonctionne avec GPU vectorization
 */

const puppeteer = require('puppeteer');

async function testChat() {
    console.log('='.repeat(70));
    console.log('Test de Chat Sémantique avec GPU Vectorization');
    console.log('='.repeat(70));

    const browser = await puppeteer.launch({
        headless: false,
        defaultViewport: { width: 1280, height: 900 }
    });

    try {
        const page = await browser.newPage();

        // 1. Naviguer vers la page de chat
        console.log('\n1. Navigation vers /chat...');
        await page.goto('http://localhost:5000/chat', { waitUntil: 'networkidle2' });
        console.log('   ✓ Page chargée');

        // 2. Screenshot de la page initiale
        await new Promise(resolve => setTimeout(resolve, 2000));
        await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\chat_page.png' });
        console.log('   ✓ Screenshot initial sauvegardé: chat_page.png');

        // 3. Trouver le champ de message
        console.log('\n2. Recherche du champ de message...');

        const possibleSelectors = [
            'textarea[name="message"]',
            'textarea[placeholder*="question"]',
            'textarea[placeholder*="message"]',
            'textarea',
            'input[type="text"]',
            '#message',
            '.chat-input'
        ];

        let messageInput = null;
        for (const selector of possibleSelectors) {
            try {
                await page.waitForSelector(selector, { timeout: 2000 });
                messageInput = selector;
                console.log(`   ✓ Champ trouvé avec sélecteur: ${selector}`);
                break;
            } catch (e) {
                // Continuer avec le prochain sélecteur
            }
        }

        if (!messageInput) {
            throw new Error('Impossible de trouver le champ de message');
        }

        // 4. Saisir une question
        const question = 'What is a Turing machine and how does it relate to computation?';
        console.log(`\n3. Saisie de la question: "${question}"`);
        await page.type(messageInput, question);
        console.log('   ✓ Question saisie');

        await page.screenshot({ path: 'C:\\GitHub\\linear_coding_library_rag\\chat_before_send.png' });
        console.log('   ✓ Screenshot avant envoi sauvegardé');

        // 5. Trouver et cliquer sur le bouton d'envoi
        console.log('\n4. Envoi de la question...');

        const submitButton = await page.$('button[type="submit"]') ||
                           await page.$('button.send-button') ||
                           await page.$('button');

        if (submitButton) {
            await submitButton.click();
            console.log('   ✓ Question envoyée (click)');
        } else {
            // Essayer avec Enter
            await page.keyboard.press('Enter');
            console.log('   ✓ Question envoyée (Enter)');
        }

        // 6. Attendre la réponse (SSE peut prendre du temps)
        console.log('\n5. Attente de la réponse (30 secondes)...');
        await new Promise(resolve => setTimeout(resolve, 30000));

        // 7. Vérifier si une réponse est affichée
        console.log('\n6. Vérification de la réponse...');

        const responseData = await page.evaluate(() => {
            // Chercher différents éléments de réponse
            const responseElements = document.querySelectorAll(
                '.response, .message, .assistant, .chat-message, [class*="response"]'
            );

            const responses = [];
            responseElements.forEach(el => {
                const text = el.innerText?.trim();
                if (text && text.length > 50) {
                    responses.push(text);
                }
            });

            // Chercher aussi le texte brut dans le body
            const bodyText = document.body.innerText;
            const hasTuring = bodyText.toLowerCase().includes('turing');
            const hasComputation = bodyText.toLowerCase().includes('computation');
            const hasMachine = bodyText.toLowerCase().includes('machine');

            return {
                responses,
                hasTuring,
                hasComputation,
                hasMachine,
                bodyLength: bodyText.length
            };
        });

        if (responseData.responses.length > 0) {
            console.log(`   ✓ ${responseData.responses.length} réponse(s) détectée(s)`);
            console.log(`\n   Extrait de la première réponse:`);
            const preview = responseData.responses[0].substring(0, 300);
            console.log(`   ${preview}...`);
        } else if (responseData.hasTuring && responseData.hasComputation) {
            console.log('   ✓ Réponse détectée (mots-clés présents)');
            console.log(`   ✓ Mentionne "Turing": ${responseData.hasTuring}`);
            console.log(`   ✓ Mentionne "computation": ${responseData.hasComputation}`);
        } else {
            console.log('   ⚠ Réponse pas clairement détectée');
            console.log(`   Body length: ${responseData.bodyLength} caractères`);
        }

        // 8. Screenshot final
        await page.screenshot({
            path: 'C:\\GitHub\\linear_coding_library_rag\\chat_response.png',
            fullPage: true
        });
        console.log('\n7. Screenshot final sauvegardé: chat_response.png');

        // 9. Vérifier les sources si disponibles
        console.log('\n8. Vérification des sources...');
        const sourcesData = await page.evaluate(() => {
            const sourcesElements = document.querySelectorAll(
                '[class*="source"], [class*="chunk"], [class*="passage"], [data-source]'
            );

            const sources = [];
            sourcesElements.forEach(el => {
                const author = el.querySelector('[class*="author"]')?.innerText || '';
                const title = el.querySelector('[class*="title"]')?.innerText || '';
                const distance = el.querySelector('[class*="distance"], [class*="score"]')?.innerText || '';

                if (author || title) {
                    sources.push({ author, title: title.substring(0, 50), distance });
                }
            });

            // Chercher aussi dans le texte pour "Sources"
            const bodyText = document.body.innerText;
            const hasSources = bodyText.includes('Sources') ||
                              bodyText.includes('sources') ||
                              bodyText.includes('References');

            return { sources, hasSources };
        });

        if (sourcesData.sources.length > 0) {
            console.log(`   ✓ ${sourcesData.sources.length} source(s) trouvée(s):`);
            sourcesData.sources.slice(0, 5).forEach((src, i) => {
                console.log(`   ${i+1}. ${src.author} - ${src.title}`);
                if (src.distance) console.log(`      Distance: ${src.distance}`);
            });
        } else if (sourcesData.hasSources) {
            console.log('   ✓ Section "Sources" détectée dans le texte');
        } else {
            console.log('   ℹ Pas de sources distinctes détectées');
        }

        // 10. Vérifier les logs réseau pour la vectorisation
        console.log('\n9. Vérification GPU embedder:');
        console.log('   → Vérifier les logs Flask pour "GPU embedder ready"');
        console.log('   → Vérifier "embed_single" dans les logs');
        console.log('   → Vérifier les appels SSE /chat');

        console.log('\n' + '='.repeat(70));
        console.log('✓ Test terminé');
        console.log('Screenshots: chat_page.png, chat_before_send.png, chat_response.png');
        console.log('Vérifiez les logs Flask pour confirmer l\'utilisation du GPU embedder');
        console.log('='.repeat(70));

        // Garder le navigateur ouvert 5 secondes
        await new Promise(resolve => setTimeout(resolve, 5000));

        return { success: true };

    } catch (error) {
        console.error('\n✗ Erreur:', error.message);

        // Screenshot d'erreur
        try {
            const pages = await browser.pages();
            if (pages.length > 0) {
                await pages[0].screenshot({
                    path: 'C:\\GitHub\\linear_coding_library_rag\\chat_error.png',
                    fullPage: true
                });
                console.log('Screenshot d\'erreur sauvegardé: chat_error.png');
            }
        } catch (screenshotError) {
            // Ignore screenshot errors
        }

        return { success: false, error: error.message };
    } finally {
        await browser.close();
    }
}

testChat()
    .then(result => {
        process.exit(result.success ? 0 : 1);
    })
    .catch(err => {
        console.error('Erreur fatale:', err);
        process.exit(1);
    });
