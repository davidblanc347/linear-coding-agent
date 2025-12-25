# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an autonomous coding agent framework that uses Claude Agent SDK with Linear integration for project management. The framework enables long-running autonomous development sessions where agents create complete applications from XML specifications.

**Key Architecture**: Two-agent pattern (Initializer + Coding Agent) with Linear as the single source of truth for project state and progress tracking.

## Common Commands

### Running the Agent

```bash
# Fresh project initialization
python autonomous_agent_demo.py --project-dir ./my_project

# Continue existing project
python autonomous_agent_demo.py --project-dir ./my_project

# Add new features to existing project (Initializer Bis)
python autonomous_agent_demo.py --project-dir ./my_project --new-spec app_spec_theme_customization.txt

# Limit iterations for testing
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

### Testing

```bash
# Run security hook tests
python test_security.py

# Test mypy type checking (for library projects)
mypy path/to/module.py
```

### Environment Setup

```bash
# Generate Claude Code OAuth token
claude setup-token

# Install dependencies
pip install -r requirements.txt
```

## High-Level Architecture

### Core Agent Flow

1. **First Run (Initializer Agent)**:
   - Reads `prompts/app_spec.txt` specification
   - Creates Linear project and ~50 issues (one per `<feature_X>` tag)
   - Creates META issue for session tracking
   - Initializes project structure with `init.sh`
   - Writes `.linear_project.json` marker file

2. **Subsequent Runs (Coding Agent)**:
   - Queries Linear for highest-priority Todo issue
   - Updates issue status to "In Progress"
   - Implements feature using SDK tools
   - Tests implementation (Puppeteer for web apps, pytest/mypy for libraries)
   - Adds comment to Linear issue with implementation notes
   - Marks issue as "Done"
   - Updates META issue with session summary

3. **Initializer Bis (Add Features)**:
   - Triggered by `--new-spec` flag on existing projects
   - Reads new spec file from `prompts/`
   - Creates additional Linear issues for new features
   - Updates existing project without re-initializing

### Key Design Patterns

**Session Handoff via Linear**: Agents don't use local state files for coordination. All session context, implementation notes, and progress tracking happens through Linear issues and comments. This provides:
- Real-time visibility in Linear workspace
- Persistent history across sessions
- Easy debugging via issue comments

**Defense-in-Depth Security** (see `security.py` and `client.py`):
1. OS-level sandbox for bash command isolation
2. Filesystem restrictions (operations limited to project directory)
3. Bash command allowlist with pre-tool-use hooks
4. Explicit MCP tool permissions

**Project Type Detection** (`agent.py:is_library_project`):
- Detects library/type-safety projects vs full-stack web apps
- Uses different coding prompts (`coding_prompt_library.md` vs `coding_prompt.md`)
- Keywords: "type safety", "docstrings", "mypy", "library rag"

### Module Responsibilities

- **`autonomous_agent_demo.py`**: Entry point, argument parsing, environment validation
- **`agent.py`**: Core agent loop, session orchestration, project type detection
- **`client.py`**: Claude SDK client configuration, MCP server setup (Linear + Puppeteer)
- **`security.py`**: Bash command validation with allowlist, pre-tool-use hooks
- **`prompts.py`**: Prompt loading utilities, spec file copying
- **`progress.py`**: Progress tracking via `.linear_project.json` marker
- **`linear_config.py`**: Linear API configuration constants

### MCP Servers

**Linear** (HTTP transport at `mcp.linear.app/mcp`):
- Project/team management
- Issue CRUD operations
- Comments and status updates
- Requires `LINEAR_API_KEY` in `.env`

**Puppeteer** (stdio transport):
- Browser automation for UI testing
- Navigate, screenshot, click, fill, evaluate
- Used by web app projects, not library projects

## Application Specification Format

Specifications use XML format in `prompts/app_spec.txt`:

```xml
<project_specification>
  <project_name>Your App Name</project_name>
  <overview>Detailed description...</overview>

  <technology_stack>
    <frontend>...</frontend>
    <backend>...</backend>
  </technology_stack>

  <core_features>
    <feature_1>
      <title>Feature title</title>
      <description>Detailed description</description>
      <priority>1-4 (1=urgent, 4=low)</priority>
      <category>frontend|backend|auth|etc</category>
      <test_steps>
        1. Step one
        2. Step two
      </test_steps>
    </feature_1>
    <!-- More features... -->
  </core_features>
</project_specification>
```

**Important**: Each `<feature_X>` tag becomes a separate Linear issue. The initializer creates exactly one issue per feature tag.

## Environment Configuration

All configuration via `.env` file (copy from `.env.example`):

```bash
CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'  # From: claude setup-token
LINEAR_API_KEY='lin_api_xxxxx'              # From: linear.app/settings/api
LINEAR_TEAM_ID='team-id'                    # Optional, agent prompts if missing
```

## Security Model

### Allowed Commands (`security.py:ALLOWED_COMMANDS`)

File operations: `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `cp`, `mkdir`, `chmod`
Development: `npm`, `node`, `python`, `python3`, `mypy`, `pytest`
Version control: `git`
Process management: `ps`, `lsof`, `sleep`, `pkill`
Scripts: `init.sh`

### Additional Validation

- **`pkill`**: Only allowed for dev processes (node, npm, vite, next)
- **`chmod`**: Only `+x` mode permitted (making scripts executable)
- **`init.sh`**: Must be `./init.sh` or end with `/init.sh`

### Adding New Commands

Edit `security.py:ALLOWED_COMMANDS` and optionally add validation logic to `bash_security_hook`.

## Generated Project Structure

After initialization, projects contain:

```
my_project/
├── .linear_project.json      # Linear state marker (project_id, total_issues, meta_issue_id)
├── .claude_settings.json     # Security settings (auto-generated)
├── app_spec.txt              # Original specification (copied from prompts/)
├── init.sh                   # Environment setup script (executable)
└── [generated code]          # Application files created by agent
```

## Creating New Applications

1. Create `prompts/app_spec.txt` with your XML specification
2. Use existing spec files as templates (see `prompts/app_spec.txt` for Claude Clone example)
3. Run: `python autonomous_agent_demo.py --project-dir ./new_app`
4. Monitor progress in Linear workspace

See `GUIDE_NEW_APP.md` for detailed guide (French).

## Prompt Templates

Located in `prompts/`:

- **`initializer_prompt.md`**: First session prompt (creates Linear project/issues)
- **`initializer_bis_prompt.md`**: Add features prompt (extends existing project)
- **`coding_prompt.md`**: Standard coding session (web apps with Puppeteer testing)
- **`coding_prompt_library.md`**: Library coding session (focuses on types/docs, uses pytest/mypy)

The framework automatically selects the appropriate prompt based on session type and project detection.

## Important Implementation Notes

### Linear Integration

- All work tracked as Linear issues, not local files
- Session handoff via Linear comments on META issue
- Status workflow: Todo → In Progress → Done
- Early termination: Agent stops when detecting "feature-complete" in responses

### Auto-Continue Behavior

Agent auto-continues with 3-second delay between sessions (`agent.py:AUTO_CONTINUE_DELAY_SECONDS`). Stops when:
- `--max-iterations` limit reached
- Response contains "feature-complete" or "all issues completed"
- Fatal error occurs

### Project Directory Handling

Relative paths automatically placed under `generations/` directory unless absolute path provided.

### Model Selection

Default: `claude-opus-4-5-20251101` (Opus 4.5 for best coding performance)
Override with: `--model claude-sonnet-4-5-20250929`
