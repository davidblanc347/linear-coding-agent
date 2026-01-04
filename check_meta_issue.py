"""
Vérifier si le META issue existe toujours dans Linear.
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY")
if not LINEAR_API_KEY:
    print("ERROR: LINEAR_API_KEY not found")
    exit(1)

# Read project info
project_file = Path("generations/library_rag/.linear_project.json")
with open(project_file) as f:
    project_info = json.load(f)

meta_issue_id = project_info.get("meta_issue_id")
project_id = project_info.get("project_id")

print("=" * 80)
print("Checking META issue existence...")
print(f"META issue ID from .linear_project.json: {meta_issue_id}")
print("=" * 80)
print()

# Try to fetch the META issue
query = """
query($issueId: String!) {
  issue(id: $issueId) {
    id
    identifier
    title
    state {
      name
    }
  }
}
"""

headers = {
    "Authorization": LINEAR_API_KEY,
    "Content-Type": "application/json"
}

response = requests.post(
    "https://api.linear.app/graphql",
    headers=headers,
    json={"query": query, "variables": {"issueId": meta_issue_id}}
)

if response.status_code != 200:
    print(f"ERROR: Linear API error: {response.status_code}")
    exit(1)

data = response.json()

if "errors" in data:
    print("META ISSUE NOT FOUND (was deleted)")
    print()
    print("SOLUTION: Need to recreate META issue or reset .linear_project.json")
    exit(1)

issue = data["data"]["issue"]
if issue is None:
    print("META ISSUE NOT FOUND (was deleted)")
    print()
    print("SOLUTION: Need to recreate META issue or reset .linear_project.json")
    exit(1)

print(f"META issue EXISTS:")
print(f"   ID: {issue['id']}")
print(f"   Identifier: {issue['identifier']}")
print(f"   Title: {issue['title']}")
print(f"   State: {issue['state']['name']}")
print()
print("OK - Can proceed with agent")
