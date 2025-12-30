#!/usr/bin/env python3
"""
MCP Client pour Library RAG avec Claude (Anthropic).

Implémentation d'un client MCP qui permet à Claude d'utiliser
les outils de Library RAG via tool calling.

Usage:
    python mcp_client_claude.py

Requirements:
    pip install anthropic python-dotenv
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Charger les variables d'environnement depuis .env
try:
    from dotenv import load_dotenv
    # Charger depuis le .env du projet parent
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    print(f"[ENV] Loaded environment from {env_path}")
except ImportError:
    print("[ENV] python-dotenv not installed, using system environment variables")
    print("      Install with: pip install python-dotenv")


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
            sys.executable,
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
                "clientInfo": {"name": "library-rag-client-claude", "version": "1.0.0"},
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
        print(f"      Arguments: {json.dumps(arguments, indent=2)[:200]}...")

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


class ClaudeWithMCP:
    """Claude avec capacité d'utiliser les outils MCP."""

    def __init__(self, mcp_client: MCPClient, anthropic_api_key: str):
        """
        Args:
            mcp_client: Client MCP initialisé
            anthropic_api_key: Clé API Anthropic
        """
        self.mcp_client = mcp_client
        self.anthropic_api_key = anthropic_api_key
        self.tools = None
        self.messages = []

        # Import Claude
        try:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=anthropic_api_key)
        except ImportError:
            raise ImportError("Install anthropic: pip install anthropic")

    async def initialize(self) -> None:
        """Charger les outils MCP et les convertir pour Claude."""
        mcp_tools = await self.mcp_client.list_tools()

        # Convertir au format Claude (identique au format MCP)
        self.tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in mcp_tools
        ]

        print(f"[Claude] Loaded {len(self.tools)} tools")

    async def chat(self, user_message: str, max_iterations: int = 10) -> str:
        """
        Converser avec Claude qui peut utiliser les outils MCP.

        Args:
            user_message: Message de l'utilisateur
            max_iterations: Limite de tool calls

        Returns:
            Réponse finale de Claude
        """
        print(f"\n[USER] {user_message}\n")

        self.messages.append({"role": "user", "content": user_message})

        for iteration in range(max_iterations):
            print(f"[Claude] Iteration {iteration + 1}/{max_iterations}")

            # Appel Claude avec tools
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5
                max_tokens=4096,
                messages=self.messages,
                tools=self.tools,
            )

            # Ajouter la réponse de Claude
            assistant_message = {
                "role": "assistant",
                "content": response.content,
            }
            self.messages.append(assistant_message)

            # Vérifier si Claude veut utiliser des outils
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            # Si pas de tool use → réponse finale
            if not tool_uses:
                # Extraire le texte de la réponse
                text_blocks = [block for block in response.content if block.type == "text"]
                if text_blocks:
                    print(f"[Claude] Final response")
                    return text_blocks[0].text
                return ""

            # Exécuter les tool uses
            print(f"[Claude] Tool uses: {len(tool_uses)}")

            tool_results = []

            for tool_use in tool_uses:
                tool_name = tool_use.name
                arguments = tool_use.input

                # Appeler via MCP
                try:
                    result = await self.mcp_client.call_tool(tool_name, arguments)
                    result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                    print(f"[MCP] Result: {result_str[:200]}...")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_str,
                    })

                except Exception as e:
                    print(f"[MCP] Error: {e}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })

            # Ajouter les résultats des outils
            self.messages.append({
                "role": "user",
                "content": tool_results,
            })

        return "Max iterations atteintes"


async def main():
    """Exemple d'utilisation du client MCP avec Claude."""

    # Configuration
    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env file")
        print("Please add to .env: ANTHROPIC_API_KEY=your_key")
        return

    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if not mistral_api_key:
        print("ERROR: MISTRAL_API_KEY not found in .env file")
        print("The MCP server needs Mistral API for OCR functionality")
        return

    # 1. Créer et démarrer le client MCP
    mcp_client = MCPClient(
        server_path=str(server_path),
        env={
            "MISTRAL_API_KEY": mistral_api_key or "",
        },
    )

    try:
        await mcp_client.start()

        # 2. Créer l'agent Claude
        agent = ClaudeWithMCP(mcp_client, anthropic_api_key)
        await agent.initialize()

        # 3. Exemples de conversations
        print("\n" + "=" * 80)
        print("EXAMPLE 1: Search in Peirce")
        print("=" * 80)

        response = await agent.chat(
            "What did Charles Sanders Peirce say about the philosophical debate "
            "between nominalism and realism? Search the database and provide "
            "a detailed summary with specific quotes."
        )

        print(f"\n[CLAUDE]\n{response}\n")

        print("\n" + "=" * 80)
        print("EXAMPLE 2: Explore database")
        print("=" * 80)

        response = await agent.chat(
            "What documents are available in the database? "
            "Give me an overview of the authors and topics covered."
        )

        print(f"\n[CLAUDE]\n{response}\n")

    finally:
        await mcp_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
