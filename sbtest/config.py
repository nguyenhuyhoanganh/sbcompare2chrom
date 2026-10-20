"""Configuration loading.

Layers (later wins): default.yaml < targets/<target>.yaml < local.yaml < local.yaml
``targets.<target>`` section < SB_* env vars < CLI overrides. The target (samsung | chrome)
comes from the CLI, SB_TARGET, local.yaml or default.yaml, in that order.
"""
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
    "SB_TARGET": "target",
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

    @property
    def target(self) -> str:
        return self.get("target", "samsung")

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


def _read(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def load_config(overrides: dict | None = None, config_dir: Path = CONFIG_DIR) -> Config:
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    default, local = _read(config_dir / "default.yaml"), _read(config_dir / "local.yaml")
    target = overrides.get("target") or os.environ.get("SB_TARGET") or local.get("target") \
        or default.get("target") or "samsung"
    target_file = config_dir / "targets" / f"{target}.yaml"
    if (config_dir / "targets").exists() and not target_file.exists():
        known = sorted(p.stem for p in (config_dir / "targets").glob("*.yaml"))
        raise ValueError(f"Unknown target {target!r}; known: {known}")
    data = deep_merge(default, _read(target_file))
    data = deep_merge(data, {k: v for k, v in local.items() if k != "targets"})
    data = deep_merge(data, (local.get("targets") or {}).get(target) or {})
    for env, key in ENV_MAP.items():
        if os.environ.get(env):
            set_dotted(data, key, _coerce(os.environ[env]))
    for key, value in overrides.items():
        set_dotted(data, key, value)
    data["target"] = target
    return Config(data)
