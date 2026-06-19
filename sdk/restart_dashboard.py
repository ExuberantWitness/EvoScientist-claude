#!/usr/bin/env python3
"""Restart the dashboard process.

Kills the current dashboard on port 8420, then launches a new instance.
Called by the /api/restart endpoint.
"""
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PORT = 8420


def _kill_port_occupant():
    """Kill process on port 8420 (cross-platform)."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["netstat", "-aon"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{PORT}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    else:
        result = subprocess.run(
            ["lsof", "-ti", f":{PORT}"], capture_output=True, text=True, timeout=5,
        )
        for pid in result.stdout.strip().split():
            subprocess.run(["kill", pid], timeout=3)


if __name__ == "__main__":
    _kill_port_occupant()
    time.sleep(2)

    subprocess.Popen(
        [sys.executable, str(PROJECT / "run_dashboard.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
