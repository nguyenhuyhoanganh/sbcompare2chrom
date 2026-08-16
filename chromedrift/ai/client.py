"""LLM client for an internal, self-hosted model.

Built against ``urllib`` with no SDK dependency, because the deployment target
is a corporate network where adding a package is a procurement conversation.
Three backends are supported:

  * ``openai``    - any OpenAI-compatible ``/chat/completions`` endpoint, which
                    is what vLLM, TGI, Ollama and most internal gateways speak
  * ``anthropic`` - the Messages API
  * ``echo``      - no network at all; returns a deterministic stub so the
                    whole pipeline can be developed, tested and demoed offline

Responses are cached on disk keyed by model plus prompt hash.  Re-running a
report after tweaking the template costs nothing, which is what makes the AI
stage safe to iterate on.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .. import jsonc


@dataclass
class LLMConfig:
    provider: str = "echo"
    base_url: str = ""
    model: str = "internal"
    api_key_env: str = "CHROMEDRIFT_LLM_KEY"
    api_key: str = ""
    context_window: int = 200_000
    max_output_tokens: int = 8_000
    reserve_tokens: int = 4_000
    temperature: float = 0.1
    timeout: int = 300
    retries: int = 3
    max_requests: int = 40
    extra_headers: Dict[str, str] = field(default_factory=dict)
    extra_body: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[str]) -> "LLMConfig":
        if not path:
            return cls()
        raw = jsonc.load(path)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def resolved_key(self) -> str:
        return self.api_key or os.environ.get(self.api_key_env, "")


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig, cache_dir: str = "",
                 log=lambda m: None):
        self.config = config
        self.cache_dir = os.path.join(cache_dir, "ai") if cache_dir else ""
        self.log = log
        self.requests_made = 0
        self.cache_hits = 0
        self.tokens_in = 0
        self.tokens_out = 0

    # -- cache ----------------------------------------------------------

    def _cache_path(self, system: str, user: str) -> str:
        digest = hashlib.sha256(
            f"{self.config.provider}\0{self.config.model}\0{self.config.temperature}"
            f"\0{system}\0{user}".encode("utf-8")
        ).hexdigest()[:32]
        return os.path.join(self.cache_dir, f"{digest}.json")

    def _read_cache(self, path: str) -> Optional[str]:
        if not self.cache_dir or not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh).get("content")
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, path: str, content: str) -> None:
        if not self.cache_dir:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"model": self.config.model, "content": content}, fh)
        except OSError:
            pass

    # -- completion -----------------------------------------------------

    def complete(self, system: str, user: str) -> str:
        cache_path = self._cache_path(system, user)
        cached = self._read_cache(cache_path)
        if cached is not None:
            self.cache_hits += 1
            return cached

        if self.requests_made >= self.config.max_requests:
            raise LLMError(
                f"request cap reached ({self.config.max_requests}); raise "
                f"max_requests or narrow the analysis with --top")

        provider = self.config.provider.lower()
        if provider == "echo":
            content = _echo_response(user)
        elif provider == "anthropic":
            content = self._complete_anthropic(system, user)
        else:
            content = self._complete_openai(system, user)

        self.requests_made += 1
        self._write_cache(cache_path, content)
        return content

    def _post(self, url: str, payload: dict, headers: Dict[str, str]) -> dict:
        body = json.dumps(payload).encode("utf-8")
        last: Optional[Exception] = None
        for attempt in range(self.config.retries):
            try:
                req = urllib.request.Request(url, data=body, headers=headers,
                                             method="POST")
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:400]
                last = LLMError(f"HTTP {exc.code}: {detail}")
                if exc.code in (400, 401, 403, 404):
                    raise last  # not retryable
            except Exception as exc:
                last = exc
            if attempt < self.config.retries - 1:
                time.sleep(2 * (2 ** attempt))
        raise LLMError(f"LLM request failed: {last}")

    def _complete_openai(self, system: str, user: str) -> str:
        if not self.config.base_url:
            raise LLMError("llm config needs base_url for the openai provider")
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = self.config.resolved_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        headers.update(self.config.extra_headers)
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }
        payload.update(self.config.extra_body)
        data = self._post(url, payload, headers)
        self._track_usage(data.get("usage") or {}, "prompt_tokens", "completion_tokens")
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {str(data)[:300]}") from exc

    def _complete_anthropic(self, system: str, user: str) -> str:
        base = self.config.base_url or "https://api.anthropic.com/v1"
        url = base.rstrip("/") + "/messages"
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        key = self.config.resolved_key()
        if key:
            headers["x-api-key"] = key
        headers.update(self.config.extra_headers)
        payload = {
            "model": self.config.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }
        payload.update(self.config.extra_body)
        data = self._post(url, payload, headers)
        self._track_usage(data.get("usage") or {}, "input_tokens", "output_tokens")
        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict))

    def _track_usage(self, usage: dict, in_key: str, out_key: str) -> None:
        self.tokens_in += int(usage.get(in_key) or 0)
        self.tokens_out += int(usage.get(out_key) or 0)

    def stats(self) -> Dict[str, int]:
        return {
            "requests": self.requests_made,
            "cache_hits": self.cache_hits,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


def _echo_response(user: str) -> str:
    """Offline stub: valid, obviously-synthetic output.

    It must parse like a real response so the downstream code path is
    exercised, and it must be unmistakably a stub so a stub run is never
    mistaken for an analysed one.
    """
    ids: List[str] = []
    for line in user.splitlines():
        if line.startswith("### "):
            ids.append(line[4:].strip())
    items = [
        {
            "id": cid,
            "verdict": "needs_review",
            "rationale": "Offline stub response (provider=echo); no model was called.",
            "action": "Configure an LLM endpoint to get a real assessment.",
            "effort": "unknown",
            "risk": "unknown",
            "test_hint": "",
        }
        for cid in ids
    ]
    return json.dumps({"assessments": items}, indent=1)


# ---------------------------------------------------------------------------


def parse_json_response(text: str) -> Optional[dict]:
    """Parse a model response that should be JSON, tolerating the usual noise.

    Models wrap JSON in prose or code fences often enough that a strict parse
    throws away otherwise-good work, so this peels fences and falls back to the
    outermost brace-balanced span before giving up.
    """
    if not text:
        return None
    stripped = text.strip()

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()

    for candidate in (stripped, _outermost_object(stripped)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                parsed = jsonc.loads(candidate)
            except Exception:
                continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"assessments": parsed}
    return None


def _outermost_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""
