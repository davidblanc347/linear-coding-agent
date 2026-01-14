# Library RAG - Système de Recherche Philosophique Avancé

Système RAG (Retrieval-Augmented Generation) dual pour la recherche philosophique et la mémoire conversationnelle, propulsé par GPU embedder et Weaviate.

## 🎯 Vue d'Ensemble

Library RAG combine deux systèmes de recherche sémantique distincts:

1. **📚 Library Philosophique** - Base documentaire de textes philosophiques (œuvres, chunks, résumés)
2. **🧠 Memory Ikario** - Système de mémoire conversationnelle (pensées et conversations)

**Architecture**: 5 collections Weaviate + GPU embedder (NVIDIA RTX 4070) + Mistral API

## 🏗️ Architecture

### Collections Weaviate (5)

```
📦 Library Philosophique (3 collections)
├─ Work           → Métadonnées des œuvres philosophiques
├─ Chunk       → 5355 passages de texte (1024-dim vectors)
└─ Summary     → Résumés hiérarchiques des documents

🧠 Memory Ikario (2 collections)
├─ Thought        → 104 pensées (réflexions, insights)
└─ Conversation   → 12 conversations avec 380 messages
```

### GPU Embedder

- **Modèle**: BAAI/bge-m3 (1024 dimensions, 8192 tokens context)
- **GPU**: NVIDIA RTX 4070 Laptop (PyTorch CUDA + FP16)
- **Performance**: 30-70x plus rapide que Docker text2vec-transformers
- **Usage**: Vectorisation manuelle pour ingestion + requêtes

### Stack Technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Vector DB** | Weaviate 1.34.4 | Stockage + recherche vectorielle |
| **Embeddings** | Python GPU embedder | Vectorisation (ingestion + requêtes) |
| **OCR** | Mistral OCR API | Extraction texte depuis PDF |
| **LLM** | Mistral Large / Ollama | Génération de réponses RAG |
| **Web** | Flask 3.0 + SSE | Interface web avec streaming |
| **Tests** | Puppeteer + pytest | Validation automatisée |

## 🚀 Démarrage Rapide

### 1. Prérequis

```bash
# Python 3.10+
python --version

# CUDA 12.4+ (pour GPU embedder)
nvidia-smi

# Docker (pour Weaviate)
docker --version
```

### 2. Installation

```bash
# Cloner le projet
git clone <repo-url>
cd linear_coding_library_rag

# Créer environnement virtuel
cd generations/library_rag
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Installer dépendances
pip install -r requirements.txt

# PyTorch avec CUDA (si pas déjà installé)
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

### 3. Configuration

```bash
# Copier le fichier d'exemple
cp .env.example .env

# Éditer .env avec vos clés API
nano .env
```

**Variables requises**:
```bash
# Mistral API (OCR + LLM)
MISTRAL_API_KEY=your-mistral-api-key

# Ollama (optionnel, pour LLM local)
OLLAMA_BASE_URL=http://localhost:11434
```

### 4. Lancer les Services

```bash
# Démarrer Weaviate
docker compose up -d

# Vérifier que Weaviate est prêt
curl http://localhost:8080/v1/.well-known/ready

