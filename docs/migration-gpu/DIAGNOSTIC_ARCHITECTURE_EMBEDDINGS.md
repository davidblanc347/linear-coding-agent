# Diagnostic - Architecture des Embeddings

**Date:** 2026-01-09
**Projet:** Library RAG
**Problème initial:** Erreurs de connexion Weaviate

## Architecture Actuelle (Système Hybride)

Le projet utilise **deux systèmes d'embeddings différents** selon le contexte:

### 1. Pour l'INGESTION (Nouveaux Documents)

**Fichiers concernés:**
- `utils/weaviate_ingest.py` (ligne 1004)
- `schema.py` (lignes 245, 355)

**Méthode:**
```python
# Dans weaviate_ingest.py:ingest_document()
chunk_collection.data.insert_many(objects=batch)
# ⚠️ Pas de vecteurs manuels = vectorisation automatique par Weaviate
```

**Configuration schéma:**
```python
# Dans schema.py:create_chunk_collection()
vectorizer_config=wvc.Configure.Vectorizer.text2vec_transformers(
    vectorize_collection_name=False,
)
```

**Service utilisé:**
- **Docker container:** `library_rag-text2vec-transformers-1`
- **Image:** `cr.weaviate.io/semitechnologies/transformers-inference:baai-bge-m3-onnx-latest`
- **Port:** 8090 (exposé), 8080 (interne Weaviate)
- **Runtime:** ONNX CPU-only (pas de CUDA)
- **Modèle:** BAAI/bge-m3 (1024 dimensions)

**Verdict:** ✅ Utilise Docker text2vec-transformers (obligatoire)

---

### 2. Pour les REQUÊTES (Recherche Sémantique)

**Fichiers concernés:**
- `flask_app.py` (lignes 92-107, 307-308, 383-384, 669-670, 1056-1057)
- `memory/core/embedding_service.py`

**Méthode:**
```python
# Dans flask_app.py (routes /search, /explore_summaries, etc.)
embedder = get_gpu_embedder()
query_vector = embedder.embed_single(query)

result = chunks.query.near_vector(
    near_vector=query_vector.tolist(),
    limit=10,
)
```

**Service utilisé:**
- **Module Python:** `GPUEmbeddingService` (singleton)
- **Framework:** PyTorch + sentence-transformers
- **Accélération:** CUDA (RTX 4070 avec FP16)
- **VRAM:** ~2.6 GB peak
- **Modèle:** BAAI/bge-m3 (1024 dimensions)
- **Performance:** ~17 ms par requête

**Verdict:** ✅ Utilise Python GPU embedder (pas de dépendance Docker)

---

## Compatibilité des Modèles

| Composant | Modèle | Dimensions | Runtime |
|-----------|--------|------------|---------|
| **Ingestion (Docker)** | BAAI/bge-m3-onnx | 1024 | ONNX CPU |
| **Requêtes (Python)** | BAAI/bge-m3 | 1024 | PyTorch CUDA |

**Statut:** ✅ **Compatible** (même modèle, même dimensionnalité)

Les vecteurs générés par les deux systèmes sont comparables car:
- Même architecture de modèle (BAAI/bge-m3)
- Même nombre de dimensions (1024)
- Différence ONNX vs PyTorch est seulement une optimisation d'exécution

---

## Problème Diagnostiqué

### Symptôme Original

```
Erreur connexion Weaviate: Connection to Weaviate failed.
Details: Error: Server disconnected without sending a response.
```

### Cause Racine

Le service Docker **`text2vec-transformers`** n'était pas démarré.

**Impact:**
- ❌ **Ingestion impossible**: Nouveaux documents ne peuvent pas être vectorisés
- ✅ **Recherche fonctionnelle**: Les requêtes utilisent le GPU embedder Python (indépendant)

### Pourquoi text2vec-transformers est nécessaire ?

Weaviate est configuré au démarrage pour utiliser ce service:

```yaml
# docker-compose.yml
environment:
  DEFAULT_VECTORIZER_MODULE: "text2vec-transformers"
  ENABLE_MODULES: "text2vec-transformers"
  TRANSFORMERS_INFERENCE_API: "http://text2vec-transformers:8080"
```

Si le service n'est pas disponible:
1. Weaviate essaie de se connecter au démarrage
2. Échec DNS: "no such host"
3. Weaviate reste partiellement fonctionnel MAIS:
   - Les connexions peuvent être instables
   - L'ingestion avec vectorisation automatique échoue

---

## Solution Appliquée

### Fix Immédiat

```bash
cd generations/library_rag
docker compose up -d  # Démarre TOUS les services
```

**Résultat:**
- ✅ `weaviate` démarré (port 8080, 50051)
- ✅ `text2vec-transformers` démarré (port 8090)
- ✅ Connexion Weaviate stable
- ✅ Ingestion opérationnelle

### Fix Permanent (docker-compose.yml)

Ajout de **healthchecks** et **depends_on**:

```yaml
services:
  weaviate:
    depends_on:
      text2vec-transformers:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/v1/.well-known/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  text2vec-transformers:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/.well-known/ready"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s  # BGE-M3 loading time
```

**Bénéfices:**
- Docker attend que text2vec-transformers soit prêt avant de démarrer Weaviate
- Pas de "race condition" au démarrage
- Redémarrages automatiques plus fiables

---

## Architecture Alternative (Full Python)

L'utilisateur a mentionné que le projet devrait utiliser **uniquement Python embedder**. Voici comment migrer:

### Option 1: Vectorisation Manuelle Complète

