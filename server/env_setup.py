import sys
import os

# Centralized path setup for the LeanBridge server monorepo.
# This ensures that the 'server' directory is always in sys.path,
# allowing for clean absolute-style imports (e.g., 'import config' or 'import agent.prompts')
# regardless of the execution context or current working directory.

def setup_environment():
    """Add the server root directory to sys.path if not already present."""
    # Get the directory of this file (server root)
    server_root = os.path.dirname(os.path.abspath(__file__))
    
    if server_root not in sys.path:
        sys.path.insert(0, server_root)
        
    # Also ensure the parent directory is in sys.path if we want to import from root (e.g. for testing)
    # But usually, keeping everything relative to 'server' is cleaner for the backend components.

# Auto-run on import to simplify usage: 'import env_setup'
setup_environment()
