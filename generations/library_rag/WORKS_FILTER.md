# Filtrage par oeuvres - Guide utilisateur

Ce guide explique comment utiliser la fonctionnalité de filtrage par oeuvres dans la page de conversation RAG.

## Vue d'ensemble

La fonctionnalité de filtrage permet de restreindre la recherche sémantique à certaines oeuvres spécifiques de votre bibliothèque. C'est particulièrement utile lorsque vous souhaitez :

- Comparer les perspectives de différents auteurs sur un même sujet
- Vous concentrer sur un corpus précis (ex: uniquement Platon)
- Exclure temporairement des textes non pertinents pour votre recherche

## Localisation

La section "Filtrer par oeuvres" se trouve dans la **sidebar droite** de la page `/chat`, au-dessus de la section "Contexte RAG".

## Fonctionnalités

### 1. Liste des oeuvres disponibles

Chaque oeuvre affiche :
- **Titre** : Le titre de l'oeuvre
- **Auteur** : Le nom de l'auteur
- **Nombre de passages** : Le nombre de chunks indexés pour cette oeuvre

### 2. Sélection / Désélection

- **Cliquer sur une oeuvre** : Toggle (active/désactive) la sélection
- **Cliquer sur la checkbox** : Même comportement

### 3. Boutons d'action rapide

| Bouton | Action |
|--------|--------|
| **Tout** | Sélectionne toutes les oeuvres |
| **Aucun** | Désélectionne toutes les oeuvres |

### 4. Badge compteur

Le badge dans l'en-tête affiche le nombre d'oeuvres sélectionnées :
- `10/10` = Toutes les oeuvres sélectionnées
- `3/10` = 3 oeuvres sur 10 sélectionnées
- `0/10` = Aucune oeuvre sélectionnée

### 5. Section collapsible

Cliquez sur le chevron (▼/▲) pour réduire ou développer la section. Le badge reste visible même quand la section est réduite.

## Comportement par défaut

- **Au premier chargement** : Toutes les oeuvres sont sélectionnées
- **Lors des visites suivantes** : La dernière sélection est restaurée (persistance localStorage)

## Impact sur la recherche

Lorsque vous posez une question :

1. **Toutes les oeuvres sélectionnées** : La recherche s'effectue sur l'ensemble de la bibliothèque
2. **Certaines oeuvres sélectionnées** : Seuls les passages des oeuvres cochées sont retournés
3. **Aucune oeuvre sélectionnée** : La recherche s'effectue sur toutes les oeuvres (équivalent à "Tout")

## Cas d'usage recommandés

### Étude comparative
> Je veux comparer ce que disent Peirce et Tiercelin sur la notion de signe.

1. Cliquez sur "Aucun"
2. Sélectionnez uniquement les oeuvres de Peirce et Tiercelin
3. Posez votre question

### Focus sur un auteur
> Je ne veux que les textes de Platon pour ma recherche sur la vertu.

1. Cliquez sur "Aucun"
2. Cochez uniquement les oeuvres de Platon
3. Effectuez vos recherches

### Exclusion temporaire
> Le corpus de Peirce est trop volumineux et noie mes résultats.

1. Cliquez sur "Tout"
2. Décochez les oeuvres de Peirce
3. Continuez vos recherches

## Persistance des préférences

Votre sélection est automatiquement sauvegardée dans le **localStorage** de votre navigateur. Elle sera restaurée lors de vos prochaines visites sur la page.

Pour **réinitialiser** vos préférences :
1. Cliquez sur "Tout" pour tout sélectionner
2. La nouvelle sélection sera sauvegardée automatiquement

## Responsive (Mobile)

Sur les écrans de moins de 992px de large :
- La section de filtrage apparaît en dessous de la zone de conversation
- Elle reste entièrement fonctionnelle
- La section peut être réduite pour économiser de l'espace

---

# API Reference (Développeurs)

## GET /api/get-works

Retourne la liste de toutes les oeuvres disponibles.

**Requête :**
```http
GET /api/get-works
```

**Réponse (200 OK) :**
```json
[
  {
    "title": "Ménon",
    "author": "Platon",
    "chunks_count": 127
  },
  {
    "title": "La logique de la science",
    "author": "Charles Sanders Peirce",
    "chunks_count": 12
  }
]
```

**Erreur (500) :**
```json
{
  "error": "Weaviate connection failed",
  "message": "Cannot connect to Weaviate database"
}
```

## POST /chat/send (paramètre selected_works)

Le paramètre `selected_works` permet de filtrer la recherche par oeuvres.

**Requête :**
```json
{
  "question": "Qu'est-ce que la vertu ?",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "limit": 5,
  "selected_works": ["Ménon", "La pensée-signe"]
}
```

**Comportement :**
- `selected_works: []` (liste vide) : Recherche dans toutes les oeuvres
- `selected_works: ["Ménon"]` : Recherche uniquement dans Ménon
- `selected_works` absent : Équivalent à liste vide (toutes les oeuvres)

**Erreurs de validation (400) :**
```json
{"error": "selected_works must be a list of work titles"}
```

```json
{"error": "selected_works must contain only strings"}
```

---

# Troubleshooting

## Aucune oeuvre n'est affichée

**Causes possibles :**
1. Weaviate n'est pas démarré
2. Aucun document n'a été ingéré

**Solutions :**
```bash
# Vérifier que Weaviate est démarré
docker compose ps

# Démarrer Weaviate si nécessaire
docker compose up -d

# Vérifier qu'il y a des documents
# Aller sur http://localhost:5000/documents
```

## Le filtre ne semble pas fonctionner

**Vérifications :**
1. Vérifiez le badge compteur (combien d'oeuvres sont sélectionnées ?)
2. Ouvrez les DevTools (F12) > Network
3. Envoyez une question
4. Vérifiez que le POST `/chat/send` contient `selected_works`

**Si le problème persiste :**
1. Rafraîchissez la page (Ctrl+F5)
2. Videz le localStorage : DevTools > Application > Local Storage > Supprimer `selectedWorks`

## Comment réinitialiser la sélection ?

**Méthode 1 - Via l'interface :**
1. Cliquez sur le bouton "Tout"
2. La sélection est sauvegardée automatiquement

**Méthode 2 - Via DevTools :**
1. Ouvrez DevTools (F12)
2. Allez dans Application > Local Storage > localhost:5000
3. Supprimez la clé `selectedWorks`
4. Rafraîchissez la page

## Le nombre de passages ne correspond pas

Le nombre de passages (`chunks_count`) représente le nombre de **chunks** indexés, pas le nombre de pages du document original. Un document de 50 pages peut générer 100+ chunks selon le découpage sémantique.
