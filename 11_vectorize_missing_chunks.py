"""Vectorize chunks that don't have vectors.

After re-chunking, new chunks were created without vectors because Chunk_v2
collection has no vectorizer configured. This script manually vectorizes
these chunks using the text2vec-transformers service.
"""

import weaviate
import sys
import requests

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Try to import tqdm
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Text2vec-transformers service URL (from docker-compose.yml)
VECTORIZER_URL = "http://localhost:8090/vectors"

client = weaviate.connect_to_local()

try:
    print("=" * 80)
    print("VECTORISATION DES CHUNKS SANS VECTEUR")
    print("=" * 80)
    print()

    chunk_v2 = client.collections.get("Chunk_v2")

    # ========== 1. IDENTIFIER LES CHUNKS SANS VECTEUR ==========
    print("1. IDENTIFICATION DES CHUNKS SANS VECTEUR")
    print("-" * 80)
    print()

    print("Analyse en cours...")

    chunks_to_vectorize = []

    for chunk in chunk_v2.iterator(include_vector=True):
        if not chunk.vector or not chunk.vector.get('default'):
            props = chunk.properties
            chunks_to_vectorize.append({
                'uuid': chunk.uuid,
                'text': props.get('text', ''),
                'summary': props.get('summary', ''),
                'keywords': props.get('keywords', []),
                'workTitle': props.get('workTitle', 'N/A')
            })

    print(f"✓ {len(chunks_to_vectorize)} chunks sans vecteur trouvés")
    print()

    if not chunks_to_vectorize:
        print("✅ Aucun chunk à vectoriser")
        print()
        print("=" * 80)
        print("SCRIPT TERMINÉ - RIEN À FAIRE")
        print("=" * 80)
        sys.exit(0)

    # ========== 2. VECTORISATION ==========
    print("2. VECTORISATION DES CHUNKS")
    print("-" * 80)
    print()

    print(f"Service vectorizer: {VECTORIZER_URL}")
    print()

    vectorized_count = 0
    errors = []

    # Create iterator with or without tqdm
    if HAS_TQDM:
        iterator = tqdm(
            chunks_to_vectorize,
            desc="Vectorisation",
            unit="chunks"
        )
    else:
        iterator = chunks_to_vectorize
        print("Vectorisation en cours...")

    for idx, chunk_data in enumerate(iterator, 1):
        try:
            # Prepare text for vectorization
            # Combine text, summary, and keywords as per original Chunk schema
            text_parts = [chunk_data['text']]

            if chunk_data['summary']:
                text_parts.append(chunk_data['summary'])

            if chunk_data['keywords']:
                text_parts.append(' '.join(chunk_data['keywords']))

            combined_text = ' '.join(text_parts)

            # Call text2vec-transformers service
            response = requests.post(
                VECTORIZER_URL,
                json={"text": combined_text},
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code != 200:
                errors.append(f"Chunk {str(chunk_data['uuid'])[:8]}: HTTP {response.status_code}")
                continue

            result = response.json()
            vector = result.get('vector')

            if not vector:
                errors.append(f"Chunk {str(chunk_data['uuid'])[:8]}: Pas de vecteur dans la réponse")
                continue

            # Update chunk with vector
            chunk_v2.data.update(
                uuid=chunk_data['uuid'],
                vector=vector
            )

            vectorized_count += 1

            # Progress without tqdm
            if not HAS_TQDM and idx % 10 == 0:
                print(f"  {idx}/{len(chunks_to_vectorize)} chunks vectorisés...")

        except requests.exceptions.RequestException as e:
            errors.append(f"Chunk {str(chunk_data['uuid'])[:8]}: Erreur réseau - {e}")
        except Exception as e:
            errors.append(f"Chunk {str(chunk_data['uuid'])[:8]}: {e}")

    print()
    print("-" * 80)
    print(f"✓ Chunks vectorisés: {vectorized_count}/{len(chunks_to_vectorize)}")

    if errors:
        print()
        print(f"⚠️  Erreurs rencontrées: {len(errors)}")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... et {len(errors) - 10} autres")

    print()

    # ========== 3. VÉRIFICATION ==========
    print("3. VÉRIFICATION POST-VECTORISATION")
    print("-" * 80)
    print()

    print("Recomptage...")
    remaining_without_vector = 0
    total_chunks = 0

    for chunk in chunk_v2.iterator(include_vector=True):
        total_chunks += 1
        if not chunk.vector or not chunk.vector.get('default'):
            remaining_without_vector += 1

    chunks_with_vector = total_chunks - remaining_without_vector

    print(f"✓ Total chunks: {total_chunks:,}")
    print(f"✓ Avec vecteur: {chunks_with_vector:,} ({chunks_with_vector/total_chunks*100:.1f}%)")
    print(f"✓ Sans vecteur: {remaining_without_vector:,}")

    print()

    if remaining_without_vector == 0:
        print("✅ Tous les chunks ont été vectorisés!")
    else:
        print(f"⚠️  {remaining_without_vector} chunks encore sans vecteur")
        print("   Relancer le script ou vérifier les erreurs")

    print()
    print("=" * 80)
    print("VECTORISATION TERMINÉE")
    print("=" * 80)
    print()

    if remaining_without_vector == 0:
        print("✅ VECTORISATION RÉUSSIE")
        print()
        print("RÉSULTATS:")
        print(f"  • {vectorized_count} nouveaux vecteurs créés")
        print(f"  • {total_chunks:,} chunks totaux")
        print(f"  • 100% des chunks ont des vecteurs")
        print()
        print("PROCHAINES ÉTAPES:")
        print("  1. Relancer le test de recherche: python 10_test_search_quality.py")
        print("  2. Tester l'application Flask")
        print()
        print("NOTE: Chunk_v2 n'a toujours pas de vectorizer configuré.")
        print("Les futurs nouveaux chunks devront être vectorisés manuellement")
        print("OU la collection devra être recréée avec un vectorizer.")
    elif vectorized_count > 0:
        print("⚠️  VECTORISATION PARTIELLE")
        print()
        print(f"  • {vectorized_count} chunks vectorisés")
        print(f"  • {remaining_without_vector} chunks restants")
        print("  • Vérifier les erreurs et relancer")
    else:
        print("❌ VECTORISATION ÉCHOUÉE")
        print()
        print("Aucun chunk n'a pu être vectorisé.")
        print("Vérifications:")
        print(f"  1. Service text2vec-transformers actif: {VECTORIZER_URL}")
        print("  2. Docker containers en cours d'exécution")
        print("  3. Logs des erreurs ci-dessus")

finally:
    client.close()
