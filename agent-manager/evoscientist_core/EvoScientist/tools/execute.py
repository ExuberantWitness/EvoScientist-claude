"""Shell execute tool for sub-agents.

Wraps the backend's execute() method as a LangChain tool so
sub-agents can run shell commands (e.g., paper-navigator scripts).
"""

from langchain_core.tools import tool


@tool
def execute(command: str, timeout: int = 120) -> str:
    """Execute a shell command and return the output.

    Use this to run Python scripts, install packages, or perform system operations.
    The command runs in the workspace directory with a default 120s timeout.

    Args:
        command: Shell command to execute.
        timeout: Maximum execution time in seconds (default 120, max 300).
    """
    import asyncio
    timeout = min(timeout, 300)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    # Use subprocess for sync execution context
    import subprocess
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        if len(output) > 50_000:
            output = output[:50_000] + "\n... [truncated]"
        return output
    except subprocess.TimeoutExpired:
        return f"[Command timed out after {timeout}s]"
    except Exception as e:
        return f"Error: {e}"
