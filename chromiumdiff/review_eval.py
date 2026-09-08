"""Structural scoring of independently authored event gold and saved trials.

Evidence membership is measurable without guessing whether prose means the
same thing. Semantic correctness and unsupported claims require adjudication.
"""

from __future__ import annotations

from itertools import combinations

from .evidence import digest
from . import review

CHECKS = ("meaning", "transition", "conditions", "impact_action", "citations", "grouping")


def assessment_template(gold, trials):
    """Pin the outputs to judge; never pre-fill a passing judgment."""
    evaluate(gold, trials)  # Check scope/membership compatibility first.
    def blank():
        return {"verdict": "unresolved", "reason": "", "evidence": []}
    return {"gold_digest": digest(gold), "reviewer": "", "provenance": "", "trials": {
        label: {"ledger_digest": digest(ledger), "reviewed_predicted_event_ids": [],
                "predicted_event_ids_to_review": [e["id"] for e in ledger["events"]],
                "events": [{"gold_id": e["id"], "predicted_event_ids": [],
                            "checks": {key: blank() for key in CHECKS}} for e in gold["events"]],
                "dispositions": blank(), "unsupported_claims": []}
        for label, _, ledger in trials}}


def _pairs(groups):
    return {tuple(sorted(pair)) for group in groups for pair in combinations(sorted(group), 2)}


def _jaccard(left, right):
    return len(left & right) / len(left | right) if left or right else 1.0


def evaluate(gold: dict, trials: list, adjudication=None, manifests=None) -> dict:
    """Gold scope is explicit; membership outside it is not silently judged."""
    if not trials or not gold.get("events"):
        raise ValueError("evaluation needs gold events and at least one trial")
    if not gold.get("provenance"):
        raise ValueError("gold must document independent source/CL provenance")
    if len({label for label, _, _ in trials}) != len(trials):
        raise ValueError("trial labels must be distinct; do not count the same directory twice")
    groups = [frozenset(e["items"]) for e in gold["events"]]
    if any(not g for g in groups) or sum(map(len, groups)) != len(set().union(*groups)):
        raise ValueError("gold event primary memberships must be nonempty and disjoint")
    if len({e["id"] for e in gold["events"]}) != len(groups):
        raise ValueError("gold event IDs must be unique")
    universe = set().union(*groups)
    expected_pairs = _pairs(groups)
    results, partitions, fingerprints = [], [], set()
    for label, index, ledger in trials:
        fingerprints.add(index["fingerprint"])
        if gold.get("fingerprint") and index["fingerprint"] != gold["fingerprint"]:
            raise ValueError(f"{label}: trial does not match pinned gold fingerprint")
        if not universe <= set(index["items"]):
            raise ValueError(f"{label}: gold names evidence outside the trial index")
        predicted = [frozenset(e["items"]) & universe for e in ledger["events"]]
        predicted = [g for g in predicted if g]
        if sum(map(len, predicted)) != len(set().union(set(), *predicted)):
            raise ValueError(f"{label}: duplicate primary members in trial")
        partition = set(predicted)
        partitions.append(partition)
        pairs = _pairs(predicted)
        found = set().union(set(), *predicted)
        exact = [e["id"] for e, members in zip(gold["events"], groups) if members in partition]
        results.append({
            "trial": label,
            "exact_event_membership_recall": len(exact) / len(groups),
            "recovered_event_ids": exact,
            "missing_event_ids": [e["id"] for e in gold["events"] if e["id"] not in exact],
            "missed_critical_event_ids": [e["id"] for e in gold["events"]
                                          if e.get("critical") and e["id"] not in exact],
            "finding_recall": len(found) / len(universe),
            "pair_precision": len(pairs & expected_pairs) / len(pairs) if pairs else None,
            "pair_recall": len(pairs & expected_pairs) / len(expected_pairs) if expected_pairs else None,
            "overmerged_groups": sum(sum(bool(p & g) for g in groups) > 1 for p in predicted),
            "split_gold_events": sum(sum(bool(p & g) for p in predicted) > 1 for g in groups),
            "provisional_events": sum(e.get("status") != "confirmed" for e in ledger["events"]),
            "unadjudicated_events_outside_gold": sum(not (set(e["items"]) & universe)
                                                     for e in ledger["events"]),
            "events_with_unadjudicated_members": sum(bool(set(e["items"]) - universe)
                                                     for e in ledger["events"]),
            "unadjudicated_items": sorted(set().union(set(), *(set(e["items"]) for e in ledger["events"])) - universe),
        })
    if len(fingerprints) != 1:
        raise ValueError("repeatability requires identical pinned evidence across trials")
    agreement = [{"trials": [trials[i][0], trials[j][0]],
                  "event_partition_jaccard": _jaccard(partitions[i], partitions[j])}
                 for i, j in combinations(range(len(trials)), 2)]
    result = {"trials": results, "repeatability": agreement,
            "scope": "Only primary evidence memberships within the independently annotated gold scope.",
            "semantic_accuracy": "not automatically measured",
            "unsupported_claims": "requires independent source/CL adjudication",
            "release_verdict": "not established by structural metrics"}
    if adjudication is not None:
        result.update(adjudicate(gold, trials, adjudication, manifests or []))
    return result


