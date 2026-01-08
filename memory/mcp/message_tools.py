"""
Message MCP Tools - Handlers for message-related operations.

Provides tools for adding, searching, and retrieving conversation messages.
"""

import weaviate
from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field
from memory.core import get_embedder


class AddMessageInput(BaseModel):
    """Input for add_message tool."""
    content: str = Field(..., description="Message content")
    role: str = Field(..., description="Role: user, assistant, system")
    conversation_id: str = Field(..., description="Conversation identifier")
    order_index: int = Field(default=0, description="Position in conversation")


class GetMessagesInput(BaseModel):
    """Input for get_messages tool."""
    conversation_id: str = Field(..., description="Conversation identifier")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum messages")


class SearchMessagesInput(BaseModel):
    """Input for search_messages tool."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    conversation_id_filter: str | None = Field(default=None, description="Filter by conversation")


async def add_message_handler(input_data: AddMessageInput) -> Dict[str, Any]:
    """
    Add a new message to Weaviate.

    Args:
        input_data: Message data to add.

    Returns:
        Dictionary with success status and message UUID.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get embedder
            embedder = get_embedder()

            # Generate vector for message content
            vector = embedder.embed_batch([input_data.content])[0]

            # Get collection
            collection = client.collections.get("Message")

            # Insert message
            uuid = collection.data.insert(
                properties={
                    "content": input_data.content,
                    "role": input_data.role,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "conversation_id": input_data.conversation_id,
                    "order_index": input_data.order_index,
                    "conversation": {
                        "conversation_id": input_data.conversation_id,
                        "category": "general",  # Default
                    },
                },
                vector=vector.tolist()
            )

            return {
                "success": True,
                "uuid": str(uuid),
                "content": input_data.content[:100] + "..." if len(input_data.content) > 100 else input_data.content,
                "role": input_data.role,
                "conversation_id": input_data.conversation_id,
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def get_messages_handler(input_data: GetMessagesInput) -> Dict[str, Any]:
    """
    Get all messages from a conversation.

    Args:
        input_data: Query parameters.

    Returns:
        Dictionary with messages in order.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get collection
            collection = client.collections.get("Message")

            # Fetch messages for conversation
            results = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("conversation_id").equal(input_data.conversation_id),
                limit=input_data.limit,
            )

            # Sort by order_index
            messages = []
            for obj in results.objects:
                messages.append({
                    "uuid": str(obj.uuid),
                    "content": obj.properties['content'],
                    "role": obj.properties['role'],
                    "timestamp": obj.properties['timestamp'],
                    "order_index": obj.properties['order_index'],
                })

            # Sort by order_index
            messages.sort(key=lambda m: m['order_index'])

            return {
                "success": True,
                "conversation_id": input_data.conversation_id,
                "messages": messages,
                "count": len(messages),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def search_messages_handler(input_data: SearchMessagesInput) -> Dict[str, Any]:
    """
    Search messages using semantic similarity.

    Args:
        input_data: Search parameters.

    Returns:
        Dictionary with search results.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get embedder
            embedder = get_embedder()

            # Generate query vector
            query_vector = embedder.embed_batch([input_data.query])[0]

            # Get collection
            collection = client.collections.get("Message")

            # Build query
            query_builder = collection.query.near_vector(
                near_vector=query_vector.tolist(),
                limit=input_data.limit,
            )

            # Apply conversation filter if provided
            if input_data.conversation_id_filter:
                query_builder = query_builder.where(
                    weaviate.classes.query.Filter.by_property("conversation_id").equal(input_data.conversation_id_filter)
                )

            # Execute search
            results = query_builder.objects

            # Format results
            messages = []
            for obj in results:
                messages.append({
                    "uuid": str(obj.uuid),
                    "content": obj.properties['content'],
                    "role": obj.properties['role'],
                    "timestamp": obj.properties['timestamp'],
                    "conversation_id": obj.properties['conversation_id'],
                    "order_index": obj.properties['order_index'],
                })

            return {
                "success": True,
                "query": input_data.query,
                "results": messages,
                "count": len(messages),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
