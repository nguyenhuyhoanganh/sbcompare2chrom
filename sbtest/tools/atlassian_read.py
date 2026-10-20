"""Read test cases from a Confluence page or Jira issue link into Markdown.

    set SB_ATLASSIAN_TOKEN=<personal access token>
    python -m sbtest.tools.atlassian_read https://confluence.company.com/display/QA/Add-ons+sanity
    python -m sbtest.tools.atlassian_read "https://confluence.company.com/pages/viewpage.action?pageId=123" --children
    python -m sbtest.tools.atlassian_read https://jira.company.com/browse/SIB-123
    python -m sbtest.tools.atlassian_read --jql "project = SIB AND labels = sanity-addons"

Output goes to ``testcases/_inbox/<name>.md`` (or ``--out``): the raw source converted to
Markdown, with tables kept as pipe tables, plus a header naming the source URL/version.
Attachments (screenshots in the cases) are downloaded next to it with ``--attachments``.
The inbox file is *input* for the agent, who then writes the normalized
``testcases/<feature>/*.md`` (see testcases/README.md).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sbtest.atlassian import Atlassian, parse_jira_key, storage_to_markdown
from sbtest.config import ROOT, load_config
from sbtest.utils import slug

INBOX = ROOT / "testcases" / "_inbox"


def page_markdown(at: Atlassian, page: dict, level: int = 1) -> str:
    body = (page.get("body") or {}).get("storage", {}).get("value", "")
    url = at.confluence_url + (page.get("_links") or {}).get("webui", f"/pages/viewpage.action?pageId={page['id']}")
    head = (f"{'#' * level} {page.get('title')}\n\n"
            f"<!-- source: confluence page {page['id']} v{(page.get('version') or {}).get('number')} {url} -->\n\n")
    return head + storage_to_markdown(body)


def issue_markdown(issue: dict, jira_url: str) -> str:
    f = issue.get("fields") or {}
    meta = [f"- Type: {(f.get('issuetype') or {}).get('name', '')}",
            f"- Priority: {(f.get('priority') or {}).get('name', '')}",
            f"- Status: {(f.get('status') or {}).get('name', '')}",
            f"- Labels: {', '.join(f.get('labels') or [])}",
            f"- Components: {', '.join(c.get('name', '') for c in f.get('components') or [])}"]
    att = [f"  - {a.get('filename')} ({a.get('content')})" for a in f.get("attachment") or []]
    return (f"## {issue['key']} {f.get('summary', '')}\n\n"
            f"<!-- source: jira {jira_url}/browse/{issue['key']} -->\n\n" + "\n".join(meta) + "\n\n"
            "### Description (Jira wiki markup)\n\n" + (f.get("description") or "").strip() + "\n"
            + ("\n### Attachments\n" + "\n".join(att) + "\n" if att else ""))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("url", nargs="?", help="Confluence page URL or Jira issue URL/key")
    p.add_argument("--jql", help="Jira search instead of a single issue")
    p.add_argument("--children", action="store_true", help="also read child pages (one level)")
    p.add_argument("--attachments", action="store_true", help="download attachments next to the output")
    p.add_argument("--out", help="output .md (default testcases/_inbox/<title>.md); '-' = stdout")
    args = p.parse_args(argv)
    if not args.url and not args.jql:
        p.error("give a URL or --jql")

    cfg = load_config()
    at = Atlassian.from_config(cfg)
    attachments: list[tuple[str, str]] = []  # (download url, filename)
    if args.jql:
        issues = at.jira_search(args.jql)
        name, text = f"jql_{slug(args.jql, 60)}", "\n\n".join(issue_markdown(i, at.jira_url) for i in issues)
        for i in issues:
            attachments += [(a["content"], a["filename"]) for a in (i["fields"].get("attachment") or [])]
    elif "/browse/" in args.url or (parse_jira_key(args.url) == args.url.strip()):
        issue = at.jira_issue(parse_jira_key(args.url))
        name, text = issue["key"], issue_markdown(issue, at.jira_url)
        attachments += [(a["content"], a["filename"]) for a in (issue["fields"].get("attachment") or [])]
    else:
        page = at.confluence_page_from_url(args.url)
        name, text = page["title"], page_markdown(at, page)
        pages = [page]
        if args.children:
            for child in at.child_pages(page["id"]):
                text += "\n\n" + page_markdown(at, child, level=2)
                pages.append(child)
        if args.attachments:
            for pg in pages:
                attachments += [(a["_links"]["download"], a["title"]) for a in at.attachments(pg["id"])]

    if args.out == "-":
        sys.stdout.write(text)
        return 0
    out = Path(args.out) if args.out else INBOX / f"{slug(name, 80)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Written {out}")
    if args.attachments and attachments:
        folder = out.with_suffix("")
        for url, fname in attachments:
            at.download(url, folder / fname)
        print(f"{len(attachments)} attachment(s) in {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
