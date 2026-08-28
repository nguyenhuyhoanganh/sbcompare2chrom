"""Attach the Chromium CL that made a change, and the issue behind it.

The rest of the tool answers *what* changed.  This answers *why it changed*,
by naming the review that did it:

    Fact  ->  the file that declares it
          ->  the CLs that touched that file between the two versions
          ->  the CLs whose diff of that file mentions this identifier
          ->  the `Bug:` footer of those CLs
          ->  every other CL that cites the same issue

Each arrow is a lookup, not a guess, and the last two come free once the first
three land.

**Why the file alone is not the answer.** A declaration file is shared: 500 CLs
touched ``chrome/browser/about_flags.cc`` between the M148 and M151 branch
points, 337 touched ``runtime_enabled_features.json5`` and 62 touched
``content_features.cc``.  Handing a reader 500 CLs for one flag is worse than
handing them none.  So the file only produces *candidates*, and the candidates
are then filtered by whether that CL's diff of that file actually mentions the
identifier.  Measured on ``content_features.cc``: 62 candidates, and
``AndroidCaptureKeyEvents`` survives in exactly one of them -- CL 7885356,
"android: Enable AndroidCaptureKeyEvents by default", which is the finding
(disabled -> enabled) in the author's own words.

**Six strengths of evidence, never merged into a score.**  Four of them name
the fact.  ``exact``: the CL edited a line carrying this identifier.
``moved``: the file was renamed and the fact came with it, so no line changed
and the move is the whole cause.  ``declares``: the CL edited the body of the
declaration -- from the line that names it to the ``}`` or ``;`` that closes
it -- which is how a Mojo method whose parameter list grew is found, since the
method's name line is untouched.  ``described``: the CL's own title or
description names it, weaker than a diff but written by the person who made
the change, and free, because descriptions arrive with the candidate list.

The four are not redundant. Measured over the top 150 findings of a real
M148 -> M151 run: 65 are found only by the diff, and 17 only by the
description, because a CL can delete the declaration it is named after and
leave the identifier in no surviving line.

**And two that do not, so that a row always answers.**  ``crowded``: more than
``DECL_MAX`` CLs edited this declaration, so they no longer single one out.
``touched``: nothing matched the identifier, and these are the newest CLs that
touched the declaring file.  Both are leads, both rank below all four above,
and the panel prints them under a sentence saying they are not a citation --
because the alternative, tried first, was to drop them and tell a reader who
clicked the row that nothing was found about a declaration eleven CLs edited.

**There is no such thing as a change without a CL.**  The two trees differ,
so something landed -- an empty row is never a fact about Chromium, only about
this search.  Saying otherwise invites the reader to conclude a declaration
changed on its own, which cannot happen.

So the file is asked three ways before the answer is no.  ``file:`` on main,
which is the question that works.  Then the same file with the branch pin
removed, because six weeks of merge-backs land on the release branch after it
is cut and those commits are in the tree being compared.  Then, when nothing
touched the file under the name we hold, the commit messages of the whole
window, because a declaration can be generated from a template, recorded by
Gerrit under another path, renamed, or rolled in from third-party code -- and
in every one of those the file question is simply the wrong question.

An empty row therefore reports the search, and names the three questions it
missed on, so a reader knows what to try rather than what to conclude.

**What it costs, and the ceiling on it.**  One request per (CL, file) pair, so
the bill is set by how *busy* the declaration files are and not by how many
findings are asked about: the top 150 findings of that run touch 56 files and
the top 300 touch 60. The expensive shape is a busy file that answers one
finding -- ``extension_features.cc`` spends 44 requests on a single row where
``autofill_features.cc`` spends 8 apiece on sixteen. So the diff pass is
budgeted, files are spent on in ascending requests-per-finding order, and a
file the budget does not reach keeps its descriptions and is named in the
summary. ``diffs_read: false`` on a finding means nobody looked, which is not
the same answer as "no CL edits this line".

**Nothing here is fetched by the report.**  chromium-review sends no
``Access-Control-Allow-Origin``, so a browser opening ``report.html`` off a
disk cannot query it, and the report is supposed to work on an air-gapped
network anyway.  Everything is resolved during the run and embedded.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..acquire import (GITILES_BASE as GITILES, USER_AGENT, AcquireError,
                       _http_get)
from ..extract.base_features import var_from_feature_name
from ..model import Change, Finding

GERRIT = "https://chromium-review.googlesource.com"
PROJECT = "chromium/src"

# Gerrit stops at 500 rows for an anonymous query and says nothing about it:
# `start=500` returns an empty list and no `_more_changes` marker, which is
# indistinguishable from having reached the end. A query that comes back at
# exactly the cap is therefore *unproven*, and the window is split and asked
# again rather than believed. Measured: about_flags.cc over the M148 -> M151
# window returns 500 whole and 130 + 196 + 174 = 500 split three ways, so that
# one really is 500 -- but the split is what established it.
PAGE_CAP = 500
PAGE = 250

# A declaration's body ends at its own closing delimiter, not N lines down, so
# that is what is scanned: forward from the line naming the identifier to the
# `;` that ends it, or to the `}` matching the `{` it opens.
#
# Two fixed radii were tried first and both were wrong in the same way, in
# opposite directions. Symmetric and 25 wide, every edit on a file of nothing
# but declarations is near every declaration: `AIManager.CreateLanguageModel`
# drew 4 unrelated CLs, `DevToolsSession.DispatchProtocolCommand` 5. Forward
# and 3 wide fixed those -- both fall to exactly one, and it is the right one --
# but a long parameter list does not fit in three lines, so
# `DedicatedWorkerHostFactoryClient.OnScriptLoadStarted` gaining a seventh
# parameter matched nothing at all. Scanning to the delimiter keeps 1 of 11 on
# the dense cases and finds both of the long ones.
#
# Capped so that a file the scanner does not understand cannot make this
# quadratic; a declaration longer than this is not one we can attribute anyway.
DECL_MAX_LINES = 60

# What one line of a diff is. `a` and `b` were being flattened into a single
# "changed" flag, which throws away the one thing that says *which direction*
# an edit went -- and direction is the whole of the strongest evidence there
# is. A CL whose added lines carry the fact's new value is not merely near the
# change, it is the change.
#
# CONTEXT is 0 and ADDED is 1 so that the older `(line, bool)` shape still
# reads correctly: a line flagged `True` is an added line, which is what a
# caller saying "this line changed" means.
CONTEXT, ADDED, REMOVED = 0, 1, 2

# Ranked strongest first. `moved` sits just under `exact` because a pure rename
# changes no line at all and is still the whole cause: CL 7810461 renamed
# `html_or_foreign_element.idl` and every member of that interface reads as
# removed at the old path, with nothing in any diff to say so. `declares` is
# next because editing a declaration's body is nearly as direct as editing the
# line that names it, and the line that names it is exactly the line a
# parameter change leaves alone. `described` is last of the four that name the
# fact: an author saying a name is weaker than a diff touching it.
#
# Below those sits the weak pair, and they exist because a reader who opens a
# row has asked a question that "nothing" does not answer. Neither is reached
# while anything above it is available, and each says what it is. `crowded`:
# more than `DECL_MAX` CLs edited this declaration's body, so they no longer
# single one out. `touched`: nothing matched the identifier at all, and these
# are simply the newest CLs that touched the declaring file.
_STRENGTH = {"introduced": 0, "exact": 1, "moved": 2, "declares": 3,
             "described": 4, "crowded": 5, "touched": 6}

# Everything ranked above this names *this* fact and is printed as a citation.
# At or below it a CL is a lead the reader has to judge, and the panel says so
# in those words rather than leaving a badge to carry the distinction alone.
CITES = 5


def strength(match: str) -> int:
    """How strongly a verdict names the fact; lower is stronger.

    One definition, because there were three. `_prune` defaulted an unknown
    verdict to 9 (weakest), `enrich` indexed the table directly and would have
    raised, and `report/markdown.py` defaulted to 0 -- so a verdict none of
    them recognised sorted last in one place, crashed in another, and printed
    as the strongest citation in the third. Unknown means unranked, and
    unranked belongs below everything that is ranked.
    """
    return _STRENGTH.get(match, len(_STRENGTH))

# How many CLs one row prints before the list is cut. Twelve rather than
# eight, matched to the cap the issue block already uses, because a revert and
# reland chain runs longer than a citation does and the eight were being taken
# off the newest end -- which on a chain is the end that holds the origin.
# Whatever is cut is now said out loud rather than folded into the pool count.
KEEP_MAX = 12

# How many CLs a `touched` fallback offers. Three, because it is reached
# exactly when nothing distinguishes them, and a longer list of undistinguished
# CLs is the 500-row problem this whole stage exists to avoid.
TOUCHED_MAX = 3

# How many `declares` CLs a finding may carry before they stop singling one
# out and are demoted to `crowded`.
#
# Proximity identifies a change only when it is scarce, and the directional
# rule is scarce where the symmetric one was not: on ai_manager.mojom it picks
# 1 of 11 where the old one picked 4, and on devtools_agent.mojom 1 of 11 where
# the old one picked 5. Four is therefore affordable -- and it has to be, since
# a field is reached through its struct, and three CLs really did edit
# `struct TokenError` in the window, one of them named "[FedCM] Modernize
# TokenError::url from string to url.mojom.Url".
#
# Past it they used to be dropped outright. That is honest -- four confident
# wrong answers are worse than none -- but it answers a reader who opened the
# row with silence, about a declaration eleven CLs really did edit. They are
# demoted instead, which keeps the confidence away from them without throwing
# away what they do say.
DECL_MAX = 4


# Gerrit rate-limits an anonymous client and says so with HTTP 429. Measured:
# eight workers over 1,568 candidate diffs drew one, and the generic retry in
# `acquire` backs off 1.5s, 3s, 6s -- too short for a limiter counting by the
# minute. A 429 that is retried too fast becomes a fetch that quietly returns
# nothing, and nothing is indistinguishable here from "this CL does not
# mention the identifier", which would turn a network hiccup into a false
# "no CL found". So 429 gets its own, much longer, ladder, and whatever still
# fails is counted and disclosed rather than absorbed.
_RATE_LIMIT_BACKOFF = (5, 20, 60)


class GerritError(Exception):
    pass


class _Failures:
    """How many fetches never came back, so the summary can say so."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.count = 0
        self.first = ""

    def record(self, url: str, detail: str) -> None:
        with self.lock:
            self.count += 1
            if not self.first:
                self.first = f"{url} ({detail})"


