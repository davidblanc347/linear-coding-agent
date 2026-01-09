# Analyse des Outils MCP Server

**Date**: 2026-01-09
**Fichier**: `generations/library_rag/mcp_server.py`
**Total**: 18 outils MCP

## Vue d'ensemble

Le serveur MCP (Model Context Protocol) expose **18 outils** organisés en **3 catégories** :

1. **Système** (1 outil) - Santé et diagnostics
2. **Library RAG** (8 outils) - Ingestion et recherche de textes philosophiques
3. **Memory** (9 outils) - Système de mémoire conversationnelle

---

## 🔧 Catégorie 1: Système (1 outil)

### 1. `ping()`
**Type**: Health check
**Paramètres**: Aucun
**Retour**: Message de statut

**Description**: Vérification que le serveur MCP est actif et répond.

**Exemple**:
```python
ping()
# → "Library RAG MCP Server is running!"
```

---

## 📚 Catégorie 2: Library RAG (8 outils)

### Outils d'Ingestion (1)

#### 2. `parse_pdf(pdf_path)`
**Type**: Ingestion PDF
**Collection cible**: Work, Chunk_v2, Summary_v2

**Paramètres**:
- `pdf_path` (str): Chemin local ou URL vers le PDF

**Configuration pré-optimisée** (fixe):
- LLM: Mistral API (mistral-medium-latest)
- OCR: Avec annotations (meilleure TOC)
- Chunking: Sémantique LLM (unités argumentatives)
- Ingestion: Automatique dans Weaviate

**Retour**:
```json
{
  "success": true,
  "document_name": "platon-menon",
  "source_id": "platon-menon",
  "pages": 120,
  "chunks_count": 456,
  "cost_ocr": 0.36,
  "cost_llm": 0.08,
  "cost_total": 0.44,
  "output_dir": "output/platon-menon",
  "metadata": {
    "title": "Ménon",
    "author": "Platon",
    "year": -380,
    "language": "fr"
  }
}
```

**Processus** (10 étapes):
1. OCR Mistral avec annotations
2. Construction Markdown
3. Extraction images
4. LLM extraction métadonnées
5. LLM extraction TOC
6. LLM classification sections
7. LLM chunking sémantique
8. Nettoyage chunks
9. LLM validation + concepts
10. Ingestion Weaviate + GPU vectorisation

---

### Outils de Recherche (7)

#### 3. `search_chunks(query, limit, min_similarity, author_filter, work_filter, language_filter)`
**Type**: Recherche sémantique
**Collection**: Chunk_v2 (5,372 chunks)

**Paramètres**:
- `query` (str): Requête en langage naturel
- `limit` (int): Nombre de résultats (1-100, défaut 10)
- `min_similarity` (float): Seuil similarité 0-1 (défaut 0.0)
- `author_filter` (str|None): Filtrer par auteur
- `work_filter` (str|None): Filtrer par œuvre
- `language_filter` (str|None): Filtrer par langue (fr, en, etc.)

**Retour**:
```json
{
  "results": [
    {
      "text": "La vertu est-elle enseignable...",
      "work": {
        "title": "Ménon",
        "author": "Platon"
      },
      "section_path": "Première partie > Dialogue initial",
      "similarity": 0.87,
      "language": "fr"
    }
  ],
  "total_count": 10,
  "query": "la vertu peut-elle s'enseigner"
}
```

**Usage**:
- Recherche sémantique dans tous les textes
- Filtrage par auteur/œuvre/langue
- Contrôle du seuil de similarité

---

#### 4. `search_summaries(query, limit, min_level, max_level)`
**Type**: Recherche sémantique (haut niveau)
**Collection**: Summary_v2 (114 résumés)

**Paramètres**:
- `query` (str): Requête en langage naturel
- `limit` (int): Nombre de résultats (défaut 10)
- `min_level` (int|None): Niveau minimum (1=chapitre)
- `max_level` (int|None): Niveau maximum (3=sous-section)

