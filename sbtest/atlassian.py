"""Minimal Confluence + Jira Server/Data Center REST client (Personal Access Token).

    at = Atlassian.from_config(cfg)            # token from env var atlassian.token_env
    page = at.confluence_page_from_url("https://confluence.company.com/display/QA/Add-ons+sanity")
    md = storage_to_markdown(page["body"]["storage"]["value"])
    issue = at.jira_issue("SIB-123")
    new = at.create_page("QA", "Run 2026-10-20", "<p>..</p>", parent_id="123456")
    at.attach(new["id"], Path("page.png"), name="BM-001_page.png")

Only the standard library is used, so corporate machines need nothing extra. HTTP(S)
proxy env vars and NO_PROXY are honoured; ``verify_ssl`` may point at the company CA file.
"""
from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import ssl
import uuid
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, unquote_plus, urlencode, urlparse
from urllib.request import Request, build_opener, HTTPSHandler

from sbtest.utils import log


class AtlassianError(RuntimeError):
    pass


class Atlassian:
    def __init__(self, confluence_url: str = "", jira_url: str = "", token: str = "", verify_ssl=True) -> None:
        self.confluence_url = confluence_url.rstrip("/")
        self.jira_url = jira_url.rstrip("/")
        self.token = token
        ctx = None
        if verify_ssl is False:
            ctx = ssl._create_unverified_context()  # noqa: S323 - explicit opt-out in config
        elif isinstance(verify_ssl, str) and verify_ssl:
            ctx = ssl.create_default_context(cafile=verify_ssl)
        self._opener = build_opener(HTTPSHandler(context=ctx)) if ctx else build_opener()

    @classmethod
    def from_config(cls, cfg) -> "Atlassian":
        env = cfg.get("atlassian.token_env") or "SB_ATLASSIAN_TOKEN"
        token = os.environ.get(env, "")
        if not token:
            raise AtlassianError(f"Set the Personal Access Token in environment variable {env}")
        return cls(cfg.get("atlassian.confluence_url") or "", cfg.get("atlassian.jira_url") or "", token,
                   cfg.get("atlassian.verify_ssl", True))

    # -- http --------------------------------------------------------------------
    def request(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None,
                raw: bool = False):
        h = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        h.update(headers or {})
        req = Request(url, data=body, method=method, headers=h)
        try:
            with self._opener.open(req, timeout=60) as r:
                data = r.read()
                return data if raw else (json.loads(data.decode("utf-8")) if data else {})
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise AtlassianError(f"{method} {url} -> HTTP {e.code}: {detail}") from e

    def _json(self, method: str, url: str, payload: dict) -> dict:
        return self.request(method, url, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})

    # -- Confluence --------------------------------------------------------------
    PAGE_EXPAND = "body.storage,version,space,ancestors"

    def confluence_page(self, page_id: str, expand: str = PAGE_EXPAND) -> dict:
        return self.request("GET", f"{self.confluence_url}/rest/api/content/{page_id}?expand={expand}")

    def confluence_page_by_title(self, space: str, title: str, expand: str = PAGE_EXPAND) -> dict:
        q = urlencode({"spaceKey": space, "title": title, "expand": expand})
        res = self.request("GET", f"{self.confluence_url}/rest/api/content?{q}").get("results", [])
        if not res:
            raise AtlassianError(f"No Confluence page {title!r} in space {space}")
        return res[0]

    def confluence_page_from_url(self, url: str) -> dict:
        """Accepts viewpage.action?pageId=, /display/SPACE/Title, /spaces/SPACE/pages/ID/..., /x/<tiny>."""
        kind, a, b = parse_confluence_url(url)
        if kind == "tiny":  # short link: follow the redirect to the real page URL
            req = Request(url, method="HEAD", headers={"Authorization": f"Bearer {self.token}"})
            with self._opener.open(req, timeout=60) as r:
                return self.confluence_page_from_url(r.geturl())
        if kind == "id":
            return self.confluence_page(a)
        return self.confluence_page_by_title(a, b)

    def child_pages(self, page_id: str) -> list[dict]:
        return self.request("GET", f"{self.confluence_url}/rest/api/content/{page_id}/child/page?limit=500"
                                   f"&expand={self.PAGE_EXPAND}").get("results", [])

    def attachments(self, page_id: str) -> list[dict]:
        return self.request("GET", f"{self.confluence_url}/rest/api/content/{page_id}/child/attachment?limit=500"
                            ).get("results", [])

    def download(self, rel_or_abs_url: str, target: Path) -> Path:
        url = rel_or_abs_url if "://" in rel_or_abs_url else self.confluence_url + rel_or_abs_url
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.request("GET", url, raw=True))
        return target

    def create_page(self, space: str, title: str, storage_html: str, parent_id: str = "") -> dict:
        payload = {"type": "page", "title": title, "space": {"key": space},
                   "body": {"storage": {"value": storage_html, "representation": "storage"}}}
        if parent_id:
            payload["ancestors"] = [{"id": str(parent_id)}]
        return self._json("POST", f"{self.confluence_url}/rest/api/content", payload)

    def update_page(self, page_id: str, title: str, storage_html: str, version: int) -> dict:
        payload = {"type": "page", "title": title, "version": {"number": version + 1},
                   "body": {"storage": {"value": storage_html, "representation": "storage"}}}
        return self._json("PUT", f"{self.confluence_url}/rest/api/content/{page_id}", payload)

    def attach(self, page_id: str, file: Path, name: str | None = None, comment: str = "") -> dict:
        name = name or file.name
        boundary = uuid.uuid4().hex
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode() + file.read_bytes() + b"\r\n",
            f'--{boundary}\r\nContent-Disposition: form-data; name="minorEdit"\r\n\r\ntrue\r\n'.encode(),
        ]
        if comment:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="comment"\r\n\r\n{comment}\r\n'.encode())
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        return self.request("POST", f"{self.confluence_url}/rest/api/content/{page_id}/child/attachment", body,
                            {"Content-Type": f"multipart/form-data; boundary={boundary}",
                             "X-Atlassian-Token": "no-check"})

    # -- Jira --------------------------------------------------------------------
    ISSUE_FIELDS = "summary,description,issuetype,priority,labels,components,status,attachment,subtasks,issuelinks"

    def jira_issue(self, key: str, fields: str = ISSUE_FIELDS) -> dict:
        return self.request("GET", f"{self.jira_url}/rest/api/2/issue/{quote(key)}?fields={fields}")

    def jira_search(self, jql: str, fields: str = ISSUE_FIELDS, limit: int = 200) -> list[dict]:
        q = urlencode({"jql": jql, "fields": fields, "maxResults": limit})
        return self.request("GET", f"{self.jira_url}/rest/api/2/search?{q}").get("issues", [])


