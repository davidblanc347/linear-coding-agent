#!/usr/bin/env python3
"""
Memory Collections Schemas for Weaviate.

This module defines the schema for 3 Memory collections:
    - Thought: Individual thoughts/reflections
    - Conversation: Complete conversations
    - Message: Individual messages in conversations

All collections use manual vectorization (GPU embeddings).
"""

import weaviate
import weaviate.classes.config as wvc
from datetime import datetime
from typing import Optional


def create_thought_collection(client: weaviate.WeaviateClient) -> None:
    """
    Create Thought collection.

    Schema:
        - content: TEXT (vectorized) - The thought content
        - thought_type: TEXT - Type (reflexion, question, intuition, observation, etc.)
        - timestamp: DATE - When created
        - trigger: TEXT (optional) - What triggered the thought
        - emotional_state: TEXT (optional) - Emotional state
        - concepts: TEXT_ARRAY (vectorized) - Related concepts/tags
        - privacy_level: TEXT - private, shared, public
        - context: TEXT (optional) - Additional context
    """
    # Check if exists
    if "Thought" in client.collections.list_all():
        print("[WARN]  Thought collection already exists, skipping")
        return

    client.collections.create(
        name="Thought",

        # Manual vectorization (GPU) - single default vector
        vectorizer_config=wvc.Configure.Vectorizer.none(),

        properties=[
            # Vectorized fields
            wvc.Property(
                name="content",
                data_type=wvc.DataType.TEXT,
                description="The thought content",
            ),
            wvc.Property(
                name="concepts",
                data_type=wvc.DataType.TEXT_ARRAY,
                description="Related concepts/tags",
            ),

            # Metadata fields (not vectorized)
            wvc.Property(
                name="thought_type",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Type: reflexion, question, intuition, observation, etc.",
            ),
            wvc.Property(
                name="timestamp",
                data_type=wvc.DataType.DATE,
                description="When the thought was created",
            ),
            wvc.Property(
                name="trigger",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="What triggered the thought (optional)",
            ),
            wvc.Property(
                name="emotional_state",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Emotional state (optional)",
            ),
            wvc.Property(
                name="privacy_level",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Privacy level: private, shared, public",
            ),
            wvc.Property(
                name="context",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Additional context (optional)",
            ),
        ],
    )

    print("[OK] Thought collection created")


def create_conversation_collection(client: weaviate.WeaviateClient) -> None:
    """
    Create Conversation collection.

    Schema:
        - conversation_id: TEXT - Unique conversation ID
        - category: TEXT - philosophy, technical, personal, etc.
        - timestamp_start: DATE - Conversation start
        - timestamp_end: DATE (optional) - Conversation end
        - summary: TEXT (vectorized) - Conversation summary
        - participants: TEXT_ARRAY - List of participants
        - tags: TEXT_ARRAY - Semantic tags
        - message_count: INT - Number of messages
        - context: TEXT (optional) - Global context
    """
    # Check if exists
    if "Conversation" in client.collections.list_all():
        print("[WARN]  Conversation collection already exists, skipping")
        return

    client.collections.create(
        name="Conversation",

        # Manual vectorization (GPU)
        vectorizer_config=wvc.Configure.Vectorizer.none(),

        properties=[
            # Vectorized field
            wvc.Property(
                name="summary",
                data_type=wvc.DataType.TEXT,
                description="Conversation summary",
            ),

            # Metadata fields (not vectorized)
            wvc.Property(
                name="conversation_id",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Unique conversation identifier",
            ),
            wvc.Property(
                name="category",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Category: philosophy, technical, personal, etc.",
            ),
            wvc.Property(
                name="timestamp_start",
                data_type=wvc.DataType.DATE,
                description="Conversation start time",
            ),
            wvc.Property(
                name="timestamp_end",
                data_type=wvc.DataType.DATE,
                description="Conversation end time (optional)",
            ),
            wvc.Property(
                name="participants",
                data_type=wvc.DataType.TEXT_ARRAY,
                skip_vectorization=True,
                description="List of participants",
            ),
            wvc.Property(
                name="tags",
                data_type=wvc.DataType.TEXT_ARRAY,
                skip_vectorization=True,
                description="Semantic tags",
            ),
            wvc.Property(
                name="message_count",
                data_type=wvc.DataType.INT,
                description="Number of messages in conversation",
            ),
            wvc.Property(
                name="context",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Global context (optional)",
            ),
        ],
    )

    print("[OK] Conversation collection created")


