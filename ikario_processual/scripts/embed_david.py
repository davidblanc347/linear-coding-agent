#!/usr/bin/env python3
"""
Script to generate David's embedding from his messages.
Returns JSON with the embedding vector.

Usage:
    python scripts/embed_david.py "concatenated text of david's messages"

Output (JSON):
    {"vector": [0.1, 0.2, ...], "dimension": 1024}
"""

import sys
import json
from sentence_transformers import SentenceTransformer

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No text provided"}))
        sys.exit(1)

    text = sys.argv[1]

    if len(text) < 10:
        print(json.dumps({"error": "Text too short"}))
        sys.exit(1)

    try:
        # Load BGE-M3 model (same as used for Ikario's embeddings)
        model = SentenceTransformer('BAAI/bge-m3')

        # Generate embedding
        vector = model.encode(text, normalize_embeddings=True)

        # Return as JSON
        result = {
            "vector": vector.tolist(),
            "dimension": len(vector)
        }
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
