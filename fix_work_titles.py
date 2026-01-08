"""Fix Work titles that contain LLM placeholder instructions."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

import weaviate
import weaviate.classes.query as wvq

# Patterns indicating bad titles/authors (LLM placeholders)
BAD_PATTERNS = [
    "si c'est bien le titre",
    "à identifier",
    "à confirmer",
    "ex:",
    "Titre corrigé",
    "Auteur à identifier",
    "Nom de l'auteur",
    "(possiblement)",
    "(correct)",
]

def is_bad_metadata(text: str) -> bool:
    """Check if metadata contains LLM placeholder patterns."""
    if not text:
        return False
    text_lower = text.lower()
    return any(pattern.lower() in text_lower for pattern in BAD_PATTERNS)

def clean_title(title: str) -> str:
    """Extract clean title from placeholder text."""
    if not is_bad_metadata(title):
        return title

    # Extract from patterns like: "Title (si c'est bien...)"
    if "(" in title:
        clean = title.split("(")[0].strip()
        if clean:
            return clean

    # Extract from patterns like: "ex: \"Real Title\""
    if "ex:" in title.lower():
        import re
        match = re.search(r'ex:\s*["\']([^"\']+)["\']', title, re.IGNORECASE)
        if match:
            return match.group(1)

    return title

def get_correct_metadata_from_chunks(
    output_dir: Path, source_id: str
) -> Tuple[str | None, str | None]:
    """Extract correct title/author from chunks JSON file.

    Returns:
        Tuple of (title, author) or (None, None) if not found.
    """
    chunks_file = output_dir / source_id / f"{source_id}_chunks.json"
    if not chunks_file.exists():
        return None, None

    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        metadata = data.get("metadata", {})

        # Priority: work > original_title > title
        title = (
            metadata.get("work") or
            metadata.get("original_title") or
            metadata.get("title")
        )

        author = (
            metadata.get("original_author") or
            metadata.get("author")
        )

        return title, author
    except Exception as e:
        print(f"  ⚠️  Error reading {chunks_file}: {e}")
        return None, None

def fix_works_and_chunks():
    """Fix Work titles and update associated chunks."""
    output_dir = Path(__file__).parent / "generations" / "library_rag" / "output"

    print("🔧 Fixing Work titles with LLM placeholders...\n")

    client = weaviate.connect_to_local()

    try:
        work_collection = client.collections.get("Work")
        chunk_collection = client.collections.get("Chunk_v2")

        # Find all Works with bad titles/authors
        works_to_fix: List[Dict[str, Any]] = []

        print("📊 Scanning Works for placeholder patterns...\n")

        for work in work_collection.iterator(include_vector=False):
            props = work.properties
            source_id = props.get("sourceId")
            title = props.get("title", "")
            author = props.get("author", "")

            if not source_id:
                continue

            needs_fix = is_bad_metadata(title) or is_bad_metadata(author)

            if needs_fix:
                works_to_fix.append({
                    "uuid": str(work.uuid),
                    "source_id": source_id,
                    "old_title": title,
                    "old_author": author,
                })
                print(f"❌ Found bad Work: {source_id}")
                print(f"   Title: {title[:80]}")
                print(f"   Author: {author[:80]}\n")

        if not works_to_fix:
            print("✅ No Works need fixing!")
            return

        print(f"\n🔍 Found {len(works_to_fix)} Works to fix\n")
        print("=" * 70)

        # Fix each Work
        fixed_count = 0
        failed_count = 0

        for work_data in works_to_fix:
            source_id = work_data["source_id"]
            work_uuid = work_data["uuid"]
            old_title = work_data["old_title"]
            old_author = work_data["old_author"]

            print(f"\n📝 Fixing: {source_id}")

            # Get correct metadata from chunks file
            correct_title, correct_author = get_correct_metadata_from_chunks(
                output_dir, source_id
            )

            if not correct_title:
                print(f"   ⚠️  Could not find correct metadata, skipping")
                failed_count += 1
                continue

            # Clean title if still has placeholders
            if is_bad_metadata(correct_title):
                correct_title = clean_title(correct_title)

            if is_bad_metadata(correct_author or ""):
                correct_author = None  # Better to leave empty than keep placeholder

            print(f"   Old title: {old_title[:60]}")
            print(f"   New title: {correct_title[:60]}")
            print(f"   Old author: {old_author[:60]}")
            print(f"   New author: {correct_author or 'None'}")

            # Update Work
            try:
                work_collection.data.update(
                    uuid=work_uuid,
                    properties={
                        "title": correct_title,
                        "author": correct_author,
                    }
                )
                print(f"   ✅ Updated Work")

                # Update associated chunks
                chunks = chunk_collection.query.fetch_objects(
                    filters=wvq.Filter.by_property("workTitle").equal(old_title),
                    limit=1000
                )

                chunk_count = len(chunks.objects)
                if chunk_count > 0:
                    print(f"   🔄 Updating {chunk_count} chunks...")

                    for chunk in chunks.objects:
                        try:
                            chunk_collection.data.update(
                                uuid=str(chunk.uuid),
                                properties={
                                    "workTitle": correct_title,
                                    "workAuthor": correct_author,
                                }
                            )
                        except Exception as e:
                            print(f"      ⚠️  Failed to update chunk {chunk.uuid}: {e}")

                    print(f"   ✅ Updated {chunk_count} chunks")

                fixed_count += 1

            except Exception as e:
                print(f"   ❌ Failed to update Work: {e}")
                failed_count += 1

        print("\n" + "=" * 70)
        print(f"\n✅ Fixed {fixed_count} Works")
        if failed_count > 0:
            print(f"⚠️  Failed to fix {failed_count} Works")

    finally:
        client.close()

if __name__ == "__main__":
    fix_works_and_chunks()
    print("\n✓ Done")
