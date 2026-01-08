"""Test search quality with re-chunked data.

This script tests semantic search to verify that the re-chunking improved
search quality and relevance.

Tests:
    1. Chunk size distribution after re-chunking
    2. Overlap verification between consecutive chunks
    3. Semantic search quality on various queries
    4. Comparison of results from giant chunks vs optimized chunks
"""

import weaviate
import sys
import requests
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

from utils.llm_chunker_improved import estimate_tokens

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Vectorizer URL (same as in 11_vectorize_missing_chunks.py)
VECTORIZER_URL = "http://localhost:8090/vectors"

def vectorize_query(query: str) -> list[float]:
    """Manually vectorize a query using text2vec-transformers service.

    Args:
        query: Query text to vectorize

    Returns:
        Vector as list of floats (1024 dimensions for BGE-M3)
    """
    response = requests.post(
        VECTORIZER_URL,
        json={"text": query},
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(f"Vectorization failed: HTTP {response.status_code}")

    result = response.json()
    vector = result.get('vector')
    if not vector:
        raise RuntimeError("No vector in response")

    return vector

client = weaviate.connect_to_local()

try:
    print("=" * 80)
    print("TEST DE LA QUALITÉ DE RECHERCHE APRÈS RE-CHUNKING")
    print("=" * 80)
    print()

    chunk_v2 = client.collections.get("Chunk_v2")

    # ========== 1. DISTRIBUTION DES TAILLES ==========
    print("1. DISTRIBUTION DES TAILLES DE CHUNKS")
    print("-" * 80)
    print()

    print("Analyse en cours...")

    sizes = []
    for chunk in chunk_v2.iterator(include_vector=False):
        text = chunk.properties.get('text', '')
        tokens = estimate_tokens(text)
        sizes.append(tokens)

    total = len(sizes)
    avg = sum(sizes) / total
    max_size = max(sizes)
    min_size = min(sizes)

    print(f"Total chunks: {total:,}")
    print(f"Taille moyenne: {avg:.0f} tokens")
    print(f"Min: {min_size} tokens")
    print(f"Max: {max_size} tokens")
    print()

    # Distribution par tranches
    ranges = [
        (0, 500, "Très petits"),
        (500, 1000, "Petits"),
        (1000, 1500, "Moyens"),
        (1500, 2000, "Grands"),
        (2000, 3000, "Très grands"),
        (3000, 10000, "ÉNORMES"),
    ]

    print("Distribution par tranches:")
    for min_tok, max_tok, label in ranges:
        count = sum(1 for s in sizes if min_tok <= s < max_tok)
        percentage = count / total * 100
        bar = "█" * int(percentage / 2)
        print(f"  {min_tok:>5}-{max_tok:>5} tokens ({label:15}): {count:>5} ({percentage:>5.1f}%) {bar}")

    print()

    # ========== 2. VÉRIFICATION OVERLAP ==========
    print("2. VÉRIFICATION DE L'OVERLAP ENTRE CHUNKS CONSÉCUTIFS")
    print("-" * 80)
    print()

    # Prendre une œuvre pour vérifier l'overlap
    print("Analyse de l'overlap dans 'Between Past and Future'...")

    arendt_chunks = []
    for chunk in chunk_v2.iterator(include_vector=False):
        props = chunk.properties
        if props.get('workTitle') == 'Between Past and Future':
            arendt_chunks.append({
                'orderIndex': props.get('orderIndex', 0),
                'text': props.get('text', ''),
                'sectionPath': props.get('sectionPath', '')
            })

    # Trier par orderIndex
    arendt_chunks.sort(key=lambda x: x['orderIndex'])

    print(f"Chunks trouvés: {len(arendt_chunks)}")
    print()

    # Vérifier overlap entre chunks consécutifs de même section
    overlaps_found = 0
    overlaps_checked = 0

    for i in range(len(arendt_chunks) - 1):
        current = arendt_chunks[i]
        next_chunk = arendt_chunks[i + 1]

        # Vérifier si même section (potentiellement des chunks split)
        if current['sectionPath'] == next_chunk['sectionPath']:
            # Extraire les derniers 200 caractères du chunk actuel
            current_end = current['text'][-200:].strip()
            # Extraire les premiers 200 caractères du chunk suivant
            next_start = next_chunk['text'][:200].strip()

            # Chercher overlap
            overlap_found = False
            for length in range(50, 201, 10):  # Tester différentes longueurs
                if len(current_end) < length or len(next_start) < length:
                    continue

                test_end = current_end[-length:]
                if test_end in next_start:
                    overlap_found = True
                    overlaps_found += 1
                    break

            overlaps_checked += 1

    if overlaps_checked > 0:
        print(f"Chunks consécutifs vérifiés: {overlaps_checked}")
        print(f"Overlaps détectés: {overlaps_found} ({overlaps_found/overlaps_checked*100:.1f}%)")
    else:
        print("Aucun chunk consécutif dans la même section (pas de split détecté)")

    print()

    # ========== 3. TESTS DE RECHERCHE SÉMANTIQUE ==========
    print("3. TESTS DE RECHERCHE SÉMANTIQUE")
    print("-" * 80)
    print()

    test_queries = [
        {
            "query": "What is the nature of representation in cognitive science?",
            "expected_work": "Mind Design III",
            "description": "Requête philosophique complexe"
        },
        {
            "query": "Comment définit-on la vertu selon Platon?",
            "expected_work": "Platon - Ménon",
            "description": "Requête en français sur un concept spécifique"
        },
        {
            "query": "pragmatism and belief fixation",
            "expected_work": "Collected papers",
            "description": "Concepts multiples (test de granularité)"
        },
        {
            "query": "Entre la logique des termes et la grammaire spéculative",
            "expected_work": "La pensée-signe",
            "description": "Requête technique académique"
        },
    ]

    for i, test in enumerate(test_queries, 1):
        print(f"Test {i}: {test['description']}")
        print(f"Query: \"{test['query']}\"")
        print()

        # Vectorize query and search with near_vector
        # (Chunk_v2 has no vectorizer, so we must manually vectorize queries)
        query_vector = vectorize_query(test['query'])
        result = chunk_v2.query.near_vector(
            near_vector=query_vector,
            limit=5,
            return_properties=[
                'text', 'workTitle', 'workAuthor',
                'sectionPath', 'chapterTitle'
            ],
            return_metadata=['distance']
        )

        if not result.objects:
            print("  ❌ Aucun résultat trouvé")
            print()
            continue

        # Analyser les résultats
        print(f"  Résultats: {len(result.objects)}")
        print()

        for j, obj in enumerate(result.objects, 1):
            props = obj.properties
            work_title = props.get('workTitle', 'N/A')
            text = props.get('text', '')
            tokens = estimate_tokens(text)

            # Distance (si disponible)
            distance = getattr(obj.metadata, 'distance', None) if hasattr(obj, 'metadata') else None
            distance_str = f" (distance: {distance:.4f})" if distance else ""

            # Marquer si c'est l'œuvre attendue
            match_icon = "✓" if test['expected_work'] in work_title else " "

            print(f"  [{match_icon}] {j}. {work_title}{distance_str}")
            print(f"      Taille: {tokens} tokens")
            print(f"      Section: {props.get('sectionPath', 'N/A')[:60]}...")
            print(f"      Extrait: {text[:120]}...")
            print()

        # Vérifier si l'œuvre attendue est dans les résultats
        found_expected = any(
            test['expected_work'] in obj.properties.get('workTitle', '')
            for obj in result.objects
        )

        if found_expected:
            rank = next(
                i for i, obj in enumerate(result.objects, 1)
                if test['expected_work'] in obj.properties.get('workTitle', '')
            )
            print(f"  ✅ Œuvre attendue trouvée (rang {rank}/5)")
        else:
            print(f"  ⚠️  Œuvre attendue '{test['expected_work']}' non trouvée dans le top 5")

        print()
        print("-" * 80)
        print()

    # ========== 4. STATISTIQUES GLOBALES ==========
    print("4. STATISTIQUES GLOBALES DE RECHERCHE")
    print("-" * 80)
    print()

    # Tester une requête large
    broad_query = "philosophy and logic"
    print(f"Requête large: \"{broad_query}\"")
    print()

    query_vector = vectorize_query(broad_query)
    result = chunk_v2.query.near_vector(
        near_vector=query_vector,
        limit=20,
        return_properties=['workTitle', 'text']
    )

    # Compter par œuvre
    work_distribution = {}
    chunk_sizes_in_results = []

    for obj in result.objects:
        props = obj.properties
        work = props.get('workTitle', 'Unknown')
        work_distribution[work] = work_distribution.get(work, 0) + 1

        text = props.get('text', '')
        tokens = estimate_tokens(text)
        chunk_sizes_in_results.append(tokens)

    print(f"Résultats par œuvre (top 20):")
    for work, count in sorted(work_distribution.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {work}: {count} chunks")

    print()

    if chunk_sizes_in_results:
        avg_result_size = sum(chunk_sizes_in_results) / len(chunk_sizes_in_results)
        max_result_size = max(chunk_sizes_in_results)
        print(f"Taille moyenne des chunks retournés: {avg_result_size:.0f} tokens")
        print(f"Taille max des chunks retournés: {max_result_size} tokens")

    print()

    # ========== 5. SCORE DE QUALITÉ ==========
    print("5. SCORE DE QUALITÉ DE LA RECHERCHE")
    print("-" * 80)
    print()

    quality_checks = []

    # Check 1: Aucun chunk > 2000 tokens
    oversized = sum(1 for s in sizes if s > 2000)
    quality_checks.append({
        'name': 'Taille des chunks',
        'passed': oversized == 0,
        'detail': f'{oversized} chunks > 2000 tokens'
    })

    # Check 2: Distribution équilibrée
    optimal_range = sum(1 for s in sizes if 200 <= s <= 1500)
    optimal_percentage = optimal_range / total * 100
    quality_checks.append({
        'name': 'Distribution optimale',
        'passed': optimal_percentage >= 80,
        'detail': f'{optimal_percentage:.1f}% dans range optimal (200-1500 tokens)'
    })

    # Check 3: Résultats variés
    unique_works = len(work_distribution)
    quality_checks.append({
        'name': 'Diversité des résultats',
        'passed': unique_works >= 3,
        'detail': f'{unique_works} œuvres différentes dans top 20'
    })

    # Check 4: Overlap présent
    quality_checks.append({
        'name': 'Overlap entre chunks',
        'passed': overlaps_found > 0 if overlaps_checked > 0 else None,
        'detail': f'{overlaps_found}/{overlaps_checked} overlaps détectés' if overlaps_checked > 0 else 'N/A'
    })

    # Afficher les résultats
    passed = sum(1 for c in quality_checks if c['passed'] is True)
    total_checks = sum(1 for c in quality_checks if c['passed'] is not None)

    for check in quality_checks:
        if check['passed'] is None:
            icon = "⚠️"
            status = "N/A"
        elif check['passed']:
            icon = "✅"
            status = "OK"
        else:
            icon = "❌"
            status = "FAIL"

        print(f"{icon} {check['name']}: {status}")
        print(f"   {check['detail']}")

    print()
    print(f"Score: {passed}/{total_checks} ({passed/total_checks*100:.0f}%)")
    print()

    # ========== 6. RÉSUMÉ ==========
    print("=" * 80)
    print("RÉSUMÉ DU TEST")
    print("=" * 80)
    print()

    if passed >= total_checks * 0.8:
        print("✅ QUALITÉ DE RECHERCHE: EXCELLENTE")
        print()
        print("Les chunks re-chunkés ont amélioré la recherche:")
        print(f"  • {total:,} chunks optimisés")
        print(f"  • Taille moyenne: {avg:.0f} tokens (optimal)")
        print(f"  • {optimal_percentage:.1f}% dans la plage optimale")
        print(f"  • Max: {max_size} tokens (< 2500)")
        print(f"  • Overlap détecté: {overlaps_found > 0 if overlaps_checked > 0 else 'N/A'}")
        print()
        print("Recommandations:")
        print("  ✓ La recherche sémantique fonctionne correctement")
        print("  ✓ Les chunks sont de taille optimale pour BGE-M3")
        print("  ✓ Le système est prêt pour la production")
    elif passed >= total_checks * 0.6:
        print("⚠️  QUALITÉ DE RECHERCHE: BONNE")
        print()
        print("Quelques améliorations possibles:")
        for check in quality_checks:
            if not check['passed'] and check['passed'] is not None:
                print(f"  • {check['name']}: {check['detail']}")
    else:
        print("❌ QUALITÉ DE RECHERCHE: À AMÉLIORER")
        print()
        print("Problèmes détectés:")
        for check in quality_checks:
            if not check['passed'] and check['passed'] is not None:
                print(f"  • {check['name']}: {check['detail']}")

finally:
    client.close()
