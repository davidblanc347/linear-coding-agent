# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**Library RAG** is a production-grade RAG system specialized in indexing and semantic search of philosophical and academic texts. It provides a complete pipeline from PDF upload through OCR, intelligent LLM-based extraction, to vectorized search in Weaviate.

**Core Architecture:**
- **Vector Database**: Weaviate 1.34.4 with manual GPU vectorization (BAAI/bge-m3, 1024-dim)
- **Embeddings**: Python GPU embedder (PyTorch CUDA, RTX 4070, FP16) for both ingestion and queries
- **OCR**: Mistral OCR API (~0.003€/page)
- **LLM**: Ollama (local, free) or Mistral API (fast, paid)
- **Web Interface**: Flask 3.0 with Server-Sent Events for real-time progress
- **Infrastructure**: Docker Compose (Weaviate only, text2vec-transformers optional)

**Migration Notes:**
- **Jan 2026**: Migrated from Docker text2vec-transformers to Python GPU embedder for 10-20x faster ingestion
- **Dec 2024**: Migrated from MiniLM-L6 (384-dim) to BGE-M3 (1024-dim) for superior multilingual support

## Common Commands

### Development Setup

```bash
# Windows
init.bat

# Linux/macOS
./init.sh

# Manual setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
docker compose up -d
python schema.py
```

### Running the Application

```bash
# Start Weaviate (must be running first)
docker compose up -d

# Create schema (first time only)
python schema.py

# Start Flask web interface
python flask_app.py
# Access at http://localhost:5000

# Process a PDF programmatically
python -c "from utils.pdf_pipeline import process_pdf; from pathlib import Path; process_pdf(Path('input/document.pdf'))"
```

### Type Checking and Testing

```bash
# Run mypy strict type checking
mypy .
mypy utils/pdf_pipeline.py  # Check specific module

# Run all tests
pytest

# Run specific test file
pytest tests/utils/test_ocr_schemas.py -v

# Run with coverage
pytest --cov=utils --cov-report=html
```

### Docker Operations

```bash
# Start services
docker compose up -d

# Check Weaviate status
curl http://localhost:8080/v1/.well-known/ready

# View logs
docker compose logs weaviate
docker compose logs text2vec-transformers

# Stop services
docker compose down

# Remove volumes (WARNING: deletes all data)
docker compose down -v
```

### MCP Server (Claude Desktop Integration)

```bash
# Run MCP server
python mcp_server.py

# Test MCP tools
python -c "from mcp_tools.parse_pdf import parse_pdf_tool; parse_pdf_tool({'pdf_path': 'input/test.pdf'})"
```

## High-Level Architecture

### PDF Processing Pipeline (10 Steps)

The core of the application is `utils/pdf_pipeline.py`, which orchestrates a 10-step intelligent pipeline:

```
[1] OCR (ocr_processor.py)
    ↓ Extract text + images via Mistral OCR (~0.003€/page)
[2] Markdown (markdown_builder.py)
    ↓ Build structured markdown from OCR
[3] Images (image_extractor.py)
    ↓ Save images to output/images/
[4] Metadata (llm_metadata.py)
    ↓ LLM extracts title, author, year, language
[5] TOC (llm_toc.py)
    ↓ LLM extracts hierarchical table of contents
[6] Classify (llm_classifier.py)
    ↓ Classify sections (main_content, preface, bibliography, etc.)
[7] Chunking (llm_chunker.py)
    ↓ LLM semantic chunking into argumentative units
[8] Cleaning (llm_cleaner.py)
    ↓ Remove OCR artifacts, validate chunk length
[9] Validation (llm_validator.py)
    ↓ LLM validation + concept/keyword extraction
[10] Ingestion (weaviate_ingest.py)
    ↓ Batch insert + auto-vectorization in Weaviate
```

