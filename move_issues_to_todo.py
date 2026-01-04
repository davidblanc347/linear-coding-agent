"""
Move all Backlog issues to Todo status for the agent to process them.
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

project_file = Path("generations/library_rag/.linear_project.json")
with open(project_file) as f:
    project_info = json.load(f)

project_id = project_info.get("project_id")
team_id = project_info.get("team_id")

print("=" * 80)
print("Moving Backlog issues to Todo...")
print("=" * 80)
print()

# Get all issues
query = """
query($projectId: String!) {
  project(id: $projectId) {
    issues(first: 200) {
      nodes {
        id
        identifier
        title
        state {
          id
          name
          type
        }
      }
    }
  }
  workflowStates(filter: { team: { id: { eq: "%s" } } }) {
    nodes {
      id
      name
      type
    }
  }
}
""" % team_id

headers = {
    "Authorization": LINEAR_API_KEY,
    "Content-Type": "application/json"
}

response = requests.post(
    "https://api.linear.app/graphql",
    headers=headers,
    json={"query": query, "variables": {"projectId": project_id}}
)

data = response.json()
issues = data["data"]["project"]["issues"]["nodes"]
workflow_states = data["data"]["workflowStates"]["nodes"]

# Find Todo state ID
todo_state_id = None
for state in workflow_states:
    if state["name"] == "Todo" or state["type"] == "unstarted":
        todo_state_id = state["id"]
        break

if not todo_state_id:
    print("ERROR: Could not find 'Todo' workflow state")
    exit(1)

print(f"Found 'Todo' state: {todo_state_id}")
print()

# Find issues in Backlog
backlog_issues = []
for issue in issues:
    state_name = issue["state"]["name"]
    state_type = issue["state"]["type"]
    if state_name == "Backlog" or state_type == "backlog":
        backlog_issues.append(issue)

print(f"Found {len(backlog_issues)} issues in Backlog:")
for issue in backlog_issues:
    print(f"   {issue['identifier']} - {issue['title'][:60]}")
print()

if len(backlog_issues) == 0:
    print("No issues to move!")
    exit(0)

# Move to Todo
mutation = """
mutation($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: { stateId: $stateId }) {
    success
    issue {
      identifier
      state {
        name
      }
    }
  }
}
"""

moved_count = 0
for issue in backlog_issues:
    print(f"Moving {issue['identifier']} to Todo...", end=" ")

    response = requests.post(
        "https://api.linear.app/graphql",
        headers=headers,
        json={
            "query": mutation,
            "variables": {
                "issueId": issue["id"],
                "stateId": todo_state_id
            }
        }
    )

    if response.status_code == 200:
        result = response.json()
        if result["data"]["issueUpdate"]["success"]:
            print("OK")
            moved_count += 1
        else:
            print("FAILED")
    else:
        print(f"FAILED (HTTP {response.status_code})")

print()
print("=" * 80)
print(f"Moved {moved_count}/{len(backlog_issues)} issues to Todo")
print("=" * 80)
print()
print("You can now run:")
print("   python autonomous_agent_demo.py --project-dir ./generations/library_rag")
print()