**Retour**:
```json
{
  "results": [
    {
      "title": "Dialogue sur la vertu",
      "text": "Ce chapitre explore la question...",
      "section_path": "Première partie",
      "level": 1,
      "concepts": ["vertu", "enseignement", "connaissance"],
      "chunks_count": 45
    }
  ],
  "total_count": 5,
  "query": "dialogue sur la vertu"
}
```

**Usage**:
- Vue d'ensemble des chapitres/sections
- Recherche par niveau hiérarchique
- Navigation structurelle

---

#### 5. `get_document(source_id, include_chunks, include_toc)`
**Type**: Récupération document
**Collections**: Work, Chunk_v2

**Paramètres**:
- `source_id` (str): Identifiant du document
- `include_chunks` (bool): Inclure les chunks (défaut False)
- `include_toc` (bool): Inclure la TOC (défaut False)

**Retour**:
```json
{
  "source_id": "platon-menon",
  "work": {
    "title": "Ménon",
    "author": "Platon",
    "year": -380,
    "language": "fr"
  },
  "chunks_count": 456,
  "chunks": [...],  // Si include_chunks=true
  "toc": [...]      // Si include_toc=true
}
```

**Usage**:
- Récupérer métadonnées d'un document
- Charger tous les chunks d'un document
- Obtenir la structure (TOC)

---

#### 6. `list_documents(limit, author_filter, language_filter)`
**Type**: Liste documents
**Collection**: Work (19 œuvres)

**Paramètres**:
- `limit` (int): Nombre max de résultats (défaut 50)
- `author_filter` (str|None): Filtrer par auteur
- `language_filter` (str|None): Filtrer par langue

**Retour**:
```json
{
  "documents": [
    {
      "source_id": "platon-menon",
      "title": "Ménon",
      "author": "Platon",
      "language": "fr",
      "year": -380,
      "chunks_count": 456
    }
  ],
  "total_count": 19
}
```

**Usage**:
- Explorer le catalogue
- Lister les œuvres d'un auteur
- Filtrer par langue

---

#### 7. `get_chunks_by_document(source_id, limit, offset)`
**Type**: Récupération chunks
**Collection**: Chunk_v2

**Paramètres**:
- `source_id` (str): Identifiant du document
- `limit` (int): Nombre de chunks (défaut 50)
- `offset` (int): Position de départ (défaut 0)

**Retour**:
```json
{
  "source_id": "platon-menon",
  "chunks": [
    {
      "text": "Socrate : Peux-tu me dire...",
      "section_path": "Première partie",
      "order_index": 0,
      "unit_type": "argument"
    }
  ],
  "total_count": 456,
  "offset": 0,
  "limit": 50
}
```

**Usage**:
- Parcourir séquentiellement un document
- Pagination des chunks
- Lecture structurée

---

#### 8. `filter_by_author(author, limit)`
**Type**: Filtrage par auteur
**Collections**: Work, Chunk_v2

**Paramètres**:
- `author` (str): Nom de l'auteur
- `limit` (int): Nombre max de résultats (défaut 100)

**Retour**:
```json
{
  "author": "Platon",
  "works": [
    {
      "title": "Ménon",
      "chunks_count": 456
    },
    {
      "title": "La République",
      "chunks_count": 892
    }
  ],
  "total_works": 2,
  "total_chunks": 1348
}
```

**Usage**:
- Bibliographie d'un auteur
- Statistiques par auteur
- Exploration par corpus

---

#### 9. `delete_document(source_id, confirm)`
**Type**: Suppression
**Collections**: Work, Chunk_v2, Summary_v2

**Paramètres**:
- `source_id` (str): Identifiant du document
- `confirm` (bool): Confirmation obligatoire (défaut False)

**Retour**:
```json
{
  "success": true,
  "source_id": "platon-menon",
  "deleted_chunks": 456,
  "deleted_summaries": 12,
  "deleted_work": true
}
```

