# Signal reference

Every finding carries one or more signals. The signal, not the score, tells you
what actually happened. Read this column first.

One of them is the **leading signal** — the one with the highest severity — and
it does two jobs: it sets the finding's severity, and it decides which of the
four buckets the finding is filed under. So the sentence a row is filed by is
always the sentence it was ranked by.

## Contents

- Behaviour changed
- Behaviour unchanged (cleanup)
- Silent breaks
- Structural
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
| `web_api_removed` | Real API removal, detected from IDL, and a page could still reach it. Site-visible break |
| `web_api_removed_gated` | Removed while still behind a closed runtime flag — no page could call it, so this is the web API spelling of `flag_retired_off`. 32 of 77 removals at M148 → M151 |
| `web_api_overload_removed` | A member kept its name and lost one of the argument lists it accepted. Deduplication used to hide this — the surviving declaration was unchanged, so nothing was reported |
| `web_api_overload_added` | A member gained an argument list. Every existing call still matches the overload it always did, so this is new surface |
| `web_api_signature_change` | An IDL member's signature moved; existing call sites may not match |
| `ipc_signature_change` | Mojo method signature moved. Breaks across the process boundary at runtime, not at compile time |
| `ipc_ordinal_changed` | A Mojo method's explicit ordinal moved. The far side routes by that number, so the message now reaches a different method or none — no build error, no signature change |
| `ipc_shape_changed` | The data half of the same break: a struct field changed type or ordinal, or a struct became a union. The other process reads those bytes as something else |
| `ipc_enum_changed` | A Mojo enum gained or lost a member. Lower severity on purpose — a peer that does not know a value **rejects** the message rather than misreading it |
| `ipc_removed` | Mojo interface, method, struct, field or enum removed |

The first two are resolved for Windows specifically, by walking the `#if
BUILDFLAG(...)` chain around the declaration. The global default and the
Windows default routinely disagree, which is why `default_flip_*` and
`enabled_by_default` are separate rows: the first says what Chromium wrote, the
second says what our users get.

## Behaviour unchanged (cleanup)

The largest group in a typical report, and the most misread. **None of these
changes what anybody sees.** They matter only to something that was setting the
flag from outside the binary — a server-side Finch config, an
`--enable-features` command line — which silently stops having an effect.

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

That is also why all three retirements are filed under **Housekeeping** rather
than under Breaking. It is the single most consequential row in the bucket
table: put them in Breaking and half of it is noise on every run.
`feature_deleted` is the exception and goes to **Behaviour change**, precisely
because the tool could not read the prior state and so cannot rule one out.

## Silent breaks

Compile cleanly, pass tests, fail in the field. The most expensive class to
discover late, because nothing warns you.

| Signal | Meaning |
|---|---|
| `feature_string_renamed` | The Finch feature name changed. Server-side field trials and `--enable-features` using the old spelling silently stop matching |
| `feature_symbol_renamed` | The mirror image: the C++ identifier changed while the feature string held. Code writing `features::kOldName` stops compiling. Loud rather than silent, but only after the merge — which is the point of seeing it now |
| `pref_renamed` | A preference key changed. Every existing user's stored value is orphaned and the setting quietly resets |
| `switch_renamed` | Command-line switch renamed. Launch scripts and automation stop taking effect |
| `pref_symbol_renamed` | The key held; its C++ constant was renamed. Stored values are safe, but code writing `prefs::kOldName` stops compiling after the merge |
| `switch_symbol_renamed` | Same for a switch: launch scripts keep working, a build against it does not |
| `param_removed` | A feature parameter is gone. Anything still setting it — a Finch config most often — silently stops having an effect |
| `param_rewired` | The parameter itself moved rather than its value: a different C++ type, or a different owning flag. Code reading it with the old type stops compiling |
| `ui_control_repointed` | The control now writes a different preference; the old one is orphaned, exactly as in a rename |
| `ipc_field_annotated` | A Mojo field's default value or its `[MinVersion]` annotation moved. Every byte on the wire is still read as the thing it is, but what an **older** peer sees changes — which is why this is a behaviour change rather than a break |

Always check these against things the tool cannot see: Finch configs, launch
scripts, CI automation, QA harnesses.

### Disappeared, cause unknown

| Signal | Meaning |
|---|---|
| `pref_left_scan` | A preference key is no longer in any file this run read. It was either deleted — orphaning every user's stored value — or moved into a file outside the scan |
| `switch_left_scan` | Same, for a command-line switch |

**These two are deliberately uncertain, and the uncertainty is the finding.**
Chromium is actively splitting `chrome/common/pref_names.h` apart: 4,322 lines
at M143, 3,267 at M151. Measured across M143 → M148 → M151 that produced **337
disappearances**, and on the default target set the tool reads 1 of the ~100
non-ChromeOS `pref_names.h` files.

**How much of the tree the run read decides how these are filed.** A run that
read the whole tree can call a disappearance a disappearance, so they are filed
under **Breaking** at full severity. A run that did not is filed under
**Housekeeping** with 15 points off, and the finding says so in its own
reasons. Measured on the same pair of versions: `default` reads 43% of the tree
and produces 139 of these in Housekeeping at 20 points; `wide` reads 99% and
produces 171 in Breaking at 35.

Resolve one by searching the current Chromium tree for the key string. Found
elsewhere means it moved and there is nothing to do; genuinely absent means
stored user data is orphaned, which is a real and silent break. Do not report
either outcome until you have looked.

## Structural

