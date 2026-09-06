---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions - feature flags, web APIs, prefs, switches, Mojo interfaces, chrome:// WebUI surfaces (routes, controls, visibility gates) - separating real behaviour changes from cleanup, and produces a ranked report of what moved. Use when planning or reviewing a Chromium upgrade such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when asked whether a Chromium change breaks anything, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
---

# Analyzing Chromium upgrades

Run `chromiumdiff` over two Chromium versions, then classify what it found and report the part the reader asked for. The tool ranks; deciding what a change means for a particular product is the job this skill describes.

**A changed declaration does not mean changed behaviour.** The tool reads declarations only, so what it files against each row is *a classification made from what that run happened to read*, not a settled conclusion about the world.

This skill re-checks that classification with context the tool does not have. It is wrong in two opposite directions: **reporting a change no user ever sees**, and **passing over a harmless-looking row that breaks something with nothing to warn you**.

## Vocabulary

These words run through the rest of the skill and through `report.json`.

- **finding and change** — a `finding` is one row of the report, an element of the `findings` array in `report.json`. Inside it, `change` holds the declaration that moved: `kind`, `signals`, `locations`, `before`, `after`.
- **signal** — a label saying why this change matters, carrying a severity floor. A finding may hold several; the one with the highest floor decides, and the report both groups and headlines the finding by it. In `change.signals`. What each one means: **[reference/signals.md](reference/signals.md)**.
- **severity and score** — severity is what that kind of change costs, decided by the signal. Score is severity after two deductions: not in the Windows build on either side → 0; unconfirmed removal → −15. Nothing raises a score, so a score below its severity always carries a sentence in `reasons` — quote the sentence, not the number.
- **bucket** — what kind of thing happened, decided by the same signal. There are exactly four, and every finding is in one:

| Bucket | Means |
|---|---|
| **Breaking** | Something outside the binary stops working, and nothing warns you: stored user data, launch scripts, Finch configs, live websites, the other process |
| **Behaviour change** | The Windows build behaves differently after this. Someone can see the difference |
| **New surface** | Surface that did not exist before. Nothing is switched on by it on its own |
| **Housekeeping** | Chromium tidying up after itself, and scheduling. Nothing observable moved, or the tool cannot tell that anything did |

## Two groups of declaration

The tool's sixteen `kind`s fall into two groups, and they differ in **whether anything stands between a change in the code and a user**. Which group decides which question to ask. Ask the wrong one and the conclusion is wrong.

Read the finding's `change.kind` and look it up here before analysing it.

| Group | `change.kind` | Standing between code and user |
|---|---|---|
| **1 — flag-gated** | `base_feature`, `blink_runtime_feature`, `flag_entry`, `webui_route`, `webui_control`, `webui_gate` | the flag's default, per platform |
| **2 — no gate** | `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`, `pref`, `switch`, `feature_param` | nothing |
| **1 or 2** | `idl_interface`, `idl_member` | `[RuntimeEnabled]` on the member or its interface, if present. Without it, read as group 2 |

### Group 1, flag-gated — a change in the diff usually is not a change

Code moves through three stages, usually milestones apart:

1. new code merges into Chromium with the flag off — users see nothing
2. the flag is switched on — **this is the change**
3. the flag is deleted — users see nothing

A diff mostly shows stages 1 and 3, which are the two nobody sees.

**Do this: read `platform_state.windows` first.** Until you have read the flag state you may not write "X changed".

Getting this group wrong produces: a reported change no user ever saw.

### Group 2, no gate — a change in the diff always is a change

There are no stages. The declaration is the contract, and it changes the moment the new version is adopted, with nothing to warn you:

- both ends of a Mojo interface are generated from the same file, so a changed signature never breaks the build
- Chromium ignores an unrecognised command-line switch and reports nothing
- a removed feature parameter leaves the Finch config setting it exactly as before, only with no effect

**Do this: do not go looking for a flag. A changed declaration is already the breakage.**

Getting this group wrong produces: a conclusion that nothing happened, while something broke and nobody was told.

### Reading Breaking, default to the group 2 question

This is a property of the signal table rather than of one run: every `ipc_*`, `pref_*`, `switch_*` and `param_*` signal — most of what files a finding under Breaking — comes only from a group 2 declaration. Group 1 reaches Breaking in a few rare cases, a renamed `base::Feature` or a `webui_control` repointed at another pref, but never through a flag being flipped.

