"""Correctif: Ajouter workAuthor, year, language aux Summary_v2."""

import weaviate
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Try to import tqdm
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

client = weaviate.connect_to_local()

try:
    print("=" * 80)
    print("CORRECTIF: AJOUTER workAuthor, year, language À SUMMARY_V2")
    print("=" * 80)
    print()

    summary_v2 = client.collections.get("Summary_v2")
    work_collection = client.collections.get("Work")

    # Build workTitle → Work metadata map
    print("Étape 1: Mapping workTitle → Work metadata")
    print("-" * 80)

    work_map = {}

    for work in work_collection.iterator(include_vector=False):
        props = work.properties
        title = props.get("title")
        if title:
            work_map[title] = {
                "author": props.get("author", "Unknown"),
                "year": props.get("year", 0),
                "language": props.get("language", "en"),
            }

    print(f"✓ {len(work_map)} mappings workTitle → metadata")
    print()

    # Count total summaries
    print("Étape 2: Comptage summaries")
    print("-" * 80)

    print("Comptage en cours...")
    total_summaries = sum(1 for _ in summary_v2.iterator(include_vector=False))

    print(f"✓ {total_summaries} summaries à corriger")
    print()

    # Update summaries
    print("Étape 3: Mise à jour des propriétés")
    print("-" * 80)
    print()

    updated = 0
    skipped = 0
    errors = []

    # Create iterator with or without tqdm
    if HAS_TQDM:
        iterator = tqdm(
            summary_v2.iterator(include_vector=False),
            total=total_summaries,
            desc="Mise à jour",
            unit="summaries"
        )
    else:
        iterator = summary_v2.iterator(include_vector=False)
        print("Mise à jour en cours...")

    for idx, summary in enumerate(iterator, 1):
        props = summary.properties

        try:
            work_title = props.get("workTitle")

            if not work_title:
                errors.append(f"Summary {summary.uuid}: pas de workTitle")
                skipped += 1
                continue

            # Get work metadata
            work_metadata = work_map.get(work_title)
            if not work_metadata:
                errors.append(f"Summary {summary.uuid}: Work '{work_title}' introuvable")
                skipped += 1
                continue

            # Check if already updated (workAuthor exists)
            if props.get("workAuthor") is not None:
                skipped += 1
                continue

            # Update properties
            summary_v2.data.update(
                uuid=summary.uuid,
                properties={
                    "workAuthor": work_metadata["author"],
                    "year": work_metadata["year"],
                    "language": work_metadata["language"],
                }
            )

            updated += 1

            # Progress without tqdm
            if not HAS_TQDM and idx % 10 == 0:
                print(f"  {idx}/{total_summaries} summaries traités...")

        except Exception as e:
            errors.append(f"Summary {summary.uuid}: {e}")

    print()
    print("-" * 80)
    print(f"✓ Total mis à jour: {updated}/{total_summaries}")
    print(f"  Déjà à jour: {skipped}")

    if errors:
        print(f"⚠️  Erreurs rencontrées: {len(errors)}")
        print()
        print("Premières erreurs:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... et {len(errors) - 10} autres")

    print()
    print("=" * 80)
    print("CORRECTIF TERMINÉ")
    print("=" * 80)
    print()

    if updated == total_summaries:
        print("✅ Tous les summaries ont été mis à jour")
        print()
        print("Propriétés ajoutées:")
        print("  ✓ workAuthor (auteur de l'œuvre)")
        print("  ✓ year (année de publication)")
        print("  ✓ language (langue du texte)")
        print()
        print("VÉRIFICATION:")
        print("  python -c \"from verify_summaries import verify; verify()\"")
    elif updated > 0:
        print(f"⚠️  {updated}/{total_summaries} summaries mis à jour")
        print("  Vérifier les erreurs")
    else:
        print("❌ Aucun summary mis à jour")
        print("  Corriger les erreurs et relancer")

finally:
    client.close()
