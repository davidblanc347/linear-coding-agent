"""Schémas Pydantic pour l'extraction structurée via OCR avec annotations.

Utilisés avec document_annotation_format et bbox_annotation_format de l'API Mistral.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class TocEntryType(str, Enum):
    """Type d'entrée de table des matières."""
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    PREAMBLE = "preamble"
    APPENDIX = "appendix"


class TocEntry(BaseModel):
    """Entrée de table des matières avec hiérarchie."""
    title: str = Field(..., description="Titre exact de la section tel qu'il apparaît dans la table des matières")
    page_number: int = Field(..., description="Numéro de page réel tel qu'imprimé/affiché dans le livre (PAS l'index séquentiel du PDF, mais le numéro visible sur la page elle-même)")
    level: int = Field(..., description="""Niveau hiérarchique détecté VISUELLEMENT dans la mise en page de la table des matières:
    - level=1 si le titre est aligné à gauche SANS indentation (titres principaux)
    - level=2 si le titre a une PETITE indentation ou est légèrement décalé vers la droite
    - level=3 si le titre a une DOUBLE indentation ou est très décalé vers la droite
    Regardez attentivement l'alignement horizontal et les espaces avant chaque titre pour déterminer le niveau.""")
    entry_type: TocEntryType = Field(default=TocEntryType.SECTION, description="Type d'entrée: 'preamble' pour préfaces/introductions, 'chapter' pour chapitres, 'section' pour sections, 'subsection' pour sous-sections, 'appendix' pour annexes")
    parent_title: Optional[str] = Field(None, description="Si level > 1, indiquer le titre du parent direct (l'entrée de level=1 sous laquelle cette entrée est indentée)")


class DocumentTOC(BaseModel):
    """Table des matières complète du document."""
    entries: List[TocEntry] = Field(..., description="""Liste COMPLÈTE de TOUTES les entrées de la table des matières dans l'ordre d'apparition. 
    IMPORTANT : Analysez attentivement l'indentation/alignement horizontal de chaque titre pour assigner le bon niveau hiérarchique:
    - Les titres alignés à gauche (non indentés) = level 1
    - Les titres légèrement indentés/décalés vers la droite = level 2 (sous-sections du titre level 1 précédent)
    - Les titres avec double indentation = level 3 (sous-sections du titre level 2 précédent)
    Chaque entrée doit avoir son vrai numéro de page tel qu'imprimé dans le livre.""")
    has_explicit_toc: bool = Field(..., description="Le document contient-il une table des matières explicite et visible ? (généralement en début de document)")
    toc_page_numbers: List[int] = Field(..., description="Liste des numéros de pages où se trouve la table des matières (généralement pages 2-5)")


class DocumentMetadata(BaseModel):
    """Métadonnées enrichies du document."""
    title: str = Field(..., description="Titre complet du document")
    author: str = Field(..., description="Auteur principal du document")
    languages: List[str] = Field(..., description="Liste des langues présentes dans le document (codes ISO 639-1, ex: ['fr', 'en'])")
    summary: str = Field(..., description="Résumé du document en 2-3 phrases maximum")
    collection: Optional[str] = Field(None, description="Nom de la collection ou série éditoriale")
    publisher: Optional[str] = Field(None, description="Nom de l'éditeur")
    year: Optional[int] = Field(None, description="Année de publication")
    total_pages: int = Field(..., description="Nombre total de pages dans le document")
    toc: DocumentTOC = Field(..., description="Table des matières structurée avec hiérarchie et numéros de page réels")
