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


def test_escape_keys():
    assert _escape_keys("a+b^c%(x)") == "a{+}b{^}c{%}{(}x{)}"


def test_class_name_re_matches_renamed_classes():
    old, new = Fake("Button", "Remove from Bookmarks", class_name="StarView"), \
        Fake("Button", "Remove from Bookmarks", class_name="PageActionView")
    root = Fake("Window", kids=[Fake("Button", "Zoom", class_name="PageActionView"), old, new])
    crit = {"class_name_re": "^(StarView|PageActionView)$", "title_re": "(?i)^remove from bookmarks"}
    assert uia.descendants(root, **crit) == [old, new]
    assert not uia.matches(Fake("Button", "Remove from Bookmarks", class_name="StarViewX"), **crit)