The counts move with the version pair, so do not carry one pair's numbers to another. At M148 → M151, for instance: 181 of 276 Breaking rows are group 2, 94 are Web IDL and depend on `[RuntimeEnabled]`, 1 is group 1. **What does not move is the default: reading Breaking, ask the group 2 question first.**

## Workflow

```
- [ ] 1. Ask the reader: which two versions, and how deep a read
- [ ] 2. Run chromiumdiff
- [ ] 3. Read the report in order
- [ ] 4. Ask why a row changed — when someone asks; re-render afterwards
- [ ] 5. Read each finding with the question for its kind
- [ ] 6. Write the report around what the reader asked for, with limits
```

### Step 1: Ask, then run

**Ask the three questions below before running anything.**

**Question 1 — which two versions?** A bare milestone number works: the tool resolves `151` to that milestone's newest stable release as of today. But then the same command run on two different days can give two different answers — `ServiceWorkerAutoPreload` is ENABLED in 143.0.7499.40 and DISABLED in 143.0.7499.194, two stable releases of milestone 143. The versions actually used are in `from_ref` and `to_ref` in `report.json`; quote the report from there, not the number the reader gave you.

**Question 2 — how deep a read?** Readers do not generally know what a "target set" is, so ask about what they get rather than about the option name:

| What the reader needs | Use | Trade |
|---|---|---|
| A quick look at what moved | `default` — the tool's default | Reads under half the files. A declaration that "vanished" may only be in a file this run never opened |
| To decide whether this upgrade can ship | `wide` | Reads nearly the whole tree. Much heavier to fetch and much slower, and in exchange a removal is worth believing |
| To know whether the tool runs at all | `minimal` | Reads 3 files. Never use it to answer a question about content |

Costs per level are in the table in step 2.

**Question 3 — which part do they want?** Nobody reads all of it: a version pair produces thousands of rows. Ask what the reader cares about and filter to that instead of handing over the whole report.

Ask in terms they can answer, then map it onto one of the three axes the report can filter on:

| Reader says | Filter on |
|---|---|
| "only what breaks" | bucket `Breaking` |
| "the Mojo side", "web APIs", "the settings pages" | `change.kind` |
| "what switches behaviour", "contracts with the outside" | consequence group — the *What happened* section of `report.md` |

If the reader is a person, **hand them the `serve` URL**: the page has four multi-select filters (bucket, surface, consequences, evidence) plus a box for terms to exclude. They will pick faster than any question gets asked.

**The platform is always Windows.** The tool always compares for Windows and no option changes that — `meta.platform` in `report.json` records `windows`. A flag's state is at `change.before.platform_state.windows` and `change.after.platform_state.windows`. Beside them sits `default_state`: that is Chromium's overall default rather than the Windows one, and reading it by mistake is the most common error at this step.

**Anything else missing, ask; do not fill it in.**

### Step 2: Run

Run every command **from the root of the `chromiumdiff` repository**: `python3 -m chromiumdiff` has to import the package, and anywhere else it reports `No module named chromiumdiff`. Every path below is relative to that root.

