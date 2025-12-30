# Spécifications MCP Client pour Application Python

## Vue d'ensemble

Ce document spécifie comment implémenter un client MCP dans votre application Python pour permettre à votre LLM d'utiliser les outils de Library RAG via le MCP server.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOTRE APPLICATION PYTHON                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────┐        ┌──────────────┐      ┌──────────────┐  │
│  │    LLM     │───────▶│  MCP Client  │─────▶│ Tool Executor│  │
│  │ (Mistral,  │◀───────│  (votre code)│◀─────│              │  │
│  │  Claude,   │        └──────────────┘      └──────────────┘  │
│  │  etc.)     │              │ ▲                                │
│  └────────────┘              │ │                                │
│                               │ │ stdio (JSON-RPC)              │
└───────────────────────────────┼─┼────────────────────────────────┘
                                │ │
                         ┌──────┴─┴──────┐
                         │ MCP Server     │
                         │ (subprocess)   │
                         │                │
                         │ library_rag/   │
                         │ mcp_server.py  │
                         └────────────────┘
                                │
                         ┌──────┴──────┐
                         │  Weaviate   │
                         │  Database   │
                         └─────────────┘
```

## Composants à implémenter

### 1. MCP Client Manager

**Fichier:** `mcp_client.py`

**Responsabilités:**
- Démarrer le MCP server comme subprocess
- Communiquer via stdin/stdout (JSON-RPC 2.0)
- Gérer le cycle de vie du server
- Exposer les outils disponibles au LLM

**Interface:**

```python
class MCPClient:
    """Client pour communiquer avec le MCP server de Library RAG."""

    def __init__(self, server_script_path: str, env: dict[str, str] | None = None):
        """
        Args:
            server_script_path: Chemin vers mcp_server.py
            env: Variables d'environnement (MISTRAL_API_KEY, etc.)
        """
        pass

    async def start(self) -> None:
        """Démarrer le MCP server subprocess."""
        pass

    async def stop(self) -> None:
        """Arrêter le MCP server subprocess."""
        pass

    async def list_tools(self) -> list[ToolDefinition]:
        """Obtenir la liste des outils disponibles."""
        pass

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> ToolResult:
        """Appeler un outil MCP.

        Args:
            tool_name: Nom de l'outil (ex: "search_chunks")
            arguments: Arguments JSON

        Returns:
            Résultat de l'outil
        """
        pass
```

### 2. JSON-RPC Communication

**Format des messages:**

**Client → Server (appel d'outil):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_chunks",
    "arguments": {
      "query": "nominalism and realism",
      "limit": 10
    }
  }
}
```

**Server → Client (résultat):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\": [...], \"total_count\": 10}"
      }
    ]
  }
}
```

### 3. LLM Integration

**Fichier:** `llm_with_tools.py`

**Responsabilités:**
- Convertir les outils MCP en format utilisable par le LLM
- Gérer le cycle de reasoning + tool calling
- Parser les réponses du LLM pour extraire les appels d'outils

**Interface:**

```python
class LLMWithMCPTools:
    """LLM avec capacité d'utiliser les outils MCP."""

    def __init__(
        self,
        llm_client,  # Mistral, Anthropic, OpenAI client
        mcp_client: MCPClient
    ):
        """
        Args:
            llm_client: Client LLM (Mistral, Claude, GPT)
            mcp_client: Client MCP initialisé
        """
        pass

    async def chat(
        self,
        user_message: str,
        max_iterations: int = 5
    ) -> str:
        """
        Converser avec le LLM qui peut utiliser les outils MCP.

        Flow:
        1. Envoyer message au LLM avec liste des outils
        2. Si LLM demande un outil → l'exécuter via MCP
        3. Renvoyer le résultat au LLM
        4. Répéter jusqu'à réponse finale

        Args:
            user_message: Question de l'utilisateur
            max_iterations: Limite de tool calls

        Returns:
            Réponse finale du LLM
        """
        pass

    async def _convert_mcp_tools_to_llm_format(
        self,
        mcp_tools: list[ToolDefinition]
    ) -> list[dict]:
        """Convertir les outils MCP au format du LLM."""
        pass
