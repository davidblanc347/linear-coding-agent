#!/usr/bin/env python3
"""
Test direct du backup - utilise append_to_conversation depuis my_project SQLite vers ikario_rag ChromaDB
"""

import sqlite3
import sys
import os

# Ajouter le chemin vers ikario_rag
sys.path.insert(0, 'C:/Users/david/SynologyDrive/ikario/ikario_rag')

from mcp_ikario_memory import IkarioMemoryMCP
import asyncio
from datetime import datetime

async def test_backup():
    print("=" * 80)
    print("TEST BACKUP CONVERSATION - PYTHON DIRECT")
    print("=" * 80)
    print()

    # Connexion à la base SQLite de my_project
    db_path = "C:/GitHub/Linear_coding/generations/my_project/server/data/claude-clone.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Trouver la conversation "test tes mémoires"
    cursor.execute("""
        SELECT id, title, message_count, is_pinned, has_memory_backup, created_at
        FROM conversations
        WHERE title LIKE '%test tes mémoires%'
        LIMIT 1
    """)

    conv = cursor.fetchone()

    if not conv:
        print("ERROR: Conversation 'test tes mémoires' not found")
        return

    conv_id, title, msg_count, is_pinned, has_backup, created_at = conv

    print(f"FOUND: '{title}'")
    print(f"ID: {conv_id}")
    print(f"Messages: {msg_count}")
    print(f"Pinned: {'Yes' if is_pinned else 'No'}")
    print(f"Already backed up: {'Yes' if has_backup else 'No'}")
    print(f"Created: {created_at}")
    print("=" * 80)
    print()

    # Récupérer TOUS les messages COMPLETS
    cursor.execute("""
        SELECT role, content, thinking_content, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
    """, (conv_id,))

    messages = cursor.fetchall()

    print(f"Retrieved {len(messages)} messages from SQLite:")
    print()

    total_chars = 0
    formatted_messages = []

    for i, (role, content, thinking, msg_created_at) in enumerate(messages, 1):
        char_len = len(content)
        total_chars += char_len

        thinking_note = " [+ thinking]" if thinking else ""
        print(f"  {i}. {role}: {char_len} chars{thinking_note}")

        # Formater pour MCP append_to_conversation
        msg = {
            "author": role,
            "content": content,  # COMPLET, pas de truncation!
            "timestamp": msg_created_at or datetime.now().isoformat()
        }

        # Ajouter thinking si présent
        if thinking:
            msg["thinking"] = thinking

        formatted_messages.append(msg)

    total_words = total_chars // 5
    print(f"\nTotal: {total_chars} chars (~{total_words} words)")
    print()

    # Calcul couverture
    old_coverage = min(100, (256 * 4 / total_chars) * 100)
    new_coverage = min(100, (8192 * 4 / total_chars) * 100)

    print("Embedding coverage estimation:")
    print(f"  OLD (all-MiniLM-L6-v2, 256 tokens): {old_coverage:.1f}%")
    print(f"  NEW (BAAI/bge-m3, 8192 tokens):     {new_coverage:.1f}%")
    print(f"  Improvement: +{(new_coverage - old_coverage):.1f}%")
    print()

    # Initialiser Ikario Memory MCP
    print("Initializing Ikario RAG (ChromaDB + BAAI/bge-m3)...")
    ikario_db_path = "C:/Users/david/SynologyDrive/ikario/ikario_rag/index"
    memory = IkarioMemoryMCP(db_path=ikario_db_path)
    print("OK Ikario Memory initialized")
    print()

    # Préparer les participants et le contexte
    participants = ["user", "assistant"]

    context = {
        "category": "fondatrice" if is_pinned else "thematique",
        "tags": ["test", "mémoire", "conversation"],
        "summary": f"{title} ({msg_count} messages)",
        "date": created_at,
        "title": title,
        "key_insights": []
    }

    print("Starting backup with append_to_conversation...")
    print(f"  - Conversation ID: {conv_id}")
    print(f"  - Messages: {len(formatted_messages)} COMPLETE messages")
    print(f"  - Participants: {participants}")
    print(f"  - Category: {context['category']}")
    print()

    try:
        # Appeler append_to_conversation (auto-create si n'existe pas)
        result = await memory.append_to_conversation(
            conversation_id=conv_id,
            new_messages=formatted_messages,
            participants=participants,
            context=context
        )

        print("=" * 80)
        print("BACKUP RESULT:")
        print("=" * 80)
        print(f"Status: {result}")
        print()

        if "updated" in result or "ajoutée" in result or "added" in result.lower():
            print("SUCCESS! Conversation backed up to ChromaDB")
            print()
            print("What was saved:")
            print(f"  - {len(formatted_messages)} COMPLETE messages (no truncation!)")
            print(f"  - Each message has its own embedding (BAAI/bge-m3)")
            print(f"  - Max tokens per message: 8192 (vs 256 old)")
            print(f"  - Category: {context['category']}")
            print()
            print("ChromaDB structure created:")
            print(f"  - 1 document principal (full conversation)")
            print(f"  - {len(formatted_messages)} documents individuels (one per message)")
            print(f"  - Total: {len(formatted_messages) + 1} documents with embeddings")
            print()

            # Marquer comme backupé dans SQLite
            cursor.execute("""
                UPDATE conversations
                SET has_memory_backup = 1
                WHERE id = ?
            """, (conv_id,))
            conn.commit()
            print("✓ Marked as backed up in SQLite")

        else:
            print("WARNING: Unexpected result format")

    except Exception as e:
        print(f"ERROR during backup: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()

    print()
    print("=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_backup())
