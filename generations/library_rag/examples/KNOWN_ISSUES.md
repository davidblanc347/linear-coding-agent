# Known Issues - MCP Client

## 1. Author/Work Filters Not Supported (Weaviate Limitation)

**Status:** Known limitation
**Affects:** `search_chunks` and `search_summaries` tools
**Error:** Results in server error when using `author_filter` or `work_filter` parameters

**Root Cause:**
Weaviate v4 does not support filtering on nested object properties. The `work` field in the Chunk schema is defined as:

```python
wvc.Property(
    name="work",
    data_type=wvc.DataType.OBJECT,
    nested_properties=[
        wvc.Property(name="title", data_type=wvc.DataType.TEXT),
        wvc.Property(name="author", data_type=wvc.DataType.TEXT),
    ],
)
```

Attempts to filter on `work.author` or `work.title` result in:
```
data type "object" not supported in query
```

**Workaround:**

Use the `filter_by_author` tool instead:

```python
# Instead of:
search_chunks(
    query="nominalism",
    author_filter="Charles Sanders Peirce"  # ❌ Doesn't work
)

# Use:
filter_by_author(
    author="Charles Sanders Peirce"  # ✓ Works
)
```

Or search without filters and filter client-side:

```python
results = await client.call_tool("search_chunks", {
    "query": "nominalism",
    "limit": 50  # Fetch more
})

# Filter in Python
filtered = [
    r for r in results["results"]
    if r["work_author"] == "Charles Sanders Peirce"
]
```

**Future Fix:**

Option 1: Add flat properties `workAuthor` and `workTitle` to Chunk schema (requires migration)
Option 2: Implement post-filtering in Python on the server side
Option 3: Wait for Weaviate to support nested object filtering

**Tests Affected:**

- `test_mcp_client.py::test_search_chunks` - Works without filters
- Search with `author_filter` - Currently fails

**Last Updated:** 2025-12-25
