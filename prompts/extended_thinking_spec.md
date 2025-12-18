# Extended Thinking Feature Specification
## Claude.ai Clone - Enhanced Reasoning Integration

---

## 1. Vue d'ensemble

Extended Thinking est une fonctionnalité de Claude qui permet d'activer des capacités de raisonnement améliorées pour les tâches complexes. Claude génère des blocs `thinking` où il expose son processus de réflexion interne étape par étape avant de fournir sa réponse finale.

### Fonctionnement
- Claude crée des blocs `thinking` contenant son raisonnement interne
- Ces blocs sont suivis de blocs `text` avec la réponse finale
- Le processus de réflexion est résumé (pour Claude 4+) mais facturé au tarif complet
- Améliore significativement la qualité des réponses pour les tâches complexes

### Cas d'usage
- Mathématiques complexes et calculs
- Programmation et débogage
- Analyse approfondie de documents
- Raisonnement logique multi-étapes
- Résolution de problèmes complexes

---

## 2. Modèles supportés

| Modèle | ID | Support Extended Thinking |
|--------|----|-----------------------------|
| Claude Sonnet 4.5 | claude-sonnet-4-5-20250929 | ✅ Oui |
| Claude Sonnet 4 | claude-sonnet-4-20250514 | ✅ Oui |
| Claude Haiku 4.5 | claude-haiku-4-5-20251001 | ✅ Oui |
| Claude Opus 4.5 | claude-opus-4-5-20251101 | ✅ Oui (avec préservation thinking) |
| Claude Opus 4.1 | claude-opus-4-1-20250805 | ✅ Oui |
| Claude Opus 4 | claude-opus-4-20250514 | ✅ Oui |
| Claude Sonnet 3.7 | claude-3-7-sonnet-20250219 | ✅ Oui (déprécié, thinking complet) |

**Note**: Claude 4+ retourne du thinking résumé. Claude 3.7 retourne du thinking complet.

---

## 3. Architecture Backend

### 3.1 Modifications API Routes

#### `server/routes/claude.js`

**Ajouts nécessaires**:

```javascript
// POST /api/claude/chat - Non-streaming avec thinking
router.post('/chat', async (req, res) => {
  const {
    messages,
    model,
    system,
    maxTokens = 4096,
    temperature = 1,
    enableMemoryTools = true,
    // Nouveaux paramètres thinking
    enableThinking = false,
    thinkingBudgetTokens = 10000
  } = req.body;

  const apiParams = {
    model,
    max_tokens: maxTokens,
    temperature,
    system: buildSystemPrompt(system, enableMemoryTools),
    messages: conversationMessages
  };

  // Ajouter thinking si activé
  if (enableThinking) {
    apiParams.thinking = {
      type: 'enabled',
      budget_tokens: thinkingBudgetTokens
    };
  }

  // Ajouter tools si activé
  if (tools.length > 0) {
    apiParams.tools = tools;
  }

  const response = await anthropic.messages.create(apiParams);
  // ... rest of logic
});
```

#### `server/routes/messages.js`

**Modifications dans les endpoints de streaming**:

```javascript
// POST /:conversationId/messages/stream
router.post('/:conversationId/messages', async (req, res) => {
  // Parse settings avec thinking support
  const settings = JSON.parse(conversation.settings || '{}');
  const model = conversation.model || 'claude-sonnet-4-5-20250929';
  const temperature = settings.temperature || 1;
  const maxTokens = settings.maxTokens || 4096;
  const enableThinking = settings.enableThinking || false;
  const thinkingBudgetTokens = settings.thinkingBudgetTokens || 10000;

  // Build request options
  const requestOptions = {
    model,
    max_tokens: maxTokens,
    temperature,
    messages: conversationMessages
  };

  // Add thinking if enabled
  if (enableThinking) {
    requestOptions.thinking = {
      type: 'enabled',
      budget_tokens: thinkingBudgetTokens
    };
  }

  // Add system prompt
  if (systemPrompt) {
    requestOptions.system = systemPrompt;
  }

  // Add tools
  if (tools.length > 0) {
    requestOptions.tools = tools;
  }

  // Create streaming response
  const stream = await anthropic.messages.stream(requestOptions);

  // Handle thinking deltas in stream
  for await (const event of stream) {
    if (event.type === 'content_block_start') {
      if (event.content_block.type === 'thinking') {
        console.log('[Messages] Thinking block started');
        res.write(`data: ${JSON.stringify({
          type: 'thinking_start',
          index: event.index
        })}\n\n`);
      }
    } else if (event.type === 'content_block_delta') {
      if (event.delta.type === 'thinking_delta') {
        fullThinkingContent += event.delta.thinking;
        res.write(`data: ${JSON.stringify({
          type: 'thinking',
          text: event.delta.thinking
        })}\n\n`);
      } else if (event.delta.type === 'text_delta') {
        fullContent += event.delta.text;
        res.write(`data: ${JSON.stringify({
          type: 'content',
          text: event.delta.text
        })}\n\n`);
      }
    }
  }
});
```

