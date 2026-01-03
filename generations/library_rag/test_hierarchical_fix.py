"""Test hierarchical search mode after fix."""

import requests
import sys
import io
from bs4 import BeautifulSoup

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:5000"

def test_hierarchical_mode():
    """Test hierarchical search mode."""
    print("=" * 80)
    print("TEST MODE HIÉRARCHIQUE APRÈS CORRECTION")
    print("=" * 80)
    print()

    query = "What is the Turing test?"
    print(f"Query: {query}")
    print(f"Mode: hierarchical")
    print("-" * 80)

    try:
        response = requests.get(
            f"{BASE_URL}/search",
            params={"q": query, "mode": "hierarchical", "limit": 5, "sections_limit": 3},
            timeout=10
        )

        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return

        html = response.text

        # Check if hierarchical mode is active
        if "hiérarchique" in html.lower():
            print("✅ Mode hiérarchique détecté")
        else:
            print("❌ Mode hiérarchique non détecté")

        # Check for results
        if "Aucun résultat" in html:
            print("❌ Aucun résultat trouvé")
            print()

            # Check for fallback reason
            if "fallback" in html.lower():
                print("Raison de fallback présente dans la réponse")

            # Print some debug info
            if "passage" in html.lower():
                print("Le mot 'passage' est présent")
            if "section" in html.lower():
                print("Le mot 'section' est présent")

            return

        # Count passages
        passage_count = html.count("passage-card") + html.count("chunk-item")
        print(f"✅ Nombre de cartes de passage trouvées: {passage_count}")

        # Count sections
        section_count = html.count("section-group")
        print(f"✅ Nombre de groupes de sections: {section_count}")

        # Check for section headers
        if "section-header" in html:
            print("✅ Headers de section présents")

        # Check for Summary text
        if "summary-text" in html or "Résumé" in html:
            print("✅ Textes de résumé présents")

        # Check for concepts
        if "Concepts" in html or "concepts" in html:
            print("✅ Concepts affichés")

        print()
        print("=" * 80)
        print("RÉSULTAT: Mode hiérarchique fonctionne!" if passage_count > 0 else "PROBLÈME: Aucun passage trouvé")
        print("=" * 80)

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hierarchical_mode()
