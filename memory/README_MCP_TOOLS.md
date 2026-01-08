# Memory MCP Tools Documentation

## Overview

The Memory MCP tools provide a complete interface for managing thoughts, messages, and conversations in the unified Weaviate-based memory system. These tools are integrated into the Library RAG MCP server (`generations/library_rag/mcp_server.py`) and use GPU-accelerated embeddings for semantic search.

## Architecture

- **Backend**: Weaviate 1.34.4 (local instance)
- **Embeddings**: BAAI/bge-m3 model (1024 dimensions, FP16 precision)
- **GPU**: CUDA-enabled (RTX 4070) via PyTorch 2.6.0+cu124
- **Collections**: 3 Weaviate collections (Thought, Message, Conversation)
- **Integration**: FastMCP framework with async handlers

## Available Tools

### Thought Tools (3)

#### 1. add_thought
Add a new thought to the memory system.

**Parameters:**
- `content` (str, required): The thought content
- `thought_type` (str, default="reflection"): Type of thought (reflection, question, intuition, observation, etc.)
- `trigger` (str, default=""): What triggered this thought
- `concepts` (list[str], default=[]): Related concepts/tags
- `privacy_level` (str, default="private"): Privacy level (private, shared, public)

**Returns:**
```python
{
    "success": True,
    "uuid": "730c1a8e-b09f-4889-bbe9-4867d0ee7f1a",
    "content": "This is a test thought...",
    "thought_type": "observation"
}
```

**Example:**
```python
result = await add_thought(
    content="Exploring vector databases for semantic search",
    thought_type="observation",
    trigger="Research session",
    concepts=["weaviate", "embeddings", "gpu"],
    privacy_level="private"
)
```

#### 2. search_thoughts
Search thoughts using semantic similarity.

**Parameters:**
- `query` (str, required): Search query text
- `limit` (int, default=10, range=1-100): Maximum results to return
- `thought_type_filter` (str, optional): Filter by thought type

**Returns:**
```python
{
    "success": True,
    "query": "vector databases GPU",
    "results": [
        {
            "uuid": "...",
            "content": "...",
            "thought_type": "observation",
            "timestamp": "2025-01-08T...",
            "trigger": "...",
            "concepts": ["weaviate", "gpu"]
        }
    ],
    "count": 5
}
```

#### 3. get_thought
Retrieve a specific thought by UUID.

**Parameters:**
- `uuid` (str, required): Thought UUID

**Returns:**
```python
{
    "success": True,
    "uuid": "730c1a8e-b09f-4889-bbe9-4867d0ee7f1a",
    "content": "...",
    "thought_type": "observation",
    "timestamp": "2025-01-08T...",
    "trigger": "...",
    "concepts": [...],
    "privacy_level": "private",
    "emotional_state": "",
    "context": ""
}
```

---

### Message Tools (3)

#### 1. add_message
Add a new message to a conversation.

**Parameters:**
- `content` (str, required): Message content
- `role` (str, required): Role (user, assistant, system)
- `conversation_id` (str, required): Conversation identifier
- `order_index` (int, default=0): Position in conversation

**Returns:**
```python
{
    "success": True,
    "uuid": "...",
    "content": "Hello, this is a test...",
    "role": "user",
    "conversation_id": "test_conversation_001"
}
```

**Example:**
```python
result = await add_message(
    content="Explain transformers in AI",
    role="user",
    conversation_id="chat_2025_01_08",
    order_index=0
)
```

#### 2. get_messages
Get all messages from a conversation in order.

**Parameters:**
- `conversation_id` (str, required): Conversation identifier
- `limit` (int, default=50, range=1-500): Maximum messages to return

**Returns:**
```python
{
    "success": True,
    "conversation_id": "test_conversation_001",
    "messages": [
        {
            "uuid": "...",
            "content": "...",
            "role": "user",
            "timestamp": "2025-01-08T...",
            "order_index": 0
        },
        {
            "uuid": "...",
            "content": "...",
            "role": "assistant",
            "timestamp": "2025-01-08T...",
            "order_index": 1
        }
    ],
    "count": 2
}
```

#### 3. search_messages
Search messages using semantic similarity.

**Parameters:**
- `query` (str, required): Search query text
- `limit` (int, default=10, range=1-100): Maximum results
- `conversation_id_filter` (str, optional): Filter by conversation

**Returns:**
```python
{
    "success": True,
    "query": "transformers AI",
    "results": [...],
    "count": 5
}
```

---

### Conversation Tools (3)

#### 1. get_conversation
Get a specific conversation by ID.

**Parameters:**
- `conversation_id` (str, required): Conversation identifier

**Returns:**
```python
{
    "success": True,
    "conversation_id": "ikario_derniere_pensee",
    "category": "testing",
    "summary": "Conversation with 2 participants...",
    "timestamp_start": "2025-01-06T...",
    "timestamp_end": "2025-01-06T...",
    "participants": ["assistant", "user"],
    "tags": [],
    "message_count": 19
}
```

#### 2. search_conversations
Search conversations using semantic similarity on summaries.

**Parameters:**
- `query` (str, required): Search query text
- `limit` (int, default=10, range=1-50): Maximum results
- `category_filter` (str, optional): Filter by category

