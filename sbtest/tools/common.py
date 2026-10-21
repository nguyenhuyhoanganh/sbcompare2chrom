"""Shared CLI plumbing for the exploration tools."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from sbtest.browser.session import BrowserSession
from sbtest.config import load_config
from sbtest.data.loader import format_data
from sbtest.server import LocalSite


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--exe", help="browser exe (default: config/env SB_EXE)")
    p.add_argument("--driver", help="chromedriver path")
    p.add_argument("--headless", action="store_true", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def make_config(args):
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    return load_config({"browser.exe": args.exe, "browser.chromedriver": args.driver,
                        "browser.headless": args.headless})


def start(args, name: str = "tool", extensions=None, bookmarks_spec: str | None = None
          ) -> tuple[BrowserSession, LocalSite]:
    """Start local site + browser. ``bookmarks_spec`` = ``file.yaml:key`` seeds the profile."""
    cfg = make_config(args)
    site = LocalSite(cfg.path("paths.site"), cfg.get("server.host"), cfg.get("server.port")).start()
    session = BrowserSession(cfg, name=name, extensions=extensions)
    if bookmarks_spec:
        file, _, key = bookmarks_spec.partition(":")
        data = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
        session.profile.bookmarks(format_data(data[key] if key else data, {"site": site.base}))
    session.start()
    return session, site


def resolve_url(cfg, site: LocalSite, url: str) -> str:
    """``bookmarks`` -> chrome://bookmarks, ``/form.html`` -> local site, else as is."""
    if "://" in url or url.startswith("about:") or url.startswith("data:"):
        return url
    if url.startswith("/"):
        return site.url(url)
    if url in (cfg.get("pages") or {}):
        return cfg.page_url(url)
    return url