**Avantages:**
- Un seul embedder (GPU Python) pour ingestion ET requêtes
- Pas besoin du service Docker text2vec-transformers
- Meilleure performance avec GPU (vs ONNX CPU)
- Configuration simplifiée

**Inconvénients:**
- Nécessite modification du code d'ingestion
- Vecteurs doivent être générés manuellement avant insert

**Implémentation:**

```python
# Dans utils/weaviate_ingest.py
from memory.core import get_embedder

# Lors de l'ingestion
embedder = get_embedder()

# Générer les vecteurs manuellement
for batch in batches:
    texts = [chunk["text"] for chunk in batch]
    vectors = embedder.embed_batch(texts)

    # Insérer avec vecteurs manuels
    for chunk, vector in zip(batch, vectors):
        chunk_collection.data.insert(
            properties=chunk,
            vector=vector.tolist(),
        )
```

**Modification schéma:**

```python
# Dans schema.py:create_chunk_collection()
vectorizer_config=wvc.Configure.Vectorizer.none(),  # Désactiver auto-vectorization
```

**Modification docker-compose.yml:**

```yaml
services:
  weaviate:
    # Supprimer text2vec-transformers des modules
    environment:
      DEFAULT_VECTORIZER_MODULE: "none"
      ENABLE_MODULES: ""
      # Supprimer TRANSFORMERS_INFERENCE_API

# Supprimer complètement le service text2vec-transformers
```

---

## Recommandations

### Court Terme (Conserver Système Actuel)

✅ **Aucun changement nécessaire** si:
- L'ingestion de nouveaux documents est rare
- La performance d'ingestion n'est pas critique
- Vous voulez éviter de réécrire le code d'ingestion

**Actions:**
- [x] S'assurer que `docker compose up -d` démarre les deux services
- [x] Ajouter healthchecks (déjà fait)
- [ ] Documenter dans README.md que les deux services sont obligatoires

### Long Terme (Migration Full Python)

✅ **Recommandé** si:
- Vous avez un GPU disponible (RTX 4070 confirmé)
- Vous voulez simplifier l'architecture
- Performance d'ingestion importante (GPU 10-20x plus rapide que ONNX CPU)

**Plan de migration:**

1. **Phase 1: Préparation**
   - [ ] Créer `utils/gpu_vectorizer.py` avec fonctions de vectorisation batch
   - [ ] Écrire tests unitaires pour vectorisation manuelle
   - [ ] Benchmarker performance GPU vs Docker

2. **Phase 2: Modification Code**
   - [ ] Modifier `utils/weaviate_ingest.py` pour utiliser vectorisation manuelle
   - [ ] Modifier `schema.py` pour désactiver auto-vectorization
   - [ ] Ajouter paramètre `--use-gpu-embedder` au pipeline

3. **Phase 3: Migration Données**
   - [ ] **CRITIQUE:** Ré-ingérer TOUS les documents existants
     (les vecteurs auto-générés par text2vec doivent être regénérés)
   - [ ] Valider que les résultats de recherche sont cohérents
   - [ ] Comparer qualité des résultats avant/après

4. **Phase 4: Cleanup**
   - [ ] Supprimer service text2vec-transformers du docker-compose.yml
   - [ ] Simplifier environnement de déploiement
   - [ ] Mettre à jour documentation

**Coût de migration:** ~2-4 heures de développement + temps de ré-ingestion (dépend du nombre de documents)

---

## Vérification du Système Actuel

### Commandes de Diagnostic

```bash
# 1. Vérifier que les deux services tournent
docker compose ps

# 2. Tester Weaviate
curl http://localhost:8080/v1/.well-known/ready

# 3. Tester text2vec-transformers
curl http://localhost:8090/.well-known/ready

# 4. Tester le GPU embedder Python
python -c "from memory.core import get_embedder; e = get_embedder(); print('GPU OK')"

# 5. Tester une connexion Weaviate Python
python -c "import weaviate; c = weaviate.connect_to_local(); print('Weaviate OK'); c.close()"
```

### Résultats Attendus

```
✅ text2vec-transformers: Up (port 8090)
✅ weaviate: Up (ports 8080, 50051)
✅ HTTP 204 No Content (Weaviate ready)
✅ HTTP 204 No Content (text2vec ready)
✅ GPU OK (VRAM: 2.60 GB allocated)
✅ Weaviate OK
```

---

## Fichiers Modifiés

| Fichier | Changement | Raison |
|---------|-----------|--------|
| `docker-compose.yml` | Ajout healthchecks + depends_on | Éviter race condition au démarrage |

---

## Conclusion

**Système actuel:** ✅ **Fonctionnel** après fix
**Architecture:** Hybride (Docker pour ingestion, Python GPU pour requêtes)
**Compatibilité:** ✅ Compatible (même modèle BGE-M3)
**Recommandation:** Migrer vers **Full Python** pour simplifier et optimiser

**Prochaines étapes:**
1. Décider si migration Full Python est prioritaire
2. Si oui: Planifier ré-ingestion de tous les documents
3. Si non: Documenter architecture hybride actuelle

---

## Références

- **Docker Compose:** `generations/library_rag/docker-compose.yml`
- **Schéma Weaviate:** `generations/library_rag/schema.py`
- **Ingestion:** `generations/library_rag/utils/weaviate_ingest.py`
- **GPU Embedder:** `memory/core/embedding_service.py`
- **Flask App:** `generations/library_rag/flask_app.py`
- **Bug Report:** `BUG_REPORT_WEAVIATE_CONNECTION.md`
