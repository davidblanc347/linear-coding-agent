"""
Unit tests for MCP parsing tools.

Tests the parse_pdf tool handler with mocked dependencies to ensure:
- Local file processing works correctly
- URL-based PDF downloads work correctly
- Error handling is comprehensive
- Fixed parameters are used correctly
- Cost tracking is accurate

Uses asyncio for async test support.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_tools.parsing_tools import (
    FIXED_LLM_MODEL,
    FIXED_LLM_PROVIDER,
    FIXED_USE_LLM,
    FIXED_USE_OCR_ANNOTATIONS,
    FIXED_USE_SEMANTIC_CHUNKING,
    download_pdf,
    extract_filename_from_url,
    is_url,
    parse_pdf_handler,
)
from mcp_tools.schemas import ParsePdfInput, ParsePdfOutput


# =============================================================================
# Test is_url Helper Function
# =============================================================================


class TestIsUrl:
    """Tests for the is_url helper function."""

    def test_https_url(self) -> None:
        """Test that HTTPS URLs are recognized."""
        assert is_url("https://example.com/document.pdf") is True

    def test_http_url(self) -> None:
        """Test that HTTP URLs are recognized."""
        assert is_url("http://example.com/document.pdf") is True

    def test_local_path_unix(self) -> None:
        """Test that Unix local paths are not recognized as URLs."""
        assert is_url("/path/to/document.pdf") is False

    def test_local_path_windows(self) -> None:
        """Test that Windows local paths are not recognized as URLs."""
        assert is_url("C:\\Documents\\document.pdf") is False

    def test_relative_path(self) -> None:
        """Test that relative paths are not recognized as URLs."""
        assert is_url("./documents/document.pdf") is False

    def test_ftp_url_not_supported(self) -> None:
        """Test that FTP URLs are not recognized (only HTTP/HTTPS supported)."""
        assert is_url("ftp://example.com/document.pdf") is False

    def test_empty_string(self) -> None:
        """Test that empty strings are not recognized as URLs."""
        assert is_url("") is False


# =============================================================================
# Test extract_filename_from_url Helper Function
# =============================================================================


class TestExtractFilenameFromUrl:
    """Tests for the extract_filename_from_url helper function."""

    def test_url_with_pdf_filename(self) -> None:
        """Test extraction when URL has a .pdf filename."""
        result = extract_filename_from_url("https://example.com/docs/aristotle.pdf")
        assert result == "aristotle.pdf"

    def test_url_with_filename_no_extension(self) -> None:
        """Test extraction when URL has a filename without extension."""
        result = extract_filename_from_url("https://example.com/docs/aristotle")
        assert result == "aristotle.pdf"

    def test_url_without_path(self) -> None:
        """Test extraction when URL has no path."""
        result = extract_filename_from_url("https://example.com/")
        assert result == "downloaded.pdf"

    def test_url_with_api_endpoint(self) -> None:
        """Test extraction when URL is an API endpoint."""
        result = extract_filename_from_url("https://api.example.com/download")
        assert result == "download.pdf"

    def test_url_with_query_params(self) -> None:
        """Test extraction when URL has query parameters."""
        result = extract_filename_from_url(
            "https://example.com/docs/kant.pdf?token=abc"
        )
        assert result == "kant.pdf"


# =============================================================================
# Test download_pdf Function
# =============================================================================


class TestDownloadPdf:
    """Tests for the download_pdf async function."""

    def test_successful_download(self) -> None:
        """Test successful PDF download from URL."""

        async def run_test() -> None:
            mock_response = MagicMock()
            mock_response.content = b"%PDF-1.4 test content"
            mock_response.headers = {"content-type": "application/pdf"}
            mock_response.raise_for_status = MagicMock()

            with patch(
                "mcp_tools.parsing_tools.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await download_pdf("https://example.com/document.pdf")

                assert result == b"%PDF-1.4 test content"
                mock_client.get.assert_called_once_with(
                    "https://example.com/document.pdf"
                )

        asyncio.run(run_test())

    def test_download_with_non_pdf_content_type(self) -> None:
        """Test download proceeds with warning when content-type is not PDF."""

        async def run_test() -> None:
            mock_response = MagicMock()
            mock_response.content = b"%PDF-1.4 test content"
            mock_response.headers = {"content-type": "application/octet-stream"}
            mock_response.raise_for_status = MagicMock()

            with patch(
                "mcp_tools.parsing_tools.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

                # Should still succeed, just logs a warning
                result = await download_pdf("https://example.com/document.pdf")
                assert result == b"%PDF-1.4 test content"

        asyncio.run(run_test())

    def test_download_http_error(self) -> None:
        """Test that HTTP errors are propagated."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "Not Found",
                        request=MagicMock(),
                        response=MagicMock(status_code=404),
                    )
                )
                mock_client_class.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(httpx.HTTPStatusError):
                    await download_pdf("https://example.com/nonexistent.pdf")

        asyncio.run(run_test())


