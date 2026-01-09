#!/usr/bin/env python3
"""
Export conversations from Weaviate to Markdown file.

Exports all conversations with their messages to docs/conversations.md
"""

import weaviate
from datetime import datetime
from pathlib import Path


def export_conversations_to_md(output_file: str = "docs/conversations.md"):
    """Export all conversations to markdown file."""

    # Connect to Weaviate
    client = weaviate.connect_to_local()

    try:
        # Get collections
        conversation_collection = client.collections.get("Conversation")
        message_collection = client.collections.get("Message")

        # Fetch all conversations (sorted by start date)
        conversations_response = conversation_collection.query.fetch_objects(
            limit=1000
        )

        conversations = conversations_response.objects
        print(f"Found {len(conversations)} conversations")

        # Sort by timestamp_start
        conversations = sorted(
            conversations,
            key=lambda c: c.properties.get("timestamp_start", datetime.min),
            reverse=True
        )

        # Build markdown content
        lines = []
        lines.append("# Conversations Export")
        lines.append(f"\n**Exported**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"\n**Total conversations**: {len(conversations)}")
        lines.append("\n---\n")

        # Process each conversation
        for idx, conv in enumerate(conversations, 1):
            props = conv.properties

            conv_id = props.get("conversation_id", "unknown")
            category = props.get("category", "N/A")
            summary = props.get("summary", "No summary")
            timestamp_start = props.get("timestamp_start")
            timestamp_end = props.get("timestamp_end")
            participants = props.get("participants", [])
            tags = props.get("tags", [])
            message_count = props.get("message_count", 0)
            context = props.get("context", "")

            # Format timestamps
            start_str = timestamp_start.strftime('%Y-%m-%d %H:%M:%S') if timestamp_start else "N/A"
            end_str = timestamp_end.strftime('%Y-%m-%d %H:%M:%S') if timestamp_end else "Ongoing"

            # Write conversation header
            lines.append(f"## Conversation {idx}: {conv_id}")
            lines.append(f"\n**Category**: {category}")
            lines.append(f"**Start**: {start_str}")
            lines.append(f"**End**: {end_str}")

            if participants:
                lines.append(f"**Participants**: {', '.join(participants)}")

            if tags:
                lines.append(f"**Tags**: {', '.join(tags)}")

            lines.append(f"**Message count**: {message_count}")

            lines.append(f"\n**Summary**:\n{summary}")

            if context:
                lines.append(f"\n**Context**:\n{context}")

            # Fetch messages for this conversation
            messages_response = message_collection.query.fetch_objects(
                filters=weaviate.classes.query.Filter.by_property("conversation_id").equal(conv_id),
                limit=1000
            )

            messages = messages_response.objects

            # Sort by order_index
            messages = sorted(
                messages,
                key=lambda m: m.properties.get("order_index", 0)
            )

            if messages:
                lines.append(f"\n### Messages ({len(messages)})\n")

                for msg in messages:
                    msg_props = msg.properties
                    role = msg_props.get("role", "unknown")
                    content = msg_props.get("content", "")
                    timestamp = msg_props.get("timestamp")
                    order_idx = msg_props.get("order_index", 0)

                    timestamp_str = timestamp.strftime('%H:%M:%S') if timestamp else "N/A"

                    # Format role emoji
                    role_emoji = {
                        "user": "👤",
                        "assistant": "🤖",
                        "system": "⚙️"
                    }.get(role, "❓")

                    lines.append(f"**[{order_idx}] {role_emoji} {role.upper()}** ({timestamp_str})")
                    lines.append(f"\n{content}\n")
            else:
                lines.append("\n*No messages found*\n")

            lines.append("\n---\n")

        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"\n[OK] Exported {len(conversations)} conversations to {output_file}")

        # Stats
        total_messages = sum(c.properties.get("message_count", 0) for c in conversations)
        print(f"   Total messages: {total_messages}")

        categories = {}
        for c in conversations:
            cat = c.properties.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        print(f"   Categories: {dict(categories)}")

    finally:
        client.close()


if __name__ == "__main__":
    export_conversations_to_md()