_failures = _Failures()

# (CL number, path) -> where that CL moved the path to. Filled by `_diff` when
# it follows a rename, and read by the scan afterwards, so establishing that a
# file moved costs nothing beyond the request `_diff` already had to make.
# Asking the question directly instead would be one file-list request per
# candidate CL -- about a thousand on a real top-300 run, to find two renames.
_followed: Dict[Tuple[int, str], str] = {}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _strip_xssi(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    if text.startswith(")]}"):
        text = text.split("\n", 1)[1] if "\n" in text else "{}"
    return text


def _cache_path(cache_dir: str, *parts: str) -> str:
    return os.path.join(cache_dir, "gerrit", *parts)


def _slug(text: str) -> str:
    """A filename that survives every filesystem, and every process.

    The long form used `hash()`, which Python salts per process: the same path
    produced a different file on every run, so a cache entry could never be
    read back by anything but the run that wrote it. Unreached on the paths
    this project actually holds -- none of 338 real ones is long enough -- and
    silent when reached, which is the combination worth removing.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    if len(safe) <= 120:
        return safe
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return safe[:100] + "_" + digest


def _get_json(url: str, cache_dir: str, key: Sequence[str],
              refresh: bool = False, log=lambda m: None):
    """Fetch JSON, caching it forever.

    A merged CL and its diff never change again, so the cache has no expiry.
    The search results do change -- a later CL can join a window that is still
    open at the newest end -- which is what ``refresh`` is for.
    """
    path = _cache_path(cache_dir, *key)
    if os.path.exists(path) and not refresh:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    raw = None
    for attempt, pause in enumerate((0,) + _RATE_LIMIT_BACKOFF):
        if pause:
            time.sleep(pause)
        try:
            raw = _http_get(url, timeout=90, retries=3)
            break
        except AcquireError as exc:
            detail = str(exc)
            if "429" not in detail or attempt == len(_RATE_LIMIT_BACKOFF):
                _failures.record(url, detail)
                log(f"  gerrit unavailable: {exc}")
                return None
    if raw is None:
        return None
    try:
        doc = json.loads(_strip_xssi(raw))
    except json.JSONDecodeError:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return doc


# ---------------------------------------------------------------------------
# The window: which CLs could possibly explain a difference between two tags
# ---------------------------------------------------------------------------

_BRANCHED_FROM = re.compile(
    r"Cr-Branched-From: ([0-9a-f]{40})-refs/heads/main@\{#(\d+)\}")
_GIT_TIME = re.compile(r"^\w{3} (\w{3}) (\d{1,2}) (\d{2}):(\d{2}):(\d{2}) (\d{4})$")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _parse_git_time(text: str) -> Optional[_dt.date]:
    m = _GIT_TIME.match((text or "").strip())
    if not m:
        return None
    return _dt.date(int(m.group(6)), _MONTHS[m.group(1)], int(m.group(2)))


def _commit(ref: str, cache_dir: str, refresh: bool = False,
            log=lambda m: None) -> Optional[dict]:
    quoted = urllib.parse.quote(ref, safe="/")
    return _get_json(f"{GITILES}/+/{quoted}?format=JSON",
                     cache_dir, ("commits", _slug(ref) + ".json"),
                     refresh=refresh, log=log)


def window_for(from_ref: str, to_ref: str, cache_dir: str,
               refresh: bool = False, log=lambda m: None) -> Optional[Tuple[str, str]]:
    """The main-branch date range that can hold the CL behind any difference.

    A release tag records where it left main:

        Cr-Branched-From: 059c884787b1...-refs/heads/main@{#1654411}

    Everything on main before the *from* tag's branch point is in both trees,
    so it cannot explain a difference -- that is the lower bound, and it is a
    fact the tag states about itself rather than an estimate from its date.
    M148's branch point is 2026-04-06 while the tag itself is dated 2026-05-26,
    so taking the tag date would have started the window seven weeks late and
    lost every CL in between.

    The upper bound is the *to* tag's own date, not its branch point. Six weeks
    of merge-backs land on the release branch after it is cut -- M151 branched
    2026-06-29 and the tag is 2026-08-10 -- and those merge-backs are in the
    tree being compared. Their originals landed on main by the tag date at the
    latest, so the tag date is the honest ceiling.

    The result is deliberately a superset. Widening it only adds candidates,
    and every candidate still has to survive the diff filter.
    """
    bounds: List[_dt.date] = []
    tag = _commit(from_ref, cache_dir, refresh, log)
    if not tag:
        return None
    branched = _BRANCHED_FROM.search(tag.get("message", "") or "")
    if branched:
        base = _commit(branched.group(1), cache_dir, refresh, log)
        start = _parse_git_time((base or {}).get("committer", {}).get("time", ""))
    else:
        start = _parse_git_time(tag.get("committer", {}).get("time", ""))
    end_tag = _commit(to_ref, cache_dir, refresh, log)
    end = _parse_git_time((end_tag or {}).get("committer", {}).get("time", ""))
    if not start or not end or end <= start:
        return None
    bounds = [start, end + _dt.timedelta(days=1)]
    return bounds[0].isoformat(), bounds[1].isoformat()


# ---------------------------------------------------------------------------
# Candidates: the CLs that touched one file inside the window
# ---------------------------------------------------------------------------

def _query(term: str, after: str, before: str, kind: str = "file",
           branch: bool = True) -> str:
    """One Gerrit query, in the three scopes this stage asks in.

    ``kind="file"`` wraps the term as a path; ``kind="raw"`` passes it through,
    which is how the message search below asks for several tokens at once.

    ``branch`` pins the search to main and is dropped when a file comes back
    with nothing there. Six weeks of merge-backs land on a release branch
    after it is cut, and those commits are in the tree being compared -- the
    window's upper bound already admits their dates, so pinning the branch was
    the only thing hiding them.
    """
    scope = f'file:"{term}"' if kind == "file" else term
    return (f'project:{PROJECT} status:merged '
            + ("branch:main " if branch else "")
            + f'{scope} mergedafter:{after} mergedbefore:{before}')


def _page(term: str, after: str, before: str, start: int, cache_dir: str,
          refresh: bool, log, kind: str = "file",
          branch: bool = True) -> List[dict]:
    q = urllib.parse.quote(_query(term, after, before, kind, branch))
    url = (f"{GERRIT}/changes/?q={q}&n={PAGE}&start={start}"
           f"&o=CURRENT_REVISION&o=CURRENT_COMMIT")
    # The scope is part of the key. Two searches for the same file that differ
    # only in whether the branch was pinned are different answers, and the
    # second would have read the first's cache entry.
    scope = f"{kind}{'' if branch else '_anybranch'}"
    key = ("search", _slug(term), f"{scope}_{after}_{before}_{start}.json")
    doc = _get_json(url, cache_dir, key, refresh=refresh, log=log)
    return doc if isinstance(doc, list) else []


def _search_window(path: str, after: str, before: str, cache_dir: str,
                   refresh: bool, log, depth: int = 0,
                   branch: bool = True) -> Tuple[List[dict], bool]:
    """Every merged CL touching ``path`` in the window, and whether that is proven.

    Returns ``(changes, truncated)``. A window that comes back at exactly the
    cap is split in half and asked again, because the cap and the true answer
    are indistinguishable from one response. ``truncated`` is True only when a
    window one day wide still returns the cap, which is the point at which
    splitting can no longer help.
    """
    rows: List[dict] = []
    start = 0
    while len(rows) < PAGE_CAP:
        page = _page(path, after, before, start, cache_dir, refresh, log,
                     "file", branch)
        rows += page
        if len(page) < PAGE:
            break
        start += len(page)
    if len(rows) < PAGE_CAP:
        return rows, False

    lo = _dt.date.fromisoformat(after)
    hi = _dt.date.fromisoformat(before)
    if (hi - lo).days <= 1 or depth >= 6:
        return rows, True
    mid = (lo + (hi - lo) / 2).isoformat()
    left, lt = _search_window(path, after, mid, cache_dir, refresh, log,
                              depth + 1, branch)
    right, rt = _search_window(path, mid, before, cache_dir, refresh, log,
                               depth + 1, branch)
    merged: Dict[int, dict] = {}
    for cl in left + right:
        merged[cl["_number"]] = cl
    return list(merged.values()), (lt or rt)


# ---------------------------------------------------------------------------
# The filter: does this CL's diff of this file mention this identifier
# ---------------------------------------------------------------------------

def spend_order(cost: Dict[str, int], served: Dict[str, int],
                budget: int) -> Tuple[List[str], List[str]]:
    """Which files to read diffs for, cheapest-per-finding first.

    A declaration file is read whole whether it explains three findings or
    one, so the honest unit of value is requests *per finding*. Measured on a
    real M148 -> M151 top 150: `autofill_features.cc` answers 16 findings at 8
    requests each, while `extension_features.cc` spends 44 on a single row and
    `runtime_enabled_features.json5` spends 500 on one. Spending in ascending
    ratio means a budget that runs out gives up the worst trade first --
    and at the default it gives up only trades that buy nothing: 1,200 diffs
    resolve the same 131 findings that 1,568 do.

    A file is taken whole or not at all. Reading half a file's CLs would make
    "no CL edits this line" depend on which half, and that is exactly the
    claim this stage is not allowed to make by accident.

    Returns ``(paths_to_read, skipped_descriptions)``; a budget of 0 reads
    everything.
    """
    order = sorted(cost, key=lambda p: (cost[p] / max(1, served.get(p, 0) or 1),
                                        cost[p], p))
    read: List[str] = []
    skipped: List[str] = []
    spent = 0
    for path in order:
        if budget and spent + cost[path] > budget:
            skipped.append(f"{path} ({cost[path]} CLs, "
                           f"{served.get(path, 0)} findings)")
            continue
        spent += cost[path]
        read.append(path)
    return read, skipped


def _blocks(doc: dict) -> List[Tuple[str, bool]]:
    """Gerrit's diff blocks as ``(line, changed)``, all four shapes handled.

    Three of the four were getting this wrong, and each wrong in a way that
    reads as evidence rather than as an error:

    - ``{"skip": N}`` stands for N unchanged lines Gerrit did not send. Ignoring
      it silently shortened the file, which moves every later line and so moves
      what counts as `nearby`. Rare -- 5 of 2,329 real diffs -- but one of those
      is the whole of a renamed file, below.
    - ``{"a": [...], "b": [...], "common": true}`` is Gerrit saying these lines
      are the *same content*, differing only inside the line: a reindent. Read
      as changed, a CL that reformats a file becomes an `exact` match for every
      declaration in it. 49 such blocks in the same sample.
    - ``{"ab": [...]}`` is context and ``{"a"/"b"}`` without ``common`` is a
      real edit; those two were already right.
    """
    seq: List[Tuple[str, int]] = []
    for block in doc.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if "skip" in block:
            try:
                seq += [("", CONTEXT)] * int(block["skip"])
            except (TypeError, ValueError):
                pass
            continue
        if "ab" in block:
            seq += [(line, CONTEXT) for line in block["ab"] or []]
            continue
        changed = not block.get("common")
        for side, state in (("a", REMOVED), ("b", ADDED)):
            seq += [(line, state if changed else CONTEXT)
                    for line in block.get(side) or []]
    return seq


def _renamed_to(cl: dict, path: str, cache_dir: str, refresh: bool,
                log) -> Optional[str]:
    """Where this CL moved ``path`` to, if it moved it.

    Gerrit answers a diff for the *old* path of a renamed file with
    ``change_type: MODIFIED`` and the whole file as one ``skip`` block -- no
    404, no rename marker, just nothing to match against. Measured: that is
    exactly what CL 7810461 returns for ``html_or_foreign_element.idl``, and
    it is why "Rename HTMLOrForeignElement to HTMLOrSVGOrMathMLElement" was
    read as no evidence for three removed IDL members it plainly explains.

    Only asked when a diff comes back with nothing changed, which cannot
    happen for an honest match -- the search already established this CL
    touched this file.
    """
    rev = cl.get("current_revision")
    if not rev:
        return None
    doc = _get_json(f"{GERRIT}/changes/{cl['id']}/revisions/{rev}/files/",
                    cache_dir, ("files", str(cl["_number"]) + ".json"),
                    refresh=refresh, log=log)
    if not isinstance(doc, dict):
        return None
    for new_path, meta in doc.items():
        if isinstance(meta, dict) and meta.get("old_path") == path:
            return new_path
    return None


def _diff(cl: dict, path: str, cache_dir: str, refresh: bool,
          log=lambda m: None) -> List[Tuple[str, bool]]:
    """The file as this CL left it, each line flagged as changed or not."""
    rev = cl.get("current_revision")
    if not rev:
        return []
    fid = urllib.parse.quote(path, safe="")
    url = f"{GERRIT}/changes/{cl['id']}/revisions/{rev}/files/{fid}/diff"
    key = ("diffs", str(cl["_number"]), _slug(path) + ".json")
    doc = _get_json(url, cache_dir, key, refresh=refresh, log=log)
    if not isinstance(doc, dict):
        return []
    seq = _blocks(doc)
    if any(changed for _, changed in seq):
        return seq
    moved = _renamed_to(cl, path, cache_dir, refresh, log)
    if not moved:
        return seq
    _followed[(cl["_number"], path)] = moved
    fid = urllib.parse.quote(moved, safe="")
    doc = _get_json(
        f"{GERRIT}/changes/{cl['id']}/revisions/{rev}/files/{fid}/diff",
        cache_dir, ("diffs", str(cl["_number"]), _slug(moved) + ".json"),
        refresh=refresh, log=log)
    return _blocks(doc) if isinstance(doc, dict) else seq


def _match_message(cl: dict, tokens: Set[str]) -> bool:
    """Does the CL's own description name this identifier?

    Free: the description arrives with the candidate list, so this costs no
    request at all. It is also not redundant with the diff -- measured over the
    top 150 findings of a real M148 -> M151 run, 17 findings are found by the
    description and *not* by the diff, because a CL can delete the declaration
    it is named after and leave the identifier in no surviving line.
    """
    text = cl.get("subject", "") + "\n" + _message_of(cl)
    return any(tok in text for tok in tokens)


class _Scanned:
    """One CL's diff of one file, arranged so a token can be rejected fast.

    The naive shape of this -- for every finding, for every CL, for every line,
    for every token -- is quadratic in the two things that grow: a file with
    127 CLs answering 16 findings ran roughly a million substring searches, and
    resolving 500 findings cost 83 seconds of pure matching. Almost all of it
    was spent proving a token is absent, which one search over the joined text
    settles.

    Identifiers contain no newline, so joining lines with one cannot create a
    match that straddles two of them.
    """

    __slots__ = ("seq", "changed_blob", "all_blob", "changed",
                 "added_blob", "removed_blob")

    def __init__(self, seq: Sequence[Tuple[str, int]]) -> None:
        self.seq = seq
        self.changed_blob = "\n".join(line for line, st in seq if st)
        self.all_blob = "\n".join(line for line, _ in seq)
        self.changed = {i for i, (_, st) in enumerate(seq) if st}
        # The two sides kept apart. Which side a value landed on is the
        # difference between "this CL touched the declaration" and "this CL
        # is the one that put the new value there".
        self.added_blob = "\n".join(l for l, st in seq if st == ADDED)
        self.removed_blob = "\n".join(l for l, st in seq if st == REMOVED)

    def declaration_edited(self, start: int) -> bool:
        """Does a changed line fall inside the declaration naming this line?

        Three shapes, tried in order, because the tree holds three:

        1. The line opens a block -- `struct Bar {` -- so the region runs to
           the matching `}`.
        2. The line is or starts a statement, so the region runs to the `;`
           that ends it: `Type name;` is one line, `Foo(` plus a parameter per
           line is however many it takes.
        3. Neither closed, which means the name is a *member* of a record
           written in some other grammar. `runtime_enabled_features.json5`
           spells a feature

               {
                 name: "GetComputedStyleOutsideFlatTree",
                 status: "stable",
               },

           where the naming line ends in a comma and nothing after it ever ends
           in a `;`. Scanning forward could only run to the cap, so the region
           is instead the innermost block *enclosing* the name. Measured: that
           picks 1 of the 510 CLs touching the file, and it is CL 7895296,
           "Return empty styles for getComputedStyle() outside flat tree".
        """
        span = self.declaration_span(start)
        return any(i in self.changed for i in span) if span else False

    def declaration_span(self, start: int) -> Optional[range]:
        """The line indices the declaration at ``start`` occupies.

        Derived once and asked two questions -- was it edited, and did the
        edit introduce this fact's new value -- because deriving the region
        twice is how the two answers drift apart.
        """
        seq = self.seq
        limit = min(len(seq), start + DECL_MAX_LINES)
        if seq[start][0].rstrip().endswith("{"):
            return self._block_span(start, limit)
        # The region only counts once it is known to have closed here. Reading
        # a change on the way to finding out reported the *next* record's edit
        # as this one's, on exactly the grammar that made the forward scan
        # fail: json5 has no `;`, so the walk ran straight out of the feature
        # it was reading and into the one below.
        for i in range(start, limit):
            if seq[i][0].rstrip().endswith(";"):
                return range(start, i + 1)
        return self._enclosing_span(start)

    def _block_span(self, start: int, limit: int) -> range:
        depth = 0
        for i in range(start, limit):
            depth += self.seq[i][0].count("{") - self.seq[i][0].count("}")
            if i > start and depth <= 0:
                return range(start, i + 1)
        # A block the scanner never sees close is capped rather than dropped:
        # the cap is already the promise this scan makes about how far it will
        # read, and honouring it here keeps a long declaration answerable.
        return range(start, limit)

    def declaration_introduced(self, start: int, gained: Set[str],
                               lost: Set[str]) -> bool:
        """Did this CL put the fact's new value into its declaration?

        The sharpest question available, and the only one whose answer is the
        change itself rather than a neighbour of it. `border_offset` moving
        from `Vector2d` to `Vector2dF` is *some* CL adding a line that says
        `Vector2dF` inside that declaration -- and among the CLs that touched
        the file, that is one of them.
        """
        span = self.declaration_span(start)
        if not span:
            return False
        for i in span:
            line, state = self.seq[i]
            if state == ADDED and any(v in line for v in gained):
                return True
            if state == REMOVED and any(v in line for v in lost):
                return True
        return False

    def _enclosing_span(self, start: int) -> Optional[range]:
        """The innermost block containing `start`, if one opens close above."""
        opener = None
        for i in range(start, max(-1, start - DECL_MAX_LINES), -1):
            if self.seq[i][0].rstrip().endswith("{"):
                opener = i
                break
        if opener is None:
            return None
        return self._block_span(opener,
                                min(len(self.seq), opener + DECL_MAX_LINES))


def _match(scan: "_Scanned", tokens: Set[str], container: str = "",
           gained: Set[str] = frozenset(),
           lost: Set[str] = frozenset()) -> str:
    """The strongest evidence this diff carries, or "".

    ``container`` is the weaker token, and it is kept apart rather than added
    to ``tokens`` because it cannot support the stronger verdict: editing a
    line that mentions the enclosing struct is not editing the line that
    declares this member.

    ``gained``/``lost`` are what the finding says the change did, and they are
    asked first because they are the only question whose answer *is* the
    change. "A changed line mentions this identifier" is satisfied by any CL
    that touched the declaration for any reason; "an added line inside this
    declaration carries the value the fact ended up with" is satisfied by the
    CL that put it there.
    """
    if not scan.changed_blob:
        return ""
    search = set(tokens)
    if container:
        search.add(container)
    # Two cheap searches over the joined sides reject almost every CL before a
    # line is walked, which is what keeps this affordable on a 500-CL file.
    if ((gained and any(v in scan.added_blob for v in gained))
            or (lost and any(v in scan.removed_blob for v in lost))):
        for i, (line, _) in enumerate(scan.seq):
            if (any(t in line for t in search)
                    and scan.declaration_introduced(i, gained, lost)):
                return "introduced"
    for token in tokens:
        if token in scan.changed_blob:
            return "exact"
    # Absent from the file entirely is the common case, and one search over the
    # whole text settles it before any line is walked.
    if not any(token in scan.all_blob for token in search):
        return ""
    for i, (line, _) in enumerate(scan.seq):
        if any(token in line for token in search) and scan.declaration_edited(i):
            return "declares"
    return ""


# The identifier a diff would spell. Both spellings of a base::Feature appear
# in the same file since the macro dropped its string argument, so both are
# asked for -- via the one definition of that correspondence, in
# `extract.base_features`, rather than a fifth copy of it here. A key that is
# a path of its own -- `blink.mojom.AIManager.CreateLanguageModel`,
# `settings/glic_page/.../pref:x#y` -- also yields its leaf, which is what the
# declaration line actually says.
_K_PREFIXED = ("base_feature", "blink_runtime_feature")
_LEAF_SPLIT = re.compile(r"[./:#>]")


def tokens_for(change: Change) -> Set[str]:
    out: Set[str] = set()
    for text in (change.key, change.name):
        if not text:
            continue
        out.add(text)
        parts = [p for p in _LEAF_SPLIT.split(text) if p]
        if parts:
            out.add(parts[-1])
        if change.kind == "feature_param" and len(parts) >= 2:
            out.update(parts)
    if change.kind in _K_PREFIXED and change.name:
        out.add(var_from_feature_name(change.name))
    return {t for t in out if len(t) >= 4}


# A delta value long enough to be specific on its own is used whole; anything
# with spaces in it is a construct spanning several lines of the file and is
# reached through the words it gained instead.
_DELTA_WHOLE_MAX = 72
_DELTA_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _codelike(text: str) -> bool:
    """Is this specific enough to search a declaration for?

    `kPreinstalledExtensions`, `IS_ANDROID` and `array<network.mojom.LinkHeader>`
    identify a change. `enabled`, `stable`, `none` and `109` appear in every
    other declaration in the file and identify nothing, so the test is whether
    the value is shaped like code -- an inner capital, an underscore or a dot --
    or is simply too long to be a coincidence.
    """
    if len(text) < 4 or not any(c.isalpha() for c in text):
        return False
    return (any(c.isupper() for c in text) or "_" in text or "." in text
            or len(text) >= 12)


def _delta_values(node, out: Set[str]) -> None:
    """Every searchable string inside one side of a delta, at any depth."""
    if isinstance(node, str):
        if " " not in node and len(node) <= _DELTA_WHOLE_MAX and _codelike(node):
            out.add(node)
        for word in _DELTA_WORD.findall(node):
            if _codelike(word):
                out.add(word)
    elif isinstance(node, dict):
        for key, value in node.items():
            _delta_values(key, out)
            _delta_values(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _delta_values(item, out)


def delta_tokens(change: Change) -> Tuple[Set[str], Set[str]]:
    """What this change put into the tree, and what it took out.

    The strongest signal the report already holds and never spent. A finding
    does not merely name a declaration, it records the declaration's two
    states -- ``{"type": ["array<url.mojom.Url>", "array<network.mojom.LinkHeader>"]}``
    -- and the CL that made that change is, by construction, a CL whose diff
    *adds* a line saying `array<network.mojom.LinkHeader>`.

    Measured on `blink.mojom.TokenError.url`, where the fact's own name cannot
    be searched for at all: 0 of 13 candidate CLs carry the name, and exactly
    one carries the after-value -- CL 7982397, "[FedCM] Modernize
    TokenError::url from string to url.mojom.Url".

    Only the difference is returned. A value on both sides did not change and
    would match every CL that touched the declaration for any reason.
    """
    gained: Set[str] = set()
    lost: Set[str] = set()
    for pair in (change.deltas or {}).values():
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            continue
        before: Set[str] = set()
        after: Set[str] = set()
        _delta_values(pair[0], before)
        _delta_values(pair[1], after)
        # Compared against the other side's *text*, not its token set. A token
        # can be a substring of one that is still there: `Vector2d` reads as
        # lost when the type became `Vector2dF`, and would then match every
        # line carrying the new type -- turning the CL that made the change
        # into evidence of the opposite change.
        before_text = json.dumps(pair[0])
        after_text = json.dumps(pair[1])
        gained |= {t for t in after if t not in before_text}
        lost |= {t for t in before if t not in after_text}
    return gained, lost


def container_for(change: Change) -> str:
    """The struct or interface to fall back on when the fact itself is unwritable.

    A qualified key is our construction, not text: `.mojom` writes

        struct TokenError {
          url.mojom.Url? url;
        };

    and never the string `blink.mojom.TokenError.url`. When the leaf is also
    too short to search for -- `url`, `id`, `name` -- the whole token set is
    unfindable, and 13 diffs were read for a string that cannot occur in any of
    them, then reported as "no CL edits a line carrying this identifier". True,
    and deeply misleading.

    Returned separately rather than mixed into `tokens_for` because it cannot
    earn the same verdict. A changed line containing `TokenError` is not a
    changed line declaring `TokenError.url`, so the container can only ever
    reach `declares` -- "a CL edited the body of the declaration this belongs
    to" -- and never `exact`. Mixed in, it claimed `exact` on two CLs that had
    merely tidied the struct, and pushed the one that says "[FedCM] Modernize
    TokenError::url from string to url.mojom.Url" out of the list.

    Empty when the fact's own name is searchable: `AIManager` names twenty
    methods, and falling back to it when the method itself can be found would
    trade one answer for twenty.
    """
    parts = [p for p in _LEAF_SPLIT.split(change.key or "") if p]
    if len(parts) < 2:
        return ""
    if tokens_for(change) - {change.key}:
        return ""
    container = parts[-2]
    return container if len(container) >= 4 else ""


# ---------------------------------------------------------------------------
# Bug footers, and the history behind one issue
# ---------------------------------------------------------------------------

# Chromium's footer is not always a public issue and not always a bug. Measured
# over the 62 CLs touching content_features.cc in the M148 -> M151 window: 68
# `Bug:` with a numeric id, 3 `Fixed:` with one, 2 `Bug: b/...` pointing at
# Google's internal tracker, 1 spelled `crbug.com/...`, and 3 CLs carrying no
# footer at all. Only the numeric ids resolve on issues.chromium.org, and even
# those can be access-restricted -- one of five sampled returned HTTP 403 -- so
# an id is offered as a link and never as a promise.
_BUG_FOOTER = re.compile(r"^(Bug|Fixed):\s*(.+)$", re.M)
_NUMERIC = re.compile(r"^(?:crbug\.com/|chromium:)?(\d{6,})$")


def bugs_in(message: str) -> List[dict]:
    """Public issue ids in a commit message, and whether the CL closes them.

    `Fixed:` and `Bug:` are not the same claim -- one says this CL is the fix,
    the other says it is related work -- and Chromium uses both: 575 `Bug:` to
    34 `Fixed:` across a real sample. Anything that is not a public numeric id
    is dropped here rather than offered as a link that cannot resolve.
    """
    out: List[dict] = []
    seen = set()
    for key, value in _BUG_FOOTER.findall(message or ""):
        for token in re.split(r"[,\s]+", value.strip()):
            m = _NUMERIC.match(token)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            entry = {"id": m.group(1)}
            if key == "Fixed":
                entry["closes"] = True
            out.append(entry)
    return out


def _title_in(doc, issue: str) -> str:
    """The issue's summary line, dug out of a positional response.

    issues.chromium.org answers in Google's index-addressed JSON -- no field
    names anywhere -- so this looks for the one landmark that is not an index:
    the array whose second element is the issue number. Its third element is
    the issue state, and the first string in that is the summary. Verified
    against eight real issues, all eight correct.

    Nothing else is taken. A component path is in there too and it did not
    survive the same check: issue 381086791 yielded `Blink>AI` for a MacOS
    memory regression, which means the walk was finding somebody else's field.
    A title that is right eight times out of eight is worth showing; a
    component that is wrong once in eight is worth less than nothing.
    """
    found: List[list] = []

    def walk(node) -> None:
        if not isinstance(node, list):
            return
        if len(node) > 2 and node[1] == int(issue) and isinstance(node[2], list):
            found.append(node)
        for child in node:
            walk(child)

    try:
        walk(doc)
    except (TypeError, ValueError):
        return ""
    for node in found:
        for value in node[2]:
            if isinstance(value, str) and value.strip():
                return value.strip()[:160]
    return ""


def issue_meta(issue: str, cache_dir: str, refresh: bool = False,
               log=lambda m: None) -> dict:
    """Whether a reader can open this issue, and what it is called.

    Both answers come from one request, which is why the accessibility check
    is a GET and no longer a HEAD: the HEAD cost nothing and told us only that
    the door was open, while the same request costs a body and also says what
    is behind it. Measured on a real M148 -> M151 run, **70 of 236 linked
    issues answer HTTP 403** -- three dead links in ten, and an unmarked one
    reads as a broken tool rather than as a closed door.

    An unknown answer is not a restricted one: a network fault must never turn
    a working link into a warning, so anything that is not an explicit refusal
    is reported as reachable and untitled.
    """
    path = _cache_path(cache_dir, "issue_access", f"{issue}.json")
    if os.path.exists(path) and not refresh:
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if isinstance(cached, dict) and "title" in cached:
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    url = f"https://issues.chromium.org/action/issues/{issue}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403, 404):
            return {"public": True, "title": ""}
        meta = {"public": False, "title": ""}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        return meta
    except Exception:
        return {"public": True, "title": ""}
    title = ""
    try:
        title = _title_in(json.loads(_strip_xssi(body)), issue)
    except (json.JSONDecodeError, ValueError):
        pass
    meta = {"public": True, "title": title}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    return meta


def issue_history(issue: str, cache_dir: str, limit: int = 25,
                  refresh: bool = False, log=lambda m: None) -> List[dict]:
    """Every CL citing one issue, newest first -- the fix history for it.

    Gerrit indexes the `Bug:` footer, so this needs no access to the tracker,
    which matters because the tracker is the half that can refuse. Measured:
    issue 40275333 returns 10 CLs spanning 2024-05 to 2026-06, ending at
    "Remove feature flag kWebAppSystemMediaControls" -- the whole arc of a
    feature, from the CL that built it to the one that deleted its flag.
    """
    q = urllib.parse.quote(f"project:{PROJECT} bug:{issue}")
    doc = _get_json(f"{GERRIT}/changes/?q={q}&n={limit}",
                    cache_dir, ("issues", f"{issue}.json"),
                    refresh=refresh, log=log)
    if not isinstance(doc, list):
        return []
    out = []
    for cl in doc:
        out.append({
            "number": cl.get("_number"),
            "subject": cl.get("subject", ""),
            "status": cl.get("status", ""),
            "date": (cl.get("submitted") or cl.get("updated") or "")[:10],
            "url": f"{GERRIT}/c/{PROJECT}/+/{cl.get('_number')}",
        })
    out.sort(key=lambda c: c["date"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def _message_of(cl: dict) -> str:
    for rev in (cl.get("revisions") or {}).values():
        commit = rev.get("commit") or {}
        return rev.get("commit_with_footers") or commit.get("message") or ""
    return ""


def _label(finding: Finding, path: str) -> str:
    """Which file a CL was found under -- only when there is more than one.

    60 of 3,022 findings on a real run are declared in two files, because the
    declaration moved. Both are searched and both contribute CLs, and until
    the panel said which was which it read as one file's history with a wrong
    denominator.
    """
    return path if len(finding.change.paths or []) > 1 else ""


def _prune(hits: List[dict]) -> List[dict]:
    """Keep the evidence that identifies something; demote the rest.

    An `exact` hit makes every `declares` one on the same finding redundant.
    More than ``DECL_MAX`` of them and no strong one means the declaration was
    edited by a crowd -- on `ai_manager.mojom` all 11 candidate CLs edit some
    method -- so they no longer single anything out.

    They used to be dropped for exactly that, and dropping them is defensible
    right up to the moment a reader clicks the row and is told nothing was
    found about a declaration that eleven CLs edited. Demoted to `crowded`
    they rank below every verdict that names the fact, so they can never be
    read as one, and the reader still gets the eleven.

    Strongest first, then newest, because the CL a reader wants is usually the
    last one to touch the line.
    """
    strong = [h for h in hits
              if h["match"] in ("introduced", "exact", "moved", "described")]
    declares = [h for h in hits if h["match"] == "declares"]
    if strong:
        # A `declares` CL edited the body of the declaration without touching
        # the line that names it. Beside an `exact` hit that was read as a
        # weaker copy of the same answer and dropped, and it is not one -- it
        # is a different CL doing different work on the same declaration. On a
        # real top 150 the rule threw away 40 CLs across 18 findings, every one
        # of them a genuine contributor to a row that had more than one.
        #
        # The scarcity test still applies, because it is what `declares` needs
        # to mean anything: a crowd of them singles nothing out whether or not
        # a strong hit is present.
        kept = strong + (declares if len(declares) <= DECL_MAX else [])
    else:
        if len(declares) > DECL_MAX:
            # A crowd of CLs that all edited this declaration is not noise to
            # be thrown away, and it is not a citation either. It is the
            # declaration's history: the fact reached the state the report
            # found it in by passing through these, and the reader who cannot
            # be given one CL can be given the sequence.
            #
            # So it is ordered forward. Every other list here is newest-first,
            # because a citation is the last word on a line; a history read
            # backwards is not a history.
            declares.sort(key=lambda h: _neg_date(h["date"]))
            return [dict(h, match="crowded")
                    for h in reversed(declares[:KEEP_MAX])]
        kept = declares
    # Selected strongest-then-newest, because that is what a cap should keep:
    # the current state of the line, not the start of its history.
    kept.sort(key=lambda h: (strength(h["match"]), _neg_date(h["date"])))
    kept = kept[:KEEP_MAX]
    # Then read forward, once there is more than one. A single CL is a
    # citation and has no order; several are a sequence, and the reason the
    # `crowded` branch already reverses itself applies here just as well --
    # a flag that launched, was reverted, relanded, reverted and relanded
    # again is a story, and a story read backwards is not one. This is where
    # those rows actually live: 28 of a real top 150 keep more than one CL.
    if len(kept) > 1:
        kept.sort(key=lambda h: h["date"] or "")
    return kept


def _neg_date(date: str) -> str:
    """Sort dates descending inside an ascending sort. ISO dates only.

    An empty date sorted first, which in a descending sort means *newest* --
    so a CL Gerrit returned without `submitted` or `updated` led every list it
    was in, and led it on the strength of knowing nothing about it. Unknown
    sorts last instead: `~` is above every digit this produces.
    """
    if not date:
        return "~"
    return "".join(chr(ord("9") - int(ch)) if ch.isdigit() else ch
                   for ch in date)


def _compact(cl: dict, match: str, path: str = "") -> dict:
    """One CL, reduced to what a row needs.

    ``revert_of`` and ``cherry_pick_of_change`` come free in the search
    response and were being dropped, which is a waste: they are Gerrit's own
    record of the revert-and-reland chains that make a feature flag's history
    hard to read from subjects alone. 23 of 534 CLs in a real sample are
    reverts and 8 are cherry-picks.

    ``path`` is recorded only when the finding was searched under more than
    one file, because that is the only time a reader cannot tell which file a
    CL belongs to.
    """
    message = _message_of(cl)
    out = {
        "number": cl.get("_number"),
        "subject": cl.get("subject", ""),
        "date": (cl.get("submitted") or cl.get("updated") or "")[:10],
        "match": match,
        "url": f"{GERRIT}/c/{PROJECT}/+/{cl.get('_number')}",
        "bugs": bugs_in(message),
    }
    if cl.get("revert_of"):
        out["reverts"] = cl["revert_of"]
    if cl.get("cherry_pick_of_change"):
        out["cherry_pick_of"] = cl["cherry_pick_of_change"]
    size = (cl.get("insertions") or 0) + (cl.get("deletions") or 0)
    if size:
        out["lines"] = size
    if path:
        out["file"] = path
    return out


# How many message-matched CLs a finding may carry. The search is unscoped by
# file, so a token that reads as an English word can return hundreds; past a
# handful they stop distinguishing and the newest are as good as the list gets.
MESSAGE_MAX = 8


def _by_message(tokens: Set[str], after: str, before: str, cache_dir: str,
                refresh: bool, log) -> List[dict]:
    """CLs whose own description names this identifier, anywhere in the tree.

    Every other lookup here starts from the file the fact is declared in, and
    asks who touched it. That question has shapes it cannot see: a declaration
    generated from a template, a path Gerrit records under another name, a
    `.idl` that arrives by a third-party roll rather than by an edit, a file
    renamed in a CL recorded only under the new name.

    A CL always exists. The two trees differ, so something landed -- "no CL"
    is only ever a statement about this search, never about Chromium. So when
    the file leads nowhere the author's own words are asked instead, unpinned
    from both the file and the branch. What comes back is `described`, which
    is what it is: the CL names the identifier, and nothing here has read a
    diff to say it edited the declaration.

    One request, not a windowed sweep: the point is to have asked, and a token
    generic enough to fill several pages is a token whose pages say nothing.
    """
    if not tokens:
        return []
    # Longest first: `blink.mojom.TokenError.url` distinguishes where `url`
    # cannot, and Gerrit ORs them so a key that is never written as a whole
    # still reaches the tree through its leaf.
    terms = sorted(tokens, key=len, reverse=True)[:3]
    expr = "(" + " OR ".join(f'message:"{t}"' for t in terms) + ")"
    rows = _page(expr, after, before, 0, cache_dir, refresh, log, "raw", False)
    rows.sort(key=lambda c: (c.get("submitted") or ""), reverse=True)
    out: List[dict] = []
    for cl in rows:
        # Gerrit's index tokenises; this is the same substring test the free
        # description pass uses, so a row cannot enter the report on a looser
        # rule than the one that would have found it beside its own file.
        if _match_message(cl, tokens):
            out.append(_compact(cl, "described"))
        if len(out) >= MESSAGE_MAX:
            break
    return out


def _last_resort(finding: Finding, searched: List[str],
                 found: Dict[str, List[dict]]) -> List[dict]:
    """The newest CLs that touched the declaring file, when nothing named it.

    A reader who clicks a row has asked a question, and "no CL among the 13
    read of the 13 that touched this file edits a line carrying this
    identifier" is a true answer that leaves them exactly where they started.
    Those 13 remain the best candidates there are: the fact differs between
    the two trees, and the CLs that touched the file declaring it are where
    the change came from -- as far as the search saw them, since Gerrit's
    500-row cap and `--gerrit-max-cls` both trim from the far end. So the
    newest few are offered as leads --
    marked `touched`, which claims nothing about the identifier, and ranked
    below every verdict that does.

    This is the floor, not a guess. It is reached only once `exact`, `moved`,
    `described`, `declares` and `crowded` have all come back empty, and it is
    itself empty in exactly one shape: no CL touched the file inside the
    window. Nothing can turn that into a citation, and the panel says so
    rather than inventing one.

    Candidates are read from the search, not the diffs, so a file the budget
    declined still answers -- which is the whole point, since that file is the
    one that produced nothing else.
    """
    out: List[dict] = []
    for path in searched:
        for cl in (found.get(path) or [])[:TOUCHED_MAX]:
            out.append(_compact(cl, "touched", _label(finding, path)))
    out.sort(key=lambda h: _neg_date(h["date"]))
    return out[:TOUCHED_MAX]


def enrich(findings: List[Finding], from_ref: str, to_ref: str, cache_dir: str,
           top: int = 150, max_cls_per_file: int = 500, workers: int = 4,
           with_history: int = 250, budget: int = 1200, refresh: bool = False,
           log=lambda m: None) -> dict:
    """Attach CL provenance to the highest-ranked findings, in place.

    Only the top ``top`` findings are resolved, because the cost is one HTTP
    request per (CL, file) pair and a full report names hundreds of files. The
    work is done per *file* rather than per finding -- one file's candidate
    diffs answer every finding declared in it -- so the bill is set by how many
    distinct files the top slice touches, not by how many findings it holds.

    Returns a summary dict for ``report.meta``: what was asked, what was
    resolved, and what could not be proven complete.
    """
    _failures.__init__()
    _followed.clear()
    window = window_for(from_ref, to_ref, cache_dir, refresh, log)
    if not window:
        log("  gerrit: could not derive a commit window from the two refs")
        return {"available": False, "reason": "no window"}
    after, before = window
    log(f"  gerrit: CLs merged {after} .. {before}")

    ranked = sorted(findings, key=lambda f: -f.score)[:top]
    wanted: Dict[str, List[Finding]] = {}
    for finding in ranked:
        for path in (finding.change.paths or [])[:2]:
            wanted.setdefault(path, []).append(finding)
    if not wanted:
        return {"available": False, "reason": "no paths"}
    log(f"  gerrit: {len(ranked)} findings across {len(wanted)} files")

    truncated: List[str] = []
    capped: List[str] = []
    # Files whose CLs were found only once the branch pin came off, and
    # findings answered only by the author's words. Both are reported, because
    # a widened search is a weaker one and a reader is owed that.
    off_main: List[str] = []
    by_message: List[str] = []
    # What the search actually found, before --gerrit-max-cls trimmed it. The
    # row prints "N of M merged CLs touched this file", and M was the trimmed
    # number -- so a file with 510 candidates read as though it had 500, which
    # is the one kind of rounding this stage is not allowed to do.
    total_found: Dict[str, int] = {}

    def candidates(path: str) -> List[dict]:
        rows, cut = _search_window(path, after, before, cache_dir, refresh, log)
        if not rows:
            # A file with nothing on main is not a file nothing landed on.
            # Merge-backs land on the release branch after it is cut, and they
            # are in the tree being compared -- the window already admits their
            # dates, and `branch:main` was the only thing hiding them.
            rows, cut = _search_window(path, after, before, cache_dir, refresh,
                                       log, branch=False)
            if rows:
                off_main.append(path)
        if cut:
            truncated.append(path)
        rows.sort(key=lambda c: (c.get("submitted") or ""), reverse=True)
        total_found[path] = len(rows)
        if len(rows) > max_cls_per_file:
            capped.append(f"{path} ({len(rows)})")
            rows = rows[:max_cls_per_file]
        return rows

    paths = list(wanted)
    with ThreadPoolExecutor(max(1, workers)) as pool:
        found = dict(zip(paths, pool.map(candidates, paths)))

    tokens = {f.uid: tokens_for(f.change) for f in ranked}
    containers = {f.uid: container_for(f.change) for f in ranked}
    deltas = {f.uid: delta_tokens(f.change) for f in ranked}
    hits: Dict[str, List[dict]] = {f.uid: [] for f in ranked}

    # The free pass. Descriptions arrive with the candidate list, so every
    # finding gets whatever its authors said about it before a single diff is
    # fetched -- and if the budget below runs out, this is what is left.
    for path, rows in found.items():
        for finding in wanted[path]:
            for cl in rows:
                if tokens[finding.uid] and _match_message(cl, tokens[finding.uid]):
                    hits[finding.uid].append(
                        _compact(cl, "described", _label(finding, path)))

    # Diffs are the whole bill: one request per (CL, file), and a declaration
    # file is shared, so the same 147 CLs are read whether they explain three
    # findings or one. Spending in ascending requests-per-finding order means a
    # budget that runs out gives up the worst-value file first -- measured on a
    # real M148 -> M151 top 150, `autofill_features.cc` answers 16 findings for
    # 8 requests each while `extension_features.cc` answers 1 for 44.
    read, skipped = spend_order(
        {p: len(rows) for p, rows in found.items()},
        {p: len(fs) for p, fs in wanted.items()}, budget)
    plan: List[Tuple[dict, str]] = [(cl, p) for p in read for cl in found[p]]
    log(f"  gerrit: reading {len(plan)} candidate diffs across {len(read)} files"
        + (f", {len(skipped)} file(s) left to their descriptions"
           if skipped else ""))
    with ThreadPoolExecutor(max(1, workers)) as pool:
        pool.map(lambda job: _diff(job[0], job[1], cache_dir, refresh, log), plan)

    for path in read:
        # Read from what the pass above just wrote. Passing `refresh` again
        # here re-fetched every diff a second time, so `--refresh` cost twice
        # what it had to and hit the rate limiter at half the work.
        diffs = [(cl, _Scanned(_diff(cl, path, cache_dir, False, log)))
                 for cl in found[path]]
        moved_here = {cl["_number"] for cl, _ in diffs
                      if (cl["_number"], path) in _followed}
        for finding in wanted[path]:
            gained, lost = deltas[finding.uid]
            # A name under four characters leaves the token set empty, and the
            # finding used to be dropped here without a diff being read. It
            # still holds two other ways in -- the struct enclosing it, and the
            # value the change introduced -- so the guard asks whether there is
            # anything at all to search with, not whether there is a name.
            if not (tokens[finding.uid] or containers[finding.uid]
                    or gained or lost):
                continue
            for cl, scan in diffs:
                verdict = _match(scan, tokens[finding.uid],
                                 containers[finding.uid], gained, lost)
                if not verdict and cl["_number"] in moved_here:
                    # The file this fact is declared in moved, and the fact is
                    # in it. Nothing was edited, so no line can carry the
                    # evidence -- the move is the evidence.
                    if any(tok in scan.all_blob for tok in tokens[finding.uid]):
                        verdict = "moved"
                if verdict:
                    hits[finding.uid].append(
                        _compact(cl, verdict, _label(finding, path)))

    resolved = exact_only = described_only = leads_only = 0
    for finding in ranked:
        # One CL can arrive as both `described` and `exact`; the strongest wins
        # so a row never lists the same review twice.
        best: Dict[int, dict] = {}
        for hit in hits[finding.uid]:
            prior = best.get(hit["number"])
            if prior is None or _STRENGTH[hit["match"]] < _STRENGTH[prior["match"]]:
                best[hit["number"]] = hit
        matched = list(best.values())
        kept = _prune(matched)
        # Every path the finding was searched under, not just the first. A
        # declaration that moved between files is searched in both, and
        # counting one of them printed "3 of 2 merged CLs touched this file".
        searched = [p for p in (finding.change.paths or [])[:2] if p in found]
        path = searched[0] if searched else ""
        block = finding.enrichment.setdefault("gerrit", {})
        block["candidates"] = sum(total_found.get(p, len(found[p]))
                                  for p in searched)
        read_count = sum(len(found[p]) for p in searched)
        if read_count != block["candidates"]:
            block["candidates_read"] = read_count
        # How many of the candidates the diff actually tied to this fact, as
        # opposed to how many of those survived the cap. The row printed the
        # second as though it were the first -- "8 of 19 merged CLs touched
        # this file" on a finding where 15 matched and 7 were cut -- and said
        # nothing about the cut. The issue block one panel down had this right
        # from the start: "11 CLs cite it, newest 8 shown".
        if len(matched) > len(kept):
            block["matched"] = len(matched)
        block["window"] = [after, before]
        # Set on every finding that was asked about, not only the ones that
        # answered. "No CL edits this line" and "nobody looked" are different
        # answers and the report has to be able to tell them apart -- when this
        # was written only on rows that already had a CL, the two findings in
        # `net/base/features.cc` that the budget declined came out looking
        # exactly like the eleven in `ai_manager.mojom` that were scanned and
        # genuinely matched nothing.
        # True only when every path behind the row was read; a half-read row
        # cannot claim the scan was complete.
        block["diffs_read"] = bool(searched) and all(p in read for p in searched)
        # The floor. Everything above named the fact; this names only the file,
        # and it is what makes a click on any row with a candidate CL answer
        # something instead of nothing.
        if not kept:
            kept = _last_resort(finding, searched, found)
        if not kept:
            # The file led nowhere at all -- not to a match, not even to a
            # candidate. Ask the tree for CLs that name this thing instead,
            # because something landed and only this search has failed.
            kept = _by_message(tokens[finding.uid], after, before, cache_dir,
                               refresh, log)
            if kept:
                block["found_by"] = "message"
                by_message.append(finding.uid)
        if not kept:
            continue
        block["changes"] = kept
        # A lead is not a resolution, and the summary counts them apart so a
        # run cannot report itself as having explained more than it did.
        if all(strength(h["match"]) >= CITES for h in kept):
            leads_only += 1
            continue
        resolved += 1
        if all(h["match"] == "exact" for h in kept):
            exact_only += 1
        elif all(h["match"] == "described" for h in kept):
            described_only += 1

    # One request per *distinct* issue, not per finding, and the result is
    # shared by every row citing it. That distinction is the whole cost: on a
    # real M148 -> M151 top 300, 224 rows carry a bug but they name only 174
    # different issues, and one issue is cited by twelve rows at once.
    #
    # This used to stop after the first ten findings, which meant 254 of 264
    # rows with a CL never had their issue looked up at all -- not because the
    # answer was uninteresting but because of a number picked out of the air.
    # 174 requests against the 1,194 this run already spends on diffs is 15%
    # more for an answer on every row instead of ten.
    by_issue: Dict[str, List[Finding]] = {}
    for finding in ranked:
        block = (finding.enrichment or {}).get("gerrit") or {}
        # Every CL shown on the row, not only the first. A row often carries a
        # launch, a revert and a reland, and reading the issue off whichever
        # happened to sort first answered a different question each time the
        # ordering changed.
        for cl in block.get("changes") or []:
            for bug in cl.get("bugs") or []:
                by_issue.setdefault(bug["id"], [])
                if finding not in by_issue[bug["id"]]:
                    by_issue[bug["id"]].append(finding)
    # A budget cut drops the least important issue, so the order is the best
    # score among the rows citing it.
    chosen = sorted(by_issue, key=lambda i: -max(f.score for f in by_issue[i]))
    dropped_issues = max(0, len(chosen) - with_history) if with_history else 0
    chosen = chosen[:with_history] if with_history else chosen
    with ThreadPoolExecutor(max(1, workers)) as pool:
        fetched = dict(zip(chosen, pool.map(
            lambda i: issue_history(i, cache_dir, refresh=refresh, log=log),
            chosen)))
        meta = dict(zip(chosen, pool.map(
            lambda i: issue_meta(i, cache_dir, refresh, log), chosen)))
    public = {i: m.get("public", True) for i, m in meta.items()}
    restricted = sorted(i for i in chosen if not public.get(i, True))

    # Marked on the CL line itself, because that is where the link is and a
    # reader deserves to know before clicking rather than after.
    for finding in ranked:
        for cl in ((finding.enrichment or {}).get("gerrit") or {}).get(
                "changes") or []:
            for bug in cl.get("bugs") or []:
                if bug["id"] in public and not public[bug["id"]]:
                    bug["restricted"] = True

    # Every issue the row's CLs cite, not the first one that happened to have a
    # history. A row carrying a launch, a revert and a reland often cites two
    # or three, and picking one meant the answer changed with the sort order.
    for issue in chosen:
        history = fetched.get(issue) or []
        # One CL and one CL only means the list would repeat the row above it.
        # The CL line already links the issue, so nothing is hidden by this --
        # the block appears when there is history, not merely an issue.
        if len(history) <= 1:
            continue
        for finding in by_issue[issue]:
            issues = finding.enrichment["gerrit"].setdefault("issues", [])
            if any(existing["id"] == issue for existing in issues):
                continue
            issues.append({
                "id": issue,
                "url": f"https://issues.chromium.org/issues/{issue}",
                "restricted": not public.get(issue, True),
                "title": (meta.get(issue) or {}).get("title", ""),
                "changes": history[:12],
                "total": len(history),
            })
    for finding in ranked:
        issues = ((finding.enrichment or {}).get("gerrit") or {}).get("issues")
        if issues:
            # Busiest first: an issue with fourteen CLs is the story, one with
            # two is a footnote.
            issues.sort(key=lambda i: -i["total"])
    histories = sum(
        1 for f in ranked
        if ((f.enrichment or {}).get("gerrit") or {}).get("issues"))

    log(f"  gerrit: {resolved}/{len(ranked)} findings carry a CL "
        f"({exact_only} on exact matches alone, {described_only} on the "
        f"author's description alone), {histories} with issue history "
        f"from {len(fetched)} distinct issues")
    if leads_only:
        log(f"  gerrit: {leads_only} further finding(s) carry leads only -- "
            f"CLs that touched the declaring file or its declaration, but "
            f"none that names the fact")
    if off_main:
        log(f"  gerrit: {len(off_main)} file(s) had no CL on main and were "
            f"found on a release branch instead: {off_main[0]}"
            + (" ..." if len(off_main) > 1 else ""))
    if by_message:
        log(f"  gerrit: {len(by_message)} finding(s) had no CL touching their "
            f"declaring file at all and were answered by searching commit "
            f"messages for the identifier")
    if restricted:
        log(f"  ! gerrit: {len(restricted)} of {len(chosen)} linked issue(s) "
            f"are access-restricted and will not open without Google "
            f"credentials; they are marked in the report")
    if dropped_issues:
        log(f"  ! gerrit: --gerrit-issues stopped at {with_history}, so "
            f"{dropped_issues} issue(s) were not looked up")
    if skipped:
        log(f"  ! gerrit: the diff budget stopped at {budget}, so "
            f"{len(skipped)} file(s) were answered from descriptions only: "
            f"{skipped[0]}" + (" ..." if len(skipped) > 1 else ""))
    if truncated:
        log(f"  ! gerrit: {len(truncated)} file(s) hit Gerrit's 500-row cap "
            f"even split by day; their CL list is partial: {truncated[0]}"
            + (" ..." if len(truncated) > 1 else ""))
    if capped:
        log(f"  ! gerrit: {len(capped)} file(s) had more candidates than "
            f"--gerrit-max-cls; only the newest were read: {capped[0]}"
            + (" ..." if len(capped) > 1 else ""))
    if _failures.count:
        log(f"  ! gerrit: {_failures.count} fetch(es) failed and were read as "
            f"no evidence; a finding may have a CL this run did not see. "
            f"First: {_failures.first}")
    return {
        "available": True,
        "window": [after, before],
        "findings_asked": len(ranked),
        "findings_resolved": resolved,
        "findings_leads_only": leads_only,
        "findings_by_message": len(by_message),
        "files_found_off_main": off_main,
        "files_searched": len(wanted),
        "candidate_diffs": len(plan),
        "budget": budget,
        "files_left_to_descriptions": skipped,
        "issue_histories": histories,
        "issues_fetched": len(fetched),
        "issues_restricted": len(restricted),
        "incomplete_files": truncated,
        "capped_files": capped,
        "failed_fetches": _failures.count,
    }
