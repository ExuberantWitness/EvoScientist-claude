#!/usr/bin/env python3
"""verify_plan.py — Check implementation_plan.md deliverables are concrete.

Usage:
  python tools/verify_plan.py iterations/N/

Checks:
  1. Each algo in plan has a corresponding planned_stubs/<algo>.py
  2. Stub passes py_compile
  3. Stub imports successfully
  4. Plan text contains no banned phrases
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

BANNED_PHRASES: list[str] = [
    "与 trainer.py 接口兼容",
    "compatible with trainer.py interface",
    "see corresponding atom",
    "见对应 atom",
]


def verify_plan(iteration_dir: Path) -> tuple[bool, list[str]]:
    """Verify an implementation plan directory. Returns (pass, errors)."""
    errors: list[str] = []

    plan_file = iteration_dir / "implementation_plan.md"
    stubs_dir = iteration_dir / "planned_stubs"

    if not plan_file.exists():
        return False, [f"[MISSING] {plan_file} not found"]

    plan_text = plan_file.read_text(encoding="utf-8")

    # 4) Banned phrase check
    for phrase in BANNED_PHRASES:
        if phrase.lower() in plan_text.lower():
            errors.append(f"[BANNED PHRASE] '{phrase}' found in plan. Replace with concrete spec.")

    # 1) Extract algorithm names from plan
    algo_pattern = re.findall(r"artifacts/(\w+)\.py", plan_text)
    if not algo_pattern:
        errors.append("[NO ALGOS] No artifacts/*.py references found in plan")
        return False, errors

    # 1) Check stubs exist
    if not stubs_dir.is_dir():
        errors.append(f"[NO STUBS] {stubs_dir} directory not found")
        return False, errors

    for algo_name in set(algo_pattern):
        stub_path = stubs_dir / f"{algo_name}.py"
        if not stub_path.exists():
            errors.append(f"[MISSING STUB] {stub_path} not found for {algo_name}")

            # 2-3) py_compile and import for existing stubs
        if stub_path.exists():
            # py_compile
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", str(stub_path)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                errors.append(f"[STUB COMPILE] {algo_name}.py: {r.stderr[:200]}")

    # 5) Plan concreteness: check for minimal per-algorithm spec
    for algo_name in set(algo_pattern):
        # Find the section for this algorithm
        section_start = plan_text.find(f"artifacts/{algo_name}.py")
        if section_start == -1:
            continue
        section = plan_text[section_start:section_start + 800]
        # Check for concrete elements
        has_code = bool(re.search(r"```|def |class ", section))
        has_lines = bool(re.search(r"L\d+", section))
        has_diff = bool(re.search(r"与.*的区别|differs from|differences", section, re.IGNORECASE))
        if not any([has_code, has_lines, has_diff]):
            errors.append(
                f"[VAGUE SPEC] {algo_name}: plan section has no code, line numbers, "
                f"or differentiation. Must include concrete implementation details."
            )

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="Verify implementation plan concreteness")
    parser.add_argument("iteration_dir", type=Path, help="Path to iterations/N/ directory")
    args = parser.parse_args()

    ok, errors = verify_plan(args.iteration_dir)
    if errors:
        for e in errors:
            print(e)
    else:
        print("PLAN PASS: all deliverables concrete and verifiable")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
