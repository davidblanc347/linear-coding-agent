#!/usr/bin/env python3
"""
Export thoughts from Weaviate to Markdown file.

Exports all thoughts to docs/thoughts.md
"""

import weaviate
from datetime import datetime
from pathlib import Path


def export_thoughts_to_md(output_file: str = "docs/thoughts.md"):
    """Export all thoughts to markdown file."""

    # Connect to Weaviate
    client = weaviate.connect_to_local()

    try:
        # Get collection
        thought_collection = client.collections.get("Thought")

        # Fetch all thoughts (sorted by timestamp)
        thoughts_response = thought_collection.query.fetch_objects(
            limit=1000
        )

        thoughts = thoughts_response.objects
        print(f"Found {len(thoughts)} thoughts")

        # Sort by timestamp (most recent first)
        thoughts = sorted(
            thoughts,
            key=lambda t: t.properties.get("timestamp", datetime.min),
            reverse=True
        )

        # Build markdown content
        lines = []
        lines.append("# Thoughts Export")
        lines.append(f"\n**Exported**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"\n**Total thoughts**: {len(thoughts)}")
        lines.append("\n---\n")

        # Group by type
        thoughts_by_type = {}
        for thought in thoughts:
            thought_type = thought.properties.get("thought_type", "unknown")
            if thought_type not in thoughts_by_type:
                thoughts_by_type[thought_type] = []
            thoughts_by_type[thought_type].append(thought)

        # Write summary by type
        lines.append("## Summary by Type\n")
        for thought_type in sorted(thoughts_by_type.keys()):
            count = len(thoughts_by_type[thought_type])
            lines.append(f"- **{thought_type}**: {count}")

        lines.append("\n---\n")

        # Process each thought
        for idx, thought in enumerate(thoughts, 1):
            props = thought.properties

            content = props.get("content", "No content")
            thought_type = props.get("thought_type", "unknown")
            timestamp = props.get("timestamp")
            trigger = props.get("trigger", "")
            emotional_state = props.get("emotional_state", "")
            concepts = props.get("concepts", [])
            privacy_level = props.get("privacy_level", "private")
            context = props.get("context", "")

            # Format timestamp
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else "N/A"

            # Type emoji
            type_emoji = {
                "reflexion": "💭",
                "question": "❓",
                "intuition": "💡",
                "observation": "👁️",
                "conclusion": "✅",
                "hypothesis": "🤔",
                "discovery": "🔍"
            }.get(thought_type, "📝")

            # Privacy emoji
            privacy_emoji = {
                "private": "🔒",
                "shared": "👥",
                "public": "🌐"
            }.get(privacy_level, "❓")

            # Write thought entry
            lines.append(f"## {type_emoji} Thought {idx}: {thought_type.upper()}")
            lines.append(f"\n**Timestamp**: {timestamp_str}")
            lines.append(f"**Privacy**: {privacy_emoji} {privacy_level}")

            if trigger:
                lines.append(f"**Trigger**: {trigger}")

            if emotional_state:
                lines.append(f"**Emotional state**: {emotional_state}")

            if concepts:
                lines.append(f"**Concepts**: {', '.join(concepts)}")

            lines.append(f"\n### Content\n\n{content}\n")

            if context:
                lines.append(f"**Context**: {context}\n")

            lines.append("\n---\n")

        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"\n[OK] Exported {len(thoughts)} thoughts to {output_file}")

        # Stats
        print(f"   Types: {dict((k, len(v)) for k, v in thoughts_by_type.items())}")

        privacy_stats = {}
        for t in thoughts:
            privacy = t.properties.get("privacy_level", "unknown")
            privacy_stats[privacy] = privacy_stats.get(privacy, 0) + 1

        print(f"   Privacy: {dict(privacy_stats)}")

    finally:
        client.close()


if __name__ == "__main__":
    export_thoughts_to_md()