### 3.2 Nouveaux Types de Réponse

**Structure de réponse avec thinking**:

```javascript
{
  "content": [
    {
      "type": "thinking",
      "thinking": "Let me analyze this step by step...",
      "signature": "WaUjzkypQ2mUEVM36O2TxuC06KN8xyfbJwyem2dw3URve..."
    },
    {
      "type": "text",
      "text": "Based on my analysis..."
    }
  ]
}
```

**Events de streaming**:

```javascript
// Événement de début de thinking
{
  "type": "thinking_start",
  "index": 0
}

// Événement de delta thinking
{
  "type": "thinking",
  "text": "Let me analyze..."
}

// Événement de fin de thinking (automatique avec content_block_stop)
{
  "type": "thinking_stop",
  "index": 0
}

// Événements de contenu normal
{
  "type": "content",
  "text": "Based on..."
}
```

### 3.3 Base de Données

#### Modifications du schéma `conversations`

```sql
-- Ajouter colonne pour activer thinking par conversation
ALTER TABLE conversations ADD COLUMN enable_thinking INTEGER DEFAULT 0;
ALTER TABLE conversations ADD COLUMN thinking_budget_tokens INTEGER DEFAULT 10000;
```

#### Modifications du schéma `messages`

```sql
-- Ajouter colonne pour stocker thinking content
ALTER TABLE messages ADD COLUMN thinking_content TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN thinking_signature TEXT DEFAULT NULL;
```

**Migration dans `server/db/index.js`**:

```javascript
// Add thinking columns if they don't exist
const hasThinkingColumns = db.prepare(`
  SELECT COUNT(*) as count FROM pragma_table_info('conversations')
  WHERE name IN ('enable_thinking', 'thinking_budget_tokens')
`).get();

if (hasThinkingColumns.count < 2) {
  console.log('Adding thinking columns to conversations table...');
  db.exec(`
    ALTER TABLE conversations ADD COLUMN enable_thinking INTEGER DEFAULT 0;
    ALTER TABLE conversations ADD COLUMN thinking_budget_tokens INTEGER DEFAULT 10000;
  `);
}

const hasMessageThinking = db.prepare(`
  SELECT COUNT(*) as count FROM pragma_table_info('messages')
  WHERE name IN ('thinking_content', 'thinking_signature')
`).get();

if (hasMessageThinking.count < 2) {
  console.log('Adding thinking columns to messages table...');
  db.exec(`
    ALTER TABLE messages ADD COLUMN thinking_content TEXT DEFAULT NULL;
    ALTER TABLE messages ADD COLUMN thinking_signature TEXT DEFAULT NULL;
  `);
}
```

---

## 4. Architecture Frontend

### 4.1 Interface Utilisateur

#### Nouveau composant: `ThinkingBlock`

**Fichier**: `src/components/ThinkingBlock.jsx`

```jsx
import React, { useState } from 'react';

function ThinkingBlock({ thinking, signature, isStreaming }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-4 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950">
      {/* Header avec toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <div className="flex items-center gap-2">
          {/* Icône cerveau/pensée */}
          <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/>
          </svg>
          <span className="font-medium text-blue-900 dark:text-blue-100">
            {isStreaming ? 'Thinking...' : 'Claude\'s reasoning'}
          </span>
          {isStreaming && (
            <div className="flex gap-1">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
            </div>
          )}
        </div>
        <svg
          className={`w-5 h-5 text-blue-600 dark:text-blue-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Contenu thinking (collapsible) */}
      {isExpanded && (
        <div className="px-3 pb-3 text-sm text-blue-800 dark:text-blue-200 whitespace-pre-wrap font-mono">
          {thinking || 'Thinking in progress...'}
        </div>
      )}
    </div>
  );
}