```bash
python3 -m chromiumdiff check          # verify machine, network, cache

python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

Pure Python 3.9+ stdlib, no install, no Chromium checkout. About three and a half minutes cold for a pair; half a second cached.

| `--target-set` | Fetched per version | Files read |
|---|---:|---|
| `minimal` | ~1 MB | 3 |
| `default` | ~40 MB | under half the files, over half the flags |
| `wide` | ~337 MB | **nearly the whole tree** |

The run writes three files into the `--out` directory you gave it:

```
out/M148_to_M151/report.md      paste into a ticket
out/M148_to_M151/report.html    open in a browser, filterable
out/M148_to_M151/report.json    the data to script against
```

Every command after this — `serve`, `report`, `why.py` — takes **that directory or the `report.json` itself**, never the parent. `serve out` reports `no report.json in out`.

The three files carry three different things, and **signal ids are only in `report.json`**:

| What you need | `report.md` | `report.html` | `report.json` |
|---|---|---|---|
| signal ids (`pref_left_scan`, `ipc_shape_changed`…) | absent — it prints labels, e.g. *Mojo data shape changed (ABI)* | only inside the filter | `change.signals` |
| a row's bucket | implied by the section | yes | `bucket` |
| `platform_state`, score, severity, `path:line` | yes | yes | yes |

**Filtering or branching on a signal means reading `report.json`.** `report.md` is the artifact for a reader, `report.html` plus `serve` is the one for someone clicking.

Fetched Chromium source lives in `.chromiumdiff-cache/` at the repository root, moved with `--cache` or the `CHROMIUMDIFF_CACHE` environment variable. It is regenerable — deleting it only makes the next run slower. `check` prints the cache directory, the free space and what a version pair costs.

Every finding cites `path:line` under `change.locations` — quote it, never paraphrase the file name.

**`report.html` alone answers *what* changed, never *why*.** Opened as a file it is a complete, offline table; the per-row "why did this change" lookup cannot run there, because a page on `file://` may not call `chromium-review.googlesource.com` and the browser blocks it before it is sent. Serving the directory changes who asks — the page calls localhost, and Python asks Gerrit:

```
python3 -m chromiumdiff serve out/M148_to_M151     # prints http://127.0.0.1:8787/
```

Offer this whenever someone asks why a row changed, what a flag was for, or which review to read. You can start it yourself and hand over the URL. Opening `report.html` directly and concluding the lookup is broken is wrong: it does not run because of `file://`, not because of a fault.

**The tool does not conclude for you.** It stops at extracted evidence and a deterministic rank. It knows nothing about what anyone patches, ships or overrides: a **Breaking** row says a contract moved, not that anyone was relying on it.

**Every run prints the coverage it achieved.** Quote that number in the report; never quote one from this file.

```
coverage: reads N of M files in this tree that could declare (P% of files)
```

**Coverage changes the answer, not just the confidence.** A removal is an inference from absence, so on a partial read it loses 15 points and a `pref_left_scan` is filed as Housekeeping rather than Breaking. Measured on M148 → M151: `default` finds 139 of these and `wide` finds 171 — but only 30 of them are in the Windows build at all, and it is those 30 that move from Housekeeping at 20 points to Breaking at 35 when the run is `wide`. The rest score 0 either way. **`Breaking: 0` on a default run does not mean nothing is broken.**

**Two error messages, one cause.** `cannot diff snapshots built from different target sets` and `cannot diff: X holds N facts against Y's M` both say one side read a fraction of the other. Neither is a bug to work around: check that `--local-src` / `--from-src` / `--to-src` points at a full Chromium `src/`.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`, `extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`, `media`) fetches and scans only the source paths listed for one feature. Right while looking at one feature, wrong as a release gate — Chromium does not organise its source by feature, so a change affecting downloads can live in `content/` and match no partition.

Two side commands: `chromiumdiff catalog <ref>` measures what the target set is missing; `chromiumdiff figures <report.json>` writes the measurements the project's own documents quote, which is how they stay true. The re-render command is in step 4, beside the reason you need it.

### Step 3: Read the report in order

The report arrives sorted by score, highest first. **That is not a reading order, and it is not a place to cut.** A Breaking row the run could not confirm loses 15 points and drops below thousands of New surface and Housekeeping rows. Measured at M148 → M151: reading the top 100 by score misses 232 of 276 Breaking rows; reading 500 still misses 55. Score orders rows inside a bucket; it does not decide how far to read.

When the list is long, **group by signal** rather than truncating: at that pair, Breaking plus Behaviour change plus New surface is nearly 2,000 rows but only about 40 distinct signals. Looking at each signal group once covers all of it.

Read by bucket, in this order.

1. **What kind of change** — the per-bucket counts at the top of `report.md`. Start here; it says how long each list is.
2. **What happened** — every finding grouped under the signal that set its severity, so a report of thousands of rows collapses to a few dozen groups.
3. **Breaking**, then **Behaviour change**, then **New surface**.
4. **Housekeeping**: skip, except for two filters to run before closing it. This is not the "low score" bucket — at M148 → M151 it holds rows at 45, above every row in New surface. Neither id below appears in `report.md`; filter on `report.json` or with the `report.html` filter.
   - `flag_expiring` — `chrome://flags` entries Chromium has scheduled for deletion, the only rows about work that has not happened yet.
   - `pref_left_scan` and `switch_left_scan` — removals this run could not confirm. They are in Housekeeping because they are **unconfirmed**, not because they are minor. Step 5, the *Flags, prefs and switches* branch, says what to do with them.

