"""Configuration loading: default.yaml < local.yaml < SB_* env vars < CLI overrides."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

# env var -> dotted config key
ENV_MAP = {
    "SB_EXE": "browser.exe",
    "SB_DRIVER": "browser.chromedriver",
    "SB_MODE": "browser.mode",
    "SB_CHROMIUM_VERSION": "browser.chromium_version",
    "SB_HEADLESS": "browser.headless",
    "SB_SCOPE": "browser.scope",
    "SB_ARTIFACTS": "paths.artifacts",
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _coerce(value: str) -> Any:
    low = value.strip().lower()
    if low in ("1", "true", "yes", "on"):
        return True
    if low in ("0", "false", "no", "off"):
        return False
    return value


def set_dotted(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


class Config:
    """Read-only view over the merged settings dict.

    Access with ``cfg.get("browser.exe")`` or attribute style ``cfg.browser["exe"]``.
    """

    def __init__(self, data: dict):
        self.data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.data
        for k in dotted.split("."):
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def __getattr__(self, item: str) -> Any:
        try:
            return self.data[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def path(self, dotted: str) -> Path:
        """A configured path, resolved against the repo root when relative."""
        p = Path(str(self.get(dotted)))
        return p if p.is_absolute() else ROOT / p

    def page_url(self, name: str) -> str:
        """URL of an internal page by logical name, e.g. ``page_url("bookmarks")``."""
        pages = self.get("pages", {})
        scheme = pages.get("scheme", "chrome")
        path = pages.get(name, name)
        if "://" in path:
            return path
        return f"{scheme}://{path}"

    @property
    def is_windows(self) -> bool:
        return os.name == "nt"

    @property
    def native_enabled(self) -> bool:
        return bool(self.get("native.enabled")) and self.is_windows and not self.get("browser.headless")


def load_config(overrides: dict | None = None, config_dir: Path = CONFIG_DIR) -> Config:
    data: dict = {}
    for name in ("default.yaml", "local.yaml"):
        f = config_dir / name
        if f.exists():
            data = deep_merge(data, yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    for env, key in ENV_MAP.items():
        if os.environ.get(env):
            set_dotted(data, key, _coerce(os.environ[env]))
    for key, value in (overrides or {}).items():
        if value is not None:
            set_dotted(data, key, value)
    return Config(data)
