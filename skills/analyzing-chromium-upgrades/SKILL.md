---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions - feature flags, web APIs, prefs, switches, Mojo interfaces, chrome:// WebUI screens (routes, controls, visibility gates) - separating real behaviour changes from cleanup, and produces a ranked report of what moved. Use when planning or reviewing a Chromium upgrade such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when asked whether a Chromium change breaks anything, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
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
- **bucket** — what kind of thing happened, decided by the same signal. There are exactly five, and every finding is in one:

| Bucket | Means |
|---|---|
| **Compatibility break** | A contract outside the binary no longer holds, and nothing at build time warns you: stored user data, launch scripts, Finch configs, live websites, the other process |
| **Behaviour change** | The Windows build behaves differently after this. Someone can see the difference |
| **New declarations** | A declaration exists in the new version that did not exist in the old. Nothing is switched on by its existence |
| **Scheduled** | A removal date, not a removal. Chromium has scheduled something for deletion or moved the date. Nothing has happened yet |
| **Upstream cleanup** | Chromium removed or moved something whose outcome was already settled, or the declaration is not in the Windows build on either side. Nothing observable moved |

- **unconfirmed** — a boolean on the finding, true when this run did not read enough of the tree to confirm the absence the row rests on. Not a bucket: the same change carries it on a `default` run and not on a `wide` one. Rows carrying it sit in Upstream cleanup because the evidence is short, **not because they are minor** — on a wide run they are compatibility breaks worth 15 more points. It is set wherever the −15 is, so it is not confined to Upstream cleanup: `summary.unconfirmed` counts 303 at M148 → M151 on the default set and 0 on the wide one, and 120 of those sit in Compatibility break.

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

### Reading Compatibility break, default to the group 2 question

This is a property of the signal table rather than of one run: every `ipc_*`, `pref_*`, `switch_*` and `param_*` signal — most of what files a finding under Compatibility break — comes only from a group 2 declaration. Group 1 reaches it in a few rare cases, a renamed `base::Feature` or a `webui_control` repointed at another pref, but never through a flag being flipped.

The counts move with the version pair, so do not carry one pair's numbers to another. At M148 → M151, for instance: 181 of 276 Compatibility break rows are group 2, 94 are Web IDL and depend on `[RuntimeEnabled]`, 1 is group 1. **What does not move is the default: reading Compatibility break, ask the group 2 question first.**

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
| "only what breaks" | bucket `contract` (**Compatibility break**) |
| "the Mojo side", "web APIs", "the settings pages" | `change.kind` |
| "what switches behaviour", "contracts with the outside" | consequence group — the *What happened* section of `report.md` |

If the reader is a person, **hand them the `serve` URL**: the page has up to five multi-select filters — bucket, kind, consequences, coverage, evidence — plus a box for terms to exclude. Coverage appears only when some row is unconfirmed, evidence only once a CL has been looked up. They will pick faster than any question gets asked.

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
| whether the run confirmed the absence | its own *Unconfirmed* section | badge on the row, `All coverage` filter | `unconfirmed`, and `summary.unconfirmed` |
| `platform_state`, score, severity, `path:line` | yes | yes | yes |

**Filtering or branching on a signal means querying `report.json` with a program.** `report.md` is the artifact for a reader, `report.html` plus `serve` is the one for someone clicking.

#### Only one of these fits in a context window

Measured on the M148 → M151 run in this repository:

| Artifact | Size | ≈ tokens | Read it how |
|---|---:|---:|---|
| `report.md` | 173 KB | **49k** | whole, top to bottom |
| `report.html` | 1.5 MB | 427k | in a browser, never in context |
| `report.json` | 4.1 MB | **1,200k** | only through a program |

A `wide` run raises the last one to about 2,052k. So `report.json` does not go into context — not with `cat`, not with `Read`, not by pasting a section of it. **Run Python over it and print the answer**, which is the only part that costs anything:

```python
import json, collections
R = json.load(open("out/M148_to_M151/report.json"))
F = R["findings"]
# Print the answer, never F itself.
print(collections.Counter(f["bucket"] for f in F))
print([f["change"]["name"] for f in F
       if "pref_left_scan" in f["change"]["signals"]][:20])
```

`grep` on it is worse than useless: the file is written on one line, so any match returns the whole 4 MB.

#### A reading order that costs about 34k