**Usage**:
- Supprimer un document du système
- Nettoyage base de données
- Ré-ingestion après modification

**⚠️ Sécurité**: Nécessite `confirm=true` explicite.

---

## 🧠 Catégorie 3: Memory (9 outils)

### Outils Thought (3)

#### 10. `add_thought(content, thought_type, trigger, concepts, privacy_level)`
**Type**: Ajout pensée
**Collection**: Thought (104 pensées)

**Paramètres**:
- `content` (str): Contenu de la pensée
- `thought_type` (str): Type (reflection, question, intuition, observation)
- `trigger` (str|None): Déclencheur
- `concepts` (list[str]): Concepts liés
- `privacy_level` (str): Niveau (private, shared, public)

**Retour**:
```json
{
  "success": true,
  "thought_id": "uuid-xxxx",
  "timestamp": "2026-01-09T10:30:00Z"
}
```

**Usage**:
- Capturer insights et réflexions
- Construire base de connaissance personnelle
- Tracer évolution de la pensée

---

#### 11. `search_thoughts(query, limit, thought_type_filter)`
**Type**: Recherche sémantique
**Collection**: Thought

**Paramètres**:
- `query` (str): Requête en langage naturel
- `limit` (int): Nombre de résultats (défaut 10)
- `thought_type_filter` (str|None): Filtrer par type

**Retour**:
```json
{
  "results": [
    {
      "content": "Vector databases enable semantic search...",
      "thought_type": "observation",
      "concepts": ["weaviate", "embeddings"],
      "timestamp": "2026-01-08T15:20:00Z",
      "similarity": 0.92
    }
  ],
  "total_count": 10
}
```

**Usage**:
- Recherche dans ses pensées
- Retrouver insights passés
- Connexions sémantiques

---

#### 12. `get_thought(uuid)`
**Type**: Récupération pensée
**Collection**: Thought

**Paramètres**:
- `uuid` (str): UUID de la pensée

**Retour**:
```json
{
  "uuid": "uuid-xxxx",
  "content": "...",
  "thought_type": "observation",
  "trigger": "Research session",
  "concepts": ["weaviate"],
  "privacy_level": "private",
  "timestamp": "2026-01-08T15:20:00Z"
}
```

**Usage**:
- Récupérer une pensée spécifique
- Accès direct par ID

---

### Outils Message (3)

#### 13. `add_message(content, role, conversation_id, order_index)`
**Type**: Ajout message
**Collection**: Message (380 messages)

**Paramètres**:
- `content` (str): Contenu du message
- `role` (str): Rôle (user, assistant, system)
- `conversation_id` (str): ID de la conversation
- `order_index` (int): Position dans la conversation

**Retour**:
```json
{
  "success": true,
  "message_id": "uuid-xxxx",
  "conversation_id": "chat_2026_01_09",
  "timestamp": "2026-01-09T10:30:00Z"
}
```

**Usage**:
- Ajouter message à une conversation
- Construire historique
- Tracer dialogue

---

#### 14. `get_messages(conversation_id, limit)`
**Type**: Récupération messages
**Collection**: Message

**Paramètres**:
- `conversation_id` (str): ID de la conversation
- `limit` (int): Nombre max de messages (défaut 50)

**Retour**:
```json
{
  "conversation_id": "chat_2026_01_09",
  "messages": [
    {
      "content": "Explain transformers...",
      "role": "user",
      "order_index": 0,
      "timestamp": "2026-01-09T10:00:00Z"
    },
    {
      "content": "Transformers are neural networks...",
      "role": "assistant",
      "order_index": 1,
      "timestamp": "2026-01-09T10:01:00Z"
    }
  ],
  "total_count": 2
}
```

**Usage**:
- Charger historique conversation
- Contexte pour continuation
- Analyse conversationnelle

---

