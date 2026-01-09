# Changelog - Library RAG Project

## 2026-01-09 - GPU Embedder Migration Complete & Documentation Overhaul

### GPU Embedder Migration (Complete)
- **Full Python GPU embedder**: Migrated from Docker text2vec-transformers to unified Python GPU embedder
- **30-70x faster ingestion**: GPU acceleration (RTX 4070, PyTorch CUDA, FP16)
- **Simplified architecture**: Single embedder for both ingestion and queries
- **Removed Docker service**: text2vec-transformers service removed, saves 10GB RAM
- **Manual vectorization**: All chunks now pre-vectorized before Weaviate insertion
- **Zero data loss**: All 5,355 existing chunks preserved during migration

### Testing & Validation
- **Chat RAG test**: Puppeteer test confirms hierarchical search (11 chunks, 5 sections)
- **Memories test**: Backend API validated (104 thoughts, 380 messages, 12 conversations)
- **Conversations test**: Search functionality working correctly
- **Performance metrics**: ~17ms query vectorization, ~100-500ms Weaviate search

### Documentation Reorganization
- **Created `docs/` structure**: Organized migration docs into `docs/migration-gpu/`
- **Moved 6 migration files**: BUG_REPORT, DIAGNOSTIC, MIGRATION_SUCCESS, TEST reports
- **Moved project_progress.md**: Centralized in `docs/`
- **Removed 15 obsolete files**: Cleaned up temporary session reports and outdated docs
- **README.md rewrite**: Comprehensive documentation of dual RAG system
  - 5 Weaviate collections explained (Work, Chunk_v2, Summary_v2, Thought, Conversation)
  - Library Philosophique + Memory Ikario architecture
  - Quick start guide, usage examples, troubleshooting
  - Performance metrics and resource usage

### Docker Configuration
- **Simplified docker-compose.yml**: Removed text2vec-transformers service and modules
- **Weaviate-only deployment**: Manual vectorization, no auto-vectorization modules needed
- **Environment cleanup**: Removed `ENABLE_MODULES` and `DEFAULT_VECTORIZER_MODULE`

### Database Stats (Current)
- **Chunk_v2**: 5,355 chunks with 1024-dim vectors (GPU embedder)
- **Summary_v2**: Hierarchical summaries with GPU vectors
- **Work**: 18 philosophical works
- **Thought**: 104 thoughts
- **Conversation**: 12 conversations with 380 messages

### Git Commits
- feat: Complete GPU embedder migration for ingestion pipeline
- test: Add Puppeteer tests for chat and memories
- refactor: Remove Docker text2vec-transformers service
- chore: Clean up temporary test files
- docs: Reorganize documentation and rewrite README
- docs: Remove obsolete documentation files

---

## 2026-01-08 - Chunking Optimization & Vectorization

### Chunking Improvements
- **Strict chunk size limits**: Max 1000 words (down from 1500-2000)
- **Overlap implementation**: 100-word overlap between consecutive chunks
- **Triple fallback system**: Ensures robust chunking even on LLM failures
- **New module**: `llm_chunker_improved.py` with overlap functionality

### Re-chunking Results
- Identified 31 oversized chunks (>2000 tokens, max 7,158)
- Split into 92 optimally-sized chunks
- **Result**: 0 chunks > 2000 tokens (100% within BGE-M3 limits)
- Preserved all metadata during split (workTitle, workAuthor, sectionPath, orderIndex)

### Vectorization
- Created manual vectorization system for Chunk_v2 (no vectorizer configured)
- Successfully vectorized 92 new chunks via text2vec-transformers API
- **Result**: 5,304/5,304 chunks with vectors (100% coverage)

### Docker Configuration
- Exposed text2vec-transformers port (8090:8080) for external vectorization
- Added cluster configuration to fix "No private IP address found" error
- Increased WORKER_TIMEOUT to 600s for very large chunks

### Search Quality
- Created comprehensive test suite (`10_test_search_quality.py`)
- Tests: distribution, overlap detection, semantic search (4 queries)
- Search now uses `near_vector()` with manual query vectorization
- **Issue identified**: Collected papers dominates results (95.8% of chunks)

### Database Stats (Post-Optimization)
- Total chunks: 5,304
- Average size: 289 tokens (optimal for BGE-M3)
- Distribution: 84.6% < 500 tokens, 11.5% 500-1000, 3.0% 1000-1500
- Works: 8 (Collected papers: 5,080 chunks, Mind Design III: 61, Platon Ménon: 56, etc.)

