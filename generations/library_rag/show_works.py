"""Script to display all documents from the Weaviate Document collection in table format.

Usage:
    python show_works.py
"""

import weaviate
from typing import Any
from tabulate import tabulate
from datetime import datetime


def format_date(date_val: Any) -> str:
    """Format date for display.

    Args:
        date_val: Date value (string or datetime).

    Returns:
        Formatted date string.
    """
    if date_val is None:
        return "-"
    if isinstance(date_val, str):
        try:
            dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return date_val
    return str(date_val)


def display_documents() -> None:
    """Connect to Weaviate and display all Document objects in table format."""
    try:
        # Connect to local Weaviate instance
        client = weaviate.connect_to_local()

        try:
            # Get Document collection
            document_collection = client.collections.get("Document")

            # Fetch all documents
            response = document_collection.query.fetch_objects(limit=1000)

            if not response.objects:
                print("No documents found in the collection.")
                return

            # Prepare data for table
            table_data = []
            for obj in response.objects:
                props = obj.properties

                # Extract nested work object
                work = props.get("work", {})
                work_title = work.get("title", "N/A") if isinstance(work, dict) else "N/A"
                work_author = work.get("author", "N/A") if isinstance(work, dict) else "N/A"

                table_data.append([
                    props.get("sourceId", "N/A"),
                    work_title,
                    work_author,
                    props.get("edition", "-"),
                    props.get("pages", "-"),
                    props.get("chunksCount", "-"),
                    props.get("language", "-"),
                    format_date(props.get("createdAt")),
                ])

            # Display header
            print(f"\n{'='*120}")
            print(f"Collection Document - {len(response.objects)} document(s) trouvé(s)")
            print(f"{'='*120}\n")

            # Display table
            headers = ["Source ID", "Work Title", "Author", "Edition", "Pages", "Chunks", "Lang", "Created At"]
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
            print()

        finally:
            client.close()

    except Exception as e:
        print(f"Error connecting to Weaviate: {e}")
        print("\nMake sure Weaviate is running:")
        print("  docker compose up -d")


if __name__ == "__main__":
    display_documents()