Retired flags are in Housekeeping too, and deliberately: at M148 → M151 there were 132 of them, 72 that had shipped and 60 abandoned, none user-visible. Reporting one as a lost feature is wrong — read [reference/traps.md](reference/traps.md) before concluding.

### Step 4: Ask why a row changed

Expanding a row in the served page looks up the review that made the change. It reads the CLs that touched the declaring file inside the milestone window, then keeps the ones a diff ties to *this* identifier — a declaration file is shared, and 500 merged CLs touched `about_flags.cc` between M148 and M151, so the file alone answers nothing.

What comes back is a CL, the issue that CL cites, and the other CLs that cite the same issue — the fix history of the bug behind the change. Each CL carries the verdict that put it there, and the verdicts are never merged into a score:

| Verdict | What it claims |
|---|---|
| `introduced` | **inside this declaration**, a line gained the value the declaration ends up with or lost the one it started from — the CL *is* the change |
| `exact` | a line the CL changed carries the identifier |
| `moved` | the file was renamed and the declaration came with it; no line changed |
| `declares` | the CL edited the declaration's body, not the line naming it |
| `described` | the CL's own title or description names it; no diff was read |
| `crowded` | several CLs edited this declaration, so none singles it out — read as that declaration's history, oldest first |
| `touched` | nothing matched the identifier; these merely touched the file |

The last two name no declaration. Never quote them as the cause; say what they are.

Lookups are written back to `report.json`, so they survive a restart. They reach `report.md` and `report.html` only on a re-render, which `serve` does not do for you — it prints the command when you stop it:

```bash
python3 -m chromiumdiff report out/M148_to_M151/report.json --format both --out out/M148_to_M151/report
```

Do that before quoting a report to anyone: what you found by clicking is in the JSON, and the two files on disk are still the ones the run wrote.

`--click-budget N` caps diffs read per row (default 600), `--no-save` leaves the file alone. An issue's history is not fetched with the row: click the issue on the CL you believe, and it opens under that CL.

**A restricted issue is normal and not a failure.** Around four in ten linked issues answer HTTP 403 — they sit in a security, abuse or Google-internal tracker component. The panel says so and keeps the link, because the reader may be the one person who can open it. **The CLs stay readable either way**: they live on Gerrit, they are public, and their subjects say what the issue was about. Report the fix history rather than only that the issue would not open.

**Finding no CL means this search found none, not that Chromium did not change.** The two trees differ, so something landed. The file is asked three ways — on main, then off it for merge-backs, then the whole window's commit messages — and if all three miss, the CL is recorded under a name or path this report does not hold. Say that; do not report that a declaration changed by itself.

### Step 5: Read each finding with the question for its kind

Read the finding's `change.kind`, branch on the table below, then ask that branch's question.

**Mojo** — `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`

1. `platform_state.windows` — `not_compiled` already scores zero; `conditional` is undetermined, not ours-by-default. A declaration under `android/`, `ash/`, `chromeos/` or `ios/` carries no guard at all.
2. **Who is on the other side?** Both ends compile from the same tree, so this is a build break for out-of-tree code before it is a runtime break. Trap 10 in [reference/traps.md](reference/traps.md) lists when it is a runtime break. Say which applies.
3. `ipc_shape_changed` and `ipc_signature_change` break deserialization with no error. `ipc_enum_changed` is milder: an unknown value is rejected rather than misread.

**Web platform** — `idl_interface`, `idl_member`, `blink_runtime_feature`

1. **Can a page reach it?** `web_api_added_live` versus `web_api_added_gated`. `web_api_added` means the gating flag was outside what this run read — check before reporting either way.
2. `web_api_removed` breaks live sites; `web_api_removed_gated` reached no user.
3. `web_api_shipped` is the moment users get it.

**Flags, prefs and switches** — `base_feature`, `feature_param`, `pref`, `switch`, `flag_entry`

