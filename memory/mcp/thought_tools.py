"""
Thought MCP Tools - Handlers for thought-related operations.

Provides tools for adding, searching, and retrieving thoughts from Weaviate.
"""

import weaviate
from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field
from memory.core import get_embedder


class AddThoughtInput(BaseModel):
    """Input for add_thought tool."""
    content: str = Field(..., description="The thought content")
    thought_type: str = Field(default="reflection", description="Type: reflection, question, intuition, observation, etc.")
    trigger: str = Field(default="", description="What triggered this thought")
    concepts: list[str] = Field(default_factory=list, description="Related concepts/tags")
    privacy_level: str = Field(default="private", description="Privacy: private, shared, public")


class SearchThoughtsInput(BaseModel):
    """Input for search_thoughts tool."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    thought_type_filter: str | None = Field(default=None, description="Filter by thought type")


async def add_thought_handler(input_data: AddThoughtInput) -> Dict[str, Any]:
    """
    Add a new thought to Weaviate.

    Args:
        input_data: Thought data to add.

    Returns:
        Dictionary with success status and thought UUID.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get embedder
            embedder = get_embedder()

            # Generate vector for thought content
            vector = embedder.embed_batch([input_data.content])[0]

            # Get collection
            collection = client.collections.get("Thought")

            # Insert thought
            uuid = collection.data.insert(
                properties={
                    "content": input_data.content,
                    "thought_type": input_data.thought_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trigger": input_data.trigger,
                    "concepts": input_data.concepts,
                    "privacy_level": input_data.privacy_level,
                    "emotional_state": "",
                    "context": "",
                },
                vector=vector.tolist()
            )

            return {
                "success": True,
                "uuid": str(uuid),
                "content": input_data.content[:100] + "..." if len(input_data.content) > 100 else input_data.content,
                "thought_type": input_data.thought_type,
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def search_thoughts_handler(input_data: SearchThoughtsInput) -> Dict[str, Any]:
    """
    Search thoughts using semantic similarity.

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
            collection = client.collections.get("Thought")

            # Build query
            query = collection.query.near_vector(
                near_vector=query_vector.tolist(),
                limit=input_data.limit,
            )

            # Apply thought_type filter if provided
            if input_data.thought_type_filter:
                query = query.where({
                    "path": ["thought_type"],
                    "operator": "Equal",
                    "valueText": input_data.thought_type_filter,
                })

            # Execute search
            results = query.objects

            # Format results
            thoughts = []
            for obj in results:
                thoughts.append({
                    "uuid": str(obj.uuid),
                    "content": obj.properties['content'],
                    "thought_type": obj.properties['thought_type'],
                    "timestamp": obj.properties['timestamp'],
                    "trigger": obj.properties.get('trigger', ''),
                    "concepts": obj.properties.get('concepts', []),
                })

            return {
                "success": True,
                "query": input_data.query,
                "results": thoughts,
                "count": len(thoughts),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def get_thought_handler(uuid: str) -> Dict[str, Any]:
    """
    Get a specific thought by UUID.

    Args:
        uuid: Thought UUID.

    Returns:
        Dictionary with thought data.
    """
    try:
        # Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # Get collection
            collection = client.collections.get("Thought")

            # Fetch by UUID
            obj = collection.query.fetch_object_by_id(uuid)

            if not obj:
                return {
                    "success": False,
                    "error": f"Thought {uuid} not found",
                }

            return {
                "success": True,
                "uuid": str(obj.uuid),
                "content": obj.properties['content'],
                "thought_type": obj.properties['thought_type'],
                "timestamp": obj.properties['timestamp'],
                "trigger": obj.properties.get('trigger', ''),
                "concepts": obj.properties.get('concepts', []),
                "privacy_level": obj.properties.get('privacy_level', 'private'),
                "emotional_state": obj.properties.get('emotional_state', ''),
                "context": obj.properties.get('context', ''),
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
