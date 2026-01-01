 ✅ CE QUI A ÉTÉ FAIT

  1. TOC extraction - CORRIGÉE
    - Fichier modifié : utils/word_toc_extractor.py
    - Ajout de 2 fonctions :
        - _roman_to_int() : Convertit chiffres romains (I, II, VII) en entiers
      - extract_toc_from_chapter_summaries() : Extrait TOC depuis "RESUME DES CHAPITRES"
    - Résultat : 7 chapitres correctement extraits (au lieu de 2)
  2. Weaviate - Investigation complète
    - Total chunks dans Weaviate : 5433 chunks (5068 de Peirce)
    - "On the origin - 10 pages" : 38 chunks supprimés (tous avaient sectionPath=1)
  3. Documentation créée
    - Fichier : WEAVIATE_SCHEMA.md (schéma complet de la base)

  🚨 PROBLÈME BLOQUANT

  text2vec-transformers tué par le système (OOM - Out Of Memory)

  Symptômes :
  Killed
  INFO: Started server process
  INFO: Application startup complete
  Killed

  Le conteneur Docker n'a pas assez de RAM pour vectoriser les chunks → ingestion échoue avec 0/7 chunks insérés.

  📋 CE QUI RESTE À FAIRE (après redémarrage)

  Option A - Simple (recommandée) :
  1. Modifier word_pipeline.py ligne 356-387 pour que le simple text splitting utilise la TOC
  2. Re-traiter avec use_llm=False (pas besoin de vectorisation intensive)
  3. Vérifier que les chunks ont les bons sectionPath (1, 2, 3... 7)

  Option B - Complexe :
  1. Augmenter RAM allouée à Docker (Settings → Resources)
  2. Redémarrer Docker
  3. Re-traiter avec use_llm=True et llm_provider='mistral'

  📂 FICHIERS MODIFIÉS

  - utils/word_toc_extractor.py (nouvelles fonctions TOC)
  - utils/word_pipeline.py (utilise nouvelle fonction TOC)
  - WEAVIATE_SCHEMA.md (nouveau fichier de documentation)

  🔧 COMMANDES APRÈS REDÉMARRAGE

  cd C:\GitHub\linear_coding_library_rag\generations\library_rag

  # Vérifier Docker
  docker ps

  # Option A (simple) - modifier le code puis :
  python -c "from pathlib import Path; from utils.word_pipeline import process_word; process_word(Path('input/On the origin - 10 pages.docx'), use_llm=False, ingest_to_weaviate=True)"

  # Vérifier résultat
  python -c "import weaviate; client=weaviate.connect_to_local(); coll=client.collections.get('Chunk'); resp=coll.query.fetch_objects(limit=100); origin=[o for o in resp.objects if 'origin - 10' in o.properties.get('work',{}).get('title','').lower()]; print(f'{len(origin)} chunks'); client.close()"