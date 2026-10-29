---
name: sbtest-explore
description: Turns a plain request about Samsung Browser for Windows ("test that opening the add-on shows info X", "check the bookmark panel lists Y", "write a test for this flow", "this test broke, fix it") into a working sbtest test - explores the real build first (screenshots, DOM and UIA dumps), maps every step to the action catalogue, writes the case doc and the script, runs it until it is stable. Use whenever a test must be written, extended or repaired and the exact UI (labels, buttons, dialogs, toolbar icons, popups, internal pages) is not already known.
---

# From a request to a stable test - explore, map, write, prove

You work on the Windows machine that has the browser. Never guess a label, selector or
behaviour: look at the real build, then write. This is how every test in this repo was made.

Other skills: `sbtest-intake` (cases from Confluence/Jira), `sbtest-author` (framework API,
conventions, page objects), `sbtest-run` (run + report). This skill is the working method.

Copy this checklist into your reply and tick it off:

```
- [ ] 1 request rewritten as a case (or an existing case extended)
- [ ] 2 UI explored, screenshots read, findings written down
- [ ] 3 every step mapped to the action catalogue (missing rows added)
- [ ] 4 green 4x in a row, whole feature green, case + overview updated
```

## 1. Understand the request -> a case

Rewrite the request as a case before touching code (format: `tests/features/README.md`):
the ID given with the case (the team's own scheme; none given -> ask the user, never invent one),
title, Type (web / native), Precondition, numbered Steps, Expected (observable facts).

- **One behaviour per case.** Check the feature's docs (`tests/features/<feature>/*.md`, overview
  `tests/features/TESTCASES.md`) first: if an existing case covers it, extend that case or reuse
  its test instead of adding a near-duplicate. Prefer a stronger existing case over a new one.
- Put the case in the file of its area: `<feature>/<area>.md` (manager page cases,
  `sanity.md`, `toolbar.md` for browser-UI flows ...). Tests mirror it:
  `tests/features/<feature>/test_<feature>_<area>.py`, so a feature can be run alone
  (`python run.py --feature bookmarks`).

## 2. Explore the real UI (always, before writing selectors)

1. Machine ready? `python -m sbtest.tools.doctor` ends with READY (once per session; new
   machine: `setup.bat`). Read
   `.agents/skills/sbtest-author/references/feature-notes.md` for the feature (known traps).
2. Quick look at an internal page: `python -m sbtest.tools.dom <page> --interactive`
   (lines end with a ready locator), with data: `--seed-bookmarks resources/data/bookmarks.yaml:seed_basic`,
   `--extension resources/extensions/sample_addon`. Native UI: `python -m sbtest.tools.uia_dump --find "(?i)text"`.
3. A flow (menus, bubbles, popups, dialogs): write a scratch test with `Explorer`
   (template: `templates/explore_template.py`) in `tests/_scratch/` (git-ignored) and run
   `python -m pytest tests/_scratch/test_x.py -s -p no:cacheprovider` (its failure evidence and
   chromedriver log: `artifacts/explore/scratch-run/`; `test-results/` is left alone).
   `x.snap(label)` saves `artifacts/explore/<name>/NN_label.png` (browser windows + bubbles),
   `.dom.txt` (locators) and `.uia.txt`; `x.try_step(label, fn)` keeps going on errors;
   `x.find_native("(?i)text")` / `x.find_web("text")` print exact names and locators.
4. **Read the screenshots** (open the PNGs) - they show what really happened: a toast instead
   of a bubble, a new tab instead of the same tab, a dialog that fades in, a label that differs.
5. Write down what you learned (labels, where it opens, what changes) - it goes into the page
   object docstring, the ui map comment and `.agents/skills/sbtest-author/references/feature-notes.md`.
6. Delete the scratch file when done.

## 3. Map each step to an action

Use `references/action-catalog.md` - "the user says / the case says" -> the call to make,
for internal pages, toolbar and bubbles, add-ons, downloads, dialogs, tabs, keyboard, data
setup, assertions. Rules that keep tests portable and readable:

