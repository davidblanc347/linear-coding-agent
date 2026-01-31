# Plan de Migration : API Anthropic → Claude Agent SDK TypeScript

> Version 1.1 - Janvier 2026
> Migration du backend Ikario vers le Claude Agent SDK

---

## Statut de Migration (mise à jour: 31 janvier 2026)

| Phase | Statut | Notes |
|-------|--------|-------|
| Phase 0 | ✅ TERMINÉ | Token OAuth configuré, SDK installé, backups créés |
| Phase 1 | ✅ TERMINÉ | `agentSdkService.js` créé avec toutes les fonctions |
| Phase 2 | ✅ TERMINÉ | `messages.js` et `claude.js` migrés vers SDK |
| Phase 3 | ✅ TERMINÉ | `@anthropic-ai/sdk` supprimé de package.json |
| Phase 4 | ✅ TERMINÉ | Tests et validation (modules importés OK) |
| Phase 5 | ✅ TERMINÉ | Mode AGENT auto-poïétique (`/api/agent/evolve`) |

**Fichiers backupés** (`backups/pre-agent-sdk/`):
- `messages.js`, `claude.js`, `unifiedRagClient.js`, `tavilyMcpClient.js`, `toolExecutor.js`

**Note**: Les clients MCP (`unifiedRagClient.js`, etc.) sont conservés car utilisés par les routes directes (`/api/rag`, `/api/memory`, `/api/tavily`) pour l'accès hors-contexte chat.

---

## Contexte

### Objectif

Remplacer l'utilisation de l'API Anthropic (`@anthropic-ai/sdk` avec `ANTHROPIC_API_KEY`) par le Claude Agent SDK (`@anthropic-ai/claude-agent-sdk` avec `CLAUDE_CODE_OAUTH_TOKEN`).

### Pourquoi ?

1. **Unification** : Un seul SDK pour le chat ET les capacités agent
2. **Simplification** : Le SDK gère automatiquement la boucle tool-use
3. **MCP intégré** : Les serveurs MCP sont déclarés dans les options, plus besoin de clients séparés
4. **Auto-poïétique** : Permet à Ikario de se modifier lui-même (Phase 5)

### Décision architecturale

- **SDK choisi** : TypeScript (`@anthropic-ai/claude-agent-sdk`) - intégration directe dans le backend Node.js
- **Extended Thinking** : Le contenu "thinking" ne sera plus affiché au frontend (limitation du SDK)

---

## Architecture

### Avant (actuel)

```
Frontend (React)
     ↓
Backend (Express)
     ↓
@anthropic-ai/sdk (ANTHROPIC_API_KEY)
     ↓
anthropic.messages.stream()
     ↓
Boucle while pour tool_use
     ↓
toolExecutor.js
     ↓
4 MCP Clients séparés:
├── unifiedRagClient.js (Weaviate)
├── tavilyMcpClient.js (Internet)
├── libraryRagMcpClient.js (Documents)
└── mcpClient.js (base)
```

### Après (cible)

```
Frontend (React)
     ↓
Backend (Express)
     ↓
@anthropic-ai/claude-agent-sdk (CLAUDE_CODE_OAUTH_TOKEN)
     ↓
query() avec for await (streaming)
     ↓
Gestion automatique des tools par le SDK
     ↓
MCP servers dans options.mcpServers:
├── unified_rag (stdio → Python)
└── tavily (stdio → npx)
```

---

## SDK TypeScript - Référence

### Installation

```bash
npm install @anthropic-ai/claude-agent-sdk
```

### API principale

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Your prompt",
  options: {
    model: "claude-opus-4-5-20251101",
    systemPrompt: "Tu es Ikario...",
    maxThinkingTokens: 5000,
    mcpServers: {
      unified_rag: {
        command: "python",
        args: ["/path/to/mcp_server.py"],
        env: { WEAVIATE_URL: "http://localhost:8080" }
      }
    },
    allowedTools: ["mcp__unified_rag__*"],
    permissionMode: "bypassPermissions"
  }
})) {
  if (message.type === 'result' && message.subtype === 'success') {
    console.log(message.result);
  }
}
```

### Types de messages

| Type | Description |
|------|-------------|
| `system` (subtype: `init`) | Initialisation, liste des MCP servers |
| `assistant` | Réponse avec content blocks (text, tool_use) |
| `result` | Résultat final avec usage, cost, duration |

### Options disponibles

| Option | Type | Description |
|--------|------|-------------|
| `model` | string | Modèle Claude à utiliser |
| `systemPrompt` | string | Prompt système |
| `maxThinkingTokens` | number | Budget Extended Thinking (1024-32000) |
| `mcpServers` | object | Configuration des serveurs MCP |
| `allowedTools` | string[] | Outils autorisés (wildcards supportés) |
| `permissionMode` | string | `default`, `acceptEdits`, `bypassPermissions` |
| `cwd` | string | Répertoire de travail |
| `hooks` | object | Hooks PreToolUse, PostToolUse, etc. |

---

## Phases de Migration

### Phase 0 : Préparation (1 jour)

| Tâche | Description | Commande/Action |
|-------|-------------|-----------------|
| 0.1 | Générer le token OAuth | `claude setup-token` |
| 0.2 | Ajouter au `.env` d'Ikario | `CLAUDE_CODE_OAUTH_TOKEN='...'` |
| 0.3 | Installer le SDK | `cd server && npm install @anthropic-ai/claude-agent-sdk` |
| 0.4 | Créer branche Git | `git checkout -b feature/agent-sdk-migration` |
| 0.5 | Backup fichiers actuels | Copier `messages.js`, `claude.js`, etc. |

**Validation Phase 0 :**
```bash
# Vérifier le token
echo $CLAUDE_CODE_OAUTH_TOKEN

