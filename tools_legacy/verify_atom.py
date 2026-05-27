#!/usr/bin/env python3
"""verify_atom.py — Machine-verifiable concreteness gate for refined atoms.

Usage:
  # L1 quick check (skill internal, ~2s)
  python tools/verify_atom.py --quick --atom refined_proposals/map1.json

  # L2 full check (pipeline controller, ~10s)
  python tools/verify_atom.py --session sessions/sess_xxx --atom refined_proposals/map1.json

Checks (ordered, any failure → exit 1 + stderr feedback):
  1. Pydantic schema: RefinedAtom.model_validate()
  2. AST: core_method_body has step/update/train_step, body >= 8 statements
  3. py_compile: core_method_body passes python -m py_compile
  4. issubclass: exec'd class inherits BaseAlgorithm
  5. literature grep: verbatim_quote fuzzy match in literature_file
  6. literature manifest: literature_file registered in _index/literature_manifest.jsonl
  7. code_correspondence: anchor lines grep-match in core_method_body
  8. trainer line range: line numbers don't exceed trainer.py actual lines

--quick mode: only checks 1-3 (Pydantic + AST + py_compile).
--session mode: all 8 checks.
"""

import argparse
import ast as ast_module
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running from any directory
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _THIS_DIR.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))


def _normalize(s: str) -> str:
    """Normalize whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", s).strip().lower()


def _fuzzy_match(quote: str, text: str, threshold: float = 0.85) -> bool:
    """Fuzzy match with whitespace normalization + substring first, then SequenceMatcher."""
    nq = _normalize(quote)
    nt = _normalize(text)
    # First try: normalized substring (handles exact match with whitespace diffs)
    if nq in nt:
        return True
    # Second try: space-stripped substring (handles code like (1-d) vs (1 - d))
    nq_nospace = nq.replace(" ", "")
    nt_nospace = nt.replace(" ", "")
    if nq_nospace in nt_nospace:
        return True
    # Third try: SequenceMatcher ratio (handles small typos/OCR errors)
    return difflib.SequenceMatcher(None, nq, nt).ratio() >= threshold


def _quick_check(atom_path: Path) -> tuple[bool, str]:
    """L1: Pydantic + AST + py_compile (~2s)."""
    from schemas.atom import RefinedAtom

    # 1) Schema validation
    data = json.loads(atom_path.read_text(encoding="utf-8"))
    try:
        atom = RefinedAtom.model_validate(data)
    except Exception as e:
        return False, f"[SCHEMA FAIL]\n{e}"

    # 2) AST check (already done by Pydantic validator, but double-check)
    code = atom.concrete_algorithm.core_method_body
    try:
        tree = ast_module.parse(code)
    except SyntaxError as e:
        return False, f"[SYNTAX FAIL]\n{e}"

    funcs = [n for n in ast_module.walk(tree) if isinstance(n, ast_module.FunctionDef)]
    target = next((f for f in funcs if f.name in {"step", "update", "train_step"}), None)
    if target is None:
        return False, "[AST FAIL] No step/update/train_step method found"

    # 3) py_compile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp_path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return False, f"[PY_COMPILE FAIL]\n{r.stderr}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return True, "L1 PASS"


def _full_check(session_dir: Path, atom_path: Path) -> tuple[bool, str]:
    """L2: All 8 checks (~10s)."""
    from schemas.atom import RefinedAtom

    errors: list[str] = []
    warnings: list[str] = []

    # --- 1) Schema ---
    data = json.loads(atom_path.read_text(encoding="utf-8"))
    try:
        atom = RefinedAtom.model_validate(data)
    except Exception as e:
        return False, f"[SCHEMA FAIL]\n{e}"

    code = atom.concrete_algorithm.core_method_body

    # --- 2-3) AST + py_compile (same as quick) ---
    ok, msg = _quick_check(atom_path)
    if not ok:
        return False, msg

    # --- 4) issubclass ---
    try:
        from tools.trainer_contract import BaseAlgorithm

        ns: dict = {}
        exec(code, ns)
        agent_cls = None
        for obj in ns.values():
            if isinstance(obj, type) and obj.__name__.endswith("Agent"):
                agent_cls = obj
                break
        if agent_cls is None:
            warnings.append("[ISSUBCLASS WARN] No *Agent class found in code (not fatal)")
        elif not issubclass(agent_cls, BaseAlgorithm):
            errors.append(
                f"[ISSUBCLASS FAIL] {agent_cls.__name__} does not inherit BaseAlgorithm"
            )
    except ImportError:
        warnings.append("[ISSUBCLASS WARN] Cannot import BaseAlgorithm (trainer_contract.py missing?)")
    except Exception as e:
        errors.append(f"[ISSUBCLASS FAIL] {e}")

    # --- 5) Literature grep ---
    for i, anchor in enumerate(atom.literature_grounding):
        lit_file = session_dir / anchor.literature_file
        if not lit_file.exists():
            errors.append(
                f"[LIT MISSING #{i}] {anchor.literature_file} not found "
                f"(expected at {lit_file})"
            )
            continue
        text = lit_file.read_text(encoding="utf-8")
        if not _fuzzy_match(anchor.verbatim_quote, text):
            errors.append(
                f"[LIT QUOTE #{i}] '{anchor.verbatim_quote[:60]}...' "
                f"not found in {anchor.literature_file}"
            )

    # --- 6) Literature manifest check ---
    manifest_path = session_dir / "_index" / "literature_manifest.jsonl"
    registered_files: set[str] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    entry = json.loads(line)
                    registered_files.add(entry.get("file", ""))
                except json.JSONDecodeError:
                    pass
        for anchor in atom.literature_grounding:
            if anchor.literature_file not in registered_files:
                errors.append(
                    f"[LIT UNREGISTERED] {anchor.literature_file} not in "
                    f"literature_manifest.jsonl — LLM may have fabricated citation"
                )

    # --- 7) code_correspondence bidirectional anchoring ---
    for i, anchor in enumerate(atom.literature_grounding):
        corr = anchor.code_correspondence
        # Extract key phrases from correspondence (text between quotes or after colon)
        snippets = re.findall(r"['\"]([^'\"]+)['\"]", corr)
        if not snippets:
            snippets = [corr.split(":", 1)[-1].strip()] if ":" in corr else []
        found_any = False
        for snippet in snippets:
            if snippet and snippet.strip():
                s = snippet.strip()
                # Token-level overlap: break snippet into words, check what % appear in code
                # Robust against (1-d) vs (1 - d), torch.min vs min, etc.
                tokens = re.findall(r'\w+|[^\s\w]', s)
                if tokens:
                    matched = sum(1 for t in tokens if t in code)
                    ratio = matched / len(tokens)
                    if ratio >= 0.60:  # 60% token overlap = sufficient correspondence
                        found_any = True
                        break
        if not found_any and snippets:
            errors.append(
                f"[CODE_CORR #{i}] No correspondence snippet from "
                f"'{corr[:60]}...' found in core_method_body"
            )

    # --- 8) Trainer line range ---
    trainer_path = session_dir / "artifacts" / "trainer.py"
    if trainer_path.exists():
        max_line = sum(1 for _ in trainer_path.open(encoding="utf-8"))
        lines_str = atom.trainer_integration.trainer_py_lines_touched
        for m in re.finditer(r"L(\d+)", lines_str):
            if int(m.group(1)) > max_line:
                errors.append(
                    f"[TRAINER LINE OOR] {m.group(0)} exceeds trainer.py "
                    f"max line {max_line}"
                )
    else:
        warnings.append("[TRAINER LINE WARN] trainer.py not found, skipping line check")

    if errors:
        return False, "\n".join(errors)
    msg = "L2 PASS"
    if warnings:
        msg += "\n" + "\n".join(warnings)
    return True, msg


def main():
    parser = argparse.ArgumentParser(description="Verify refined atom concreteness")
    parser.add_argument("--quick", action="store_true", help="L1 fast check only")
    parser.add_argument("--session", type=Path, help="Session directory (L2 full check)")
    parser.add_argument("--atom", type=Path, required=True, help="Path to refined atom JSON")
    args = parser.parse_args()

    if args.quick:
        ok, msg = _quick_check(args.atom)
    elif args.session:
        ok, msg = _full_check(args.session, args.atom)
    else:
        # Default to quick check if no session given
        ok, msg = _quick_check(args.atom)

    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
