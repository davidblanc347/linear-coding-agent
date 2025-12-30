"""
Unit tests for MCP configuration management.

Tests the MCPConfig class for proper loading, validation, and defaults.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from mcp_config import MCPConfig


class TestMCPConfigFromEnv:
    """Test MCPConfig.from_env() method."""

    def test_loads_with_required_key(self) -> None:
        """Test config loads when MISTRAL_API_KEY is present."""
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key-123"}, clear=True):
            config = MCPConfig.from_env()
            assert config.mistral_api_key == "test-key-123"

    def test_raises_without_api_key(self) -> None:
        """Test ValueError is raised when MISTRAL_API_KEY is missing."""
        with patch("mcp_config.load_dotenv"):  # Prevent reading .env file
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError) as exc_info:
                    MCPConfig.from_env()
                assert "MISTRAL_API_KEY" in str(exc_info.value)

    def test_default_values_applied(self) -> None:
        """Test all default values are applied correctly."""
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}, clear=True):
            config = MCPConfig.from_env()

            # Check all defaults
            assert config.ollama_base_url == "http://localhost:11434"
            assert config.structure_llm_model == "deepseek-r1:14b"
            assert config.structure_llm_temperature == 0.2
            assert config.default_llm_provider == "ollama"
            assert config.weaviate_host == "localhost"
            assert config.weaviate_port == 8080
            assert config.log_level == "INFO"
            assert config.output_dir == Path("output")

    def test_custom_values_loaded(self) -> None:
        """Test custom environment values are loaded correctly."""
        custom_env = {
            "MISTRAL_API_KEY": "custom-key",
            "OLLAMA_BASE_URL": "http://custom:1234",
            "STRUCTURE_LLM_MODEL": "custom-model",
            "STRUCTURE_LLM_TEMPERATURE": "0.7",
            "DEFAULT_LLM_PROVIDER": "mistral",
            "WEAVIATE_HOST": "weaviate.example.com",
            "WEAVIATE_PORT": "9999",
            "LOG_LEVEL": "DEBUG",
            "OUTPUT_DIR": "/custom/output",
        }
        with patch.dict(os.environ, custom_env, clear=True):
            config = MCPConfig.from_env()

            assert config.mistral_api_key == "custom-key"
            assert config.ollama_base_url == "http://custom:1234"
            assert config.structure_llm_model == "custom-model"
            assert config.structure_llm_temperature == 0.7
            assert config.default_llm_provider == "mistral"
            assert config.weaviate_host == "weaviate.example.com"
            assert config.weaviate_port == 9999
            assert config.log_level == "DEBUG"
            assert config.output_dir == Path("/custom/output")


class TestMCPConfigValidation:
    """Test MCPConfig.validate() method."""

    def test_valid_config_passes(self) -> None:
        """Test valid configuration passes validation."""
        config = MCPConfig(
            mistral_api_key="test-key",
            default_llm_provider="ollama",
            log_level="INFO",
            structure_llm_temperature=0.5,
        )
        # Should not raise
        config.validate()

    def test_invalid_llm_provider_fails(self) -> None:
        """Test invalid LLM provider raises ValueError."""
        config = MCPConfig(
            mistral_api_key="test-key",
            default_llm_provider="invalid",  # type: ignore
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid LLM provider" in str(exc_info.value)

    def test_invalid_log_level_fails(self) -> None:
        """Test invalid log level raises ValueError."""
        config = MCPConfig(
            mistral_api_key="test-key",
            log_level="INVALID",
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid log level" in str(exc_info.value)

    def test_invalid_temperature_fails(self) -> None:
        """Test temperature outside 0-2 range raises ValueError."""
        config = MCPConfig(
            mistral_api_key="test-key",
            structure_llm_temperature=2.5,
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid temperature" in str(exc_info.value)


class TestMCPConfigProperties:
    """Test MCPConfig properties."""

    def test_weaviate_url_property(self) -> None:
        """Test weaviate_url property returns correct URL."""
        config = MCPConfig(
            mistral_api_key="test-key",
            weaviate_host="my-host",
            weaviate_port=9090,
        )
        assert config.weaviate_url == "http://my-host:9090"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