# Vérifier le package
cd generations/ikario/server && npm ls @anthropic-ai/claude-agent-sdk
```

---

### Phase 1 : Service Agent SDK (2-3 jours)

**Objectif** : Créer `server/services/agentSdkService.js`

#### 1.1 Structure du service

```javascript
// server/services/agentSdkService.js
import { query } from "@anthropic-ai/claude-agent-sdk";

/**
 * Crée une query Agent SDK avec la configuration Ikario
 */
export function createAgentQuery(prompt, ikarioOptions = {}) {
  const {
    model = "claude-sonnet-4-5-20250929",
    systemPrompt = "",
    thinkingBudget = 5000,
    enableMemory = true,
    enableTavily = false,
    cwd = null,
    additionalTools = []
  } = ikarioOptions;

  // Construire les MCP servers
  const mcpServers = {};
  const allowedTools = [];

  if (enableMemory) {
    mcpServers.unified_rag = {
      command: "python",
      args: [process.env.UNIFIED_RAG_SERVER_PATH],
      env: {
        WEAVIATE_URL: process.env.WEAVIATE_URL,
        WEAVIATE_API_KEY: process.env.WEAVIATE_API_KEY || ""
      }
    };
    allowedTools.push("mcp__unified_rag__*");
  }

  if (enableTavily && process.env.TAVILY_API_KEY) {
    mcpServers.tavily = {
      command: "npx",
      args: ["-y", "@anthropic-ai/mcp-tavily"],
      env: {
        TAVILY_API_KEY: process.env.TAVILY_API_KEY
      }
    };
    allowedTools.push("mcp__tavily__*");
  }

  // Ajouter les outils supplémentaires
  allowedTools.push(...additionalTools);

  return query({
    prompt,
    options: {
      model,
      systemPrompt,
      maxThinkingTokens: thinkingBudget,
      mcpServers,
      allowedTools,
      permissionMode: "bypassPermissions",
      ...(cwd && { cwd })
    }
  });
}

/**
 * Construit le system prompt complet pour Ikario
 */
export function buildIkarioSystemPrompt(options = {}) {
  const {
    globalInstructions = "",
    projectInstructions = "",
    enableMemory = true,
    enableTavily = false
  } = options;

  const parts = [];

  // Date/Heure
  const now = new Date();
  parts.push(`## Date et Heure Actuelles
Date: ${now.toLocaleDateString('fr-FR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
Heure: ${now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
Fuseau: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`);

  // Instructions globales
  if (globalInstructions.trim()) {
    parts.push(`## Instructions Globales\n${globalInstructions.trim()}`);
  }

  // Instructions projet
  if (projectInstructions.trim()) {
    parts.push(`## Instructions Projet\n${projectInstructions.trim()}`);
  }

  // Mémoire
  if (enableMemory) {
    parts.push(`## Mémoire
Tu as une mémoire persistante. Les conversations sont sauvegardées AUTOMATIQUEMENT.
Utilise add_thought pour tes réflexions internes, search_memories pour chercher.`);
  }

  // Internet
  if (enableTavily) {
    parts.push(`## Internet
Tu as accès à internet via Tavily: tavily_search (web), tavily_search_news (actualités).
Cite tes sources.`);
  }

  return parts.join('\n\n');
}
```

#### 1.2 Tests du service

```javascript
// server/services/__tests__/agentSdkService.test.js
import { createAgentQuery, buildIkarioSystemPrompt } from '../agentSdkService.js';