export default ThinkingBlock;
```

#### Modifications dans `src/App.jsx`

**1. État pour thinking dans Message Component**:

```jsx
function Message({ message, isStreaming }) {
  const [thinkingContent, setThinkingContent] = useState(message.thinking_content || '');
  const [isThinkingStreaming, setIsThinkingStreaming] = useState(false);

  return (
    <div className="message">
      {/* Afficher thinking block si présent */}
      {thinkingContent && (
        <ThinkingBlock
          thinking={thinkingContent}
          signature={message.thinking_signature}
          isStreaming={isThinkingStreaming}
        />
      )}

      {/* Contenu normal du message */}
      <div className="message-content">
        {message.content}
      </div>
    </div>
  );
}
```

**2. Settings Panel - Ajouter contrôles thinking**:

```jsx
function ConversationSettings({ conversation, onUpdate }) {
  const [settings, setSettings] = useState(JSON.parse(conversation.settings || '{}'));

  return (
    <div className="settings-panel">
      {/* Existing settings */}
      <div className="setting-group">
        <label>Temperature</label>
        <input type="range" ... />
      </div>

      {/* Nouveau: Extended Thinking Toggle */}
      <div className="setting-group">
        <label className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/>
            </svg>
            Extended Thinking
          </span>
          <input
            type="checkbox"
            checked={settings.enableThinking || false}
            onChange={(e) => {
              const newSettings = {
                ...settings,
                enableThinking: e.target.checked
              };
              setSettings(newSettings);
              onUpdate(newSettings);
            }}
            className="w-4 h-4"
          />
        </label>
        <p className="text-xs text-gray-500 mt-1">
          Enable enhanced reasoning for complex tasks
        </p>
      </div>

      {/* Thinking Budget (si thinking activé) */}
      {settings.enableThinking && (
        <div className="setting-group">
          <label>Thinking Budget</label>
          <input
            type="range"
            min="1024"
            max="32000"
            step="1024"
            value={settings.thinkingBudgetTokens || 10000}
            onChange={(e) => {
              const newSettings = {
                ...settings,
                thinkingBudgetTokens: parseInt(e.target.value)
              };
              setSettings(newSettings);
              onUpdate(newSettings);
            }}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>1K tokens</span>
            <span>{(settings.thinkingBudgetTokens || 10000).toLocaleString()} tokens</span>
            <span>32K tokens</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Higher budgets enable more thorough analysis
          </p>
        </div>
      )}
    </div>
  );
}
```

**3. Streaming Handler - Gérer thinking deltas**:

```jsx
async function sendMessage(content) {
  // ... existing code ...

  const eventSource = new EventSource(`${API_BASE}/conversations/${conversationId}/messages`);

  let currentThinking = '';
  let currentContent = '';
  let isInThinkingBlock = false;

  eventSource.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'thinking_start':
        isInThinkingBlock = true;
        currentThinking = '';
        setIsThinkingStreaming(true);
        break;

      case 'thinking':
        currentThinking += data.text;
        // Update thinking content in real-time
        setThinkingContent(currentThinking);
        break;

      case 'thinking_stop':
        isInThinkingBlock = false;
        setIsThinkingStreaming(false);
        break;

      case 'content':
        currentContent += data.text;
        // Update message content
        setMessageContent(currentContent);
        break;

      case 'done':
        eventSource.close();
        // Save message with thinking
        saveMessage({
          content: currentContent,
          thinking_content: currentThinking,
          thinking_signature: data.thinking_signature
        });
        break;
    }
  });
}
```

### 4.2 Indicateurs Visuels

#### Badge "Thinking Enabled" dans conversation list

```jsx
function ConversationListItem({ conversation }) {
  const settings = JSON.parse(conversation.settings || '{}');

  return (
    <div className="conversation-item">
      <div className="conversation-title">{conversation.title}</div>

      {/* Badge thinking */}
      {settings.enableThinking && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200">
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/>
          </svg>
          Thinking
        </span>
      )}
    </div>
  );
}
```

---

## 5. Gestion du Streaming

### 5.1 Events Sequence

```
User: "Solve this complex math problem..."

Event 1: thinking_start
  → Show thinking block with loading animation

Event 2-N: thinking deltas
  → Update thinking content incrementally
  → Show typing animation

Event N+1: thinking_stop (implicit with content_block_stop)
  → Stop thinking animation
  → Mark thinking complete

Event N+2: content_start
  → Start showing answer

Event N+3-M: content deltas
  → Stream answer text

Event M+1: done
  → Save complete message with thinking + content
```

### 5.2 Error Handling

**Timeout pour thinking**:
```javascript
const THINKING_TIMEOUT = 120000; // 2 minutes

let thinkingTimeout = setTimeout(() => {
  console.warn('[Thinking] Timeout reached');
  res.write(`data: ${JSON.stringify({
    type: 'thinking_timeout',
    message: 'Thinking process is taking longer than expected...'
  })}\n\n`);
}, THINKING_TIMEOUT);

