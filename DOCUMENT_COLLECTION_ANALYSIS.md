# Analyse: Collection Document - À supprimer

**Date**: 2026-01-09
**Statut**: ✅ CONFIRMATION - La collection Document n'est PAS utilisée et DOIT être supprimée

## Problème identifié

La collection `Document` est toujours définie dans le schéma et contient actuellement **13 objets**, alors que l'architecture devrait utiliser uniquement:
- `Work` - Métadonnées des œuvres
- `Chunk_v2` - Fragments vectorisés (5,372 chunks)
- `Summary_v2` - Résumés de sections (114 summaries)

## État actuel

### Collections existantes (Weaviate):
```
Work:        19 objets  ✓ UTILISÉ
Document:    13 objets  ✗ NON UTILISÉ (à supprimer)
Chunk_v2:    5,372 objets  ✓ UTILISÉ
Summary_v2:  114 objets  ✓ UTILISÉ
Chunk:       0 objets  (ancienne collection, peut être supprimée)
Conversation, Message, Thought: Collections chat (séparées)
```

### Données dans Document:
```json
{
  "sourceId": "Alan_Turing_and_John_von_Neumann_Their_B",
  "edition": null,
  "pages": 0,
  "chunksCount": 11,
  "work": null
}
```

**Observation**: La plupart des champs sont NULL ou 0 (pas de données utiles).

## Analyse du code

### 1. Schéma (`schema.py`)

**Lignes 159-224**: Définition complète de la collection Document
- Créée par défaut lors de l'initialisation du schéma
- Propriétés: sourceId, edition, language, pages, chunksCount, toc, hierarchy, createdAt, work (nested)

**Problème de cohérence** (lignes 747-757 dans `weaviate_ingest.py`):
```python
doc_obj: Dict[str, Any] = {
    "sourceId": doc_name,
    "title": title,        # ❌ N'EXISTE PAS dans schema.py
    "author": author,      # ❌ N'EXISTE PAS dans schema.py
    "toc": json.dumps(toc),
    "hierarchy": json.dumps(hierarchy),
    "pages": pages,
    "chunksCount": chunks_count,
    "language": metadata.get("language"),
    "createdAt": datetime.now().isoformat(),
}
```

Le code d'ingestion essaie d'insérer des champs `title` et `author` qui n'existent pas dans le schéma! Cela devrait causer une erreur mais est silencieusement ignoré.

### 2. Ingestion (`utils/weaviate_ingest.py`)

**Fonction `ingest_document_metadata()` (lignes 695-765)**:
- Insère les métadonnées du document dans la collection Document
- Stocke: sourceId, toc, hierarchy, pages, chunksCount, language, createdAt

**Fonction `ingest_document()` (lignes 891-1107)**:
- Paramètre: `ingest_document_collection: bool = True` (ligne 909)
- Par défaut, la fonction INSÈRE dans Document collection (ligne 1010)

**Fonction `delete_document_from_weaviate()` (lignes 1213-1267)**:
- Supprime de la collection Document (ligne 1243)

### 3. Flask App (`flask_app.py`)

**Résultat**: ✅ AUCUNE référence à la collection Document
- Pas de `collections.get("Document")`
- Pas de requêtes vers Document
- Les TOC et métadonnées sont chargées depuis les fichiers `chunks.json` (ligne 3360)

## Conclusion: Document n'est PAS nécessaire

### Données actuellement dans Document:

| Champ | Disponible ailleurs? | Source alternative |
|-------|---------------------|-------------------|
| `sourceId` | ✓ | `Chunk_v2.workTitle` (dénormalisé) |
| `toc` | ✓ | `output/<doc>/<doc>_chunks.json` |
| `hierarchy` | ✓ | `output/<doc>/<doc>_chunks.json` |
| `pages` | ✓ | `output/<doc>/<doc>_chunks.json` (metadata.pages) |
| `chunksCount` | ✓ | Dérivable via `Chunk_v2.aggregate.over_all(filter=workTitle)` |
| `language` | ✓ | `Work.language` + `Chunk_v2.language` |
| `createdAt` | ✓ | Dérivable via horodatage système des fichiers output/ |
| `edition` | ✗ | Jamais renseigné (toujours NULL) |
| `work` (nested) | ✓ | Collection `Work` dédiée |

**Verdict**: Toutes les informations utiles de Document sont disponibles ailleurs. La collection est redondante.

## Impact de la suppression

### ✅ Aucun impact négatif:
- Flask app n'utilise pas Document
- TOC/hierarchy chargés depuis fichiers JSON
- Métadonnées disponibles dans Work et Chunk_v2

### ✅ Bénéfices:
- Simplifie l'architecture (3 collections au lieu de 4)
- Réduit la mémoire Weaviate (~13 objets + index)
- Simplifie le code d'ingestion (moins d'étapes)
- Évite la confusion sur "quelle collection utiliser?"

## Plan d'action recommandé

### Étape 1: Supprimer la collection Document de Weaviate
```python
import weaviate
client = weaviate.connect_to_local()
client.collections.delete("Document")
client.close()
```

### Étape 2: Supprimer de `schema.py`
- Supprimer fonction `create_document_collection()` (lignes 159-224)
- Supprimer appel dans `create_schema()` (ligne 432)
- Mettre à jour `verify_schema()` pour ne plus vérifier Document (ligne 456)
- Mettre à jour `display_schema()` pour ne plus afficher Document (ligne 483)

### Étape 3: Nettoyer `utils/weaviate_ingest.py`
- Supprimer fonction `ingest_document_metadata()` (lignes 695-765)
- Supprimer paramètre `ingest_document_collection` (ligne 909)
- Supprimer appel à `ingest_document_metadata()` (ligne 1010)
- Supprimer suppression de Document dans `delete_document_from_weaviate()` (lignes 1241-1248)

### Étape 4: Mettre à jour la documentation
- Mettre à jour `schema.py` docstring (ligne 12: supprimer Document de la hiérarchie)
- Mettre à jour `CLAUDE.md` (ligne 11: supprimer Document)
- Mettre à jour `.claude/CLAUDE.md` (supprimer références à Document)

### Étape 5: Supprimer aussi la collection `Chunk` (ancienne)
```python
# Chunk_v2 la remplace complètement
client.collections.delete("Chunk")
```

## Risques

**Aucun risque identifié** car:
- Collection non utilisée par l'application
- Données disponibles ailleurs
- Pas de dépendances externes

---

**Recommandation finale**: Procéder à la suppression immédiate de la collection Document.