# =============================================================================
# Test parse_pdf_handler - Local Files
# =============================================================================


class TestParsePdfHandlerLocalFile:
    """Tests for parse_pdf_handler with local file paths."""

    def test_successful_local_file_processing(
        self,
        temp_pdf_file: Path,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test successful processing of a local PDF file."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = successful_pipeline_result

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.success is True
                assert result.document_name == "test-document"
                assert result.pages == 10
                assert result.chunks_count == 25
                assert result.cost_ocr == 0.03
                assert result.cost_llm == 0.05
                assert result.cost_total == 0.08
                assert result.metadata["title"] == "Test Document Title"
                assert result.error is None

        asyncio.run(run_test())

    def test_local_file_uses_fixed_parameters(
        self,
        temp_pdf_file: Path,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test that local file processing uses the fixed optimal parameters."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = successful_pipeline_result

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                await parse_pdf_handler(input_data)

                # Verify fixed parameters are passed
                mock_process_pdf.assert_called_once()
                call_kwargs = mock_process_pdf.call_args.kwargs

                assert call_kwargs["use_llm"] == FIXED_USE_LLM
                assert call_kwargs["llm_provider"] == FIXED_LLM_PROVIDER
                assert call_kwargs["llm_model"] == FIXED_LLM_MODEL
                assert call_kwargs["use_semantic_chunking"] == FIXED_USE_SEMANTIC_CHUNKING
                assert call_kwargs["use_ocr_annotations"] == FIXED_USE_OCR_ANNOTATIONS

        asyncio.run(run_test())

    def test_file_not_found_error(self) -> None:
        """Test error handling when local file does not exist."""

        async def run_test() -> None:
            input_data = ParsePdfInput(pdf_path="/nonexistent/path/document.pdf")
            result = await parse_pdf_handler(input_data)

            assert result.success is False
            assert "not found" in result.error.lower()
            assert result.pages == 0
            assert result.chunks_count == 0

        asyncio.run(run_test())

    def test_pipeline_failure(
        self,
        temp_pdf_file: Path,
        failed_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test handling when the pipeline returns a failure."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = failed_pipeline_result

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.success is False
                assert "OCR processing failed" in result.error
                assert result.pages == 0

        asyncio.run(run_test())

    def test_pipeline_exception(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test handling when the pipeline raises an exception."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.side_effect = RuntimeError("Unexpected error")

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.success is False
                assert "Processing error" in result.error
                assert "Unexpected error" in result.error

        asyncio.run(run_test())


# =============================================================================
# Test parse_pdf_handler - URL Downloads
# =============================================================================


class TestParsePdfHandlerUrl:
    """Tests for parse_pdf_handler with URL inputs."""

    def test_successful_url_processing(
        self,
        sample_pdf_bytes: bytes,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test successful processing of a PDF from URL."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock
            ) as mock_download:
                with patch(
                    "mcp_tools.parsing_tools.process_pdf_bytes"
                ) as mock_process:
                    mock_download.return_value = sample_pdf_bytes
                    mock_process.return_value = successful_pipeline_result

                    input_data = ParsePdfInput(
                        pdf_path="https://example.com/philosophy/kant.pdf"
                    )
                    result = await parse_pdf_handler(input_data)

                    assert result.success is True
                    assert result.document_name == "test-document"
                    mock_download.assert_called_once_with(
                        "https://example.com/philosophy/kant.pdf"
                    )

        asyncio.run(run_test())

    def test_url_uses_extracted_filename(
        self,
        sample_pdf_bytes: bytes,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test that filename is extracted from URL for processing."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock
            ) as mock_download:
                with patch(
                    "mcp_tools.parsing_tools.process_pdf_bytes"
                ) as mock_process:
                    mock_download.return_value = sample_pdf_bytes
                    mock_process.return_value = successful_pipeline_result

                    input_data = ParsePdfInput(
                        pdf_path="https://example.com/docs/aristotle-metaphysics.pdf"
                    )
                    await parse_pdf_handler(input_data)

                    # Verify filename was extracted and passed
                    mock_process.assert_called_once()
                    call_kwargs = mock_process.call_args.kwargs
                    assert call_kwargs["filename"] == "aristotle-metaphysics.pdf"

        asyncio.run(run_test())

    def test_url_uses_fixed_parameters(
        self,
        sample_pdf_bytes: bytes,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test that URL processing uses the fixed optimal parameters."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock
            ) as mock_download:
                with patch(
                    "mcp_tools.parsing_tools.process_pdf_bytes"
                ) as mock_process:
                    mock_download.return_value = sample_pdf_bytes
                    mock_process.return_value = successful_pipeline_result

                    input_data = ParsePdfInput(
                        pdf_path="https://example.com/document.pdf"
                    )
                    await parse_pdf_handler(input_data)

                    call_kwargs = mock_process.call_args.kwargs
                    assert call_kwargs["llm_provider"] == FIXED_LLM_PROVIDER
                    assert call_kwargs["llm_model"] == FIXED_LLM_MODEL
                    assert (
                        call_kwargs["use_semantic_chunking"]
                        == FIXED_USE_SEMANTIC_CHUNKING
                    )
                    assert (
                        call_kwargs["use_ocr_annotations"] == FIXED_USE_OCR_ANNOTATIONS
                    )

        asyncio.run(run_test())

    def test_url_download_http_error(self) -> None:
        """Test error handling when URL download fails with HTTP error."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock
            ) as mock_download:
                mock_download.side_effect = httpx.HTTPStatusError(
                    "Not Found",
                    request=MagicMock(),
                    response=MagicMock(status_code=404),
                )

                input_data = ParsePdfInput(
                    pdf_path="https://example.com/nonexistent.pdf"
                )
                result = await parse_pdf_handler(input_data)

                assert result.success is False
                assert "Failed to download PDF" in result.error

        asyncio.run(run_test())

    def test_url_download_network_error(self) -> None:
        """Test error handling when URL download fails with network error."""

        async def run_test() -> None:
            with patch(
                "mcp_tools.parsing_tools.download_pdf", new_callable=AsyncMock
            ) as mock_download:
                mock_download.side_effect = httpx.ConnectError("Connection refused")

                input_data = ParsePdfInput(
                    pdf_path="https://example.com/document.pdf"
                )
                result = await parse_pdf_handler(input_data)

                assert result.success is False
                assert "Failed to download PDF" in result.error

        asyncio.run(run_test())


# =============================================================================
# Test Cost Tracking
# =============================================================================


class TestCostTracking:
    """Tests for cost tracking in parse_pdf output."""

    def test_costs_are_tracked_correctly(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test that OCR and LLM costs are correctly tracked."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = {
                    "success": True,
                    "document_name": "test-doc",
                    "source_id": "test-doc",
                    "pages": 50,
                    "chunks_count": 100,
                    "cost_ocr": 0.15,  # 50 pages * 0.003€
                    "cost_llm": 0.25,
                    "cost_total": 0.40,
                    "output_dir": Path("output/test-doc"),
                    "metadata": {},
                    "error": None,
                }

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.cost_ocr == 0.15
                assert result.cost_llm == 0.25
                assert result.cost_total == 0.40

        asyncio.run(run_test())

    def test_cost_total_calculated_when_missing(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test that cost_total is calculated if not provided."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = {
                    "success": True,
                    "document_name": "test-doc",
                    "source_id": "test-doc",
                    "pages": 10,
                    "chunks_count": 20,
                    "cost_ocr": 0.03,
                    "cost_llm": 0.05,
                    # cost_total intentionally missing
                    "output_dir": Path("output/test-doc"),
                    "metadata": {},
                    "error": None,
                }

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.cost_total == 0.08  # 0.03 + 0.05

        asyncio.run(run_test())

    def test_zero_costs_on_failure(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test that costs are zero when processing fails early."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.side_effect = RuntimeError("Early failure")

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.success is False
                assert result.cost_ocr == 0.0
                assert result.cost_llm == 0.0
                assert result.cost_total == 0.0

        asyncio.run(run_test())


# =============================================================================
# Test Metadata Handling
# =============================================================================


class TestMetadataHandling:
    """Tests for metadata extraction and handling."""

    def test_metadata_extracted_correctly(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test that metadata is correctly passed through."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = {
                    "success": True,
                    "document_name": "platon-menon",
                    "source_id": "platon-menon",
                    "pages": 80,
                    "chunks_count": 150,
                    "cost_ocr": 0.24,
                    "cost_llm": 0.30,
                    "cost_total": 0.54,
                    "output_dir": Path("output/platon-menon"),
                    "metadata": {
                        "title": "Ménon",
                        "author": "Platon",
                        "language": "fr",
                        "year": -380,
                        "genre": "dialogue",
                    },
                    "error": None,
                }

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.metadata["title"] == "Ménon"
                assert result.metadata["author"] == "Platon"
                assert result.metadata["language"] == "fr"
                assert result.metadata["year"] == -380
                assert result.metadata["genre"] == "dialogue"

        asyncio.run(run_test())

    def test_empty_metadata_handled(
        self,
        temp_pdf_file: Path,
    ) -> None:
        """Test that empty/None metadata is handled gracefully."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = {
                    "success": True,
                    "document_name": "test-doc",
                    "source_id": "test-doc",
                    "pages": 10,
                    "chunks_count": 20,
                    "cost_ocr": 0.03,
                    "cost_llm": 0.05,
                    "cost_total": 0.08,
                    "output_dir": Path("output/test-doc"),
                    "metadata": None,  # Explicitly None
                    "error": None,
                }

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                assert result.metadata == {}

        asyncio.run(run_test())


# =============================================================================
# Test Output Schema Validation
# =============================================================================


class TestOutputSchemaValidation:
    """Tests for ParsePdfOutput schema compliance."""

    def test_output_is_valid_schema(
        self,
        temp_pdf_file: Path,
        successful_pipeline_result: Dict[str, Any],
    ) -> None:
        """Test that output conforms to ParsePdfOutput schema."""

        async def run_test() -> None:
            with patch("mcp_tools.parsing_tools.process_pdf") as mock_process_pdf:
                mock_process_pdf.return_value = successful_pipeline_result

                input_data = ParsePdfInput(pdf_path=str(temp_pdf_file))
                result = await parse_pdf_handler(input_data)

                # Verify it's the correct type
                assert isinstance(result, ParsePdfOutput)

                # Verify all required fields are present
                assert hasattr(result, "success")
                assert hasattr(result, "document_name")
                assert hasattr(result, "source_id")
                assert hasattr(result, "pages")
                assert hasattr(result, "chunks_count")
                assert hasattr(result, "cost_ocr")
                assert hasattr(result, "cost_llm")
                assert hasattr(result, "cost_total")
                assert hasattr(result, "output_dir")
                assert hasattr(result, "metadata")
                assert hasattr(result, "error")

        asyncio.run(run_test())

    def test_error_output_is_valid_schema(self) -> None:
        """Test that error output conforms to ParsePdfOutput schema."""

        async def run_test() -> None:
            input_data = ParsePdfInput(pdf_path="/nonexistent/file.pdf")
            result = await parse_pdf_handler(input_data)

            assert isinstance(result, ParsePdfOutput)
            assert result.success is False
            assert result.error is not None
            assert isinstance(result.error, str)

        asyncio.run(run_test())
