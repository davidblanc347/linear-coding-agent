"""
Script pour vérifier l'état actuel des issues Linear du projet library_rag.

Affiche :
- Nombre total d'issues
- Nombre d'issues par statut (Todo, In Progress, Done)
- Liste des issues In Progress (si présentes)
- Liste des issues Todo avec priorité 1 ou 2
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY")
if not LINEAR_API_KEY:
    print("❌ LINEAR_API_KEY not found in .env file")
    exit(1)

# Read project info
project_file = Path("generations/library_rag/.linear_project.json")
if not project_file.exists():
    print(f"❌ Project file not found: {project_file}")
    exit(1)

with open(project_file) as f:
    project_info = json.load(f)

project_id = project_info.get("project_id")
team_id = project_info.get("team_id")
total_issues_created = project_info.get("total_issues", 0)

print("=" * 80)
print(f"LINEAR STATUS CHECK - Project: {project_info.get('project_name')}")
print(f"URL: {project_info.get('project_url')}")
print(f"Total issues created historically: {total_issues_created}")
print("=" * 80)
print()

# GraphQL query to list all issues in the project
query = """
query($projectId: String!) {
  project(id: $projectId) {
    issues(first: 200) {
      nodes {
        id
        identifier
        title
        priority
        state {
          name
        }
        createdAt
      }
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
    json={"query": query, "variables": {"projectId": project_id}}
)

if response.status_code != 200:
    print(f"❌ Linear API error: {response.status_code}")
    print(response.text)
    exit(1)

data = response.json()

if "errors" in data:
    print(f"❌ GraphQL errors: {data['errors']}")
    exit(1)

issues = data["data"]["project"]["issues"]["nodes"]

# Count by status
status_counts = {
    "Todo": 0,
    "In Progress": 0,
    "Done": 0,
    "Other": 0
}

issues_by_status = {
    "Todo": [],
    "In Progress": [],
    "Done": []
}

for issue in issues:
    state_name = issue["state"]["name"]
    if state_name in status_counts:
        status_counts[state_name] += 1
        issues_by_status[state_name].append(issue)
    else:
        status_counts["Other"] += 1

# Display summary
print(f"STATUS SUMMARY:")
print(f"   Done:        {status_counts['Done']}")
print(f"   In Progress: {status_counts['In Progress']}")
print(f"   Todo:        {status_counts['Todo']}")
print(f"   Other:       {status_counts['Other']}")
print(f"   TOTAL:       {len(issues)}")
print()

# Check for issues In Progress (potential blocker)
if status_counts["In Progress"] > 0:
    print("WARNING: There are 'In Progress' issues:")
    print()
    for issue in issues_by_status["In Progress"]:
        priority = issue.get("priority", "N/A")
        print(f"   [IN PROGRESS] {issue['identifier']} - Priority {priority}")
        print(f"      {issue['title']}")
        print()
    print("! The agent will resume these issues first!")
    print()

# List high-priority Todo issues
high_priority_todo = [
    issue for issue in issues_by_status["Todo"]
    if issue.get("priority") in [1, 2]
]

if high_priority_todo:
    print(f"HIGH PRIORITY TODO (Priority 1-2): {len(high_priority_todo)}")
    print()
    for issue in sorted(high_priority_todo, key=lambda x: x.get("priority", 99)):
        priority = issue.get("priority", "N/A")
        print(f"   [TODO] {issue['identifier']} - Priority {priority}")
        print(f"      {issue['title'][:80]}")
        print()

# List all Todo issues (for reference)
if status_counts["Todo"] > 0:
    print(f"ALL TODO ISSUES: {status_counts['Todo']}")
    print()
    for issue in sorted(issues_by_status["Todo"], key=lambda x: x.get("priority", 99)):
        priority = issue.get("priority", "N/A")
        title = issue['title'][:60] + "..." if len(issue['title']) > 60 else issue['title']
        print(f"   {issue['identifier']} [P{priority}] {title}")
    print()

# Recommendation
print("=" * 80)
if status_counts["In Progress"] > 0:
    print("RECOMMENDATION:")
    print("   - There are 'In Progress' issues that should be finished first")
    print("   - Before adding new issues, check if these should be:")
    print("     1. Completed")
    print("     2. Cancelled (moved back to Todo)")
    print("     3. Deleted")
elif status_counts["Todo"] > 10:
    print("RECOMMENDATION:")
    print(f"   - There are {status_counts['Todo']} Todo issues pending")
    print("   - Consider finishing them before adding new ones")
else:
    print("RECOMMENDATION:")
    print("   - Project is in good state to add new issues")
    print("   - You can proceed with --new-spec")
print("=" * 80)