**Key Parameters:**
- `skip_ocr=True` - Reuse existing markdown (avoid OCR cost)
- `use_llm=True` - Enable LLM processing steps
- `llm_provider="ollama"|"mistral"` - Choose LLM provider
- `use_semantic_chunking=True` - LLM-based chunking (slower, higher quality)
- `use_ocr_annotations=True` - OCR with annotations (3x cost, better TOC)
- `ingest_to_weaviate=True` - Insert chunks into Weaviate

### Weaviate Schema (3 Collections)

Defined in `schema.py`, the database uses a denormalized design with nested objects:

```
Work (no vectorizer)
  title, author, year, language, genre
  │
  ├─► Chunk_v2 (manual GPU vectorization) ⭐ PRIMARY
  │     text (VECTORIZED)
  │     keywords (VECTORIZED)
  │     workTitle, workAuthor, sectionPath, chapterTitle, unitType, orderIndex
  │     work: {title, author} (nested)
  │
  └─► Summary_v2 (manual GPU vectorization)
        text (VECTORIZED)
        concepts (VECTORIZED)
        sectionPath, title, level, chunksCount
        work: {title, author} (nested)
```

**Vectorization Strategy:**
- Only `Chunk_v2.text`, `Chunk_v2.keywords`, `Summary_v2.text`, `Summary_v2.concepts` are vectorized
- Manual vectorization with Python GPU embedder (BAAI/bge-m3, 1024-dim, RTX 4070)
- Metadata fields use `skip_vectorization=True` for filtering performance
- Nested objects avoid joins for efficient single-query retrieval
- BAAI/bge-m3 model: 1024 dimensions, 8192 token context

### Module Organization

```
library_rag/
├── flask_app.py              # Flask web app (38 KB) - routes, SSE, job queue
├── schema.py                 # Weaviate schema definition + management
├── docker-compose.yml        # Weaviate + text2vec-transformers config
│
├── utils/                    # Pipeline modules (all strictly typed)
│   ├── types.py              # Central TypedDict definitions (31 KB)
│   ├── pdf_pipeline.py       # Main orchestration (64 KB)
│   │
│   ├── mistral_client.py     # Mistral OCR API client
│   ├── ocr_processor.py      # OCR processing logic
│   ├── ocr_schemas.py        # OCR response types
│   │
│   ├── llm_structurer.py     # LLM infrastructure (Ollama/Mistral)
│   ├── llm_metadata.py       # Step 4: Metadata extraction
│   ├── llm_toc.py            # Step 5: TOC extraction
│   ├── llm_classifier.py     # Step 6: Section classification
│   ├── llm_chunker.py        # Step 7: Semantic chunking
│   ├── llm_cleaner.py        # Step 8: Chunk cleaning
│   ├── llm_validator.py      # Step 9: Validation + concepts
│   │
│   ├── markdown_builder.py   # Step 2: Markdown construction
│   ├── image_extractor.py    # Step 3: Image extraction
│   ├── hierarchy_parser.py   # Hierarchical TOC parsing
│   ├── weaviate_ingest.py    # Step 10: Database ingestion
│   │
│   └── toc_extractor*.py     # Alternative TOC strategies
│
├── mcp_server.py             # MCP server for Claude Desktop
├── mcp_tools/                # MCP tool implementations
│   ├── parse_pdf.py
│   └── search.py
│
├── templates/                # Jinja2 templates
│   ├── upload.html           # PDF upload form
│   ├── upload_progress.html  # SSE progress display
│   ├── search.html           # Semantic search interface
│   └── ...
│
└── tests/                    # Unit tests
    └── utils/
```

### Type Safety System

**Critical Rule:** All code MUST pass `mypy --strict`. This is non-negotiable.

**Type Definitions (`utils/types.py`):**
- `Metadata` - Document metadata (title, author, year, language)
- `TOCEntry` - Hierarchical table of contents entries
- `ChunkData` - Processed chunk with metadata
- `PipelineResult` - Complete pipeline result dict
- `LLMProvider` - Literal["ollama", "mistral"]
- `SectionType` - 12 section classification types
- `UnitType` - 10 chunk unit types (argument, definition, etc.)
- `ProgressCallback` - Protocol for progress reporting

