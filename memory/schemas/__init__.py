"""
Memory Schemas Package.

Defines Weaviate schemas for Memory collections:
    - Thought
    - Conversation
    - Message
"""

from memory.schemas.memory_schemas import (
    create_thought_collection,
    create_conversation_collection,
    create_message_collection,
    create_all_memory_schemas,
    delete_memory_schemas,
)

__all__ = [
    "create_thought_collection",
    "create_conversation_collection",
    "create_message_collection",
    "create_all_memory_schemas",
    "delete_memory_schemas",
]