def create_message_collection(client: weaviate.WeaviateClient) -> None:
    """
    Create Message collection.

    Schema:
        - content: TEXT (vectorized) - Message content
        - role: TEXT - user, assistant, system
        - timestamp: DATE - When sent
        - conversation_id: TEXT - Link to parent Conversation
        - order_index: INT - Position in conversation
        - conversation: OBJECT (nested) - Denormalized conversation data
            - conversation_id: TEXT
            - category: TEXT
    """
    # Check if exists
    if "Message" in client.collections.list_all():
        print("[WARN]  Message collection already exists, skipping")
        return

    client.collections.create(
        name="Message",

        # Manual vectorization (GPU)
        vectorizer_config=wvc.Configure.Vectorizer.none(),

        properties=[
            # Vectorized field
            wvc.Property(
                name="content",
                data_type=wvc.DataType.TEXT,
                description="Message content",
            ),

            # Metadata fields (not vectorized)
            wvc.Property(
                name="role",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Role: user, assistant, system",
            ),
            wvc.Property(
                name="timestamp",
                data_type=wvc.DataType.DATE,
                description="When the message was sent",
            ),
            wvc.Property(
                name="conversation_id",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Link to parent Conversation",
            ),
            wvc.Property(
                name="order_index",
                data_type=wvc.DataType.INT,
                description="Position in conversation",
            ),

            # Nested object (denormalized for performance)
            wvc.Property(
                name="conversation",
                data_type=wvc.DataType.OBJECT,
                skip_vectorization=True,
                description="Denormalized conversation data",
                nested_properties=[
                    wvc.Property(
                        name="conversation_id",
                        data_type=wvc.DataType.TEXT,
                    ),
                    wvc.Property(
                        name="category",
                        data_type=wvc.DataType.TEXT,
                    ),
                ],
            ),
        ],
    )

    print("[OK] Message collection created")


def create_all_memory_schemas(client: weaviate.WeaviateClient) -> None:
    """
    Create all 3 Memory collections.

    Args:
        client: Connected Weaviate client.
    """
    print("="*60)
    print("Creating Memory Schemas")
    print("="*60)

    create_thought_collection(client)
    create_conversation_collection(client)
    create_message_collection(client)

    print("\n" + "="*60)
    print("Memory Schemas Created Successfully")
    print("="*60)

    # List all collections
    all_collections = client.collections.list_all()
    print(f"\nTotal collections: {len(all_collections)}")

    memory_cols = [c for c in all_collections.keys() if c in ["Thought", "Conversation", "Message"]]
    library_cols = [c for c in all_collections.keys() if c in ["Work", "Document", "Chunk", "Summary"]]

    print(f"\nMemory collections ({len(memory_cols)}): {', '.join(sorted(memory_cols))}")
    print(f"Library collections ({len(library_cols)}): {', '.join(sorted(library_cols))}")


def delete_memory_schemas(client: weaviate.WeaviateClient) -> None:
    """
    Delete all Memory collections (for testing/cleanup).

    WARNING: This deletes all data in Memory collections!
    """
    print("[WARN]  WARNING: Deleting all Memory collections...")

    for collection_name in ["Thought", "Conversation", "Message"]:
        try:
            client.collections.delete(collection_name)
            print(f"Deleted {collection_name}")
        except Exception as e:
            print(f"Could not delete {collection_name}: {e}")
