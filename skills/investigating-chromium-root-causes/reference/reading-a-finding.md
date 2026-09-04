# Reading a finding

An investigation starts from one row and has to decide what that row means
before it goes looking for the CL behind it. Three things decide it: what the
row's signals say, the ways a correct finding can still be read wrongly, and
the chain sitting behind a settings control.

They are here so an investigation needs nothing outside this directory.

## Contents

- The signals this skill acts on
- Traps that change the verdict
- The settings three-hop chain

## The signals this skill acts on

| Signal | Meaning |
|---|---|
| `enabled_by_default` | Now ON by default **on Windows** |
| `default_flip_on` | Global default flipped on |
| `ipc_signature_change` | Mojo method signature moved. Breaks across the process boundary at runtime, not at compile time |
| `ipc_shape_changed` | The data half of the same break: a struct field changed type or ordinal, or a struct became a union. The other process reads those bytes as something else |

A report carries far more signals than these four; these are the ones this
skill's own steps name. For any other signal, read the row's `signals` field
together with its finding text — the leading signal is the one with the highest
severity, and it is both what set the severity and what filed the row under its
bucket.

## Traps that change the verdict

Read these before interpreting any removal. Each is a way to reach a wrong
answer from a finding that is itself correct.

### A retired flag is not a removed feature

A `base::Feature` or Blink runtime feature disappears and the diff reads as
lost capability. Chromium deletes the flag once the outcome is settled, so the
state the flag held *just before* deletion says which outcome that was.

Across a milestone pair this is a large class, and most of it is
`flag_retired_on` — features that shipped — rather than `flag_retired_off`.
Reading the class as lost capability inverts what it usually means.

`flag_retired_on` means the behaviour is now permanent and unremovable;
`flag_retired_off` means the code is gone. Neither changes behaviour at this
upgrade, but both break the build of anything naming the symbol, and both
silently kill any override that was setting the flag from outside the binary.

### A declaration usually moved rather than went away

An entry vanishes from a file and normally reappears elsewhere, often behind a
different flag. M148 → M151 "lost" the route `SITE_SETTINGS_LOCAL_NETWORK_ACCESS`;
Chromium was mid-migration and declared both versions of the page at M148, each
behind its own guard, then deleted the old one once the new guard had shipped.

Search the whole tree for the key before reporting a removal, and read the
`guards` attribute on both sides. If it exists elsewhere this is a move, and
the user-visible change happened whenever the controlling flag flipped —
usually earlier than either version being compared, which is why the CL you
want may sit outside the window.

### A Mojo ABI break has to break it for somebody

Both ends of a Mojo interface are compiled from the same tree, so the browser
and renderer processes of one build always agree. An `ipc_signature_change`
between two stock versions is therefore a **build break for code outside this
tree**, not a runtime break — unless something ships separately from the
browser and speaks the same interface, an install can end up part-updated so
two versions run side by side, or there is out-of-tree code implementing the
interface, which is the usual case.

Say which of those applies before calling it a runtime break. A **Breaking**
row says a contract moved, not that anyone had signed it.

### A removed switch fails silently; a removed pref may orphan data

Chromium **ignores command-line switches it does not recognise** — no warning,
no error, no log line. A launch script or test runner keeps starting the
browser exactly as before while the flag it passes stops doing anything.

A removed preference is different: the key stays in the user's `Preferences`
file on disk, and whether that matters depends on whether Chromium wrote a
migration in `chrome/browser/prefs/browser_prefs.cc`.

For a switch, search launch scripts and test automation for the string. For a
pref, note that `browser_prefs.cc` is read on a `wide` run and not on a
`default` one. And apply the previous trap first: on a default run a removed
key arrives as `pref_left_scan`, whose own reason says the key may simply have
moved into a pref file the scan never opened. That signal is an unsettled
question, not a deletion, and a `wide` run is what settles it.

## The settings three-hop chain

When the symptom is a control on a settings page, the flag behind it is three
hops away:

```
route.ts  --guard-->  loadTimeData key  --settings_ui.cc-->  base::Feature
```

| Source | Gives |
|---|---|
| `chrome/browser/resources/settings/route.ts` | The page inventory plus the `loadTimeData` guard around each route |
| `chrome/browser/resources/settings/<page>/` templates | Each control, its type (`settings-toggle-button`, `settings-dropdown-menu`, `cr-radio-group`), and its `pref="{{prefs.x.y}}"` binding |
| `chrome/browser/ui/webui/settings/settings_ui.cc` | Maps each `loadTimeData` key to the `base::Feature` behind it |
| `chrome/browser/resources/settings/page_visibility.ts` | Per-page visibility keys. **Not fetched by the tool** — read it by hand when a page's presence is the question |
| `chrome/common/pref_names.h` | Backing prefs |

**Follow all three hops.** Stopping at the first reports a page as present that
a flag may be hiding: a declarative file declares more than ships.

The `pref="{{prefs.x.y}}"` binding is the strongest join between a control and
the browser core, because it is declarative and survives a redesign — the page
can be rewritten while the preference behind it stays, so the binding tells you
the same control moved rather than a new one appearing beside an old one
disappearing. The control type is written in the element name, which is what
makes "a dropdown became a toggle" mechanically detectable.