`report.md` is ordered so the first sections are the ones to write from. Read in this order and stop when the question is answered:

| Read | ≈ tokens | What it gives |
|---|---:|---|
| Header, *What kind of change*, *What happened* | 2k | the counts, and every signal group at once |
| *Related changes, grouped* | 1k | the items to write, already assembled |
| *What changed on each screen* | 2k | the per-screen items |
| *Compatibility break* | 18k | the rows to read closely — every signal in the bucket has one |
| *Behaviour change* | 11k | as above |

That is the whole story of a 3,022-finding run for about 34k, leaving the budget for the reasoning. The remaining sections — *New declarations*, *Scheduled*, *Unconfirmed* — are about 2k each and are read when the question calls for them.

**Where `report.md` truncates, query rather than open the file.** A bucket table gives each signal in that bucket its top few rows, heaviest signal first, then stops. Each screen stops at 12. Both print how many are hidden. One query returns the rest:

```python
[f["change"]["name"] for f in F
 if f["bucket"] == "contract" and f["change"]["kind"].startswith("mojo_")]
```

Fetched Chromium source lives in `.chromiumdiff-cache/` at the repository root, moved with `--cache` or the `CHROMIUMDIFF_CACHE` environment variable. It is regenerable — deleting it only makes the next run slower. `check` prints the cache directory, the free space and what a version pair costs.

Every finding cites `path:line` under `change.locations` — quote it, never paraphrase the file name.

**`report.html` alone answers *what* changed, never *why*.** Opened as a file it is a complete, offline table; the per-row "why did this change" lookup cannot run there, because a page on `file://` may not call `chromium-review.googlesource.com` and the browser blocks it before it is sent. Serving the directory changes who asks — the page calls localhost, and Python asks Gerrit:

```
python3 -m chromiumdiff serve out/M148_to_M151     # prints http://127.0.0.1:8787/
```

Offer this whenever someone asks why a row changed, what a flag was for, or which review to read. You can start it yourself and hand over the URL. Opening `report.html` directly and concluding the lookup is broken is wrong: it does not run because of `file://`, not because of a fault.

**The tool does not conclude for you.** It stops at extracted evidence and a deterministic rank. It knows nothing about what anyone patches, ships or overrides: a **Compatibility break** row says a contract moved, not that anyone was relying on it.

**Every run prints the coverage it achieved.** Quote that number in the report; never quote one from this file.

```
coverage: reads N of M files in this tree that could declare (P% of files)
```

**Coverage changes the answer, not just the confidence.** A removal is an inference from absence. On a partial read it loses 15 points, carries `unconfirmed`, and — for `pref_left_scan` and `switch_left_scan` — is filed as Upstream cleanup rather than a Compatibility break.

Measured on M148 → M151: `default` finds 139 `pref_left_scan` rows, `wide` finds 171. Only 30 of them are in the Windows build at all. Those 30 move from Upstream cleanup at 20 points to Compatibility break at 35 when the run is `wide`; the rest score 0 either way. **`Compatibility break: 0` on a default run does not mean nothing is broken** — read `summary.unconfirmed` before saying it does.

