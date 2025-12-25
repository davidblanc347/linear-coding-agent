"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
"""

import shutil
from pathlib import Path


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.md"
    return prompt_path.read_text()


def get_initializer_prompt() -> str:
    """Load the initializer prompt."""
    return load_prompt("initializer_prompt")


def get_coding_prompt() -> str:
    """Load the coding agent prompt."""
    return load_prompt("coding_prompt")


def get_coding_prompt_library() -> str:
    """Load the library-specific coding agent prompt (for type safety & documentation projects)."""
    return load_prompt("coding_prompt_library")


def copy_spec_to_project(project_dir: Path) -> None:
    """Copy the app spec file into the project directory for the agent to read."""
    spec_source = PROMPTS_DIR / "app_spec.txt"
    spec_dest = project_dir / "app_spec.txt"
    if not spec_dest.exists():
        shutil.copy(spec_source, spec_dest)
        print("Copied app_spec.txt to project directory")
        

############################################################################################
#  New specifications added  by davebb
############################################################################################

def get_initializer_bis_prompt() -> str:
    """Load the initializer bis prompt for adding new specifications."""
    return load_prompt("initializer_bis_prompt")


def copy_new_spec_to_project(project_dir: Path, new_spec_filename: str) -> None:
    """
    Copy a new specification file into the project directory for the agent to read.
    
    Args:
        project_dir: Project directory path
        new_spec_filename: Name of the new spec file (e.g., "app_spec_new1.txt")
    """
    spec_source = PROMPTS_DIR / new_spec_filename
    if not spec_source.exists():
        raise FileNotFoundError(f"New specification file not found: {spec_source}")
    
    spec_dest = project_dir / new_spec_filename
    shutil.copy(spec_source, spec_dest)
    print(f"Copied {new_spec_filename} to project directory")
