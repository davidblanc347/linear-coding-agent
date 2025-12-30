"""Mistral API Client Management.

This module provides utilities for managing the Mistral API client,
including API key retrieval and OCR cost estimation. It serves as the
foundation for all Mistral API interactions in the Library RAG pipeline.

Key Features:
    - Automatic API key discovery from multiple sources
    - Client instantiation with proper authentication
    - OCR cost estimation for budget planning

API Key Priority:
    The module searches for the Mistral API key in this order:
    1. Explicit argument passed to functions
    2. MISTRAL_API_KEY environment variable
    3. .env file in the project root

Cost Estimation:
    Mistral OCR pricing (as of 2024):
    - Standard OCR: ~1 EUR per 1000 pages (0.001 EUR/page)
    - OCR with annotations: ~3 EUR per 1000 pages (0.003 EUR/page)

Example:
    Basic client creation and usage::

        from utils.mistral_client import create_client, estimate_ocr_cost

        # Create authenticated client
        client = create_client()

        # Estimate cost for a 100-page document
        cost = estimate_ocr_cost(100, use_annotations=False)
        print(f"Estimated cost: {cost:.2f} EUR")  # Output: Estimated cost: 0.10 EUR

    Using explicit API key::

        client = create_client(api_key="your-api-key-here")

See Also:
    - :mod:`utils.ocr_processor`: OCR execution functions using this client
    - :mod:`utils.pdf_uploader`: PDF upload utilities for OCR processing

Note:
    Ensure MISTRAL_API_KEY is set before using this module in production.
    The API key can be obtained from the Mistral AI platform dashboard.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from mistralai import Mistral


def get_api_key(api_key: Optional[str] = None) -> str:
    """Retrieve the Mistral API key from available sources.

    Searches for the API key in the following priority order:
    1. Explicit argument passed to this function
    2. MISTRAL_API_KEY environment variable
    3. .env file in the project root

    Args:
        api_key: Optional API key to use directly. If provided and non-empty,
            this value is used without checking other sources.

    Returns:
        The Mistral API key as a string.

    Raises:
        RuntimeError: If no API key is found in any of the checked sources.

    Example:
        >>> # Using environment variable
        >>> key = get_api_key()
        >>> len(key) > 0
        True

        >>> # Using explicit key
        >>> key = get_api_key("my-api-key")
        >>> key
        'my-api-key'
    """
    # 1. Argument fourni
    if api_key and api_key.strip():
        return api_key.strip()

    # 2. Variable d environnement
    env_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if env_key:
        return env_key

    # 3. Fichier .env
    load_dotenv()
    env_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if env_key:
        return env_key

    raise RuntimeError(
        "MISTRAL_API_KEY manquante. "
        "Definissez la variable d environnement ou creez un fichier .env"
    )


def create_client(api_key: Optional[str] = None) -> Mistral:
    """Create and return an authenticated Mistral client.

    This is the primary entry point for obtaining a Mistral client instance.
    The client can be used for OCR operations, chat completions, and other
    Mistral API features.

    Args:
        api_key: Optional API key. If not provided, the key is automatically
            retrieved from environment variables or .env file.

    Returns:
        An authenticated Mistral client instance ready for API calls.

    Raises:
        RuntimeError: If no API key is found (propagated from get_api_key).

    Example:
        >>> client = create_client()
        >>> # Client is now ready for OCR or other operations
        >>> response = client.ocr.process(...)  # doctest: +SKIP
    """
    key = get_api_key(api_key)
    return Mistral(api_key=key)


def estimate_ocr_cost(nb_pages: int, use_annotations: bool = False) -> float:
    """Estimate the cost of OCR processing for a document.

    Calculates the expected cost based on Mistral OCR pricing model.
    This is useful for budget planning before processing large document
    collections.

    Pricing Model:
        - Standard OCR: ~1 EUR per 1000 pages (0.001 EUR/page)
        - OCR with annotations: ~3 EUR per 1000 pages (0.003 EUR/page)

    The annotation mode is approximately 3x more expensive but provides
    additional structural information useful for TOC extraction.

    Args:
        nb_pages: Number of pages in the document to process.
        use_annotations: If True, uses the higher annotation pricing.
            Annotations provide bounding box and structural data.

    Returns:
        Estimated cost in euros as a float.

    Example:
        >>> # Standard OCR for 100 pages
        >>> estimate_ocr_cost(100)
        0.1

        >>> # OCR with annotations for 100 pages
        >>> estimate_ocr_cost(100, use_annotations=True)
        0.3

        >>> # Large document collection
        >>> estimate_ocr_cost(10000)
        10.0
    """
    if use_annotations:
        return nb_pages * 0.003  # 3 EUR / 1000 pages
    else:
        return nb_pages * 0.001  # 1 EUR / 1000 pages