// Clear timeout when thinking completes
stream.on('content_block_stop', () => {
  clearTimeout(thinkingTimeout);
});
```

**Redacted thinking blocks**:
```javascript
if (event.content_block.type === 'redacted_thinking') {
  console.log('[Thinking] Redacted thinking block detected');
  res.write(`data: ${JSON.stringify({
    type: 'thinking_redacted',
    message: 'Some reasoning has been encrypted for safety'
  })}\n\n`);
}
```

---

## 6. Compatibilité avec Tools

### 6.1 Préservation des Thinking Blocks

**Important**: Lors de l'utilisation de tools avec thinking, il faut préserver les thinking blocks:

```javascript
// Quand Claude utilise un tool
if (finalMessage.stop_reason === 'tool_use') {
  // Extraire tous les blocks thinking ET tool_use
  const thinkingBlocks = finalMessage.content.filter(b =>
    b.type === 'thinking' || b.type === 'redacted_thinking'
  );
  const toolUseBlocks = finalMessage.content.filter(b =>
    b.type === 'tool_use'
  );

  // Ajouter à la conversation
  conversationMessages.push({
    role: 'assistant',
    content: [...thinkingBlocks, ...toolUseBlocks]
  });

  // Exécuter tools
  const toolResults = await processToolCalls(toolUseBlocks);

  // Continuer avec les résultats
  conversationMessages.push({
    role: 'user',
    content: toolResults
  });
}
```

### 6.2 Interleaved Thinking (Beta)

Pour activer le thinking entre les tool calls:

```javascript
// Ajouter le beta header
const response = await anthropic.messages.create({
  model: 'claude-opus-4-5',
  thinking: { type: 'enabled', budget_tokens: 20000 },
  tools: memoryTools,
  messages: conversationMessages
}, {
  headers: {
    'anthropic-beta': 'interleaved-thinking-2025-05-14'
  }
});
```

---

## 7. Pricing & Token Management

### 7.1 Facturation

**Résumé (Claude 4+)**:
- Input tokens: Tokens de la requête (excluant thinking précédents)
- Output tokens (facturés): Tokens thinking originaux complets
- Output tokens (visibles): Tokens thinking résumés affichés
- Pas de charge: Tokens utilisés pour générer le résumé

**Important**: Le nombre de tokens facturés ≠ tokens visibles dans la réponse.

### 7.2 Token Tracking

**Backend - Logging détaillé**:

```javascript
// Après réponse avec thinking
console.log('[Thinking Tokens]', {
  input_tokens: response.usage.input_tokens,
  output_tokens: response.usage.output_tokens, // Inclut thinking complet
  visible_thinking_tokens: calculateTokens(thinkingContent), // Thinking résumé
  text_output_tokens: calculateTokens(textContent)
});

