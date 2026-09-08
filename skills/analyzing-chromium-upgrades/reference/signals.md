# Signal reference

A finding may carry signals, or none at all. Signals describe the deterministic
classifier's interpretation of the declarations this run read. Use them to
choose questions, then verify source, consumers and conditions before making
behaviour or product-impact claims. They are not a discovery allowlist.

One of them is the **leading signal** — the one with the highest severity — and
it does two jobs: it sets the finding's severity, and it decides which of the
five buckets the finding is filed under. So the sentence a row is filed by is
always the sentence it was ranked by.

## Contents

- Behaviour changed
- Behaviour unchanged (cleanup)
- Silent breaks
- Structural
- Bucket meanings
- Scoring

## Behaviour changed

These signals identify potential behaviour/contract changes to investigate.

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
| `web_api_overload_shadowed` | A member gained an overload taking an argument count another already took. Web IDL resolves by count first, so a call that used to reach the older one can now reach the new one — nothing removed, nothing edited at the call site |
| `web_api_overload_added` | A member gained an argument list. Every existing call still matches the overload it always did, so this is purely additive |
| `web_api_signature_change` | An IDL member's signature moved; existing call sites may not match |
| `ipc_signature_change` | Mojo method signature moved. Check out-of-tree callers and mixed-version peers before claiming build/runtime impact |
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

These are cleanup hypotheses based on declaration state. Inspect retained and
removed consumers to establish the actual behaviour. Check external overrides
and code naming removed symbols independently.

| Signal | Meaning |
|---|---|
| `flag_retired_on` | Flag removed after an enabled source default; verify whether its enabled branch was retained |
| `flag_retired_off` | Flag removed after a disabled source default; verify whether implementation was removed or replaced |
| `killswitch_retired` | Blink runtime equivalent of `flag_retired_on` |
| `experimental_dropped` | Experimental Blink flag abandoned |
| `feature_deleted` | Flag removed but its prior state could not be determined — investigate manually |
| `declaration_moved` | Declaration moved to another file; nothing else changed |

Measured evidence for why this distinction exists:

- **M148 → M151, Windows**: 154 `base::Feature` flags removed — 72
  `flag_retired_on`, 60 `flag_retired_off`, and 22 `feature_deleted` whose
  prior state could not be read. These labels alone do not establish whether
  a capability was deleted.
- **M139 → M143, Blink**: of 202 runtime features that disappeared, **167 had
  been `stable`** — retired after shipping, not removed capability.

That is also why all three retirements are filed under **Upstream cleanup**
rather than under Compatibility break. It is the most consequential row in the
bucket table: put them in Compatibility break and half of that bucket is noise
on every run.
`feature_deleted` is the exception and goes to **Behaviour change**, precisely
because the tool could not read the prior state and so cannot rule one out.

## Silent breaks

These can affect external consumers and persisted state. Establish which
consumer still relies on the old contract and whether a migration exists.

| Signal | Meaning |
|---|---|
| `feature_string_renamed` | The Finch feature name changed. Server-side field trials and `--enable-features` using the old spelling silently stop matching |
| `feature_symbol_renamed` | The mirror image: the C++ identifier changed while the feature string held. Code writing `features::kOldName` stops compiling. It fails loudly rather than silently, but only after the merge |
| `pref_renamed` | A preference key changed; check migrations and consumers before claiming stored values reset |
| `switch_renamed` | Command-line switch renamed. Launch scripts and automation stop taking effect |
| `pref_symbol_renamed` | The key held; its C++ constant was renamed. Stored values are safe, but code writing `prefs::kOldName` stops compiling after the merge |
| `switch_symbol_renamed` | Same for a switch: launch scripts keep working, a build against it does not |
| `param_removed` | A feature parameter is gone. Anything still setting it — a Finch config most often — silently stops having an effect |
| `param_rewired` | The parameter itself moved rather than its value: a different C++ type, or a different owning flag. Code reading it with the old type stops compiling |
| `ui_control_repointed` | The control binds a different preference; inspect migration and other readers of the old key |
| `ipc_stability_changed` | A Mojo declaration gained or lost `[Stable]`. Mojo promises wire compatibility for a stable declaration and nothing for the rest, so this is the compatibility promise changing, not the bytes |
| `ipc_field_annotated` | A Mojo field's default value or its `[MinVersion]` annotation moved. Every byte on the wire is still read as the thing it is, but what an **older** peer sees changes — which is why this is a behaviour change rather than a break |

