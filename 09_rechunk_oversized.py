"""Script to re-chunk oversized chunks (> 2000 tokens) in Chunk_v2.

This script identifies chunks that are too large (> 2000 tokens) and splits them
into smaller chunks with overlap (max 1000 words, overlap 100 words).

Steps:
    1. Identify all chunks > 2000 tokens in Chunk_v2
    2. Re-chunk using simple_chunk_with_overlap (1000 words max, 100 overlap)
    3. Delete the original oversized chunk
    4. Insert new smaller chunks with preserved metadata
    5. Update Summary_v2 chunksCount if needed
"""

import weaviate
import sys
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

from utils.llm_chunker_improved import simple_chunk_with_overlap, estimate_tokens

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Try to import tqdm
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Constants
TOKEN_THRESHOLD = 2000  # Chunks > 2000 tokens will be re-chunked
MAX_WORDS = 1000
OVERLAP_WORDS = 100

client = weaviate.connect_to_local()

try:
    print("=" * 80)
    print("RE-CHUNKING DES CHUNKS SURDIMENSIONNÉS")
    print("=" * 80)
    print()

    chunk_v2 = client.collections.get("Chunk_v2")
    work_collection = client.collections.get("Work")

    # ========== 1. IDENTIFIER LES CHUNKS PROBLÉMATIQUES ==========
    print("1. IDENTIFICATION DES CHUNKS > 2000 TOKENS")
    print("-" * 80)
    print()

    oversized_chunks = []

    print("Analyse en cours...")
    for chunk in chunk_v2.iterator(include_vector=False):
        props = chunk.properties
        text = props.get('text', '')
        tokens = estimate_tokens(text)

        if tokens > TOKEN_THRESHOLD:
            oversized_chunks.append({
                'uuid': str(chunk.uuid),
                'tokens': tokens,
                'chars': len(text),
                'text': text,
                'workTitle': props.get('workTitle', ''),
                'workAuthor': props.get('workAuthor', ''),
                'year': props.get('year', 0),
                'language': props.get('language', 'en'),
                'sectionPath': props.get('sectionPath', ''),
                'chapterTitle': props.get('chapterTitle', ''),
                'canonicalReference': props.get('canonicalReference', ''),
                'unitType': props.get('unitType', 'main_content'),
                'keywords': props.get('keywords', []),
                'orderIndex': props.get('orderIndex', 0),
            })

    print(f"✓ {len(oversized_chunks)} chunks > {TOKEN_THRESHOLD} tokens trouvés")
    print()

    if not oversized_chunks:
        print("✅ Aucun chunk surdimensionné à traiter")
        print()
        print("=" * 80)
        print("SCRIPT TERMINÉ - RIEN À FAIRE")
        print("=" * 80)
        sys.exit(0)

    # Trier par taille
    oversized_chunks.sort(key=lambda x: x['tokens'], reverse=True)

    print("Top 5 plus gros chunks:")
    for i, chunk in enumerate(oversized_chunks[:5], 1):
        print(f"{i}. {chunk['tokens']:,} tokens ({chunk['chars']:,} chars)")
        print(f"   Œuvre: {chunk['workTitle']}")
        print(f"   Section: {chunk['sectionPath'][:60]}...")
        print()

    if len(oversized_chunks) > 5:
        print(f"... et {len(oversized_chunks) - 5} autres")

    print()

    # ========== 2. RE-CHUNKING ==========
    print("2. RE-CHUNKING AVEC OVERLAP")
    print("-" * 80)
    print()

    # Build work_title -> work_uuid map for references
    work_map = {}
    for work in work_collection.iterator(include_vector=False):
        props = work.properties
        title = props.get("title")
        if title:
            work_map[title] = str(work.uuid)

    print(f"✓ {len(work_map)} Works mappés")
    print()

    deleted_count = 0
    inserted_count = 0
    errors = []

    # Create iterator with or without tqdm
    if HAS_TQDM:
        iterator = tqdm(
            oversized_chunks,
            desc="Re-chunking",
            unit="chunks"
        )
    else:
        iterator = oversized_chunks
        print("Re-chunking en cours...")

    for idx, old_chunk in enumerate(iterator, 1):
        try:
            # Re-chunk text
            new_texts = simple_chunk_with_overlap(
                old_chunk['text'],
                max_words=MAX_WORDS,
                overlap_words=OVERLAP_WORDS
            )

            # Get work reference
            work_uuid = work_map.get(old_chunk['workTitle'])
            if not work_uuid:
                errors.append(f"Chunk {old_chunk['uuid'][:8]}: Work '{old_chunk['workTitle']}' introuvable")
                continue

            # Insert new chunks
            for i, new_text in enumerate(new_texts):
                # Sub-ordering: multiply base index by 100 and add part index
                # Example: orderIndex=5 becomes 500, 501, 502, etc.
                new_order_index = (old_chunk['orderIndex'] * 100) + i

                new_props = {
                    "text": new_text,
                    "summary": "",  # Empty summary for simple chunks
                    "keywords": old_chunk['keywords'],
                    "workTitle": old_chunk['workTitle'],
                    "workAuthor": old_chunk['workAuthor'],
                    "year": old_chunk['year'],
                    "language": old_chunk['language'],
                    "sectionPath": old_chunk['sectionPath'],
                    "chapterTitle": old_chunk['chapterTitle'],
                    "canonicalReference": old_chunk['canonicalReference'],
                    "unitType": old_chunk['unitType'],
                    "orderIndex": new_order_index,
                }

                chunk_v2.data.insert(
                    properties=new_props,
                    references={"work": work_uuid}
                )
                inserted_count += 1

            # Delete old chunk
            chunk_v2.data.delete_by_id(old_chunk['uuid'])
            deleted_count += 1

            # Progress without tqdm
            if not HAS_TQDM and idx % 5 == 0:
                print(f"  {idx}/{len(oversized_chunks)} chunks traités...")

        except Exception as e:
            errors.append(f"Chunk {old_chunk['uuid'][:8]}: {e}")

    print()
    print("-" * 80)
    print(f"✓ Chunks supprimés: {deleted_count}")
    print(f"✓ Nouveaux chunks créés: {inserted_count}")
    if deleted_count > 0:
        print(f"  Expansion moyenne: {inserted_count / deleted_count:.1f}x")
    else:
        print(f"  ⚠️  Aucun chunk supprimé - vérifier les erreurs")

    if errors:
        print()
        print(f"⚠️  Erreurs rencontrées: {len(errors)}")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... et {len(errors) - 10} autres")

    print()

    # ========== 3. VÉRIFICATION ==========
    print("3. VÉRIFICATION POST-RECHUNKING")
    print("-" * 80)
    print()

    print("Comptage des nouveaux chunks...")
    remaining_oversized = 0
    total_chunks = 0

    for chunk in chunk_v2.iterator(include_vector=False):
        total_chunks += 1
        text = chunk.properties.get('text', '')
        tokens = estimate_tokens(text)
        if tokens > TOKEN_THRESHOLD:
            remaining_oversized += 1

    print(f"✓ Total chunks: {total_chunks:,}")
    print(f"✓ Chunks > {TOKEN_THRESHOLD} tokens: {remaining_oversized}")

    if remaining_oversized == 0:
        print()
        print("✅ Aucun chunk surdimensionné restant!")
    else:
        print()
        print(f"⚠️  {remaining_oversized} chunks encore > {TOKEN_THRESHOLD} tokens")
        print("   Relancer le script si nécessaire")

    print()
    print("=" * 80)
    print("RE-CHUNKING TERMINÉ")
    print("=" * 80)
    print()

    print("RÉSULTATS:")
    print(f"  • Chunks supprimés: {deleted_count}")
    print(f"  • Nouveaux chunks créés: {inserted_count}")
    if deleted_count > 0:
        print(f"  • Expansion: {inserted_count / deleted_count:.1f}x")
    print(f"  • Chunks restants > {TOKEN_THRESHOLD} tokens: {remaining_oversized}")
    print()

    if remaining_oversized == 0 and deleted_count > 0:
        print("✅ RE-CHUNKING RÉUSSI")
        print()
        print("AMÉLIORATIONS:")
        print(f"  • {deleted_count} chunks géants éliminés")
        print(f"  • {inserted_count} chunks optimaux créés")
        print(f"  • Taille max: {MAX_WORDS} mots (~{MAX_WORDS * 2.5:.0f} tokens)")
        print(f"  • Overlap: {OVERLAP_WORDS} mots (contexte préservé)")
        print()
        print("PROCHAINES ÉTAPES:")
        print("  1. Tester la recherche sémantique")
        print("  2. Vérifier la qualité des vecteurs")
        print("  3. Optionnel: Mettre à jour Summary_v2.chunksCount si nécessaire")
    elif deleted_count == 0:
        print("ℹ️  Aucun chunk n'a nécessité de re-chunking")

finally:
    client.close()
