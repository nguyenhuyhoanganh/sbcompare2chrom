"""Map-reduce analysis of findings with a context-window budget.

Map: batches of change records, grouped by owned area so each request sees a
coherent slice of the product, are assessed one batch per request.

Reduce: the assessments (which are small) are summarized into an executive
brief in a single request.

Everything is bounded before the first call: only the top-N ranked findings are
sent, batches are packed against the real budget, and the client enforces a
request cap.  An analysis that quietly costs 400 requests is not one a team
will keep running in CI.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..model import BUCKET_ORDER, MODE_UPREV, Finding
from ..sbprofile import Area, TouchSet
from .budget import Budget, estimate_tokens, group_by, pack
from .client import LLMClient, LLMError, parse_json_response
from .prompts import (
    SYSTEM_REDUCE,
    build_map_prompt,
    build_reduce_prompt,
    render_finding,
    render_milestone_brief,
    system_for,
)

VALID_VERDICTS = {"breaks_us", "behaviour_change", "adopt", "no_impact", "unknown"}


def select_for_analysis(findings: Sequence[Finding], top: int = 150,
                        buckets: Optional[Sequence[str]] = None) -> List[Finding]:
    """Pick which findings are worth model time.

    Ranking already happened deterministically, so this is a cut, not a
    re-sort: take the actionable buckets in priority order until the cap.
    """
    wanted = list(buckets) if buckets else BUCKET_ORDER[:3]  # skip pure FYI
    pool = [f for f in findings if f.bucket in wanted]
    pool.sort(key=lambda f: (BUCKET_ORDER.index(f.bucket), -f.score))
    return pool[:top] if top else pool


def _areas_for(findings: Sequence[Finding], touch: TouchSet) -> List[Area]:
    ids = {a for f in findings for a in f.areas}
    return [a for a in touch.areas if a.id in ids]


def analyze(findings: Sequence[Finding], touch: TouchSet, client: LLMClient,
            from_ref: str, to_ref: str, top: int = 150,
            milestone_brief: Optional[Sequence[dict]] = None,
            mode: str = MODE_UPREV,
            log=print) -> Tuple[List[Finding], Dict[str, object]]:
    """Attach AI assessments in place and return (analyzed, summary)."""
    selected = select_for_analysis(findings, top=top)
    if not selected:
        log("  nothing selected for AI analysis")
        return [], {}

    system_map = system_for(mode)
    budget = Budget(
        context_window=client.config.context_window,
        max_output_tokens=client.config.max_output_tokens,
        reserve_tokens=client.config.reserve_tokens,
    )
    # The shared milestone brief is repeated in every request, so it is fixed
    # overhead rather than packable content.
    brief_cost = estimate_tokens(render_milestone_brief(milestone_brief or []))
    overhead = estimate_tokens(system_map) + 800 + brief_cost
    per_request = budget.input_budget(fixed_overhead=overhead)
    if milestone_brief:
        log(f"  shared context: {len(milestone_brief)} chromestatus entries "
            f"(~{brief_cost} tokens per request)")

    # Group by primary owned area so a batch reads as one subsystem, then
    # merge whole groups together while they still fit.
    #
    # Grouping without merging is the trap here: with a 200k window and a
    # typical uprev, every area group is a couple of thousand tokens, so
    # one-request-per-group spends five requests to send 4k tokens.  Merging
    # keeps each area's changes contiguous -- the model still sees them
    # together -- while actually using the window we are paying for.
    groups = group_by(selected, lambda f: f.areas[0] if f.areas else "_unassigned")
    render = lambda f: render_finding(f, touch.platform)

    batches: List[List[Finding]] = []
    current: List[Finding] = []
    used = 0
    for _, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        cost = sum(estimate_tokens(render(f)) for f in group)
        if cost > per_request:
            # A single area too big for one request: flush, then split it.
            if current:
                batches.append(current)
                current, used = [], 0
            batches.extend(pack(group, render, per_request))
            continue
        if current and used + cost > per_request:
            batches.append(current)
            current, used = [], 0
        current.extend(group)
        used += cost
    if current:
        batches.append(current)

    log(f"  analyzing {len(selected)} findings in {len(batches)} request(s) "
        f"(budget ~{per_request} input tokens per request)")

    by_id = {f.uid: f for f in selected}
    all_assessments: List[dict] = []
    failures: List[str] = []

    for i, batch in enumerate(batches, 1):
        prompt = build_map_prompt(batch, touch, from_ref, to_ref,
                                  _areas_for(batch, touch),
                                  milestone_brief=milestone_brief, mode=mode)
        log(f"    batch {i}/{len(batches)}: {len(batch)} records, "
            f"~{estimate_tokens(prompt)} tokens")
        try:
            raw = client.complete(system_map, prompt)
        except LLMError as exc:
            failures.append(f"batch {i}: {exc}")
            log(f"    ! batch {i} failed: {exc}")
            continue
        parsed = parse_json_response(raw)
        if not parsed:
            failures.append(f"batch {i}: unparseable response")
            log(f"    ! batch {i}: could not parse response as JSON")
            continue
        items = parsed.get("assessments")
        if not isinstance(items, list):
            failures.append(f"batch {i}: no assessments array")
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            uid = item.get("id", "")
            finding = by_id.get(uid)
            if finding is None:
                continue  # hallucinated or mangled id: drop it
            verdict = item.get("verdict", "unknown")
            if verdict not in VALID_VERDICTS:
                verdict = "unknown"
            finding.ai = {
                "verdict": verdict,
                "rationale": str(item.get("rationale", ""))[:1200],
                "action": str(item.get("action", ""))[:800],
                "effort": str(item.get("effort", "unknown"))[:40],
                "risk": str(item.get("risk", "unknown"))[:40],
                "test_hint": str(item.get("test_hint", ""))[:600],
            }
            all_assessments.append({"id": uid, **finding.ai})

    analyzed = [f for f in selected if f.ai]
    coverage = f"{len(analyzed)}/{len(selected)}"
    log(f"  assessed {coverage} selected findings")

    summary = _reduce(all_assessments, selected, touch, client, from_ref, to_ref,
                      mode=mode, log=log)
    summary["coverage"] = coverage
    summary["batches"] = len(batches)
    if failures:
        summary["failures"] = failures
    summary["llm"] = client.stats()
    summary["llm"]["model"] = client.config.model
    summary["llm"]["provider"] = client.config.provider
    return analyzed, summary


def _reduce(assessments: List[dict], findings: Sequence[Finding],
            touch: TouchSet, client: LLMClient, from_ref: str, to_ref: str,
            mode: str = MODE_UPREV, log=print) -> Dict[str, object]:
    if not assessments:
        return {}
    bucket_counts: Dict[str, int] = {}
    for finding in findings:
        bucket_counts[finding.bucket] = bucket_counts.get(finding.bucket, 0) + 1

    prompt = build_reduce_prompt(assessments, findings, touch, from_ref, to_ref,
                                 bucket_counts, mode=mode)
    budget = Budget(context_window=client.config.context_window,
                    max_output_tokens=client.config.max_output_tokens,
                    reserve_tokens=client.config.reserve_tokens)
    limit = budget.input_budget(fixed_overhead=estimate_tokens(SYSTEM_REDUCE))
    if estimate_tokens(prompt) > limit:
        # Assessments are short, so this only trips on very large runs; keep the
        # highest-ranked ones rather than failing the summary outright.
        keep = int(len(assessments) * limit / max(1, estimate_tokens(prompt)))
        log(f"  reduce prompt over budget; summarizing top {keep} assessments")
        prompt = build_reduce_prompt(assessments[:keep], findings, touch,
                                     from_ref, to_ref, bucket_counts, mode=mode)

    try:
        raw = client.complete(SYSTEM_REDUCE, prompt)
    except LLMError as exc:
        log(f"  ! summary failed: {exc}")
        return {"error": str(exc)}
    parsed = parse_json_response(raw)
    if not parsed:
        return {"error": "unparseable summary response"}
    return {k: parsed.get(k) for k in
            ("headline", "themes", "must_do", "watch", "questions")
            if parsed.get(k)}