**Configuration (`mypy.ini`):**
- Strict mode enabled globally
- Google-style docstrings required
- Per-module overrides for gradual migration
- Third-party libraries (weaviate, mistralai) have ignore_missing_imports

**When adding new code:**
1. Define types in `utils/types.py` first
2. Add type annotations to all functions/methods
3. Run `mypy .` before committing
4. Write Google-style docstrings

## Flask Application Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Homepage with collection statistics |
| `/passages` | GET | Browse all chunks (paginated) |
| `/search` | GET | Semantic search interface |
| `/upload` | GET | PDF upload form |
| `/upload` | POST | Start PDF processing job |
| `/upload/progress/<job_id>` | GET | SSE stream for job progress |
| `/upload/status/<job_id>` | GET | JSON job status |
| `/upload/result/<job_id>` | GET | Processing results page |
| `/documents` | GET | List all processed documents |
| `/documents/<doc>/view` | GET | Document details view |
| `/documents/delete/<doc>` | POST | Delete document + chunks |
| `/output/<filepath>` | GET | Download processed files |

**Server-Sent Events (SSE):** The upload progress route streams real-time updates for each pipeline step using Flask's `stream_with_context`.

## Cost Management

**OCR Costs (Mistral API):**
- Standard: ~0.001-0.003€/page
- With annotations: ~0.009€/page (3x, better TOC)

**LLM Costs:**
- Ollama (local): FREE (slower, requires GPU/powerful CPU)
- Mistral API: Variable (fast, production-ready)

**Best Practices:**
1. Use `skip_ocr=True` when re-processing existing documents
2. Use Ollama for development/testing
3. Use Mistral API for production
4. Check `<doc>_chunks.json` for cost tracking: `cost_ocr`, `cost_llm`, `cost_total`

## Development Workflow

### Adding a New Pipeline Step

1. Create module in `utils/` (e.g., `llm_summarizer.py`)
2. Define types in `utils/types.py`
3. Add step to `pdf_pipeline.py` orchestration
4. Update progress callback to report step
5. Add tests in `tests/utils/test_<module>.py`
6. Run `mypy .` to verify types
7. Update this CLAUDE.md if user-facing

### Modifying Weaviate Schema

1. **IMPORTANT:** Schema changes require data migration
2. Edit `schema.py` collection definitions
3. Test on empty Weaviate instance first
4. Create migration script if data exists
5. Update `utils/weaviate_ingest.py` ingestion logic
6. Update `utils/types.py` if object shapes change
7. Document migration in README.md

### Adding New Flask Routes

1. Add route handler in `flask_app.py`
2. Create Jinja2 template in `templates/` if needed
3. Update navigation in `templates/base.html`
4. Add route to table in this CLAUDE.md
5. Consider adding to MCP server if useful for Claude Desktop

## Common Debugging Scenarios

### "Weaviate connection failed"
```bash
docker compose ps  # Check if running
docker compose up -d  # Start if needed
docker compose logs weaviate  # Check errors
curl http://localhost:8080/v1/.well-known/ready  # Test readiness
```

### "OCR cost too high"
```python
# Reuse existing markdown
result = process_pdf(
    Path("input/document.pdf"),
    skip_ocr=True,  # Avoids OCR cost
    use_llm=True,
)
```

### "LLM timeout (Ollama)"
```bash
# Use lighter model
export STRUCTURE_LLM_MODEL=qwen2.5:7b  # Instead of deepseek-r1:14b

# Or switch to Mistral API
result = process_pdf(..., llm_provider="mistral")
```

### "Empty chunks after cleaning"
1. Check `output/<doc>/<doc>_chunks.json`
2. Look at `classified_sections` - may have classified main content as "ignore"
3. Adjust classification prompts in `llm_classifier.py`
4. Lower `min_chars` threshold in `llm_cleaner.py` if needed

