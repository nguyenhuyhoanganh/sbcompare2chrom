# chromiumdiff

A tool that compares two Chromium versions and answers one question: **what actually changed, and how much does each change matter.**

The target product is a Chromium-based desktop browser on Windows, which is why the platform is fixed rather than selectable. Everything here is plain Python, no third-party libraries, no `pip install`.

**Every measurement below was taken on one pair of versions, M148 → M151, unless the sentence names another. They are evidence for the argument being made, not properties of the tool: the number to trust is the one your own run prints.**

---

## Contents

1. [The problem](#1-the-problem)
2. [Quick start](#2-quick-start)
3. [What stands between the code and the user](#3-what-stands-between-the-code-and-the-user)
4. [What the tool reads](#4-what-the-tool-reads)
5. [Coverage: how much of the tree gets read](#5-coverage-how-much-of-the-tree-gets-read)
6. [The commands](#6-the-commands)
7. [How a change is ranked](#7-how-a-change-is-ranked)
8. [Reading the report](#8-reading-the-report)
9. [Limits](#9-limits)
10. [Environment and troubleshooting](#10-environment-and-troubleshooting)
11. [Tests](#11-tests)
12. [Source layout](#12-source-layout)

---

## 1. The problem

Every few releases the team moves its Chromium base to a newer milestone — M148 to M151, say. Each time, three questions have to be answered:

- What did Chromium **add**?
- What did Chromium **remove**?
- What is **still there but behaves differently**?

Download two Chromium releases and run `git diff` and you get several million changed lines. Most of it is irrelevant: renamed variables, cleanup, typo fixes in comments, third-party library rolls. Reading all of it is not possible; skimming it misses exactly the thing that mattered.

So the real problem is not "how do we compare them" but **"how do we filter down to the part that means something"**. That is what chromiumdiff does.

### Three design principles

**No Chromium checkout.** A full one is about 100 GB and hours of syncing. The tool only needs a few thousand declaration files — the ones that list what exists, what it is called, and whether it defaults on or off. Chromium serves individual directories over Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<version>/<directory>.tar.gz
```

About 337 MB per version. A team that already has a checkout or an internal mirror uses `--local-src` instead; nothing else changes.

**Normalize first, compare second.** Between M139 and M143, Chromium changed how the feature-declaration macro is written:

```cpp
// M139 and earlier
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);

// M142 onwards — the string name is derived from the variable name
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
```

In a single file, M139 has 170 of 170 declarations in the old form and M143 has 12 of 187. A tool that compares source text reports "170 features deleted, 187 features added" — which is meaningless. chromiumdiff normalizes `kBackForwardCache` to `"BackForwardCache"` before comparing, and gets a readable answer: 152 unchanged, 18 dropped, 35 added.

**Stop at the evidence.** The deterministic stages — extract, normalize, compare, rank — turn several million changed lines into a few thousand labelled changes, sorted so the ones that cost something are at the top, and then stop. The tool does not conclude "this means X for the product". That takes judgement about a particular product, and it belongs to whoever reads the report, or to an agent running the [`analyzing-chromium-upgrades`](skills/analyzing-chromium-upgrades/SKILL.md) skill. chromiumdiff's job is to make that input complete, ranked and citable.

It is also why nothing in the tool describes *your* codebase. A ranking that added points for files you patch or symbols you reference would need that description on every run, and without it every one of those points would be zero. The tool therefore reports what two Chromium trees can establish on their own, and the step it does not take — searching your own tree for the identifier a finding cites — is one command you run yourself.

---

## 2. Quick start

### Requirements

| Item | Requirement |
|---|---|
| Python | 3.9 or newer. No 3.10+ syntax. Tested on 3.14.6 |
| Third-party libraries | None. Standard library only |
| Free disk | ~320 MB for two versions, measured on M148 → M151 |
| Network | Four HTTPS hosts, see the table below. Only the first is ever required |
| Chromium checkout | Not needed |

| Host | Used for | Required |
|---|---|---|
| `chromium.googlesource.com` | Fetching source by tag | Yes |
| `chromiumdash.appspot.com` | Resolving `151` to `151.0.7922.138` | No, if you always write the full version |
| `chromestatus.com` | Feature summaries and spec links | No, skip with `--no-enrich` |
| `chromium-review.googlesource.com` | The CL and issue behind a change | No, only `serve` uses it |

### Installing

There is no build step. Copy the directory to the target machine and it runs:

```bash
tar czf chromiumdiff.tgz chromiumdiff/ tests/ skills/ docs/ README.md
# on the target machine, in an empty directory
tar xzf chromiumdiff.tgz
python3 -m chromiumdiff --version
```

On Windows use `py -3` instead of `python3`.

### Checking the machine

Run this first on any new machine. It checks everything that commonly breaks, in one pass, instead of letting you discover each failure two minutes into a run:

```bash
python3 -m chromiumdiff check
```

```
python
  [OK  ] version 3.14.6
cache directory
  [OK  ] /path/.chromiumdiff-cache writable — 68 GB free
network
  [OK  ] gitiles (source) — HTTP 200
  [OK  ] chromiumdash (version resolution) — HTTP 200
  [OK  ] chromestatus (enrichment, optional) — HTTP 200

ready
```

Exit code `0` means ready, `1` means there is a FAIL line to deal with — usable in CI as a preflight step.

### Smoke-testing the pipeline (~10 seconds)

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 \
  --target-set smoke --no-enrich
```

`smoke` fetches three files — enough to confirm the pipeline is wired up. It
reads far too little to compare two versions.

### A full run

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

About three and a half minutes on a cold cache. Measured per version: 97 seconds, of which 69 are fetching and 25 are the fourteen directory listings, leaving about 3 for extraction — so two versions plus enrichment. A second run over the same pair of tags is a cache hit, measured at **0.3 seconds** for the whole pipeline: both snapshots read, 3,022 changes compared and ranked, and all three report files written. A released tag's content never changes, so the cache is kept forever, and network speed is the only reason your cold number will differ.

Results land in `out/M148_to_M151/`:

| File | Size | Use it for |
|---|---|---|
| `report.md` | ~126 KB | Pasting into Jira, Confluence, a merge request |
| `report.html` | ~1.5 MB | Opening in a browser; filterable and sortable, fully self-contained |
| `report.json` | ~4.2 MB | Scripts, dashboards, comparing across cycles |

`report.html` loads no external resources, so it works on an air-gapped network and can be attached to an email.

### From findings to meaningful upgrade events

The [upgrade-analysis skill](skills/analyzing-chromium-upgrades/SKILL.md) uses
a resumable evidence workbench. It does not require an additional model API or
third-party dependency: the executing agent supplies the interpretation.

```bash
python3 -m chromiumdiff review init out/M148_to_M151 --directory out/M148_to_M151/review
python3 -m chromiumdiff review index out/M148_to_M151/review --limit 30
python3 -m chromiumdiff review check out/M148_to_M151/review
```

The index includes every finding regardless of score, declared relationships
through unchanged facts in both snapshots, milestone leads, and raw changes
between cached source files. Add `--source-repo /path/to/chromium/src` to
`review init` to inventory all changed paths between exact Git refs without
checking out either revision. Cached-only inventory is explicitly partial;
one uncached side is not evidence of an upstream addition or removal.

Use `inspect`, `related`, `unresolved` and `source` for bounded, version-qualified
retrieval. The agent records evidence-backed event decisions with `record`;
`render` writes `review.md` from `review.json`. Neither edits the raw report.
`check` returns nonzero for pending/unresolved work, provisional conclusions or
stale inputs. Accounting completion does not certify semantic completeness.
See the [decision and refresh procedure](skills/analyzing-chromium-upgrades/reference/investigation.md)
and [independent evaluation protocol](docs/review-evaluation.md).

A review can also record an explicit item selection for the user's scope.
`review check --selection` and `review render --require-selection-complete`
check that selection while preserving whole-index counts and any PARTIAL status.
See the [selection record](skills/analyzing-chromium-upgrades/reference/selection.md);
a path filter returning no rows neither defines nor completes it.

The evaluation workflow includes `prepare-trial`, `run-trial`, `collect-trial`
and `evaluate --adjudication ... --manifests ...`. Source-pinned case specs and
separate source-first rubrics live under `tests/fixtures/review_cases` and
`review_gold`; gold is never staged for the tested agent. A perfect membership
score is not a semantic pass. The optional release gate requires independent
claim/citation review, complete accounting, repeated executions and a verified
runner context limit. See the protocol for runnable examples and current limits.

### Always write the full version

`151` resolves to whatever is the newest stable release *at the moment you run it*, and that moves. Here is a real difference:

```
143.0.7499.40   → ServiceWorkerAutoPreload = ENABLED
143.0.7499.194  → ServiceWorkerAutoPreload = DISABLED   (reverted in a patch release)
```

The same `run 139 143` a few weeks apart can produce two different conclusions, and both are correct. For anything official, write the full version and record it in the ticket. Bare milestone numbers are for exploring.

---

## 3. What stands between the code and the user

This section is why the tool exists. It has two halves, and they go wrong in opposite directions — the mistake worth avoiding is learning the first and assuming it covers the second.

Between "the code changed" and "someone notices" there is usually something holding the door: a **gate**. Where there is one, the code change and the visible change happen in different milestones, so a diff between two versions shows you the wrong milestone. Where there is none, the code change *is* the change, and it lands the day you adopt the version.

Every kind is one or the other:

| Kind | What holds the door | Code change and user-visible change land together? |
|---|---|---|
| `base::Feature`, Blink runtime flags | the flag's own default, per platform | No — usually several releases apart |
| chrome:// screens | a `loadTimeData` boolean, which resolves to a flag | No — same as above |
| Web IDL | `[RuntimeEnabled=Foo]`, on the member **or** its interface | Sometimes — 133 of 220 added members at M148 → M151 are reachable on arrival |
| Mojo | nothing. `[EnableIf]` decides which *platform* compiles it, not who can see it | **Yes** |
| Preferences, command-line switches | nothing | **Yes** |

Both halves are large, and the second carries the higher severities: at M148 → M151, **220 of the 276 Compatibility break rows are Mojo or web API**. The report is ordered to keep them apart — `report.md` opens with the per-bucket counts, and Compatibility break is the first list of rows it prints.

---

### Half one: there is a gate, and the diff shows the wrong milestone

#### Chromium never turns a new feature straight on

Their process is always four steps:

1. Write the new code **behind a flag**, defaulting off. The code ships but nobody sees anything.
2. **Turn it on remotely** — 1% of users, then 10%, then 50%. If something goes wrong they turn it back off without shipping a release. That is a *feature flag*.
3. **Set the default to on in code**, once it is clearly fine.
4. A few releases later, **delete the flag** and the old code, because nobody needs to turn it off any more.

#### The consequence: a feature has three moments

| Moment | What happens in the code | What users see |
|---|---|---|
| A | New code appears, flag off | Nothing |
| B | Flag flips on | **This is when it changes** |
| C | Old code and flag deleted | Nothing |

Those three are usually several releases apart: appears at M145, turns on at M147, cleaned up at M151.

Now suppose you compare M148 with M151 and look only at the code. You see **moment C** — old code gone — and conclude "Chromium just removed this feature". In fact the feature changed at M147, and between M148 and M151 users saw nothing different at all.

Put shortly: **the declaration files tell you what exists; only the gate tells you what users actually get.** Which is why half two below matters as much: a Mojo field or a preference has no gate, so there is no moment A and no moment C — there is only the change, and it arrives with the version.

#### A real example: Local Network Access

Checked against real M148 → M151 data:

**Step 1.** Compare the settings page list, and `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` is gone. Read naively: "Chromium removed the Local Network Access page" — an important privacy page.

**Step 2.** Read M148 more carefully and there are **two** pages declared at once:

```js
If the flag 'enableLocalNetworkAccessSetting' is on:
    → create page  /localNetworkAccess     (the old one)

If the flag 'enableLocalNetworkAccessSplitPermissions' is on:
    → create page  /localNetwork           (the new one, with finer-grained permissions)
```

**Step 3.** At M151 only the new one is left.

**Step 4.** Check the flag: `kLocalNetworkAccessChecksSplitPermissions` was **enabled by default at M148**, and deleted entirely at M151.

**The real conclusion:** the page was not removed, it was **replaced** by the split-permissions version. Because the flag was already on at M148, M148 users were already seeing the new one. Between the two versions the experience did not change; M151 only cleaned up the code.

The work required to move to M151 is not "restore a lost feature" — it is: if anything still points at the old `/localNetworkAccess`, change it to `/localNetwork`. A small job, and completely different from what a raw diff makes you think.

#### The scale of it

This is not an isolated case:

- **M148 → M151, Windows:** 154 flags removed — 72 that had shipped, 60 that were abandoned, 22 whose prior state is unreadable. None of the first two groups changes behaviour. Labelling all 154 "feature lost" makes most of the alert list a false alarm.
- **M139 → M143, web layer:** of 202 features that "disappeared", 167 were already stable — the flag was cleaned up after the feature shipped successfully.

A tool that puts 167 false alarms at the top of its first run is not usable.

---

### Half two: there is no gate, and nothing warns you

Mojo, preferences and command-line switches have no gate at all. There is no stage A, no remote rollout, and no milestone at which it takes effect. **The declaration is the contract, and changing it changes the contract on the day you adopt the version.**

This half is dangerous because **nothing tells you**:

```
blink.mojom.PublicKeyCredentialRequestOptions.challenge
    array<uint8>?  →  array<uint8>
```

A WebAuthn message field stopped being nullable. Nothing in Chromium warns about this, and it does not break the build: both ends of a Mojo interface are generated from this same file, so they always agree with each other. It breaks whatever is on the *other* side that was not regenerated — which is why the tool scores it 80 and why trap 10 exists to say who that other side actually is.

Preferences and switches fail the same way, one step further out. Chromium **ignores a command-line switch it does not recognise** — no warning, no error, no log line — so a launch script keeps starting the browser exactly as before and the flag it passes stops doing anything at all.

For this half the questions from half one give a wrong answer rather than no answer. "Did the flag state change?" has no answer here, and answering "no" reads as "then nothing happened". Traps 9 to 12 are written for these kinds, and the decision procedure in the skill branches on the declaration's kind before it asks anything.


### Assembling the fragments into one change

One Chromium change does not arrive in one place. The Local Network Access case above produces exactly seven fragments:

```
webui_route    SITE_SETTINGS_LOCAL_NETWORK_ACCESS         removed
webui_route    SITE_SETTINGS_LOCAL_NETWORK                guard changed
webui_gate     enableLocalNetworkAccessSplitPermissions   removed
webui_gate     enableLocalNetworkAccessSetting            expression changed
webui_control  label:siteSettingsLocalNetworkAccess       removed
base_feature   LocalNetworkAccessChecksSplitPermissions   shipped, then flag retired
blink_runtime  LocalNetworkAccessSplitPermissions         experimental flag dropped
```

Read line by line they contradict each other: one says a page was removed, the next says a page appeared. Read as one group they say one thing.

`cluster.py` groups them using **links the data itself declares**, not name similarity:

```
route  --names its guard-->  gate  --names its feature-->  base_feature
control  --names its label-->  route
feature_param  --names its owning feature-->  base_feature
blink  --names its base_feature-->  base_feature
finding  --was changed by-->  CL  <--was changed by--  finding
```

Each arrow is a real field. The seventh fragment — `blink_runtime LocalNetworkAccessSplitPermissions` — deliberately stands apart, because its fact declares `base_feature: "none"`: Chromium is saying outright that this flag has no matching C++ feature. A similar name is not a relationship.

**The last arrow is the one that reaches the top of the report.** The four above it join on a link Chromium writes *in the source*, and between a `.mojom` and an `.idl` no such link is ever written — so they group a feature with its parameters, which is the bottom of the ranking, and almost nothing else. On the M148 → M151 run they build 72 clusters covering 183 of 3,022 findings, and of the 150 highest-scoring findings they reach **6**.

A shared CL is the same evidence recorded somewhere else: the author wrote one change and it landed across several declarations, and the CL number is Chromium saying so. With the top 150 resolved it reaches **84** of them and takes the whole report to 261. Measured on that run, **9 of the 20 highest-scoring rows** are a repeat of a change already on screen — one CL introducing a mixin takes 14 rows, `[sub apps] change web api` takes 7 across three kinds.

Only the CL, never the issue: one issue on that run carries 24 CLs across unrelated areas. Only verdicts that name the fact, never `crowded` or `touched`, which name the declaring file — `about_flags.cc` alone would put five hundred findings in one group. And the grouping runs where its evidence arrives, which is a lookup: `run` asks Gerrit nothing, so on a report where nothing has been looked up this arrow contributes nothing and the other four are all there is.

The report has a *Related changes, grouped* section ordered by the highest score in each cluster, and every finding's own section says whether it is a fragment and what the heaviest thing in its group scores — because that section is what a reader pastes into a ticket, and the table is not.

---

## 4. What the tool reads

### Nine extractors

Each extractor is two pure functions: "does this file belong to what I read" and "what can I read out of it". That makes every one of them testable on its own, with no network and no Chromium.

| Extractor | Reads | Tells you |
|---|---|---|
| `base_features.py` | `base::Feature` declarations in C++ | Feature switches and their per-platform default on/off |
| `blink_runtime.py` | `runtime_enabled_features.json5` | Web-engine features and their stable/experimental status |
| `web_idl.py` | `.idl` files | The exact shape of a web API: interfaces, methods, attributes |
| `mojom.py` | `.mojom` files | Both halves of the process boundary: the interfaces and their method signatures, and the structs, unions, enums and fields that travel along them |
| `constants.py` | `*switches.{cc,h}`, `*pref_names.{h,cc}`, `*_prefs.{h,cc}` | Command-line switches and user settings keys |
| `flags_metadata.py` | `flag-metadata.json` | Which switches are scheduled for removal in an upcoming release |
| `webui_routes.py` | `route.ts` | The page list of a `chrome://` screen, with its visibility conditions |
| `webui_controls.py` | `.html` and `.html.ts` templates | Each control, its type, and the setting it writes |
| `webui_gates.py` | `*_ui.cc` | The link between a UI condition and a feature switch |

Supporting the C++ extractors is `_cpp.py`. It masks comments while preserving file length (so reported line numbers stay correct), splits balanced arguments (ignoring parentheses inside string literals), and evaluates preprocessor conditions for our platform. `jsonc.py` is a hand-written JSON5 reader, because Chromium uses that format, Python has none built in, and we are not allowed to add a library.

### Three WebUI extractors cover every screen

`chrome://settings`, `chrome://history`, `chrome://downloads`, `chrome://bookmarks`, `chrome://extensions` and roughly 130 other `chrome://` screens are all built the same way: a web page under `chrome/browser/resources/`. So those three extractors read all of them.

They form a three-hop chain, and you have to walk all three hops to reach the right conclusion:

```
route.ts                          which pages exist
   ↓ guarded by
loadTimeData key                  the visibility condition
   ↓ given its value in
settings_ui.cc  →  base::Feature  the real switch
```

Stopping at the first hop is exactly the Local Network Access trap.

The control's type is the tag name itself — `settings-toggle-button` is a toggle, `settings-dropdown-menu` is a dropdown, `cr-radio-group` is a radio group — so "a dropdown became a toggle" is caught by comparing tag names.

Chromium is migrating WebUI from Polymer (`.html`) to Lit (`.html.ts`), and unevenly: at M151, settings still has 243 Polymer files against 6 Lit, while extensions is 2 against 33 and print_preview 2 against 32. The extractor reads both dialects.

**What counts as a control is a rule, not a list of names.** An element is a control when it binds a preference; or when a hyphen-separated segment of its tag names an interactive component *and* it has a stable identity (an element id or a label); or when it is one of the structural units a page is built from. Matching segments rather than substrings is what separates `cr-icon-button` from `cr-icon`. An identity is required because an element with no preference, no id and no label can only be identified by its position, which changes whenever a template is reordered. At M151 an `analysis` run reads 1,431 controls: 190 of them bind a preference, and 15 (1%) are identified only by their position.

**Identity has to be specific enough to tell things apart.** A loadTimeData key is not unique: at M151, 62 of 668 keys are set by more than one handler — `undoDescription` by both `bookmarks_ui.cc` and `downloads_ui.cc` — and 26 of those set different values. Controls are the same: 98 of 1,256 keys collide between files in the same directory, like `id:nicknameInput` existing in both `credit_card_edit_dialog` and `iban_edit_dialog`. When keys collide one copy is dropped, and which one survives depends on directory walk order. So a gate carries its handler name and a control carries its file name: that recovered 318 declarations that were being thrown away. Routes still join to gates by the bare key, so the three-hop chain is unchanged.

### Why preprocessor conditions have to be read

Chromium frequently gives a feature a different default per operating system:

```cpp
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
```

Reading naively — take the first value you find — gives "enabled". In this example that happens to be right, because `IS_WIN` is in the first branch. The danger is the opposite case, where Windows falls into the `#else`. In a single file, 14 of 187 features have per-platform defaults.

| Guard around the declaration | Naive read | Real value on Windows |
|---|---|---|
| `IS_WIN \|\| IS_MAC \|\| IS_LINUX` | `enabled` | `enabled` — they agree |
| `IS_ANDROID` … `#else` | `enabled` | **`disabled`** — the naive read is backwards |
| `ENABLE_PLUGINS` … `#else` | `enabled` | `conditional` — no guess |

The second row is the case the tool is for: reading the wrong one gives the opposite conclusion. The third row matters too: when the condition depends on a non-platform buildflag, the three-valued evaluator answers "undecidable" rather than guessing.

### The platform is fixed, not an option

The product is a desktop browser on Windows, so **there is no `--platform` option**. That is deliberate: an option nobody checks is a way to be silently wrong, and as above, being wrong here inverts the conclusion.

Other platforms' macros are still recognised, but so they evaluate to *false* rather than "undecidable":

```python
eval_condition("BUILDFLAG(IS_WIN)")          # True
eval_condition("BUILDFLAG(IS_ANDROID)")      # False  — definitely not us
eval_condition("BUILDFLAG(ENABLE_PLUGINS)")  # None   — no guess
```

Build conditions are resolved for Windows everywhere they appear, not only in feature macros: an `#if` around a pref or switch constant (117 keys at M151 are not in the Windows build), and a GRIT `<if expr="...">` around a WebUI control (16 controls). One three-valued evaluator, two dialects — `not is_win` and `!BUILDFLAG(IS_WIN)` ask the same question.

Other platforms' trees (`ash/`, `chromeos/`, `ios/`, `fuchsia/`) are skipped, **with one exception**: string constants are read wherever they live. A pref key is identified by its string, and Chromium is currently splitting `chrome/common/pref_names.h` apart. When a key moves into a ChromeOS file we cannot see, the tool reports it as deleted — and a deleted pref means every existing user's stored value is orphaned. Measured M148 → M151: reading the curated files alone reports 139 keys gone and an `analysis` run still holds 29 of them, so those 29 had moved rather than been deleted.

### Comparison by meaning, not by text

`diff.py` rests on two rules:

**Only compare attributes that mean something.** Between M139 and M143 every declaration changed syntax; comparing a "which syntax" attribute would produce thousands of meaningless changes. Each kind of fact has a whitelist of attributes worth comparing.

**Score for the real platform.** A default that flips on desktop but not on Windows is not a change for you.

Then it attaches a **meaning label** to every change — this is what turns "a line of code differs" into something readable:

| Label | Do users see a change? | Meaning |
|---|---|---|
| `default_flip_on` | Yes | The switch flipped on |
| `web_api_shipped` | Yes | A web API reached stable |
| `ipc_signature_change` | Yes | A cross-process call signature changed — breaks silently at runtime |
| `flag_retired_on` | No | Shipped, switch removed, behaviour is now permanent and cannot be turned off |
| `flag_retired_off` | No | Never shipped, code removed, cannot be turned on any more |
| `feature_string_renamed` | No, but… | The Finch name changed — server-side configs silently stop matching |
| `feature_symbol_renamed` | No, but… | The C++ identifier changed — our build breaks after the merge |
| `pref_renamed` | No, but… | A settings key changed — every existing user's stored value is orphaned |

Every attribute that gets compared produces a label like this, and a test enforces it. An attribute is in the whitelist because a change to it matters, so a change the report could not name would be a row nobody can read.

The last four labels are the dangerous kind: they **compile cleanly, pass tests, and fail in the field** — or break the build right after the merge, at the latest possible moment.

`diff.py` also detects renames. For prefs and switches, identity is the string, while the C++ variable name stays put; so a rename shows up as an unrelated removal plus an unrelated addition. Pairing them by variable name reveals what really happened. A real case:

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);   // lowercase r
// M143 — the macro derives the name from the variable
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   the string name is now "FedCmIdPRegistration"                  // uppercase R
```

Nobody edited a name — changing the macro changed it. Every server-side field-trial config and every `--enable-features` flag using the old spelling **silently stopped working**. No compile error, no warning.

When a pref or switch disappears and cannot be paired, the tool does **not** claim it was deleted. It labels it `pref_left_scan` / `switch_left_scan`, meaning "left the scanned scope" — possibly deleted, possibly moved to a file we do not read. On the M148 → M151 run reading the curated files alone, all 139 vanished prefs carried that label.

---

## 5. Coverage: how much of the tree gets read

### Every run measures it

A hand-written file list is only correct for the version it was written against. Build the list as it stood at M130 and run it at M151, twenty-one milestones later, and it misses 27% of the pref files and 34% of the feature files that exist there. A third of the coverage is lost over two years, and nothing reports it: a file nobody listed is a file nobody notices.

So on every run the tool asks that version's own tree what exists, and measures the target set against it. Gitiles returns a recursive listing of a directory in one request, so the 25 roots cost about 33 MB per version — measured at 151.0.7922.138 — cached forever because a tag's tree never changes.

The result is printed on every run, stored on the snapshot, and carried into the report — `report.json` at `meta.coverage` (`{from, to}`, one measurement per side) together with the unread paths at `meta.uncovered_files`, and `report.md` in its closing *How this was produced* section:

```
coverage: reads 8295 of 8366 files in this tree that could declare (99% of files)
  largest gaps: chrome/services/ (24 files), chrome/credential_provider/ (15 files), chrome/installer/ (12 files)
  no target reads these; the run cannot see them at all
```

That is the 151 side of the 148.0.7778.217 → 151.0.7922.138 run in `docs/reviews/`. The three directories it names are the ones no target reads, which is why the last line says the run cannot see them rather than offering a wider set.

**The numbers in this document are a measurement taken at M151. The number to trust is the one your run prints.**

### Two target sets

| | Downloaded | Kept on disk | Declaration files read | Use it for |
|---|---:|---:|---:|---|
| `analysis` (the default) | ~337 MB | ~110 MB | **nearly all of them** | Comparing two versions |
| `smoke` | ~300 KB | ~1 MB | 3 files | Checking the pipeline runs |

`analysis` is a hand-picked file list plus whole-directory archives. The list alone would be ~40 MB per version and read under half the declaration files — and **file count is not declaration count**, because the hand-picked files are the big ones. Measured at M151, what the archives add:

| | curated files alone | `analysis` |
|---|---:|---:|
| `base::Feature` | 2,069 | 4,243 |
| Feature params | 863 | 1,686 |
| Prefs | 689 | 2,460 |
| Switches | 288 | 1,222 |
| Mojo interfaces | 338 | 1,479 |
| Mojo methods | 1,362 | 6,012 |
| Mojo structs | 703 | 2,867 |
| Mojo struct fields | 3,076 | 13,015 |
| Mojo enums | 373 | 1,477 |
| WebUI controls | 971 | 1,431 |
| **Total facts** | **29,138** | **54,298** |

So the curated list alone reads under half the files but more than half of the `base::Feature` declarations, and the share is very uneven between surfaces: nearly all the Web IDL, a quarter of the Mojo, a fiftieth of the pref and switch files. The archives are what close that gap, and they are why a run costs 337 MB rather than 40. The list is not selectable on its own for exactly that reason.

`analysis` reads nearly the whole tree. The coverage denominator is not a second list maintained beside the target list: it asks each extractor whether it would read a file, so an extractor added later widens the denominator by existing, and the measurement and the extractors cannot disagree.

The denominator is the whole tree rather than the directories the fetch targets live under, because a measurement built from those directories could only ever return 100%. What an `analysis` run still misses has names — `chrome/services/`, `chrome/credential_provider/`, `chrome/installer/` — and the run prints them: at M151 it reads 8,295 of 8,366 candidate files.

Declaration files outside the browser's own directories are fetched for the same reason. `base/`, `device/`, `cc/`, `sandbox/`, `storage/`, `google_apis/`, `pdf/`, `mojo/` and Blink's `renderer/platform` hold files such as `base/features.cc`, `cc/base/features.cc` (the compositor), `device/fido/public/features.cc` (WebAuthn) and `sandbox/policy/features.cc`. They add 22 MB per version, which brings a run to 337 MB.

Some files are excluded by name rather than fetched: the headless shell, Chrome Remote Desktop, the updater, the enterprise companion, the Windows services, and Fuchsia's own tree. They are binaries that ship beside the browser rather than being it, so their switches reach none of the browser's users; `content/shell/` is excluded for the same reason.

Vendored third-party projects — abseil, grpc, zlib, the WebRTC overrides — are excluded by name rather than by falling outside a root. Fourteen of their files match the naming conventions, they are other people's libraries rather than Chromium's own code, and naming the exclusion is what keeps `catalog` and the per-run measurement describing one population.

That suffix list now exists exactly once (`targets.READABLE_SUFFIXES`), shared by the archive roots and `--complete`, because both ask the same question: which filename shapes can an extractor read.

### Partitions: bounding what is fetched and scanned

When you only care about one area, `--partition` bounds both the fetching and the reading:

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 --partition downloads
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 --partition settings --partition bookmarks
```

Available: `settings, downloads, bookmarks, history, extensions, passwords, printing, newtab, webplatform, network, media`.

A partition is a **filter over the target list**, not a second list to maintain — add a target and it flows into whichever partitions its path matches. A few entries are kept in every partition because they are cheap and relevant to everything: `pref_names.h`, `flag-metadata.json`, `content_switches.cc`.

A partitioned run prints two coverage figures. The first counts every file in the tree that could declare something, as an unpartitioned run does. It is the figure the report shows and the one a removal is confirmed against. The second counts only the files under the partition's own roots. Measured at M151, on the new side of `run 148.0.7778.217 151.0.7922.138 --partition downloads`:

```
coverage: reads 10 of 8366 files in this tree that could declare (0% of files)
inside the partition's roots: reads 10 of 22 (45% of files)
```

A removal is confirmed only when the run read at least 95% of that kind's files in the whole tree (§7). On the downloads partition at M148 → M151, 16 removals carry `unconfirmed`: 15 preference keys and 1 switch. Six of them are still declared in the M151 tree, in files outside the partition. The 220 removed chrome://flags entries are confirmed, because their only file, `flag-metadata.json`, is read by every partition.

**The trade has to be stated plainly:** a partition is faster and less complete, in one direction only. Chromium is not organized by product feature — a change affecting Downloads can live in `content/`, in a Mojo interface, or in a flag file matching no partition at all. Right while iterating on one area; **wrong as a release gate**.

Add `--complete` and the partition fetches whole directory roots instead of filtering a file list, so coverage inside those directories is complete by construction. Measured at M151: `--partition extensions --complete` reads 19 of 19 files inside its roots. The option is refused for partitions whose roots are entire subsystems (`webplatform`), because Gitiles serves a whole directory or nothing.

### Measuring with a blobless clone — the `catalog` command

`catalog` answers the same question from a different source: a clone that downloads no file contents gets Chromium's entire tree structure in seconds.

```bash
python3 -m chromiumdiff catalog 151.0.7922.138
```

It uses **the same rule** as the per-run measurement, so the two numbers describe the same population, and it names every missing file so they can be added in priority order.

### Two meanings of "complete"

| Question | Can it be answered |
|---|---|
| Did we read every declaration **inside** an area's directories? | **Yes** — with `--complete`, or an unpartitioned run for the whole tree |
| Did we read every feature that **belongs to** that area? | **No** — every area references things outside itself |

For example: every declaration in `chrome/browser/resources/settings` is readable, but a feature shown on the Settings page may be controlled by a flag declared in `content/`. That is why the report has a *reference closure* section — it walks every link the data itself declares and lists the ones pointing at something absent from the snapshot.

---

## 6. The commands

```bash
python3 -m chromiumdiff check      # verify this machine can run the pipeline
python3 -m chromiumdiff snapshot   # extract the feature surface of ONE version
python3 -m chromiumdiff compare    # semantic comparison between TWO versions
python3 -m chromiumdiff run        # the whole pipeline: snapshot → compare → rank → report
python3 -m chromiumdiff report     # re-render a saved report.json
python3 -m chromiumdiff catalog    # measure which files the target set is missing
python3 -m chromiumdiff serve      # serve a report where opening a row looks its CL up
python3 -m chromiumdiff why        # which CLs changed one finding, and the bug behind them
python3 -m chromiumdiff cl         # one CL's own message, and the diff of one of its files
python3 -m chromiumdiff review     # the agent's review ledger; section 9 covers it
```

Splitting them up has a reason. The expensive stage (fetching) and the stage you tune repeatedly (ranking, reporting) have completely different cost profiles. Re-running the cheap half against a warm cache is what makes the tool worth tuning rather than running once.

`serve`, `why` and `cl` are the stages that ask a question the two trees cannot answer between them: *who changed this, and what were they fixing.* They are separate from `run` because they need the network and because a report is worth reading without them. `serve` answers it for a person, through a page and a click; `why` and `cl` answer it for an agent, which has neither. The page asks `/api/ping` once on load and enables the live path only if something answers, so the same `report.html` opened from a disk, or mailed to a colleague, behaves exactly as it always did. Section 8 says what it produces and how far it can be trusted.

Each command accepts only the options it actually uses. `catalog` has no `--local-src`, `check` has no `--partition` — a command that accepts a flag and ignores it is a bug, and a test blocks it.

---

## 7. How a change is ranked

Two numbers travel with every finding. Every point of gap between them has a sentence beside it.

### Severity: what this kind of change costs

Severity comes from the **leading signal** — the label with the highest weight among the ones the comparison attached. When a change carries no signal at all, and only then, it comes from a coarse prior on the kind and the direction.

The signal takes precedence even when the prior is higher, because the signal states what changed and the prior is only an estimate from the kind and the direction:

| Change | Prior | Signal | Severity |
|---|---:|---|---:|
| Mojo method, signature moved | 75 | `ipc_signature_change` | 80 |
| Mojo method, `[EnableIfNot=is_win]` added | 75 | `build_gate_changed` | 35 |
| chrome://flags removal date slipped | 15 | `flag_expiry_moved` | 10 |
| Blink flag moved test → experimental | 40 | `web_api_status_moved` | 25 |

On an `analysis` run at M148 → M151 the prior is higher than the leading signal on 681 of 6,064 findings. The largest group is a chrome://flags removal date slipping, 245 rows. Taking the higher of the two would rank every one of them above what its signal states.

### Score: what it costs *here*

Score is the severity, or zero. One rule, based on Chromium's build conditions, decides which:

**A declaration Chromium keeps out of the Windows build on every side of the change scores zero.** It cannot move anything in a binary it is not in. 441 of 6,064 findings on an `analysis` run at M148 → M151 are in that state.

Chromium says this in three ways, and the tool reads all three:

| How Chromium says it | Looks like |
|---|---|
| A preprocessor guard | `#if BUILDFLAG(IS_WIN)` |
| A mojom attribute | `[EnableIf=is_android]` |
| A directory name | `chrome/browser/ash/`, `.../android/` |

The second and third are separate rules, not variations on the first. A `.mojom` file has no preprocessor, and a directory Chromium excludes in BUILD.gn contains **no guard anywhere** — the path is the only evidence there is.

The directory rule applies only when *every* declaration of a key sits under such a directory, because five keys at M151 sit both inside and outside one, and deduplication keeps the copy we do not build.

The words *every side* are what the rule turns on. A declaration that **enters or leaves** the Windows build keeps its full severity, because that is the change: a feature whose Windows guard closes is a feature the Windows build loses.

**An unconfirmed removal keeps its score.** A removal is an inference from absence, and absence from files the run did not read is weak evidence. When the new version's read of that kind's files is under 95% of the tree, or the side the evidence comes from has a hole (a target the source did not have, a file that would not parse), the finding carries `unconfirmed` and a reason line, and its score stays at its severity:

```
severity 35 — Preference no longer in the file we read — it may have been
    deleted, orphaning stored values, or simply moved to one of the ~100
    pref files outside the scan
unconfirmed: this run read 0.4% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    upstream cleanup rather than a compatibility break
```

The score is not reduced, because the score and the flag answer different questions. The score and the bucket state what the change costs if it is real; `unconfirmed` states that the evidence for it is incomplete. This also keeps a single meaning for a score of 0: the declaration is outside the Windows build.

Coverage is not applied to additions. An addition is observed directly in the new version, and a partial read of the old version does not change that. An addition is flagged only when the old side has a hole, because the tool then cannot show that the declaration was absent before; the row is filed as Upstream cleanup with `unconfirmed`. The error a partial read produces is a moved declaration reported as a removal, so coverage is applied to removals only.

**A score is its severity, or zero.** The ranking therefore follows from the signal table, and the one case where the two numbers differ is stated in a reason line.

### The five buckets

The leading signal also decides which bucket a finding is filed under, so a row is filed under the sentence it was ranked by.

| Bucket | Meaning | `analysis`, M148 → M151 |
|---|---|---:|
| **Compatibility break** | A contract outside the binary no longer holds, and nothing at build time warns you: stored user data, launch scripts, Finch configs, live websites, the other process | 798 |
| **Behaviour change** | The Windows build behaves differently. Someone can see a difference | 696 |
| **New declarations** | A declaration exists in the new version that did not exist in the old. Nothing is switched on by its existence | 2,979 |
| **Scheduled** | A removal date, not a removal. Chromium has scheduled something for deletion or moved the date. Nothing has happened yet | 302 |
| **Upstream cleanup** | Chromium removed or moved something whose outcome was already settled, or the declaration is not in the Windows build on either side. Nothing observable moved | 1,289 |

All five answer one question: what kind of thing happened. The ranking is the score's job, and upstream's motive is not recorded. Upstream cleanup therefore holds several kinds of row: changes whose outcome was already settled, such as a retired flag or a moved declaration; removals that no signal describes; declarations outside the Windows build on both sides; and absences the run could not confirm, namely removed preferences and switches, and additions the run cannot show are new. It is not the low-score bucket.

Three placements are worth arguing about explicitly, because each decides whether the report stays readable:

**Retired flags are Upstream cleanup, not a compatibility break.** On an `analysis` run at M148 → M151, 344 `base::Feature` flags are removed. 129 had shipped (`flag_retired_on`) and 125 had never shipped (`flag_retired_off`). Neither kind changes what a user sees, so those 254 rows are filed as Upstream cleanup rather than at the top of the report, and the label still says the flag is gone. The other 90 have no readable prior state (`feature_deleted`); the 6 of them in the Windows build are filed as Behaviour change.

**A date is not an event.** `flag_expiring` and `flag_expiry_moved` are the only rows in a report about work that has *not* happened: 302 of the 6,064 rows on an `analysis` run at M148 → M151, 57 and 245 respectively. Filed as cleanup they would read as work that happened and did not matter, which is the opposite of what they say.

**A removal the run cannot confirm is filed by what the evidence supports, and says so on the row.** `pref_left_scan` says "deleted, or moved to a file outside the scan", and which of those it is depends on how much of the tree the run read. Measured on M148 → M151:

| Run | Pref and switch files read at M151 | `pref_left_scan` rows in the Windows build | Bucket | Score |
|---|---:|---:|---|---:|
| `analysis` | 99.4% | 30 | **Compatibility break** | 35 |
| `--partition downloads` | 0.4% | 15 | Upstream cleanup, `unconfirmed` | 35 |

The score is the same on both runs. The bucket and the flag say what each run can support.

The flag describes the run, not the change, so it is a field rather than a bucket. **`unconfirmed`** is a boolean on every row of `report.json`, an outlined badge beside the bucket pill in `report.html` with an `All coverage` filter over it, and a section of its own in `report.md`. It is set on every row whose evidence is incomplete, not only on rows whose bucket changes: only `pref_left_scan` and `switch_left_scan` change bucket, because their own label is an inference from absence, so a flagged Mojo or web API removal stays a Compatibility break. `summary.unconfirmed` counts them — 0 on an `analysis` run at M148 → M151 and 16 on the downloads partition — and says how much of a report is limited by what the run read rather than by what Chromium did.

### Changing the ranking

`SIGNAL_SEVERITY`, `BASE_SEVERITY` and `SIGNAL_BUCKET` in `chromiumdiff/diff.py`, and the 95% threshold `CONFIRMING_COVERAGE` in `chromiumdiff/score.py`, are all plain data. A test holds the three tables to the same set of signals, so a new signal cannot be added to one and forgotten in the others.

---

## 8. Reading the report

### The five counts at the top

On an `analysis` run at M148 → M151:

```
Compatibility break   798   ← a contract outside the binary no longer holds, silently
Behaviour change      696   ← the Windows build behaves differently
New declarations     2979   ← exists now, did not before. Nothing is on by it
Scheduled             302   ← a date, not an event. Nothing has happened yet
Upstream cleanup     1289   ← removals and moves whose outcome was already settled
```

Read in that order. `report.md` gives the first four a table each and gives Upstream cleanup none, because nothing in it needs doing; `report.json` and the sortable table in `report.html` hold it. The flagged rows in it are listed in the Unconfirmed section.

Scheduled has a table of its own because `flag_expiring` and `flag_expiry_moved` are the only rows about work that has *not* happened, and a reader planning the next milestone needs them in one place.

`report.md` also gives a table to every row that carries **`unconfirmed`**, with each row's bucket, because the flagged preference and switch removals sit in Upstream cleanup, which has no table. At M148 → M151 an `analysis` run has none and the downloads partition has 16. They are in Upstream cleanup because the evidence is incomplete, not because the change is minor.

What decides a bucket, and the three placements worth arguing about, are in §7.

`report.json` also carries `meta.missing_targets`, one list per side, naming any file the target set asked for that the source did not have. A target absent from one side and present on the other is what reads as a mass deletion, so the count is restated on every run, including cached ones, and `report.md` names them in *How this was produced*.

Every finding cites **`path:line`** on both sides, not just a filename. `content_features.cc` declares nearly two hundred features, so citing the file leaves the reader to do the finding.

### One table, and every row says what it is

`report.html` is **a single table**, filterable and sortable, because a table lets a reader see every row at once, sort it and search it. Grouping rows by signal instead would produce many groups whose titles are near-synonyms in Chromium's own vocabulary: `Default flipped on`, `Now ON by default on Windows` and `New feature, on by default` are three different signals.

Every row states what it is — the page, the direction, the kind of control — rather than a bare identifier such as `id:cancelButton`:

```
~  feature flag PrefetchPrerenderIntegration — off → on for Windows
   disabled → enabled
                    Now ON by default on Windows │ content/public/common │ 75
```

The marker at the start of the cell: `+` new, `~` changed, `−` gone.

The "what happened" sentence is **the label of the signal that set the severity** for that finding, not the first signal in the list. Pick the wrong one and a row carries one sentence while being ranked by another. A finding with no signal at all — something that just appeared, with no default to move — uses its direction and kind as the sentence (`New feature flag`, `Removed chrome://flags entry`), so every row has one.

### Five clickable triage cards

The five cards at the top are filters: click one and the table below filters to that bucket. The number on the card and the number of filtered rows always match — a test holds that.

### What changed on each screen

The **Where** column answers "where is this" for every row: `settings › privacy_page` for a control, the declaring directory for everything else. `report.md` additionally has a whole section grouped by screen, because the markdown version is read top to bottom and cannot be filtered:

```
settings › ai_page — 13 new · 1 changed · 5 gone
  + section    aiPageTitle
  + link row   skillsSettingLabel
  ~ toggle — glicExperimentalTriggering  (writes glic.experimental_triggering_enabled)
  − page /localNetworkAccess
```

The data comes from the facts: every control carries its screen, page, file, tag and the pref it writes; every route carries its path and guard; every gate carries the handler that sets it. The same loadTimeData key appears once per handler that sets it, so without this column `webuiRefresh2026` shows up as nine identical rows.

### The table: an identifier is not a description

The table has six columns:

| Column | Answers |
|---|---|
| Score | The ranking, with every point explained |
| Bucket | Which triage bucket it falls in |
| What | The direction (`+` / `~` / `−`) and the thing **in words**, not a bare identifier: `feature flag AAPMBlocksWebGPU — off → on for Windows` |
| What happened | The sentence describing what happened |
| Where | The screen, or the declaring directory |
| Kind | The fact kind, with its meaning group |

Direction is a coloured marker at the start of the What cell rather than a column of its own, because one character (`~`) carries it.

### Every score is explainable

```
severity 75 — Now ON by default on Windows
```

```
severity 35 — Preference no longer in the file we read — it may have been
    deleted, orphaning stored values, or simply moved to one of the ~100
    pref files outside the scan
unconfirmed: this run read 0.4% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    upstream cleanup rather than a compatibility break
```

The second is `enterprise_reporting.extension_request.enabled` on `--partition downloads` at M148 → M151. An `analysis` run finds the key in its new file and reports it as moved, not removed. The check is per surface, not per run: on the same downloads partition the 220 removed chrome://flags entries are confirmed, because their only file, `flag-metadata.json`, is read, while a removed preference is not.

The first line is always the severity. It is also the score, unless a line below states that the declaration is outside the Windows build. The other lines state why a row is flagged or filed where it is. §7 describes where the numbers come from and how to change them.

### Analyse everything, render at read time

`report.json` always holds every finding, including Upstream cleanup, and the two rendered files are views of it:

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138
python3 -m chromiumdiff report out/report.json --format both --out out/again
```

Size is not the constraint: the whole of an upgrade is about 4 MB of JSON and `report.md` is about 173 KB. The constraint is human reading time, which is what the buckets and the *What happened* section exist to bound.

### Sixteen fact kinds, three meaning groups

The report groups its filter by *what a change means*, rather than presenting sixteen kinds as a flat list:

| Group | Contains | A change here means |
|---|---|---|
| Feature switches | feature flag, feature param, Blink runtime | Behaviour itself changed |
| External contracts | pref, switch, Web IDL, and all five Mojo kinds | Something outside the binary breaks, silently: stored user data, launch scripts, live websites, the other process |
| UI and scheduling | WebUI route/control/gate, `chrome://flags` | What the user sees changed, or the date something is scheduled for removal moved |

On a real M139 → M143 report, 3,120 findings split 34% / 35% / 30%. So **two thirds of a report is not about features being turned on or off** — reading it as sixteen kinds of "feature" is the most common misreading.

The three groups appear in two places in `report.html`: as a sub-line under each row's `Kind` column, and as the option groups of the `All kinds` dropdown. `report.md` orders its sections by them, because markdown is read sequentially and cannot be filtered. A test holds every fact kind to exactly one group — miss one and its `Kind` column renders empty.

### Context from chromestatus

`enrich/chromestatus.py` fetches the human-written feature descriptions. Matching them per finding barely works — a hit is the exception — because their names are prose and ours are identifiers. So instead of forcing a match, the tool carries the whole "what Chromium shipped in this window" list into the report as background. It is the one source that says what Chromium *intended* to ship, so it sits in the report as context, never as a second opinion on any individual row.

The window is counted back from the version being adopted, and the list is ordered newest milestone first, so the milestone being adopted is never the part that is cut. Truncation happens only in the renderer, which is the only place that knows what it cut, so the count shown is true and `report.json` holds the rest.

---

### Why it changed: the CL and the issue

The two trees say a feature flipped from `disabled` to `enabled`. They cannot say who did it or what they were fixing. `chromiumdiff serve` answers that from Chromium's own review server, one row at a time, and without ever asserting anything the diff does not show.

The chain is four lookups, and none of them is a guess:

```
fact  →  the file that declares it
      →  every merged CL that touched that file between the two versions
      →  the CLs whose diff of that file mentions this identifier
      →  the Bug: footer, and every other CL citing the same issue
```

The middle step is what makes the result usable. A declaration file is shared: **500 merged CLs touched `chrome/browser/about_flags.cc` between the M148 and M151 branch points**, 337 touched `runtime_enabled_features.json5`, and 62 touched `content_features.cc`. Handing a reader 500 CLs for one flag is worse than handing them none. Filtering those 62 by whether the CL's own diff of that file mentions `AndroidCaptureKeyEvents` leaves exactly one — CL 7885356, *"android: Enable AndroidCaptureKeyEvents by default"* — which is the finding in the author's own words.

The panel prints the denominator with the CL, because `1 of 62` is what makes the one mean something.

**The strengths of evidence, and they are never merged into a score.** All but the last two name the fact. Those two name only the file, and the panel says so in words above the list.

| Badge | What it means | What it costs |
|---|---|---|
| `introduced` | inside the fact's own declaration, that CL added the value it ends up with or removed the one it started from | one request per CL |
| `exact` | that CL edited a line carrying this identifier | one request per CL |
| `moved` | that CL renamed the file the identifier is declared in | nothing extra |
| `declares` | a changed line falls inside the declaration this identifier names | one request per CL |
| `described` | the CL's own title or description names it | nothing |
| `crowded` | more than four CLs edited that declaration, so none of them singles it out | nothing extra |
| `touched` | nothing matched the identifier; these are the newest CLs that touched the file | nothing extra |

`introduced` is the only verdict whose answer *is* the change rather than a neighbour of it, and it costs nothing extra because the report already holds what it needs. A finding does not merely name a declaration — it records that declaration's two states, `{"type": ["array<url.mojom.Url>", "array<network.mojom.LinkHeader>"]}` — and the CL that made that change is, by construction, a CL whose diff *adds* a line saying `array<network.mojom.LinkHeader>` inside that declaration. Every other verdict asks "did this CL touch the thing?", which any CL that reformatted the file can satisfy. This one asks "did this CL put the new value there?".

It is the verdict that answers `blink.mojom.TokenError.url`, whose own name is unsearchable because `.mojom` writes `struct TokenError {` and `url.mojom.Url? url;` and never the qualified string. **Zero of its 10 candidate CLs carry the name; exactly one carries the after-value** — CL 7982397, *"[FedCM] Modernize TokenError::url from string to url.mojom.Url"*.

Only the *difference* between the two states is searched for. A value on both sides did not change and would match every CL that touched the declaration for any reason. Values are kept whole when they fit on a line and reduced to the words they gained when they do not, which is how a Mojo method's multi-line parameter list is reached: `CreateLanguageModel` gained `DownloadObserver` and `on_device_model`, and those are single-line strings even though the signature is not.

A value has to look like code to be searched for — an inner capital, an underscore or a dot, or simply be long. `kPreinstalledExtensions`, `IS_ANDROID` and `array<network.mojom.LinkHeader>` identify a change; `enabled`, `stable` and `109` appear in every other declaration in the file and identify nothing.

Measured over the top 150 findings of a real M148 → M151 run: **37 CLs earn `introduced` across 33 rows**, and **29 of those 33 resolve to exactly one CL**.

`described` is free because descriptions arrive with the candidate list, and it is not a weaker copy of `exact` — the two find different things. It is the thinnest of the five, and deliberately so: over the top 150 findings of a real M148 → M151 run only **2 CLs** earn it, both on rows a diff had already answered, and no row rests on it alone. It is worth keeping because a CL can delete the declaration it is named after and leave the identifier in no surviving line, which is the one shape no diff search can reach.

`moved` exists because a pure rename changes no line and is still the whole cause. CL 7810461 renamed `html_or_foreign_element.idl`, so every member of that interface reads as removed at the old path with nothing in any diff to say so — six findings whose only evidence is the rename itself.

`declares` exists because a Mojo method whose parameter list changed has its *name* line untouched — the edit is in the body below it. A fixed number of lines around the name does not find it reliably. A symmetric window 25 lines wide is near every declaration in a file made of declarations: `AIManager.CreateLanguageModel` would draw four unrelated CLs. A window three lines wide, forward only, misses a long parameter list: a method gaining a seventh parameter would match nothing.

The scan therefore follows the declaration's own extent. A declaration's body ends at its own closing delimiter, and that is what is scanned: `struct Bar {` to its matching `}`, `Foo(` to the `);` that closes its parameter list, `Type name;` is the one line. Where neither closes — `runtime_enabled_features.json5` names a feature inside a `{ … },` record and nothing after it ever ends in `;` — the region is the innermost block *enclosing* the name instead. That last rule picks **1 of the 337 CLs** touching that file, and it is CL 7895296, "Return empty styles for getComputedStyle() outside flat tree".

Measured over the top 150 findings of a real M148 → M151 run: **150 of 150 carry a CL** — 94 `exact`, 60 `declares`, 37 `introduced`, 6 `moved`, 2 `described` and 7 `touched` — 206 citations across 129 CLs. **147 of the 150 are named by a verdict; 3 hold leads only.**

**A row keeps every CL that contributed, not the best one.** 40 of those 150 hold more than one, because a flag that launched, was reverted, relanded, reverted and relanded again is five CLs and one change. Two rules follow from that:

- **A strong hit does not remove the `declares` CLs beside it.** A CL that edited the declaration's body without touching the line naming it is a different CL doing different work. The scarcity test that gives `declares` its meaning applies regardless: a crowd of them singles nothing out whether or not a strong hit is present.
- **The list keeps up to twelve CLs, chosen strongest first and then newest, and shows them oldest-first.** In a chain the origin is the oldest CL, so a list of several CLs is read in the order they landed. The cap matches the issue block's, and what it cuts is printed (`15 of 19 merged CLs touched this file, newest 12 shown`) rather than folded into the pool count.

The 40 is a measurement of one run at one budget, not a property of the tool — a smaller `--click-budget` reads fewer diffs and finds fewer of them.

**A row says what would make its own answer less than sure.** Three things can: a request that failed, a candidate list Gerrit returned at its page limit, and a diff budget that declined the file. None of them makes the row wrong, and all three make it unfinished, so the qualifier sits above the answer in every shape the panel can take rather than inside one branch of it.

It is recorded by the lookup rather than by whoever called it, because it belongs to the answer: the run summary records nothing for a lookup of one row.

#### The last two badges, and why a row always answers

That 150 of 150 is a measurement of one slice of one run, not a property of the tool. Five paths can end with a reader clicking a row and receiving no verdict: a name under four characters long, which is unsearchable; a file the diff budget declined; a crowd of CLs that all edited the same declaration; a diff that matched nothing; and a finding whose name is not written anywhere in the file that declares it.

In four of those five the candidate CLs are already known, and `crowded` and `touched` present them. They rank below every badge above them, so they are never reached while real evidence exists, and they can never displace it. The page keeps them apart from evidence in three places: the row gets its own state (`weak`, and the `Has a CL` filter excludes it), the badge is grey rather than borrowing a verdict's colour, and the list is printed under a sentence saying what it is.

**The two do not share that sentence, because they are not the same claim.** `touched` is a lead: these CLs touched the file and nothing ties any of them to the identifier. `crowded` is every CL that edited *this declaration* — which is that declaration's history, so it is ordered oldest-first, headed **How it got here**, and read as the sequence the fact passed through rather than as one citation that failed to appear.

**A row the diff budget declined is not a row that was searched.** Its leads sit over diffs nobody opened, so the verdicts that name a fact were never attempted on it. Such a row says `Nothing here was read — 147 CLs touched this file, more than the run's diff budget would open` and keeps the lookup button, because it can still be answered; filled with `touched` it would read as exhausted.

This is a trade. Eleven CLs edited `ai_manager.mojom` and none of them singles out `AIManager.CreateLanguageModel`, so none of them is cited as `declares`: four confident wrong answers would be worse than none. Showing the eleven as `crowded`, under a sentence saying what they are, gives the reader more than silence, as long as nothing about them reads as a citation.

#### There is no such thing as a change without a CL

The two trees differ, so something landed. An empty row is never a fact about Chromium — it is a fact about this search, and phrasing it as an absence invites a reader to conclude that a declaration changed on its own, which cannot happen.

So the question is asked three ways before the answer is no:

1. **`file:` on main.** The question that works, and the one everything above is built on.
2. **The same file, branch pin removed.** Six weeks of merge-backs land on the release branch after it is cut, and those commits are in the tree being compared. The window's upper bound already admitted their dates — `branch:main` was the only thing hiding them.
3. **The commit messages of the whole window.** Reached only when nothing touched the file at all, because at that point the file question is the wrong question: a declaration can be generated from a template, recorded by Gerrit under another path, renamed in a CL indexed only under the new name, or rolled in from third-party code. What comes back is `described` — the CL names the identifier, and no diff was read to claim more.

A row answered that way says *found by commit message — nothing touched this file in the window* instead of borrowing the file search's denominator, which did not count it.

**What is left is a search that missed, and it says so.** The panel names the three questions it asked and states the conclusion a reader can act on: the CL is recorded under something other than the name or the path held here. The run reports the count (`findings_by_message`, `files_found_off_main`) so a pair of versions where this happens often is visible rather than silently absorbed.

### Why this needs a server, and why nothing else would do

The report is one self-contained file, which is why it can be mailed and why it works air-gapped. It is also why it cannot ask Chromium anything on its own.

The JavaScript in it runs perfectly well from a disk — the filtering, the sorting, the expanding all do. What the browser refuses is to let that JavaScript *read* a response from another site unless that site says it may, with an `Access-Control-Allow-Origin` header. chromium-review does not send one. Every way around it was tried and closed:

| Attempt | Result |
|---|---|
| `Origin: null` (a `file://` page) | no `Access-Control-Allow-Origin` |
| A real `https://` origin | no header either |
| `OPTIONS` preflight | HTTP 400 |
| JSONP (`?callback=`) | ignored; the XSSI-prefixed JSON comes back unchanged |
| gitiles instead of Gerrit | no header, and its path-scoped `+log` and `+blame` answer 401 |

Serving the page over `http://127.0.0.1` does not defeat that rule either — the same page served over HTTP is blocked identically. What it changes is *who asks*:

```
before:  browser ──✗──→ chromium-review

serve:   browser ──✓──→ 127.0.0.1   (same origin; the rule does not apply)
                            │
                            └──✓──→ chromium-review   (Python, not a browser)
```

The browser only ever talks to this process. Python does the asking, and the same-origin rule exists inside browsers to protect your cookies — `curl` and `urllib` were never subject to it.

### What it costs

One request per (CL, file) pair, so the bill is set by how *busy* the declaration files are and not by how many findings exist. Because it is a click that asks, you pay for the rows you open and nothing else: a report costs nothing until you expand a row, and then costs that one file's diffs. Measured on a cold cache, a row at score 45 answered in **5.7 seconds**; over a stratified sample of 183 findings across all sixteen kinds the median file has **8** candidate CLs, and the busiest are `flag-metadata.json` at 662, `about_flags.cc` at 500 and `runtime_enabled_features.json5` at 337.

Everything is cached forever — a merged CL never changes — so the second row in the same file is instant, and so is the same row tomorrow.

**A stored answer is asked again rather than served in three cases.** A stored answer is what makes the second click on a row instant, so the checks run on what was stored and need no flag or version stamp: the lookup lost requests; a CL has no submit stamp, so its list was ordered only by the day; or a CL is dated after the target left main, so it is not in the tree at all. On one real report, 16 of its 60 resolved rows cite a CL of the last kind; asked again, `blink.mojom.TokenError.url` is answered by CL 7982397 at `introduced`.

What a session resolves is written back to `report.json`, atomically, through a temporary file in the same directory. The page is rendered from the report this process holds rather than read off the disk, so a reload shows what the clicks have found and a restart still does. An hour of triage is not lost to a closed terminal. `--no-save` opts out. It reaches `report.md` and `report.html` only on the re-render above: until then those two carry no CL at all, however many the session resolved, so whoever reads the files rather than the screen reads the run's first answer. `serve` prints the command when it stops.

Proving that a token is *absent* is one search over the joined text of a diff, before any line is examined; the 500-row case takes **5.0 seconds**.

### Gerrit responses that need explicit handling

Each case below would otherwise produce a confident wrong answer rather than an error.

- **A renamed file.** Gerrit answers a diff request for the *old* path with `change_type: MODIFIED` and the whole file as one `{"skip": N}` block — no 404, no rename marker. The parser reads the `skip` block as N unchanged lines. A diff with no changed line makes the lookup ask where the CL moved the file, and the fact is followed to the new path as `moved`.
- **A reformat.** A block marked `{"a": [...], "b": [...], "common": true}` is Gerrit saying these lines have the same content and differ only inside the line — a reindent. It is not counted as a changed line, so a CL that reformats a file is not an `exact` match for every declaration in it. A sample of 2,329 diffs holds 49 such blocks.
- **A declined file.** `diffs_read` is set on every row that was asked about, so a row whose file the budget declined is distinguishable from a row that was scanned and matched nothing, and the panel says which.
- **A declaration in two files.** A declaration that moved between files is searched in both, and each CL records which file it was found in.
- **A qualified key.** A `.mojom` writes `struct TokenError {` and `url.mojom.Url? url;`, never `blink.mojom.TokenError.url`, and `url` is too short to search for. Such a fact falls back to its enclosing struct, kept apart from the token set: a changed line mentioning `TokenError` is not a changed line declaring `TokenError.url`, so the struct can earn `declares` but never `exact`.
- **One field list.** The server builds a lookup response with the page's own row renderer and keeps the renderer's `PROVENANCE_KEYS`, so there is one list of fields and the server cannot drop one the page reads.

**The window is taken from the tags, not estimated, and it has two ceilings.** A release tag records where it left main (`Cr-Branched-From:`), so the search starts at the *from* tag's branch point — 2026-04-06 for M148, seven weeks before the tag itself is dated.

The search pinned to `branch:main` stops at the *to* tag's branch point. A CL that lands on main after the release branch is cut is not in the released tree, so it cannot be the cause of anything — and it is not a harmless extra candidate, because it can carry the identifier, earn `exact`, and outrank the CL that really did it. Running this search to the tag date instead admits such CLs: over 105 resolved rows, **38 of 160 cited CLs landed after M151 branched, 11 rows would rank one of them first, and 9 rows would cite nothing else**, and five Autofill flags would be attributed to one cleanup CL that M151 does not contain. Stopping at the branch point removes all of them and roughly halves the candidate pools.

The searches with the pin removed — the merge-back retry and the commit-message search — still run to the *to* tag's own date, because merge-backs keep landing on a release branch for weeks after it is cut and those commits *are* in the tree being compared. M151 branched 2026-06-29 and is dated 2026-08-10, so those six weeks belong to that question and to no other.

**Gerrit stops at 500 rows for an anonymous query and does not say so** — `start=500` returns an empty page that looks exactly like reaching the end. A window that comes back at the cap is therefore split and asked again until the count is established. Where the per-file ceiling still trims the result, the panel prints both numbers. `chrome/browser/flag-metadata.json` is touched by **662** CLs on this pair and the newest 500 are read, so a row declared in it reads *"3 of 662 merged CLs touched this file · 500 of them read"* — found and opened are different claims, and the gap between them is where a missing CL would be.

**A failed fetch is counted, never absorbed.** Gerrit rate-limits with HTTP 429, and a diff that came back empty because of one is indistinguishable, at the point of use, from a diff that genuinely does not mention the identifier. Rate limiting gets its own long retry ladder, and a network failure must never be reported as "no CL found".

**Nearly half of issue links do not open.** Of the 97 distinct issues the top 150 findings of a real M148 → M151 run link, **44 answer HTTP 403** — restricted to Google accounts. An unmarked dead link reads as a broken tool rather than as a restricted issue, so every linked issue is probed once with a `HEAD` (no body either way) and the restricted ones are marked `RESTRICTED` in place. The link is kept, because the reader may have access.

**An issue that opens says what it is about.** The accessibility check is a GET rather than a HEAD because the same request also returns the summary line. issues.chromium.org answers in index-addressed JSON with no field names, so the title is found by the one landmark that is not an index — the array whose second element is the issue number — and verified against eight real issues, all eight correct. A component path is in the response too and it is *not* shown: the same walk gives `Blink>AI` for a MacOS memory regression, so the field is wrong for one of the eight issues checked. For example, `ViewTransitionElement.border_offset` changing from `Vector2d` to `Vector2dF` is shown as: CL 7757059, "VT: Avoid transform rounding in style tracker", against issue 500417362, *"Snapshot positioning pixel rounding error?"*

`Fixed:` and `Bug:` are shown apart, because closing an issue and referencing one are different claims — Chromium writes far more of the latter than the former. `revert_of` and `cherry_pick_of_change` come free in the same response and are printed too: 23 of 534 CLs in a real sample are reverts, and they are what makes a flag's launch–revert–reland history readable without diffing subjects by eye.

### The payload stops repeating itself

Every interaction on the page is under 5 ms — filtering 3,022 rows and repainting takes 4 ms, expanding the heaviest row 0.1 ms — so the cost a reader notices is the download and the JSON parse. `reasons`, `signals` and `group` repeat a small set of strings across rows (66, 63 and 3 distinct values on that 3,022-row report), so each is stored once and referenced by index, which removes about a quarter of the page.

`what` and `paths` are deliberately left alone — they are near-unique per row, so a table of them is the same bytes plus an index. The page puts the five pooled fields back in one pass on load, so nothing downstream knows it happened, and the payload has one reader — `html.payload_of` — rather than a regex in each place that wants it.

### Telling the rows apart

A row that carries a CL and a row that does not look identical in the table. So the table gains an **All evidence** filter — and its states are separate because collapsing them is the mistake the whole stage exists to avoid:

| | |
|---|---|
| **Has a CL** | something was found that names this fact |
| **A diff proved it** | every CL shown was tied to the identifier by a changed line — `introduced` or `exact` |
| **Leads only, nothing names it** | CLs are listed, and none of them names this fact |
| **Scanned, nothing found** | the diffs were read and none matched |
| **Not looked up** | nobody looked |

A 3px edge on the score cell says the same thing while you scroll. The control starts hidden on a report nothing has been looked up in, and the page unhides it the moment a server answers or the first lookup lands.

**An issue opens where the reader asks for it.** Every CL on the row carries its `Bug:` footer, which is free in the search response, so the row can name every issue without asking the tracker anything. The history behind one — its title, whether it opens, and the other CLs citing it — is fetched only when the reader clicks that CL's issue, which is the click that says which CL they think is the right one.

Each one opens in its own box under the CL it belongs to, and a second does not close the first: a reader comparing two issues is comparing them, not toggling between them. Clicking the same chip again closes only that one. Opened from disk, the chip is a plain tracker link.

```bash
python3 -m chromiumdiff serve out/M148_to_M151      # then open http://127.0.0.1:8787/
```

---

## 9. Limits

Stated plainly, so nobody reads a clean report as a clean upgrade.

### Five classes of declaration it does not read, inside files it reads completely

The extractors turn sixteen kinds of declaration into facts. These five are in files the tool downloads and parses without error, and it makes nothing of them — measured at M151:

| Not turned into facts | Count |
|---|---:|
| Web IDL `callback` definitions | 85 |
| Web IDL `typedef`s | 144 |
| Web IDL `Interface includes Mixin` relations | 200 |
| Mojo `feature` blocks | 18 |
| Mojo constants | 311 |

Two real changes that therefore produced no row at all: `typedef LanguageModelMessageValue` changed its underlying union at M143 → M147, and the Mojo constant `kWebNNDirectML` disappeared at M151.

**The coverage figure counts files, not grammar.** A file can be read completely and still hold a declaration class nothing here understands, and nothing is raised when that happens — `extract_stats._errors = 0` means no extractor threw, not that every declaration was recognised. `includes` is the most valuable of the five to add, because it says which concrete interface actually receives a mixin's members.

### The tool reads declarations, not logic

Every WebUI page has two parallel files:

```
downloads_page.html   ← READ     declarations: which controls exist, of what type, bound to which pref
downloads_page.ts     ← SKIPPED  behaviour:    when they show, what happens on click
```

In the `.html` the tool can read:

```html
<template is="dom-if" if="[[autoOpenDownloads_]]" restamp>
    ... the "Clear all" button ...
</template>
```

It knows there is a block guarded by a condition named `autoOpenDownloads_`. But in the `.ts`:

```ts
autoOpenDownloads_ = autoOpen;    // autoOpen is runtime state
```

it **cannot know** when that condition is true — it depends on whether the user has set a file type to auto-open, which is runtime state, not a declaration.

Measured over 332 template files across the eight screens: 602 conditional blocks, 460 `hidden="[[...]]"` bindings, and **37% of controls sit inside a conditional block**. So roughly a third of controls have a visibility condition the tool cannot resolve.

| | |
|---|---|
| A control added or removed | Caught |
| A control changing type (dropdown → toggle) | Caught |
| A control changing which pref it writes | Caught |
| A page added or removed, or its **page**-level guard changing | Caught |
| The logic deciding when a **control** shows | No |
| What a button does when clicked | No |
| How a list is sorted or filtered | No |

Three deliberate reasons for skipping it:

1. **Reading logic is dataflow analysis, not lexical scanning.** Knowing when `autoOpenDownloads_` is true means following callbacks and state sent over from C++. It would break the moment Chromium rewrote a function.
2. **It breaks the "no Chromium checkout" principle.** The declarations are a few dozen megabytes; reading logic means pulling the whole TypeScript tree, and even then it is not enough because the logic continues into C++.
3. **Consistency with the C++ layer.** The tool does not read C++ function bodies either, only declaration macros. Read logic on one side and you have to read it on both — at which point it is a compiler, not a tool that runs in two minutes.

The `route → guard → flag` chain covers the most important part — **page**-level visibility, because Chromium declares that as `loadTimeData` rather than as logic. That is why the Local Network Access case can be traced all the way down. What is not covered is the condition on a **control inside a page**; only comparing screenshots answers that.

### The remaining limits

- **A declaration present in the source tree may still not be compiled into the binary.** The tool does not read the GN graph, so it knows what is *declared*, not what is *built*.
- **A change entirely inside a C++ function body** — the same reason as above, a layer down.
- **Display strings in `.grd`** — a changed label is not caught.
- **Extension APIs.** The `.idl` extension serves three different languages in the Chromium tree: Blink's Web IDL, Chrome Extensions IDL (`chrome/common/extensions/api/`, `extensions/common/api/`) and MIDL (`ichromeaccessible.idl`). The extractor understands only the first, so it reads only under `third_party/blink/renderer/`. Reading the other two with the Web IDL grammar produces wrong facts — 1,081 at M151, 96 of them with an entire nested declaration inside their own signature and the rest labelled "Web API" when no website can call `chrome.fileManagerPrivate`. Reading a dialect wrongly is worse than not reading it; covering the extension surface needs its own extractor and its own fact kind.
- **Everything outside the repository:** server-side Finch configs, launch scripts, test automation.
- **Rendered UI** — no screenshots, no layout, no visual regressions.
- **How often the answer is right, measured rather than asserted.** Over a stratified sample of 183 findings — twelve of each of the sixteen kinds, spread across the score range of a real M148 → M151 run — every one returned at least one CL, and 166 of the 183 carried at least one CL that a changed line or the author's own words tie to the fact. The other 17 are rows whose whole answer is `crowded` or `touched`, which the panel labels as leads in those words.

Two independent checks, neither of which reads the diff the match was made on. On the 28 `base_feature` rows whose default flipped, the direction stated in the CL's subject agrees with the direction parsed from source in 27 of the 27 that state one. On the 84 Mojo and Web IDL rows, the CL's full commit message names the fact in 39; reading the remaining 45 by hand, all but five are unmistakable in the author's own vocabulary rather than the identifier's — `[sub apps] change web api` against `SubAppsServiceRemoveResult.manifest_id`, `[autosizer] Delete the text autosizer` against `TextAutosizerPageInfo`. Both checks under-count by construction and are quoted as floors.

**A CL naming a change is not proof it caused it.** `serve` establishes that a CL edited a line carrying the identifier inside the window — not that this edit is the one the finding is about. A file touched by a rename, a reformat and the real change reports all three as `exact`. The reader still opens the CL.

### What can still be extended

The curated file list names eight `chrome://` screens; the archives reach all 132. Chromium has 132 directories under `chrome/browser/resources/`, but that number is misleading: 39 are debug pages users never see and 9 are ChromeOS-only. **The number worth considering is about 29**, for example `autofill`, `certificate_manager`, `enterprise`, `lens`, `pdf`, `side_panel`, `signin`, `tab_search`, `webauthn`.

Adding a screen is one line in `chromiumdiff/targets.py`:

```python
WEBUI_SURFACES = (
    "settings",
    "history",
    ...
    "pdf",        # ← this line is the whole change
)
```

No new parser needed — the three WebUI extractors are general across screens.

### Adding a new source of truth

Write an extractor with two pure functions, `applies_to(path)` and `extract(text, path)`, register it with one line in `chromiumdiff/extract/__init__.py`, and declare the files to fetch in `chromiumdiff/targets.py`. Nothing else changes.

---

## 10. Environment and troubleshooting

### Operating systems

| Platform | Status | How it was verified |
|---|---|---|
| macOS | Fully working | The whole pipeline, Python 3.14.6 |
| Linux / Ubuntu | Fully working | Ubuntu 24.04 + Python 3.12 and Debian + Python 3.9 in Docker, matching macOS number for number |
| Windows | Works | Not run directly; each Windows-specific failure mode was checked separately — see below |

On Windows, nothing in the source depends on POSIX. The things that usually break a Python tool there were each checked:

- **Console encoding** — this was a real bug, found and fixed. Windows only uses UTF-8 for a real console; the moment output is redirected to a file or a pipe it falls back to cp1252, and reports contain `→` and `·`. The CLI now forces stdout/stderr to UTF-8 at startup, with a regression test that runs the CLI under `PYTHONIOENCODING=cp1252`.
- **Reading UTF-8 files** — every `open()` declares `encoding=` explicitly.
- **Path semantics** — checked directly against the `ntpath` module, including the path-traversal guard when unpacking tarballs.
- **The 260-character limit** — the longest relative path in the cache measures 142 characters. Comfortable, but do not put the project somewhere very deep.
- **Reserved filenames and case collisions** — the whole cache was scanned: no `CON`/`PRN`/`AUX`/`NUL`/`COM*`/`LPT*` names, no pairs of files differing only in case, no `: * ? " < > |` characters.

### Behind a corporate proxy

`urllib` reads the environment variables itself:

```bash
export HTTPS_PROXY=http://proxy.internal:8080
export NO_PROXY=localhost,127.0.0.1,.internal
python3 -m chromiumdiff check          # prints the proxy in use
```

If the proxy terminates TLS and you get `CERTIFICATE_VERIFY_FAILED`, point Python at the internal CA:

```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-internal.pem
```

### Fully air-gapped

Two options.

**Use an internal checkout or mirror.** `--local-src` applies to both refs, so when the two versions live in different directories use `--from-src` and `--to-src`:

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 \
  --from-src /mirror/chromium-148/src \
  --to-src   /mirror/chromium-151/src \
  --no-enrich
```

**Move the cache from a networked machine.** Snapshots are plain JSON:

```bash
# on the networked machine
python3 -m chromiumdiff snapshot 151.0.7922.138
# copy .chromiumdiff-cache/snapshots/*.json to the air-gapped machine
```

### Troubleshooting table

| Symptom | Cause | What to do |
|---|---|---|
| `could not resolve milestone 151` | chromiumdash unreachable | Write the full version. Look it up at chromiumdash.appspot.com/branches |
| `404 …` during snapshot | The tag does not exist | Only released tags are available |
| `GET failed after 4 attempts` | Flaky network or rate limiting | Re-run — the cache keeps what already downloaded. If it repeats, see the proxy section |
| `every target missing for <ref>` | The ref is entirely wrong | Check the ref string; `refs/tags/` is added automatically |
| `snapshot: N facts` with N very small | `--local-src` points at the wrong place | It must point at Chromium's `src/` directory, the one containing `content/` and `third_party/` |
| `missing targets: 1` | The file does not exist at that milestone | Normal. Chromium moves files between releases |
| `cannot diff snapshots built from different target sets` | The two snapshots were built with different `--target-set` | Re-run with the same one. The tool refuses rather than comparing wrongly — if one side is missing whole categories of fact, every fact on the other side reads as an addition |
| `cannot diff: X holds N facts against Y's M` | One side is a truncated tree, almost always a `--local-src` / `--from-src` / `--to-src` pointing at a partial checkout | Point it at a full Chromium `src/` — the directory holding `content/` and `third_party/` — and re-run that side with `--refresh`. Two real versions differ by about 3%, so a gap of half or more is not a change. Compared as-is it would report every fact only the other side has as something this one removed |
| `X produced no facts at all` | The ref is wrong, or the checkout has none of the target files | Same check as above. Nothing can be compared against an empty side |
| `! <ref>: N target(s) absent from that source` | Files the target set asked for were not in that tree | Normal for an older milestone, where Chromium had not created the file yet. Not normal for a local checkout — there it means the tree is partial, and each absent target is a whole file's declarations missing from the comparison |
| `snapshot cache stale (schema N != M)` | The cache was written by an older build | Normal, it rebuilds itself |
| `report.json is schema N, and this build reads M` | The report was written by an older build | Re-run. A report cannot be rebuilt from itself, and an older report's bucket ids may not name the current buckets, so rendering it would print wrong bucket counts |
| `scope: N FILE(S) OUT OF SCOPE` | The tree cache still holds files from a wider earlier run | Re-run that side with `--refresh` |
| Few or no Compatibility breaks on a partitioned run | Expected, and not evidence that nothing is broken | A partition is measured against the whole tree, so a preference or switch it reads only inside its own roots and finds removed is filed as Upstream cleanup with `unconfirmed`, and `summary.unconfirmed` counts them: 16 rows on `--partition downloads` at M148 → M151, where Compatibility break is 2. Changes outside the partition are not in the report at all. Drop `--partition` before concluding anything |
| A finding scores 0 | Chromium's build conditions keep the declaration out of the Windows binary on both sides | Working as intended. Its reasons line says so, and the row is still in the JSON and the HTML table |
| Different result from the last run | A bare milestone number was used | Always pin the full version for anything official |
| (Windows) `FileNotFoundError` while unpacking | Hitting the 260-character limit | Put the project on a short path, or `set CHROMIUMDIFF_CACHE=C:\cdcache` |
| (Windows) `python3` is not a command | Windows names it differently | Use `py -3` or `python` |

### Cache and logs

```bash
CHROMIUMDIFF_DEBUG=1 python3 -m chromiumdiff run …   # print full tracebacks
python3 -m chromiumdiff run … --refresh             # ignore the cache and refetch
export CHROMIUMDIFF_CACHE=/shared/chromiumdiff-cache # put the cache elsewhere
```

A shared cache makes later CI jobs nearly instant. A released tag's snapshot never changes, so it can be shared freely between jobs and between teams.

### Running in CI

```bash
#!/bin/bash
set -euo pipefail
export CHROMIUMDIFF_CACHE=/shared/chromiumdiff-cache

FROM="148.0.7778.217"        # pinned, not a bare milestone number
TO="151.0.7922.138"

python3 -m chromiumdiff check
python3 -m chromiumdiff run "$FROM" "$TO" \
  --out "reports/${FROM}_to_${TO}"

# Block the merge until someone has looked at the breaking changes
BREAKS=$(python3 -c "import json,sys; \
  print(json.load(open(sys.argv[1]))['summary']['by_bucket'].get('contract', 0))" \
  "reports/${FROM}_to_${TO}/report.json")
[ "$BREAKS" -eq 0 ] || { echo "$BREAKS compatibility breaks to triage"; exit 1; }
```

On an `analysis` run at M148 → M151 `summary.unconfirmed` is 0. A non-zero
value means a kind of file was read under 95% or a side had a hole. The
flagged rows keep their scores, and the removed preferences and switches among
them are filed as Upstream cleanup, so they are not counted in `contract`.

---

## 11. Tests

```bash
python3 -m unittest discover -s tests
```

The suite runs with no network.

The fixtures are shortened but structurally accurate excerpts of real Chromium files, including the shapes the parsers have to handle: two-argument macros, defaults wrapped in preprocessor conditions, per-platform states.

Re-run them after any change to `diff.py` or `score.py` — those two hold the classification decisions.

Some tests check no behaviour at all but **internal consistency**, because the most frequently recurring class of bug in this project is one fact derived in two places that then drift apart:

- Everywhere that asks "is this path in scope" must give the same answer.
- Everywhere that asks "could this file declare something" must give the same answer.
- Every naming convention the coverage measurement counts must be claimed by an extractor, and the other way round.
- Every naming convention an extractor claims must be inside the download filter — otherwise the file sits on disk unopened, which looks exactly like a file that does not exist.
- Every measurement gets its own name: "tree coverage" and "area coverage" are two different things.
- The same source tree must produce the same set of facts, whatever order the filesystem returns directories in.
- Every attribute that gets compared must produce a label explaining it; a row with a score and an empty "why" column is unreadable. Checked both synthetically — every kind, every whitelisted attribute — and against two real snapshots.
- Every signal must have a severity, a label **and** a bucket, and every bucket must be reachable. One signal missing from the bucket table would be filed by "something was removed" rather than by what the removal was.
- Every kind and direction must produce a bucket, including the third of a report that carries no signal at all.
- A score is its severity or zero, and on every row `unconfirmed` is set exactly when a reason line starts with `unconfirmed:`. Any other score would mean a rule had been added without a sentence to explain it.
- Every tag the control rule can admit must have a display word, and every word must name a tag the rule admits.
- Every fact must point at the line that declares it, and that line number must survive into the report.
- No command may accept a flag and then ignore it.
- The coverage denominator is the tree, not the roots the fetch list happens to live under. A rule that admits a file while the measurement cannot see it makes the percentage wrong in the flattering direction.
- Two sides of a comparison must have read comparable amounts. Refusing a truncated tree is the same reasoning as refusing two different target sets, one derivation further along.
- No display string may hard-code a coverage number — every run measures and prints its own.

### Checking against real data

Unit tests show that the code does what its author intended. To check the extractor against Chromium itself, an independent method — strip every preprocessor directive, split on `;`, different regular expressions — was applied to `content_features.cc` between M148 and M151:

```
Independent method :  19 added,  9 removed
The tool reports   :  19 added,  8 removed
```

The difference is one feature that moved from `content_features.cc` to `media_switches.cc`. The tool reports it as `declaration_moved`; the independent method reads one file and counts it as removed.

---

## 12. Source layout

```
chromiumdiff/
  acquire.py      fetch source over Gitiles or from a local checkout
  targets.py      declares which files to fetch and why; partitions; coverage rules
  snapshot.py     combines fetch + extract into one cached snapshot
  extract/        the extractors, and the C++/GRIT/mojom condition scanner
  diff.py         semantic comparison, labelling, severity, bucketing
  cluster.py      assemble scattered fragments into one change
  score.py        the Windows build rule, the unconfirmed flag, and the reasons
  catalog.py      measure what the target set is missing; check reference closure
  model.py        shared data structures, the five buckets, JSON read/write
  eligibility.py  one policy for what is product code, shared by discovery and extraction
  jsonc.py        hand-written JSON5 reader
  report/         markdown + self-contained HTML dashboard;
                  groups findings by what happened and by screen
  enrich/         context from chromestatus; the CL and issue behind a change
  serve.py        localhost server that resolves a row's CL on demand
  cli.py          the command-line entry points
```

The whole pipeline is a straight line of pure data transforms:

```
Snapshot(ref)            ->  [Fact]      extract/
(Snapshot, Snapshot)     ->  [Change]    diff.py
[Change]                 ->  [Finding]   score.py
[Finding]                ->  [Finding+]  cluster.py, enrich/
[Finding]                ->  report      report/
```

Every stage reads and writes JSON, so any stage can be run, inspected and re-run on its own. That matters here because the expensive stage (network) and the stage you keep tuning (ranking, reporting) have completely different cost profiles.

`model.py` holds a `SCHEMA_VERSION` constant. It is bumped whenever a cached artifact stops meaning what an older build thought it meant, with a note saying exactly what was silently wrong — so old caches are rebuilt instead of misread.

---

## Further reading

- The two history lookups are `chromiumdiff why` and `chromiumdiff cl`, both in
  [chromiumdiff/history_cli.py](chromiumdiff/history_cli.py). Either skill
  calls them, because a command belongs to the tool and not to a skill, and
  each skill keeps its own references. Cross-skill handoffs name the skill and
  its task rather than reaching into its directory.
- `chromiumdiff why --retry` repeats a lookup with cached successful requests;
  `--refresh` refetches Gerrit data. Text and JSON disclose incomplete lookups
  (exit 3); input/save failures return 2. `chromiumdiff cl --offset N
  --limit N` pages matching file diffs and reports omitted files.
- Root-cause evaluation uses `review prepare-trial --task-type root-cause`,
  `root-assessment-template` and `root-evaluate`. Source-pinned cases and
  separately held rubrics are described in the [evaluation protocol](docs/review-evaluation.md).
- **[skills/analyzing-chromium-upgrades/SKILL.md](skills/analyzing-chromium-upgrades/SKILL.md)** — the knowledge pack for an agent: the triage procedure, the signal reference, and the traps verified against real data. The valuable part is not how to run the commands, but the knowledge that stops an agent reaching a wrong conclusion.
