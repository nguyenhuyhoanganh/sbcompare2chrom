"""Load per-feature test data from ``test_data/<feature>.yaml``.

String values may contain ``{site}`` which is replaced by the local test site base URL
when ``site`` is given, e.g. ``url: "{site}/page?title=Docs"``.
"""
from __future__ import annotations

from typing import Any

import yaml

from sbtest.config import ROOT


def format_data(value: Any, mapping: dict) -> Any:
    if isinstance(value, str):
        for k, v in mapping.items():
            value = value.replace("{" + k + "}", v)
        return value
    if isinstance(value, list):
        return [format_data(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: format_data(v, mapping) for k, v in value.items()}
    return value


def load_data(feature: str, site=None, data_dir=None) -> dict:
    path = (data_dir or ROOT / "test_data") / f"{feature}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return format_data(data, {"site": site.base}) if site is not None else data
