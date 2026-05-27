"""Helper script to restart the dashboard. Spawned by restart_api endpoint."""
import subprocess
import sys
import time
from pathlib import Path

PORT = 8420
AGENT_MGR_DIR = Path(__file__).resolve().parent
LAUNCHER = AGENT_MGR_DIR / "start_dashboard_standalone.py"
PYTHON = sys.executable
LOG = "/tmp/evo-dashboard-restart.log"


def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")


# 1. Wait for HTTP response to flush
with open(LOG, "w") as f:
    f.write("")
log(f"Restart started. Python={PYTHON}")
time.sleep(2)

# 2. Kill Python processes on port
try:
    lsof = subprocess.run(["lsof", "-ti", f":{PORT}"], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in lsof.stdout.strip().split("\n") if p.strip()]
    for pid in pids:
        comm = subprocess.run(["ps", "-o", "comm=", "-p", pid], capture_output=True, text=True, timeout=3)
        if "python" in comm.stdout.lower():
            subprocess.run(["kill", "-9", pid], capture_output=True, timeout=3)
            log(f"Killed PID {pid}")
    time.sleep(1)
except Exception as e:
    log(f"Kill error: {e}")

# 3. Launch new dashboard immediately (uvicorn uses SO_REUSEADDR)
try:
    with open("/tmp/evo-dashboard.log", "w") as out:
        proc = subprocess.Popen(
            [PYTHON, str(LAUNCHER)],
            cwd=str(AGENT_MGR_DIR),
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log(f"New dashboard PID: {proc.pid}")
except Exception as e:
    log(f"Launch failed: {e}")
