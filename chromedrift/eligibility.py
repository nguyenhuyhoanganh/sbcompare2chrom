"""Is this file part of the product, and if not, why not.

One definition, because there were two and they disagreed in both directions.
Discovery -- the denominator every run prints -- wrapped the extractor
predicates in one set of exclusions, and extraction wrapped the same
predicates in another. Measured at M151:

  * `content/web_test/common/mojo_echo.mojom` counted as a candidate and was
    never read, so it sat in the denominator as a permanent miss.
  * `cc/mojom/hit_test_opaqueness.mojom` was read and produced facts while
    being excluded from the denominator, because a substring rule saw `_test_`
    inside `hit_test`. Hit testing is a product concept, not test code.

Saying the two pipelines share a predicate is not enough while each wraps it
in its own policy. They call this instead.

The rules are conventions rather than truth -- Chromium states the real answer
in BUILD.gn, which this tool does not read -- so they are written as narrowly
as the convention allows: a suffix immediately before the extension, or an
exact directory component. A substring rule is what produced the `hit_test`
error, and widening one to catch `_test_service` would have produced more.
"""

from __future__ import annotations

import re

# Directory components that are never product code, matched exactly.
_SKIP_DIRS = (
    "testing", "test", "tests", "out", ".git", "__pycache__",
    "fuzzers", "fuzzer", "web_test", "web_tests", "mock",
)

# Filename conventions for test code, anchored to the extension so `hit_test`
# and `latency_test_helper` are told apart by where the word sits.
_TEST_FILE_RE = re.compile(
    r"(?:^|/)[^/]*?"
    r"(_test|_tests|_unittest|_browsertest|_perftest|_test_api|_test_service"
    r"|_test_util|_test_utils|_fuzzer|_mock)"
    r"\.[A-Za-z0-9]+$"
    r"|(?:^|/)(fuzz|mock)\.[A-Za-z0-9]+$"
)

# Binaries that ship beside the browser rather than being it. Their switches
# and features are real declarations that reach none of our users.
_NOT_THE_PRODUCT_RE = re.compile(
    r"^content/shell/|^chrome/test/|^tools/|^headless/|^remoting/"
    r"|^chrome/(updater|enterprise_companion|windows_services)/")

# Other people's libraries, carrying files whose names match our conventions.
_VENDORED_RE = re.compile(
    r"^third_party/(?!blink/)"
    r"|/third_party/(abseil|grpc|ipcz|libxml|opus|tflite|zlib|webrtc_overrides)/")


def skip_reason(path: str) -> str:
    """"" when the file is in scope, otherwise why it is not."""
    path = path.replace("\\", "/")
    parts = path.split("/")[:-1]
    for part in parts:
        if part in _SKIP_DIRS:
            return f"{part}/ is not product code"
    if _TEST_FILE_RE.search(path):
        return "test or fuzzer declaration"
    if _NOT_THE_PRODUCT_RE.search(path):
        return "a binary that ships beside the browser"
    if _VENDORED_RE.search(path):
        return "vendored third-party source"
    return ""


def in_scope(path: str) -> bool:
    return not skip_reason(path)