// Test basique
async function testBasicQuery() {
  const q = createAgentQuery("Dis bonjour", {
    model: "claude-sonnet-4-5-20250929",
    systemPrompt: "Tu es Ikario.",
    enableMemory: false,
    enableTavily: false
  });

  for await (const message of q) {
    console.log(message.type, message);
    if (message.type === 'result') {
      console.log("Résultat:", message.result);
    }
  }
}
```

**Validation Phase 1 :**
```bash
# Test manuel du service
node -e "
import('./services/agentSdkService.js').then(async ({ createAgentQuery }) => {
  const q = createAgentQuery('Dis bonjour', { enableMemory: false });
  for await (const m of q) {
    if (m.type === 'result') console.log(m.result);
  }
});
"
```

---

### Phase 2 : Migration Route Messages (2-3 jours)

**Objectif** : Modifier `server/routes/messages.js` pour utiliser le SDK

#### 2.1 Changements principaux

| Avant | Après |
|-------|-------|
| `import Anthropic from '@anthropic-ai/sdk'` | `import { createAgentQuery, buildIkarioSystemPrompt } from '../services/agentSdkService.js'` |
| `const anthropic = new Anthropic({ apiKey })` | Supprimé (le SDK utilise CLAUDE_CODE_OAUTH_TOKEN) |
| `anthropic.messages.stream({...})` | `createAgentQuery(prompt, options)` |
| `stream.on('text', ...)` | `for await (const message of query)` |
| Boucle while tool_use | Supprimée (automatique) |

#### 2.2 Mapping SSE

```javascript
// Nouveau code streaming
const q = createAgentQuery(content, {
  model: conversation.model,
  systemPrompt: buildIkarioSystemPrompt({
    globalInstructions,
    projectInstructions,
    enableMemory: true,
    enableTavily: conversation.enable_internet
  }),
  thinkingBudget: conversation.thinking_budget_tokens,
  enableMemory: true,
  enableTavily: conversation.enable_internet
});

for await (const message of q) {
  // Messages assistant avec contenu
  if (message.type === 'assistant') {
    for (const block of message.message.content) {
      if (block.type === 'text') {
        res.write(`data: ${JSON.stringify({ type: 'content', text: block.text })}\n\n`);
      }
      if (block.type === 'tool_use') {
        res.write(`data: ${JSON.stringify({ type: 'tool_use', name: block.name })}\n\n`);
      }
    }
  }

  // Résultat final
  if (message.type === 'result') {
    if (message.subtype === 'success') {
      res.write(`data: ${JSON.stringify({
        type: 'done',
        id: assistantMessageId,
        usage: {
          inputTokens: message.usage?.input_tokens || 0,
          outputTokens: message.usage?.output_tokens || 0
        }
      })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({
        type: 'error',
        message: message.result || 'Erreur inconnue'
      })}\n\n`);
    }
  }
}
```

#### 2.3 Fichiers à modifier

| Fichier | Modifications |
|---------|---------------|
| `server/routes/messages.js` | Route principale streaming |
| `server/routes/claude.js` | Route API Claude (si utilisée) |
| `server/index.js` | Supprimer init des anciens clients MCP |

**Validation Phase 2 :**
```bash
# Test streaming
curl -X POST http://localhost:3001/api/conversations/test-conv-id/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"content": "Bonjour Ikario"}'
```

---

### Phase 3 : Nettoyage (1-2 jours)

**Objectif** : Supprimer le code obsolète

#### 3.1 Fichiers à supprimer

```bash
# Services MCP obsolètes
rm server/services/unifiedRagClient.js
rm server/services/tavilyMcpClient.js
rm server/services/libraryRagMcpClient.js
rm server/services/mcpClient.js
rm server/services/toolExecutor.js

# Configs tools obsolètes (optionnel - peuvent être gardées comme référence)
# rm server/config/memoryTools.js
# rm server/config/tavilyTools.js
# rm server/config/libraryRagTools.js
```

#### 3.2 Dépendances à supprimer

```bash
cd server
npm uninstall @anthropic-ai/sdk
```

#### 3.3 Nettoyage des imports

Rechercher et supprimer dans tous les fichiers :
- `import Anthropic from '@anthropic-ai/sdk'`
- `import { ... } from '../services/unifiedRagClient.js'`
- `import { ... } from '../services/tavilyMcpClient.js'`
- `import { ... } from '../services/toolExecutor.js'`

**Validation Phase 3 :**
```bash
# Vérifier qu'il n'y a plus de références aux anciens fichiers
grep -r "unifiedRagClient" server/
grep -r "tavilyMcpClient" server/
grep -r "toolExecutor" server/
grep -r "@anthropic-ai/sdk" server/
```

---

### Phase 4 : Tests et Validation (2 jours)

| Test | Description | Commande |
|------|-------------|----------|
| 4.1 | Streaming SSE | Envoyer message, vérifier réponse temps réel |
| 4.2 | Outils mémoire | `add_thought`, `search_thoughts`, `search_memories` |
| 4.3 | Tavily | Recherche internet (si activé) |
| 4.4 | Images | Upload et analyse d'images |
| 4.5 | Tokens | Vérifier compteur tokens correct |
| 4.6 | Conversations | Multi-tours, contexte préservé |
| 4.7 | Projets | Instructions projet appliquées |

**Script de test complet :**
```bash
# Test conversation complète
./tests/test_agent_sdk_integration.sh
```

---

### Phase 5 : Mode AGENT Auto-poïétique (3-4 jours)

**Objectif** : Permettre à Ikario de modifier son propre code

#### 5.1 Nouvelle route

```javascript
// server/routes/agent.js
import express from 'express';
import { query } from '@anthropic-ai/claude-agent-sdk';

