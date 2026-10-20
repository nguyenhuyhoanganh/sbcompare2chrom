"""Reference: drag & drop inside a page. Choosing the method:
html5 = draggable/dataTransfer pages, actions = mouse-event widgets, native = real mouse
(see tests/reference/native and files/ for drags that involve browser UI or Explorer)."""


def test_html5_drag_and_drop(web, site):
    web.open(site.url("/dragdrop.html"))
    web.drag_and_drop("#drag-html5", "#drop-html5", method="html5")
    web.wait_text("#html5-result", "dropped:html5")


def test_html5_sortable_list(web, site):
    web.open(site.url("/dragdrop.html"))
    web.drag_and_drop("#sortable li:nth-child(3)", "#sortable li:nth-child(1)", method="html5")
    web.wait_until(lambda: web.texts("#sortable li") == ["Item C", "Item A", "Item B"], message="C moved first")
