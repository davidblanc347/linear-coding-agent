# Guide d'Installation TTS - Après Redémarrage Windows

## 📋 Contexte
Vous avez installé **Microsoft Visual Studio Build Tools avec composants C++**.
Après redémarrage de Windows, ces outils seront actifs et permettront la compilation de TTS.

---

## 🔄 Étapes Après Redémarrage

### 1. Vérifier que Visual Studio Build Tools est actif

Ouvrir un **nouveau** terminal et tester :

```bash
# Vérifier que le compilateur C++ est disponible
where cl

# Devrait afficher un chemin comme :
# C:\Program Files\Microsoft Visual Studio\...\cl.exe
```

### 2. Installer TTS (Coqui XTTS v2)

```bash
# Aller dans le dossier du projet
cd C:\GitHub\linear_coding_library_rag\generations\library_rag

# Installer TTS (cela prendra 5-10 minutes)
pip install TTS==0.22.0
```

**Attendu** : Compilation réussie avec "Successfully installed TTS-0.22.0"

### 3. Vérifier l'installation

```bash
# Test d'import
python -c "import TTS; print(f'TTS version: {TTS.__version__}')"

# Devrait afficher : TTS version: 0.22.0
```

### 4. Redémarrer Flask et Tester

```bash
# Lancer Flask
python flask_app.py

# Aller sur http://localhost:5000/chat
# Poser une question
# Cliquer sur le bouton "Audio"
```

**Premier lancement** : Le modèle XTTS v2 (~2GB) sera téléchargé automatiquement (5-10 min).

---

## ⚠️ Si TTS échoue encore après redémarrage

### Solution Alternative : edge-tts (Déjà installé ✅)

**edge-tts** est déjà installé et fonctionne immédiatement. C'est une excellente alternative avec :
- ✅ Voix Microsoft Edge haute qualité
- ✅ Support français excellent
- ✅ Pas de compilation nécessaire
- ✅ Pas besoin de GPU

**Pour utiliser edge-tts**, il faudra modifier `utils/tts_generator.py`.

---

## 📊 Comparaison des Options

| Critère | TTS (XTTS v2) | edge-tts |
|---------|---------------|----------|
| Installation | ⚠️ Complexe (compilation) | ✅ Simple (pip install) |
| Qualité | ⭐⭐⭐⭐⭐ Excellente | ⭐⭐⭐⭐⭐ Excellente |
| GPU | ✅ Oui (4-6 GB VRAM) | ❌ Non (CPU uniquement) |
| Vitesse (100 mots) | 2-5 secondes (GPU) | 3-8 secondes (CPU) |
| Offline | ✅ Oui (après download) | ⚠️ Requiert Internet |
| Taille modèle | ~2 GB | Aucun téléchargement |
| Voix françaises | Oui, naturelles | Oui, Microsoft Azure |

---

## 🎯 Recommandation

1. **Essayer TTS après redémarrage** (pour profiter du GPU)
2. **Si échec** : Utiliser edge-tts (déjà installé, fonctionne immédiatement)

---

## 📝 Commandes de Diagnostic

Si TTS échoue encore :

```bash
# Vérifier Python
python --version

# Vérifier pip
pip --version

# Vérifier torch (déjà installé)
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# Vérifier Visual Studio
where cl
```

---

## 🔧 Fichiers Modifiés

- ✅ `requirements.txt` - TTS>=0.22.0 ajouté
- ✅ `utils/tts_generator.py` - Module TTS créé (pour XTTS v2)
- ✅ `flask_app.py` - Route /chat/export-audio ajoutée
- ✅ `templates/chat.html` - Bouton Audio ajouté

**Commit** : `d91abd3` - "Ajout de la fonctionnalité TTS"

---

## 📞 Contact après redémarrage

Après redémarrage, exécutez simplement :

```bash
pip install TTS==0.22.0
```

Et dites-moi le résultat (succès ou erreur).