# Lancer Flask
python flask_app.py
```

**URLs**:
- 🌐 Flask: http://localhost:5000
- 🗄️ Weaviate: http://localhost:8080

## 📖 Utilisation

### Interface Web

Accéder à http://localhost:5000 pour:

| Page | URL | Description |
|------|-----|-------------|
| **Accueil** | `/` | Dashboard principal |
| **Recherche** | `/search` | Recherche dans library philosophique |
| **Chat** | `/chat` | Chat RAG avec contexte sémantique |
| **Memories** | `/memories` | Recherche dans pensées et messages |
| **Conversations** | `/conversations` | Historique des conversations |
| **Upload** | `/upload` | Ingestion de nouveaux PDF |

### 1. Recherche Philosophique

**Modes de recherche** (via `/search`):

- **📄 Simple**: Recherche directe dans les chunks
- **🌳 Hiérarchique**: Recherche par sections avec contexte
- **📚 Résumés**: Recherche dans les résumés de haut niveau

**Exemple**:
```
Requête: "la conscience selon Turing"
→ 16 résultats pertinents
→ Filtrage par auteur/œuvre
→ GPU embedder: ~17ms/requête
```

### 2. Chat RAG

**Fonctionnalités** (via `/chat`):

- 💬 Réponses longues et détaillées (500-800 mots)
- 📚 Citations directes des passages sources
- 🎯 Filtrage par œuvres (18 œuvres disponibles)
- 🔄 Streaming SSE (Server-Sent Events)
- 📖 Section "Sources utilisées" obligatoire

**Exemple de session**:
```
Question: "What is a Turing machine?"
→ Recherche sémantique: 11 chunks sur 5 sections
→ Génération LLM: ~30 secondes (Mistral Large)
→ Réponse académique détaillée avec sources
```

### 3. Memory Ikario

**Recherche dans pensées** (via `/memories`):

```
Requête: "test search"
→ 10 pensées pertinentes
→ Type: reflection, test, spontaneous
→ Concepts associés
```

**Recherche dans conversations**:

```
Requête: "philosophie intelligence"
→ Conversations pertinentes
→ Messages contextuels
→ Métadonnées (catégorie, date)
```

### 4. Ingestion de Documents

**Via interface web** (`/upload`):

1. Upload PDF (max 100 MB)
2. Sélection options:
   - LLM provider (Mistral/Ollama)
   - Chunking sémantique (optionnel)
   - OCR annotations (optionnel)
3. Traitement automatique:
   - OCR Mistral (~0.003€/page)
   - Extraction métadonnées (auteur, titre, année)
   - Chunking intelligent
   - Vectorisation GPU (~15ms/chunk)
   - Insertion Weaviate

**Via Python**:

```python
from utils.pdf_pipeline import process_pdf

result = process_pdf(
    pdf_path="document.pdf",
    use_llm=True,
    llm_provider="mistral",
    ingest_to_weaviate=True
)

print(f"Chunks: {result['chunks_count']}")
print(f"Cost: €{result['cost_total']:.4f}")
```

## 🧪 Tests

### Tests Automatisés

```bash
# Test ingestion GPU
python test_gpu_mistral.py

# Test recherche sémantique (Puppeteer)
node test_search_simple.js

# Test chat RAG (Puppeteer)
node test_chat_puppeteer.js

# Test memories/conversations (Puppeteer)
node test_memories_conversations.js
```

**Résultats attendus**:
- ✅ Ingestion: 9 chunks en ~1.2s
- ✅ Recherche: 16 résultats en ~2s
- ✅ Chat: 11 chunks, 5 sections, réponse complète
- ✅ Memories: API backend fonctionnelle

### Tests Manuels

```bash
# Vérifier GPU embedder
curl http://localhost:5000/search?q=Turing

# Vérifier Weaviate
curl http://localhost:8080/v1/meta

# Vérifier nombre de chunks
python -c "import weaviate; c=weaviate.connect_to_local(); print(c.collections.get('Chunk').aggregate.over_all()); c.close()"
```

## 📊 Métriques de Performance

### Ingestion

| Métrique | Avant (Docker) | Après (GPU) | Amélioration |
|----------|---------------|-------------|--------------|
| **Vitesse** | 500-1000ms/chunk | 15ms/chunk | **30-70x** |
| **RAM** | 10 GB (container) | 0 GB | **-10 GB** |
| **VRAM** | 0 GB | 2.6 GB | +2.6 GB |
| **Architecture** | Hybride | Unifiée | Simplifiée |

### Recherche

| Opération | Temps | Détails |
|-----------|-------|---------|
| **Vectorisation requête** | ~17ms | GPU embedder (modèle chargé) |
| **Recherche Weaviate** | ~100-500ms | Selon complexité |
| **Recherche hiérarchique** | ~500ms | 11 chunks sur 5 sections |
| **Chat complet** | ~30s | Inclut génération LLM |

### Ressources

- **VRAM**: 2.6 GB peak (RTX 4070, 8 GB disponibles)
- **Modèle**: BAAI/bge-m3 (1024 dims, FP16 precision)
- **Batch size**: 48 (optimal pour RTX 4070)

## 🔧 Configuration Avancée

### GPU Embedder

**Fichier**: `memory/core/embedding_service.py`

```python
class GPUEmbeddingService:
    model_name = "BAAI/bge-m3"
    embedding_dim = 1024
    optimal_batch_size = 48  # Ajuster selon GPU
```

**Réduire VRAM** (si Out of Memory):
```python
optimal_batch_size = 24  # Au lieu de 48
```

### Weaviate

**Fichier**: `docker-compose.yml`

```yaml
services:
  weaviate:
    mem_limit: 8g        # Limiter RAM
    cpus: 4              # Limiter CPU
