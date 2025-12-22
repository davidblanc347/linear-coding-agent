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

Create a `.env` file in the root directory by copying the example:

```bash
cp .env.example .env
```

Then configure your credentials in the `.env` file:

**1. Claude Code OAuth Token:**
```bash
# Generate the token using Claude Code CLI
claude setup-token

# Add to .env file:
CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token-here'
```

**2. Linear API Key:**
```bash
# Get your API key from: https://linear.app/YOUR-TEAM/settings/api
# Add to .env file:
LINEAR_API_KEY='lin_api_xxxxxxxxxxxxx'

# Optional: Linear Team ID (if not set, agent will list teams)
LINEAR_TEAM_ID='your-team-id'
```

**Important:** The `.env` file is already in `.gitignore` - never commit it!

### 3. Verify Installation

```bash
claude --version  # Should be latest version
pip show claude-code-sdk  # Check SDK is installed
```

## Quick Start

### Option 1: Use the Example (Claude Clone)

```bash
# Initialize the Claude Clone example project
python autonomous_agent_demo.py --project-dir ./my_project

# Add new features to an existing project
python autonomous_agent_demo.py --project-dir ./my_project --new-spec app_spec_theme_customization.txt
```

For testing with limited iterations:
```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

### Option 2: Create Your Own Application

See the [Creating a New Application](#creating-a-new-application) section below for detailed instructions on creating a custom application from scratch.

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

## Configuration (.env file)

All configuration is done via a `.env` file in the root directory.

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token (from `claude setup-token`) | Yes |
| `LINEAR_API_KEY` | Linear API key for MCP access | Yes |
| `LINEAR_TEAM_ID` | Linear Team ID (if not set, agent will list teams and ask) | No |

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

## Creating a New Application

This framework is designed to be **generic and reusable** for any web application. Here's how to create your own application from scratch.

### Understanding the Framework Structure

#### Generic Framework Files (DO NOT MODIFY)

These files work for all applications and should remain unchanged:

```
linear-coding-agent/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK + MCP client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── linear_config.py          # Linear configuration constants
├── requirements.txt          # Python dependencies
└── prompts/
    ├── initializer_prompt.md      # First session prompt template
    ├── initializer_bis_prompt.md  # New features prompt template
    └── coding_prompt.md           # Continuation session prompt template
```

#### Application-Specific Files (CREATE THESE)

The **only file you need to create** is your application specification:

```
prompts/
└── app_spec.txt  # Your application specification (XML format)
```

### Step-by-Step Guide

#### Step 1: Create Your Specification File

Create `prompts/app_spec.txt` using this XML structure:

```xml
<project_specification>
  <project_name>Your Application Name</project_name>

  <overview>
    Complete description of your application. Explain what you want to build,
    main objectives, and key features.
  </overview>

  <technology_stack>
    <frontend>
      <framework>React with Vite</framework>
      <styling>Tailwind CSS</styling>
      <state_management>React hooks</state_management>
    </frontend>
    <backend>
      <runtime>Node.js with Express</runtime>
      <database>SQLite</database>
    </backend>
  </technology_stack>

  <prerequisites>
    <environment_setup>
      - List of prerequisites (dependencies, API keys, etc.)
    </environment_setup>
  </prerequisites>

  <core_features>
    <feature_1>
      <title>Feature 1 Title</title>
      <description>Detailed description</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Test step 1
        2. Test step 2
      </test_steps>
    </feature_1>

    <feature_2>
      <!-- More features -->
    </feature_2>
  </core_features>
</project_specification>
```

#### Step 2: Define Your Features

Each feature should have:

- **Title**: Clear, descriptive title
- **Description**: Complete explanation of what it does
- **Priority**: 1 (urgent) to 4 (optional)
- **Category**: `frontend`, `backend`, `database`, `auth`, `integration`, etc.
- **Test Steps**: Precise verification steps

Example feature:

```xml
<feature_1>
  <title>User Authentication - Login Flow</title>
  <description>
    Implement authentication system with:
    - Login form (email/password)
    - Client and server-side validation
    - JWT session management
    - Password reset page
  </description>
  <priority>1</priority>
  <category>auth</category>
  <test_steps>
    1. Access login page
    2. Enter invalid email → see error
    3. Enter valid credentials → redirect to dashboard
    4. Verify JWT token is stored
    5. Test logout functionality
  </test_steps>
