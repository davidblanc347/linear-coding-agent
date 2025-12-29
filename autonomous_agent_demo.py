#!/usr/bin/env python3
"""
Autonomous Coding Agent Demo
============================

A minimal harness demonstrating long-running autonomous coding with Claude.
This script implements the two-agent pattern (initializer + coding agent) and
incorporates all the strategies from the long-running agents guide.

Example Usage:
    python autonomous_agent_demo.py --project-dir ./claude_clone_demo
    python autonomous_agent_demo.py --project-dir ./claude_clone_demo --max-iterations 5
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Fix Windows encoding issues with emojis and Unicode characters
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from agent import run_autonomous_agent

# Load environment variables from .env file
load_dotenv()


# Configuration
# Using Claude Opus 4.5 as default for best coding and agentic performance
# See: https://www.anthropic.com/news/claude-opus-4-5
DEFAULT_MODEL = "claude-opus-4-5-20251101"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Coding Agent Demo - Long-running agent harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start fresh project
  python autonomous_agent_demo.py --project-dir ./claude_clone

  # Use a specific model
  python autonomous_agent_demo.py --project-dir ./claude_clone --model claude-sonnet-4-5-20250929

  # Limit iterations for testing
  python autonomous_agent_demo.py --project-dir ./claude_clone --max-iterations 5

  # Continue existing project
  python autonomous_agent_demo.py --project-dir ./claude_clone

  # Add new specifications to existing project
  python autonomous_agent_demo.py --project-dir ./claude_clone --new-spec app_spec_new1.txt

Configuration (.env file):
  CLAUDE_CODE_OAUTH_TOKEN    Claude Code OAuth token (required)
  LINEAR_API_KEY             Linear API key (required)
  LINEAR_TEAM_ID             Linear Team ID (optional)
        """,
    )

    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("./autonomous_demo_project"),
        help="Directory for the project (default: generations/autonomous_demo_project). Relative paths automatically placed in generations/ directory.",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of agent iterations (default: unlimited)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--new-spec",
        type=str,
        default=None,
        help="Name of new specification file to add (e.g., 'app_spec_new1.txt'). Use this to add new features to an existing project.",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Check for Claude Code OAuth token
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("Error: CLAUDE_CODE_OAUTH_TOKEN not found in .env file")
        print("\n1. Run 'claude setup-token' after installing the Claude Code CLI")
        print("2. Copy .env.example to .env")
        print("3. Add your token to .env: CLAUDE_CODE_OAUTH_TOKEN='your-token-here'")
        return

    # Check for Linear API key
    if not os.environ.get("LINEAR_API_KEY"):
        print("Error: LINEAR_API_KEY not found in .env file")
        print("\n1. Get your API key from: https://linear.app/YOUR-TEAM/settings/api")
        print("2. Add it to .env: LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'")
        return

    # Automatically place projects in generations/ directory unless already specified
    project_dir = args.project_dir
    if not str(project_dir).startswith("generations/"):
        # Convert relative paths to be under generations/
        if project_dir.is_absolute():
            # If absolute path, use as-is
            pass
        else:
            # Prepend generations/ to relative paths
            project_dir = Path("generations") / project_dir

    # Run the agent
    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                model=args.model,
                max_iterations=args.max_iterations,
                new_spec_filename=args.new_spec,
            )
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print("To resume, run the same command again")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()
