"""Test script for Summary mode in dropdown integration."""

import requests
import sys
import io

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:5000"

def test_summary_dropdown():
    """Test the summary mode via dropdown in /search endpoint."""
    print("=" * 80)
    print("TESTING SUMMARY MODE IN DROPDOWN")
    print("=" * 80)
    print()

    # Test queries with mode=summary
    test_cases = [
        {
            "query": "What is the Turing test?",
            "expected_doc": "Haugeland",
            "expected_icon": "🟣",
        },
        {
            "query": "Can virtue be taught?",
            "expected_doc": "Platon",
            "expected_icon": "🟢",
        },
        {
            "query": "What is pragmatism according to Peirce?",
            "expected_doc": "Tiercelin",
            "expected_icon": "🟡",
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}/3: '{test['query']}' (mode=summary)")
        print("-" * 80)

        try:
            response = requests.get(
                f"{BASE_URL}/search",
                params={"q": test["query"], "limit": 5, "mode": "summary"},
                timeout=10
            )

            if response.status_code == 200:
                # Check if expected document icon is in response
                if test["expected_icon"] in response.text:
                    print(f"✅ PASS - Found {test['expected_doc']} icon {test['expected_icon']}")
                else:
                    print(f"❌ FAIL - Expected icon {test['expected_icon']} not found")

                # Check if summary badge is present
                if "Résumés uniquement" in response.text or "90% visibilité" in response.text:
                    print("✅ PASS - Summary mode badge displayed")
                else:
                    print("❌ FAIL - Summary mode badge not found")

                # Check if results are present
                if "passage" in response.text and "trouvé" in response.text:
                    print("✅ PASS - Results displayed")
                else:
                    print("❌ FAIL - No results found")

                # Check for concepts
                if "Concepts" in response.text or "concept" in response.text:
                    print("✅ PASS - Concepts displayed")
                else:
                    print("⚠️ WARN - Concepts may not be displayed")

            else:
                print(f"❌ FAIL - HTTP {response.status_code}")

        except Exception as e:
            print(f"❌ ERROR - {e}")

        print()

    # Test that mode dropdown has summary option
    print("Test 4/4: Summary option in mode dropdown")
    print("-" * 80)
    try:
        response = requests.get(f"{BASE_URL}/search", timeout=10)
        if response.status_code == 200:
            if 'value="summary"' in response.text:
                print("✅ PASS - Summary option present in dropdown")
            else:
                print("❌ FAIL - Summary option not found in dropdown")

            if "90% visibilité" in response.text or "Résumés uniquement" in response.text:
                print("✅ PASS - Summary option label correct")
            else:
                print("⚠️ WARN - Summary option label may be missing")
        else:
            print(f"❌ FAIL - HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ ERROR - {e}")

    print()
    print("=" * 80)
    print("DROPDOWN INTEGRATION TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_summary_dropdown()
