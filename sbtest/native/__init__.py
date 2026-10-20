"""Native layer (Windows only): everything that is NOT web content.

Use it for: toolbar/omnibox/star/menus/tab strip (browser "Views" UI), browser bubbles
and prompts (bookmark added, add extension, download bubble), OS dialogs (Save As,
Open, Print, message boxes), Windows toast notifications, browser keyboard shortcuts
(Ctrl+D, Ctrl+H, Ctrl+J ...), real mouse drag & drop.

Built on pywinauto with the UIA backend. Imported lazily so Linux/CI can run web tests.
"""
import os


def available() -> bool:
    if os.name != "nt":
        return False
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        return False
    return True


def require() -> None:
    if not available():
        raise RuntimeError("Native layer needs Windows + pywinauto (pip install -r requirements.txt)")