**Returns:**
```python
{
    "success": True,
    "query": "philosophical discussion",
    "results": [
        {
            "conversation_id": "...",
            "category": "philosophy",
            "summary": "...",
            "timestamp_start": "...",
            "timestamp_end": "...",
            "participants": [...],
            "message_count": 25
        }
    ],
    "count": 5
}
```

#### 3. list_conversations
List all conversations with optional filtering.

**Parameters:**
- `limit` (int, default=20, range=1-100): Maximum conversations to return
- `category_filter` (str, optional): Filter by category

**Returns:**
```python
{
    "success": True,
    "conversations": [
        {
            "conversation_id": "...",
            "category": "testing",
            "summary": "Conversation with 2 participants... (truncated)",
            "timestamp_start": "...",
            "message_count": 19,
            "participants": [...]
        }
    ],
    "count": 10
}
```

---

## Implementation Details

### Handler Pattern

All tools follow a consistent async handler pattern:

```python
async def tool_handler(input_data: InputModel) -> Dict[str, Any]:
    """Handler function."""
    try:
        # 1. Connect to Weaviate
        client = weaviate.connect_to_local()

        try:
            # 2. Get GPU embedder (for vectorization)
            embedder = get_embedder()

            # 3. Generate vector (if needed)
            vector = embedder.embed_batch([text])[0]

            # 4. Query/Insert data
            collection = client.collections.get("CollectionName")
            result = collection.data.insert(...)

            # 5. Return success response
            return {"success": True, ...}

        finally:
            client.close()

    except Exception as e:
        return {"success": False, "error": str(e)}
```

### GPU Vectorization

All text content is vectorized using the GPU-accelerated embedder:

```python
from memory.core import get_embedder

embedder = get_embedder()  # Returns PyTorch GPU embedder
vector = embedder.embed_batch([content])[0]  # Returns 1024-dim FP16 vector
```

### Weaviate Connection

Each tool handler creates a new connection and closes it after use:

```python
client = weaviate.connect_to_local()  # Connects to localhost:8080
try:
    # Perform operations
    collection = client.collections.get("Thought")
    # ...
finally:
    client.close()  # Always close connection
```

## Testing

A comprehensive test suite is available at `test_memory_mcp_tools.py`:

```bash
python test_memory_mcp_tools.py
```

**Test Results (2025-01-08):**
```
============================================================
TESTING THOUGHT TOOLS
============================================================
[OK] add_thought: Created thought with UUID
[OK] search_thoughts: Found 5 thoughts
[OK] get_thought: Retrieved thought successfully

============================================================
TESTING MESSAGE TOOLS
============================================================
[OK] add_message: Added 3 messages (user, assistant, user)
[OK] get_messages: Retrieved 3 messages in order
[OK] search_messages: Found 5 messages

============================================================
TESTING CONVERSATION TOOLS
============================================================
[OK] list_conversations: Found 10 conversations
[OK] get_conversation: Retrieved conversation metadata
[OK] search_conversations: Found 5 conversations

[OK] ALL TESTS COMPLETED
============================================================
```

## Integration with MCP Server

The Memory tools are integrated into `generations/library_rag/mcp_server.py` alongside the existing Library RAG tools:

**Total tools available: 17**
- Library RAG: 8 tools (search_documents, add_document, etc.)
- Memory: 9 tools (thought, message, conversation tools)

**Configuration:**
The MCP server is configured in Claude Desktop settings:
```json
{
  "mcpServers": {
    "library-rag": {
      "command": "python",
      "args": ["C:/GitHub/linear_coding_library_rag/generations/library_rag/mcp_server.py"]
    }
  }
}
```

## Error Handling

All tools return consistent error responses:

```python
{
    "success": False,
    "error": "Error message description"
}
```

Common errors:
- Connection errors: "Failed to connect to Weaviate"
- Not found: "Conversation {id} not found"
- Validation errors: "Invalid parameter: {details}"

## Performance

- **Vectorization**: ~50-100ms per text on RTX 4070 GPU
- **Search latency**: <100ms for near-vector queries
- **Batch operations**: Use embedder.embed_batch() for efficiency

## Next Steps

**Phase 5: Backend Integration** (Pending)
- Update Flask routes to use Weaviate Memory tools
- Replace ChromaDB calls with new MCP tool calls
- Connect flask-app frontend to new backend

## Module Structure

```
memory/
├── core/
│   ├── __init__.py        # GPU embedder initialization
│   └── config.py          # Weaviate connection config
├── mcp/
│   ├── __init__.py        # Tool exports
│   ├── thought_tools.py   # Thought handlers
│   ├── message_tools.py   # Message handlers
│   └── conversation_tools.py  # Conversation handlers
└── README_MCP_TOOLS.md    # This file
```

## Dependencies

- weaviate-client >= 4.0.0
- PyTorch 2.6.0+cu124
- transformers (for BAAI/bge-m3)
- pydantic (for input validation)
- FastMCP framework

## Related Documentation

- Weaviate Schema: `memory/schemas/` (Thought, Message, Conversation schemas)
- Migration Scripts: `memory/migration/` (ChromaDB → Weaviate migration)
- Library RAG README: `generations/library_rag/README.md`

---

**Last Updated**: 2025-01-08
**Status**: Phase 4 Complete ✓
**Next Phase**: Phase 5 - Backend Integration
