#!/usr/bin/env python3
"""
MCP Client de référence pour Library RAG.

Implémentation complète d'un client MCP qui permet à un LLM
d'utiliser les outils de Library RAG.

Usage:
    python mcp_client_reference.py

Requirements:
    pip install mistralai anyio
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ToolDefinition:
    """Définition d'un outil MCP."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    """Client pour communiquer avec le MCP server de Library RAG."""

    def __init__(self, server_path: str, env: dict[str, str] | None = None):
        """
        Args:
            server_path: Chemin vers mcp_server.py
            env: Variables d'environnement additionnelles
        """
        self.server_path = server_path
        self.env = env or {}
        self.process = None
        self.request_id = 0

    async def start(self) -> None:
        """Démarrer le MCP server subprocess."""
        print(f"[MCP] Starting server: {self.server_path}")

        # Préparer l'environnement
        full_env = {**os.environ, **self.env}

        # Démarrer le subprocess
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,  # Python executable
            self.server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )

        # Phase 1: Initialize
        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "library-rag-client", "version": "1.0.0"},
            },
        )

        print(f"[MCP] Server initialized: {init_result.get('serverInfo', {}).get('name')}")

        # Phase 2: Initialized notification
        await self._send_notification("notifications/initialized", {})

        print("[MCP] Client ready")

    async def _send_request(self, method: str, params: dict) -> dict:
        """Envoyer une requête JSON-RPC et attendre la réponse."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        # Envoyer
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()

        # Recevoir
        response_line = await self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("MCP server closed connection")

        response = json.loads(response_line.decode())

        # Vérifier erreurs
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})

    async def _send_notification(self, method: str, params: dict) -> None:
        """Envoyer une notification (pas de réponse)."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}

        notification_json = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_json.encode())
        await self.process.stdin.drain()

    async def list_tools(self) -> list[ToolDefinition]:
        """Obtenir la liste des outils disponibles."""
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])

        tool_defs = [
            ToolDefinition(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["inputSchema"],
            )
            for tool in tools
        ]

        print(f"[MCP] Found {len(tool_defs)} tools")
        return tool_defs

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Appeler un outil MCP."""
        print(f"[MCP] Calling tool: {tool_name}")
        print(f"      Arguments: {json.dumps(arguments, indent=2)}")

        result = await self._send_request(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )

        # Extraire le contenu
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            text_content = content[0]["text"]
            try:
                return json.loads(text_content)
            except json.JSONDecodeError:
                return text_content

        return result

    async def stop(self) -> None:
        """Arrêter le MCP server."""
        if self.process:
            print("[MCP] Stopping server...")
            self.process.terminate()
            await self.process.wait()
            print("[MCP] Server stopped")


class LLMWithMCP:
    """LLM avec capacité d'utiliser les outils MCP."""

    def __init__(self, mcp_client: MCPClient, mistral_api_key: str):
        """
        Args:
            mcp_client: Client MCP initialisé
            mistral_api_key: Clé API Mistral
        """
        self.mcp_client = mcp_client
        self.mistral_api_key = mistral_api_key
        self.tools = None
        self.messages = []

        # Import Mistral
        try:
            from mistralai import Mistral

            self.mistral = Mistral(api_key=mistral_api_key)
        except ImportError:
            raise ImportError("Install mistralai: pip install mistralai")

    async def initialize(self) -> None:
        """Charger les outils MCP et les convertir pour Mistral."""
        mcp_tools = await self.mcp_client.list_tools()

        # Convertir au format Mistral
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in mcp_tools
        ]

        print(f"[LLM] Loaded {len(self.tools)} tools for Mistral")

    async def chat(self, user_message: str, max_iterations: int = 10) -> str:
        """
        Converser avec le LLM qui peut utiliser les outils MCP.

        Args:
            user_message: Message de l'utilisateur
            max_iterations: Limite de tool calls

        Returns:
            Réponse finale du LLM
        """
        print(f"\n[USER] {user_message}\n")

        self.messages.append({"role": "user", "content": user_message})

        for iteration in range(max_iterations):
            print(f"[LLM] Iteration {iteration + 1}/{max_iterations}")

            # Appel LLM avec tools
            response = self.mistral.chat.complete(
                model="mistral-large-latest",
                messages=self.messages,
                tools=self.tools,
                tool_choice="auto",
            )

            assistant_message = response.choices[0].message

            # Ajouter le message assistant
            self.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": (
                        [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in assistant_message.tool_calls
                        ]
                        if assistant_message.tool_calls
                        else None
                    ),
                }
            )

            # Si pas de tool calls → réponse finale
            if not assistant_message.tool_calls:
                print(f"[LLM] Final response")
                return assistant_message.content

            # Exécuter les tool calls
            print(f"[LLM] Tool calls: {len(assistant_message.tool_calls)}")

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                # Appeler via MCP
                try:
                    result = await self.mcp_client.call_tool(tool_name, arguments)
                    result_str = json.dumps(result)
                    print(f"[MCP] Result: {result_str[:200]}...")

                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    print(f"[MCP] Error: {e}")

                # Ajouter le résultat
                self.messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": result_str,
                        "tool_call_id": tool_call.id,
                    }
                )

        return "Max iterations atteintes"


async def main():
    """Exemple d'utilisation du client MCP."""

    # Configuration
    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if not mistral_api_key:
        print("ERROR: MISTRAL_API_KEY not set")
        return

    # 1. Créer et démarrer le client MCP
    mcp_client = MCPClient(
        server_path=str(server_path),
        env={
            "MISTRAL_API_KEY": mistral_api_key,
            # Ajouter autres variables si nécessaire
        },
    )

    try:
        await mcp_client.start()

        # 2. Créer l'agent LLM
        agent = LLMWithMCP(mcp_client, mistral_api_key)
        await agent.initialize()

        # 3. Exemples de conversations
        print("\n" + "=" * 80)
        print("EXAMPLE 1: Search")
        print("=" * 80)

        response = await agent.chat(
            "What did Charles Sanders Peirce say about the debate between "
            "nominalism and realism? Search the database and give me a summary "
            "with specific quotes."
        )

        print(f"\n[ASSISTANT]\n{response}\n")

        print("\n" + "=" * 80)
        print("EXAMPLE 2: List documents")
        print("=" * 80)

        response = await agent.chat(
            "List all the documents in the database. "
            "How many are there and who are the authors?"
        )

        print(f"\n[ASSISTANT]\n{response}\n")

    finally:
        await mcp_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
