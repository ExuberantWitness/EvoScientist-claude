#!/usr/bin/env python3
"""Audit agent method signatures before BaseAlgorithm enforcement.

Scans artifacts/ for agent classes, extracts method signatures,
and reports mismatches against the expected BaseAlgorithm interface.

Usage:
  python scripts/audit_agent_methods.py [artifacts_dir]
"""

import ast
import sys
from pathlib import Path

EXPECTED_METHODS = {
    "select_action": {"min_params": 2, "max_params": 3},  # self, obs, [deterministic]
    "train": {"min_params": 2, "max_params": 4},  # self, replay_buffer, [batch_size]
    "save": {"min_params": 2, "max_params": 2},  # self, path
    "load": {"min_params": 2, "max_params": 2},  # self, path
}


def scan_file(filepath: Path) -> list[dict]:
    """Scan a .py file for agent classes and their methods."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    results = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Agent classes end with "Agent"
        if not node.name.endswith("Agent"):
            continue

        methods_found = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                params = [a.arg for a in item.args.args]
                methods_found[item.name] = {
                    "params": params,
                    "param_count": len(params),
                }

        results.append({
            "class_name": node.name,
            "file": str(filepath),
            "methods": methods_found,
        })

    return results


def audit(artifacts_dir: Path) -> dict:
    """Audit all agent files. Returns report dict."""
    report = {"agents": [], "mismatches": [], "summary": {}}

    for py_file in sorted(artifacts_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        agents = scan_file(py_file)
        if not agents:
            continue

        for agent in agents:
            report["agents"].append(agent)
            missing = []
            signature_mismatch = []

            for method_name, expected in EXPECTED_METHODS.items():
                if method_name not in agent["methods"]:
                    missing.append(method_name)
                else:
                    actual = agent["methods"][method_name]
                    n = actual["param_count"]
                    if n < expected["min_params"] or n > expected["max_params"]:
                        signature_mismatch.append(
                            f"{method_name}({', '.join(actual['params'])}) "
                            f"— expected {expected['min_params']}-{expected['max_params']} params"
                        )

            if missing or signature_mismatch:
                report["mismatches"].append({
                    "class": agent["class_name"],
                    "file": agent["file"],
                    "missing_methods": missing,
                    "signature_mismatches": signature_mismatch,
                })

    total = len(report["agents"])
    mismatched = len(report["mismatches"])
    report["summary"] = {
        "total_agents": total,
        "agents_ok": total - mismatched,
        "agents_with_mismatches": mismatched,
        "ready_for_basealgorithm": mismatched == 0,
    }

    return report


def main():
    artifacts_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/artifacts"
    )

    if not artifacts_dir.is_dir():
        print(f"ERROR: {artifacts_dir} not found")
        sys.exit(2)

    report = audit(artifacts_dir)

    print("=" * 60)
    print("Agent Method Audit Report")
    print("=" * 60)

    for agent in report["agents"]:
        methods = ", ".join(agent["methods"].keys())
        print(f"\n  {agent['class_name']} ({agent['file']})")
        for name, info in agent["methods"].items():
            sig = f"{name}({', '.join(info['params'])})"
            status = "✓" if name in EXPECTED_METHODS else "?"
            print(f"    {status} {sig}")

    if report["mismatches"]:
        print("\n" + "!" * 60)
        print("MISMATCHES FOUND — must fix before Phase 0b:")
        print("!" * 60)
        for m in report["mismatches"]:
            print(f"\n  {m['class']} ({m['file']})")
            for method in m["missing_methods"]:
                print(f"    ✗ MISSING: {method}")
            for sig in m["signature_mismatches"]:
                print(f"    ⚠ SIGNATURE: {sig}")
    else:
        print("\n" + "✓" * 60)
        print("All agents match BaseAlgorithm interface. Ready for Phase 0b.")
        print("✓" * 60)

    print(f"\nSummary: {report['summary']['agents_ok']}/{report['summary']['total_agents']} agents OK, "
          f"{report['summary']['agents_with_mismatches']} with mismatches")

    if not report["summary"]["ready_for_basealgorithm"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
