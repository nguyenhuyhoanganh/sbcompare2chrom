"""Getting Chromium source for a given ref, without a full checkout.

A `fetch chromium && gclient sync` per milestone is ~100 GB and hours of wall
clock.  We only need a few thousand declaration files, so instead we pull
per-directory tarballs straight from Gitiles:

    https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<tag>/<dir>.tar.gz

Measured on M143 the whole target set is roughly 35-40 MB per version, which
makes a two-version comparison a couple of minutes on a cold cache and
instant on a warm one.

If a team *does* have a checkout (or a Samsung internal mirror), `LocalSource`
reads from disk instead and the rest of the pipeline is unchanged.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import ssl
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

USER_AGENT = "chromedrift/0.1 (+chromium uprev impact analysis)"
GITILES_BASE = "https://chromium.googlesource.com/chromium/src"
CHROMIUMDASH = "https://chromiumdash.appspot.com"

DEFAULT_TIMEOUT = 180
DEFAULT_RETRIES = 4


class AcquireError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
              accept_404: bool = False) -> Optional[bytes]:
    """GET with retry/backoff.

    Gitiles rate-limits and occasionally closes connections mid-body; bare
    curl returned a zero-length file for a URL that had just worked.  Every
    fetch therefore retries with backoff and validates that it got a body.
    Returns None for 404 when ``accept_404`` (a target simply may not exist in
    an older milestone -- that is data, not an error).
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not data:
                raise AcquireError("empty response body")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                if accept_404:
                    return None
                raise AcquireError(f"404 {url}") from exc
            last_err = exc
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError,
                AcquireError) as exc:
            last_err = exc
        if attempt < retries - 1:
            time.sleep(1.5 * (2 ** attempt))
    raise AcquireError(f"GET failed after {retries} attempts: {url} ({last_err})")


# ---------------------------------------------------------------------------
# Ref resolution
# ---------------------------------------------------------------------------

_MILESTONE_RE = re.compile(r"^\d{2,3}$")
_FULL_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def resolve_ref(ref: str, platform: str = "Android", timeout: int = 60) -> Tuple[str, Optional[int]]:
    """Turn a user-supplied ref into a concrete git ref plus milestone.

    Accepts a bare milestone ("143"), a full version ("143.0.7499.40"), or any
    raw git ref (branch, tag, sha) which is passed through untouched.  Bare
    milestones resolve against the *stable* release for the requested platform,
    which is what a downstream browser actually rebases onto.
    """
    ref = ref.strip()
    if _FULL_VERSION_RE.match(ref):
        return f"refs/tags/{ref}", int(ref.split(".")[0])
    if _MILESTONE_RE.match(ref):
        milestone = int(ref)
        version = _latest_stable_version(milestone, platform, timeout)
        if not version:
            raise AcquireError(
                f"could not resolve milestone {milestone} for platform {platform}; "
                f"pass an explicit version like {milestone}.0.xxxx.yy"
            )
        return f"refs/tags/{version}", milestone
    return ref, _milestone_from_ref(ref)


def _milestone_from_ref(ref: str) -> Optional[int]:
    m = re.search(r"(\d{2,3})\.\d+\.\d+\.\d+", ref)
    return int(m.group(1)) if m else None


def _latest_stable_version(milestone: int, platform: str, timeout: int) -> Optional[str]:
    """Highest stable release for a milestone, via chromiumdash."""
    for plat in (platform, "Android", "Windows"):
        url = (f"{CHROMIUMDASH}/fetch_releases?channel=Stable"
               f"&platform={urllib.parse.quote(plat)}&milestone={milestone}&num=25")
        try:
            raw = _http_get(url, timeout=timeout, retries=2)
        except AcquireError:
            continue
        if not raw:
            continue
        try:
            releases = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        versions = [r.get("version") for r in releases if r.get("version")]
        versions = [v for v in versions if _FULL_VERSION_RE.match(v)]
        if versions:
            return max(versions, key=_version_key)
    return None


