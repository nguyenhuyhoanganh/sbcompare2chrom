"""Freeze root-cause answers and require independent semantic adjudication.

The scorer verifies artifact identity and recorded judgments. It cannot infer
causality from prose or authenticate a reviewer/runner's declarations.
"""

from __future__ import annotations

from pathlib import Path

from . import review
from .evidence import digest
from .model import read_json


CHECKS = ("transition", "cause", "symptom", "uncertainty", "citations")


def inspect_trial(metadata):
    workspace = Path(metadata["workspace"])
    errors = []
    frozen = metadata.get("frozen_files") or {}
    if not frozen:
        errors.append("trial has no frozen evidence manifest")
    for relative, expected in frozen.items():
        try:
            path = review.safe_path(str(workspace), relative)
            if not path.is_file() or review._file_hash(path) != expected:
                errors.append("changed or missing input: " + relative)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    actual = review.implementation_identity(workspace)
    if actual["tool_sha256"] != metadata["implementation"]["tool_sha256"]:
        errors.append("staged executable implementation changed")
    skills = digest({str(p.relative_to(workspace)): review._file_hash(p)
                     for p in sorted((workspace / "skills").rglob("*"))
                     if p.is_file() and p.suffix != ".pyc"})
    if skills != metadata["staged_skill_sha256"]:
        errors.append("staged skill changed")
    answer = workspace / "answer.md"
    valid = answer.is_file() and not answer.is_symlink() and bool(answer.read_text(encoding="utf-8").strip())
    return {"artifacts_valid": bool(valid and not errors), "input_errors": errors,
            "answer_sha256": review._file_hash(answer) if valid else None,
            "evidence_fingerprint": metadata.get("evidence_fingerprint"),
            "semantic_accuracy": "requires independent assessment of the entire answer"}


def _trials(gold, directories):
    if not gold.get("case_id") or not gold.get("source_spec_digest") or not gold.get("provenance"):
        raise ValueError("gold needs case_id, source_spec_digest and source/CL provenance")
    if set(gold.get("checks", {})) != set(CHECKS) or any(
            not isinstance(v, str) or not v.strip() for v in gold["checks"].values()):
        raise ValueError("gold must describe every root-cause check")
    labels = [str(Path(d).resolve()) for d in directories]
    if not labels or len(labels) != len(set(labels)):
        raise ValueError("trial directories must be nonempty and distinct")
    rows = []
    for label in labels:
        metadata = read_json(str(Path(label) / "trial.json"))
        if metadata.get("task_type") != "root-cause":
            raise ValueError("not a root-cause trial: " + label)
        if metadata.get("case_id") != gold["case_id"] or metadata.get("source_spec_digest") != gold["source_spec_digest"]:
            raise ValueError("trial differs from the pinned root-cause case")
        result = inspect_trial(metadata)
        rows.append((label, metadata, result))
    return rows


def assessment_template(gold, directories):
    trials = {}
    for label, metadata, result in _trials(gold, directories):
        if metadata.get("state") != "collected" or not result["artifacts_valid"]:
            raise ValueError("collect a valid answer before requesting assessment: " + label)
        if result["answer_sha256"] != metadata["result"].get("answer_sha256"):
            raise ValueError("answer changed after collection: " + label)
        trials[label] = {"answer_sha256": result["answer_sha256"],
                         "evidence_fingerprint": result["evidence_fingerprint"],
                         "answer_reviewed": False,
                         "checks": {k: {"verdict": "unresolved", "reason": "", "evidence": []} for k in CHECKS},
                         "unsupported_claims": None}
    return {"gold_digest": digest(gold), "reviewer": "", "provenance": "", "trials": trials}


