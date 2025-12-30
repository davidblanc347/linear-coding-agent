"""OCR Processing via Mistral API.

This module provides functions for executing OCR (Optical Character Recognition)
on PDF documents using the Mistral API. It handles both standard OCR and advanced
OCR with structured annotations for better document understanding.

Key Features:
    - Standard OCR for text extraction with optional image embedding
    - Advanced OCR with document and bounding box annotations
    - Response serialization for JSON storage and further processing
    - Support for page-by-page processing

OCR Modes:
    1. **Standard OCR** (run_ocr):
       - Extracts text and optionally images
       - Cost: ~1 EUR per 1000 pages (0.001 EUR/page)
       - Best for: Simple text extraction, content indexing

    2. **OCR with Annotations** (run_ocr_with_annotations):
       - Extracts text with structural metadata (bounding boxes, document structure)
       - Cost: ~3 EUR per 1000 pages (0.003 EUR/page)
       - Best for: TOC extraction, layout analysis, structured documents
       - Document annotations limited to 8 pages max
       - Bounding box annotations have no page limit

Response Structure:
    The OCR response contains:
    - pages: List of page objects with text content
    - images: Optional base64-encoded images (if include_images=True)
    - annotations: Structural metadata (if using annotation mode)

Example:
    Basic OCR processing::

        from utils.mistral_client import create_client
        from utils.ocr_processor import run_ocr, serialize_ocr_response

        # Create client and read PDF
        client = create_client()
        with open("document.pdf", "rb") as f:
            pdf_bytes = f.read()

        # Run OCR
        response = run_ocr(client, pdf_bytes, "document.pdf")

        # Serialize for storage
        ocr_dict = serialize_ocr_response(response)
        print(f"Extracted {len(ocr_dict['pages'])} pages")

Cost Considerations:
    - Always estimate costs before batch processing with estimate_ocr_cost()
    - Use pages parameter to limit processing when full document is not needed
    - Annotation mode is 3x more expensive - use only when structure is needed
    - Cache OCR results to avoid reprocessing (saved in output/<doc>/<doc>.json)

See Also:
    - utils.mistral_client: Client creation and cost estimation
    - utils.pdf_uploader: PDF upload utilities
    - utils.pdf_pipeline: Full pipeline orchestration

Note:
    OCR responses are Pydantic models from the Mistral SDK. Use
    serialize_ocr_response() to convert to dictionaries before JSON storage.
"""

import json
from typing import Any, Dict, List, Optional, Type

from mistralai import Mistral
from pydantic import BaseModel

from .pdf_uploader import upload_pdf
from .types import OCRResponse


def run_ocr(
    client: Mistral,
    file_bytes: bytes,
    filename: str,
    include_images: bool = True,
) -> Any:
    """Execute standard OCR on a PDF document via Mistral API.

    Uploads the PDF to Mistral servers and runs OCR to extract text content.
    Optionally includes base64-encoded images from the document.

    This is the most cost-effective OCR mode (~0.001 EUR/page) suitable for
    basic text extraction and content indexing.

    Args:
        client: Authenticated Mistral client instance created via
            utils.mistral_client.create_client().
        file_bytes: Binary content of the PDF file to process.
        filename: Original filename of the PDF (used for identification).
        include_images: If True, includes base64-encoded images from each page
            in the response. Set to False to reduce response size when images
            are not needed. Defaults to True.

    Returns:
        OCR response object from Mistral API (Pydantic model). Contains:
        - pages: List of page objects with extracted text
        - images: Base64 images if include_images=True

        Use serialize_ocr_response() to convert to a dictionary.

    Raises:
        RuntimeError: If the Mistral client is not properly authenticated.
        HTTPError: If the API request fails (network issues, rate limits).

    Example:
        >>> from utils.mistral_client import create_client
        >>> client = create_client()
        >>> with open("document.pdf", "rb") as f:
        ...     pdf_bytes = f.read()
        >>> response = run_ocr(client, pdf_bytes, "document.pdf")
        >>> # Access extracted text from first page
        >>> first_page_text = response.pages[0].markdown  # doctest: +SKIP

    Note:
        The PDF is first uploaded to Mistral servers via
        utils.pdf_uploader.upload_pdf(), then processed. The uploaded
        file is automatically cleaned up by Mistral after processing.
    """
    # Upload du document
    doc_url: str = upload_pdf(client, file_bytes, filename)

    # Appel OCR
    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": doc_url,
        },
        include_image_base64=include_images,
    )

    return response


