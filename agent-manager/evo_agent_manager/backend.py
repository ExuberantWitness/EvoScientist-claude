"""
UnrestrictedBackend — Replaces EvoScientist's CustomSandboxBackend.

Removes path blacklists and command restrictions so conda, GPU tools,
and system paths work. Keeps timeout and output limits as safety nets.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class UnrestrictedBackend:
    """Shell backend without sandbox restrictions.

    Unlike CustomSandboxBackend, this does NOT block:
    - conda/pip commands
    - System paths (/opt/, ~/,  /home/, etc.)
    - sudo, chmod, and other system commands

    It DOES keep:
    - Command timeout (default 300s)
    - Output size limit (default 100KB)
    - Command logging to command_log.md
    """

    def __init__(
        self,
        root_dir: str = ".",
        *,
        timeout: int = 300,
        max_output_bytes: int = 100_000,
        log_commands: bool = True,
    ):
        self.root_dir = str(Path(root_dir).resolve())
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.log_commands = log_commands

    async def execute(self, command: str, timeout: int | None = None) -> dict:
        """Execute a shell command without sandbox restrictions."""
        timeout = timeout or self.timeout

        if self.log_commands:
            self._log_command(command)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.root_dir,
                env={**os.environ},
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "exit_code": 124,
                    "output": f"[Command timed out after {timeout}s]\n"
                    "Tip: For long tasks, run in background:\n"
                    "  nohup <command> > output.log 2>&1 &",
                }

            output = stdout.decode("utf-8", errors="replace")

            if len(output) > self.max_output_bytes:
                output = (
                    output[: self.max_output_bytes]
                    + f"\n... [output truncated at {self.max_output_bytes} bytes]"
                )

            return {
                "exit_code": proc.returncode,
                "output": output,
            }

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return {
                "exit_code": 1,
                "output": f"Execution error: {e}",
            }

    def execute_sync(self, command: str, timeout: int | None = None) -> dict:
        """Synchronous version for contexts without event loop."""
        timeout = timeout or self.timeout

        if self.log_commands:
            self._log_command(command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.root_dir,
                env={**os.environ},
            )
            output = result.stdout + result.stderr
            if len(output) > self.max_output_bytes:
                output = output[: self.max_output_bytes] + "\n... [truncated]"

            return {"exit_code": result.returncode, "output": output}

        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "output": f"[Timed out after {timeout}s]"}
        except Exception as e:
            return {"exit_code": 1, "output": f"Error: {e}"}

    def _log_command(self, command: str):
        """Append command to command_log.md in workspace."""
        try:
            from .utils import now_iso
            log_path = Path(self.root_dir) / "command_log.md"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"- `{now_iso()}` `{command}`\n")
        except Exception:
            pass  # Non-critical, don't fail on logging errors
