"""Upload de fichiers PDF vers l'API Mistral."""

from mistralai import Mistral


def upload_pdf(client: Mistral, file_bytes: bytes, filename: str) -> str:
    """Upload un PDF vers Mistral et retourne l'URL signée.

    Args:
        client: Client Mistral authentifié
        file_bytes: Contenu binaire du fichier PDF
        filename: Nom du fichier

    Returns:
        URL signée du document uploadé
    """
    # Upload du fichier
    uploaded = client.files.upload(
        file={
            "file_name": filename,
            "content": file_bytes,
        },
        purpose="ocr",
    )
    
    # Récupération de l'URL signée
    signed = client.files.get_signed_url(file_id=uploaded.id)
    
    return signed.url


