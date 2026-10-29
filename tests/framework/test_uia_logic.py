"""Native layer logic with fake UIA elements (real UIA needs Windows)."""
from types import SimpleNamespace

from sbtest.native import uia
from sbtest.native.dialogs import Dialog, _escape_keys


class Fake:
    def __init__(self, control_type, name="", auto_id="", class_name="", kids=(), value=None):
        self.element_info = SimpleNamespace(control_type=control_type, name=name, automation_id=auto_id,
                                            class_name=class_name)
        self.kids = list(kids)
        self.value = value
        self.invoked = False

    def children(self):
        return self.kids

    def descendants(self, **cond):
        out = []
        for k in self.kids:
            out += [k] + k.descendants()
        return [e for e in out if all(getattr(e.element_info, {"title": "name"}.get(a, a)) == v
                                      for a, v in cond.items())]

    def rectangle(self):
        return SimpleNamespace(left=0, top=0, right=10, bottom=10)

    def is_enabled(self):
        return True

    def is_visible(self):
        return True

    def get_value(self):
        if self.value is None:
            raise AttributeError
        return self.value

    def invoke(self):
        self.invoked = True

    def click_input(self):
        self.clicked = True


def tree(button_class="Button"):
    done = Fake("Button", "Done", class_name=button_class)
    return Fake("Window", "Bookmark added", kids=[
        Fake("Text", "Bookmark added"),
        Fake("Edit", "Name", auto_id="name", value="Static page 1"),
        Fake("Pane", kids=[done, Fake("Button", "Remove")]),
    ]), done


def test_descendants_filters_and_index():
    root, _ = tree()
    assert [e.element_info.name for e in uia.descendants(root, control_type="Button")] == ["Done", "Remove"]
    assert [e.element_info.name for e in uia.descendants(root, title_re="(?i)^rem")] == ["Remove"]
    assert uia.descendants(root, control_type="Button", found_index=1)[0].element_info.name == "Remove"
    assert uia.descendants(root, auto_id="name")[0].element_info.control_type == "Edit"


def test_texts_and_dump():
    root, _ = tree()
    assert uia.texts(root) == ["Bookmark added", "Static page 1", "Done", "Remove"]
    assert "Button 'Done'" in uia.dump(root)


def test_dialog_click_by_partial_name():
    root, done = tree()  # Win32 button: UIA Invoke
    Dialog(root, timeout=0.5).click("done")
    assert done.invoked


def test_dialog_click_views_button_uses_mouse():
    root, done = tree(button_class="OneUITextButton")  # browser bubble: ignores Invoke while fading in
    Dialog(root, timeout=0.5).click("done")
    assert getattr(done, "clicked", False) and not done.invoked


def test_views_button_waits_out_the_input_protection(monkeypatch):
    import time

    monkeypatch.setattr(uia, "input_protection", lambda: 0.3)
    root, done = tree(button_class="OneUITextButton")
    dlg = Dialog(root, timeout=0.5)
    start = time.monotonic()
    dlg.click("done")
    assert time.monotonic() - start >= 0.25   # the bubble was just shown: Chromium drops early clicks
    dlg.seen_at -= 1
    start = time.monotonic()
    dlg.click("done")
    assert time.monotonic() - start < 0.25    # shown long ago: no extra wait


def test_wait_actionable_waits_until_the_element_stops_moving():
    el = Fake("Button", "Pin")
    lefts = iter([0, 40, 80, 100, 100])
    el.rectangle = lambda: SimpleNamespace(left=(x := next(lefts, 100)), top=0, right=x + 10, bottom=10)
    assert uia.wait_actionable(el, timeout=2, interval=0.01) is el
    assert next(lefts, "done") == "done"      # it kept sampling until two equal rectangles


def test_wait_actionable_says_why_it_gave_up():
    import pytest

    el = Fake("Button", "Save")
    el.is_enabled = lambda: False
    with pytest.raises(TimeoutError, match="Button 'Save' not ready to click.*disabled"):
        uia.wait_actionable(el, timeout=0.1, interval=0.02)
    el.is_enabled, el.is_visible = (lambda: True), (lambda: False)
    with pytest.raises(TimeoutError, match="off screen"):
        uia.wait_actionable(el, timeout=0.1, interval=0.02)


def test_escape_keys():
    assert _escape_keys("a+b^c%(x)") == "a{+}b{^}c{%}{(}x{)}"


def test_class_name_re_matches_renamed_classes():
    old, new = Fake("Button", "Remove from Bookmarks", class_name="StarView"), \
        Fake("Button", "Remove from Bookmarks", class_name="PageActionView")
    root = Fake("Window", kids=[Fake("Button", "Zoom", class_name="PageActionView"), old, new])
    crit = {"class_name_re": "^(StarView|PageActionView)$", "title_re": "(?i)^remove from bookmarks"}
    assert uia.descendants(root, **crit) == [old, new]
    assert not uia.matches(Fake("Button", "Remove from Bookmarks", class_name="StarViewX"), **crit)