// Sauvegarder dans usage_tracking
db.prepare(`
  INSERT INTO usage_tracking (
    id, user_id, conversation_id, message_id, model,
    input_tokens, output_tokens, thinking_tokens, created_at
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
  uuidv4(), 'default', conversationId, messageId, model,
  response.usage.input_tokens,
  response.usage.output_tokens,
  calculateTokens(thinkingContent), // Pour tracking
  new Date().toISOString()
);
```

**Frontend - Affichage dans usage stats**:

```jsx
function UsageStats({ conversation }) {
  return (
    <div className="usage-stats">
      <div className="stat">
        <label>Total Tokens</label>
        <span>{conversation.token_count.toLocaleString()}</span>
      </div>

      {conversation.thinking_tokens > 0 && (
        <>
          <div className="stat text-blue-600">
            <label>Thinking Tokens</label>
            <span>{conversation.thinking_tokens.toLocaleString()}</span>
          </div>
          <p className="text-xs text-gray-500">
            Thinking tokens are summarized but billed at full rate
          </p>
        </>
      )}
    </div>
  );
}
```

---

## 8. Best Practices

### 8.1 Quand activer thinking

**Recommandé pour**:
- ✅ Problèmes mathématiques complexes
- ✅ Analyse de code et debugging
- ✅ Raisonnement logique multi-étapes
- ✅ Analyse approfondie de documents
- ✅ Tâches nécessitant planification

**Pas nécessaire pour**:
- ❌ Questions simples
- ❌ Tâches créatives (écriture, brainstorming)
- ❌ Conversations courtes
- ❌ Réponses rapides

### 8.2 Budget Recommendations

| Type de tâche | Budget recommandé |
|---------------|-------------------|
| Calculs simples | 1,024 - 4,096 tokens |
| Analyse standard | 4,096 - 10,000 tokens |
| Problèmes complexes | 10,000 - 16,000 tokens |
| Tâches très complexes | 16,000 - 32,000 tokens |
| Recherche approfondie | 32,000+ tokens (batch) |

**Note**: Au-delà de 32K tokens, utiliser batch processing pour éviter les timeouts.

### 8.3 UI/UX Guidelines

1. **Visibility**: Thinking blocks doivent être collapsibles par défaut
2. **Feedback**: Montrer animation pendant le thinking streaming
3. **Transparency**: Indiquer clairement quand thinking est actif
4. **Performance**: Thinking peut augmenter le temps de réponse de 2-5x
5. **Settings**: Permettre d'activer/désactiver par conversation

---

## 9. Plan d'Implémentation

### Phase 1: Backend Core (2-3h)
- [ ] Modifier `server/routes/claude.js` pour supporter thinking parameter
- [ ] Modifier `server/routes/messages.js` pour streaming thinking
- [ ] Ajouter colonnes DB pour thinking storage
- [ ] Migration base de données
- [ ] Tests API avec thinking enabled

### Phase 2: Frontend UI (3-4h)
- [ ] Créer composant `ThinkingBlock.jsx`
- [ ] Intégrer thinking display dans messages
- [ ] Ajouter toggle thinking dans settings
- [ ] Ajouter thinking budget slider
- [ ] Tests visuels et UX

### Phase 3: Streaming & Real-time (2-3h)
- [ ] Implémenter thinking_delta handling
- [ ] Animations de streaming
- [ ] Gestion des timeouts
- [ ] Error handling pour redacted thinking
- [ ] Tests de streaming

### Phase 4: Tools Integration (2h)
- [ ] Préservation thinking blocks avec tools
- [ ] Tests thinking + memory tools
- [ ] Tests thinking + autres tools futurs

### Phase 5: Polish & Optimization (2h)
- [ ] Token tracking et logging
- [ ] Usage analytics pour thinking
- [ ] Documentation utilisateur
- [ ] Performance optimization
- [ ] Tests end-to-end

### Phase 6: Testing & Deployment (1-2h)
- [ ] Tests avec différents modèles
- [ ] Tests avec différents budgets
- [ ] Tests cas d'edge (redacted, timeouts)
- [ ] Commit et push
- [ ] Documentation finale

**Temps total estimé**: 12-16 heures

---

## 10. Exemples de Code Complets

### 10.1 Exemple Backend Complet

```javascript
// server/routes/messages.js - POST /:conversationId/messages

router.post('/:conversationId/messages', async (req, res) => {
  const db = getDatabase();
  const { conversationId } = req.params;
  const { content, images } = req.body;

  // Validate conversation exists
  const conversation = db.prepare('SELECT * FROM conversations WHERE id = ? AND is_deleted = 0')
    .get(conversationId);

  if (!conversation) {
    return res.status(404).json({ error: { message: 'Conversation not found', status: 404 } });
  }

  // Set up SSE headers
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  // Parse settings with thinking support
  const settings = JSON.parse(conversation.settings || '{}');
  const model = conversation.model || 'claude-sonnet-4-5-20250929';
  const temperature = settings.temperature || 1;
  const maxTokens = settings.maxTokens || 4096;
  const enableThinking = settings.enableThinking || false;
  const thinkingBudgetTokens = settings.thinkingBudgetTokens || 10000;
  const enableMemoryTools = true;

  // Save user message
  const userMessageId = uuidv4();
  const now = new Date().toISOString();

  db.prepare(`
    INSERT INTO messages (id, conversation_id, role, content, created_at, images)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(userMessageId, conversationId, 'user', content, now, JSON.stringify(images || []));

  // Get conversation history
  const dbMessages = db.prepare(`
    SELECT role, content, images FROM messages
    WHERE conversation_id = ?
    ORDER BY created_at ASC
  `).all(conversationId);

  // Format messages for Claude API
  const apiMessages = dbMessages.map(m => ({
    role: m.role,
    content: m.content
  }));

  // Get tools and system prompt
  const tools = enableMemoryTools ? getMemoryTools() : [];
  const systemPrompt = buildSystemPrompt(
    getGlobalCustomInstructions(),
    getProjectCustomInstructions(conversation.project_id),
    enableMemoryTools
  );

  // Tracking variables
  const assistantMessageId = uuidv4();
  let fullThinkingContent = '';
  let thinkingSignature = '';
  let fullContent = '';
  let totalInputTokens = 0;
  let totalOutputTokens = 0;

  try {
    // Build request options
    const requestOptions = {
      model,
      max_tokens: maxTokens,
      temperature,
      messages: apiMessages
    };

    if (systemPrompt) {
      requestOptions.system = systemPrompt;
    }

    if (tools.length > 0) {
      requestOptions.tools = tools;
    }

    // Add thinking if enabled
    if (enableThinking) {
      requestOptions.thinking = {
        type: 'enabled',
        budget_tokens: thinkingBudgetTokens
      };
      console.log(`[Messages] Extended thinking enabled with budget: ${thinkingBudgetTokens}`);
    }

    // Create streaming response
    const stream = await anthropic.messages.stream(requestOptions);

    let isInThinkingBlock = false;
    let currentBlockIndex = -1;

    // Stream events to client
    for await (const event of stream) {
      if (event.type === 'content_block_start') {
        currentBlockIndex = event.index;

        if (event.content_block.type === 'thinking') {
          isInThinkingBlock = true;
          console.log('[Messages] Thinking block started');
          res.write(`data: ${JSON.stringify({
            type: 'thinking_start',
            index: currentBlockIndex
          })}\n\n`);
        } else if (event.content_block.type === 'tool_use') {
          console.log(`[Messages] Tool use requested: ${event.content_block.name}`);
          res.write(`data: ${JSON.stringify({
            type: 'tool_use',
            tool: event.content_block.name,
            id: event.content_block.id
          })}\n\n`);
        }
      } else if (event.type === 'content_block_delta') {
        if (event.delta.type === 'thinking_delta') {
          fullThinkingContent += event.delta.thinking;
          res.write(`data: ${JSON.stringify({
            type: 'thinking',
            text: event.delta.thinking
          })}\n\n`);
        } else if (event.delta.type === 'text_delta') {
          fullContent += event.delta.text;
          res.write(`data: ${JSON.stringify({
            type: 'content',
            text: event.delta.text
          })}\n\n`);
        } else if (event.delta.type === 'signature_delta') {
          thinkingSignature += event.delta.signature;
        }
      } else if (event.type === 'content_block_stop') {
        if (isInThinkingBlock) {
          isInThinkingBlock = false;
          console.log('[Messages] Thinking block completed');
          res.write(`data: ${JSON.stringify({
            type: 'thinking_stop',
            index: currentBlockIndex
          })}\n\n`);
        }
      } else if (event.type === 'message_delta') {
        if (event.usage) {
          totalInputTokens += event.usage.input_tokens || 0;
          totalOutputTokens += event.usage.output_tokens || 0;
        }
      }
    }

    // Get final message
    const finalMessage = await stream.finalMessage();
    totalInputTokens = finalMessage.usage?.input_tokens || totalInputTokens;
    totalOutputTokens = finalMessage.usage?.output_tokens || totalOutputTokens;

    // Save assistant message with thinking
    const assistantNow = new Date().toISOString();
    db.prepare(`
      INSERT INTO messages (
        id, conversation_id, role, content,
        thinking_content, thinking_signature,
        created_at, tokens, finish_reason
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      assistantMessageId, conversationId, 'assistant', fullContent,
      fullThinkingContent || null, thinkingSignature || null,
      assistantNow, totalOutputTokens, finalMessage.stop_reason
    );

    // Update conversation
    db.prepare(`
      UPDATE conversations
      SET last_message_at = ?, updated_at = ?,
          message_count = message_count + 2,
          token_count = token_count + ?
      WHERE id = ?
    `).run(assistantNow, assistantNow, totalInputTokens + totalOutputTokens, conversationId);

    // Track usage
    db.prepare(`
      INSERT INTO usage_tracking (
        id, user_id, conversation_id, message_id, model,
        input_tokens, output_tokens, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      uuidv4(), 'default', conversationId, assistantMessageId, model,
      totalInputTokens, totalOutputTokens, assistantNow
    );

    // Send done event
    res.write(`data: ${JSON.stringify({
      type: 'done',
      id: assistantMessageId,
      model: finalMessage.model,
      stopReason: finalMessage.stop_reason,
      usage: {
        inputTokens: totalInputTokens,
        outputTokens: totalOutputTokens
      },
      thinkingTokens: fullThinkingContent.length > 0 ?
        Math.ceil(fullThinkingContent.length / 4) : 0
    })}\n\n`);

    res.end();

  } catch (error) {
    console.error('Claude API stream error:', error);
    res.write(`data: ${JSON.stringify({
      type: 'error',
      message: error.message
    })}\n\n`);
    res.end();
  }
});
```

### 10.2 Exemple Frontend Complet

```jsx
// src/App.jsx - Message Component with Thinking

