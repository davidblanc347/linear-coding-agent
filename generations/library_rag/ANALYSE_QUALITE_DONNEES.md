# Analyse de la qualité des données Weaviate

**Date** : 01/01/2026
**Script** : `verify_data_quality.py`
**Rapport complet** : `rapport_qualite_donnees.txt`

---

## Résumé exécutif

Vous aviez raison : **il y a des incohérences majeures dans les données**.

**Problème principal** : Les 16 "documents" dans la collection Document sont en réalité **des doublons** de seulement 9 œuvres distinctes. Les chunks et summaries sont bien créés, mais pointent vers des documents dupliqués.

---

## Statistiques globales

| Collection | Objets | Note |
|------------|--------|------|
| **Work** | 0 | ❌ Vide (devrait contenir 9 œuvres) |
| **Document** | 16 | ⚠️ Contient des doublons (9 œuvres réelles) |
| **Chunk** | 5,404 | ✅ OK |
| **Summary** | 8,425 | ✅ OK |

**Œuvres uniques détectées** : 9 (via nested objects dans Chunks)

---

## Problèmes détectés

### 1. Documents dupliqués (CRITIQUE)

Les 16 documents contiennent des **doublons** :

| Document sourceId | Occurrences | Chunks associés |
|-------------------|-------------|-----------------|
| `peirce_collected_papers_fixed` | **4 fois** | 5,068 chunks (tous les 4 pointent vers les mêmes chunks) |
| `tiercelin_la-pensee-signe` | **3 fois** | 36 chunks (tous les 3 pointent vers les mêmes chunks) |
| `Haugeland_J._Mind_Design_III...` | **3 fois** | 50 chunks (tous les 3 pointent vers les mêmes chunks) |
| Autres documents | 1 fois chacun | Nombre variable |

**Impact** :
- La collection Document contient 16 objets au lieu de 9
- Les chunks pointent correctement vers les sourceId (pas de problème de côté Chunk)
- Mais vous avez des entrées Document redondantes

**Cause probable** :
- Ingestions multiples du même document (tests, ré-ingestions)
- Le script d'ingestion n'a pas vérifié les doublons avant insertion dans Document

---

### 2. Collection Work vide (BLOQUANT)

- **0 objets** dans la collection Work
- **9 œuvres uniques** détectées dans les nested objects des chunks

**Œuvres détectées** :
1. Mind Design III (John Haugeland et al.)
2. La pensée-signe (Claudine Tiercelin)
3. Collected papers (Charles Sanders Peirce)
4. La logique de la science (Charles Sanders Peirce)
5. The Fixation of Belief (C. S. Peirce)
6. AI: The Very Idea (John Haugeland)
7. Between Past and Future (Hannah Arendt)
8. On a New List of Categories (Charles Sanders Peirce)
9. Platon - Ménon (Platon)

**Recommandation** :
```bash
python migrate_add_work_collection.py  # Crée la collection Work avec vectorisation
# Ensuite : script pour extraire les 9 œuvres uniques et les insérer dans Work
```

---

### 3. Incohérence Document.chunksCount (MAJEUR)

| Métrique | Valeur |
|----------|--------|
| Total déclaré (`Document.chunksCount`) | 731 |
| Chunks réels dans collection Chunk | 5,404 |
| **Différence** | **4,673 chunks non comptabilisés** |

**Cause** :
- Le champ `chunksCount` n'a pas été mis à jour lors des ingestions suivantes
- Ou les chunks ont été créés sans mettre à jour le document parent

**Impact** :
- Les statistiques affichées dans l'UI seront fausses
- Impossible de se fier à `chunksCount` pour savoir combien de chunks un document possède

**Solution** :
- Script de réparation pour recalculer et mettre à jour tous les `chunksCount`
- Ou accepter que ce champ soit obsolète et le recalculer à la volée

---

### 4. Summaries manquants (MOYEN)

**5 documents n'ont AUCUN summary** (ratio 0.00) :
- `The_fixation_of_beliefs` (1 chunk, 0 summaries)
- `AI-TheVery-Idea-Haugeland-1986` (1 chunk, 0 summaries)
- `Arendt_Hannah_-_Between_Past_and_Future_Viking_1968` (9 chunks, 0 summaries)
- `On_a_New_List_of_Categories` (3 chunks, 0 summaries)

**3 documents ont un ratio < 0.5** (peu de summaries) :
- `tiercelin_la-pensee-signe` : 0.42 (36 chunks, 15 summaries)
- `Platon_-_Menon_trad._Cousin` : 0.22 (50 chunks, 11 summaries)

