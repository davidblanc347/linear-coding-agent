"""
Conversation MCP Tools - Handlers for conversation-related operations.

Provides tools for searching and retrieving conversations.
"""

import weaviate
from typing import Any, Dict
from pydantic import BaseModel, Field
from memory.core import get_embedder


class GetConversationInput(BaseModel):
    """Input for get_conversation tool."""
    conversation_id: str = Field(..., description="Conversation identifier")


class SearchConversationsInput(BaseModel):
    """Input for search_conversations tool."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results")
    category_filter: str | None = Field(default=None, description="Filter by category")


class ListConversationsInput(BaseModel):
    """Input for list_conversations tool."""
    limit: int = Field(default=20, ge=1, le=100, description="Maximum conversations")
    category_filter: str | None = Field(default=None, description="Filter by category")


async def get_conversation_handler(input_data: GetConversationInput) -> Dict[str, Any]:
    """
    Get a specific conversation by ID.

    Args:
        input_data: Query parameters.

    Returns:
        Dictionary with conversation data.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get collection
            collection = client.collections.get("Conversation")

            # Fetch by conversation_id
            results = collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("conversation_id").equal(input_data.conversation_id),
                limit=1,
            )

            if not results.objects:
                return {
                    "success": False,
                    "error": f"Conversation {input_data.conversation_id} not found",
                }

            obj = results.objects[0]

            return {
                "success": True,
                "conversation_id": obj.properties['conversation_id'],
                "category": obj.properties['category'],
                "summary": obj.properties['summary'],
                "timestamp_start": obj.properties['timestamp_start'],
                "timestamp_end": obj.properties['timestamp_end'],
                "participants": obj.properties['participants'],
                "tags": obj.properties.get('tags', []),
                "message_count": obj.properties['message_count'],
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def search_conversations_handler(input_data: SearchConversationsInput) -> Dict[str, Any]:
    """
    Search conversations using semantic similarity.

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
            collection = client.collections.get("Conversation")

            # Build query
            query_builder = collection.query.near_vector(
                near_vector=query_vector.tolist(),
                limit=input_data.limit,
            )

            # Apply category filter if provided
            if input_data.category_filter:
                query_builder = query_builder.where(
                    weaviate.classes.query.Filter.by_property("category").equal(input_data.category_filter)
                )

            # Execute search
            results = query_builder.objects

            # Format results
            conversations = []
            for obj in results:
                conversations.append({
                    "conversation_id": obj.properties['conversation_id'],
                    "category": obj.properties['category'],
                    "summary": obj.properties['summary'],
                    "timestamp_start": obj.properties['timestamp_start'],
                    "timestamp_end": obj.properties['timestamp_end'],
                    "participants": obj.properties['participants'],
                    "message_count": obj.properties['message_count'],
                })

            return {
                "success": True,
                "query": input_data.query,
                "results": conversations,
                "count": len(conversations),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def list_conversations_handler(input_data: ListConversationsInput) -> Dict[str, Any]:
    """
    List all conversations with filtering.

    Args:
        input_data: Query parameters.

    Returns:
        Dictionary with conversation list.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get collection
            collection = client.collections.get("Conversation")

            # Build query
            if input_data.category_filter:
                results = collection.query.fetch_objects(
                    filters=weaviate.classes.query.Filter.by_property("category").equal(input_data.category_filter),
                    limit=input_data.limit,
                )
            else:
                results = collection.query.fetch_objects(
                    limit=input_data.limit,
                )

            # Format results
            conversations = []
            for obj in results.objects:
                conversations.append({
                    "conversation_id": obj.properties['conversation_id'],
                    "category": obj.properties['category'],
                    "summary": obj.properties['summary'][:100] + "..." if len(obj.properties['summary']) > 100 else obj.properties['summary'],
                    "timestamp_start": obj.properties['timestamp_start'],
                    "message_count": obj.properties['message_count'],
                    "participants": obj.properties['participants'],
                })

            return {
                "success": True,
                "conversations": conversations,
                "count": len(conversations),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