function Message({ message, isStreaming }) {
  const [thinkingContent, setThinkingContent] = useState(message.thinking_content || '');
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const [isThinkingStreaming, setIsThinkingStreaming] = useState(false);

  return (
    <div className={`message ${message.role === 'assistant' ? 'assistant' : 'user'}`}>
      {/* Thinking Block (si présent) */}
      {thinkingContent && message.role === 'assistant' && (
        <div className="my-4 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950">
          {/* Header */}
          <button
            onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
          >
            <div className="flex items-center gap-2">
              {/* Brain Icon */}
              <svg
                className="w-5 h-5 text-blue-600 dark:text-blue-400"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/>
              </svg>
              <span className="font-medium text-blue-900 dark:text-blue-100">
                {isThinkingStreaming ? 'Claude is thinking...' : 'Claude\'s reasoning process'}
              </span>

              {/* Loading dots si streaming */}
              {isThinkingStreaming && (
                <div className="flex gap-1 ml-2">
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{animationDelay: '0ms'}}
                  />
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{animationDelay: '150ms'}}
                  />
                  <div
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{animationDelay: '300ms'}}
                  />
                </div>
              )}
            </div>

            {/* Chevron */}
            <svg
              className={`w-5 h-5 text-blue-600 dark:text-blue-400 transition-transform duration-200 ${
                isThinkingExpanded ? 'rotate-180' : ''
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {/* Thinking Content (collapsible) */}
          {isThinkingExpanded && (
            <div className="px-3 pb-3 border-t border-blue-200 dark:border-blue-800">
              <div className="pt-3 text-sm text-blue-800 dark:text-blue-200 whitespace-pre-wrap font-mono leading-relaxed">
                {thinkingContent || (
                  <div className="italic text-blue-600 dark:text-blue-400">
                    Thinking in progress...
                  </div>
                )}
              </div>

              {/* Stats footer */}
              <div className="mt-3 pt-2 border-t border-blue-200 dark:border-blue-800 flex items-center justify-between text-xs text-blue-600 dark:text-blue-400">
                <span>
                  ~{Math.ceil(thinkingContent.length / 4)} tokens
                </span>
                <span className="italic">
                  Summarized for display
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Message Content */}
      <div className="message-content prose dark:prose-invert max-w-none">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}

// Streaming handler avec thinking support
async function sendMessage(conversationId, content) {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let currentThinking = '';
  let currentContent = '';
  let isInThinkingBlock = false;
  let messageId = null;

  // Create temporary message
  const tempMessage = {
    id: 'temp-' + Date.now(),
    role: 'assistant',
    content: '',
    thinking_content: '',
    isStreaming: true
  };

  setMessages(prev => [...prev, tempMessage]);

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;

      try {
        const data = JSON.parse(line.slice(6));

        switch (data.type) {
          case 'thinking_start':
            isInThinkingBlock = true;
            setMessages(prev => prev.map(m =>
              m.id === tempMessage.id
                ? { ...m, isThinkingStreaming: true }
                : m
            ));
            break;

          case 'thinking':
            currentThinking += data.text;
            setMessages(prev => prev.map(m =>
              m.id === tempMessage.id
                ? { ...m, thinking_content: currentThinking }
                : m
            ));
            break;

          case 'thinking_stop':
            isInThinkingBlock = false;
            setMessages(prev => prev.map(m =>
              m.id === tempMessage.id
                ? { ...m, isThinkingStreaming: false }
                : m
            ));
            break;

          case 'content':
            currentContent += data.text;
            setMessages(prev => prev.map(m =>
              m.id === tempMessage.id
                ? { ...m, content: currentContent }
                : m
            ));
            break;

          case 'done':
            messageId = data.id;
            // Update with final message
            setMessages(prev => prev.map(m =>
              m.id === tempMessage.id
                ? {
                    id: messageId,
                    role: 'assistant',
                    content: currentContent,
                    thinking_content: currentThinking,
                    isStreaming: false,
                    isThinkingStreaming: false,
                    usage: data.usage
                  }
                : m
            ));
            break;

          case 'error':
            console.error('Streaming error:', data.message);
            setMessages(prev => prev.filter(m => m.id !== tempMessage.id));
            alert('Error: ' + data.message);
            break;
        }
      } catch (e) {
        console.error('Error parsing SSE data:', e);
      }
    }
  }
}
```

---

## 11. Testing Checklist

### 11.1 Tests Fonctionnels

- [ ] Thinking activé pour conversation → blocs thinking apparaissent
- [ ] Thinking désactivé → pas de blocs thinking
- [ ] Streaming thinking fonctionne en temps réel
- [ ] Toggle thinking dans settings fonctionne
- [ ] Budget slider fonctionne (1K-32K)
- [ ] Thinking blocks sont collapsibles
- [ ] Thinking blocks persistent après refresh
- [ ] Thinking + memory tools fonctionnent ensemble
- [ ] Multiple thinking blocks dans une réponse
- [ ] Redacted thinking est géré correctement

### 11.2 Tests Edge Cases

- [ ] Thinking timeout (>2 min) géré gracefully
- [ ] Erreurs réseau pendant thinking stream
- [ ] Thinking avec très grand budget (>32K)
- [ ] Thinking avec petit budget (1K)
- [ ] Conversation avec 100+ messages et thinking
- [ ] Regenerate avec thinking activé
- [ ] Edit message avec thinking
- [ ] Export conversation avec thinking

### 11.3 Tests Performance

- [ ] Temps de réponse thinking vs non-thinking
- [ ] Mémoire utilisée avec thinking streaming
- [ ] Database performance avec thinking storage
- [ ] UI responsive pendant thinking
- [ ] Multiple conversations avec thinking simultanées

---

## 12. Documentation Utilisateur

### Guide Rapide

**Qu'est-ce que Extended Thinking?**

Extended Thinking permet à Claude de "montrer son travail" en exposant son processus de raisonnement étape par étape avant de donner sa réponse finale. Particulièrement utile pour:
- Problèmes mathématiques complexes
- Analyse de code approfondie
- Raisonnement logique multi-étapes
- Planification de tâches complexes

**Comment l'activer?**

1. Ouvrir les paramètres de conversation (icône ⚙️)
2. Activer "Extended Thinking"
3. Ajuster le budget si nécessaire (10K par défaut)
4. Commencer à discuter

**Interpréter les blocs de thinking**

- 🧠 **Thinking blocks** (bleu): Processus de réflexion de Claude
- Cliquer pour expand/collapse
- Contenu est résumé mais bille au tarif complet
- Peut augmenter le temps de réponse de 2-5x

**Quand l'utiliser?**

✅ **OUI**: Calculs, code, analyse, logique complexe
❌ **NON**: Questions simples, chat rapide, créativité

---

## 13. Notes Importantes

### 13.1 Limitations

1. **Incompatibilités**:
   - ❌ Pas compatible avec `temperature` custom ou `top_k`
   - ❌ Pas de pre-fill responses avec thinking
   - ❌ Pas de forced tool use (`tool_choice: "any"`)
   - ✅ Compatible avec `top_p` (0.95-1)

2. **Context Window**:
   - Thinking blocks précédents retirés automatiquement
   - Token budget thinking compte vers `max_tokens`
   - Formule: `context = current_input + (thinking + encrypted + output)`

3. **Caching**:
   - Changer thinking parameters invalide message cache
   - System prompt reste en cache
   - Thinking blocks comptent comme input tokens en cache

### 13.2 Modèles Spécifiques

**Claude Opus 4.5** (unique):
- Préserve thinking blocks par défaut
- Meilleure optimization cache
- Économies de tokens sur multi-turn

**Claude 3.7** (déprécié):
- Retourne thinking COMPLET (non résumé)
- Tokens visibles = tokens facturés
- Migration vers Claude 4+ recommandée

---

## Annexes

### A. Structure de fichiers complète

```
generations/my_project/
├── server/
│   ├── routes/
│   │   ├── claude.js          # Modifié: thinking support
│   │   └── messages.js         # Modifié: thinking streaming
│   ├── db/
│   │   └── index.js            # Modifié: thinking columns migration
│   └── config/
│       └── thinkingDefaults.js # Nouveau: configuration thinking
├── src/
│   ├── components/
│   │   └── ThinkingBlock.jsx   # Nouveau: composant thinking
│   ├── App.jsx                 # Modifié: thinking UI integration
│   └── utils/
│       └── thinkingHelpers.js  # Nouveau: helpers thinking
└── prompts/
    └── extended_thinking_spec.md # Cette spec
```

### B. Variables d'environnement

Aucune nouvelle variable nécessaire. Extended Thinking fonctionne avec les credentials Anthropic existants.

### C. Compatibilité navigateurs

Extended Thinking utilise EventSource (SSE) qui est supporté par:
- ✅ Chrome/Edge 79+
- ✅ Firefox 65+
- ✅ Safari 13+
- ❌ IE11 (non supporté)

---

**Fin de la spécification Extended Thinking**

Version: 1.0
Date: 2025-12-18
Auteur: Claude Sonnet 4.5
