"""Prepare answer-free, source-pinned workspaces for independent trials.

No inference service is bundled. A trial can be executed by a fresh interactive
agent or a user-supplied runner command. Staging excludes gold and prior reviews;
the runner must enforce its own filesystem and network access boundaries.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import random
import shutil
import subprocess
import time
import uuid

from . import cluster, review
from .diff import diff_snapshots
from .evidence import build_graph, digest
from .extract import run_on_tree
from .model import Report, Snapshot, read_json, write_json
from .report import markdown
from .score import Scope, score_all, summarize_findings
from .snapshot import snapshot_path, tree_path


def prepare(spec: dict, directory: str, cache: str, reference_mode="full", seed=0) -> dict:
    """Derive trial inputs from whole files, never a list of expected findings."""
    dest = Path(directory).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("trial directory must be new or empty; existing trials are never overwritten")
    if reference_mode not in ("full", "core"):
        raise ValueError("reference mode must be full or core")
    if not spec.get("id") or not spec.get("files") or set(spec.get("refs", {})) != {"from", "to"}:
        raise ValueError("case needs id, from/to refs and a nonempty files list")
    primary = sorted(set(spec["files"]))
    context = sorted(set(spec.get("context_files", [])) - set(primary))
    source_root = Path(__file__).resolve().parent.parent
    workspace = dest / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root / "chromiumdiff", workspace / "chromiumdiff",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(source_root / "skills", workspace / "skills",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evaluations.json"))
    if reference_mode == "core":
        # Withhold all domain examples, not particular feature names. Keep the
        # links usable and the generic checkpoint contract intact.
        refs = workspace / "skills/analyzing-chromium-upgrades/reference"
        for path in refs.glob("*.md"):
            if path.name != "investigation.md":
                path.write_text("# Reference withheld for this trial\n\n"
                                "Use the generic investigation procedure in SKILL.md and actual source evidence.\n",
                                encoding="utf-8")
    data = workspace / "data"
    staged_cache = data / "cache"
    inputs, source_hashes = {}, {}
    for side, ref in spec["refs"].items():
        original = tree_path(cache, ref)
        target = Path(tree_path(str(staged_cache), ref))
        supplemental = Path(tree_path(str(staged_cache / "review-sources"), ref))
        hashes = source_hashes[side] = {}
        for relative in primary + context:
            src = review.safe_path(original, relative)
            if not src.is_file():
                raise ValueError(f"case source not cached: {side} {relative}; absence cannot be inferred")
            actual = review._file_hash(src)
            expected = (spec.get("sha256", {}).get(side) or {}).get(relative)
            if expected and actual != expected:
                raise ValueError(f"case source hash mismatch: {side} {relative}")
            hashes[relative] = actual
            dst = review.safe_path(str(target if relative in primary else supplemental), relative)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        facts, _ = run_on_tree(str(target), allow_paths=set(primary), allow_prefixes={})
        extra, _ = run_on_tree(str(supplemental), allow_paths=set(context), allow_prefixes={})
        all_facts = Snapshot(ref, facts + extra, created="1970-01-01T00:00:00+00:00")
        graph = build_graph(Report(ref, ref), all_facts, all_facts)
        by_uid = all_facts.index()
        retained = {f.uid for f in facts}
        outgoing = {}
        for edge in graph["edges"]:
            outgoing.setdefault(edge["source"], set()).add(edge["target"])
        frontier = set(retained)
        while frontier:
            frontier = {uid for parent in frontier for uid in outgoing.get(parent, ())} - retained
            retained.update(frontier)
        meta = {"target_set": "evaluation", "platform": "windows", "partitions": [],
                "complete": False, "coverage": {}, "evaluation_scope": primary,
                "context_only_files": context}
        inputs[side] = Snapshot(ref, [by_uid[uid] for uid in sorted(retained)],
                                created="1970-01-01T00:00:00+00:00", meta=meta)
        write_json(snapshot_path(str(staged_cache), ref, "evaluation"), inputs[side].to_dict())
    old, new = inputs["from"], inputs["to"]
    changes = diff_snapshots(old, new, platform="windows")
    findings = score_all(changes, Scope({}, to_ref=new.ref,
                        incomplete="Deliberately bounded evaluation source scope",
                        from_incomplete="Deliberately bounded evaluation source scope"))
    report = Report(old.ref, new.ref, findings, summarize_findings(findings), {
        "target_set": "evaluation", "platform": "windows", "partitions": [], "complete": False,
        "evaluation_case": spec["id"], "evaluation_scope": primary,
        "context_only_files": context, "source_sha256": source_hashes,
        "coverage": {"from": {}, "to": {}},
        "scope_note": "Complete review of these selected files, not a release-wide audit. "
                      "Context files supply referenced facts only; their other changes are outside this case."})
    cluster.refresh(report)
    if seed:
        rng = random.Random(seed)
        rng.shuffle(report.findings)
        for f in report.findings:
            f.score = rng.randrange(101)
            f.bucket = rng.choice(("contract", "behaviour", "added", "scheduled", "cleanup"))
        report.summary.update(summarize_findings(report.findings))
        cluster.refresh(report)
    write_json(str(data / "report.json"), report.to_dict())
    (data / "report.md").write_text(markdown.render(report, platform="windows"), encoding="utf-8")
    metadata = {"schema": 1, "case_id": spec["id"], "source_spec_digest": digest(spec),
                "source_sha256": source_hashes, "reference_mode": reference_mode, "seed": seed,
                "workspace": str(workspace), "review_directory": str(workspace / "review"),
                "implementation": review.implementation_identity(), "state": "prepared",
                "runner": None, "execution": None}
    # Record the actual staged reference variant, not only its parent revision.
    metadata["staged_skill_sha256"] = digest({str(p.relative_to(workspace)): review._file_hash(p)
                                             for p in sorted((workspace / "skills").rglob("*"))
                                             if p.is_file()})
    write_json(str(dest / "trial.json"), metadata)
    task = ("Analyze every meaningful change supported by the supplied comparison and declared file scope.\n"
            "Use skills/analyzing-chromium-upgrades/SKILL.md and its available references.\n"
            "Start with data/report.md and the documented CLI. The report is data/report.json; "
            "its cache is data/cache. Write the review into review/.\n"
            "Explain transitions, related evidence, conditions, consumer impact and actions. "
            "Do not output bucket/score lists. Investigate source deltas even when findings omit them.\n"
            "This is a deliberately bounded source comparison; do not claim release-wide completeness.\n"
            "Work offline with supplied evidence. Record missing evidence as a limit rather than inventing rollout or chronology.\n"
            "Do not inspect implementation files, tests, expected answers, prior reviews or unrelated workspace paths. "
            "The command interface and exact-version Chromium source are available for investigation.\n"
            "Complete record/check/render and leave review.json and review.md. "
            "A provisional result is preferable to an unsupported confirmed claim.\n")
    (workspace / "TASK.md").write_text(task, encoding="utf-8")
    return metadata


def run(directory: str, runner: dict) -> dict:
    """Execute only an explicitly supplied runner; no shell interpolation."""
    path = Path(directory).resolve()
    metadata = read_json(str(path / "trial.json"))
    if metadata["state"] != "prepared":
        raise ValueError("trial has already been attempted; prepare a new directory for a fresh run")
    required = ("model", "context_limit", "command", "timeout_seconds")
    if any(not runner.get(k) for k in required):
        raise ValueError("runner requires model, context_limit, command argv and timeout_seconds")
    if (not isinstance(runner["command"], list) or not all(isinstance(x, str) for x in runner["command"])
            or type(runner["context_limit"]) is not int or runner["context_limit"] < 1
            or type(runner["timeout_seconds"]) is not int or not 1 <= runner["timeout_seconds"] <= 7200):
        raise ValueError("invalid runner argv, context limit or timeout (1..7200 seconds)")
    replacements = {"{workspace}": metadata["workspace"], "{task}": str(Path(metadata["workspace"]) / "TASK.md"),
                    "{review}": metadata["review_directory"]}
    argv = [replacements.get(arg, arg) for arg in runner["command"]]
    metadata.update(state="running", runner=runner,
                    started=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write_json(str(path / "trial.json"), metadata)
    started = time.monotonic()
    try:
        with open(path / "runner.stdout.log", "wb") as stdout, open(path / "runner.stderr.log", "wb") as stderr:
            result = subprocess.run(argv, cwd=metadata["workspace"], stdout=stdout, stderr=stderr,
                                    timeout=runner["timeout_seconds"], check=False)
        execution = {"exit_code": result.returncode, "timed_out": False}
    except subprocess.TimeoutExpired:
        execution = {"exit_code": None, "timed_out": True}
    except OSError as exc:
        execution = {"exit_code": None, "error": str(exc), "timed_out": False}
    execution["elapsed_seconds"] = round(time.monotonic() - started, 3)
    execution["session_id"] = str(uuid.uuid4())
    metadata.update(state="executed", execution=execution)
    write_json(str(path / "trial.json"), metadata)
    return finish(directory)


def finish(directory: str, runner=None) -> dict:
    """Register interactive or command-run artifacts without granting a pass."""
    path = Path(directory).resolve()
    metadata = read_json(str(path / "trial.json"))
    if runner is not None:
        if metadata["state"] != "prepared":
            raise ValueError("interactive provenance can only be registered for an uncollected prepared trial")
        if not runner.get("model") or not runner.get("session_id"):
            raise ValueError("interactive runner must declare model and unique session_id; unknown limits stay unverified")
        metadata["runner"] = runner
        metadata["execution"] = {"mode": "interactive", "elapsed_seconds": runner.get("elapsed_seconds"),
                                 "session_id": runner["session_id"]}
        if runner.get("failure"):
            metadata["execution"]["error"] = runner["failure"]
    result = {"artifacts_valid": False, "accounting_complete": False}
    try:
        index, ledger = review.load(metadata["review_directory"])
        check = review.check(index, ledger)
        input_errors = review.verify_sources(index)
        result.update(artifacts_valid=not check["errors"] and not input_errors,
                      accounting_complete=bool(check["accounting_complete"] and not input_errors),
                      check=check, input_errors=input_errors,
                      fingerprint=index["fingerprint"], ledger_digest=digest(ledger))
    except (OSError, ValueError, KeyError) as exc:
        result["error"] = str(exc)
    metadata.update(state="collected", result=result)
    write_json(str(path / "trial.json"), metadata)
    return metadata
