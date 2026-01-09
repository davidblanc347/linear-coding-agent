# Rapport de Bug - Erreur de Connexion Weaviate

**Date:** 2026-01-09
**Statut:** ✅ RÉSOLU

## Symptômes

L'application Flask affichait des erreurs de connexion Weaviate lors de l'accès aux routes:

```
Erreur connexion Weaviate: Connection to Weaviate failed.
Details: Error: Server disconnected without sending a response..
Is Weaviate running and reachable at http://localhost:8080?
```

Les requêtes HTTP pour les images fonctionnaient (200 OK), mais toutes les requêtes nécessitant Weaviate échouaient.

## Cause Racine

Le service Docker **`text2vec-transformers`** n'était pas démarré, alors que Weaviate en a besoin pour la vectorisation.

### Architecture Docker

Le `docker-compose.yml` définit **deux services** interdépendants:

1. **`weaviate`** - Serveur Weaviate principal (port 8080, 50051)
2. **`text2vec-transformers`** - Service de vectorisation BGE-M3 (port 8090)

Weaviate est configuré pour communiquer avec le service de vectorisation:
```yaml
environment:
  DEFAULT_VECTORIZER_MODULE: "text2vec-transformers"
  ENABLE_MODULES: "text2vec-transformers"
  TRANSFORMERS_INFERENCE_API: "http://text2vec-transformers:8080"
```

### Séquence d'Erreur

1. Seul le service `weaviate` était démarré
2. Weaviate tentait de se connecter à `text2vec-transformers` au démarrage
3. Résolution DNS échouait: "no such host"
4. Weaviate timeout: "context deadline exceeded"
5. Les connexions des clients Python échouaient avec "Server disconnected without sending a response"

### Logs Weaviate (Diagnostic)

```
{"action":"transformer_remote_wait_for_startup",
 "error":"Get \"http://text2vec-transformers:8080/.well-known/ready\":
          dial tcp: lookup text2vec-transformers on 127.0.0.11:53: no such host",
 "level":"warning",
 "msg":"transformer remote inference service not ready"}
```

## Solution

### Démarrage Correct

```bash
cd generations/library_rag

# Démarrer TOUS les services (pas seulement weaviate)
docker compose up -d

# Vérifier que les deux services tournent
docker compose ps

# Tester la connexion
python -c "import weaviate; client = weaviate.connect_to_local(); print('OK'); client.close()"
```

### Vérification

```bash
# Les deux services doivent apparaître
$ docker compose ps
NAME                                  STATUS
library_rag-text2vec-transformers-1   Up
library_rag-weaviate-1                Up

# Weaviate doit être ready
$ curl http://localhost:8080/v1/.well-known/ready
# Retourne: HTTP 204 No Content (succès)

# text2vec-transformers doit être ready
$ curl http://localhost:8090/.well-known/ready
# Retourne: HTTP 204 No Content (succès)
```

## Prévention

### 1. Scripts de Démarrage

Le fichier `init.sh` (ou `init.bat`) devrait déjà contenir:

```bash
# Démarrer Weaviate ET text2vec-transformers
docker compose up -d
```

⚠️ **NE PAS utiliser**: `docker compose up -d weaviate` (démarre seulement un service)

### 2. Health Check

Ajouter une vérification dans les scripts Python critiques:

```python
import weaviate
import sys

def check_weaviate_health():
    """Vérifie que Weaviate et le vectorizer sont opérationnels."""
    try:
        with weaviate.connect_to_local() as client:
            if not client.is_ready():
                print("❌ Weaviate n'est pas prêt")
                print("Démarrez les services: docker compose up -d")
                sys.exit(1)
        print("✓ Connexion Weaviate OK")
    except Exception as e:
        print(f"❌ Erreur connexion Weaviate: {e}")
        print("Vérifiez que les services Docker tournent:")
        print("  docker compose ps")
        print("  docker compose up -d")
        sys.exit(1)
```

### 3. Monitoring

Ajouter un healthcheck dans `docker-compose.yml`:

```yaml
services:
  weaviate:
    # ... config existante ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/v1/.well-known/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    depends_on:
      text2vec-transformers:
        condition: service_healthy

  text2vec-transformers:
    # ... config existante ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/.well-known/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s  # Le modèle BGE-M3 prend du temps à charger
```

## Commandes de Dépannage

### Diagnostic

```bash
# 1. Vérifier l'état des services
docker compose ps

# 2. Vérifier les logs Weaviate
docker compose logs weaviate --tail=50

# 3. Vérifier les logs text2vec-transformers
docker compose logs text2vec-transformers --tail=50

# 4. Tester la connectivité réseau entre les services
docker compose exec weaviate ping text2vec-transformers
```

### Redémarrage Propre

```bash
# Arrêter tous les services
docker compose down

# Redémarrer
docker compose up -d

# Attendre ~30 secondes que text2vec-transformers charge le modèle BGE-M3
sleep 30

# Vérifier
docker compose ps
curl http://localhost:8080/v1/.well-known/ready
curl http://localhost:8090/.well-known/ready
```

### Problèmes de Mémoire

Si `text2vec-transformers` crash (OOM - Out of Memory):

```yaml
# Dans docker-compose.yml, augmenter les limites:
text2vec-transformers:
  mem_limit: 12g      # Actuellement 10g
  memswap_limit: 14g  # Actuellement 12g
```

Le modèle BGE-M3 (1024 dimensions) nécessite ~6-8 GB de RAM au minimum.

## Tests de Non-Régression

Ajouter ce test dans `tests/integration/test_weaviate_startup.py`:

```python
import pytest
import weaviate
from weaviate.exceptions import WeaviateStartUpError

def test_weaviate_connection():
    """Test que Weaviate est accessible et prêt."""
    with weaviate.connect_to_local() as client:
        assert client.is_ready()

def test_text2vec_transformers_available():
    """Test que le module text2vec-transformers est chargé."""
    with weaviate.connect_to_local() as client:
        meta = client.get_meta()
        modules = meta.get("modules", {})
        assert "text2vec-transformers" in modules

        # Vérifier la configuration BGE-M3
        t2v_config = modules["text2vec-transformers"]
        assert "BAAI/bge-m3" in str(t2v_config).lower()
```

## Leçons Apprises

1. **Dépendances implicites**: Weaviate ne peut pas démarrer correctement sans `text2vec-transformers` quand configuré avec `DEFAULT_VECTORIZER_MODULE`
2. **Messages d'erreur trompeurs**: "Server disconnected" ne pointe pas directement vers le service manquant
3. **Importance de `depends_on`**: Docker Compose ne garantit pas l'ordre de démarrage sans `depends_on` et `healthcheck`
4. **Logs critiques**: Les logs Weaviate contenaient l'information clé ("no such host"), mais nécessitaient investigation

## Impact

- **Sévérité**: Critique (application non fonctionnelle)
- **Fréquence**: Se produit après redémarrage système ou `docker compose down`
- **Utilisateurs affectés**: Tous les développeurs/utilisateurs locaux
- **Temps de résolution**: 5 minutes (une fois diagnostiqué)

## Références

- Documentation Weaviate: https://weaviate.io/developers/weaviate/installation/docker-compose
- BGE-M3 Model: https://huggingface.co/BAAI/bge-m3
- Configuration actuelle: `generations/library_rag/docker-compose.yml`