```

## Protocole de communication détaillé

### Phase 1: Initialisation

```python
# 1. Démarrer le subprocess
process = await asyncio.create_subprocess_exec(
    "python", "mcp_server.py",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=environment_variables
)

# 2. Envoyer initialize request
initialize_request = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {}
        },
        "clientInfo": {
            "name": "my-python-app",
            "version": "1.0.0"
        }
    }
}

# 3. Recevoir initialize response
# Server retourne ses capabilities et la liste des outils

# 4. Envoyer initialized notification
initialized_notification = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
}
```

### Phase 2: Découverte des outils

```python
# Liste des outils disponibles
tools_request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
}

# Réponse attendue:
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "tools": [
            {
                "name": "search_chunks",
                "description": "Search for text chunks using semantic similarity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                        "author_filter": {"type": "string"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "parse_pdf",
                "description": "Process a PDF with OCR and ingest to Weaviate",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pdf_path": {"type": "string"}
                    },
                    "required": ["pdf_path"]
                }
            }
            // ... autres outils
        ]
    }
}
```

### Phase 3: Appel d'outil

```python
# Appel d'outil
tool_call_request = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "search_chunks",
        "arguments": {
            "query": "What is nominalism?",
            "limit": 5,
            "author_filter": "Charles Sanders Peirce"
        }
    }
}

# Réponse
{
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "{\"results\": [{\"text\": \"...\", \"similarity\": 0.89}], \"total_count\": 5}"
            }
        ]
    }
}
```

## Dépendances Python

```toml
# pyproject.toml
[project]
dependencies = [
    "anyio>=4.0.0",           # Async I/O
    "pydantic>=2.0.0",        # Validation
    "httpx>=0.27.0",          # HTTP client (si download PDF)

    # LLM client (choisir un):
    "anthropic>=0.39.0",      # Pour Claude
    "mistralai>=1.2.0",       # Pour Mistral
    "openai>=1.54.0",         # Pour GPT
]
```

## Exemple d'implémentation minimale

### mcp_client.py (squelette)

```python
import asyncio
import json
from typing import Any
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    def __init__(self, server_path: str, env: dict[str, str] | None = None):
        self.server_path = server_path
        self.env = env or {}
        self.process = None
        self.request_id = 0

    async def start(self):
        """Démarrer le MCP server."""
        self.process = await asyncio.create_subprocess_exec(
            "python", self.server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env}
        )

        # Initialize
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "my-app", "version": "1.0"}
        })

        # Notification initialized
        await self._send_notification("notifications/initialized", {})

    async def _send_request(self, method: str, params: dict) -> dict:
        """Envoyer une requête JSON-RPC et attendre la réponse."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }

        # Écrire dans stdin
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()

        # Lire depuis stdout
        response_line = await self.process.stdout.readline()
        response = json.loads(response_line.decode())

        return response.get("result")

    async def _send_notification(self, method: str, params: dict):
        """Envoyer une notification (pas de réponse attendue)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        notification_json = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_json.encode())
        await self.process.stdin.drain()

    async def list_tools(self) -> list[ToolDefinition]:
        """Obtenir la liste des outils."""
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])

        return [
            ToolDefinition(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["inputSchema"]
            )
            for tool in tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Appeler un outil."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        # Extraire le contenu texte
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])

        return result

    async def stop(self):
        """Arrêter le server."""
        if self.process:
            self.process.terminate()
            await self.process.wait()
```

### llm_agent.py (exemple avec Mistral)

```python
from mistralai import Mistral


