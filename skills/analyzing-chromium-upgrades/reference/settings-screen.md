# The settings screen

Where settings live, how to compare them, and how large a "feature" should be.

## Contents

- Where settings live
- Desktop sources and the three-hop chain
- Feature granularity
- Grouping rule
- Current tool coverage

## Where settings live

On desktop, settings are a web page: `chrome://settings` is TypeScript and HTML
templates under `chrome/browser/resources/settings/`, served by C++ handlers in
`chrome/browser/ui/webui/settings/`.

Chromium's mobile builds implement settings a completely different way — as
declarative preference XML with Java visibility logic — and share no code with
this. That tree is irrelevant to a Windows product, is excluded from the target
set, and should not appear in a report. If a finding points into it, the
finding is wrong.

## Desktop sources and the three-hop chain

| Source | Gives |
|---|---|
| `chrome/browser/resources/settings/route.ts` | The page inventory plus the `loadTimeData` guard around each route. Measured: 104 routes at M148, 108 at M151 |
| `chrome/browser/resources/settings/<page>/` templates | Each control, its type (`settings-toggle-button`, `settings-dropdown-menu`, `cr-radio-group`), and its `pref="{{prefs.x.y}}"` binding |
| `chrome/browser/ui/webui/settings/settings_ui.cc` | Maps each `loadTimeData` key to the `base::Feature` behind it |
| `chrome/browser/resources/settings/page_visibility.ts` | Per-page visibility keys (24 at both M148 and M151). **Not fetched by the tool** — read it by hand when a page's presence is the question |
| `chrome/common/pref_names.h` | Backing prefs. Already covered by the tool: 785 keys at M148, 683 at M151 |

The chain is:

```
route.ts  --guard-->  loadTimeData key  --settings_ui.cc-->  base::Feature
```

**Follow all three hops.** Stopping at the first gives trap 6, *declarative
files declare more than ships*: the route table declares pages that a flag may
hide. `reference/traps.md` is linked from SKILL.md.

The `pref="{{prefs.x.y}}"` binding in the templates is the strongest join key
between a UI control and the browser core, because it is declarative. It is
what survives a redesign: the page can be rewritten while the preference behind
it stays, so the binding tells you the same control moved rather than a new one
appearing beside an old one disappearing.

The control type is written in the element name, which is what makes
"a dropdown became a toggle" mechanically detectable.

## Feature granularity

Report at the size the audience cares about and say which size you are using.

| Size | Example | Detect via |
|---|---|---|
| **Control** | A toggle became a dropdown; a label changed | Template element type; strings |
| **Page / entry** | A new route, with its own visibility and behaviour conditions | `route.ts` plus gate/consumer source |
| **Capability** | Related pages, controls and core consumers establish one transition | Trace bindings and source/CL evidence on both versions |

## Grouping rule

Use shared flags, names and files as retrieval leads. Verify a shared mechanism
before grouping: a common prefix or screen does not establish one capability,
and a broad feature gate can control multiple independent changes. The same
pref or unchanged gate can bridge changed components; inspect its consumers.

Without grouping, one capability-level change reports as roughly ten
contradictory lines, simultaneously claiming a page was removed and a page was
added. With grouping it is one line that states the migration, when it became
visible to users, and what is left to update.

Changes without a flag can also establish a capability transition. Determine
its size from the behaviour and consumer evidence, not the presence of a flag.

## Current tool coverage

`chromiumdiff` covers flags, Blink runtime features, Web IDL, Mojo, switches,
prefs, chrome://flags metadata, **and the desktop WebUI screens**: page routes,
controls and visibility gates.

The same three extractors read every `chrome://` screen, not only settings.
Eight are tracked by default — settings, history, downloads, bookmarks,
extensions, password_manager, new_tab_page, print_preview — for about 1.7 MB
per version. Measured at M151 on the default target set: 108 routes, 971
controls across those eight screens, 764 gates.

`cluster.py` supplies candidate bundles. The review workbench preserves typed
links through both snapshots, including unchanged facts; neither is a final
decision that every connected row belongs to one semantic event.

Measured at M151, `chrome/browser/resources/` holds **132** screens, so the
eight tracked are **6%** of them; adding another is one line in `targets.py`.
Only the declarative parts are read — the route table and the HTML templates,
not `page_visibility.ts` and not the TypeScript behaviour.
