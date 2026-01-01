#!/usr/bin/env python3
"""Test script for hierarchical search auto-detection."""

import sys

# Fix encoding for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from flask_app import should_use_hierarchical_search

print("=" * 60)
print("TEST AUTO-DÉTECTION RECHERCHE HIÉRARCHIQUE")
print("=" * 60)
print()

test_queries = [
    ("justice", False, "Requête courte, 1 concept"),
    ("Qu'est-ce que la justice selon Platon ?", True, "Requête longue ≥15 chars"),
    ("vertu et sagesse", True, "Multi-concepts avec connecteur 'et'"),
    ("la mort", False, "Requête courte avec stop words"),
    ("âme immortelle", True, "2+ mots significatifs"),
    ("Peirce", False, "Nom propre seul, court"),
    ("Comment atteindre le bonheur ?", True, "Question philosophique ≥15 chars"),
]

print(f"{'Requête':<45} {'Attendu':<10} {'Obtenu':<10} {'Statut'}")
print("-" * 75)

all_passed = True
for query, expected, reason in test_queries:
    result = should_use_hierarchical_search(query)
    status = "✅ PASS" if result == expected else "❌ FAIL"
    if result != expected:
        all_passed = False

    print(f"{query:<45} {expected!s:<10} {result!s:<10} {status}")
    print(f"  Raison : {reason}")
    print()

print("=" * 60)
if all_passed:
    print("✅ TOUS LES TESTS PASSENT")
else:
    print("❌ CERTAINS TESTS ONT ÉCHOUÉ")
print("=" * 60)
