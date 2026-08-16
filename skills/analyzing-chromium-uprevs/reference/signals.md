# Signal reference

Every finding carries one or more signals. The signal, not the score, tells you
what actually happened. Read this column first.

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
| `android_enabled_by_default` | Now ON by default on our platform |
| `android_disabled_by_default` | Now OFF by default on our platform |
| `default_flip_on` | Global default flipped on |
| `default_flip_off` | Global default flipped off — usually a rollback |
| `web_api_shipped` | Web API reached stable; sites will start using it |
| `web_api_unshipped` | Web API pulled back from stable — rare, investigate |
| `web_api_removed` | Real API removal, detected from IDL. Site-visible break |
| `ipc_signature_change` | Mojo method signature moved. Breaks across the process boundary at runtime, not at compile time |
| `ipc_removed` | Mojo interface or method removed |

The platform-named signals are computed for the platform passed via
`--platform`. A feature can flip on desktop and stay put on the platform you
ship, or the reverse.

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
| `pref_renamed` | A preference key changed. Every existing user's stored value is orphaned and the setting quietly resets |
| `switch_renamed` | Command-line switch renamed. Launch scripts and automation stop taking effect |
| `origin_trial_change` | Origin trial wiring changed |

Always check these against things the tool cannot see: Finch configs, launch
scripts, CI automation, QA harnesses.

## Structural

| Signal | Meaning |
|---|---|
| `web_api_added` | New web API surface — test coverage, possible adoption |
| `new_feature_on_by_default` | New flag, already on |
| `param_default_changed` | A feature parameter default moved; behaviour tuning |
| `flag_expiring` | chrome://flags entry scheduled for removal in an upcoming milestone — future forced work |

## Bucket meanings

| Bucket | Meaning | Action |
|---|---|---|
| Must fix | We reference the symbol AND it changed | Assume work |
| Needs review | We touch the area, or severity is high enough to confirm | Triage by hand |
| New opportunity | New capability | Product decision |
| FYI | Recorded for completeness | Do not read line by line |

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