Always check these against things the tool cannot see: Finch configs, launch
scripts, CI automation, QA harnesses.

### Disappeared, cause unknown

| Signal | Meaning |
|---|---|
| `pref_left_scan` | A preference key is no longer in any file this run read. It was either deleted — orphaning every user's stored value — or moved into a file outside the scan |
| `switch_left_scan` | Same, for a command-line switch |

**These two do not say which of the two happened, and that is what the row reports.**
Chromium is actively splitting `chrome/common/pref_names.h` apart: 4,322 lines
at M143, 3,267 at M151. Measured across M143 → M148 → M151 that produced **337
disappearances**, and on the default target set the tool reads 1 of the ~100
non-ChromeOS `pref_names.h` files.

**How much of the tree the run read decides how these are filed.** A run that
read the whole tree can call a disappearance a disappearance, so they are filed
under **Compatibility break** at full severity. A run that did not is filed
under **Upstream cleanup** with 15 points off and carries `unconfirmed`, and
the finding says so in its own
reasons. Measured on the same pair of versions: `default` reads 43% of the tree and
finds 139 of these, `wide` reads 99% and finds 171. Only 30 are in the Windows
build on either side, and it is those 30 that move from Upstream cleanup at 20
points to Compatibility break at 35; the rest score 0 whichever set is used.

Resolve one by searching the exact target version for the key and its consumers.
A declaration elsewhere suggests a move; evaluate callers and build conditions.
Absence needs adequate source coverage, and data loss needs migration/consumer
evidence. Do not infer either from a partial scan or a bucket label.

## Structural

| Signal | Meaning |
|---|---|
| `web_api_added_live` | New web API a page can call on arrival — nothing gates it, or the flag gating it already reached stable |
| `web_api_added_gated` | New web API still behind a runtime flag whose status is not stable. Stage A: the code shipped, nothing can reach it yet |
| `web_api_added` | New web API whose gate names a flag this run did not read. Undecided rather than guessed — a `default` run reads a third of the flags |
| `ui_page_added` / `ui_page_removed` | A chrome:// page appeared or disappeared. **Check its guard before concluding** — see traps.md |
| `ui_page_regated` | A recorded route guard changed; compare complete expressions and consumers to establish visibility |
| `ui_page_moved` | The page's URL or parent route changed |
| `ui_control_type_changed` | A control changed type, e.g. dropdown became a toggle |
| `ui_control_added` / `ui_control_removed` | A control appeared or disappeared on a page |
| `ui_gate_changed` / `ui_gate_removed` / `ui_gate_added` | The condition deciding a page's visibility moved, went away, or appeared |
| `new_feature_on_by_default` | New flag, already on |
| `param_default_changed` | A feature parameter default moved; behaviour tuning |
| `flag_expiring` | chrome://flags entry scheduled for removal in an upcoming milestone — filed under **Scheduled**, because it is about work that has not happened yet rather than work that has |
| `flag_expiry_moved` | The removal date moved further out. Scheduling on a settings page, not a feature change — the largest single group in most reports |
| `build_gate_changed` | The `#if` or GRIT `<if>` around a declaration moved, so it may no longer be in the binary we ship |
| `origin_trial_change` | Origin trial wiring changed: who may turn the feature on from outside the binary |
| `web_api_exposure_changed` | An IDL extended attribute or the `[RuntimeEnabled]` flag gating a member moved: who can reach the API changed |
| `web_api_shape_changed` | An interface's inheritance or an enum's member list moved |
| `web_api_status_moved` | A Blink flag moved between `test` and `experimental`. Never reached stable, so users see nothing |
| `runtime_flag_rewired` | Recorded dependencies or base-feature wiring changed. `base_feature: none` declares no generated base-feature link; it does not prove another C++ flag was deleted |
| `ui_control_relabelled` | A control's label key changed. The tool reads the key, never the display string — that lives in a `.grd` it does not open — so it cannot say whether anyone sees a difference |