def evaluate(gold, directories, adjudication=None):
    rows = _trials(gold, directories)
    if adjudication is not None:
        if adjudication.get("gold_digest") != digest(gold):
            raise ValueError("stale root-cause gold assessment")
        if not adjudication.get("reviewer") or not adjudication.get("provenance"):
            raise ValueError("independent reviewer and evidence provenance are required")
        if set(adjudication.get("trials", {})) != {label for label, _, _ in rows}:
            raise ValueError("assessment must cover exactly the supplied trials")
    results, sessions, profiles, fingerprints = [], [], set(), set()
    blockers = []
    for label, metadata, current in rows:
        execution = metadata.get("execution") or {}
        runner = metadata.get("runner") or {}
        executed = (metadata.get("state") == "collected" and bool(execution.get("session_id"))
                    and not execution.get("error") and not execution.get("timed_out")
                    and (execution.get("exit_code") == 0 or execution.get("mode") == "interactive"))
        sessions.append(execution.get("session_id"))
        context = runner.get("context_limit")
        bounded = (type(context) is int and 0 < context <= 200000 and
                   runner.get("context_limit_verified") is True and bool(runner.get("model")))
        profiles.add(digest({"model": runner.get("model"), "context_limit": context,
                             "settings": runner.get("settings"),
                             "implementation": metadata["implementation"],
                             "staged_skill": metadata["staged_skill_sha256"],
                             "reference_mode": metadata["reference_mode"]}))
        fingerprints.add(current["evidence_fingerprint"])
        fresh = (current["artifacts_valid"] and current["answer_sha256"] ==
                 (metadata.get("result") or {}).get("answer_sha256"))
        passed = False
        verdicts = {}
        if adjudication is not None:
            entry = adjudication["trials"][label]
            if (entry.get("answer_sha256") != current["answer_sha256"] or
                    entry.get("evidence_fingerprint") != current["evidence_fingerprint"]):
                raise ValueError("stale answer/evidence assessment: " + label)
            if set(entry.get("checks", {})) != set(CHECKS):
                raise ValueError("assessment must include every root-cause check")
            for key, check in entry["checks"].items():
                if check.get("verdict") not in ("pass", "fail", "unresolved"):
                    raise ValueError("invalid assessment verdict")
                if check["verdict"] != "unresolved" and (
                        not isinstance(check.get("reason"), str) or not check["reason"].strip() or
                        not isinstance(check.get("evidence"), list) or not check["evidence"] or
                        any(not isinstance(e, str) or not e.strip() for e in check["evidence"])):
                    raise ValueError("resolved assessments need a reason and evidence citations")
                verdicts[key] = check["verdict"]
            unsupported = entry.get("unsupported_claims")
            if unsupported is not None and (not isinstance(unsupported, list) or any(
                    not isinstance(c, dict) or c.get("severity") not in ("major", "minor") or
                    not c.get("claim") or not c.get("reason") or not c.get("evidence") for c in unsupported)):
                raise ValueError("unsupported claims need severity, claim, reason and evidence")
            passed = (entry.get("answer_reviewed") is True and
                      all(v == "pass" for v in verdicts.values()) and unsupported is not None and
                      not any(c["severity"] == "major" for c in unsupported))
        results.append({"trial": label, "artifacts_valid": bool(fresh), "input_errors": current["input_errors"],
                        "execution_valid": bool(executed), "context_verified": bounded,
                        "checks": verdicts, "semantic_pass": bool(passed and fresh and executed and bounded)})
    if adjudication is None:
        blockers.append("independent semantic assessment is missing")
    if len(rows) < 5 or len(set(sessions)) != len(rows) or any(not s for s in sessions):
        blockers.append("at least five distinct completed executions are required")
    if len(profiles) != 1 or len(fingerprints) != 1 or None in fingerprints:
        blockers.append("case, evidence, tool, skill and runner profile must remain fixed")
    if not all(r["semantic_pass"] for r in results):
        blockers.append("every trial must pass artifact, execution and independent semantic checks")
    return {"case_id": gold["case_id"], "trials": results, "blockers": blockers,
            "verdict": "not_passed" if blockers else "pass_for_pinned_case_and_runner_only",
            "limit": "Judgments and runner declarations require independent audit; this is not release-wide certification."}
