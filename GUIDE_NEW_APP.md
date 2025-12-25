# Guide : Créer une Nouvelle Application avec le Framework Linear Coding

Ce guide explique comment utiliser ce framework pour créer une **toute nouvelle application** à partir de zéro.

## Vue d'ensemble

Ce framework permet de générer automatiquement une application complète en utilisant :
- **Linear** pour la gestion de projet (issues, suivi, commentaires)
- **Claude Agent SDK** pour le développement autonome
- **Spécifications en format XML** pour décrire l'application

## Structure du Framework

### Fichiers génériques (à NE PAS modifier)

Ces fichiers font partie du framework et sont réutilisables pour toutes les applications :

```
linear-coding-agent/
├── autonomous_agent_demo.py  # Point d'entrée principal
├── agent.py                  # Logique des sessions d'agent
├── client.py                 # Configuration SDK Claude + MCP
├── security.py              # Validation et whitelist des commandes
├── progress.py               # Utilitaires de suivi de progression
├── prompts.py                # Utilitaires de chargement des prompts
├── linear_config.py          # Constantes de configuration Linear
├── requirements.txt          # Dépendances Python
└── prompts/
    ├── initializer_prompt.md      # Prompt pour la session initiale
    ├── initializer_bis_prompt.md  # Prompt pour ajouter des features
    └── coding_prompt.md          # Prompt pour les sessions de codage
```

**⚠️ Ne modifiez PAS ces fichiers** - ils sont génériques et fonctionnent pour toutes les applications.

### Fichiers spécifiques à votre application (à CRÉER)

Le seul fichier que vous devez créer est :

```
prompts/
└── app_spec.txt  # Votre spécification d'application (format XML)
```

## Étapes pour Créer une Nouvelle Application

### Étape 1 : Créer votre fichier de spécification

Créez un fichier `prompts/app_spec.txt` qui décrit votre application. Utilisez le format XML suivant :

```xml
<project_specification>
  <project_name>Nom de Votre Application</project_name>

  <overview>
    Description complète de votre application. Expliquez ce que vous voulez construire,
    les objectifs principaux, et les fonctionnalités clés.
  </overview>

  <technology_stack>
    <frontend>
      <framework>React avec Vite</framework>
      <styling>Tailwind CSS</styling>
      <state_management>React hooks</state_management>
      <!-- Ajoutez d'autres technologies frontend -->
    </frontend>
    <backend>
      <runtime>Node.js avec Express</runtime>
      <database>SQLite</database>
      <!-- Ajoutez d'autres technologies backend -->
    </backend>
  </technology_stack>

  <prerequisites>
    <environment_setup>
      - Liste des prérequis (dépendances, clés API, etc.)
    </environment_setup>
  </prerequisites>

  <core_features>
    <feature_1>
      <title>Titre de la fonctionnalité 1</title>
      <description>Description détaillée</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Étape de test 1
        2. Étape de test 2
      </test_steps>
    </feature_1>
    
    <feature_2>
      <!-- Autres fonctionnalités -->
    </feature_2>
  </core_features>
</project_specification>
```

### Étape 2 : Exemple de structure complète

Voici un exemple basé sur l'application "Claude Clone" que vous pouvez utiliser comme référence :

**Structure recommandée de `app_spec.txt` :**

```xml
<project_specification>
  <project_name>Mon Application</project_name>

  <overview>
    Description de votre application...
  </overview>

  <technology_stack>
    <!-- Stack technique complète -->
  </technology_stack>

  <prerequisites>
    <!-- Prérequis -->
  </prerequisites>

  <core_features>
    <!-- Liste toutes vos fonctionnalités avec des balises <feature_X> -->
  </core_features>

  <ui_design>
    <!-- Spécifications UI si nécessaire -->
  </ui_design>

  <api_endpoints>
    <!-- Endpoints API si nécessaire -->
  </api_endpoints>

  <database_schema>
    <!-- Schéma de base de données si nécessaire -->
  </database_schema>
</project_specification>
```

### Étape 3 : Lancer l'initialisation

Une fois votre `app_spec.txt` créé, lancez l'agent initializer :

```bash
python autonomous_agent_demo.py --project-dir ./ma_nouvelle_app
```

L'agent va :
1. Lire votre `app_spec.txt`
2. Créer un projet Linear
3. Créer ~50 issues Linear basées sur votre spécification
4. Initialiser la structure du projet

### Étape 4 : Suivre le développement

Les agents de codage vont ensuite :
- Travailler sur les issues Linear une par une
- Implémenter les fonctionnalités
- Tester avec Puppeteer
- Mettre à jour les issues avec leurs commentaires

## Exemple : Utiliser l'application "Claude Clone" comme référence

L'application "Claude Clone" dans `prompts/app_spec.txt` est un excellent exemple à suivre car elle contient :

### ✅ Éléments à copier/adapter :

1. **Structure XML** : La structure générale avec `<project_specification>`, `<overview>`, `<technology_stack>`, etc.

2. **Format des fonctionnalités** : Comment structurer les `<feature_X>` avec :
   - `<title>`
   - `<description>`
   - `<priority>`
   - `<category>`
   - `<test_steps>`

3. **Détails techniques** : Comment décrire :
   - La stack technologique
   - Les prérequis
   - Les endpoints API
   - Le schéma de base de données
   - Les spécifications UI

