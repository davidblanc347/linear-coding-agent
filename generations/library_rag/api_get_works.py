

# ═══════════════════════════════════════════════════════════════════════════════
# Works Filter API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/get-works")
def api_get_works() -> WerkzeugResponse:
    """Get list of all available works with metadata for filtering.

    Returns a JSON array of all unique works in the database, sorted by author
    then title. Each work includes the title, author, and number of chunks.

    Returns:
        JSON response with array of works:
        [
            {"title": "Ménon", "author": "Platon", "chunks_count": 127},
            ...
        ]

    Raises:
        500: If Weaviate connection fails or query errors occur.

    Example:
        GET /api/get-works
        Returns: [{"title": "Ménon", "author": "Platon", "chunks_count": 127}, ...]
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return jsonify({
                    "error": "Weaviate connection failed",
                    "message": "Cannot connect to Weaviate database"
                }), 500

            # Query Chunk collection to get all unique works with counts
            chunks = client.collections.get("Chunk")

            # Fetch all chunks to aggregate by work
            # Using a larger limit to get all documents
            all_chunks = chunks.query.fetch_objects(
                limit=10000,
                return_properties=["work"]
            )

            # Aggregate chunks by work (title + author)
            works_count: Dict[str, Dict[str, Any]] = {}

            for obj in all_chunks.objects:
                work_obj = obj.properties.get("work")
                if work_obj and isinstance(work_obj, dict):
                    title = work_obj.get("title", "")
                    author = work_obj.get("author", "")

                    if title:  # Only count if title exists
                        # Use title as key (assumes unique titles)
                        if title not in works_count:
                            works_count[title] = {
                                "title": title,
                                "author": author or "Unknown",
                                "chunks_count": 0
                            }
                        works_count[title]["chunks_count"] += 1

            # Convert to list and sort by author, then title
            works_list = list(works_count.values())
            works_list.sort(key=lambda w: (w["author"].lower(), w["title"].lower()))

            print(f"[API] /api/get-works: Found {len(works_list)} unique works")

            return jsonify(works_list)

    except Exception as e:
        print(f"[API] /api/get-works error: {e}")
        return jsonify({
            "error": "Database query failed",
            "message": str(e)
        }), 500