def _assessment(value):
    if (not isinstance(value, dict) or value.get("verdict") not in ("pass", "fail", "unresolved")
            or not isinstance(value.get("reason"), str) or not value["reason"].strip()
            or not isinstance(value.get("evidence"), list) or not value["evidence"]
            or not all(isinstance(e, str) and e.strip() for e in value["evidence"])):
        raise ValueError("each adjudication needs verdict, reason and nonempty source evidence citations")
    return value["verdict"] == "pass"


def adjudicate(gold, trials, record, manifests):
    """Validate independent assessments, not infer truth from prose keywords.

    Reviewer/runner identities are declared provenance, not authentication.
    A passing verdict applies only to the pinned benchmark scope and profile.
    """
    if not record.get("reviewer") or not record.get("provenance"):
        raise ValueError("adjudication must identify an independent reviewer and provenance")
    if record.get("gold_digest") != digest(gold):
        raise ValueError("adjudication does not match pinned gold digest")
    labels = [label for label, _, _ in trials]
    if len(set(labels)) != len(labels) or set(record.get("trials", {})) != set(labels):
        raise ValueError("adjudication must cover each distinct trial exactly once")
    gold_ids = {e["id"] for e in gold["events"]}
    critical = {e["id"] for e in gold["events"] if e.get("critical")}
    scores, recovered_sets, blockers = [], [], []
    for label, index, ledger in trials:
        entry = record["trials"][label]
        if entry.get("ledger_digest") != digest(ledger):
            raise ValueError(f"{label}: adjudication is stale for this ledger")
        predicted = {e["id"]: e for e in ledger["events"]}
        reviewed = entry.get("reviewed_predicted_event_ids", [])
        if len(set(reviewed)) != len(reviewed) or set(reviewed) != set(predicted):
            raise ValueError(f"{label}: all predicted events, including extras, must be adjudicated")
        assessments = entry.get("events", [])
        if len(assessments) != len(gold_ids) or {e["gold_id"] for e in assessments} != gold_ids:
            raise ValueError(f"{label}: adjudication must include every gold event (including omissions)")
        recovered = set()
        for event in assessments:
            mapped = event.get("predicted_event_ids", [])
            if len(set(mapped)) != len(mapped) or not set(mapped) <= set(predicted):
                raise ValueError(f"{label}: invalid predicted event mapping")
            if set(event.get("checks", {})) != set(CHECKS):
                raise ValueError("event adjudication needs all checks: " + ", ".join(CHECKS))
            passed = [_assessment(event["checks"][key]) for key in CHECKS]
            if mapped and all(passed) and all(predicted[uid]["status"] == "confirmed" for uid in mapped):
                recovered.add(event["gold_id"])
        dispositions_ok = _assessment(entry.get("dispositions"))
        claims = entry.get("unsupported_claims")
        if not isinstance(claims, list):
            raise ValueError("unsupported_claims must explicitly be a list, even when empty")
        for claim in claims:
            if (claim.get("severity") not in ("major", "minor") or claim.get("event_id") not in predicted
                    or not claim.get("claim")):
                raise ValueError("unsupported claim needs severity, known event_id and claim")
            _assessment({**claim, "verdict": "fail"})
        accounting = review.check(index, ledger)
        input_errors = review.verify_sources(index)
        complete = accounting["accounting_complete"] and not input_errors
        missed = sorted(critical - recovered)
        major = sum(c["severity"] == "major" for c in claims)
        score = {"trial": label, "event_recall": len(recovered) / len(gold_ids),
                 "recovered_event_ids": sorted(recovered), "missed_critical_event_ids": missed,
                 "major_unsupported_claims": major, "minor_unsupported_claims": len(claims) - major,
                 "dispositions_adjudicated_pass": dispositions_ok, "accounting_complete": complete,
                 "input_errors": input_errors}
        scores.append(score)
        recovered_sets.append(recovered)
        if score["event_recall"] < .95 or missed or major or not complete or not dispositions_ok:
            blockers.append(f"{label}: semantic recall, critical coverage, claim support or accounting failed")
    agreement = [{"trials": [labels[i], labels[j]], "core_event_jaccard": _jaccard(a, b)}
                 for (i, a), (j, b) in combinations(enumerate(recovered_sets), 2)]
    if len(trials) < 5:
        blockers.append("at least five independent executions of the frozen case are required")
    if any(a["core_event_jaccard"] < .9 for a in agreement):
        blockers.append("core event repeatability is below 0.90")
    by_directory = {m.get("review_directory"): m for m in manifests}
    executions, profiles, implementations, specs = set(), set(), set(), set()
    for label, index, ledger in trials:
        manifest = by_directory.get(label, {})
        runner = manifest.get("runner") or {}
        result = manifest.get("result") or {}
        execution = manifest.get("execution") or {}
        session = execution.get("session_id")
        if (not session or session in executions or manifest.get("state") != "collected"
                or not result.get("artifacts_valid") or result.get("ledger_digest") != digest(ledger)
                or result.get("fingerprint") != index["fingerprint"]
                or execution.get("timed_out") or execution.get("error") or execution.get("exit_code", 0) != 0
                or (manifest.get("implementation") or {}).get("tool_sha256") !=
                   index["inputs"]["implementation"]["tool_sha256"]
                or (gold.get("source_spec_digest") and
                    manifest.get("source_spec_digest") != gold["source_spec_digest"])
                or not runner.get("model") or runner.get("context_limit_verified") is not True
                or type(runner.get("context_limit")) is not int or not 1 <= runner["context_limit"] <= 200000):
            blockers.append(f"{label}: missing/stale independent execution or verified <=200k runner profile")
        executions.add(session)
        profiles.add(digest({k: runner.get(k) for k in ("model", "context_limit", "settings")}))
        implementations.add((manifest.get("implementation") or {}).get("tool_sha256"))
        specs.add(manifest.get("source_spec_digest"))
    if len(profiles) != 1 or len(implementations) != 1 or None in implementations or len(specs) != 1 or None in specs:
        blockers.append("runner profile, tool revision and source case must be frozen across repetitions")
    return {"semantic_accuracy": {"method": "independent adjudication; declared reviewer provenance",
                                  "reviewer": record["reviewer"], "trials": scores},
            "semantic_repeatability": agreement,
            "unsupported_claims": "independently adjudicated, including events outside primary gold membership",
            "release_verdict": "pass_for_pinned_case_and_runner_only" if not blockers else "not_passed",
            "release_blockers": blockers,
            "release_scope": "This case and declared runner only; not universal discovery or authentication of reviewer judgments."}