def _version_key(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def milestone_info(milestone: int, timeout: int = 60) -> dict:
    """Branch/owner metadata for a milestone (best effort, never fatal)."""
    try:
        raw = _http_get(f"{CHROMIUMDASH}/fetch_milestones?mstone={milestone}",
                        timeout=timeout, retries=2)
        data = json.loads(raw.decode("utf-8", "replace"))
        return data[0] if isinstance(data, list) and data else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


class Source:
    """Provides Chromium files for a single ref into a local directory."""

    ref: str

    def materialize(self, targets: Iterable["FetchTarget"], root: str) -> Dict[str, str]:
        raise NotImplementedError


class GitilesSource(Source):
    def __init__(self, ref: str, cache_dir: str, base: str = GITILES_BASE,
                 timeout: int = DEFAULT_TIMEOUT, refresh: bool = False,
                 log=lambda m: None):
        self.ref = ref
        self.base = base.rstrip("/")
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.refresh = refresh
        self.log = log

    # -- low level ------------------------------------------------------

    def _quoted_ref(self) -> str:
        return urllib.parse.quote(self.ref, safe="/")

    def fetch_file(self, path: str) -> Optional[bytes]:
        url = f"{self.base}/+/{self._quoted_ref()}/{path}?format=TEXT"
        raw = _http_get(url, timeout=self.timeout, accept_404=True)
        if raw is None:
            return None
        try:
            return base64.b64decode(raw)
        except Exception as exc:  # pragma: no cover - malformed server reply
            raise AcquireError(f"bad base64 for {path}: {exc}") from exc

    def fetch_archive(self, directory: str) -> Optional[bytes]:
        d = directory.strip("/")
        url = f"{self.base}/+archive/{self._quoted_ref()}/{d}.tar.gz"
        return _http_get(url, timeout=self.timeout, accept_404=True)

    def list_tree(self, directory: str) -> List[dict]:
        d = directory.strip("/")
        url = f"{self.base}/+/{self._quoted_ref()}/{d}/?format=JSON"
        raw = _http_get(url, timeout=self.timeout, accept_404=True)
        if raw is None:
            return []
        text = raw.decode("utf-8", "replace")
        # Gitiles prefixes JSON responses with an anti-XSSI guard line.
        if text.startswith(")]}"):
            text = text.split("\n", 1)[1] if "\n" in text else "{}"
        try:
            return json.loads(text).get("entries", [])
        except json.JSONDecodeError:
            return []

    # -- public ---------------------------------------------------------

    def materialize(self, targets: Iterable["FetchTarget"], root: str) -> Dict[str, str]:
        """Populate ``root`` so it looks like a (very partial) src/ checkout."""
        stats: Dict[str, str] = {}
        for target in targets:
            dest = os.path.join(root, target.path.replace("/", os.sep))
            marker = os.path.join(root, ".chromedrift", _safe_name(target.path) + ".ok")
            if os.path.exists(marker) and not self.refresh:
                stats[target.path] = "cached"
                continue
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            if target.kind == "file":
                data = self.fetch_file(target.path)
                if data is None:
                    stats[target.path] = "missing"
                    _touch(marker)
                    continue
                os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(data)
                stats[target.path] = f"file {len(data)}B"
            else:
                blob = self.fetch_archive(target.path)
                if blob is None:
                    stats[target.path] = "missing"
                    _touch(marker)
                    continue
                n = _extract_tar_gz(blob, dest, include=target.include)
                stats[target.path] = f"tree {n} files, {len(blob)}B"
            _touch(marker)
            self.log(f"    {target.path}: {stats[target.path]}")
        return stats


class LocalSource(Source):
    """Read from an existing Chromium checkout (or internal mirror)."""

    def __init__(self, ref: str, src_root: str, log=lambda m: None):
        self.ref = ref
        self.src_root = os.path.abspath(src_root)
        self.log = log
        if not os.path.isdir(self.src_root):
            raise AcquireError(f"not a directory: {self.src_root}")

    def materialize(self, targets: Iterable["FetchTarget"], root: str) -> Dict[str, str]:
        stats: Dict[str, str] = {}
        for target in targets:
            src = os.path.join(self.src_root, target.path.replace("/", os.sep))
            dest = os.path.join(root, target.path.replace("/", os.sep))
            if not os.path.exists(src):
                stats[target.path] = "missing"
                continue
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
                shutil.copyfile(src, dest)
                stats[target.path] = "file"
            else:
                n = _copy_tree(src, dest, include=target.include)
                stats[target.path] = f"tree {n} files"
        return stats


# ---------------------------------------------------------------------------
# Fetch targets
# ---------------------------------------------------------------------------


class FetchTarget:
    """One thing to pull: a single file, or a directory filtered by suffix."""

    __slots__ = ("path", "kind", "include", "note")

    def __init__(self, path: str, kind: str = "file",
                 include: Optional[Tuple[str, ...]] = None, note: str = ""):
        if kind not in ("file", "tree"):
            raise ValueError(f"bad target kind: {kind}")
        self.path = path.strip("/")
        self.kind = kind
        self.include = include
        self.note = note

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<FetchTarget {self.kind} {self.path}>"


# ---------------------------------------------------------------------------
# Archive / filesystem helpers
# ---------------------------------------------------------------------------


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("ok\n")


def _safe_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", path)


def _match_include(name: str, include: Optional[Tuple[str, ...]]) -> bool:
    if not include:
        return True
    return any(name.endswith(suffix) for suffix in include)


def _extract_tar_gz(blob: bytes, dest: str, include: Optional[Tuple[str, ...]] = None) -> int:
    """Extract a Gitiles subtree tarball, filtered by filename suffix.

    Gitiles archives contain paths relative to the requested directory and no
    leading component.  We still guard against traversal: a malicious or
    corrupt archive must not be able to write outside ``dest``.
    """
    os.makedirs(dest, exist_ok=True)
    dest_abs = os.path.abspath(dest)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            if not _match_include(os.path.basename(member.name), include):
                continue
            out_path = os.path.abspath(os.path.join(dest_abs, member.name))
            if not out_path.startswith(dest_abs + os.sep):
                continue  # path traversal attempt
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with open(out_path, "wb") as fh:
                shutil.copyfileobj(extracted, fh)
            count += 1
    return count


def _copy_tree(src: str, dest: str, include: Optional[Tuple[str, ...]] = None) -> int:
    count = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in (".git", "out", "__pycache__")]
        for fn in filenames:
            if not _match_include(fn, include):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), src)
            out_path = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            shutil.copyfile(os.path.join(dirpath, fn), out_path)
            count += 1
    return count