**Cause probable** :
- Documents courts ou sans structure hiérarchique claire
- Problème lors de la génération des summaries (étape 9 du pipeline)
- Ou summaries intentionnellement non créés pour certains types de documents

---

## Analyse par œuvre

### ✅ Données cohérentes

**peirce_collected_papers_fixed** (5,068 chunks, 8,313 summaries) :
- Ratio Summary/Chunk : 1.64
- Nested objects cohérents ✅
- Work manquant dans collection Work ❌

### ⚠️ Problèmes mineurs

**tiercelin_la-pensee-signe** (36 chunks, 15 summaries) :
- Ratio faible : 0.42 (peu de summaries)
- Dupliqué 3 fois dans Document

**Platon - Ménon** (50 chunks, 11 summaries) :
- Ratio très faible : 0.22 (peu de summaries)
- Peut-être structure hiérarchique non détectée

### ⚠️ Documents courts sans summaries

**The_fixation_of_beliefs**, **AI-TheVery-Idea**, **On_a_New_List_of_Categories**, **Arendt_Hannah** :
- 1 à 9 chunks seulement
- 0 summaries
- Peut-être trop courts pour avoir des chapitres/sections

---

## Recommandations d'action

### Priorité 1 : Nettoyer les doublons Document

**Problème** : 16 documents au lieu de 9 (7 doublons)

**Solution** :
1. Créer un script `clean_duplicate_documents.py`
2. Pour chaque sourceId, garder **un seul** objet Document (le plus récent)
3. Supprimer les doublons
4. Recalculer les `chunksCount` pour les documents restants

**Impact** : Réduction de 16 → 9 documents

---

### Priorité 2 : Peupler la collection Work

**Problème** : Collection Work vide (0 objets)

**Solution** :
1. Exécuter `migrate_add_work_collection.py` (ajoute vectorisation)
2. Créer un script `populate_work_collection.py` :
   - Extraire les 9 œuvres uniques depuis les nested objects des chunks
   - Insérer dans la collection Work
   - Optionnel : lier les documents aux Works via cross-reference

**Impact** : Collection Work peuplée avec 9 œuvres

---

### Priorité 3 : Recalculer Document.chunksCount

**Problème** : Incohérence de 4,673 chunks (731 déclaré vs 5,404 réel)

**Solution** :
1. Créer un script `fix_chunks_count.py`
2. Pour chaque document :
   - Compter les chunks réels (via filtrage Python comme dans verify_data_quality.py)
   - Mettre à jour le champ `chunksCount`

**Impact** : Métadonnées correctes pour statistiques UI

---

### Priorité 4 (optionnelle) : Regénérer summaries manquants

**Problème** : 5 documents sans summaries, 3 avec ratio < 0.5

**Solution** :
- Analyser si c'est intentionnel (documents courts)
- Ou ré-exécuter l'étape de génération de summaries (étape 9 du pipeline)
- Peut nécessiter ajustement des seuils (ex: nombre minimum de chunks pour créer summary)

**Impact** : Meilleure recherche hiérarchique

---

## Scripts à créer

1. **`clean_duplicate_documents.py`** - Nettoyer doublons (Priorité 1)
2. **`populate_work_collection.py`** - Peupler Work depuis nested objects (Priorité 2)
3. **`fix_chunks_count.py`** - Recalculer chunksCount (Priorité 3)
4. **`regenerate_summaries.py`** - Optionnel (Priorité 4)

---

## Conclusion

Vos suspicions étaient correctes : **les œuvres ne se retrouvent pas dans les 4 collections de manière cohérente**.

**Problèmes principaux** :
1. ❌ Work collection vide (0 au lieu de 9)
2. ⚠️ Documents dupliqués (16 au lieu de 9)
3. ⚠️ chunksCount obsolète (4,673 chunks non comptabilisés)
4. ⚠️ Summaries manquants pour certains documents

**Bonne nouvelle** :
- ✅ Les chunks et summaries sont bien créés et cohérents
- ✅ Les nested objects sont cohérents (pas de conflits title/author)
- ✅ Pas de données orphelines (tous les chunks/summaries ont un document parent)

**Next steps** :
1. Décider quelle priorité nettoyer en premier
2. Je peux créer les scripts de nettoyage si vous le souhaitez
3. Ou vous pouvez les créer vous-même en vous inspirant de `verify_data_quality.py`

---

**Fichiers générés** :
- `verify_data_quality.py` - Script de vérification
- `rapport_qualite_donnees.txt` - Rapport complet détaillé
- `ANALYSE_QUALITE_DONNEES.md` - Ce document (résumé)