def parse_confluence_url(url: str) -> tuple[str, str, str]:
    """-> ("id", page_id, "") | ("title", space, title) | ("tiny", url, "")"""
    u = urlparse(url)
    qs = parse_qs(u.query)
    if "pageId" in qs:
        return "id", qs["pageId"][0], ""
    m = re.search(r"/pages/(\d+)(?:/|$)", u.path)
    if m:
        return "id", m.group(1), ""
    m = re.search(r"/display/([^/]+)/([^/?#]+)", u.path)
    if m:
        return "title", m.group(1), unquote_plus(m.group(2))
    if re.search(r"/x/[^/]+$", u.path):
        return "tiny", url, ""
    raise AtlassianError(f"Unrecognised Confluence URL: {url}")


def parse_jira_key(text: str) -> str | None:
    m = re.search(r"\b([A-Z][A-Z0-9_]+-\d+)\b", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- storage -> markdown
class _MdConverter(HTMLParser):
    """Confluence storage format (XHTML + ac:/ri: macros) -> readable Markdown.

    Keeps what test cases need: headings, lists (numbered steps), tables, code, panels,
    status lozenges, links and image references.
    """

    BLOCK = {"p", "div", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.lists: list[list] = []          # stack of [kind, counter]
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.in_pre = False
        self.macro: list[str] = []
        self.param: str | None = None
        self.link_href: str | None = None

    # writing goes to the current table cell when inside one
    def w(self, text: str) -> None:
        (self.cell if self.cell is not None else self.out).append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.w("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self.w("\n\n" if self.cell is None else " ")
        elif tag == "br":
            self.w("\n" if self.cell is None else "<br>")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
        elif tag == "li":
            if self.lists:
                self.lists[-1][1] += 1
                kind, n = self.lists[-1]
                indent = "  " * (len(self.lists) - 1)
                bullet = f"{n}." if kind == "ol" else "-"
                self.w(("\n" if self.cell is None else " ") + f"{indent}{bullet} ")
        elif tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("_")
        elif tag == "code" and not self.in_pre:
            self.w("`")
        elif tag == "pre":
            self.in_pre = True
            self.w("\n```\n")
        elif tag == "a":
            self.link_href = a.get("href")
        elif tag == "ac:structured-macro":
            name = a.get("ac:name", "")
            self.macro.append(name)
            if name == "code":
                self.w("\n```\n")
            elif name in ("info", "note", "warning", "tip", "panel", "expand"):
                self.w(f"\n\n> [{name}] ")
        elif tag == "ac:parameter":
            self.param = a.get("ac:name")
        elif tag == "ri:attachment":
            self.w(f"[attachment: {a.get('ri:filename', '')}]")
        elif tag == "ri:page":
            self.w(f"[page: {a.get('ri:content-title', '')}]")
        elif tag == "ri:url":
            self.w(f"[{a.get('ri:value', '')}]")
        elif tag == "ac:task":
            self.w("\n- [ ] ")
        elif tag == "time":
            self.w(a.get("datetime", ""))

    def handle_endtag(self, tag):
        if tag in ("ul", "ol") and self.lists:
            self.lists.pop()
            if not self.lists and self.cell is None:
                self.w("\n")
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self._flush_table()
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("_")
        elif tag == "code" and not self.in_pre:
            self.w("`")
        elif tag == "pre":
            self.in_pre = False
            self.w("\n```\n")
        elif tag == "a":
            if self.link_href and not self.link_href.startswith("#"):
                self.w(f" ({self.link_href})")
            self.link_href = None
        elif tag == "ac:structured-macro" and self.macro:
            name = self.macro.pop()
            if name == "code":
                self.w("\n```\n")
        elif tag == "ac:parameter":
            self.param = None

    def handle_data(self, data):
        if self.param is not None:
            if self.macro and self.macro[-1] == "status" and self.param == "title":
                self.w(f"[{data}]")
            elif self.param == "title" and self.macro and self.macro[-1] in ("expand", "panel"):
                self.w(f"**{data}** ")
            return
        if self.in_pre or (self.macro and self.macro[-1] == "code"):
            self.w(data)
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip() or (self.out and not self.out[-1].endswith(("\n", " "))):
            self.w(text)

    def _flush_table(self):
        rows = [r for r in self.table if any(c for c in r)]
        self.table = None
        if not rows:
            return
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        self.out.append("\n\n" + "\n".join(lines) + "\n")

    def result(self) -> str:
        text = "".join(self.out)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def storage_to_markdown(storage: str) -> str:
    conv = _MdConverter()
    conv.feed(storage)
    conv.close()
    return conv.result()


def esc(text) -> str:
    """Escape text for Confluence storage XHTML."""
    return html.escape(str(text or ""), quote=True)


def log_page(page: dict) -> None:
    log.info("Confluence page %s %r (space %s, v%s)", page.get("id"), page.get("title"),
             (page.get("space") or {}).get("key"), (page.get("version") or {}).get("number"))