class LLMAgent:
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        self.mistral = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
        self.tools = None
        self.messages = []

    async def initialize(self):
        """Charger les outils MCP."""
        mcp_tools = await self.mcp_client.list_tools()

        # Convertir au format Mistral
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in mcp_tools
        ]

    async def chat(self, user_message: str) -> str:
        """Converser avec tool calling."""
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        max_iterations = 10

        for _ in range(max_iterations):
            # Appel LLM
            response = self.mistral.chat.complete(
                model="mistral-large-latest",
                messages=self.messages,
                tools=self.tools,
                tool_choice="auto"
            )

            assistant_message = response.choices[0].message
            self.messages.append(assistant_message)

            # Si pas de tool calls → réponse finale
            if not assistant_message.tool_calls:
                return assistant_message.content

            # Exécuter les tool calls
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                # Appeler via MCP
                result = await self.mcp_client.call_tool(tool_name, arguments)

                # Ajouter le résultat
                self.messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(result),
                    "tool_call_id": tool_call.id
                })

        return "Max iterations atteintes"
```

### main.py (exemple d'utilisation)

```python
import asyncio
import os


async def main():
    # 1. Créer le client MCP
    mcp_client = MCPClient(
        server_path="path/to/library_rag/mcp_server.py",
        env={
            "MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY"),
            "LINEAR_API_KEY": os.getenv("LINEAR_API_KEY")  # Si besoin
        }
    )

    # 2. Démarrer le server
    await mcp_client.start()

    try:
        # 3. Créer l'agent LLM
        agent = LLMAgent(mcp_client)
        await agent.initialize()

        # 4. Converser
        response = await agent.chat(
            "What did Peirce say about nominalism versus realism? "
            "Search the database and summarize the key points."
        )

        print(response)

    finally:
        # 5. Arrêter le server
        await mcp_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

## Flow complet

```
User: "What did Peirce say about nominalism?"
  │
  ▼
LLM Agent
  │
  ├─ Appel Mistral avec tools disponibles
  │
  ▼
Mistral décide: "Je dois utiliser search_chunks"
  │
  ▼
LLM Agent → MCP Client
  │
  ├─ call_tool("search_chunks", {
  │     "query": "Peirce nominalism realism",
  │     "limit": 10
  │   })
  │
  ▼
MCP Server (subprocess)
  │
  ├─ Exécute search_chunks_handler
  │
  ├─ Query Weaviate
  │
  ├─ Retourne résultats JSON
  │
  ▼
MCP Client reçoit résultat
  │
  ▼
LLM Agent renvoie résultat à Mistral
  │
  ▼
Mistral synthétise la réponse finale
  │
  ▼
User reçoit: "Peirce was a realist who believed that universals..."
```

## Variables d'environnement requises

```bash
# .env
MISTRAL_API_KEY=your_mistral_key       # Pour le LLM ET pour l'OCR
WEAVIATE_URL=http://localhost:8080     # Optionnel (défaut: localhost)
PYTHONPATH=/path/to/library_rag        # Pour les imports
```

## Références

- **MCP Protocol**: https://spec.modelcontextprotocol.io/
- **JSON-RPC 2.0**: https://www.jsonrpc.org/specification
- **Mistral Tool Use**: https://docs.mistral.ai/capabilities/function_calling/
- **Anthropic Tool Use**: https://docs.anthropic.com/en/docs/tool-use

## Next Steps

1. Implémenter `MCPClient` avec gestion complète du protocole
2. Implémenter `LLMAgent` avec votre LLM de choix
3. Tester avec un outil simple (`search_chunks`)
4. Ajouter error handling et retry logic
5. Implémenter logging pour debug
6. Ajouter tests unitaires

## Notes importantes

- Le MCP server utilise **stdio** (stdin/stdout) pour la communication
- Chaque message JSON-RPC doit être sur **une seule ligne** terminée par `\n`
- Le server peut envoyer des logs sur **stderr** (à ne pas confondre avec stdout)
- Les tool calls peuvent être **longs** (parse_pdf prend plusieurs minutes)
- Implémenter des **timeouts** appropriés
