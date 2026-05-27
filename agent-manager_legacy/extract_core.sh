#!/usr/bin/env bash
# Extract EvoScientist core modules (skip CLI, channels, stt, etc.)
# Usage: ./extract_core.sh /path/to/EvoScientist-main

set -euo pipefail

SOURCE="${1:?Usage: $0 /path/to/EvoScientist-main}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/evoscientist_core/EvoScientist"

if [ ! -f "$SOURCE/EvoScientist/EvoScientist.py" ]; then
    echo "ERROR: $SOURCE/EvoScientist/EvoScientist.py not found"
    echo "Make sure the path points to the extracted EvoScientist-main directory"
    exit 1
fi

echo "Extracting EvoScientist core from: $SOURCE"
echo "Target: $TARGET"

rm -rf "$SCRIPT_DIR/evoscientist_core"
mkdir -p "$TARGET"

# Core files
for f in __init__.py EvoScientist.py prompts.py subagent.yaml paths.py utils.py sessions.py backends.py; do
    if [ -f "$SOURCE/EvoScientist/$f" ]; then
        cp "$SOURCE/EvoScientist/$f" "$TARGET/"
        echo "  copied $f"
    fi
done

# Core subdirectories
for d in llm middleware tools stream mcp config skills; do
    if [ -d "$SOURCE/EvoScientist/$d" ]; then
        cp -r "$SOURCE/EvoScientist/$d" "$TARGET/"
        echo "  copied $d/"
    fi
done

# Create package marker for evoscientist_core
touch "$SCRIPT_DIR/evoscientist_core/__init__.py"

# Count files
TOTAL=$(find "$TARGET" -type f | wc -l)
echo ""
echo "Done. Extracted $TOTAL files."
echo ""
echo "Skipped (not needed):"
echo "  cli/            — replaced by MCP server"
echo "  channels/       — Telegram/Slack/etc not needed"
echo "  stt.py          — speech-to-text not needed"
echo "  ccproxy_manager.py — OAuth proxy not needed"
echo "  update_check.py — version check not needed"