def run_ocr_with_annotations(
    client: Mistral,
    file_bytes: bytes,
    filename: str,
    include_images: bool = True,
    document_annotation_format: Optional[Type[BaseModel]] = None,
    bbox_annotation_format: Optional[Type[BaseModel]] = None,
    pages: Optional[List[int]] = None,
) -> Any:
    """Execute OCR with structured annotations on a PDF document.

    This advanced OCR mode extracts text along with structural metadata
    defined by Pydantic schemas. Useful for extracting structured data
    like table of contents, form fields, or document hierarchy.

    Two annotation modes are available:
    - Document annotations: Extract document-level structure (limited to 8 pages)
    - Bounding box annotations: Extract element positions (no page limit)

    This mode is approximately 3x more expensive than standard OCR (~0.003 EUR/page).

    Args:
        client: Authenticated Mistral client instance created via
            utils.mistral_client.create_client().
        file_bytes: Binary content of the PDF file to process.
        filename: Original filename of the PDF (used for identification).
        include_images: If True, includes base64-encoded images from each page.
            Defaults to True.
        document_annotation_format: Optional Pydantic model defining the expected
            document-level annotation structure. The model is converted to JSON
            schema for the API. Limited to processing 8 pages maximum.
        bbox_annotation_format: Optional Pydantic model defining the expected
            bounding box annotation structure. No page limit applies.
        pages: Optional list of 0-indexed page numbers to process. If None,
            all pages are processed. Use this to limit costs and processing time.

    Returns:
        OCR response object with annotations from Mistral API. Contains:
        - pages: List of page objects with extracted text
        - annotations: Structured data matching the provided Pydantic schema
        - images: Base64 images if include_images=True

        Use serialize_ocr_response() to convert to a dictionary.

    Raises:
        RuntimeError: If the Mistral client is not properly authenticated.
        HTTPError: If the API request fails (network issues, rate limits).
        ValueError: If document_annotation_format is used with more than 8 pages.

    Example:
        Extract table of contents from first 8 pages::

            from pydantic import BaseModel
            from typing import List, Optional

            class TOCEntry(BaseModel):
                title: str
                page: int
                level: int
                children: Optional[List["TOCEntry"]] = None

            response = run_ocr_with_annotations(
                client,
                pdf_bytes,
                "book.pdf",
                document_annotation_format=TOCEntry,
                pages=[0, 1, 2, 3, 4, 5, 6, 7]
            )

            # Access annotations
            toc_data = response.annotations  # doctest: +SKIP

    Note:
        - Document annotations are more expensive but provide rich structure
        - For large documents, use pages parameter to limit processing
        - Consider caching results to avoid reprocessing costs
    """
    from mistralai.extra import response_format_from_pydantic_model
    
    # Upload du document
    doc_url: str = upload_pdf(client, file_bytes, filename)

    # Construire les arguments de l'appel OCR
    kwargs: Dict[str, Any] = {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": doc_url,
        },
        "include_image_base64": include_images,
    }
    
    # Ajouter les pages si spécifié
    if pages is not None:
        kwargs["pages"] = pages
    
    # Ajouter le format d'annotation document si fourni
    if document_annotation_format is not None:
        kwargs["document_annotation_format"] = response_format_from_pydantic_model(
            document_annotation_format
        )
    
    # Ajouter le format d'annotation bbox si fourni
    if bbox_annotation_format is not None:
        kwargs["bbox_annotation_format"] = response_format_from_pydantic_model(
            bbox_annotation_format
        )
    
    # Appel OCR avec annotations
    response = client.ocr.process(**kwargs)
    return response


def serialize_ocr_response(response: Any) -> Dict[str, Any]:
    """Convert an OCR response object to a JSON-serializable dictionary.

    The Mistral OCR API returns Pydantic model objects that need to be
    converted to plain dictionaries for JSON storage or further processing.
    This function handles various response formats from different versions
    of the Mistral SDK.

    Args:
        response: OCR response object from Mistral API. Can be any object
            that has model_dump(), dict(), or json() method.

    Returns:
        A dictionary representation of the OCR response, suitable for:
        - JSON serialization with json.dumps()
        - Storage in files (output/<doc>/<doc>.json)
        - Further processing in the pipeline

        The dictionary typically contains:
        - pages: List of page data with text content
        - images: Base64-encoded images (if requested)
        - model: OCR model used
        - usage: Token/page usage statistics

    Raises:
        TypeError: If the response object cannot be serialized using any
            of the supported methods (model_dump, dict, json).

    Example:
        >>> # Assuming response is from run_ocr()
        >>> ocr_dict = serialize_ocr_response(response)  # doctest: +SKIP
        >>> import json
        >>> with open("ocr_result.json", "w") as f:
        ...     json.dump(ocr_dict, f, indent=2)  # doctest: +SKIP

        >>> # Access page count
        >>> num_pages = len(ocr_dict["pages"])  # doctest: +SKIP

    Note:
        This function tries multiple serialization methods in order of
        preference:
        1. model_dump() - Pydantic v2 (preferred)
        2. dict() - Pydantic v1 compatibility
        3. json() - Fallback for other Pydantic models
    """
    if hasattr(response, "model_dump"):
        result: Dict[str, Any] = response.model_dump()
        return result

    if hasattr(response, "dict"):
        result = response.dict()
        return result

    if hasattr(response, "json"):
        result = json.loads(response.json())
        return result

    raise TypeError("Réponse OCR non sérialisable")


