# Autonomous Coding Agent Demo (Linear-Integrated)

A minimal harness demonstrating long-running autonomous coding with the Claude Agent SDK. This demo implements a two-agent pattern (initializer + coding agent) with **Linear as the core project management system** for tracking all work.

## Key Features

- **Linear Integration**: All work is tracked as Linear issues, not local files
- **Real-time Visibility**: Watch agent progress directly in your Linear workspace
- **Session Handoff**: Agents communicate via Linear comments, not text files
- **Two-Agent Pattern**: Initializer creates Linear project & issues, coding agents implement them
- **Initializer Bis**: Add new features to existing projects without re-initializing
- **Browser Testing**: Puppeteer MCP for UI verification
- **Claude Opus 4.5**: Uses Claude's most capable model by default

## Prerequisites

### 1. Install Claude Code CLI and Python SDK

```bash
# Install Claude Code CLI (latest version required)
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set Up Authentication

You need two authentication tokens:

**Claude Code OAuth Token:**
```bash
# Generate the token using Claude Code CLI
claude setup-token

# Set the environment variable
export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token-here'
```

**Linear API Key:**
```bash
# Get your API key from: https://linear.app/YOUR-TEAM/settings/api
export LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'
```

### 3. Verify Installation

```bash
claude --version  # Should be latest version
pip show claude-code-sdk  # Check SDK is installed
```

## Quick Start

```bash
# Initialize a new project
python autonomous_agent_demo.py --project-dir ./my_project

# Add new features to an existing project
python autonomous_agent_demo.py --project-dir ./my_project --new-spec app_spec_theme_customization.txt
```

For testing with limited iterations:
```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

## How It Works

### Linear-Centric Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    LINEAR-INTEGRATED WORKFLOW               │
├─────────────────────────────────────────────────────────────┤
│  app_spec.txt ──► Initializer Agent ──► Linear Issues (50) │
│                                              │               │
│                    ┌─────────────────────────▼──────────┐   │
│                    │        LINEAR WORKSPACE            │   │
│                    │  ┌────────────────────────────┐    │   │
│                    │  │ Issue: Auth - Login flow   │    │   │
│                    │  │ Status: Todo → In Progress │    │   │
│                    │  │ Comments: [session notes]  │    │   │
│                    │  └────────────────────────────┘    │   │
│                    └────────────────────────────────────┘   │
│                                              │               │
│                    Coding Agent queries Linear              │
│                    ├── Search for Todo issues               │
│                    ├── Update status to In Progress         │
│                    ├── Implement & test with Puppeteer      │
│                    ├── Add comment with implementation notes│
│                    └── Update status to Done                │
└─────────────────────────────────────────────────────────────┘
```

### Two-Agent Pattern

1. **Initializer Agent (Session 1):**
   - Reads `app_spec.txt`
   - Lists teams and creates a new Linear project
   - Creates 50 Linear issues with detailed test steps
   - Creates a META issue for session tracking
   - Sets up project structure, `init.sh`, and git

2. **Coding Agent (Sessions 2+):**
   - Queries Linear for highest-priority Todo issue
   - Runs verification tests on previously completed features
   - Claims issue (status → In Progress)
   - Implements the feature
   - Tests via Puppeteer browser automation
   - Adds implementation comment to issue
   - Marks complete (status → Done)
   - Updates META issue with session summary

### Initializer Bis: Adding New Features

The **Initializer Bis** agent allows you to add new features to an existing project without re-initializing it. This is useful when you want to extend your application with additional functionality.

**How it works:**
1. Create a new specification file (e.g., `app_spec_theme_customization.txt`) in the `prompts/` directory
2. Run the agent with `--new-spec` flag pointing to your new spec file
3. The Initializer Bis agent will:
   - Read the existing project state from `.linear_project.json`
   - Read the new specification file
   - Create new Linear issues for each `<feature>` tag in the spec
   - Add these issues to the existing Linear project
   - Update the META issue with information about the new features
   - Copy the new spec file to the project directory

**Example:**
```bash
# Add theme customization features to an existing project
python autonomous_agent_demo.py --project-dir ./my_project --new-spec app_spec_theme_customization.txt
```

This will create multiple Linear issues (one per `<feature>` tag) that will be worked on by subsequent coding agent sessions.

### Session Handoff via Linear

Instead of local text files, agents communicate through:
- **Issue Comments**: Implementation details, blockers, context
- **META Issue**: Session summaries and handoff notes
- **Issue Status**: Todo / In Progress / Done workflow

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token (from `claude setup-token`) | Yes |
| `LINEAR_API_KEY` | Linear API key for MCP access | Yes |

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | Directory for the project | `./autonomous_demo_project` |
| `--max-iterations` | Max agent iterations | Unlimited |
| `--model` | Claude model to use | `claude-opus-4-5-20251101` |
| `--new-spec` | Name of new specification file to add (e.g., 'app_spec_new1.txt'). Use this to add new features to an existing project. | None |

## Project Structure

```
linear-agent-harness/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK + MCP client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── linear_config.py          # Linear configuration constants
├── prompts/
│   ├── app_spec.txt          # Application specification (Claude Clone example)
│   ├── app_spec_template.txt # Template for creating new applications
│   ├── app_spec_theme_customization.txt  # Example: Theme customization spec
│   ├── app_spec_mistral_extensible.txt   # Example: Mistral provider spec
│   ├── initializer_prompt.md # First session prompt (creates Linear issues)
│   ├── initializer_bis_prompt.md # Prompt for adding new features
│   └── coding_prompt.md      # Continuation session prompt (works issues)
├── GUIDE_NEW_APP.md          # Guide pour créer une nouvelle application
└── requirements.txt          # Python dependencies
```

## Generated Project Structure

After running, your project directory will contain:

```
my_project/
├── .linear_project.json      # Linear project state (marker file)
├── app_spec.txt              # Copied specification
├── app_spec_theme_customization.txt  # New spec file (if using --new-spec)
├── init.sh                   # Environment setup script
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## MCP Servers Used

