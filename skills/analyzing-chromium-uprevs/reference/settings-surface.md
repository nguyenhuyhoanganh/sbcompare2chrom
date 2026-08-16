# Settings surface

Where settings live, how to compare them, and how large a "feature" should be.

## Contents

- Platform split
- Desktop sources and the three-hop chain
- Android sources
- Feature granularity
- Grouping rule
- Current tool coverage

## Platform split

Desktop and Android settings share no code. Pick one and stay in it.

| Platform | Settings are | Location |
|---|---|---|
| Windows / Mac / Linux | A WebUI page (`chrome://settings`) | `chrome/browser/resources/settings/` |
| Android | Declarative preference XML | `chrome/android/java/res/xml/` plus component directories |

For a Windows product, ignore the Android tree entirely.

## Desktop sources and the three-hop chain

| Source | Gives |
|---|---|
| `chrome/browser/resources/settings/route.ts` | The page inventory plus the `loadTimeData` guard around each route. Measured: 104 routes at M148, 108 at M151 |
| `chrome/browser/resources/settings/<page>/` templates | Each control, its type (`settings-toggle-button`, `settings-dropdown-menu`, `cr-radio-group`), and its `pref="{{prefs.x.y}}"` binding |
| `chrome/browser/ui/webui/settings/settings_ui.cc` | Maps each `loadTimeData` key to the `base::Feature` behind it |
| `chrome/browser/resources/settings/page_visibility.ts` | Per-page visibility keys (24 at both M148 and M151) |
| `chrome/common/pref_names.h` | Backing prefs. Already covered by the tool: 786 keys at M148, 684 at M151 |

The chain is:

```
route.ts  --guard-->  loadTimeData key  --settings_ui.cc-->  base::Feature
```

**Follow all three hops.** Stopping at the first gives trap 6 in
[traps.md](traps.md): the route table declares pages that a flag may hide.

The `pref="{{prefs.x.y}}"` binding in the templates is the strongest join key
between a UI control and the browser core, because it is declarative. Use it
when mapping a fork's own settings UI back to Chromium prefs — a fork usually
replaces the UI while keeping the underlying prefs.

The control type is written in the element name, which is what makes
"a dropdown became a toggle" mechanically detectable.

## Android sources

Roughly 43 preference XML files: 18 in `chrome/android/java/res/xml/` and the
rest across `components/browser_ui/site_settings/`, `chrome/browser/safety_hub/`,
`chrome/browser/privacy_sandbox/`, `chrome/browser/autofill/`,
`chrome/browser/download/`.

Visibility is decided in the matching `*Settings.java` via `ChromeFeatureList`
checks, for example:

```java
if (ChromeFeatureList.sAndroidAppearanceSettings.isEnabled()) {
    removePreferenceIfPresent(PREF_TOOLBAR_SHORTCUT);
    removePreferenceIfPresent(PREF_UI_THEME);
}
```

Android UI flags are declared in
`chrome/browser/flags/android/chrome_feature_list.cc` (268 at M148, 276 at
M151). That file is **not** in the tool's default target set; add it only if
working on an Android product.

## Feature granularity

Report at the size the audience cares about and say which size you are using.

| Size | Example | Detect via |
|---|---|---|
| **Control** | A toggle became a dropdown; a label changed | Template element type; strings |
| **Page / entry** | Five AI routes added at M151: `/ai/skills`, `/ai/suggestions`, `/autofill/suggestionsFromGemini`, `/shopping`, and a site-settings submenu | `route.ts` diff |
| **Capability** | Local Network Access split-permissions migration: 1 route removed, 1 added, 5 flags, 3 Blink runtime features, plus strings | Group by flag family |

## Grouping rule

**Group by flag family, not by file.** Chromium organizes its own work by flag,
so the shared prefix of a flag name is the correlation key — for example every
`kLocalNetworkAccessChecks*` flag belongs to one capability.

Without grouping, one capability-level change reports as roughly ten
contradictory lines, simultaneously claiming a page was removed and a page was
added. With grouping it is one line that states the migration, when it became
visible to users, and what the fork must update.

Changes with no flag (pure refactor, string-only edits) stop at control or page
size. Record them; do not promote them to capability.

## Current tool coverage

`chromedrift` covers flags, Blink runtime features, Web IDL, Mojo, switches,
prefs, chrome://flags metadata, **and the desktop WebUI surfaces**: page routes,
controls and visibility gates.

The same three extractors read every `chrome://` surface, not only settings.
Eight are tracked by default — settings, history, downloads, bookmarks,
extensions, password_manager, new_tab_page, print_preview — for about 1.7 MB
per version. Measured at M151: 108 routes, 633 controls, 668 gates.

Related fragments are grouped into one story by `cluster.py`, using links the
data declares (a route names its guard, a guard names its features) rather than
name similarity. The Local Network Access migration collapses 7 fragments
across 4 surfaces into a single row.

Chromium has roughly 130 WebUI surfaces; adding another is one line in
`targets.py`. Only the declarative parts are read — the route table and the
HTML templates, not the TypeScript behaviour.