#### 15. `search_messages(query, limit, conversation_id_filter)`
**Type**: Recherche sémantique
**Collection**: Message

**Paramètres**:
- `query` (str): Requête en langage naturel
- `limit` (int): Nombre de résultats (défaut 10)
- `conversation_id_filter` (str|None): Filtrer par conversation

**Retour**:
```json
{
  "results": [
    {
      "content": "Transformers use self-attention...",
      "role": "assistant",
      "conversation_id": "chat_2026_01_09",
      "timestamp": "2026-01-09T10:01:00Z",
      "similarity": 0.94
    }
  ],
  "total_count": 10
}
```

**Usage**:
- Rechercher dans l'historique
- Retrouver réponses passées
- Analyse transversale conversations

---

### Outils Conversation (3)

#### 16. `get_conversation(conversation_id)`
**Type**: Récupération conversation
**Collection**: Conversation (12 conversations)

**Paramètres**:
- `conversation_id` (str): ID de la conversation

**Retour**:
```json
{
  "conversation_id": "chat_2026_01_09",
  "title": "Discussion on AI transformers",
  "category": "technical",
  "summary": "Explained transformer architecture...",
  "tags": ["AI", "transformers", "architecture"],
  "message_count": 24,
  "timestamp": "2026-01-09T10:00:00Z"
}
```

**Usage**:
- Métadonnées conversation
- Vue d'ensemble
- Navigation conversations

---

#### 17. `search_conversations(query, limit, category_filter)`
**Type**: Recherche sémantique
**Collection**: Conversation

**Paramètres**:
- `query` (str): Requête en langage naturel
- `limit` (int): Nombre de résultats (défaut 10)
- `category_filter` (str|None): Filtrer par catégorie

**Retour**:
```json
{
  "results": [
    {
      "conversation_id": "chat_2026_01_09",
      "title": "Discussion on AI transformers",
      "summary": "Explained transformer architecture...",
      "category": "technical",
      "message_count": 24,
      "similarity": 0.89
    }
  ],
  "total_count": 10
}
```

**Usage**:
- Rechercher conversations passées
- Retrouver discussions par thème
- Navigation sémantique

---

#### 18. `list_conversations(limit, category_filter)`
**Type**: Liste conversations
**Collection**: Conversation

**Paramètres**:
- `limit` (int): Nombre max de résultats (défaut 20)
- `category_filter` (str|None): Filtrer par catégorie

**Retour**:
```json
{
  "conversations": [
    {
      "conversation_id": "chat_2026_01_09",
      "title": "Discussion on AI transformers",
      "category": "technical",
      "message_count": 24,
      "timestamp": "2026-01-09T10:00:00Z"
    }
  ],
  "total_count": 12
}
```

**Usage**:
- Explorer l'historique
- Lister par catégorie
- Vue chronologique

---

## 📊 Résumé des Outils

| Catégorie | Nombre | Collections utilisées | GPU Embedder |
|-----------|--------|----------------------|--------------|
| **Système** | 1 | - | - |
| **Library RAG** | 8 | Work, Chunk_v2, Summary_v2 | ✅ |
| **Memory** | 9 | Thought, Message, Conversation | ✅ |
| **TOTAL** | **18** | **6 collections** | **5 vectorisées** |

---

## 🎯 Patterns d'Usage

### Pattern 1: Ingestion complète
```python
# 1. Ingérer un PDF
result = parse_pdf("path/to/platon-menon.pdf")

# 2. Vérifier l'ingestion
docs = list_documents(author_filter="Platon")

# 3. Rechercher dans le document
chunks = search_chunks("la vertu peut-elle s'enseigner", work_filter="Ménon")
```

### Pattern 2: Recherche multi-niveaux
```python
# 1. Recherche haut niveau (résumés)
summaries = search_summaries("dialectique maïeutique", limit=5)

# 2. Recherche détaillée (chunks)
chunks = search_chunks("dialectique maïeutique", limit=20)
```