---

## 2025-01 - Weaviate v2 Migration & GPU Integration

### Phase 1-3: Schema Migration (Complete)
- Migrated from Chunk/Summary/Document to Chunk_v2/Summary_v2/Work
- Removed nested `document` object, added direct properties (workTitle, workAuthor, year, language)
- Work collection with sourceId for documents
- Fixed 114 summaries missing properties
- Deleted vL-jepa chunks (17), fixed null workTitles

### Phase 4: Memory System (Complete)
- Added Thought/Message/Conversation collections to Weaviate
- 9 MCP tools for memory management (add_thought, search_thoughts, etc.)
- GPU embeddings integration (BAAI/bge-m3, RTX 4070)
- Data: 102 Thoughts, 377 Messages, 12 Conversations

### Phase 5: Backend Integration (Complete)
- Integrated GPU embedder into Flask app (singleton pattern)
- All search routes now use manual vectorization with `near_vector()`
- Updated all routes: simple_search, hierarchical_search, summary_only_search, rag_search
- Fixed Work → Chunk/Summary property mapping (v2 schema)

### Phase 6-7: Testing & Optimization
- Comprehensive testing of search routes
- MCP tools validation
- Performance optimization with GPU embeddings
- Documentation updates (README.md, CLAUDE.md)

### Phase 8: Documentation Cleanup
- Consolidated all phase documentation
- Updated README with Memory MCP tools section
- Cleaned up temporary files and scripts

---

## Archive Structure

```
archive/
├── migration_scripts/        # Migration & optimization scripts (01-11)
│   ├── 01_migrate_document_to_work.py
│   ├── 02_create_schema_v2.py
│   ├── 03_migrate_chunks_v2.py
│   ├── 04_migrate_summaries_v2.py
│   ├── 05_validate_migration.py
│   ├── 07_cleanup.py
│   ├── 08_fix_summaries_properties.py
│   ├── 09_rechunk_oversized.py
│   ├── 10_test_search_quality.py
│   ├── 11_vectorize_missing_chunks.py
│   └── old_scripts/          # ChromaDB migration scripts
├── migration_docs/           # Detailed migration documentation
│   ├── PLAN_MIGRATION_V2_SANS_DOCUMENT.md
│   ├── PHASE5_BACKEND_INTEGRATION.md
│   └── WEAVIATE_RETRIEVAL_ARCHITECTURE.md
├── documentation/            # Phase summaries
│   ├── PHASE_0_PYTORCH_CUDA.md
│   ├── PHASE_2_MIGRATION_SUMMARY.md
│   ├── PHASE_3_CONVERSATIONS_SUMMARY.md
│   ├── PHASE_4_MIGRATION_CHROMADB.md
│   ├── PHASE_5_MCP_TOOLS.md
│   ├── PHASE_6_TESTS_OPTIMISATION.md
│   ├── PHASE_7_INTEGRATION_BACKEND.md
│   ├── PHASE_8_DOCUMENTATION_CLEANUP.md
│   └── MIGRATION_README.md
└── backups/                  # Pre-migration data backups
    └── pre_migration_20260108_152033/
```

---

## Technology Stack

**Vector Database**: Weaviate 1.34.4 with BAAI/bge-m3 embeddings (1024-dim)
**Embedder**: PyTorch 2.6.0+cu124, GPU RTX 4070
**Backend**: Flask 3.0 with Server-Sent Events
**MCP Integration**: 9 memory tools + 6 RAG tools for Claude Desktop
**OCR**: Mistral OCR API
**LLM**: Ollama (local) or Mistral API

---

## Known Issues

1. **Chunk_v2 has no vectorizer**: All new chunks require manual vectorization via `11_vectorize_missing_chunks.py`
2. **Data imbalance**: Collected papers represents 95.8% of chunks, dominating search results
3. **Mind Design III underrepresented**: Only 61 chunks (1.2%) vs 5,080 for Collected papers

## Recommendations

1. Add more diverse works to balance corpus
2. Consider re-ranking with per-work boosting for diversity
3. Recreate Chunk_v2 with text2vec-transformers vectorizer for auto-vectorization (requires full data reload)

---

For detailed implementation notes, see `.claude/CLAUDE.md` and `archive/` directories.