1. **Did the flag state change on our platform?** Read `platform_state`. `disabled → enabled` or the reverse is a real behavioural change. Stop.
2. **Did the flag disappear?** Read the state it held *before*. `flag_retired_on` / `flag_retired_off` mean behaviour did not change here.
3. **Is the disappearance confirmed?** `pref_left_scan` / `switch_left_scan` mean "not in the files this run read". Search the tree for the key, or re-run `wide`, before reporting either outcome.

**chrome:// pages** — `webui_route`, `webui_control`, `webui_gate`

1. **Follow the guard to its flag.** A control or page that vanished usually moved behind a different guard, and the user-visible change happened when that flag flipped. Traps 2 and 6 in [reference/traps.md](reference/traps.md).

**Fixed outside the repository** — this branch keys on the signal rather than the kind. All nine below compile perfectly and stop working in the field, and the edit that fixes them is in a Finch config, a launch script or automation rather than in the declaring file:

`feature_string_renamed`, `switch_renamed`, `param_removed`, `param_rewired`, `flag_retired_on`, `flag_retired_off`, `killswitch_retired`, `flag_expiring`, `flag_expiry_moved`

1. **Always actionable if the old name appears anywhere.** The first four kill whatever was setting the value from outside. The next three are retired flags, which silently make every external override a no-op. The last two are scheduling: a flag with a deletion date is an override with a deadline.
2. The tool cannot see any of those places. This is a list of things to check, not a list of things that broke.

Signal meanings: **[reference/signals.md](reference/signals.md)**.

### Step 6: Write the report around what the reader asked for

Question 3 decides the layout — group by what the reader named, and say what you filtered to. The template below is the default when they named nothing: grouped by the branches of step 5.

```markdown
## Overall risk
[One sentence on risk, and which branch carries most of it.]

## Mojo — N to look at
## Web platform — N
## Flags, prefs and switches — N
## chrome:// pages — N
[Skip a section with nothing in Breaking or Behaviour change, and say so.]

## Fixed outside the repository — N
[Always present, always last, even when filtered: a renamed flag or switch kills the override of anyone who set it, not of one team.]

## New capability
[web_api_added_live only. Product input, not a blocker.]

## Limits
[Coverage figure the run printed, target set, partitions, exact versions.]
```

Every finding needs three parts: **what moved**, **whether users see a difference**, **what someone must do**. The middle part decides priority and a raw diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."*

Good: *"Local Network Access moved to split permissions. The flag was ENABLED at M148, so users saw this before our current base; M151 only retires the flag. No behavioural change. Action: update any reference to `kLocalNetworkAccessChecksSplitPermissions` or the `/localNetworkAccess` route."*

## Reference

- **[reference/traps.md](reference/traps.md)** — the ways to reach a wrong conclusion, each one measured against real Chromium data. Read before interpreting any removal; the later traps cover Mojo, web APIs and switches.
- **[reference/signals.md](reference/signals.md)** — what each signal means.
- **[reference/settings-surface.md](reference/settings-surface.md)** — the three-hop chain from a settings page to the flag behind it, and how to size a "feature".

## What the tool cannot see

State these in every report. A clean report does not imply a clean upgrade.

- **Whether any of it touches a particular product.** The tool compares Chromium against Chromium. Searching your own tree for the identifier a finding cites is the step that answers "does this affect us".
- **Implementation-only changes.** It reads declarations. Behaviour changed inside a function body is invisible.
- **Five classes of declaration it does not turn into facts**, in files it otherwise reads completely. Measured at M151: 85 Web IDL `callback` definitions, 144 `typedef`s, 200 `Interface includes Mixin` relations, 18 Mojo `feature` blocks and 311 Mojo constants. Real examples that produced no row: `typedef LanguageModelMessageValue` changing its underlying union at M143 → M147, and the Mojo constant `kWebNNDirectML` disappearing at M151. **"Reads 99% of the files" is a statement about files, not about grammar.**
- **Anything outside the repository** — Finch configs, launch scripts, test automation, enterprise policy, store metadata.
- **Chrome Extensions IDL and MIDL.** Only Blink's own `.idl` is read.
- **Page behaviour.** Only the declarative parts of a WebUI surface: the route table and the HTML templates, not the TypeScript.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

Use flags and declarations to *discover*, targeted code reading to *explain*, screenshots only to *confirm* a short list. Do not use screenshots to discover changes.
