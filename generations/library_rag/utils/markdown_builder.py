"""Markdown document builder from OCR API responses.

This module transforms Mistral OCR API responses into structured Markdown text.
It handles text extraction, page marker insertion, and image processing
(either base64 embedding or disk-based storage with relative path references).

The builder is a core component of the PDF processing pipeline, sitting between
OCR extraction and hierarchical parsing.

Pipeline Position:
    PDF → OCR (mistral_client) → **Markdown Builder** → Hierarchy Parser → Chunks

Features:
    - Page markers: Inserts HTML comments (<!-- Page N -->) for traceability
    - Image handling: Supports both inline base64 and external file references
    - Type safety: Uses Protocol-based typing for OCR response structures

Workflow:
    1. Iterate through pages in the OCR response
    2. Extract Markdown content from each page
    3. Process images (embed as base64 or save via ImageWriter callback)
    4. Assemble the complete Markdown document

Image Handling Modes:
    1. **No images**: Set embed_images=False and image_writer=None
    2. **Inline base64**: Set embed_images=True (large file size)
    3. **External files**: Provide image_writer callback (recommended)

Example:
    >>> from pathlib import Path
    >>> from utils.image_extractor import create_image_writer
    >>>
    >>> # Create image writer for output directory
    >>> writer = create_image_writer(Path("output/my_doc/images"))
    >>>
    >>> # Build markdown with external image references
    >>> markdown = build_markdown(
    ...     ocr_response,
    ...     embed_images=False,
    ...     image_writer=writer
    ... )
    >>> print(markdown[:100])
    <!-- Page 1 -->
    # Document Title
    ...

Note:
    - Page indices are 1-based for human readability
    - The OCR response must follow the Mistral API structure
    - Empty pages produce only the page marker comment

See Also:
    - utils.mistral_client: OCR API client for obtaining responses
    - utils.image_extractor: Image writer factory and extraction
    - utils.hierarchy_parser: Next step in pipeline (structure parsing)
"""

from typing import Any, Callable, List, Optional, Protocol


# Type pour le writer d'images
ImageWriterCallable = Callable[[int, int, str], Optional[str]]


class OCRImage(Protocol):
    """Protocol pour une image extraite par OCR."""

    image_base64: Optional[str]


class OCRPage(Protocol):
    """Protocol pour une page extraite par OCR."""

    markdown: Optional[str]
    images: Optional[List[OCRImage]]


class OCRResponseProtocol(Protocol):
    """Protocol pour la réponse complète de l'API OCR Mistral."""

    pages: List[OCRPage]


def build_markdown(
    ocr_response: OCRResponseProtocol,
    embed_images: bool = False,
    image_writer: Optional[ImageWriterCallable] = None,
) -> str:
    """Construit le texte Markdown à partir de la réponse OCR.

    Args:
        ocr_response: Réponse de l'API OCR Mistral contenant les pages extraites.
        embed_images: Intégrer les images en base64 dans le Markdown.
        image_writer: Fonction pour sauvegarder les images sur disque.
                     Signature: (page_idx, img_idx, base64_data) -> chemin_relatif.

    Returns:
        Texte Markdown complet du document avec marqueurs de page et images.

    Example:
        >>> markdown = build_markdown(
        ...     ocr_response,
        ...     embed_images=False,
        ...     image_writer=lambda p, i, b64: f"images/p{p}_i{i}.png"
        ... )
    """
    md_parts: List[str] = []

    for page_index, page in enumerate(ocr_response.pages, start=1):
        # Commentaire de page
        md_parts.append(f"<!-- Page {page_index} -->\n\n")

        # Contenu Markdown de la page
        page_markdown: Optional[str] = getattr(page, "markdown", None)
        if page_markdown:
            md_parts.append(page_markdown)
            md_parts.append("\n\n")

        # Traitement des images
        page_images: Optional[List[OCRImage]] = getattr(page, "images", None)
        if page_images:
            for img_idx, img in enumerate(page_images, start=1):
                image_b64: Optional[str] = getattr(img, "image_base64", None)
                if not image_b64:
                    continue

                if embed_images:
                    # Image intégrée en base64
                    data_uri: str = f"data:image/png;base64,{image_b64}"
                    md_parts.append(
                        f"![Page {page_index} – Image {img_idx}]({data_uri})\n\n"
                    )
                elif image_writer:
                    # Image sauvegardée sur disque
                    rel_path: Optional[str] = image_writer(page_index, img_idx, image_b64)
                    if rel_path:
                        md_parts.append(
                            f"![Page {page_index} – Image {img_idx}]({rel_path})\n\n"
                        )

    return "".join(md_parts)