</feature_1>
```

#### Step 3: Launch Initialization

Once your `app_spec.txt` is ready:

```bash
python autonomous_agent_demo.py --project-dir ./my_new_app
```

The initializer agent will:
1. Read your `app_spec.txt`
2. Create a Linear project
3. Create ~50 Linear issues based on your spec
4. Initialize project structure, `init.sh`, and git

#### Step 4: Monitor Development

Coding agents will then:
- Work on Linear issues one by one
- Implement features
- Test with Puppeteer browser automation
- Update issues with implementation comments
- Mark issues as complete

### Minimal Example

Here's a minimal Todo App example to get started:

```xml
<project_specification>
  <project_name>Todo App - Task Manager</project_name>

  <overview>
    Simple web application for managing task lists.
    Users can create, edit, complete, and delete tasks.
  </overview>

  <technology_stack>
    <frontend>
      <framework>React with Vite</framework>
      <styling>Tailwind CSS</styling>
    </frontend>
    <backend>
      <runtime>Node.js with Express</runtime>
      <database>SQLite</database>
    </backend>
  </technology_stack>

  <core_features>
    <feature_1>
      <title>Main Interface - Task List</title>
      <description>Display a list of all tasks with their status</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Open application
        2. Verify task list displays
      </test_steps>
    </feature_1>

    <feature_2>
      <title>Create New Task</title>
      <description>Form to add a new task to the list</description>
      <priority>1</priority>
      <category>frontend</category>
      <test_steps>
        1. Click "New Task"
        2. Enter a title
        3. Click "Add"
        4. Verify task appears in list
      </test_steps>
    </feature_2>
  </core_features>
</project_specification>
```

### Best Practices

#### 1. Be Detailed but Structured

Each feature must have:
- Clear title
- Complete description of functionality
- Precise test steps
- Priority (1=urgent, 4=optional)

#### 2. Use Consistent XML Format

Follow the structure shown above for all features using `<feature_X>` tags.

#### 3. Organize by Categories

Group features by category:
- `auth`: Authentication
- `frontend`: User interface
- `backend`: API and server logic
- `database`: Models and migrations
- `integration`: External integrations

#### 4. Prioritize Features

- **Priority 1**: Critical features (auth, database)
- **Priority 2**: Important features (core functionality)
- **Priority 3**: Secondary features (UX improvements)
- **Priority 4**: Nice-to-have (polish, optimizations)

### Using the Claude Clone as Reference

The Claude Clone example in `prompts/app_spec.txt` is excellent reference material:

#### ✅ Elements to Copy/Adapt:

1. **XML Structure**: Overall structure with `<project_specification>`, `<overview>`, `<technology_stack>`, etc.
2. **Feature Format**: How to structure `<feature_X>` tags with all required fields
3. **Technical Details**: How to describe technology stack, prerequisites, API endpoints, database schema, UI specs

#### ❌ Elements NOT to Copy:

1. **Specific Content**: Details about "Claude API", "artifacts", "conversations" are app-specific
2. **Business Features**: Adapt features to your application's needs

### Checklist for New Application

- [ ] Create `prompts/app_spec.txt` with your specification
- [ ] Define `<project_name>` for your application
- [ ] Write complete `<overview>`
- [ ] Specify `<technology_stack>` (frontend + backend)
- [ ] List all `<prerequisites>`
- [ ] Define all `<core_features>` with `<feature_X>` tags
- [ ] Add `<test_steps>` for each feature
- [ ] Launch: `python autonomous_agent_demo.py --project-dir ./my_app`
- [ ] Verify in Linear that issues are created correctly

## Customization

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

**"CLAUDE_CODE_OAUTH_TOKEN not found in .env file"**
1. Run `claude setup-token` to generate a token
2. Copy `.env.example` to `.env`
3. Add your token to the `.env` file

**"LINEAR_API_KEY not found in .env file"**
1. Get your API key from `https://linear.app/YOUR-TEAM/settings/api`
2. Add it to your `.env` file

**"Appears to hang on first run"**
Normal behavior. The initializer is creating a Linear project and 50 issues with detailed descriptions. Watch for `[Tool: mcp__linear__create_issue]` output.

**"Command blocked by security hook"**
The agent tried to run a disallowed command. Add it to `ALLOWED_COMMANDS` in `security.py` if needed.

**"MCP server connection failed"**
Verify your `LINEAR_API_KEY` in the `.env` file is valid and has appropriate permissions. The Linear MCP server uses HTTP transport at `https://mcp.linear.app/mcp`.

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
