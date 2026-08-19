# Signal reference

Every finding carries one or more signals. The signal, not the score, tells you
what actually happened. Read this column first.

## Contents

- Behaviour changed
- Behaviour unchanged (cleanup)
- Silent breaks
- Structural
- Fork-comparison signals (`--mode fork`)
- Bucket meanings
- Scoring

## Behaviour changed

Users experience a difference. This is the short list that matters.

| Signal | Meaning |
|---|---|
| `enabled_by_default` | Now ON by default **on Windows** |
| `disabled_by_default` | Now OFF by default **on Windows** |
| `default_flip_on` | Global default flipped on |
| `default_flip_off` | Global default flipped off — usually a rollback |
| `web_api_shipped` | Web API reached stable; sites will start using it |
| `web_api_unshipped` | Web API pulled back from stable — rare, investigate |
| `web_api_removed` | Real API removal, detected from IDL. Site-visible break |
| `web_api_signature_change` | An IDL member's signature moved; existing call sites may not match |
| `ipc_signature_change` | Mojo method signature moved. Breaks across the process boundary at runtime, not at compile time |
| `ipc_removed` | Mojo interface or method removed |

The first two are resolved for Windows specifically, by walking the `#if
BUILDFLAG(...)` chain around the declaration. The global default and the
Windows default routinely disagree, which is why `default_flip_*` and
`enabled_by_default` are separate rows: the first says what Chromium wrote, the
second says what our users get.

## Behaviour unchanged (cleanup)

The largest group in a typical report, and the most misread. **None of these
changes behaviour.** They matter only if the fork references the symbol — in
which case the build breaks or an override silently stops applying.

| Signal | Meaning |
|---|---|
| `flag_retired_on` | Shipped earlier; behaviour is now permanent and **can no longer be turned off** |
| `flag_retired_off` | Never shipped; code removed, **can no longer be turned on** |
| `killswitch_retired` | Blink runtime equivalent of `flag_retired_on` |
| `experimental_dropped` | Experimental Blink flag abandoned |
| `feature_deleted` | Flag removed but its prior state could not be determined — investigate manually |
| `declaration_moved` | Declaration moved to another file; nothing else changed |

Measured evidence for why this distinction exists:

- **M148 → M151, Windows**: 90 `base::Feature` flags removed, split exactly
  45 `flag_retired_on` / 45 `flag_retired_off`. Labelling all 90 "feature
  deleted" makes half the list false alarms.
- **M139 → M143, Blink**: of 202 runtime features that disappeared, **170 had
  been `stable`** — retired after shipping, not removed capability.

## Silent breaks

Compile cleanly, pass tests, fail in the field. The most expensive class to
discover late, because nothing warns you.

| Signal | Meaning |
|---|---|
| `feature_string_renamed` | The Finch feature name changed. Server-side field trials and `--enable-features` using the old spelling silently stop matching |
| `feature_symbol_renamed` | The mirror image: the C++ identifier changed while the feature string held. Code writing `features::kOldName` stops compiling. Loud rather than silent, but only after the merge — which is the point of seeing it now |
| `pref_renamed` | A preference key changed. Every existing user's stored value is orphaned and the setting quietly resets |
| `switch_renamed` | Command-line switch renamed. Launch scripts and automation stop taking effect |
| `origin_trial_change` | Origin trial wiring changed |

Always check these against things the tool cannot see: Finch configs, launch
scripts, CI automation, QA harnesses.

### Disappeared, cause unknown

| Signal | Meaning |
|---|---|
| `pref_left_scan` | A preference key is no longer in the one `pref_names.h` file this tool reads. It was either deleted — orphaning every user's stored value — or moved into one of the ~100 other `pref_names.h` files outside the scan |
| `switch_left_scan` | Same, for a command-line switch |