### "TOC extraction failed"
```python
# Use OCR annotations (more reliable but 3x cost)
result = process_pdf(
    Path("input/document.pdf"),
    use_ocr_annotations=True,
)
```

### Type errors from mypy
```bash
# Check specific module
mypy utils/pdf_pipeline.py

# Ignore specific errors (last resort)
# Add to mypy.ini:
# [mypy-module_name]
# ignore_errors = True
```

## Output Files Structure

For each processed document `<doc_name>`:

```
output/<doc_name>/
├── <doc_name>.md              # Structured markdown with hierarchy
├── <doc_name>_ocr.json        # Raw OCR response from Mistral
├── <doc_name>_chunks.json     # Processed chunks + metadata + costs
├── <doc_name>_weaviate.json   # Ingestion results (UUIDs, counts)
└── images/                    # Extracted images
    ├── page_001_image_0.png
    └── ...
```

**chunks.json structure:**
```json
{
  "metadata": {...},
  "classified_sections": [...],
  "chunks": [...],
  "cost_ocr": 0.12,
  "cost_llm": 0.03,
  "total_cost": 0.15,
  "pages": 40,
  "chunks_count": 127
}
```

## Important Implementation Notes

### LLM Provider Configuration

Set in `.env` file:
```env
# Ollama (local)
STRUCTURE_LLM_MODEL=qwen2.5:7b
OLLAMA_BASE_URL=http://localhost:11434

# Mistral API
MISTRAL_API_KEY=your_key_here
STRUCTURE_LLM_MODEL=mistral-large-latest

# OCR (required)
MISTRAL_API_KEY=your_key_here
```

### Weaviate Connection

Default: `localhost:8080` (HTTP), `localhost:50051` (gRPC)

Python client v4 uses `connect_to_local()`:
```python
import weaviate
client = weaviate.connect_to_local()
```

### Nested Objects vs Cross-References

We use **nested objects** instead of Weaviate cross-references because:
- Single-query retrieval (no joins needed)
- Denormalized for read performance
- Simplified query logic
- Trade-off: Small data duplication acceptable

### Google-Style Docstrings Required

```python
def process_pdf(
    pdf_path: Path,
    *,
    use_llm: bool = True,
    llm_provider: LLMProvider = "ollama",
) -> PipelineResult:
    """Process a PDF through the complete RAG pipeline.

    Args:
        pdf_path: Path to the PDF file to process.
        use_llm: Enable LLM processing steps (metadata, TOC, chunking).
        llm_provider: LLM provider ("ollama" for local, "mistral" for API).

    Returns:
        Dictionary containing processing results with keys:
        - success: Whether processing succeeded
        - document_name: Name of the processed document
        - chunks_count: Number of chunks created
        - cost_ocr: OCR cost in euros
        - cost_llm: LLM cost in euros
        - cost_total: Total cost in euros

    Raises:
        FileNotFoundError: If PDF file does not exist.
        OCRError: If OCR processing fails.
        LLMStructureError: If LLM processing fails.
    """
```

## Testing Strategy

**Current test coverage:** Partial (OCR schemas, TOC extraction)

**Priority areas needing tests:**
- End-to-end pipeline tests with mock OCR/LLM
- Weaviate ingestion tests with test collections
- Flask route tests with test client
- LLM module tests with fixed prompts

**When writing tests:**
```python
# tests/utils/test_my_module.py
import pytest
from unittest.mock import Mock, patch
from utils.my_module import my_function

def test_my_function_success():
    """Test my_function with valid input."""
    result = my_function("valid_input")
    assert result["success"] is True

@patch("utils.my_module.expensive_api_call")
def test_my_function_with_mock(mock_api):
    """Test my_function with mocked API."""
    mock_api.return_value = {"data": "test"}
    result = my_function("input")
    mock_api.assert_called_once()
```

Run tests: `pytest tests/ -v`
