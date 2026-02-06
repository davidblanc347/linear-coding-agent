"""
Identity MCP Tools - Handlers for reading Ikario and David state tensors.

Provides tools for:
- get_state_profile: Read Ikario's state tensor projected onto 109 interpretable directions
- get_david_profile: Read David's profile from messages + declared profile
- compare_profiles: Compare Ikario and David profiles
- get_state_tensor: Get raw 8x1024 state tensor (advanced usage)

Architecture v2: StateTensor (8 named vectors x 1024 dims) replaces StateVector (single 1024-dim).
Each category maps to a dimension via CATEGORY_TO_DIMENSION for proper projection.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import weaviate
from pydantic import BaseModel, Field

from memory.core import get_embedder


# =============================================================================
# Category -> Dimension mapping (must match state_to_language.py)
# =============================================================================

CATEGORY_TO_DIMENSION = {
    'epistemic': 'firstness',
    'affective': 'dispositions',
    'cognitive': 'thirdness',
    'relational': 'engagements',
    'ethical': 'valeurs',
    'temporal': 'orientations',
    'thematic': 'pertinences',
    'metacognitive': 'secondness',
    'vital': 'dispositions',
    'ecosystemic': 'engagements',
    'philosophical': 'thirdness',
}

DIMENSION_NAMES = [
    'firstness', 'secondness', 'thirdness',
    'dispositions', 'orientations', 'engagements',
    'pertinences', 'valeurs',
]


# =============================================================================
# Input Models
# =============================================================================


class GetStateProfileInput(BaseModel):
    """Input for get_state_profile tool."""

    state_id: Optional[int] = Field(
        default=None,
        description="State ID to retrieve (default: latest state)"
    )


class GetDavidProfileInput(BaseModel):
    """Input for get_david_profile tool."""

    include_declared: bool = Field(
        default=True,
        description="Include declared profile values from david_profile_declared.json"
    )
    max_messages: int = Field(
        default=500,
        ge=10,
        le=1000,
        description="Maximum number of David's messages to analyze"
    )


class CompareProfilesInput(BaseModel):
    """Input for compare_profiles tool."""

    categories: Optional[List[str]] = Field(
        default=None,
        description="Filter to specific categories (e.g., ['epistemic', 'affective'])"
    )
    state_id: Optional[int] = Field(
        default=None,
        description="Ikario state ID to compare (default: latest)"
    )


class GetStateTensorInput(BaseModel):
    """Input for get_state_tensor tool (advanced usage)."""

    state_id: Optional[int] = Field(
        default=None,
        description="State ID (default: latest)"
    )
    entity: str = Field(
        default="ikario",
        description="Entity to retrieve: 'ikario' or 'david'"
    )


# =============================================================================
# Helper Functions
# =============================================================================


def get_latest_state_tensor(client: weaviate.WeaviateClient) -> tuple[dict, dict]:
    """
    Get the latest StateTensor from Weaviate (v2 architecture).

    Returns:
        Tuple of (properties dict, named_vectors dict[dim_name -> list[float]])
    """
    collection = client.collections.get("StateTensor")

    result = collection.query.fetch_objects(
        limit=100,
        include_vector=True
    )

    if not result.objects:
        raise ValueError("No StateTensor found in Weaviate")

    # Find the one with highest state_id
    latest = max(result.objects, key=lambda o: o.properties.get("state_id", -1))

    # Extract named vectors
    named_vectors = {}
    if isinstance(latest.vector, dict):
        for dim_name in DIMENSION_NAMES:
            if dim_name in latest.vector:
                named_vectors[dim_name] = latest.vector[dim_name]

    if not named_vectors:
        raise ValueError(f"StateTensor S({latest.properties.get('state_id')}) has no named vectors")

    return latest.properties, named_vectors


def get_state_tensor_by_id(
    client: weaviate.WeaviateClient,
    state_id: int
) -> tuple[dict, dict]:
    """
    Get a specific StateTensor by state_id.

    Returns:
        Tuple of (properties dict, named_vectors dict[dim_name -> list[float]])
    """
    collection = client.collections.get("StateTensor")

    from weaviate.classes.query import Filter

    result = collection.query.fetch_objects(
        filters=Filter.by_property("state_id").equal(state_id),
        limit=1,
        include_vector=True
    )

    if not result.objects:
        raise ValueError(f"StateTensor with state_id={state_id} not found")

    obj = result.objects[0]

    named_vectors = {}
    if isinstance(obj.vector, dict):
        for dim_name in DIMENSION_NAMES:
            if dim_name in obj.vector:
                named_vectors[dim_name] = obj.vector[dim_name]

    if not named_vectors:
        raise ValueError(f"StateTensor S({state_id}) has no named vectors")

    return obj.properties, named_vectors


def get_all_projection_directions(client: weaviate.WeaviateClient) -> list[dict]:
    """
    Get all ProjectionDirection objects from Weaviate.

    Returns:
        List of direction objects with properties and vectors
    """
    collection = client.collections.get("ProjectionDirection")

    result = collection.query.fetch_objects(
        limit=200,
        include_vector=True
    )

    directions = []
    for obj in result.objects:
        directions.append({
            "name": obj.properties.get("name"),
            "category": obj.properties.get("category"),
            "pole_positive": obj.properties.get("pole_positive"),
            "pole_negative": obj.properties.get("pole_negative"),
            "description": obj.properties.get("description"),
            "vector": obj.vector["default"]
        })

    return directions


def compute_projection(state_vector: list, direction_vector: list) -> float:
    """
    Compute projection (dot product) of state onto direction.

    Both vectors should be normalized (cosine similarity).
    """
    state = np.array(state_vector)
    direction = np.array(direction_vector)

    return float(np.dot(state, direction))


def build_tensor_profile(
    named_vectors: dict,
    directions: list[dict]
) -> dict[str, dict[str, float]]:
    """
    Build a profile by projecting each direction onto the correct tensor dimension.

    Uses CATEGORY_TO_DIMENSION to map each direction's category to the right
    dimension of the 8x1024 state tensor.

    Returns:
        Dict[category, Dict[direction_name, projection_value]]
    """
    profile = {}

    for direction in directions:
        category = direction["category"]
        name = direction["name"]
        dir_vector = direction["vector"]

        # Map category to tensor dimension
        dim_name = CATEGORY_TO_DIMENSION.get(category, "thirdness")
        state_vector = named_vectors.get(dim_name)

        if state_vector is None:
            continue

        projection = compute_projection(state_vector, dir_vector)

        if category not in profile:
            profile[category] = {}

        profile[category][name] = round(projection, 4)

    return profile


def get_david_messages(client: weaviate.WeaviateClient, max_messages: int) -> list[str]:
    """
    Get David's messages from Weaviate Message collection.

    Returns:
        List of message contents
    """
    collection = client.collections.get("Message")

    from weaviate.classes.query import Filter

    result = collection.query.fetch_objects(
        filters=Filter.by_property("role").equal("user"),
        limit=max_messages
    )

    messages = []
    for obj in result.objects:
        content = obj.properties.get("content", "")
        if len(content) > 20:
            messages.append(content)

    return messages


def load_declared_profile() -> dict | None:
    """
    Load David's declared profile from JSON file.

    Returns:
        Profile dict or None if not found
    """
    possible_paths = [
        Path(__file__).parent.parent.parent / "ikario_processual" / "david_profile_declared.json",
        Path("ikario_processual/david_profile_declared.json"),
        Path("david_profile_declared.json"),
    ]

    for path in possible_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    return None


# =============================================================================
# Handlers
# =============================================================================


async def get_state_profile_handler(input_data: GetStateProfileInput) -> Dict[str, Any]:
    """
    Get Ikario's state profile projected onto interpretable directions.

    Uses StateTensor (8x1024) with CATEGORY_TO_DIMENSION mapping for proper projection.
    Returns profile organized by categories (epistemic, affective, etc.)
    with values for each direction (curiosity, certainty, etc.).
    """
    try:
        client = weaviate.connect_to_local()

        try:
            # 1. Get StateTensor (8 named vectors)
            if input_data.state_id is not None:
                properties, named_vectors = get_state_tensor_by_id(
                    client, input_data.state_id
                )
            else:
                properties, named_vectors = get_latest_state_tensor(client)

            # 2. Get all ProjectionDirections
            directions = get_all_projection_directions(client)

            if not directions:
                return {
                    "success": False,
                    "error": "No ProjectionDirection found in Weaviate. Run phase2_projection_directions.py first."
                }

            # 3. Build profile using tensor dimensions
            profile = build_tensor_profile(named_vectors, directions)

            return {
                "success": True,
                "state_id": properties.get("state_id"),
                "timestamp": str(properties.get("timestamp", "")),
                "trigger_type": properties.get("trigger_type", "unknown"),
                "profile": profile,
                "directions_count": len(directions),
                "categories": list(profile.keys()),
                "architecture": "v2_tensor",
                "dimensions_loaded": list(named_vectors.keys())
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_david_profile_handler(input_data: GetDavidProfileInput) -> Dict[str, Any]:
    """
    Get David's profile from his messages and optionally declared profile.

    Computes David's embedding from his messages, projects onto directions,
    and optionally merges with declared profile values.
    """
    try:
        client = weaviate.connect_to_local()

        try:
            # 1. Get David's messages
            messages = get_david_messages(client, input_data.max_messages)

            if not messages:
                return {
                    "success": False,
                    "error": "No messages from David found in Weaviate"
                }

            # 2. Concatenate and embed
            text = "\n\n".join(messages)[:5000]

            embedder = get_embedder()
            david_vector = embedder.embed_batch([text])[0].tolist()

            # 3. Get directions and compute profile
            directions = get_all_projection_directions(client)

            if not directions:
                return {
                    "success": False,
                    "error": "No ProjectionDirection found. Run phase2_projection_directions.py first."
                }

            # For David, use same vector for all dimensions (single embedding)
            david_named_vectors = {dim: david_vector for dim in DIMENSION_NAMES}
            computed_profile = build_tensor_profile(david_named_vectors, directions)

            # 4. Load declared profile if requested
            declared_profile = None
            has_declared = False

            if input_data.include_declared:
                declared_data = load_declared_profile()
                if declared_data:
                    declared_profile = declared_data.get("profile", {})
                    has_declared = True

            # 5. Merge profiles (declared takes precedence for display)
            final_profile = {}
            for category, directions_dict in computed_profile.items():
                final_profile[category] = {}
                for name, computed_value in directions_dict.items():
                    entry = {
                        "computed": computed_value,
                    }

                    if declared_profile and category in declared_profile:
                        declared_value = declared_profile[category].get(name)
                        if declared_value is not None:
                            entry["declared"] = declared_value
                            entry["declared_normalized"] = round(declared_value / 10, 2)

                    final_profile[category][name] = entry

            # 6. Compute similarity with Ikario
            try:
                _, ikario_vectors = get_latest_state_tensor(client)
                # Cosine similarity across all dimensions
                similarities = []
                for dim_name in DIMENSION_NAMES:
                    if dim_name in ikario_vectors:
                        sim = float(np.dot(david_vector, ikario_vectors[dim_name]))
                        similarities.append(sim)
                similarity_percent = round(np.mean(similarities) * 100, 1) if similarities else None
            except Exception:
                similarity_percent = None

            return {
                "success": True,
                "profile": final_profile,
                "similarity_with_ikario": similarity_percent,
                "messages_analyzed": len(messages),
                "has_declared_profile": has_declared,
                "categories": list(final_profile.keys()),
                "directions_count": len(directions)
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def compare_profiles_handler(input_data: CompareProfilesInput) -> Dict[str, Any]:
    """
    Compare Ikario and David profiles.

    Returns similarity score and detailed comparison by direction,
    including convergent and divergent dimensions.
    """
    try:
        client = weaviate.connect_to_local()

        try:
            # 1. Get Ikario's state tensor
            if input_data.state_id is not None:
                _, ikario_vectors = get_state_tensor_by_id(client, input_data.state_id)
            else:
                _, ikario_vectors = get_latest_state_tensor(client)

            # 2. Get David's messages and embed
            messages = get_david_messages(client, max_messages=100)
            if not messages:
                return {
                    "success": False,
                    "error": "No messages from David found"
                }

            text = "\n\n".join(messages)[:5000]
            embedder = get_embedder()
            david_vector = embedder.embed_batch([text])[0].tolist()
            david_named_vectors = {dim: david_vector for dim in DIMENSION_NAMES}

            # 3. Get directions
            directions = get_all_projection_directions(client)
            if not directions:
                return {
                    "success": False,
                    "error": "No ProjectionDirection found"
                }

            # 4. Filter directions by category if specified
            if input_data.categories:
                directions = [
                    d for d in directions
                    if d["category"] in input_data.categories
                ]

            # 5. Compute projections for both using tensor dimensions
            ikario_profile = build_tensor_profile(ikario_vectors, directions)
            david_profile = build_tensor_profile(david_named_vectors, directions)

            # 6. Build comparison
            comparison = {}
            all_deltas = []

            for category in ikario_profile.keys():
                comparison[category] = {}
                for name in ikario_profile[category].keys():
                    ikario_val = ikario_profile[category][name]
                    david_val = david_profile[category].get(name, 0)
                    delta = round(abs(ikario_val - david_val), 4)

                    comparison[category][name] = {
                        "ikario": ikario_val,
                        "david": david_val,
                        "delta": delta
                    }

                    all_deltas.append({
                        "name": name,
                        "category": category,
                        "ikario": ikario_val,
                        "david": david_val,
                        "delta": delta
                    })

            # 7. Find convergent and divergent dimensions
            sorted_by_delta = sorted(all_deltas, key=lambda x: x["delta"])

            convergent = sorted_by_delta[:5]
            divergent = sorted_by_delta[-5:][::-1]

            # 8. Compute overall similarity (mean across dimensions)
            similarities = []
            for dim_name in DIMENSION_NAMES:
                if dim_name in ikario_vectors:
                    sim = float(np.dot(david_vector, ikario_vectors[dim_name]))
                    similarities.append(sim)
            similarity_percent = round(np.mean(similarities) * 100, 1) if similarities else 0

            return {
                "success": True,
                "similarity": similarity_percent,
                "comparison": comparison,
                "convergent_dimensions": [
                    {
                        "name": d["name"],
                        "category": d["category"],
                        "ikario": d["ikario"],
                        "david": d["david"]
                    }
                    for d in convergent
                ],
                "divergent_dimensions": [
                    {
                        "name": d["name"],
                        "category": d["category"],
                        "ikario": d["ikario"],
                        "david": d["david"]
                    }
                    for d in divergent
                ],
                "categories_compared": list(comparison.keys()),
                "directions_compared": len(all_deltas)
            }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_state_tensor_handler(input_data: GetStateTensorInput) -> Dict[str, Any]:
    """
    Get raw 8x1024 state tensor (advanced usage).

    Returns the 8 named dimension vectors for Ikario or a single embedding for David.
    """
    try:
        client = weaviate.connect_to_local()

        try:
            if input_data.entity == "ikario":
                if input_data.state_id is not None:
                    properties, named_vectors = get_state_tensor_by_id(
                        client, input_data.state_id
                    )
                else:
                    properties, named_vectors = get_latest_state_tensor(client)

                # Return first 10 values per dimension (truncated for readability)
                truncated = {
                    dim: list(vec[:10]) if hasattr(vec, '__len__') else vec
                    for dim, vec in named_vectors.items()
                }

                return {
                    "success": True,
                    "entity": "ikario",
                    "dimensions": truncated,
                    "dimension_count": len(named_vectors),
                    "vector_size": 1024,
                    "metadata": {
                        "state_id": properties.get("state_id"),
                        "timestamp": str(properties.get("timestamp", "")),
                        "trigger_type": properties.get("trigger_type")
                    }
                }

            elif input_data.entity == "david":
                messages = get_david_messages(client, max_messages=100)
                if not messages:
                    return {
                        "success": False,
                        "error": "No messages from David found"
                    }

                text = "\n\n".join(messages)[:5000]
                embedder = get_embedder()
                david_vector = embedder.embed_batch([text])[0].tolist()

                return {
                    "success": True,
                    "entity": "david",
                    "vector": david_vector[:10],  # Truncated
                    "dimension": len(david_vector),
                    "metadata": {
                        "source": "messages_embedding",
                        "messages_count": len(messages)
                    }
                }

            else:
                return {
                    "success": False,
                    "error": f"Unknown entity: {input_data.entity}. Use 'ikario' or 'david'."
                }

        finally:
            client.close()

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
