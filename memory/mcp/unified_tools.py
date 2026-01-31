"""
Unified Memory MCP Tools.

Provides unified search and analysis tools that work across
Thoughts and Conversations collections.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import weaviate
from weaviate.classes.query import MetadataQuery
import os
from datetime import datetime, timedelta
import re

# Import embedder for vector search (since Weaviate vectorizer is "none")
from memory.core.embedding_service import get_embedder


# =============================================================================
# Input Models
# =============================================================================


class SearchMemoriesInput(BaseModel):
    """Input for unified memory search."""
    query: str = Field(description="Search query text (can be empty for listing)")
    n_results: int = Field(default=5, ge=1, le=20, description="Number of results")
    filter_type: Optional[str] = Field(default=None, description="Filter: 'thoughts' or 'conversations'")
    since: Optional[str] = Field(default=None, description="Filter after date (ISO or relative: 7d, 3h, 1w)")
    before: Optional[str] = Field(default=None, description="Filter before date (ISO only)")
    sort_by: Optional[str] = Field(default="relevance", description="Sort: relevance, date_desc, date_asc")


class TraceConceptEvolutionInput(BaseModel):
    """Input for concept evolution tracing."""
    concept: str = Field(description="The concept to trace")
    limit: int = Field(default=10, ge=1, le=50, description="Max timeline points")


class CheckConsistencyInput(BaseModel):
    """Input for consistency checking."""
    statement: str = Field(description="The statement to check for consistency")


class UpdateThoughtEvolutionStageInput(BaseModel):
    """Input for updating thought evolution stage."""
    thought_id: str = Field(description="Thought ID (format: thought_YYYY-MM-DDTHH:MM:SS or UUID)")
    new_stage: str = Field(description="New stage: nascent, developing, mature, revised, abandoned")


# =============================================================================
# Helper Functions
# =============================================================================


def get_weaviate_client():
    """Get Weaviate client from environment."""
    url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
    api_key = os.environ.get("WEAVIATE_API_KEY")

    if api_key:
        return weaviate.connect_to_custom(
            http_host=url.replace("http://", "").replace("https://", "").split(":")[0],
            http_port=int(url.split(":")[-1]) if ":" in url.split("/")[-1] else 8080,
            http_secure=url.startswith("https"),
            auth_credentials=weaviate.auth.AuthApiKey(api_key),
        )
    else:
        return weaviate.connect_to_local(
            host=url.replace("http://", "").replace("https://", "").split(":")[0],
            port=int(url.split(":")[-1]) if ":" in url.split("/")[-1] else 8080,
        )


def parse_relative_date(date_str: str) -> Optional[datetime]:
    """Parse relative date string (7d, 3h, 1w, 30m) to datetime."""
    if not date_str:
        return None

    # Try ISO format first
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    # Parse relative format
    match = re.match(r"(\d+)([dhwm])", date_str.lower())
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        now = datetime.now()
        if unit == "d":
            return now - timedelta(days=value)
        elif unit == "h":
            return now - timedelta(hours=value)
        elif unit == "w":
            return now - timedelta(weeks=value)
        elif unit == "m":
            return now - timedelta(minutes=value)

    return None


# =============================================================================
# Tool Handlers
# =============================================================================


async def search_memories_handler(input_data: SearchMemoriesInput) -> Dict[str, Any]:
    """
    Search across both Thoughts and Conversations.

    Returns unified results sorted by relevance or date.
    Uses near_vector with embedder since Weaviate vectorizer is "none".
    """
    try:
        client = get_weaviate_client()
        results = []

        # Get embedder for vector search
        embedder = get_embedder()
        query_vector = None
        if input_data.query:
            query_vector = embedder.embed_batch([input_data.query])[0].tolist()

        # Parse date filters
        since_dt = parse_relative_date(input_data.since) if input_data.since else None
        before_dt = parse_relative_date(input_data.before) if input_data.before else None

        # Search Thoughts (if not filtered to conversations only)
        if input_data.filter_type != "conversations":
            try:
                thought_collection = client.collections.get("Thought")

                if query_vector:
                    thought_results = thought_collection.query.near_vector(
                        near_vector=query_vector,
                        limit=input_data.n_results,
                        return_metadata=MetadataQuery(distance=True),
                    )
                else:
                    thought_results = thought_collection.query.fetch_objects(
                        limit=input_data.n_results,
                    )

                for obj in thought_results.objects:
                    props = obj.properties
                    timestamp = props.get("timestamp", "")

                    # Apply date filters
                    if since_dt and timestamp:
                        try:
                            obj_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if obj_dt < since_dt:
                                continue
                        except:
                            pass

                    if before_dt and timestamp:
                        try:
                            obj_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if obj_dt > before_dt:
                                continue
                        except:
                            pass

                    results.append({
                        "type": "thought",
                        "id": str(obj.uuid),
                        "content": props.get("content", "")[:500],
                        "thought_type": props.get("thought_type", ""),
                        "timestamp": timestamp,
                        "concepts": props.get("concepts", []),
                        "distance": obj.metadata.distance if obj.metadata else None,
                    })
            except Exception as e:
                # Collection might not exist
                pass

        # Search Conversations (if not filtered to thoughts only)
        if input_data.filter_type != "thoughts":
            try:
                conv_collection = client.collections.get("Conversation")

                if query_vector:
                    conv_results = conv_collection.query.near_vector(
                        near_vector=query_vector,
                        limit=input_data.n_results,
                        return_metadata=MetadataQuery(distance=True),
                    )
                else:
                    conv_results = conv_collection.query.fetch_objects(
                        limit=input_data.n_results,
                    )

                for obj in conv_results.objects:
                    props = obj.properties
                    timestamp = props.get("timestamp_start", "") or props.get("timestamp_end", "")

                    # Apply date filters
                    if since_dt and timestamp:
                        try:
                            obj_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if obj_dt < since_dt:
                                continue
                        except:
                            pass

                    if before_dt and timestamp:
                        try:
                            obj_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if obj_dt > before_dt:
                                continue
                        except:
                            pass

                    results.append({
                        "type": "conversation",
                        "id": props.get("conversation_id", str(obj.uuid)),
                        "summary": props.get("summary", "")[:500],
                        "category": props.get("category", ""),
                        "timestamp": timestamp,
                        "tags": props.get("tags", []),
                        "distance": obj.metadata.distance if obj.metadata else None,
                    })
            except Exception as e:
                # Collection might not exist
                pass

        # Sort results
        if input_data.sort_by == "date_desc":
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        elif input_data.sort_by == "date_asc":
            results.sort(key=lambda x: x.get("timestamp", ""))
        else:
            # Sort by distance (relevance) - lower is better
            results.sort(key=lambda x: x.get("distance") or 999)

        # Limit results
        results = results[:input_data.n_results]

        client.close()

        return {
            "success": True,
            "query": input_data.query,
            "results": results,
            "count": len(results),
            "filter_type": input_data.filter_type,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": input_data.query,
            "results": [],
            "count": 0,
        }


async def trace_concept_evolution_handler(input_data: TraceConceptEvolutionInput) -> Dict[str, Any]:
    """
    Trace the evolution of a concept through thoughts and conversations over time.

    Returns a timeline showing how the concept appeared and evolved.
    Uses near_vector with embedder since Weaviate vectorizer is "none".
    """
    try:
        client = get_weaviate_client()
        timeline = []

        # Get embedder for vector search
        embedder = get_embedder()
        concept_vector = embedder.embed_batch([input_data.concept])[0].tolist()

        # Search Thoughts for the concept
        try:
            thought_collection = client.collections.get("Thought")
            thought_results = thought_collection.query.near_vector(
                near_vector=concept_vector,
                limit=input_data.limit,
                return_metadata=MetadataQuery(distance=True),
            )

            for obj in thought_results.objects:
                props = obj.properties
                distance = obj.metadata.distance if obj.metadata else 1.0

                # Only include reasonably relevant results
                if distance < 0.8:
                    timeline.append({
                        "type": "thought",
                        "id": str(obj.uuid),
                        "timestamp": props.get("timestamp", ""),
                        "content": props.get("content", "")[:300],
                        "thought_type": props.get("thought_type", ""),
                        "evolution_stage": props.get("evolution_stage", "nascent"),
                        "relevance": 1 - distance,
                    })
        except:
            pass

        # Search Conversations for the concept
        try:
            conv_collection = client.collections.get("Conversation")
            conv_results = conv_collection.query.near_vector(
                near_vector=concept_vector,
                limit=input_data.limit,
                return_metadata=MetadataQuery(distance=True),
            )

            for obj in conv_results.objects:
                props = obj.properties
                distance = obj.metadata.distance if obj.metadata else 1.0

                if distance < 0.8:
                    timeline.append({
                        "type": "conversation",
                        "id": props.get("conversation_id", str(obj.uuid)),
                        "timestamp": props.get("timestamp_start", ""),
                        "summary": props.get("summary", "")[:300],
                        "category": props.get("category", ""),
                        "relevance": 1 - distance,
                    })
        except:
            pass

        # Sort by timestamp
        timeline.sort(key=lambda x: x.get("timestamp", ""))

        # Limit results
        timeline = timeline[:input_data.limit]

        client.close()

        return {
            "success": True,
            "concept": input_data.concept,
            "timeline": timeline,
            "count": len(timeline),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "concept": input_data.concept,
            "timeline": [],
            "count": 0,
        }


async def check_consistency_handler(input_data: CheckConsistencyInput) -> Dict[str, Any]:
    """
    Check if a statement is consistent with existing thoughts and conversations.

    Searches for similar content and identifies potential contradictions.
    Uses near_vector with embedder since Weaviate vectorizer is "none".
    """
    try:
        client = get_weaviate_client()
        related_content = []

        # Get embedder for vector search
        embedder = get_embedder()
        statement_vector = embedder.embed_batch([input_data.statement])[0].tolist()

        # Search for similar thoughts
        try:
            thought_collection = client.collections.get("Thought")
            thought_results = thought_collection.query.near_vector(
                near_vector=statement_vector,
                limit=10,
                return_metadata=MetadataQuery(distance=True),
            )

            for obj in thought_results.objects:
                props = obj.properties
                distance = obj.metadata.distance if obj.metadata else 1.0

                if distance < 0.7:  # Only very similar content
                    related_content.append({
                        "type": "thought",
                        "content": props.get("content", "")[:400],
                        "thought_type": props.get("thought_type", ""),
                        "timestamp": props.get("timestamp", ""),
                        "similarity": 1 - distance,
                    })
        except:
            pass

        # Search for similar conversations
        try:
            conv_collection = client.collections.get("Conversation")
            conv_results = conv_collection.query.near_vector(
                near_vector=statement_vector,
                limit=10,
                return_metadata=MetadataQuery(distance=True),
            )

            for obj in conv_results.objects:
                props = obj.properties
                distance = obj.metadata.distance if obj.metadata else 1.0

                if distance < 0.7:
                    related_content.append({
                        "type": "conversation",
                        "summary": props.get("summary", "")[:400],
                        "category": props.get("category", ""),
                        "timestamp": props.get("timestamp_start", ""),
                        "similarity": 1 - distance,
                    })
        except:
            pass

        client.close()

        # Sort by similarity
        related_content.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        # Calculate consistency score
        if not related_content:
            consistency_score = 1.0  # No related content = no contradiction
            analysis = "Aucun contenu similaire trouvé. L'affirmation semble nouvelle."
        else:
            avg_similarity = sum(c.get("similarity", 0) for c in related_content) / len(related_content)
            consistency_score = avg_similarity

            if avg_similarity > 0.8:
                analysis = "L'affirmation est très cohérente avec le contenu existant."
            elif avg_similarity > 0.6:
                analysis = "L'affirmation est partiellement cohérente. Quelques nuances possibles."
            else:
                analysis = "L'affirmation pourrait nécessiter une vérification. Similarité modérée."

        return {
            "success": True,
            "statement": input_data.statement,
            "consistency_score": round(consistency_score, 2),
            "analysis": analysis,
            "related_content": related_content[:5],
            "count": len(related_content),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "statement": input_data.statement,
            "consistency_score": 0,
            "analysis": f"Erreur lors de la vérification: {str(e)}",
            "related_content": [],
        }


async def update_thought_evolution_stage_handler(
    input_data: UpdateThoughtEvolutionStageInput
) -> Dict[str, Any]:
    """
    Update the evolution stage of an existing thought.

    Stages: nascent, developing, mature, revised, abandoned
    """
    valid_stages = ["nascent", "developing", "mature", "revised", "abandoned"]

    if input_data.new_stage not in valid_stages:
        return {
            "success": False,
            "error": f"Invalid stage. Must be one of: {', '.join(valid_stages)}",
            "thought_id": input_data.thought_id,
        }

    try:
        client = get_weaviate_client()
        thought_collection = client.collections.get("Thought")

        # Try to find the thought by ID
        # The thought_id could be a UUID or a custom format like "thought_2025-01-15T10:30:00"
        thought_uuid = None

        # Try direct UUID lookup
        try:
            import uuid as uuid_module
            thought_uuid = uuid_module.UUID(input_data.thought_id)
        except ValueError:
            # Not a UUID, search by custom ID pattern
            pass

        if thought_uuid:
            # Update by UUID
            thought_collection.data.update(
                uuid=thought_uuid,
                properties={"evolution_stage": input_data.new_stage}
            )
        else:
            # Search for thought with matching ID in content or metadata
            results = thought_collection.query.fetch_objects(
                limit=100,  # Search through recent thoughts
            )

            found = False
            for obj in results.objects:
                # Check if the thought_id matches any identifier
                props = obj.properties
                timestamp = props.get("timestamp", "")

                # Match by timestamp-based ID
                if input_data.thought_id in timestamp or timestamp in input_data.thought_id:
                    thought_collection.data.update(
                        uuid=obj.uuid,
                        properties={"evolution_stage": input_data.new_stage}
                    )
                    found = True
                    break

            if not found:
                client.close()
                return {
                    "success": False,
                    "error": f"Thought not found with ID: {input_data.thought_id}",
                    "thought_id": input_data.thought_id,
                }

        client.close()

        return {
            "success": True,
            "thought_id": input_data.thought_id,
            "new_stage": input_data.new_stage,
            "message": f"Evolution stage updated to '{input_data.new_stage}'",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "thought_id": input_data.thought_id,
        }
