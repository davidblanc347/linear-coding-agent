# BGE-M3 Search Quality Validation Results

**Generated:** (Run `python test_bge_m3_quality.py --output SEARCH_QUALITY_RESULTS.md` to populate)

**Weaviate Version:** TBD

## Database Statistics

- **Total Documents:** TBD
- **Total Chunks:** TBD
- **Vector Dimensions:** TBD (expected: 1024)

## Vector Dimension Verification

Run the validation script to confirm BGE-M3 (1024-dim) vectors are properly configured.

Expected output: **BGE-M3 (1024-dim) vectors confirmed.**

## Test Categories

### 1. Multilingual Queries

Tests the model's ability to understand philosophical terms in multiple languages:

| Language | Test Terms |
|----------|------------|
| French | justice, vertu, liberte, verite, connaissance |
| English | virtue, knowledge, ethics, wisdom, justice |
| Greek | arete, telos, psyche, logos, eudaimonia |
| Latin | virtus, sapientia, forma, anima, ratio |

### 2. Semantic Understanding

Tests concept mapping for philosophical questions:

| Query | Expected Topics |
|-------|----------------|
| "What is the nature of reality?" | ontology, metaphysics, being |
| "How should we live?" | ethics, virtue, good life |
| "What can we know?" | epistemology, knowledge, truth |
| "What is the meaning of life?" | purpose, existence, value |
| "What is beauty?" | aesthetics, art, form |

### 3. Long Query Handling

Tests the extended 8192 token context (vs MiniLM-L6's 512 tokens):

- Uses a 100+ word query about Plato's Meno
- Verifies no truncation occurs
- Measures semantic accuracy of results

### 4. Performance Metrics

Performance targets:
- **Query Latency:** < 500ms average
- **Throughput:** Measured across 10 iterations per query

## Running the Tests

```bash
# Run all tests with verbose output
python test_bge_m3_quality.py --verbose

# Generate markdown report
python test_bge_m3_quality.py --output SEARCH_QUALITY_RESULTS.md

# Output as JSON
python test_bge_m3_quality.py --json
```

## Prerequisites

1. Weaviate must be running:
   ```bash
   docker-compose up -d
   ```

2. Documents must be ingested with BGE-M3 vectorizer

3. Schema must be created with 1024-dim vectors

## Expected Improvements over MiniLM-L6

| Feature | MiniLM-L6 | BGE-M3 |
|---------|-----------|--------|
| Vector Dimensions | 384 | 1024 (2.7x richer) |
| Context Window | 512 tokens | 8192 tokens (16x larger) |
| Multilingual | Limited | Excellent (Greek, Latin, French, English) |
| Academic Texts | Good | Superior (trained on research papers) |

## Troubleshooting

### "Connection error: Failed to connect to Weaviate"

Ensure Weaviate is running:
```bash
docker-compose up -d
docker-compose ps  # Check status
```

### "No vectors found in Chunk collection"

Ensure documents have been ingested:
```bash
python reingest_from_cache.py
```

### Vector dimensions show 384 instead of 1024

The BGE-M3 migration is incomplete. Re-run:
```bash
python migrate_to_bge_m3.py
```
