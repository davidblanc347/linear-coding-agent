"""Hierarchical Markdown document parser for semantic chunking.

This module provides utilities for parsing Markdown documents into
hierarchical structures based on heading levels (# to ######). It is
a key component of the RAG pipeline, enabling:

1. **Structure Extraction**: Parse Markdown into a tree of sections
2. **Context Preservation**: Maintain hierarchical context (part > chapter > section)
3. **Semantic Chunking**: Flatten hierarchy into chunks with full path context

The parser uses a stack-based algorithm to build nested section trees,
preserving the document's logical structure for downstream processing.

Architecture:
    Input: Raw Markdown text with headings
        ↓
    build_hierarchy() → DocumentHierarchy (tree structure)
        ↓
    flatten_hierarchy() → List[FlatChunk] (with hierarchical context)

TypedDict Definitions:
    - HierarchyPath: Hierarchical path (part/chapter/section/subsection)
    - HierarchyNode: Tree node with title, level, content, children
    - DocumentHierarchy: Complete document structure
    - FlatChunk: Flattened chunk with context for RAG ingestion

Algorithm:
    The build_hierarchy() function uses a stack-based approach:
    1. Initialize a virtual root node at level 0
    2. For each line in the document:
       - If heading: pop stack until parent level found, then push new node
       - If content: append to current node's content
    3. Finalize nodes by joining content lines

Example:
    >>> markdown = '''
    ... # Introduction
    ... This is the intro.
    ...
    ... ## Background
    ... Some background text.
    ...
    ... ## Methodology
    ... Methods used here.
    ... '''
    >>> hierarchy = build_hierarchy(markdown)
    >>> print(hierarchy["sections"][0]["title"])
    'Introduction'
    >>> chunks = flatten_hierarchy(hierarchy)
    >>> for chunk in chunks:
    ...     print(f"{chunk['chunk_id']}: {chunk['title']}")
    chunk_00001: Introduction
    chunk_00002: Background
    chunk_00003: Methodology

See Also:
    - utils.llm_chunker: Semantic chunking using LLM
    - utils.markdown_builder: Markdown generation from OCR
    - utils.weaviate_ingest: Ingestion of chunks into Weaviate
"""

from __future__ import annotations

import re
from typing import List, Optional, Pattern, TypedDict

# Import type definitions from central types module
from utils.types import (
    DocumentHierarchy,
    FlatChunk,
    HierarchyNode,
    HierarchyPath,
)


class _BuildNode(TypedDict):
    """Noeud interne pour la construction de la hiérarchie."""

    title: Optional[str]
    level: int
    content: List[str]
    children: List[_BuildNode]


def build_hierarchy(markdown_text: str) -> DocumentHierarchy:
    """Construit une structure hiérarchique à partir des titres Markdown.

    Analyse les titres (# à ######) et construit un arbre de sections
    avec leur contenu textuel.

    Args:
        markdown_text: Texte Markdown à analyser

    Returns:
        Dictionnaire avec :
        - preamble: Texte avant le premier titre
        - sections: Liste de sections imbriquées

        Chaque section contient :
        - title: Titre de la section
        - level: Niveau (1-6)
        - content: Contenu textuel
        - children: Sous-sections
    """
    # Regex pour les titres Markdown
    heading_re: Pattern[str] = re.compile(r"^(#{1,6})\s+(.*)$")

    lines: List[str] = markdown_text.splitlines()

    # Noeud racine (niveau 0, virtuel)
    root: _BuildNode = {
        "title": None,
        "level": 0,
        "content": [],
        "children": [],
    }

    # Pile pour suivre la hiérarchie
    stack: List[_BuildNode] = [root]

    for line in lines:
        stripped: str = line.rstrip()
        match: Optional[re.Match[str]] = heading_re.match(stripped)

        if match:
            # C'est un titre
            level: int = len(match.group(1))
            title: str = match.group(2).strip()

            # Remonter dans la pile jusqu'au parent approprié
            while stack and stack[-1]["level"] >= level:
                stack.pop()

            # Créer le nouveau noeud
            node: _BuildNode = {
                "title": title,
                "level": level,
                "content": [],
                "children": [],
            }

            # Ajouter au parent
            parent: _BuildNode = stack[-1]
            parent["children"].append(node)

            # Empiler le nouveau noeud
            stack.append(node)
        else:
            # C'est du contenu, l'ajouter au noeud courant
            stack[-1]["content"].append(stripped)

    # Finaliser les noeuds (joindre le contenu)
    def finalize(node: _BuildNode) -> HierarchyNode:
        """Convertit un noeud de construction en noeud final."""
        return HierarchyNode(
            title=node["title"],
            level=node["level"],
            content="\n".join(node["content"]).strip(),
            children=[finalize(child) for child in node["children"]],
        )

    # Extraire le préambule et les sections
    preamble: str = "\n".join(root["content"]).strip()
    sections: List[HierarchyNode] = [finalize(child) for child in root["children"]]

    return DocumentHierarchy(
        preamble=preamble,
        sections=sections,
    )


def flatten_hierarchy(hierarchy: DocumentHierarchy) -> List[FlatChunk]:
    """Aplatit la hiérarchie en une liste de chunks.

    Args:
        hierarchy: Structure hiérarchique (sortie de build_hierarchy)

    Returns:
        Liste de chunks avec leur contexte hiérarchique
    """
    chunks: List[FlatChunk] = []

    # Préambule comme premier chunk
    if hierarchy.get("preamble"):
        preamble_chunk: FlatChunk = {
            "chunk_id": "chunk_00000",
            "text": hierarchy["preamble"],
            "hierarchy": HierarchyPath(
                part=None,
                chapter=None,
                section=None,
                subsection=None,
            ),
            "type": "preamble",
            "level": 0,
            "title": None,
        }
        chunks.append(preamble_chunk)

    def process_section(
        section: HierarchyNode,
        path: HierarchyPath,
        index: int,
    ) -> int:
        """Traite récursivement une section.

        Args:
            section: Noeud de section à traiter
            path: Chemin hiérarchique courant
            index: Index du prochain chunk

        Returns:
            Nouvel index après traitement
        """
        level: int = section["level"]
        title: Optional[str] = section["title"]

        # Mettre à jour le chemin hiérarchique
        current_path: HierarchyPath = path.copy()
        if level == 1:
            current_path = HierarchyPath(
                part=title,
                chapter=None,
                section=None,
                subsection=None,
            )
        elif level == 2:
            current_path["chapter"] = title
            current_path["section"] = None
            current_path["subsection"] = None
        elif level == 3:
            current_path["section"] = title
            current_path["subsection"] = None
        elif level >= 4:
            current_path["subsection"] = title

        # Créer le chunk si contenu
        if section["content"]:
            chunk: FlatChunk = {
                "chunk_id": f"chunk_{index:05d}",
                "text": section["content"],
                "hierarchy": current_path.copy(),
                "type": "main_content",
                "level": level,
                "title": title,
            }
            chunks.append(chunk)
            index += 1

        # Traiter les enfants
        for child in section["children"]:
            index = process_section(child, current_path, index)

        return index

    # Traiter toutes les sections
    idx: int = 1
    initial_path: HierarchyPath = HierarchyPath(
        part=None,
        chapter=None,
        section=None,
        subsection=None,
    )
    for section in hierarchy.get("sections", []):
        idx = process_section(section, initial_path, idx)

    return chunks
