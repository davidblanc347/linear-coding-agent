"""Script pour vérifier la progression de la génération de résumés."""

import json
import sys
from datetime import datetime
from pathlib import Path

import weaviate

# Fix encoding
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROGRESS_FILE = Path("summary_generation_progress.json")

print("=" * 80)
print("PROGRESSION GÉNÉRATION DE RÉSUMÉS")
print("=" * 80)

# Lire la progression
if not PROGRESS_FILE.exists():
    print("\n⚠ Aucune progression sauvegardée")
    print("  → Lancez resume_summaries.bat pour démarrer")
    sys.exit(0)

with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
    progress = json.load(f)

processed = progress["total_processed"]
last_update = progress.get("last_update", "N/A")

print(f"\n📊 Chunks traités      : {processed}")
print(f"🕒 Dernière MAJ        : {last_update}")

# Connexion Weaviate pour vérifier le total
try:
    client = weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051)

    chunk_collection = client.collections.get("Chunk")
    all_chunks = chunk_collection.query.fetch_objects(limit=10000)

    without_summary = sum(1 for obj in all_chunks.objects if not obj.properties.get("summary", ""))
    total = len(all_chunks.objects)
    with_summary = total - without_summary

    print(f"\n📈 Total chunks        : {total}")
    print(f"✓  Avec résumé        : {with_summary} ({with_summary/total*100:.1f}%)")
    print(f"⏳ Sans résumé        : {without_summary} ({without_summary/total*100:.1f}%)")

    if without_summary > 0:
        print(f"\n🎯 Progression estimée : {with_summary}/{total} chunks")
        print(f"   Reste à traiter     : {without_summary} chunks")

        # Estimation temps restant (basé sur 50s/chunk)
        time_remaining_hours = (without_summary * 50) / 3600
        print(f"   ETA (~50s/chunk)    : {time_remaining_hours:.1f} heures")
    else:
        print("\n✅ TERMINÉ ! Tous les chunks ont un résumé !")

    client.close()

except Exception as e:
    print(f"\n⚠ Erreur connexion Weaviate: {e}")

print("\n" + "=" * 80)
print("Pour relancer la génération : resume_summaries.bat")
print("=" * 80)
