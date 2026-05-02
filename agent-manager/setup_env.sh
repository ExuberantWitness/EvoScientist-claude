#!/usr/bin/env bash
# Setup conda environment for EvoScientist Agent Manager
set -euo pipefail

ENV_NAME="${1:-evo-agents}"
PYTHON_VER="${2:-3.11}"

echo "=== EvoScientist Agent Manager: Environment Setup ==="
echo "  Conda env: $ENV_NAME"
echo "  Python:    $PYTHON_VER"
echo ""

# Check conda
if ! command -v conda &>/dev/null; then
    echo "ERROR: conda not found. Install miniconda first:"
    echo "  https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# Create env (skip if exists)
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "Conda env '$ENV_NAME' already exists. Updating..."
else
    echo "Creating conda env '$ENV_NAME'..."
    conda create -n "$ENV_NAME" python="$PYTHON_VER" -y
fi

echo ""
echo "Installing dependencies..."
conda run --no-banner -n "$ENV_NAME" pip install \
    "deepagents>=0.4.11" \
    "langchain>=1.2.12" \
    "langchain-anthropic>=1.4.0" \
    "langgraph>=0.4" \
    "langgraph-checkpoint-sqlite>=3.0.0" \
    "mcp>=1.0.0" \
    "httpx>=0.27" \
    "pyyaml>=6.0" \
    "python-dotenv>=1.0" \
    "rich>=14.0"

echo ""
echo "Optional: Install OpenAI support? (for multi-model review)"
echo "  conda run -n $ENV_NAME pip install langchain-openai>=1.1"
echo ""
echo "Optional: Install web search?"
echo "  conda run -n $ENV_NAME pip install tavily-python"
echo ""
echo "=== Environment setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Extract core modules:  ./extract_core.sh /path/to/EvoScientist-main"
echo "  2. Register MCP server:   ./register_mcp.sh"