### ❌ Éléments spécifiques à NE PAS copier :

1. **Le contenu spécifique** : Les détails sur "Claude API", "artifacts", "conversations", etc. sont spécifiques à cette app
2. **Les fonctionnalités métier** : Adaptez-les à votre application

## Checklist pour une Nouvelle Application

- [ ] Créer `prompts/app_spec.txt` avec votre spécification
- [ ] Définir le `<project_name>` de votre application
- [ ] Décrire l'`<overview>` complète
- [ ] Spécifier la `<technology_stack>` (frontend + backend)
- [ ] Lister les `<prerequisites>` nécessaires
- [ ] Définir toutes les `<core_features>` avec des balises `<feature_X>`
- [ ] Ajouter des `<test_steps>` pour chaque fonctionnalité
- [ ] Lancer : `python autonomous_agent_demo.py --project-dir ./mon_app`
- [ ] Vérifier dans Linear que les issues sont créées correctement

## Conseils pour Rédiger une Bonne Spécification

### 1. Soyez détaillé mais structuré

Chaque fonctionnalité doit avoir :
- Un titre clair
- Une description complète de ce qu'elle fait
- Des étapes de test précises
- Une priorité (1=urgent, 4=optionnel)

### 2. Utilisez le format XML cohérent

```xml
<feature_1>
  <title>Authentification - Connexion utilisateur</title>
  <description>
    Implémenter un système d'authentification avec :
    - Formulaire de connexion (email/mot de passe)
    - Validation côté client et serveur
    - Gestion des sessions avec JWT
    - Page de réinitialisation de mot de passe
  </description>
  <priority>1</priority>
  <category>auth</category>
  <test_steps>
    1. Accéder à la page de connexion
    2. Entrer un email invalide → voir erreur
    3. Entrer des identifiants valides → redirection vers dashboard
    4. Vérifier que le token JWT est stocké
    5. Tester la déconnexion
  </test_steps>
</feature_1>
```

### 3. Organisez par catégories

Groupez les fonctionnalités par catégorie :
- `auth` : Authentification
- `frontend` : Interface utilisateur
- `backend` : API et logique serveur
- `database` : Modèles et migrations
- `integration` : Intégrations externes

### 4. Priorisez les fonctionnalités

- **Priority 1** : Fonctionnalités critiques (auth, base de données)
- **Priority 2** : Fonctionnalités importantes (core features)
- **Priority 3** : Fonctionnalités secondaires (améliorations UX)
- **Priority 4** : Nice-to-have (polish, optimisations)

## Exemple Minimal

Voici un exemple minimal pour démarrer :

```xml
<project_specification>
  <project_name>Todo App - Gestionnaire de Tâches</project_name>

  <overview>
    Application web simple pour gérer des listes de tâches.
    Les utilisateurs peuvent créer, modifier, compléter et supprimer des tâches.
  </overview>

  <technology_stack>
    <frontend>
      <framework>React avec Vite</framework>
      <styling>Tailwind CSS</styling>
    </frontend>
    <backend>
      <runtime>Node.js avec Express</runtime>
      <database>SQLite</database>
    </backend>
  </technology_stack>

  <core_features>
    <feature_1>
      <title>Interface principale - Liste des tâches</title>
      <description>Afficher une liste de toutes les tâches avec leur statut</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Ouvrir l'application
        2. Vérifier que la liste des tâches s'affiche
      </test_steps>
    </feature_1>

    <feature_2>
      <title>Créer une nouvelle tâche</title>
      <description>Formulaire pour ajouter une nouvelle tâche à la liste</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Cliquer sur "Nouvelle tâche"
        2. Entrer un titre
        3. Cliquer sur "Ajouter"
        4. Vérifier que la tâche apparaît dans la liste
      </test_steps>
    </feature_2>
  </core_features>
</project_specification>
```

## Fichiers à Conserver du Framework

Ces fichiers sont **génériques** et fonctionnent pour toutes les applications :

- ✅ `autonomous_agent_demo.py` - Point d'entrée
- ✅ `agent.py` - Logique des agents
- ✅ `client.py` - Configuration Claude SDK
- ✅ `prompts.py` - Chargement des prompts
- ✅ `progress.py` - Suivi de progression
- ✅ `security.py` - Sécurité
- ✅ `linear_config.py` - Config Linear
- ✅ `prompts/initializer_prompt.md` - Template initializer
- ✅ `prompts/initializer_bis_prompt.md` - Template initializer bis
- ✅ `prompts/coding_prompt.md` - Template coding agent
- ✅ `requirements.txt` - Dépendances Python

## Fichiers à Créer pour Votre Application

- ✅ `prompts/app_spec.txt` - **Votre spécification (le seul fichier à créer !)**

## Résumé

Pour créer une nouvelle application :

1. **Copiez la structure XML** de `prompts/app_spec.txt` (exemple Claude Clone)
2. **Adaptez le contenu** à votre application
3. **Définissez toutes vos fonctionnalités** avec des balises `<feature_X>`
4. **Lancez** : `python autonomous_agent_demo.py --project-dir ./mon_app`
5. **Suivez le progrès** dans Linear

Le framework s'occupe du reste ! 🚀





