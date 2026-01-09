#!/usr/bin/env python3
"""Test GPU vectorization with Mistral LLM (faster than Ollama)."""

import sys
from pathlib import Path

# Add library_rag to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

from utils.pdf_pipeline import process_pdf

# Small PDF for testing
PDF_PATH = Path(r"C:\Users\david\Philosophie\IA\Human machine\most_viewed_papers_similar_to_this_one\Turing_and_Computationalism.pdf")

print("="*70)
print("GPU Vectorization Test with Mistral LLM")
print("="*70)

if not PDF_PATH.exists():
    print(f"ERROR: PDF not found at {PDF_PATH}")
    sys.exit(1)

print(f"\n1. PDF: {PDF_PATH.name}")
print(f"   Size: {PDF_PATH.stat().st_size / 1024:.1f} KB")

print("\n2. Processing with Mistral LLM + GPU Vectorization...")

try:
    result = process_pdf(
        PDF_PATH,
        use_llm=True,
        llm_provider="mistral",  # MISTRAL instead of Ollama
        use_semantic_chunking=False,  # Faster
        use_ocr_annotations=False,
        ingest_to_weaviate=True,  # GPU vectorization happens here
    )

    print("\n3. Results:")
    if result.get("success"):
        print(f"   SUCCESS!")
        print(f"   - Document: {result.get('document_name')}")
        print(f"   - Chunks: {result.get('chunks_count')}")
        print(f"   - Cost OCR: {result.get('cost_ocr', 0):.4f} EUR")
        print(f"   - Cost LLM: {result.get('cost_llm', 0):.4f} EUR")
        print(f"   - Total: {result.get('cost_total', 0):.4f} EUR")
    else:
        print(f"   FAILED: {result.get('error')}")

except Exception as e:
    print(f"\nException: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("Check logs above for 'GPU embedder ready' message")
print("="*70)