```

### LLM Chat

**Fichier**: `flask_app.py` (ligne 1272)

```python
# Personnaliser le prompt système
system_instruction = """
Vous êtes un assistant expert en philosophie...
"""
```

## 📚 Documentation

### Structure du Projet

```
generations/library_rag/
├── flask_app.py              # Application Flask principale
├── schema.py                 # Schémas Weaviate (5 collections)
├── docker-compose.yml        # Weaviate (sans text2vec-transformers)
├── requirements.txt          # Dépendances Python
├── .env.example              # Configuration exemple
├── utils/
│   ├── pdf_pipeline.py       # Pipeline ingestion PDF
│   ├── weaviate_ingest.py    # Ingestion GPU vectorization
│   ├── llm_metadata.py       # Extraction métadonnées LLM
│   └── ocr_processor.py      # Mistral OCR
├── memory/
│   └── core/
│       └── embedding_service.py  # GPU embedder
├── templates/                # Templates HTML
└── static/                   # CSS, JS, images

docs/
├── migration-gpu/            # Documentation migration GPU embedder
│   ├── MIGRATION_GPU_EMBEDDER_SUCCESS.md
│   ├── TESTS_COMPLETS_GPU_EMBEDDER.md
│   └── ...
└── project_progress.md       # Historique développement

tests/
├── test_gpu_mistral.py       # Test ingestion
├── test_search_simple.js     # Test recherche
├── test_chat_puppeteer.js    # Test chat
└── test_memories_conversations.js  # Test memories
```

### Documentation Détaillée

- **[Migration GPU Embedder](docs/migration-gpu/MIGRATION_GPU_EMBEDDER_SUCCESS.md)** - Rapport de migration détaillé
- **[Tests Complets](docs/migration-gpu/TESTS_COMPLETS_GPU_EMBEDDER.md)** - Résultats de tous les tests
- **[Project Progress](docs/project_progress.md)** - Historique du développement
- **[CHANGELOG](CHANGELOG.md)** - Historique des versions

## 🐛 Dépannage

### Problème: "No module named 'memory'"

**Solution**:
```python
# Vérifier sys.path dans weaviate_ingest.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
```

### Problème: "CUDA not available"

**Solution**:
```bash
# Réinstaller PyTorch avec CUDA
pip uninstall torch
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

### Problème: "Out of Memory (VRAM)"

**Solution**:
```python
# Réduire batch size dans embedding_service.py
optimal_batch_size = 24  # Au lieu de 48
```

### Problème: Weaviate connection failed

**Solution**:
```bash
# Vérifier que Weaviate est lancé
docker compose ps

# Vérifier les logs
docker compose logs weaviate

# Redémarrer si nécessaire
docker compose restart
```

### Problème: Recherche ne renvoie rien

**Solution**:
```bash
# Vérifier nombre de chunks dans Weaviate
python -c "import weaviate; c=weaviate.connect_to_local(); print(f'Chunks: {c.collections.get(\"Chunk\").aggregate.over_all().total_count}'); c.close()"

# Réinjecter les données si nécessaire
python schema.py --recreate-chunk
```

## 🔐 Sécurité

- `.env` dans `.gitignore` (ne jamais commit les clés API)
- API Mistral: Facturation par usage (~€0.003/page OCR)
- Weaviate: Pas d'authentification (dev local uniquement)
- Flask: Mode debug (désactiver en production)

## 📈 Roadmap

### Court Terme
- [ ] Monitorer performance GPU en production
- [ ] Benchmarks formels sur gros documents (100+ pages)
- [ ] Tests unitaires pour `vectorize_chunks_batch()`

### Moyen Terme
- [ ] API REST complète (OpenAPI/Swagger)
- [ ] Support multi-utilisateurs avec authentification
- [ ] Export résultats (PDF, Word, citations)

### Long Terme
- [ ] Fine-tuning BGE-M3 sur corpus philosophique
- [ ] Support langues supplémentaires (grec ancien, latin)
- [ ] Clustering automatique des concepts philosophiques

## 🤝 Contribution

1. Fork le projet
2. Créer une branche (`git checkout -b feature/amazing`)
3. Commit (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing`)
5. Ouvrir une Pull Request

## 📄 Licence

MIT License - voir [LICENSE](LICENSE) pour détails.

## 🙏 Remerciements

- **Weaviate** - Vector database
- **BAAI** - BGE-M3 embedding model
- **Mistral AI** - OCR et LLM API
- **Anthropic** - Claude pour développement assisté

---

**Généré avec**: Claude Sonnet 4.5
**Dernière mise à jour**: Janvier 2026
**Version**: 2.0 (GPU Embedder Migration)
