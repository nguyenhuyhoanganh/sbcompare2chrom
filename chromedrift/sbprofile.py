"""The downstream side of the join: what this browser actually touches.

Chromium changing something only matters if *we* depend on it.  This module
builds a ``TouchSet`` -- the set of Chromium paths and symbols a downstream
browser has a stake in -- from whatever evidence a team already has:

  * a directory of ``.patch`` files (the usual shape of a vendor fork)
  * ``git diff --name-only`` against the upstream tag, for a full source fork
  * a hand-maintained path list, for teams that track ownership in a doc
  * a scan of the vendor's own source for references to Chromium symbols

The scan deserves a note on direction.  Rather than grepping Chromium for
vendor names, we take the vocabulary of the *new snapshot* (every feature,
flag, switch and pref name Chromium declares) and look for those tokens in
vendor source.  That inverts a many-passes-over-a-huge-tree problem into one
pass over a small tree, and it finds references the patch list misses -- code
that reads a Chromium feature without patching the file that declares it.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

from . import jsonc
from .extract._cpp import PLATFORM
from .extract.base_features import feature_name_from_var
from .model import Change, Snapshot

# Source extensions worth scanning in a vendor tree.
SCAN_EXTS = (".cc", ".cpp", ".h", ".java", ".kt", ".mm", ".py", ".gn", ".gni",
             ".json", ".xml", ".ts", ".js")

SCAN_SKIP_DIRS = {".git", "out", "node_modules", "__pycache__", "build",
                  ".gradle", "third_party"}

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STRING_RE = re.compile(r"\"([^\"\n]{2,120})\"")
_PATCH_PATH_RE = re.compile(r"^\+\+\+ [ab]/(.+?)(?:\t.*)?$", re.MULTILINE)
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)


# Areas come in three kinds, and mixing them up is how a scoped report loses
# its most severe findings. Measured on M148 -> M151: defining only product
# areas left 1,802 of 2,226 findings unassigned, including every one of the ten
# highest-severity items (Mojo signature changes score 80 and belong to no
# product).
AREA_PRODUCT = "product"    # Downloads, Bookmarks, History - has an owning team
AREA_INFRA = "infra"        # Mojo, IDL, process model - cross-cutting
AREA_PLATFORM = "platform"  # flags, prefs, switches - cuts across everything
AREA_KINDS = (AREA_PRODUCT, AREA_INFRA, AREA_PLATFORM)

UNASSIGNED = "_unassigned"


@dataclass
class Area:
    """A named part of the product, with the Chromium surface it depends on.

    Matching is deliberately multi-modal. Chromium is not organized by product
    feature: "downloads" spans components/, chrome/browser/ and content/, plus
    prefs, flags and Mojo interfaces. Path and symbol matching alone reaches
    only a fraction of that, so prefs, flags and fact kinds match too.
    """

    id: str
    title: str = ""
    weight: int = 50          # 0-100; how much a change here costs us
    kind: str = AREA_PRODUCT
    paths: List[str] = field(default_factory=list)     # path prefixes
    symbols: List[str] = field(default_factory=list)   # substring match
    prefs: List[str] = field(default_factory=list)     # pref key prefixes
    flags: List[str] = field(default_factory=list)     # feature/var name prefixes
    kinds: List[str] = field(default_factory=list)     # fact kinds owned outright
    owner: str = ""
    notes: str = ""

    def matches_path(self, path: str) -> bool:
        return any(path.startswith(p.rstrip("/")) for p in self.paths) if self.paths else False

    def matches_symbol(self, token: str) -> bool:
        low = token.lower()
        return any(s.lower() in low for s in self.symbols) if self.symbols else False

    def matches_pref(self, key: str) -> bool:
        return any(key.startswith(p) for p in self.prefs) if self.prefs else False

    def matches_flag(self, name: str) -> bool:
        if not self.flags:
            return False
        bare = feature_name_from_var(name)
        return any(name.startswith(f) or bare.startswith(f.lstrip("k"))
                   for f in self.flags)

    def matches_kind(self, fact_kind: str) -> bool:
        return fact_kind in self.kinds if self.kinds else False


@dataclass
class TouchSet:
    name: str = "downstream"
    platform: str = "windows"
    modified_paths: Set[str] = field(default_factory=set)
    modified_prefixes: Set[str] = field(default_factory=set)
    symbols: Set[str] = field(default_factory=set)
    areas: List[Area] = field(default_factory=list)
    ignore_paths: List[str] = field(default_factory=list)
    provenance: Dict[str, int] = field(default_factory=dict)

    # -- matching -------------------------------------------------------

    def is_ignored(self, path: str) -> bool:
        return any(path.startswith(p.rstrip("/")) for p in self.ignore_paths)

    def match_paths(self, paths: Sequence[str]) -> List[str]:
        hits = []
        for path in paths:
            if path in self.modified_paths:
                hits.append(path)
                continue
            if any(path.startswith(prefix) for prefix in self.modified_prefixes):
                hits.append(path)
        return sorted(set(hits))

    def match_symbols(self, tokens: Iterable[str]) -> List[str]:
        return sorted({t for t in tokens if t and t in self.symbols})

    def match_areas(self, change, tokens: Iterable[str]) -> List[Area]:
        """Every area this change belongs to. May be empty -- see UNASSIGNED.

        Order of checks is cheapest first; any single match claims the area.
        """
        token_list = [t for t in tokens if t]
        out = []
        for area in self.areas:
            if area.matches_kind(change.kind):
                out.append(area)
                continue
            if any(area.matches_path(p) for p in change.paths):
                out.append(area)
                continue
            if change.kind == "pref" and area.matches_pref(change.key):
                out.append(area)
                continue
            if change.kind in ("base_feature", "feature_param", "blink_runtime_feature"):
                var = ((change.after or change.before) or {}).get("var", "")
                if area.matches_flag(change.name) or (var and area.matches_flag(var)):
                    out.append(area)
                    continue
            if any(area.matches_symbol(t) for t in token_list):
                out.append(area)
        return out

    def area_by_id(self, area_id: str) -> Optional[Area]:
        return next((a for a in self.areas if a.id == area_id), None)

    def has_evidence(self) -> bool:
        return bool(self.modified_paths or self.modified_prefixes or self.symbols)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_profile(path: str, snapshots: Optional[Sequence[Snapshot]] = None,
                 log=lambda m: None) -> TouchSet:
    """Build a TouchSet from a profile file plus whatever it points at.

    ``snapshots`` supplies the Chromium vocabulary used to tell a real symbol
    reference from ordinary C++ noise.  Pass **both** sides of the uprev: the
    old snapshot is what the fork currently compiles against, so a symbol that
    exists only there is precisely the interesting case -- something we depend
    on that upstream just deleted.  Building the vocabulary from the new
    snapshot alone filters those out, silently hiding the build breaks this
    tool exists to find.
    """
    profile = jsonc.load(path)
    base_dir = os.path.dirname(os.path.abspath(path))

    # The tool dropped its --platform option because reading the wrong platform
    # inverts conclusions rather than blurring them. The profile kept a
    # `platform` field, and it was trusted without checking -- so a profile left
    # saying "android" (which the shipped example said until recently) silently
    # disabled the not-compiled penalty entirely: platform_state carries only
    # "windows", so looking up "android" finds nothing and scores nothing down.
    # A field that can only be right one way should not be a field you can get
    # wrong quietly.
    declared = (profile.get("platform") or PLATFORM).lower()
    if declared != PLATFORM:
        raise ValueError(
            f"profile {os.path.basename(path)} declares platform "
            f"{declared!r}, but this tool only analyses {PLATFORM!r} "
            f"(a Chromium-based desktop browser on Windows). Set "
            f'platform: "{PLATFORM}" or remove the field.'
        )

    touch = TouchSet(
        name=profile.get("name", "downstream"),
        platform=PLATFORM,
        ignore_paths=list(profile.get("ignore_paths", [])),
    )

    for raw in profile.get("areas", []):
        kind = raw.get("kind", AREA_PRODUCT)
        if kind not in AREA_KINDS:
            log(f"  ! area {raw.get('id')}: unknown kind {kind!r}, "
                f"treating as {AREA_PRODUCT}")
            kind = AREA_PRODUCT
        touch.areas.append(Area(
            id=raw.get("id") or raw.get("title", "area"),
            title=raw.get("title", raw.get("id", "")),
            weight=int(raw.get("weight", 50)),
            kind=kind,
            paths=list(raw.get("paths", [])),
            symbols=list(raw.get("symbols", [])),
            prefs=list(raw.get("prefs", [])),
            flags=list(raw.get("flags", [])),
            kinds=list(raw.get("kinds", [])),
            owner=raw.get("owner", ""),
            notes=raw.get("notes", ""),
        ))

    # -- explicit path list
    explicit = list(profile.get("modified_paths", []))
    listfile = profile.get("modified_paths_file")
    if listfile:
        listfile = _resolve(base_dir, listfile)
        if os.path.exists(listfile):
            with open(listfile, encoding="utf-8") as fh:
                explicit += [ln.strip() for ln in fh
                             if ln.strip() and not ln.startswith("#")]
    _add_paths(touch, explicit, "explicit")

    # -- patch directories
    patch_symbols: Set[str] = set()
    for raw_dir in profile.get("patch_dirs", []):
        patch_dir = _resolve(base_dir, raw_dir)
        found_paths, found_symbols = paths_from_patches(patch_dir)
        _add_paths(touch, found_paths, "patches")
        patch_symbols |= found_symbols
        log(f"  patches {patch_dir}: {len(found_paths)} paths, "
            f"{len(found_symbols)} raw tokens")

    # -- git working fork
    git_cfg = profile.get("git") or {}
    if git_cfg.get("repo"):
        repo = _resolve(base_dir, git_cfg["repo"])
        upstream = git_cfg.get("upstream_ref", "")
        found = paths_from_git(repo, upstream, log=log)
        _add_paths(touch, found, "git")
        log(f"  git {repo}: {len(found)} paths")

    # -- explicit symbols
    for sym in profile.get("symbols", []):
        touch.symbols.add(sym)
    touch.provenance["symbols_explicit"] = len(touch.symbols)

    # -- symbol scan over vendor source
    roots = [_resolve(base_dir, r) for r in profile.get("source_roots", [])]
    roots = [r for r in roots if os.path.isdir(r)]

    vocab_tokens: Set[str] = set()
    vocab_strings: Set[str] = set()
    for snap in snapshots or ():
        tokens, strings = build_vocabulary(snap)
        vocab_tokens |= tokens
        vocab_strings |= strings

    # Raw patch tokens are mostly C++ noise ("bool", "base", "return").  Only
    # the ones Chromium actually declares as a feature, switch or pref are
    # evidence of a dependency.
    if patch_symbols:
        if vocab_tokens or vocab_strings:
            kept = patch_symbols & (vocab_tokens | vocab_strings)
        else:
            kept = {s for s in patch_symbols
                    if re.fullmatch(r"k[A-Z]\w+", s) or re.search(r"[-.]", s)}
        touch.symbols |= kept
        touch.provenance["symbols_from_patches"] = len(kept)
        log(f"  patch tokens matching chromium vocabulary: {len(kept)}")

    if roots and (vocab_tokens or vocab_strings):
        found = scan_sources(roots, vocab_tokens, vocab_strings, log=log)
        touch.symbols |= found
        touch.provenance["symbols_scanned"] = len(found)
        log(f"  source scan: {len(found)} chromium symbols referenced")
    elif roots:
        log("  source scan skipped (no snapshot supplied)")

    touch.provenance["paths_total"] = len(touch.modified_paths)
    touch.provenance["prefixes_total"] = len(touch.modified_prefixes)
    touch.provenance["symbols_total"] = len(touch.symbols)
    return touch


def _resolve(base_dir: str, path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(
        os.path.join(base_dir, path))


def _add_paths(touch: TouchSet, paths: Iterable[str], source: str) -> None:
    count = 0
    for raw in paths:
        path = raw.strip().lstrip("./")
        if not path:
            continue
        if path.endswith("/") or ("." not in os.path.basename(path)):
            touch.modified_prefixes.add(path.rstrip("/") + "/")
        else:
            touch.modified_paths.add(path)
        count += 1
    touch.provenance[f"paths_{source}"] = count


# ---------------------------------------------------------------------------
# Evidence sources
# ---------------------------------------------------------------------------


def paths_from_patches(patch_dir: str) -> tuple:
    """Chromium paths *and* identifiers touched by the patches in a directory.

    Paths alone are blunt evidence.  ``content_features.cc`` declares nearly
    two hundred features, so a fork that patches one default would otherwise
    look like it depends on all of them, and every feature change in the file
    would be flagged as ours.

    Reading the hunk bodies fixes that: the tokens a patch actually adds,
    removes or sits next to are specific, so a patch that flips one feature
    yields evidence for that feature rather than for the file.
    """
    paths: List[str] = []
    symbols: Set[str] = set()
    if not os.path.isdir(patch_dir):
        return [], symbols
    for dirpath, dirnames, filenames in os.walk(patch_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SCAN_SKIP_DIRS)
        for filename in filenames:
            if not filename.endswith((".patch", ".diff")):
                continue
            try:
                with open(os.path.join(dirpath, filename), encoding="utf-8",
                          errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            paths += [m for m in _PATCH_PATH_RE.findall(text) if m != "/dev/null"]
            for a, b in _DIFF_GIT_RE.findall(text):
                paths += [a, b]
            symbols |= _symbols_from_hunks(text)
    return sorted(set(paths)), symbols


def _symbols_from_hunks(patch_text: str) -> Set[str]:
    """Identifiers and string literals appearing in changed/context lines."""
    found: Set[str] = set()
    for line in patch_text.splitlines():
        if not line or line[0] not in "+- ":
            continue
        if line.startswith(("+++", "---")):
            continue
        body = line[1:]
        found |= set(_IDENT_RE.findall(body))
        found |= set(_STRING_RE.findall(body))
    return found


def paths_from_git(repo: str, upstream_ref: str, log=lambda m: None) -> List[str]:
    """``git diff --name-only <upstream_ref>`` inside a vendor fork."""
    if not os.path.isdir(os.path.join(repo, ".git")):
        log(f"  ! not a git repo: {repo}")
        return []
    cmd = ["git", "-C", repo, "diff", "--name-only"]
    if upstream_ref:
        cmd.append(upstream_ref)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"  ! git diff failed: {exc}")
        return []
    if result.returncode != 0:
        log(f"  ! git diff failed: {result.stderr.strip()[:200]}")
        return []
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


# Kinds whose *name* is a distinctive identifier, so finding it in vendor
# source is real evidence of a dependency.
_NAMED_KINDS = {"base_feature", "blink_runtime_feature", "feature_param",
                "idl_interface", "mojo_interface"}

# Type names common enough that matching them means nothing.
_TOO_GENERIC = {"Window", "Document", "Element", "Event", "Response", "Request",
                "Options", "Result", "Error", "Data", "Value", "Type", "Name",
                "Range", "Node", "Text", "Image", "Stream", "Buffer", "Config"}


def build_vocabulary(snapshot: Snapshot) -> tuple:
    """Tokens and string literals worth looking for in vendor source.

    Deliberately excludes bare IDL and Mojo *member* names.  Web IDL is full of
    members called ``before``, ``after``, ``has``, ``values`` and ``close``;
    matching those against prose in a patch comment produced a confident
    false positive ("we reference `before`") from the word "before" in an
    English sentence.  A member name only means something qualified by its
    interface, and the interface name is already in the vocabulary, so
    dropping the bare form loses no real signal.
    """
    tokens: Set[str] = set()
    strings: Set[str] = set()
    for fact in snapshot.facts:
        var = fact.attrs.get("var")
        if isinstance(var, str) and var:
            tokens.add(var)
        if fact.kind in ("switch", "pref"):
            strings.add(fact.key)
        elif fact.kind in _NAMED_KINDS:
            name = fact.name or ""
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{3,}", name):
                tokens.add(name)
        # Members contribute their owning interface, never their own name.
        iface = fact.attrs.get("interface")
        if isinstance(iface, str) and re.fullmatch(r"[A-Za-z_][\w.]{3,}", iface):
            tokens.add(iface.split(".")[-1])
    return tokens - _TOO_GENERIC, strings


def scan_sources(roots: Sequence[str], vocab_tokens: Set[str],
                 vocab_strings: Set[str], log=lambda m: None) -> Set[str]:
    """One pass over vendor source, intersecting against Chromium's vocabulary."""
    found: Set[str] = set()
    files = 0
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SCAN_SKIP_DIRS)
            for filename in filenames:
                if not filename.endswith(SCAN_EXTS):
                    continue
                try:
                    with open(os.path.join(dirpath, filename), encoding="utf-8",
                              errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                files += 1
                found |= vocab_tokens.intersection(_IDENT_RE.findall(text))
                if vocab_strings:
                    found |= vocab_strings.intersection(_STRING_RE.findall(text))
    log(f"  scanned {files} vendor source files")
    return found


# ---------------------------------------------------------------------------


def change_tokens(change: Change) -> List[str]:
    """Identifiers a downstream codebase could plausibly reference."""
    tokens = [change.name, change.key]
    for attrs in (change.before, change.after):
        if not attrs:
            continue
        for field_name in ("var", "interface", "feature", "base_feature"):
            value = attrs.get(field_name)
            if isinstance(value, str) and value:
                tokens.append(value)
                if "." in value:
                    tokens.append(value.split(".")[-1])
    if "." in change.key:
        tokens.append(change.key.split(".")[0])
    return [t for t in dict.fromkeys(tokens) if t]
