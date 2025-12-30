"""
Configuration management for Library RAG MCP Server.

Loads and validates environment variables for the MCP server.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


@dataclass
class MCPConfig:
    """
    Configuration for Library RAG MCP Server.

    Attributes:
        mistral_api_key: API key for Mistral OCR and LLM services.
        ollama_base_url: Base URL for Ollama local LLM server.
        structure_llm_model: Model name for LLM processing.
        structure_llm_temperature: Temperature for LLM generation.
        weaviate_host: Weaviate server hostname.
        weaviate_port: Weaviate server port.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        default_llm_provider: Default LLM provider ("ollama" or "mistral").
        output_dir: Base directory for processed files.
    """

    # Required
    mistral_api_key: str

    # LLM Configuration
    ollama_base_url: str = "http://localhost:11434"
    structure_llm_model: str = "deepseek-r1:14b"
    structure_llm_temperature: float = 0.2
    default_llm_provider: Literal["ollama", "mistral"] = "ollama"

    # Weaviate Configuration
    weaviate_host: str = "localhost"
    weaviate_port: int = 8080

    # Logging
    log_level: str = "INFO"

    # File System
    output_dir: Path = Path("output")

    @classmethod
    def from_env(cls) -> "MCPConfig":
        """
        Load configuration from environment variables.

        Returns:
            MCPConfig instance populated from .env file.

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Load .env file
        load_dotenv()

        # Required variables
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        if not mistral_api_key:
            raise ValueError(
                "MISTRAL_API_KEY environment variable is required. "
                "Please set it in your .env file."
            )

        # Optional variables with defaults
        return cls(
            mistral_api_key=mistral_api_key,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            structure_llm_model=os.getenv("STRUCTURE_LLM_MODEL", "deepseek-r1:14b"),
            structure_llm_temperature=float(
                os.getenv("STRUCTURE_LLM_TEMPERATURE", "0.2")
            ),
            default_llm_provider=os.getenv("DEFAULT_LLM_PROVIDER", "ollama"),  # type: ignore
            weaviate_host=os.getenv("WEAVIATE_HOST", "localhost"),
            weaviate_port=int(os.getenv("WEAVIATE_PORT", "8080")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        )

    @property
    def weaviate_url(self) -> str:
        """Get full Weaviate URL."""
        return f"http://{self.weaviate_host}:{self.weaviate_port}"

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If configuration is invalid.
        """
        # Validate LLM provider
        if self.default_llm_provider not in ("ollama", "mistral"):
            raise ValueError(
                f"Invalid LLM provider: {self.default_llm_provider}. "
                "Must be 'ollama' or 'mistral'."
            )

        # Validate log level
        valid_log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log level: {self.log_level}. "
                f"Must be one of {valid_log_levels}."
            )

        # Validate temperature
        if not 0.0 <= self.structure_llm_temperature <= 2.0:
            raise ValueError(
                f"Invalid temperature: {self.structure_llm_temperature}. "
                "Must be between 0.0 and 2.0."
            )

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