### Pattern 3: Exploration par auteur
```python
# 1. Lister les œuvres d'un auteur
author_data = filter_by_author("Platon")

# 2. Récupérer un document spécifique
doc = get_document("platon-menon", include_toc=True)

# 3. Parcourir les chunks
chunks = get_chunks_by_document("platon-menon", limit=100)
```

### Pattern 4: Memory workflow
```python
# 1. Capturer une pensée
add_thought(
    content="Vector databases enable semantic search...",
    thought_type="observation",
    concepts=["weaviate", "embeddings"]
)

# 2. Démarrer une conversation
add_message(
    content="Explain transformers",
    role="user",
    conversation_id="chat_2026_01_09"
)

# 3. Rechercher dans l'historique
messages = search_messages("transformers architecture")
```

---

## 🔐 Sécurité

### Validation des entrées
- Tous les paramètres sont typés avec Pydantic
- Validation automatique des limites (1-100 pour results)
- Filtrage SQL injection via Weaviate client

### Permissions
- `delete_document` nécessite `confirm=true` explicite
- Pas d'authentification (usage local Claude Desktop)
- Logs structurés JSON pour audit

### Error Handling
- `WeaviateConnectionError`: Problème connexion base
- `PDFProcessingError`: Échec traitement PDF
- Tous les outils retournent `success: false` + message d'erreur

---

## 🚀 Performance

### Latence typique
- `ping()`: <1ms
- `search_chunks()`: 100-500ms (vectorisation + recherche)
- `parse_pdf()`: 2-5min (dépend taille PDF, OCR, LLM)
- `list_documents()`: 50-100ms
- Memory tools: 100-300ms

### Optimisations
- GPU embedder (BAAI/bge-m3, RTX 4070): 17ms par query
- Weaviate HNSW + RQ: recherche <100ms sur 5k+ chunks
- Batch processing pour ingestion
- Cache Weaviate pour requêtes répétées

---

## 📝 Notes d'Implémentation

### Architecture
- **Serveur**: FastMCP (stdio transport)
- **Handlers**: Fonctions async dans `mcp_tools/`
- **Memory handlers**: Dans `memory/mcp/`
- **Validation**: Pydantic models
- **Logging**: JSON structuré avec timestamps

### Collections Weaviate
```
6 collections au total:

RAG (3):
- Work (no vectorizer) - 19 œuvres
- Chunk_v2 (GPU embedder) - 5,372 chunks
- Summary_v2 (GPU embedder) - 114 résumés

Memory (3):
- Conversation (GPU embedder) - 12 conversations
- Message (GPU embedder) - 380 messages
- Thought (GPU embedder) - 104 pensées
```

### GPU Embedder
- **Modèle**: BAAI/bge-m3 (1024 dimensions)
- **Hardware**: RTX 4070 (PyTorch CUDA)
- **Performance**: 17ms par vectorisation
- **Context**: 8192 tokens
- **Usage**: Toutes les 5 collections vectorisées

---

## 🎓 Cas d'Usage

### 1. Recherche académique
- Ingérer corpus philosophique complet
- Recherche sémantique multi-œuvres
- Analyse comparative auteurs/concepts

### 2. Aide à la rédaction
- Rechercher citations pertinentes
- Explorer arguments philosophiques
- Contextualiser concepts

### 3. Apprentissage
- Parcourir documents structurés (TOC)
- Recherche par niveaux (chapitres → sections)
- Découverte guidée

### 4. Mémoire conversationnelle
- Capturer insights pendant recherche
- Historique conversations avec Claude
- Recherche transversale dans l'historique

---

**Dernière mise à jour**: 2026-01-09
**Version**: Library RAG MCP Server v2.0
**Collections**: 6 (3 RAG + 3 Memory)
**GPU Embedder**: BAAI/bge-m3 (RTX 4070)
