"""Generate PDF documents from chat exchanges.

This module provides functionality to export chat conversations between users
and the RAG assistant into formatted PDF documents.

Example:
    Export a simple chat exchange::

        from pathlib import Path
        from utils.pdf_exporter import create_chat_export_pdf

        filepath = create_chat_export_pdf(
            user_question="What is phenomenology?",
            assistant_response="Phenomenology is a philosophical movement...",
            output_dir=Path("output")
        )

    Export with reformulated question::

        filepath = create_chat_export_pdf(
            user_question="What does Husserl mean by phenomenology?",
            assistant_response="Husserl defines phenomenology as...",
            is_reformulated=True,
            original_question="What is phenomenology?",
            output_dir=Path("output")
        )
"""

from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
except ImportError:
    raise ImportError(
        "reportlab is required for PDF export. "
        "Install with: pip install reportlab"
    )


def create_chat_export_pdf(
    user_question: str,
    assistant_response: str,
    is_reformulated: bool = False,
    original_question: Optional[str] = None,
    output_dir: Path = Path("output"),
) -> Path:
    """Create a PDF document from a chat exchange.

    Args:
        user_question: The user's question (or reformulated version).
        assistant_response: The assistant's complete response text.
        is_reformulated: Whether the question was reformulated by the system.
            If True, both original and reformulated questions are included.
        original_question: The original user question before reformulation.
            Only used when is_reformulated is True.
        output_dir: Directory where the PDF file will be saved.
            Created if it doesn't exist.

    Returns:
        Path to the generated PDF file.

    Raises:
        OSError: If the output directory cannot be created or file cannot be saved.

    Example:
        >>> from pathlib import Path
        >>> filepath = create_chat_export_pdf(
        ...     user_question="Qu'est-ce que la phénoménologie ?",
        ...     assistant_response="La phénoménologie est...",
        ...     output_dir=Path("output/test_exports")
        ... )
        >>> print(filepath)
        output/test_exports/chat_export_20250101_123045.pdf
    """
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_export_{timestamp}.pdf"
    filepath = output_dir / filename

    # Create directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create PDF document
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    # Get default styles
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=HexColor("#2B2B2B"),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    date_style = ParagraphStyle(
        "DateStyle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=HexColor("#808080"),
        alignment=TA_CENTER,
        spaceAfter=20,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=HexColor("#7D6E58"),
        spaceAfter=10,
        spaceBefore=15,
        fontName="Helvetica-Bold",
    )

    question_style = ParagraphStyle(
        "QuestionStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=HexColor("#2B2B2B"),
        spaceAfter=10,
        leftIndent=1 * cm,
        rightIndent=1 * cm,
        backColor=HexColor("#F8F4EE"),
        borderPadding=10,
    )

    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=HexColor("#2B2B2B"),
        spaceAfter=10,
        alignment=TA_JUSTIFY,
        leading=16,
    )

    footer_style = ParagraphStyle(
        "FooterStyle",
        parent=styles["Normal"],
        fontSize=8,
        textColor=HexColor("#969696"),
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
    )

    # Build document content
    story = []

    # Title
    story.append(Paragraph("Conversation RAG - Export", title_style))

    # Date
    date_text = f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    story.append(Paragraph(date_text, date_style))

    # Original question (if reformulated)
    if is_reformulated and original_question:
        story.append(Paragraph("Question Originale", heading_style))
        story.append(Paragraph(original_question, question_style))
        story.append(Spacer(1, 0.5 * cm))

    # User question
    question_label = "Question Reformulée" if is_reformulated else "Question"
    story.append(Paragraph(question_label, heading_style))
    story.append(Paragraph(user_question, question_style))
    story.append(Spacer(1, 0.5 * cm))

    # Assistant response
    story.append(Paragraph("Réponse de l'Assistant", heading_style))

    # Split response into paragraphs
    response_paragraphs = assistant_response.split("\n\n")
    for para in response_paragraphs:
        if para.strip():
            story.append(Paragraph(para.strip(), body_style))

    # Footer
    story.append(Spacer(1, 1 * cm))
    story.append(
        Paragraph("Généré par Library RAG - Recherche Philosophique", footer_style)
    )

    # Build PDF
    doc.build(story)

    return filepath
