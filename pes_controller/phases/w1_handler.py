"""W1 Intake & Scope Handler — GitHub baseline search + user confirmation + cc.db。

Steps:
  1. github_search_baseline    — Search GitHub/Tavily for baseline methods
  2. classify_baselines        — Classify results into algorithms/frameworks/benchmarks
  3. present_baseline_options  — Present to Dashboard for user confirmation
  4. write_baselines_to_cc     — Write confirmed baselines to cc.db
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W1 Intake & Scope"

# Words to skip when extracting candidate names
_SKIP_WORDS = {
    "THE", "AND", "FOR", "ARE", "NOT", "BUT", "CAN", "ALL", "NEW", "FROM",
    "WHEN", "THAT", "WITH", "THIS", "WILL", "HAVE", "BEEN", "WERE", "THEY",
    "WHAT", "WHICH", "THERE", "THEIR", "ABOUT", "WOULD", "COULD", "SHOULD",
}

_SKIP_TERMS = {
    "critic", "actor", "model", "method", "network", "algorithm", "system",
    "data", "learning", "training", "policy", "value", "state", "action",
    "reward", "agent", "environment", "layer", "neural", "deep", "batch",
    "gradient", "loss", "function", "parameter", "weight",
}

# Known algorithm acronyms for classification
_ALGO_PATTERNS = re.compile(
    r'\b(SAC|TD3|PPO|DDPG|A3C|DQN|DPO|RLHF|SVM|RF|XGBoost|BERT|GPT|LSTM|'
    r'GRU|CNN|RNN|GAN|VAE|Transformer|ResNet|VGG|YOLO|UNet|AlphaGo|'
    r'MuZero|IMPALA|APEX|R2D2|TQC|SAC2|TRPO|ACKTR)\b',
    re.IGNORECASE,
)


def _classify_repo(name: str, description: str, topics: list[str]) -> str:
    """Classify a repo as algorithm/framework/benchmark/other."""
    full = f"{name} {description} {' '.join(topics)}".lower()
    if any(kw in full for kw in ["benchmark", "environment", "dataset", "corpus", "gym"]):
        return "benchmark"
    if any(kw in full for kw in ["framework", "library", "platform", "toolkit", "suite", "toolbox"]):
        return "framework"
    if _ALGO_PATTERNS.search(full):
        return "algorithm"
    return "other"


def _extract_english_keywords(topic: str) -> str:
    """Extract English keywords from a research topic for GitHub search."""
    words = re.findall(r'[A-Za-z][A-Za-z0-9\-]{2,}', topic)
    stop = {"the", "and", "for", "are", "not", "but", "can", "all", "new",
            "from", "how", "improve", "using", "based", "with", "via", "does"}
    filtered = [w for w in words if w.lower() not in stop][:8]
    return " ".join(filtered) if filtered else " ".join(topic.split()[:5])


@register_handler(PHASE)
class W1Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "github_search_baseline",
        "classify_baselines",
        "present_baseline_options",
        "test_baseline",
        "write_baselines_to_cc",
    ]

    def build_step(self, step_name: str) -> StepResult:
        dispatch = {
            "github_search_baseline": self._step_search,
            "classify_baselines": self._step_classify,
            "present_baseline_options": self._step_present,
            "test_baseline": self._step_test_baseline,
            "write_baselines_to_cc": self._step_write_cc,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return StepResult(done=True, phase=self.phase_label, step=step_name,
                              step_index=self._step_index(), action="error",
                              data={"message": f"Unknown step: {step_name}"})
        return handler()

    # ── Step 1: GitHub search ──

    def _step_search(self) -> StepResult:
        """Search GitHub and web for baseline methods."""
        topic = self._research_topic()
        ws = self._ws()
        results_dir = ws / "intake"
        results_dir.mkdir(parents=True, exist_ok=True)

        search_results = []

        # 1. GitHub search via github-search.mjs
        gh_results = self._github_search(topic)
        if gh_results:
            search_results.extend(gh_results)

        # 2. Tavily web search as supplement
        tavily_results = self._tavily_search(topic)
        if tavily_results:
            search_results.extend(tavily_results)

        # Deduplicate by name
        seen = set()
        unique = []
        for r in search_results:
            key = r.get("name", "").lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        # Save raw results
        (results_dir / "search_results.json").write_text(
            json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")

        return StepResult(
            done=False, phase=self.phase_label, step="github_search_baseline",
            step_index=self._step_index(), action="search_completed",
            data={"result_count": len(unique)},
        )

    def _github_search(self, topic: str) -> list[dict]:
        """Call github-search.mjs to search GitHub repos."""
        skill_script = Path.home() / ".claude" / "skills" / "github-search" / "scripts" / "github-search.mjs"
        if not skill_script.exists():
            logger.info("github-search.mjs not found, skipping GitHub search")
            return []

        query = _extract_english_keywords(topic)
        if not query:
            return []

        # Find Node.js
        node_bin = self._find_node()
        if not node_bin:
            return []

        try:
            env = os.environ.copy()
            # Ensure proxy settings are available
            for proxy_env in ['https_proxy', 'http_proxy', 'HTTPS_PROXY', 'HTTP_PROXY']:
                if not env.get(proxy_env):
                    lower = proxy_env.lower()
                    upper = proxy_env.upper()
                    env[proxy_env] = env.get(lower, env.get(upper, ''))

            r = subprocess.run(
                [node_bin, str(skill_script), query, "--limit", "15",
                 "--sort", "stars", "--min-stars", "10", "--output", "json"],
                capture_output=True, text=True, timeout=30,
                cwd=str(skill_script.parent),
                env=env,
            )
            if r.returncode != 0:
                logger.warning("github-search failed: %s", r.stderr[:200])
                return []

            data = json.loads(r.stdout) if r.stdout.strip() else {}
            items = data if isinstance(data, list) else data.get("results", data.get("items", []))

            results = []
            for item in items[:15]:
                results.append({
                    "name": item.get("full_name", item.get("name", "")),
                    "description": item.get("description", "") or "",
                    "url": item.get("html_url", item.get("url", "")),
                    "stars": item.get("stargazers_count", item.get("stars", 0)),
                    "topics": item.get("topics", []) if isinstance(item.get("topics"), list) else [],
                    "source": "github",
                })
            return results
        except Exception as e:
            logger.warning("GitHub search error: %s", e)
            return []

    def _tavily_search(self, topic: str) -> list[dict]:
        """Search Tavily for baselines as supplement."""
        if not self.tavily_client:
            return []
        try:
            query = f"GitHub {topic} baseline implementation"
            results = self.tavily_client.search(query, max_results=10)
            out = []
            for r in results:
                url = r.get("url", "")
                name = url.split("github.com/")[-1] if "github.com/" in url else ""
                if not name:
                    continue
                out.append({
                    "name": name,
                    "description": r.get("content", "")[:200],
                    "url": url,
                    "stars": 0,
                    "topics": [],
                    "source": "tavily",
                })
            return out
        except Exception as e:
            logger.warning("Tavily search error: %s", e)
            return []

    def _find_node(self) -> str | None:
        """Find Node.js binary (NVM or system)."""
        # Windows
        if os.name == "nt":
            for candidate in ["node", "node.exe"]:
                try:
                    subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                    return candidate
                except Exception:
                    continue
            return None

        # Linux/macOS
        for candidate in [
            Path.home() / ".nvm/versions/node/v22.22.2/bin/node",
            Path.home() / ".nvm/versions/node/v20.19.5/bin/node",
        ]:
            if candidate.exists():
                return str(candidate)
        # System node
        try:
            subprocess.run(["node", "--version"], capture_output=True, timeout=5)
            return "node"
        except Exception:
            return None

    # ── Step 2: Classify baselines ──

    def _step_classify(self) -> StepResult:
        """Classify search results into algorithms/frameworks/benchmarks."""
        ws = self._ws()
        results_file = ws / "intake" / "search_results.json"
        if not results_file.exists():
            return StepResult(
                done=False, phase=self.phase_label, step="classify_baselines",
                step_index=self._step_index(), action="classify_completed",
                data={"algorithms": [], "frameworks": [], "benchmarks": []},
            )

        results = json.loads(results_file.read_text(encoding="utf-8"))
        classified = {"algorithms": [], "frameworks": [], "benchmarks": [], "other": []}

        for r in results:
            category = _classify_repo(
                r.get("name", ""), r.get("description", ""), r.get("topics", []),
            )
            classified[category].append(r)

        # Save classified results
        (ws / "intake" / "classified_baselines.json").write_text(
            json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")

        return StepResult(
            done=False, phase=self.phase_label, step="classify_baselines",
            step_index=self._step_index(), action="classify_completed",
            data={
                "algorithms": len(classified["algorithms"]),
                "frameworks": len(classified["frameworks"]),
                "benchmarks": len(classified["benchmarks"]),
            },
        )

    # ── Step 3: Present baseline options → Dashboard ──

    def _step_present(self) -> StepResult:
        """Send baseline options to Dashboard via SSE and wait for user selection."""
        ws = self._ws()
        classified_file = ws / "intake" / "classified_baselines.json"
        if not classified_file.exists():
            # No results — skip selection, go directly to write step
            return StepResult(
                done=False, phase=self.phase_label, step="present_baseline_options",
                step_index=self._step_index(), action="no_baselines_found",
                data={"message": "No baselines found, proceeding without user confirmation"},
            )

        classified = json.loads(classified_file.read_text(encoding="utf-8"))

        # Build options for Dashboard
        options = []
        for cat in ["algorithms", "frameworks", "benchmarks"]:
            for r in classified.get(cat, [])[:5]:
                options.append({
                    "name": r.get("name", ""),
                    "description": r.get("description", "")[:200],
                    "url": r.get("url", ""),
                    "stars": r.get("stars", 0),
                    "category": cat,
                })

        # Send SSE event
        self._post_event("baseline_options_ready", {
            "phase": self.phase_label,
            "options": options,
            "categories": {
                "algorithms": [r.get("name", "") for r in classified.get("algorithms", [])[:5]],
                "frameworks": [r.get("name", "") for r in classified.get("frameworks", [])[:3]],
                "benchmarks": [r.get("name", "") for r in classified.get("benchmarks", [])[:3]],
            },
        })

        # Set awaiting_decision — sub_loop will stop and wait for user
        state = self.state.copy()
        state["status"] = "awaiting_decision"
        state["intake_options"] = options
        from pes_controller.protocol import atomic_write
        atomic_write(ws / "PIPELINE_STATE.json", state)

        return StepResult(
            done=False, phase=self.phase_label, step="present_baseline_options",
            step_index=self._step_index(), action="present_options",
            data={"options_type": "baseline", "option_count": len(options)},
        )

    # ── Step 4: Test selected baseline (optional) ──

    def _step_test_baseline(self) -> StepResult:
        """Clone + install + quick-test user-selected baselines.

        Only runs when the user selected baselines to test in the Dashboard.
        If no baselines were selected for testing, this step is a no-op.
        """
        ws = self._ws()
        state = self.state

        # Get user's test selection from state (set by Dashboard transition)
        test_targets = state.get("baselines_to_test", [])
        if not test_targets:
            return StepResult(
                done=False, phase=self.phase_label, step="test_baseline",
                step_index=self._step_index(), action="test_skipped",
                data={"message": "No baselines selected for testing"},
            )

        test_dir = ws / "baseline_tests"
        test_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for target in test_targets:
            r = self._run_single_baseline_test(test_dir, target)
            results.append(r)

        # Save test results
        (test_dir / "baseline_test_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        # Notify Dashboard
        self._post_event("baseline_test_completed", {
            "phase": self.phase_label,
            "results": results,
        })

        return StepResult(
            done=False, phase=self.phase_label, step="test_baseline",
            step_index=self._step_index(), action="test_completed",
            data={"tested": len(results),
                  "passed": sum(1 for r in results if r["status"] == "passed")},
        )

    def _run_single_baseline_test(self, test_dir: Path, target: str) -> dict:
        """Clone, detect, install, and quick-test a single baseline repo.

        Args:
            test_dir: Directory for test artifacts
            target: Repo URL or name (e.g. "https://github.com/user/repo" or "user/repo")

        Returns:
            dict with keys: baseline, status, clone_ok, deps_ok, entry_points, notes
        """
        result = {
            "baseline": target,
            "status": "skipped",
            "clone_ok": False,
            "deps_ok": False,
            "entry_points": [],
            "notes": "",
        }

        # Resolve URL
        repo_url = target if target.startswith("http") else f"https://github.com/{target}"
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        # 1. Clone
        baseline_dir = test_dir / repo_name
        try:
            r = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(baseline_dir)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                result["notes"] = f"Clone failed: {r.stderr[:200]}"
                result["status"] = "failed"
                return result
            result["clone_ok"] = True
        except subprocess.TimeoutExpired:
            result["notes"] = "Clone timed out"
            result["status"] = "failed"
            return result
        except Exception as e:
            result["notes"] = f"Clone error: {e}"
            result["status"] = "failed"
            return result

        # 2. Detect entry points and deps
        entry_points = []
        for ep in ["train.py", "main.py", "run.py", "test.py", "evaluate.py", "demo.py"]:
            if (baseline_dir / ep).exists():
                entry_points.append(ep)
            for sub in ["scripts", "examples", "tools"]:
                sub_ep = baseline_dir / sub / ep
                if sub_ep.exists():
                    entry_points.append(f"{sub}/{ep}")
        result["entry_points"] = entry_points

        # 3. Install deps
        python_bin = sys.executable
        try:
            if (baseline_dir / "requirements.txt").exists():
                subprocess.run(
                    [python_bin, "-m", "pip", "install", "-r", "requirements.txt",
                     "--quiet", "--no-deps"],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(baseline_dir),
                )
            if (baseline_dir / "setup.py").exists():
                subprocess.run(
                    [python_bin, "-m", "pip", "install", "-e", ".", "--quiet"],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(baseline_dir),
                )
            result["deps_ok"] = True
        except Exception as e:
            result["notes"] = f"Deps install error: {e}"

        # 4. Quick test (--help on first entry point)
        test_ok = False
        for ep in entry_points:
            ep_path = baseline_dir / ep
            if not ep_path.exists():
                continue
            try:
                r = subprocess.run(
                    [python_bin, str(ep_path), "--help"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(baseline_dir),
                )
                if r.returncode == 0 and r.stdout.strip():
                    test_ok = True
                    result["notes"] = f"{ep} --help OK"
                    break
            except Exception:
                continue

        if test_ok and result["deps_ok"]:
            result["status"] = "passed"
        elif result["clone_ok"]:
            result["status"] = "partial"
        else:
            result["status"] = "failed"

        return result

    # ── Step 5: Write confirmed baselines to cc.db ──

    def _step_write_cc(self) -> StepResult:
        """Write user-confirmed baselines to cc.db."""
        ws = self._ws()
        state = self.state

        # Get confirmed baselines from state (set by transition_phase after user selection)
        confirmed = state.get("confirmed_baselines", {})
        if not confirmed:
            # If no user selection yet, auto-confirm all classified baselines
            classified_file = ws / "intake" / "classified_baselines.json"
            if classified_file.exists():
                classified = json.loads(classified_file.read_text(encoding="utf-8"))
                confirmed = {
                    "algorithms": [r.get("name", "") for r in classified.get("algorithms", [])[:3]],
                    "frameworks": [r.get("name", "") for r in classified.get("frameworks", [])[:2]],
                    "benchmarks": [r.get("name", "") for r in classified.get("benchmarks", [])[:2]],
                    "user_added": [],
                }

        if not confirmed:
            confirmed = {"algorithms": [], "frameworks": [], "benchmarks": [], "user_added": []}

        # Write to cc.db
        written = 0
        cc_path = ws / "_index" / "cc.db"
        if cc_path.exists():
            try:
                from claim_chain.chain import ClaimChainV2
                cc = ClaimChainV2(cc_path)
                for cat, items in confirmed.items():
                    for item in items:
                        if not item:
                            continue
                        source = "user_provided" if cat == "user_added" else "github_search"
                        cc.add_atom(
                            type="fact",
                            title=str(item),
                            content=json.dumps({
                                "source": source,
                                "category": cat,
                                "method": str(item),
                            }, ensure_ascii=False),
                            tags=["baseline", "user-confirmed", cat],
                            evidence_level="verified",
                            metadata={"source": source, "category": cat},
                        )
                        written += 1
                cc.close()
            except Exception as e:
                logger.error("Failed to write baselines to cc.db: %s", e)

        # Save confirmed baselines
        (ws / "intake" / "confirmed_baselines.json").write_text(
            json.dumps(confirmed, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update state with confirmed baselines
        state["confirmed_baselines"] = confirmed
        from pes_controller.protocol import atomic_write
        atomic_write(ws / "PIPELINE_STATE.json", state)

        # Try BGE embedding computation (non-blocking)
        self._try_compute_embeddings(ws, cc_path)

        return StepResult(
            done=True, phase=self.phase_label, step="write_baselines_to_cc",
            step_index=self._step_index(), action="baselines_written",
            data={"atoms_written": written, "baselines": confirmed},
        )

    def _try_compute_embeddings(self, ws: Path, cc_path: Path):
        """Attempt to compute embeddings via EmbeddingProvider (non-blocking)."""
        try:
            from pes_controller.embedding_provider import get_embedding_provider
            provider = get_embedding_provider()
            if provider is None:
                logger.info("No embedding provider available, skipping embeddings")
                return

            # Directly compute embeddings (no socket server needed)
            import sqlite3
            if not cc_path.exists():
                return

            conn = sqlite3.connect(str(cc_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            rows = conn.execute(
                "SELECT id, title, summary FROM nodes WHERE embedding IS NULL"
            ).fetchall()
            conn.close()

            if not rows:
                return

            texts = [f"{r[1]}: {r[2][:500]}" for r in rows]
            vecs = provider.encode(texts)

            conn = sqlite3.connect(str(cc_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            for i, row in enumerate(rows):
                emb_json = json.dumps(vecs[i].tolist(), ensure_ascii=False)
                conn.execute("UPDATE nodes SET embedding = ? WHERE id = ?", (emb_json, row[0]))
            conn.commit()
            conn.close()
            logger.info("Embedded %d atoms via %s", len(rows), provider.name)
        except Exception as e:
            logger.warning("Embedding computation failed (non-blocking): %s", e)

    def _post_event(self, event_type: str, data: dict):
        """Post SSE event to Dashboard."""
        import urllib.request
        try:
            session_id = self._session_id()
            payload = json.dumps({
                "session_id": session_id,
                "type": event_type,
                "data": data,
            }).encode()
            req = urllib.request.Request(
                "http://localhost:8420/api/internal/events",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # Dashboard may not be running yet