| Server | Transport | Purpose |
|--------|-----------|---------|
| **Linear** | HTTP (Streamable HTTP) | Project management - issues, status, comments |
| **Puppeteer** | stdio | Browser automation for UI testing |

## Security Model

This demo uses defense-in-depth security (see `security.py` and `client.py`):

1. **OS-level Sandbox:** Bash commands run in an isolated environment
2. **Filesystem Restrictions:** File operations restricted to project directory
3. **Bash Allowlist:** Only specific commands permitted (npm, node, git, etc.)
4. **MCP Permissions:** Tools explicitly allowed in security settings

## Linear Setup

Before running, ensure you have:

1. A Linear workspace with at least one team
2. An API key with read/write permissions (from Settings > API)
3. The agent will automatically detect your team and create a project

The initializer agent will create:
- A new Linear project named after your app
- 50 feature issues based on `app_spec.txt`
- 1 META issue for session tracking and handoff

All subsequent coding agents will work from this Linear project.

## Customization

### Creating a New Application from Scratch

To create a **completely new application** (not based on the Claude Clone example):

1. **Read the guide**: See [GUIDE_NEW_APP.md](GUIDE_NEW_APP.md) for detailed instructions
2. **Use the template**: Copy `prompts/app_spec_template.txt` as a starting point
3. **Reference the example**: Use `prompts/app_spec.txt` (Claude Clone) as a reference for structure and detail level
4. **Create your spec**: Write your `prompts/app_spec.txt` with your application specification
5. **Launch**: Run `python autonomous_agent_demo.py --project-dir ./my_new_app`

**Key points:**
- Keep the framework files unchanged (they're generic and reusable)
- Only create/modify `prompts/app_spec.txt` for your new application
- Use the XML structure from the Claude Clone example as a template
- Define features with `<feature_X>` tags - each will become a Linear issue

### Changing the Application

Edit `prompts/app_spec.txt` to specify a different application to build.

### Adding New Features to Existing Projects

1. Create a new specification file in `prompts/` directory (e.g., `app_spec_new_feature.txt`)
2. Format it with `<feature>` tags following the same structure as `app_spec.txt`
3. Run with `--new-spec` flag:
   ```bash
   python autonomous_agent_demo.py --project-dir ./my_project --new-spec app_spec_new_feature.txt
   ```
4. The Initializer Bis agent will create new Linear issues for each feature in the spec file

### Adjusting Issue Count

Edit `prompts/initializer_prompt.md` and change "50 issues" to your desired count.

### Modifying Allowed Commands

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

## Troubleshooting

**"CLAUDE_CODE_OAUTH_TOKEN not set"**
Run `claude setup-token` to generate a token, then export it.

**"LINEAR_API_KEY not set"**
Get your API key from `https://linear.app/YOUR-TEAM/settings/api`

**"Appears to hang on first run"**
Normal behavior. The initializer is creating a Linear project and 50 issues with detailed descriptions. Watch for `[Tool: mcp__linear__create_issue]` output.

**"Command blocked by security hook"**
The agent tried to run a disallowed command. Add it to `ALLOWED_COMMANDS` in `security.py` if needed.

**"MCP server connection failed"**
Verify your `LINEAR_API_KEY` is valid and has appropriate permissions. The Linear MCP server uses HTTP transport at `https://mcp.linear.app/mcp`.

## Viewing Progress

Open your Linear workspace to see:
- The project created by the initializer agent
- All 50 issues organized under the project
- Real-time status changes (Todo → In Progress → Done)
- Implementation comments on each issue
- Session summaries on the META issue
- New issues added by Initializer Bis when using `--new-spec`

## License

MIT License - see [LICENSE](LICENSE) for details.
