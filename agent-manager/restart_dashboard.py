"""Helper script to restart the dashboard. Spawned by restart_api endpoint."""
import subprocess
import sys
import time
import socket
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
log(f"Restart started. Python={PYTHON}, Launcher={LAUNCHER}")
time.sleep(2)

# 2. Kill Python processes on port
try:
    lsof = subprocess.run(["lsof", "-ti", f":{PORT}"], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in lsof.stdout.strip().split("\n") if p.strip()]
    for pid in pids:
        comm = subprocess.run(["ps", "-o", "comm=", "-p", pid], capture_output=True, text=True, timeout=3)
        if "python" in comm.stdout.lower():
            subprocess.run(["kill", pid], capture_output=True, timeout=3)
            log(f"Killed PID {pid}")
except Exception as e:
    log(f"Kill error: {e}")

# 3. Wait for port to free
for i in range(30):
    time.sleep(0.5)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("0.0.0.0", PORT))
            log(f"Port freed after {i+1} attempts")
            break
    except OSError:
        continue
else:
    log("Port not freed after 15s")

# 4. Launch new dashboard
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
