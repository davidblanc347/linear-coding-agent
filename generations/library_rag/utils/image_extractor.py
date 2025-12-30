"""Image extraction and storage from OCR API responses.

This module provides utilities for extracting and saving images from
Mistral OCR API responses. It is a companion module to markdown_builder,
handling the image-specific aspects of document processing.

Features:
    - **Image Writer Factory**: Creates reusable callbacks for image saving
    - **Batch Extraction**: Processes all images from an OCR response
    - **Protocol-based Design**: Flexible interface for custom implementations

Pipeline Position:
    OCR Response → **Image Extractor** → Saved images + paths for Markdown

Components:
    1. ImageWriterProtocol: Interface definition for image saving
    2. create_image_writer(): Factory for standard file-based writers
    3. extract_images(): Batch extraction from OCR responses

Integration:
    The image writer is designed to integrate with markdown_builder:

    >>> from utils.image_extractor import create_image_writer
    >>> from utils.markdown_builder import build_markdown
    >>>
    >>> writer = create_image_writer(Path("output/doc/images"))
    >>> markdown = build_markdown(ocr_response, image_writer=writer)

Standalone Usage:
    >>> from pathlib import Path
    >>> from utils.image_extractor import extract_images
    >>>
    >>> # Extract all images from OCR response
    >>> paths = extract_images(ocr_response, Path("output/my_doc"))
    >>> print(f"Extracted {len(paths)} images")

File Naming Convention:
    Images are named: page{N}_img{M}.png
    - N: Page number (1-based)
    - M: Image index within page (1-based)
    - Format: Always PNG (base64 from Mistral is PNG)

Note:
    - All indices are 1-based for consistency with page numbering
    - The images subdirectory is created automatically if needed
    - Base64 data without proper encoding is silently skipped
    - Large documents may produce many images; monitor disk space

See Also:
    - utils.markdown_builder: Uses ImageWriter for markdown generation
    - utils.mistral_client: Source of OCR responses with image data
"""

import base64
from pathlib import Path
from typing import Any, Callable, List, Optional, Protocol


class ImageWriterProtocol(Protocol):
    """Protocol for image writing callbacks.

    This protocol defines the interface for functions that save
    images extracted from OCR responses and return a relative
    path for markdown references.

    The protocol expects:
        - page_idx: 1-based page number
        - img_idx: 1-based image index within the page
        - image_b64: Base64-encoded image data

    Returns:
        Relative path to the saved image for markdown inclusion.

    Example:
        >>> def my_writer(page_idx: int, img_idx: int, image_b64: str) -> str:
        ...     # Custom saving logic
        ...     return f"images/page{page_idx}_img{img_idx}.png"
    """

    def __call__(self, page_idx: int, img_idx: int, image_b64: str) -> str:
        """Save image and return relative path for markdown reference."""
        ...


# Type alias for image writer callables
ImageWriter = Callable[[int, int, str], str]


def create_image_writer(images_dir: Path) -> ImageWriter:
    """Create a function for saving images to disk.

    This factory function creates a closure that saves base64-encoded
    images to the specified directory and returns relative paths
    suitable for markdown image references.

    Args:
        images_dir: Directory path where images will be saved.
            The directory will be created if it doesn't exist.

    Returns:
        A callable that accepts (page_idx, img_idx, image_b64) and
        returns the relative path to the saved image.

    Example:
        >>> from pathlib import Path
        >>> writer = create_image_writer(Path("output/images"))
        >>> path = writer(1, 0, "iVBORw0KGgoAAAANS...")
        >>> print(path)
        'images/page1_img0.png'
    """
    # Create directory if it doesn't exist
    images_dir.mkdir(parents=True, exist_ok=True)

    def writer(page_idx: int, img_idx: int, image_b64: str) -> str:
        """Save an image and return its relative path.

        Args:
            page_idx: Page number (1-based).
            img_idx: Image index within the page (1-based).
            image_b64: Base64-encoded image data.

        Returns:
            Relative path to the saved image file.
        """
        filename: str = f"page{page_idx}_img{img_idx}.png"
        filepath: Path = images_dir / filename

        # Decode and save
        image_data: bytes = base64.b64decode(image_b64)
        filepath.write_bytes(image_data)

        # Return relative path for markdown
        return f"images/{filename}"

    return writer


def extract_images(ocr_response: Any, output_dir: Path) -> List[str]:
    """Extract all images from an OCR response.

    Iterates through all pages in the OCR response, extracts any
    embedded images, decodes them from base64, and saves them
    to the output directory.

    Args:
        ocr_response: OCR response object from Mistral API.
            Expected to have a pages attribute, where each page
            may have an images list containing objects with
            image_base64 attributes.
        output_dir: Base output directory. Images will be saved
            to a subdirectory named "images".

    Returns:
        List of absolute file paths to the extracted images.

    Example:
        >>> from pathlib import Path
        >>> paths = extract_images(ocr_response, Path("output/my_doc"))
        >>> for path in paths:
        ...     print(path)
        'C:/output/my_doc/images/page1_img1.png'
        'C:/output/my_doc/images/page2_img1.png'

    Note:
        - Pages and images are 1-indexed in filenames
        - Images without base64 data are silently skipped
        - The images subdirectory is created automatically
    """
    images_dir: Path = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    extracted: List[str] = []

    for page_index, page in enumerate(ocr_response.pages, start=1):
        if not getattr(page, "images", None):
            continue

        for img_idx, img in enumerate(page.images, start=1):
            image_b64: Optional[str] = getattr(img, "image_base64", None)
            if not image_b64:
                continue

            filename: str = f"page{page_index}_img{img_idx}.png"
            filepath: Path = images_dir / filename

            # Decode and save
            image_data: bytes = base64.b64decode(image_b64)
            filepath.write_bytes(image_data)

            extracted.append(str(filepath))

    return extracted
