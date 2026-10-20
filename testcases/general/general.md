# General browsing (sample cases)

## GEN-001 Back and forward navigation
- Steps: open page 1, page 2; Back; Forward
- Expected: titles follow page 1 -> page 2 -> page 1 -> page 2
- Automated: tests/general/test_navigation.py::test_back_forward

## GEN-002 Link with target=_blank opens a new tab
- Steps: click "Open page 2 in new tab"
- Expected: a second tab with "Static page 2"
- Automated: tests/general/test_navigation.py::test_link_opens_new_tab

## GEN-003 JavaScript alert / confirm / prompt
- Steps: trigger each dialog; accept / dismiss / type a value
- Expected: page shows the matching result
- Automated: tests/general/test_page_interactions.py::test_js_dialogs

## GEN-004 Fill and submit a form with a file upload
- Steps: fill text, select, checkbox, radio, file; submit
- Expected: the server echoes the submitted values
- Automated: tests/general/test_page_interactions.py::test_form_submit

## GEN-005 HTML5 drag and drop
- Steps: drag the item onto the drop zone
- Expected: "dropped:html5"
- Automated: tests/general/test_page_interactions.py::test_drag_and_drop_html5

## GEN-010 Type a URL in the address bar (native)
- Type: native
- Steps: focus the omnibox, type a local URL, Enter
- Expected: the page loads, the omnibox shows the URL
- Automated: tests/general/test_native_ui.py::test_omnibox_navigation

## GEN-011 Save page with Ctrl+S (native Save As)
- Type: native
- Steps: open page 1, Ctrl+S, save to a temp folder
- Expected: the .html file exists
- Automated: tests/general/test_native_ui.py::test_save_page_as