**Two error messages, one cause.** `cannot diff snapshots built from different target sets` and `cannot diff: X holds N facts against Y's M` both say one side read a fraction of the other. Neither is a bug to work around: check that `--local-src` / `--from-src` / `--to-src` points at a full Chromium `src/`.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`, `extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`, `media`) fetches and scans only the source paths listed for one feature. Right while looking at one feature, wrong as a release gate — Chromium does not organise its source by feature, so a change affecting downloads can live in `content/` and match no partition.

Two side commands: `chromiumdiff catalog <ref>` measures what the target set is missing; `chromiumdiff figures <report.json>` writes the measurements the project's own documents quote, which is how they stay true. The re-render command is in step 4, beside the reason you need it.

### Step 3: Read the report in order

The report arrives sorted by score, highest first. **That is not a reading order, and it is not a place to cut.** A Compatibility break row the run could not confirm loses 15 points and drops below thousands of lower-consequence rows. Measured at M148 → M151: reading the top 100 by score misses 232 of 276 Compatibility break rows; reading 500 still misses 55. Score orders rows inside a bucket; it does not decide how far to read.

When the list is long, **cover it by signal** rather than truncating. At that pair the four buckets above Upstream cleanup hold 2,287 rows but only 38 distinct leading signals, so reading each signal group once covers all of them. `report.md` is built that way: a bucket table carries every signal in the bucket, heaviest first.

**That is how you read, not how you write.** Signal, bucket and score band are properties of the machinery. The report you hand back groups by what happened — step 6 — and a section headed by a signal name, a bucket name or a score range is the shape this skill exists to avoid.

Read by bucket, in this order.

1. **What kind of change** — the per-bucket counts at the top of `report.md`. Start here; it says how long each list is.
2. **What happened** — every finding grouped under the signal that set its severity, so a report of thousands of rows collapses to a few dozen groups.
3. **Compatibility break**, then **Behaviour change**, then **New declarations**. Each has a table in `report.md`.
4. **Scheduled** — also a table. Read it as next milestone's list, not this one's: nothing in it has happened. It is not the "low score" bucket either. At M148 → M151 it tops out at 45, above every row in New declarations, because `flag_expiring` is a deletion Chromium has committed to.
5. **Unconfirmed** — its own table in `report.md`, and the `All coverage` filter in `report.html`. These are removals this run could not confirm. Most keep their bucket and lose 15 points. The `pref_left_scan` and `switch_left_scan` ones also move to Upstream cleanup, where they sit because the evidence is short, **not because they are minor**. Step 5, the *Flags, prefs and switches* branch, says what to do with them.

   303 of them at M148 → M151 on the default set, 120 of those in Compatibility break. A `wide` run has none.
6. **Upstream cleanup**: skip. It has no table on purpose — it is the largest bucket in every report and, once Scheduled and Unconfirmed are out of it, the one where nothing needs doing. At M148 → M151 it tops out at 35.

Retired flags are in Upstream cleanup, and deliberately: at M148 → M151 there were 132 of them, 72 that had shipped and 60 abandoned, none user-visible. Reporting one as a lost feature is wrong — read [reference/traps.md](reference/traps.md) before concluding.

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

Question 3 decides the layout — group by what the reader named, and say what you filtered to.

**When they named nothing, group by what happened, not by how the tool found it.** A bucket, a score band and a fact kind are all properties of the machinery. Group by any of them and a change that arrived as seven fragments goes back under several headings — the flag beneath one, the pages beneath another. That is the state `cluster.py` had already undone.

```markdown
## Overall risk
[One sentence: what this upgrade does, and where the work is.]

## What happened
[One item per thing that happened, heaviest consequence first.]

### <what a person calls it> — <the movement, in a few words>
[What moved, read from the fragments together. Name every identifier someone
would grep for.]
**Check:** [what to go and look at, and where — including outside this
repository.]

## Fixed outside the repository — N
[Always present, always last, even when filtered: a renamed flag or switch kills the override of anyone who set it, not of one team.]

## New capability
[web_api_added_live only. Product input, not a blocker.]

## Limits
[Coverage figure the run printed, target set, partitions, exact versions, and `summary.unconfirmed`.]
```

#### What counts as one item

In this order, so nothing is written twice:

1. **A block of `## Related changes, grouped`.** Already one item.

   Blocks are ordered by `spread`: how many consequence groups, buckets and directions the fragments fall across. That measures how much the grouping tells you that the rows do not. A block holding both a removal and an addition comes first, because that is the pair that misleads when read apart. Every block whose fragments disagree is printed, however many there are — 9 at M148 → M151 on the default set, 16 on the wide one. `summary.clusters` in the JSON holds all of them, each with its `spread` and `directions`.
2. **A screen and a direction.** Five pages arriving on `settings` is one item, not five. `## What changed on each screen` has them, truncated at twelve — take the rest from `report.json` when the screen has more.
3. **A row that stands alone.** One Mojo signature, one renamed pref. Its own item only if no cluster claimed it.

#### Reading a block into one sentence

The fragments contradict each other apart and agree together, so read every one of them before writing. Two attributes carry the direction: **the gate a page sits behind**, and **the state a flag held when it was removed**.

Worked, from the M148 → M151 block:

