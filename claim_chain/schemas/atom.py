"""schemas/atom.py — RefinedAtom Pydantic schema with hard validators.

Enforces concrete, executable algorithm specifications.
Philosophical templates physically cannot pass validation.

Core mechanisms:
1. AST check: core_method_body MUST contain step/update/train_step with >=8 statements
2. Buzzword filter: docstrings and code body checked for philosophical template words
3. Literature anchoring: verbatim_quote must come from literature/*.md (grep enforced)
4. Type system: Hyperparameter.default rejects str → "tunable" impossible
5. Code correspondence: literature references anchored to specific code lines

Reference: ARIS (ProblemAnchor), Karpathy (py_compile), Intern-Atlas
"""

import ast
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ── Philosophical buzzwords (blocked in core_method_body + docstrings) ──

PHILOSOPHICAL_BUZZWORDS: list[str] = [
    "isomorphic",
    "cyclic_3node",
    "relational structure",
    "map the structure",
    "reconcile via",
    "structural analogy",
    "analyze what makes",
    "test whether the structural",
    "adapt the mapped",
    "precedes→",
    "counterfactual",
    "base: ",
    "violate: ",
    "counterfactual: ",
    "reconcile: ",
]

# ── Domain model components ──


class Hyperparameter(BaseModel):
    """A named hyperparameter with concrete default value.

    default is typed as float|int|bool — str is rejected.
    This means "tunable", "varies", "see paper" are physically impossible.
    """

    name: str = Field(..., pattern=r"^[a-z_][a-z0-9_]*$")
    default: float | int | bool  # str NOT accepted
    range: tuple[float, float] | None = None
    description: str = Field(..., min_length=15)


class LiteratureAnchor(BaseModel):
    """A specific literature reference that can be grep-verified.

    Every reference must point to a real literature/*.md file with
    a verbatim quote that exists in that file (verified by grep).
    code_correspondence anchors the literature to specific code lines.
    """

    literature_file: str = Field(..., pattern=r"^literature/.+\.md$")
    paper_title: str = Field(..., min_length=10)
    adapted_element: str = Field(
        ..., min_length=20,
        description="e.g. 'Eq.3 of Sec.3.2', not just 'the method'",
    )
    verbatim_quote: str = Field(
        ..., min_length=30,
        description="Sentence from literature_file, grep-verified",
    )
    code_correspondence: str = Field(
        ..., min_length=20,
        description="Which lines in core_method_body implement this element. "
        "e.g. 'lines 7-9: q_target = ... - alpha * entropy'",
    )


class NoveltyVsArtifact(BaseModel):
    """How this algorithm differs from an existing artifact/implementation.

    Each difference must be >=30 chars and not use vague boilerplate.
    """

    artifact_path: str = Field(..., pattern=r"^artifacts/.+\.py$")
    differences: list[str] = Field(..., min_length=2)

    @field_validator("differences")
    @classmethod
    def reject_generic(cls, v):
        banned = [
            "different name", "different approach", "similar to",
            "isomorphic", "structurally similar", "analogous",
        ]
        for d in v:
            if len(d) < 30:
                raise ValueError(f"Diff too short ({len(d)} chars, need >=30): {d!r}")
            if any(b in d.lower() for b in banned):
                raise ValueError(f"Diff too vague (contains banned phrase): {d!r}")
        return v


class ProblemAnchor(BaseModel):
    """Frozen problem definition — prevents scope drift (ARIS mechanism).

    Written BEFORE concrete_algorithm. Copied verbatim into every revision.
    """

    bottom_line: str = Field(
        ..., min_length=30,
        description="What metric must improve, by how much, on what data?",
    )
    bottleneck: str = Field(
        ..., min_length=20,
        description="Which specific failure mode does this address?",
    )
    non_goals: list[str] = Field(..., min_length=1)
    constraints: list[str] = Field(..., min_length=1)
    success_condition: str = Field(
        ..., min_length=20,
        description="What evidence makes us say YES this works?",
    )


class ConcreteAlgorithm(BaseModel):
    """The core specification — must be executable Python, not philosophy.

    Key enforcement:
    - core_method_body: real Python with step/update/train_step, >=8 body statements
    - AST-validated (not just string blacklist)
    - Docstrings checked for buzzwords too
    """

    core_method_body: str = Field(
        ..., min_length=200,
        description="The step()/update()/train_step() method body as runnable Python. "
        "NOT the first N lines of the file — the METHOD BODY itself.",
    )
    core_update_equation_latex: str = Field(
        ..., min_length=30,
        description="The key mathematical formula in LaTeX.",
    )
    memory_structure: str = Field(
        ..., min_length=50,
        description="Data structures: shapes, buffers, tensors.",
    )
    hyperparameters: list[Hyperparameter] = Field(..., min_length=2)

    @field_validator("core_method_body")
    @classmethod
    def must_be_real_method(cls, v: str) -> str:
        """AST-level enforcement. LLM cannot bypass with clever rewording."""
        # 1) Must be syntactically valid Python
        try:
            tree = ast.parse(v)
        except SyntaxError as e:
            raise ValueError(f"SyntaxError in core_method_body: {e}")

        # 2) Must contain a method named step/update/train_step
        funcs = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        target_names = {"step", "update", "train_step"}
        matching = [f for f in funcs if f.name in target_names]
        if not matching:
            raise ValueError(
                f"core_method_body must define one of {target_names}. "
                f"Found functions: {[f.name for f in funcs]}"
            )

        target = matching[0]

        # 3) Method body must have >= 8 statements
        if len(target.body) < 8:
            raise ValueError(
                f"Method '{target.name}' body has only {len(target.body)} "
                f"statements, need >=8. The method body must be substantial."
            )

        # 4) Check docstring for buzzwords
        doc = ast.get_docstring(target)
        full_text = v + "\n" + (doc or "")

        for buzz in PHILOSOPHICAL_BUZZWORDS:
            if buzz.lower() in full_text.lower():
                raise ValueError(
                    f"Philosophical buzzword '{buzz}' found in code or docstring. "
                    f"Write what the algorithm DOES, not what it is ANALOGOUS to."
                )

        return v


class TrainerIntegration(BaseModel):
    """How this algorithm integrates with the training infrastructure.

    Specifies exact line ranges, method signatures, and required data fields.
    Karpathy mechanism: scope narrowed to specific, verifiable changes.
    """

    trainer_py_lines_touched: str = Field(
        ...,
        pattern=r"^L\d+(-L\d+)?(,\s*L\d+(-L\d+)?)*$",
        description="e.g. 'L42-L78' or 'L42, L100-L120'",
    )
    step_method_signature: str = Field(..., min_length=30)
    required_batch_fields: list[str] = Field(..., min_length=1)


# ── Top-level atom schema ──


class RefinedAtom(BaseModel):
    """Complete refined algorithm proposal.

    Output of evo-refine skill. Must pass verify_atom.py before entering
    Claim Chain or MAP-Elites archive.
    """

    atom_id: str = Field(..., pattern=r"^[a-z][a-z0-9_]+$")
    philosophical_analogy: str = Field(
        default="",
        description="Old method_sketch content — preserved for traceability, "
        "not used for verification.",
    )
    problem_anchor: ProblemAnchor
    concrete_algorithm: ConcreteAlgorithm
    novelty_vs_artifacts: list[NoveltyVsArtifact] = Field(..., min_length=1)
    literature_grounding: list[LiteratureAnchor] = Field(..., min_length=3)
    trainer_integration: TrainerIntegration
    reviewer_score: Optional[float] = None  # Populated by evo-review
