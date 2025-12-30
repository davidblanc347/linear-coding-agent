#!/bin/bash
# Library RAG - Type Safety & Documentation Enhancement
# Initialization script for development environment

set -e  # Exit on error

echo "=========================================="
echo "Library RAG - Development Environment Setup"
echo "=========================================="
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
python_version=$(python --version 2>&1)
echo "  Found: $python_version"
if ! python -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'" 2>/dev/null; then
    echo "  ERROR: Python 3.10 or higher is required"
    exit 1
fi
echo "  OK"
echo ""

# Create virtual environment if it doesn't exist
echo "[2/5] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python -m venv venv
    echo "  Created venv/"
else
    echo "  Virtual environment already exists"
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi
echo "  Activated virtual environment"
echo ""

# Install dependencies
echo "[3/5] Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
# Install type checking tools
pip install --quiet mypy types-Flask pydocstyle
echo "  Installed all dependencies"
echo ""

# Start Docker containers
echo "[4/5] Starting Weaviate with Docker Compose..."
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        docker compose up -d
        echo "  Weaviate is starting..."
        echo "  Waiting for Weaviate to be ready..."
        sleep 5

        # Check if Weaviate is ready
        max_attempts=30
        attempt=0
        while [ $attempt -lt $max_attempts ]; do
            if curl -s http://localhost:8080/v1/.well-known/ready > /dev/null 2>&1; then
                echo "  Weaviate is ready!"
                break
            fi
            attempt=$((attempt + 1))
            sleep 2
        done

        if [ $attempt -eq $max_attempts ]; then
            echo "  WARNING: Weaviate may not be ready yet. Check 'docker compose logs'"
        fi
    else
        echo "  WARNING: Docker Compose not found. Please install Docker Desktop."
        echo "  Weaviate will need to be started manually: docker compose up -d"
    fi
else
    echo "  WARNING: Docker not found. Please install Docker Desktop."
    echo "  Weaviate will need to be started manually: docker compose up -d"
fi
echo ""

# Create Weaviate schema if needed
echo "[5/5] Initializing Weaviate schema..."
python -c "
import weaviate
try:
    client = weaviate.connect_to_local()
    collections = client.collections.list_all()
    if 'Chunk' in collections:
        print('  Schema already exists')
    else:
        print('  Creating schema...')
        import schema
        print('  Schema created successfully')
    client.close()
except Exception as e:
    print(f'  Note: Could not connect to Weaviate: {e}')
    print('  Run this script again after Weaviate is ready, or run: python schema.py')
" 2>/dev/null || echo "  Schema setup will be done on first Flask app run"
echo ""

# Print summary
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the Flask application:"
echo "  python flask_app.py"
echo ""
echo "The application will be available at:"
echo "  http://localhost:5000"
echo ""
echo "Useful commands:"
echo "  - Run type checks:    mypy --strict ."
echo "  - Run tests:          pytest tests/ -v"
echo "  - Check docstrings:   pydocstyle --convention=google ."
echo "  - View Weaviate:      http://localhost:8080/v1"
echo ""
echo "For development with Ollama (free LLM):"
echo "  1. Install Ollama: https://ollama.ai"
echo "  2. Pull model: ollama pull qwen2.5:7b"
echo "  3. Start Ollama: ollama serve"
echo ""
echo "For MCP Server (Claude Desktop integration):"
echo "  1. Run MCP server: python mcp_server.py"
echo "  2. Configure Claude Desktop (see MCP_README.md)"
echo "  3. Use parse_pdf and search tools from Claude"
echo ""