| Signal | Meaning |
|---|---|
| `web_api_added_live` | New web API a page can call on arrival — nothing gates it, or the flag gating it already reached stable |
| `web_api_added_gated` | New web API still behind a runtime flag whose status is not stable. Stage A: the code shipped, nothing can reach it yet |
| `web_api_added` | New web API whose gate names a flag this run did not read. Undecided rather than guessed — a `default` run reads a third of the flags |
| `ui_page_added` / `ui_page_removed` | A chrome:// page appeared or disappeared. **Check its guard before concluding** — see traps.md |
| `ui_page_regated` | The page is now shown under a different flag. The user-visible switch happened when that flag flipped, usually earlier |
| `ui_page_moved` | The page's URL or parent route changed |
| `ui_control_type_changed` | A control changed type, e.g. dropdown became a toggle |
| `ui_control_added` / `ui_control_removed` | A control appeared or disappeared on a page |
| `ui_gate_changed` / `ui_gate_removed` / `ui_gate_added` | The condition deciding a page's visibility moved, went away, or appeared |
| `new_feature_on_by_default` | New flag, already on |
| `param_default_changed` | A feature parameter default moved; behaviour tuning |
| `flag_expiring` | chrome://flags entry scheduled for removal in an upcoming milestone — **the one thing in Housekeeping worth looking up on purpose**, because it is about work that has not happened yet rather than work that has |
| `flag_expiry_moved` | The removal date moved further out. Scheduling on a settings page, not a feature change — the largest single group in most reports |
| `build_gate_changed` | The `#if` or GRIT `<if>` around a declaration moved, so it may no longer be in the binary we ship |
| `origin_trial_change` | Origin trial wiring changed: who may turn the feature on from outside the binary |
| `web_api_exposure_changed` | An IDL extended attribute or the `[RuntimeEnabled]` flag gating a member moved: who can reach the API changed |
| `web_api_shape_changed` | An interface's inheritance or an enum's member list moved |
| `web_api_status_moved` | A Blink flag moved between `test` and `experimental`. Never reached stable, so users see nothing |
| `runtime_flag_rewired` | The `base::Feature` behind a Blink flag, what it depends on, or its visibility changed. `base_feature: none` means the C++ flag that controlled it is gone |
| `ui_control_relabelled` | A control's label key changed. The tool reads the key, never the display string — that lives in a `.grd` it does not open — so it cannot say whether anyone sees a difference |

Everything the comparison treats as meaningful produces one of these rows. That
is a rule, not an aspiration: an attribute in `MEANINGFUL_ATTRS` was put there
because someone decided its movement means something, so a change to it that
arrives with a severity and a blank reason column is unreadable — the reader has
to open the source to find out what moved. Measured M148 → M151, **380 of 709
modified changes used to arrive that way**; a test now asserts none do.

A change can also carry **no signal at all**, and about a third of a report
does: 971 of 3,027 findings at M148 → M151, almost all of them things that
simply appeared. There the direction and the kind are the whole story, and the
report writes them as one — *New feature flag*, *Removed chrome://flags entry*.

## Bucket meanings

Four buckets, decided by the leading signal, and every one of them is a
statement about the change rather than about the reader.

| Bucket | Meaning | Action |
|---|---|---|
| Breaking | Something outside the binary stops working, and nothing warns you: stored user data, launch scripts, Finch configs, live websites, the other process | Find every place that names it |
| Behaviour change | The Windows build behaves differently. Someone can see a difference | Confirm what the difference is |
| New surface | Surface that did not exist before. Nothing is switched on by it on its own | Product input, not a blocker |
| Housekeeping | Chromium tidying up after itself, and scheduling. Nothing observable moved, or the tool cannot tell that anything did | Do not read line by line; filter it for `flag_expiring` |

Two rules make these hold together, and both are tested:

- **Every signal names exactly one bucket**, so nothing falls through to a
  default. A signal missing from the table would be filed by "something was
  removed" rather than by what the removal was.
- **A finding is filed under the sentence it is ranked by.** The leading signal
  sets the severity and picks the bucket, so a row cannot be headlined *Flag
  scheduled for removal* while having been ranked as *Shipped, then flag
  retired*.

## Scoring

Two numbers, and the gap between them is the whole point.

**Severity** is what this kind of change costs, and it comes from the leading
signal. When there is no signal, and only then, it comes from a coarse prior on
the kind and the direction. That order matters: the prior used to win whenever
it was higher, so a Mojo method whose mojom build condition moved was ranked 75
— identical to one whose signature moved — because `(mojo_method, modified)` is
75 and `build_gate_changed` is 35.

**Score** is that after two facts about this particular run:

- **A declaration Chromium keeps out of the Windows build on both sides scores
  zero.** It cannot move anything here. One that *enters or leaves* the build
  keeps its full severity — that is the change.
- **An unconfirmed removal loses 15.** See `pref_left_scan` above.

**Nothing raises a score.** Severity is the ceiling, and every point below it
has a sentence beside it on the finding:

```
severity 35 — Preference no longer in the file we read — it may have been
    deleted, orphaning stored values, or simply moved to one of the ~100
    pref files outside the scan
-15 unconfirmed: this run read 1% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    housekeeping rather than breaking — --target-set wide settles it
```

Argue with the score when it is wrong. To change the ranking permanently, edit
`SIGNAL_SEVERITY`, `BASE_SEVERITY` or `SIGNAL_BUCKET` in `chromedrift/diff.py`,
or the two constants in `chromedrift/score.py`. All of them are plain data, not
logic.
