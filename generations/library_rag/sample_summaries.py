"""Récupère des exemples de résumés générés."""
import weaviate

client = weaviate.connect_to_local()
chunk_col = client.collections.get('Chunk')

# Récupérer les 10 premiers chunks avec résumé
response = chunk_col.query.fetch_objects(limit=100)

summaries_found = 0
for obj in response.objects:
    summary = obj.properties.get('summary', '')
    if summary and summary != '':
        text = obj.properties.get('text', '')
        work = obj.properties.get('work', {})

        print("=" * 80)
        print(f"WORK: {work.get('title', 'N/A')} - {work.get('author', 'N/A')}")
        print("=" * 80)
        print(f"\nTEXTE ORIGINAL ({len(text)} chars):")
        print(text[:300] + "..." if len(text) > 300 else text)
        print(f"\nRÉSUMÉ GÉNÉRÉ ({len(summary)} chars):")
        print(summary)
        print("\n")

        summaries_found += 1
        if summaries_found >= 5:
            break

client.close()

print(f"\n✓ {summaries_found} exemples affichés")
