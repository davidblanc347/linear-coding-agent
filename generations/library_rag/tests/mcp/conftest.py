"""
Pytest fixtures for MCP server tests.

Provides common fixtures for mocking dependencies and test data.
"""

import os
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_config import MCPConfig


@pytest.fixture
def mock_env_with_api_key() -> Generator[Dict[str, str], None, None]:
    """
    Provide environment with MISTRAL_API_KEY set.

    Yields:
        Dictionary of environment variables.
    """
    env = {"MISTRAL_API_KEY": "test-api-key-12345"}
    with patch.dict(os.environ, env, clear=True):
        yield env


@pytest.fixture
def valid_config() -> MCPConfig:
    """
    Provide a valid MCPConfig instance for testing.

    Returns:
        MCPConfig with valid test values.
    """
    return MCPConfig(
        mistral_api_key="test-api-key",
        ollama_base_url="http://localhost:11434",
        structure_llm_model="test-model",
        structure_llm_temperature=0.2,
        default_llm_provider="ollama",
        weaviate_host="localhost",
        weaviate_port=8080,
        log_level="INFO",
        output_dir=Path("test_output"),
    )


@pytest.fixture
def mock_weaviate_client() -> Generator[MagicMock, None, None]:
    """
    Provide a mocked Weaviate client.

    Yields:
        MagicMock configured as a Weaviate client.
    """
    with patch("weaviate.connect_to_local") as mock_connect:
        mock_client = MagicMock()
        mock_connect.return_value = mock_client
        yield mock_client


# =============================================================================
# Parsing Tools Fixtures
# =============================================================================


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """
    Provide minimal valid PDF bytes for testing.

    Returns:
        Bytes representing a minimal valid PDF file.
    """
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
193
%%EOF"""


@pytest.fixture
def successful_pipeline_result() -> Dict[str, Any]:
    """
    Provide a successful pipeline result for mocking.

    Returns:
        Dictionary mimicking a successful process_pdf result.
    """
    return {
        "success": True,
        "document_name": "test-document",
        "source_id": "test-document",
        "pages": 10,
        "chunks_count": 25,
        "cost_ocr": 0.03,
        "cost_llm": 0.05,
        "cost_total": 0.08,
        "output_dir": Path("output/test-document"),
        "metadata": {
            "title": "Test Document Title",
            "author": "Test Author",
            "language": "en",
            "year": 2023,
        },
        "error": None,
    }


@pytest.fixture
def failed_pipeline_result() -> Dict[str, Any]:
    """
    Provide a failed pipeline result for mocking.

    Returns:
        Dictionary mimicking a failed process_pdf result.
    """
    return {
        "success": False,
        "document_name": "failed-document",
        "source_id": "failed-document",
        "pages": 0,
        "chunks_count": 0,
        "cost_ocr": 0.0,
        "cost_llm": 0.0,
        "cost_total": 0.0,
        "output_dir": "",
        "metadata": {},
        "error": "OCR processing failed: Invalid PDF structure",
    }


@pytest.fixture
def mock_process_pdf() -> Generator[MagicMock, None, None]:
    """
    Provide a mocked process_pdf function.

    Yields:
        MagicMock for utils.pdf_pipeline.process_pdf.
    """
    with patch("mcp_tools.parsing_tools.process_pdf") as mock:
        yield mock


@pytest.fixture
def mock_process_pdf_bytes() -> Generator[MagicMock, None, None]:
    """
    Provide a mocked process_pdf_bytes function.

    Yields:
        MagicMock for utils.pdf_pipeline.process_pdf_bytes.
    """
    with patch("mcp_tools.parsing_tools.process_pdf_bytes") as mock:
        yield mock


@pytest.fixture
def mock_download_pdf() -> Generator[AsyncMock, None, None]:
    """
    Provide a mocked download_pdf function.

    Yields:
        AsyncMock for mcp_tools.parsing_tools.download_pdf.
    """
    with patch("mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def temp_pdf_file(tmp_path: Path, sample_pdf_bytes: bytes) -> Path:
    """
    Create a temporary PDF file for testing.

    Args:
        tmp_path: Pytest tmp_path fixture.
        sample_pdf_bytes: Sample PDF content.

    Returns:
        Path to the temporary PDF file.
    """
    pdf_path = tmp_path / "test_document.pdf"
    pdf_path.write_bytes(sample_pdf_bytes)
    return pdf_path