- Selectors live in page objects (`sbtest/pages/*.py`), UIA criteria in `config/native_ui.yaml`
  (with `{name}` params for per-item names); what a test may contain: `sbtest-author`, "Hard
  rules". Missing? Add a page-object method / ui-map entry from what you explored.
- Each doc step = `with step("N. ...", expected="..."):`; assertions = the doc's Expected.
- Wait for conditions (`web.wait_until`, page `wait_*`, `native.element(..., timeout)`), no sleeps.

## 4. Prove it

1. `python run.py --case <ID>` until green, then 3 more runs.
2. Run it once with `--screenshot-steps` and open `artifacts/test-results/steps/<test>/` (or
   watch the `--record` video in `videos/`): each `NN-I_<kind>.jpg` frames what the step is
   about to touch - check it is the right element; a wrong one shows even when the test passes.
3. On failure read `artifacts/test-results/failures/<test>/failure.txt`, then `screen.png` /
   `page.png`, fix, repeat. The product behaves differently from the request -> do not bend the
   test: report it with the screenshot.
4. `--feature X` once (nothing else broke), add `- Automated: tests/...::test_x` to the case,
   regenerate the overview (`references/action-catalog.md` -> "After writing").

## Worked example

Request: *"Write a test: open the add-on from the toolbar, its popup shows the add-on name
and a counter that increases when clicked."*

1. Case: existing `ADD-112` already covers it -> extend, don't duplicate. (If it did not
   exist: `tests/features/addons/toolbar.md`, Type native, Precondition "SB Sample Addon installed
   and pinned", Steps "click the add-on icon / click the popup button", Expected "popup with
   name + Clicked 0 / becomes Clicked 1".)
2. Explore: scratch test -> `native.click("extensions_button")`, `x.find_native("(?i)sb sample|pin")`
   showed `Button 'Pin SB Sample Addon'`; after pinning, `ToolbarActionView 'SB Sample Addon\nHas
   access to this site'`; clicking it showed `Document 'SB popup'`, `Button 'Clicked 0' auto_id=count`.
3. Map: ui map `addons_menu_pin` (title "Pin {name}"), `extension_action` (class
   ToolbarActionView, title_re "^{name}"); test: `native.click("addons_menu_pin", name=ADDON)`,
   `native.click("extension_action", name=ADDON)`, `native.click(POPUP_COUNTER, in_main=False)`
   (the popup is its own window).
4. Prove: `python run.py --case ADD-112` x4, then `--feature addons`.

## Worked example: a sanity case given as text (how GEN-002 was made)

Given: *"GEN-002 General - open a link in a new tab. Precondition: a page with a link. Steps: open the
page; right-click the link, choose 'Open link in new tab'. Expected: a new tab opens with the
linked page; the first tab still shows the original page."*

1. Case: `coverage --feature general` -> not covered yet; ID GEN-002 as given. Written to
   `tests/features/general/general.md` with a local page as the precondition ("Static page 1",
   link "Next" to "Static page 2"), Type native (the right-click menu is browser UI).
2. Explore: scratch test, right-click `#next` with the real mouse, print `native.menu_items()`
   -> Samsung's label is **"Open in new tab"** (the case used Chrome's "Open link in new tab");
   the tab handles showed the new tab opens in the BACKGROUND. Both went into feature-notes.
3. Map: catalogue "right-click on a page" -> `native.context_menu_web(web, "#next", "Open in new tab")`,
   "new tab expected" -> `before = web.tabs` ... `web.wait_new_tab(before)`; Expected = assertions
   on the titles of both tabs. Steps titled like the doc: `step("2. Right-click the link ...")`.
4. Prove: green 4x, once with `--screenshot-steps` (the frame sat on "Open in new tab"),
   `--feature general` green, `- Automated:` added, overview regenerated.

The wording of a case is the author's guess at the UI: keep its meaning, use the labels the
build really shows, and say so in your report.
