"""Context budgeting for the analysis stage.

A four-milestone Chromium diff is far larger than any context window: the
M139->M143 run produces hundreds of changes from three files alone, and
thousands from the full target set.  Feeding raw diffs to a model is not an
option, and truncating arbitrarily silently drops the findings that mattered.

The approach here is to make the deterministic stages do the hard part.  By
the time anything reaches the model it has already been normalized, scored and
explained, so a "change record" is a few hundred tokens instead of a few
thousand lines.  This module then:

  * groups records by owned area, so a batch is coherent and the model sees
    related changes together rather than an alphabetical slice
  * packs each batch against a real budget derived from the model's window
  * never splits a record across batches

With a 200k window and ~4k reserved for instructions plus ~8k for output, one
batch comfortably holds well over a hundred change records, so a typical uprev
is a handful of requests rather than hundreds.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Sequence, TypeVar

T = TypeVar("T")

# Mixed English prose and code identifiers land near 3.5 characters per token
# for the common BPE vocabularies.  Deliberately conservative: overestimating
# costs an extra request, underestimating costs a truncated one.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate."""
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN) + 1


try:  # pragma: no cover - only when the optional dep is present
    import tiktoken as _tiktoken

    _ENC = _tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(text: str) -> int:  # type: ignore[no-redef]  # noqa: F811
        """Exact count when tiktoken is available, estimate otherwise."""
        if not text:
            return 0
        return len(_ENC.encode(text, disallowed_special=()))
except Exception:  # pragma: no cover - the normal path in a locked-down env
    pass


class Budget:
    """Token accounting for one model configuration."""

    def __init__(self, context_window: int = 200_000, max_output_tokens: int = 8_000,
                 reserve_tokens: int = 4_000, safety_ratio: float = 0.90):
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens
        self.reserve_tokens = reserve_tokens
        self.safety_ratio = safety_ratio

    def input_budget(self, fixed_overhead: int = 0) -> int:
        """Tokens available for variable content in a single request."""
        usable = int(self.context_window * self.safety_ratio)
        available = usable - self.max_output_tokens - self.reserve_tokens - fixed_overhead
        return max(1_000, available)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (f"<Budget window={self.context_window} out={self.max_output_tokens} "
                f"input={self.input_budget()}>")


def pack(items: Sequence[T], render: Callable[[T], str], budget_tokens: int,
         max_items: int = 0) -> List[List[T]]:
    """Greedily pack rendered items into batches under ``budget_tokens``.

    An item larger than the whole budget still gets its own batch rather than
    being dropped -- the caller can decide to truncate, and a visibly oversized
    single item is a better failure than a silently missing one.
    """
    batches: List[List[T]] = []
    current: List[T] = []
    used = 0
    for item in items:
        cost = estimate_tokens(render(item))
        too_big = used + cost > budget_tokens
        too_many = max_items and len(current) >= max_items
        if current and (too_big or too_many):
            batches.append(current)
            current, used = [], 0
        current.append(item)
        used += cost
    if current:
        batches.append(current)
    return batches


def group_by(items: Iterable[T], key: Callable[[T], str]) -> Dict[str, List[T]]:
    """Stable grouping that preserves input order within each group."""
    groups: Dict[str, List[T]] = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    return groups