**These two are deliberately uncertain, and the uncertainty is the finding.**
Chromium is actively splitting `chrome/common/pref_names.h` apart: 4,322 lines
at M143, 3,267 at M151. Measured across M143 → M148 → M151 that produced **337
disappearances**, and the tool cannot tell a deletion from a move because it
reads 1 of the ~100 non-ChromeOS `pref_names.h` files.

Resolve one by searching the current Chromium tree for the key string. Found
elsewhere means it moved and there is nothing to do; genuinely absent means
stored user data is orphaned, which is a real and silent break. Do not report
either outcome until you have looked.

## Structural

| Signal | Meaning |
|---|---|
| `web_api_added` | New web API surface — test coverage, possible adoption |
| `ui_page_added` / `ui_page_removed` | A chrome:// page appeared or disappeared. **Check its guard before concluding** — see traps.md |
| `ui_page_regated` | The page is now shown under a different flag. The user-visible switch happened when that flag flipped, usually earlier |
| `ui_page_moved` | The page's URL or parent route changed |
| `ui_control_type_changed` | A control changed type, e.g. dropdown became a toggle |
| `ui_control_repointed` | The control now writes a different preference; the old one is orphaned |
| `ui_control_added` / `ui_control_removed` | A control appeared or disappeared on a page |
| `ui_gate_changed` / `ui_gate_removed` / `ui_gate_added` | The condition deciding a page's visibility moved, went away, or appeared |
| `new_feature_on_by_default` | New flag, already on |
| `param_default_changed` | A feature parameter default moved; behaviour tuning |
| `flag_expiring` | chrome://flags entry scheduled for removal in an upcoming milestone — future forced work |

## Fork-comparison signals (`--mode fork`)

A different run entirely: upstream Chromium against **our fork at the same
milestone**, rather than upstream against its own future. Direction is fixed as
upstream → fork, so these signals describe what *we* did, not what Chromium did.
An uprev signal never appears in a fork report and vice versa.

| Signal | Meaning |
|---|---|
| `fork_dropped` | We removed something upstream still has. **The next rebase brings it back** unless a patch carries the removal |
| `fork_added` | We have something upstream does not. Our own divergence, already shipped, to be carried through every future merge |
| `fork_default_override` | We ship a different default from upstream. A rebase can silently revert it |
| `fork_modified` | Our declaration differs from upstream's in some other way |
| `fork_ui_removed` / `fork_ui_added` | We removed or added a page or control |

The hard question these cannot answer on their own is whether a difference is a
*decision* or *debt* — someone chose it, or a merge quietly dropped it. Two-way
comparison cannot tell them apart. `chromedrift provenance` can, by comparing
the fork against the series of upstream versions it was merged from: matching an
older version exactly means stale, not decided. Read that report alongside this
one.

## Bucket meanings

| Bucket | Uprev meaning | Fork meaning | Action |
|---|---|---|---|
| Must fix | We reference the symbol AND it changed | Divergence we depend on; a rebase undoes it silently | Assume work |
| Needs review | We touch the area, or severity is high enough to confirm | Divergence with no clear owner: keep ours, or take upstream's | Triage by hand |
| New opportunity | New capability | *Never used* — nothing in a fork comparison is an opportunity | Product decision |
| FYI | Recorded for completeness | Same | Do not read line by line |

Only **symbol-level** evidence promotes a finding to Must fix. A path match
means "somewhere in a file we also touch" — `content_features.cc` declares
nearly 200 features, so patching it says almost nothing about which of them we
depend on.

## Scoring

Every finding lists the reasons behind its score, for example:

```
base severity 75 (modified base_feature)
  | +12 we patch 1 of the declaring file(s): content/public/common/content_features.cc
  | +30 our source references ServiceWorkerAutoPreload, kServiceWorkerAutoPreload
  | +16 owned area 'Browser UI' (weight 80)
```

Argue with the score when it is wrong. To change ranking permanently, edit
`BASE_SEVERITY` and `SIGNAL_SEVERITY` in `chromedrift/diff.py`, or the bonus
constants and `_bucket` in `chromedrift/impact.py`. Both are plain data, not
logic.