Everything the comparison treats as meaningful produces one of these rows. This
is enforced by a test: an attribute is in `MEANINGFUL_ATTRS` because a change
to it was decided to matter, so a change to it that
arrives with a severity and a blank reason column is unreadable — the reader has
to open the source to find out what moved. Measured M148 → M151, **380 of 709
modified changes used to arrive that way**; a test now asserts none do.

A change can also carry **no signal at all**, and about a third of a report
does: 981 of 3,022 findings at M148 → M151, almost all of them things that
simply appeared. Direction and kind summarize those observations, but their
meaning still needs investigation. Unsignalled additions can establish a new
capability alongside other declarations or implementation changes.

## Bucket meanings

Five buckets, decided by the leading signal, and every one of them is a
statement about the change rather than about the reader.

| Bucket | Meaning | Action |
|---|---|---|
| Compatibility break | A contract outside the binary no longer holds, and nothing at build time warns you: stored user data, launch scripts, Finch configs, live websites, the other process | Find every place that names it |
| Behaviour change | The Windows build behaves differently. Someone can see a difference | Confirm what the difference is |
| New declarations | A declaration exists in the new version that did not exist in the old. Nothing is switched on by its existence | Product input, not a blocker |
| Scheduled | A removal date, not a removal. Chromium has scheduled something for deletion or moved the date. Nothing has happened yet | Plan for the next milestone; nothing to do in this one |
| Upstream cleanup | Classifier hypothesis of cleanup or platform exclusion; can also contain insufficient absence evidence | Account for these items too; verify consumers and `unconfirmed` before dismissing |

Three rules make these hold together, and all three are tested:

- **Every signal names exactly one bucket**, so nothing falls through to a
  default. A signal missing from the table would be filed by "something was
  removed" rather than by what the removal was.
- **A finding is filed under the sentence it is ranked by.** The leading signal
  sets the severity and picks the bucket, so a row cannot be headlined *Flag
  scheduled for removal* while having been ranked as *Shipped, then flag
  retired*.
- **No word names two things on the page.** A row shows five naming
  vocabularies side by side — bucket, kind, kind group, column header, filter —
  so a word used in two of them names two things at once. Two nouns are
  also spoken for outside those: `surface` is the body of declarations coverage
  is measured over, and `screen` is the `chrome://` screen a WebUI fact sits
  on. Neither may be used as a label.

## Evidence is not a bucket

Whether the run confirmed the absence a finding rests on is a property of the
**run**, not of the change: the same removal is unconfirmed on a `default` run
and confirmed on a `wide` one. So it is a field, `unconfirmed`, and not a sixth
bucket.

Every row carries it in `report.json`. `report.html` shows it as an outlined
badge beside the bucket pill with an `All evidence` filter over it, offered
only when at least one row has it. `report.md` gives them a section of their
own, because they sit in Upstream cleanup and that is the one bucket with no
table.

It is set wherever the 15-point deduction is, not only where the filing moves,
so it is not confined to Upstream cleanup: 303 rows carry it at M148 → M151 on
the default target set and **0 on the wide one**, 120 of them in Compatibility
break. That number is the answer to "how much of this report is limited by what
the run read rather than by what Chromium did".

`summary.unconfirmed` in `report.json` holds the count.

## Scoring

Two numbers. Every point of gap between them has a sentence beside it.

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
-15 unconfirmed: this run read 2% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    upstream cleanup rather than a compatibility break — --target-set wide
    settles it
```

Argue with the score when it is wrong. To change the ranking permanently, edit
`SIGNAL_SEVERITY`, `BASE_SEVERITY` or `SIGNAL_BUCKET` in `chromiumdiff/diff.py`,
or the two constants in `chromiumdiff/score.py`. All of them are plain data, not
logic.
