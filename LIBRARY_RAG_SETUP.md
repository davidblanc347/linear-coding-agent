# Library RAG MCP Setup Guide

## Quick Setup

To enable the Library RAG MCP server (document search with Weaviate), you need to configure the following in your `.env` file:

### Required Environment Variables

```bash
# Library RAG MCP Configuration
LIBRARY_RAG_ENABLED=true
MCP_LIBRARY_RAG_SERVER_PATH=C:/GitHub/linear_coding_library_rag/generations/library_rag/mcp_server.py
LIBRARY_RAG_PYTHON_COMMAND=python
LIBRARY_RAG_CONNECTION_TIMEOUT=10000
LIBRARY_RAG_AUTO_RECONNECT=true
LIBRARY_RAG_MAX_RETRIES=3

# Weaviate Configuration
WEAVIATE_URL=http://localhost:8080

# REQUIRED: Mistral API Key (for OCR functionality)
MISTRAL_API_KEY=your_mistral_api_key_here
```

### Why MISTRAL_API_KEY is Required

The Library RAG MCP server uses Mistral API for:
- **OCR with annotations**: Extracting text from PDF images with layout annotations
- **LLM processing**: Metadata extraction, table of contents generation, semantic chunking

Without this key, the MCP server **will fail to start** and the backend connection will timeout with error: `MCP error -32001: Request timed out`.

### Getting Your Mistral API Key

1. Go to https://console.mistral.ai/
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key and add it to your `.env` file

### Troubleshooting

**Issue**: Library RAG shows `"connected": false` in status endpoint

**Solution**:
1. Check that `MISTRAL_API_KEY` is uncommented in `.env`
2. Verify the key is valid
3. Restart the backend server: `npm run dev`

**Issue**: Connection timeout error

**Cause**: The MCP server subprocess cannot start without the Mistral API key

**Fix**: Add the key to `.env` and restart

### Verifying Connection

Check the connection status:

```bash
curl http://localhost:5175/api/library-rag/status | python -m json.tool
```

Expected response when connected:
```json
{
  "success": true,
  "data": {
    "connected": true,
    "message": "Library RAG MCP server is connected and ready",
    "tools": [...],
    "error": null
  }
}
```

### Available Tools

Once connected, you'll have access to:

1. **upload_document** - Upload and index PDF documents with full pipeline (OCR, metadata, chunking, Weaviate ingestion)
2. **search_library** - Semantic search over document chunks
3. **hybrid_search** - Search summaries and high-level content
4. **list_collections** - List all indexed documents
5. **get_document** - Retrieve document metadata
6. **filter_search** - Filter by author, work, or language
7. **extract_text_from_image** - OCR from image URLs

### Related Configuration

Make sure Weaviate Docker is running:

```bash
cd C:\GitHub\linear_coding_library_rag\generations\library_rag
docker-compose up -d
```

Check Weaviate status:

```bash
curl http://localhost:8080/v1/meta
```

## Changelog

**2025-12-26**: Fixed MCP connection issue by adding MISTRAL_API_KEY requirement to documentation. The key must be present in `.env` for the MCP server to start successfully.