const router = express.Router();

// POST /api/agent/evolve
router.post('/evolve', async (req, res) => {
  const { task, context } = req.body;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const q = query({
    prompt: `
Contexte: ${context}
Tâche: ${task}

Instructions:
1. Analyse le code actuel avec Read/Grep
2. Planifie les modifications
3. Implémente avec Edit/Write
4. Documente dans la mémoire (add_thought)
`,
    options: {
      model: "claude-opus-4-5-20251101",
      systemPrompt: "Tu es Ikario en mode auto-modification...",
      allowedTools: [
        "Read", "Write", "Edit", "Glob", "Grep", "Bash",
        "mcp__unified_rag__add_thought",
        "mcp__unified_rag__search_thoughts"
      ],
      mcpServers: {
        unified_rag: {
          command: "python",
          args: [process.env.UNIFIED_RAG_SERVER_PATH],
          env: { WEAVIATE_URL: process.env.WEAVIATE_URL }
        }
      },
      cwd: process.env.IKARIO_PROJECT_DIR,
      hooks: {
        PreToolUse: [{
          matcher: 'Write|Edit',
          hooks: [protectSensitiveFiles]
        }]
      },
      permissionMode: "acceptEdits"
    }
  });

  for await (const message of q) {
    res.write(`data: ${JSON.stringify(message)}\n\n`);
  }

  res.end();
});

// Hook de sécurité
async function protectSensitiveFiles(input, toolUseID, { signal }) {
  const filePath = input.tool_input?.file_path || '';
  const fileName = filePath.split('/').pop();

  const protected = ['.env', 'api-key', 'credentials', 'secret'];
  if (protected.some(p => fileName.includes(p))) {
    return {
      hookSpecificOutput: {
        hookEventName: input.hook_event_name,
        decision: 'deny',
        reason: `Fichier protégé: ${fileName}`
      }
    };
  }
  return {};
}

export default router;
```

#### 5.2 Variables d'environnement

Ajouter dans `.env` :
```bash
IKARIO_PROJECT_DIR=/path/to/generations/ikario
```

#### 5.3 UI (optionnel)

Créer un composant React pour déclencher l'auto-modification depuis l'interface.

---

## Variables d'Environnement Finales

```bash
# === CLAUDE AGENT SDK (nouveau) ===
CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'  # De: claude setup-token

# === WEAVIATE (inchangé) ===
WEAVIATE_URL=http://localhost:8080
WEAVIATE_API_KEY=                           # Optionnel pour cloud

# === UNIFIED RAG MCP (inchangé) ===
UNIFIED_RAG_SERVER_PATH=/path/to/library_rag/mcp_server.py

# === TAVILY (inchangé) ===
TAVILY_API_KEY=tvly-xxxxx

# === MODE AGENT (nouveau) ===
IKARIO_PROJECT_DIR=/path/to/generations/ikario

# === OBSOLÈTES (à supprimer) ===
# ANTHROPIC_API_KEY=sk-ant-xxxxx  # Plus nécessaire
```

---

## Récapitulatif

| Phase | Durée | Objectif | Livrable |
|-------|-------|----------|----------|
| 0 | 1 jour | Préparation | Token, package, branche |
| 1 | 2-3 jours | Service SDK | `agentSdkService.js` |
| 2 | 2-3 jours | Migration routes | `messages.js` modifié |
| 3 | 1-2 jours | Nettoyage | Anciens fichiers supprimés |
| 4 | 2 jours | Tests | Validation complète |
| 5 | 3-4 jours | Mode AGENT | `/api/agent/evolve` |

**Total : 11-15 jours**

---

## Breaking Changes

1. **Extended Thinking** : Le contenu "thinking" n'est plus affiché au frontend
2. **API Key** : `ANTHROPIC_API_KEY` remplacé par `CLAUDE_CODE_OAUTH_TOKEN`
3. **MCP Clients** : Les 4 clients séparés sont supprimés
4. **toolExecutor** : Supprimé, géré automatiquement par le SDK

---

## Rollback

En cas de problème, restaurer depuis la branche `main` :

```bash
git checkout main
git branch -D feature/agent-sdk-migration
```

---

*Document créé le 31 janvier 2026*
*Migration vers Claude Agent SDK TypeScript*
