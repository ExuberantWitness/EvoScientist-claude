#!/usr/bin/env python3
"""BGE-M3 embedding socket service.

Pure embedding computation daemon — no database access.
Uses RNDEvaluator as the sole BGE-M3 model owner.

Protocol (JSON-line over Unix socket):
  {"action":"embed","texts":["..."]}  →  {"embeddings":[[1024 floats]]}
  {"action":"ping"}  →  {"status":"ok"}

Usage:
  python tools/bge_socket_server.py --workspace /path/to/workspace
  python tools/bge_socket_server.py --socket /path/to/socket
"""

import argparse
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BGE-SOCKET] %(message)s")
logger = logging.getLogger("bge_socket")

DEFAULT_SOCKET_NAME = "bge_socket.sock"


def get_rnd_evaluator():
    """Lazy-import RNDEvaluator with best available embedding provider."""
    from pes_controller.embedding_provider import get_embedding_provider
    from pes_controller.elo.neighborhood import RNDEvaluator
    provider = get_embedding_provider()
    return RNDEvaluator(provider=provider)


def _load_model(rnd):
    """Force model loading."""
    _ = rnd.model
    return rnd


def _embed_texts(rnd, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, return list of 1024-dim float lists."""
    if not texts:
        return []
    vecs = rnd._encode(texts)
    return vecs.tolist()


def handle_request(rnd, data: dict) -> dict:
    """Process a single JSON request, return JSON response."""
    action = data.get("action", "")

    if action == "ping":
        return {"status": "ok"}

    elif action == "embed":
        texts = data.get("texts", [])
        embeddings = _embed_texts(rnd, texts)
        return {"embeddings": embeddings}

    else:
        return {"error": f"unknown action: {action}"}


def run_server(socket_path: str):
    """Start Unix socket server, process requests until interrupted."""
    sock_path = Path(socket_path)
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale socket
    if sock_path.exists():
        sock_path.unlink()

    logger.info(f"Loading BGE-M3 model...")
    rnd = get_rnd_evaluator()
    _load_model(rnd)
    logger.info("BGE-M3 model ready")

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(5)
    logger.info(f"Listening on {socket_path}")

    try:
        while True:
            conn, _ = server.accept()
            try:
                # Read until newline (JSON-line protocol)
                buf = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break

                if not buf:
                    conn.close()
                    continue

                # Parse request (handle possible multiple lines)
                for line in buf.decode("utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        request = json.loads(line)
                        response = handle_request(rnd, request)
                    except json.JSONDecodeError as e:
                        response = {"error": f"JSON parse error: {e}"}
                    except Exception as e:
                        logger.error(f"Request error: {e}")
                        response = {"error": str(e)}

                    resp_bytes = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
                    conn.sendall(resp_bytes)
            except Exception as e:
                logger.error(f"Connection error: {e}")
            finally:
                conn.close()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.close()
        if sock_path.exists():
            sock_path.unlink()
        logger.info("Server stopped")


def main():
    parser = argparse.ArgumentParser(description="BGE-M3 embedding socket service")
    parser.add_argument("--workspace", help="Workspace directory (sets socket path to workspace/_index/bge_socket.sock)")
    parser.add_argument("--socket", help="Explicit socket path")
    args = parser.parse_args()

    if args.socket:
        socket_path = args.socket
    elif args.workspace:
        socket_path = str(Path(args.workspace) / "_index" / DEFAULT_SOCKET_NAME)
    else:
        print("ERROR: must specify --workspace or --socket", file=sys.stderr)
        sys.exit(1)

    run_server(socket_path)


if __name__ == "__main__":
    main()