```
- `−` SITE_SETTINGS_LOCAL_NETWORK_ACCESS · WebUI page · 55
  - route: localNetworkAccess
  - guards: enableLocalNetworkAccessSetting
- `~` enableLocalNetworkAccessSetting · WebUI visibility gate · 45
  - features: −kLocalNetworkAccessChecksSplitPermissions
- `~` SITE_SETTINGS_LOCAL_NETWORK · WebUI page · 45
  - guards: −enableLocalNetworkAccessSplitPermissions, +enableLocalNetworkAccessSetting
- `~` SITE_SETTINGS_LOOPBACK_NETWORK · WebUI page · 45
  - guards: −enableLocalNetworkAccessSplitPermissions, +enableLocalNetworkAccessSetting
- `−` enableLocalNetworkAccessSplitPermissions · WebUI visibility gate · 40
- `−` LocalNetworkAccessChecksSplitPermissions · Chromium feature flag · 20
  - default_state: enabled
- `−` label:siteSettingsLocalNetworkAccess · WebUI control · 20
```

Three things follow, in order. The flag was **enabled** before it was removed, so users already had the split. The experimental gate is gone, and the two split pages moved onto the gate the combined page had used. The combined page and its control went with it.

That is one movement, not seven facts:

> **Local Network Access — the split shipped, the combined page is gone.**
> The page `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` (route `localNetworkAccess`) and its control `siteSettingsLocalNetworkAccess` are removed. `SITE_SETTINGS_LOCAL_NETWORK` and `SITE_SETTINGS_LOOPBACK_NETWORK` moved off the experimental gate `enableLocalNetworkAccessSplitPermissions` onto `enableLocalNetworkAccessSetting`, and both that gate and `LocalNetworkAccessChecksSplitPermissions` — which was **enabled** at M148 — are retired. Users saw the split before this upgrade; M151 removes the machinery.
> **Check:** anything linking to `chrome://settings/localNetworkAccess`; any use of the string `siteSettingsLocalNetworkAccess`; any Finch config setting `kLocalNetworkAccessChecksSplitPermissions`.

And a screen group, from the same run:

> **Five new settings pages.** `/ai/suggestions` and `/ai/skills` behind `showAiPage`, `/autofill/suggestionsFromGemini` and `/shopping` behind `enableYourSavedInfoSettingsPage`, and `inlineCueMenu` behind **no gate at all**.
> **Check:** `inlineCueMenu` is the one that is reachable the day the version is adopted. Quote a route exactly as `report.json` holds it — four of these five carry a leading `/` and that one does not.

#### What every item has to carry

**What moved**, **whether anyone sees a difference**, **what someone must do**. The middle part decides priority and a raw diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."* — one fragment of seven, and it reads as a lost feature.

Also bad: *"12 changes to chrome:// pages, 3 Compatibility break."* — a count is not a thing that happened.

**Stop at what the evidence shows.** Write what moved and what to check; do not write that something is a bug. The tool has one Chromium version and another, and no knowledge of what this product patches or ships.

## Reference

- **[reference/traps.md](reference/traps.md)** — the ways to reach a wrong conclusion, each one measured against real Chromium data. Read before interpreting any removal; the later traps cover Mojo, web APIs and switches.
- **[reference/signals.md](reference/signals.md)** — what each signal means.
- **[reference/settings-screen.md](reference/settings-screen.md)** — the three-hop chain from a settings page to the flag behind it, and how to size a "feature".

## What the tool cannot see

State these in every report. A clean report does not imply a clean upgrade.

- **Whether any of it touches a particular product.** The tool compares Chromium against Chromium. Searching your own tree for the identifier a finding cites is the step that answers "does this affect us".
- **Implementation-only changes.** It reads declarations. Behaviour changed inside a function body is invisible.
- **Five classes of declaration it does not turn into facts**, in files it otherwise reads completely. Measured at M151: 85 Web IDL `callback` definitions, 144 `typedef`s, 200 `Interface includes Mixin` relations, 18 Mojo `feature` blocks and 311 Mojo constants. Real examples that produced no row: `typedef LanguageModelMessageValue` changing its underlying union at M143 → M147, and the Mojo constant `kWebNNDirectML` disappearing at M151. **"Reads 99% of the files" is a statement about files, not about grammar.**
- **Anything outside the repository** — Finch configs, launch scripts, test automation, enterprise policy, store metadata.
- **Chrome Extensions IDL and MIDL.** Only Blink's own `.idl` is read.
- **Page behaviour.** Only the declarative parts of a WebUI screen: the route table and the HTML templates, not the TypeScript.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

Use flags and declarations to *discover*, targeted code reading to *explain*, screenshots only to *confirm* a short list. Do not use screenshots to discover changes.