def test_class_name_re_alternatives_search_natively_per_class():
    star = Fake("Button", "Remove from Bookmarks", class_name="PageActionView")
    root = Fake("Window", kids=[Fake("Pane", "web", kids=[Fake("Text", "x")] * 3), star])
    calls = []
    orig = root.descendants

    def spy(**cond):
        calls.append(cond)
        return orig(**cond)

    root.descendants = spy
    assert uia.descendants(root, class_name_re="^(StarView|PageActionView)$", title_re="(?i)remove") == [star]
    assert calls == [{"class_name": "StarView"}, {"class_name": "PageActionView"}]


def test_window_rect_covers_browser_windows_only():
    from sbtest.native.browser_ui import NativeBrowser

    def win(l, t, r, b):
        return SimpleNamespace(rectangle=lambda: SimpleNamespace(left=l, top=t, right=r, bottom=b,
                                                                 width=lambda: r - l, height=lambda: b - t))
    nb = NativeBrowser.__new__(NativeBrowser)
    nb.pid = 1
    frame, bubble, minimized, helper = win(0, 0, 1200, 900), win(1000, 50, 1400, 300), \
        win(-32000, -32000, -31840, -31972), win(5, 5, 5, 5)
    nb.windows = lambda: [frame, bubble, minimized, helper]
    assert nb.window_rect() == (0, 0, 1400, 900)
    nb.windows = lambda: [minimized]
    try:
        nb.window_rect()
        raise AssertionError("expected LookupError")
    except LookupError:
        pass


def test_screen_grab_prefers_the_browser_windows(tmp_path):
    from sbtest.reporting import evidence

    shots = []
    native = SimpleNamespace(screenshot=lambda p: shots.append(p) or p)
    session = SimpleNamespace(native=native)
    cfg = {"report.screen_capture": "window"}
    conf = SimpleNamespace(get=lambda k, d=None: cfg.get(k, d))
    assert evidence.screen_grab(tmp_path / "s.png", session, conf) == tmp_path / "s.png"
    assert shots == [tmp_path / "s.png"]


def test_keyboard_goes_only_to_the_browser(monkeypatch):
    import pytest

    from sbtest.native import browser_ui
    from sbtest.native.browser_ui import NativeBrowser

    monkeypatch.setattr(browser_ui, "poll", lambda fn, *a, **k: fn() or (_ for _ in ()).throw(TimeoutError()))
    nb = NativeBrowser.__new__(NativeBrowser)
    nb.pids = lambda: {10, 11}
    front = {"pid": 11}
    nb.foreground_owner = lambda: (front["pid"], {10: "samsunginternet.exe", 11: "samsunginternet.exe", 99: "Widgets.exe"}[front["pid"]])
    focused = []
    nb.focus = lambda: focused.append(True) or front.update(pid=10)
    nb.ensure_keyboard_target()                        # a browser window is in front: nothing to do
    assert not focused
    front["pid"] = 99
    nb.ensure_keyboard_target(refocus=True)            # shortcut: bring the browser back
    assert focused and front["pid"] == 10
    front["pid"] = 99
    with pytest.raises(RuntimeError, match="Widgets.exe"):
        nb.ensure_keyboard_target(refocus=False)       # typing into a field: never move the focus


def test_only_test_browsers_left_by_a_crash_are_closed(monkeypatch):
    from types import SimpleNamespace as NS

    from sbtest import utils

    procs = [NS(info={"pid": 1, "cmdline": ["sb.exe", r"--user-data-dir=C:\repo\artifacts\test-results\profiles\t_1"]}),
             NS(info={"pid": 2, "cmdline": ["sb.exe", r"--user-data-dir=C:\repo\artifacts\test-results\profiles\t_1",
                                            "--type=renderer"]}),                         # child: goes with pid 1
             NS(info={"pid": 3, "cmdline": ["sb.exe", r"--user-data-dir=C:\Users\me\AppData\Samsung\User Data"]}),
             NS(info={"pid": 4, "cmdline": ["sb.exe"]})]                                  # the user's own browser
    killed = []
    monkeypatch.setattr(utils.psutil, "process_iter", lambda attrs: procs)
    monkeypatch.setattr(utils, "kill_tree", killed.append)
    assert utils.kill_browsers_using([r"C:\repo\artifacts\test-results\profiles"]) == [1] and killed == [1]


def test_startup_bubbles_stop_waiting_when_the_build_never_shows_them():
    import time

    from sbtest.native import browser_ui

    nb = browser_ui.NativeBrowser.__new__(browser_ui.NativeBrowser)
    nb.ui_map = {"startup_bubbles": [{"text": "(?i)has been updated", "button": "Close"}]}
    nb.windows = lambda: []
    browser_ui._STARTUP_BUBBLES.update(starts=0, seen=0)
    took = []
    for _ in range(3):
        t = time.monotonic()
        assert nb.dismiss_startup_bubbles(timeout=0.4) == []
        took.append(time.monotonic() - t)
    assert took[0] >= 0.4 and took[1] >= 0.4 and took[2] < 0.1, took
    browser_ui._STARTUP_BUBBLES.update(starts=0, seen=0)
