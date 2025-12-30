# Library RAG - Exemples MCP Client

Ce dossier contient des exemples d'implémentation de clients MCP pour utiliser Library RAG depuis votre application Python.

## Clients MCP avec LLM

### 1. `mcp_client_claude.py` ⭐ RECOMMANDÉ

**Client MCP avec Claude (Anthropic)**

**Modèle:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)

**Features:**
- Auto-chargement des clés depuis `.env`
- Tool calling automatique
- Gestion multi-tour de conversation
- Synthèse naturelle des résultats

**Usage:**
```bash
# Assurez-vous que .env contient:
# ANTHROPIC_API_KEY=your_key
# MISTRAL_API_KEY=your_key

python examples/mcp_client_claude.py
```

**Exemple:**
```
User: "What did Peirce say about nominalism?"

Claude → search_chunks(query="Peirce nominalism")
       → Weaviate (BGE-M3 embeddings)
       → 10 chunks retournés
Claude → "Peirce characterized nominalism as a 'tidal wave'..."
```

### 2. `mcp_client_reference.py`

**Client MCP avec Mistral AI**

**Modèle:** Mistral Large (`mistral-large-latest`)

Même fonctionnalités que le client Claude, mais utilise Mistral AI.

**Usage:**
```bash
python examples/mcp_client_reference.py
```

## Tests

### `test_mcp_quick.py`

Test rapide (< 5 secondes) des fonctionnalités MCP:
- ✅ search_chunks (recherche sémantique)
- ✅ list_documents
- ✅ filter_by_author

```bash
python examples/test_mcp_quick.py
```

### `test_mcp_client.py`

Suite de tests complète pour le client MCP (tests unitaires des 9 outils).

## Exemples sans MCP (direct pipeline)

### `example_python_usage.py`

Utilisation des handlers MCP directement (sans subprocess):
```python
from mcp_tools import search_chunks_handler, SearchChunksInput

result = await search_chunks_handler(
    SearchChunksInput(query="nominalism", limit=10)
)
```

### `example_direct_pipeline.py`

Utilisation directe du pipeline PDF:
```python
from utils.pdf_pipeline import process_pdf

result = process_pdf(
    Path("document.pdf"),
    use_llm=True,
    ingest_to_weaviate=True
)
```

## Architecture

```
┌─────────────────────────────────────────┐
│ Votre Application                       │
│                                         │
│  Claude/Mistral (LLM conversationnel)   │
│         ↓                               │
│  MCPClient (stdio JSON-RPC)             │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ MCP Server (subprocess)                 │
│  - 9 outils disponibles                 │
│  - search_chunks, parse_pdf, etc.       │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│ Weaviate + BGE-M3 embeddings            │
│  - 5,180 chunks de Peirce               │
│  - Recherche sémantique                 │
└─────────────────────────────────────────┘
```

## Embeddings vs LLM

**Important:** Trois modèles distincts sont utilisés:

1. **BGE-M3** (text2vec-transformers dans Weaviate)
   - Rôle: Vectorisation (embeddings 1024-dim)
   - Quand: Ingestion + recherche
   - Non modifiable sans migration

2. **Claude/Mistral** (Agent conversationnel)
   - Rôle: Comprendre questions + synthétiser réponses
   - Quand: Chaque conversation utilisateur
   - Changeable (votre choix)

3. **Mistral OCR** (pixtral-12b)
   - Rôle: Extraction texte depuis PDF
   - Quand: Ingestion de PDFs (via parse_pdf tool)
   - Fixé par le MCP server

## Outils MCP disponibles

| Outil | Description |
|-------|-------------|
| `search_chunks` | Recherche sémantique (500 max) |
| `search_summaries` | Recherche dans résumés |
| `list_documents` | Liste tous les documents |
| `get_document` | Récupère un document spécifique |
| `get_chunks_by_document` | Chunks d'un document |
| `filter_by_author` | Filtre par auteur |
| `parse_pdf` | Ingère un PDF/Markdown |
| `delete_document` | Supprime un document |
| `ping` | Health check |

## Limitations connues

Voir `KNOWN_ISSUES.md` pour les détails:
- ⚠️ `author_filter` et `work_filter` ne fonctionnent pas (limitation Weaviate nested objects)
- ✅ Workaround: Utiliser `filter_by_author` tool à la place

## Requirements

```bash
pip install anthropic python-dotenv  # Pour Claude
# OU
pip install mistralai  # Pour Mistral
```

Toutes les dépendances sont dans `requirements.txt` du projet parent.
