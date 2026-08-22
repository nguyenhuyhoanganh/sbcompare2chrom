# chromedrift

A tool that compares two Chromium versions and answers one question: **what actually changed, and how much does each change matter.**

The target product is a Chromium-based desktop browser on Windows, which is why the platform is fixed rather than selectable. Everything here is plain Python (10,879 lines, 30 files), no third-party libraries, no `pip install`.

There is exactly one other document: **[docs/pipeline.html](docs/pipeline.html)** — open it in a browser, no network needed — which follows one real change through every stage of the pipeline, with the vocabulary defined and each kind of file explained. This README says what the project is and how to use it; `pipeline.html` says how it works inside.

---

## Contents

1. [The problem](#1-the-problem)
2. [Quick start](#2-quick-start)
3. [What stands between the code and the user](#3-what-stands-between-the-code-and-the-user)
4. [What the tool reads](#4-what-the-tool-reads)
5. [Coverage: how much of the tree gets read](#5-coverage-how-much-of-the-tree-gets-read)
6. [Seven commands](#6-seven-commands)
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

So the real problem is not "how do we compare them" but **"how do we filter down to the part that means something"**. That is what chromedrift does.

### Three design principles

**No Chromium checkout.** A full one is about 100 GB and hours of syncing. The tool only needs a few thousand declaration files — the ones that list what exists, what it is called, and whether it defaults on or off. Chromium serves individual directories over Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<version>/<directory>.tar.gz
```

About 40 MB per version with the default target set. A team that already has a checkout or an internal mirror uses `--local-src` instead; nothing else changes.

**Normalize first, compare second.** Between M139 and M143, Chromium changed how the feature-declaration macro is written:

```cpp
// M139 and earlier
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);

// M142 onwards — the string name is derived from the variable name
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
```

In a single file, M139 has 170 of 170 declarations in the old form and M143 has 12 of 187. A tool that compares source text reports "170 features deleted, 187 features added" — which is meaningless. chromedrift normalizes `kBackForwardCache` to `"BackForwardCache"` before comparing, and gets a readable answer: 152 unchanged, 18 dropped, 35 added.

**Stop at the evidence.** The deterministic stages — extract, normalize, compare, rank — turn several million changed lines into a few thousand labelled changes, sorted so the ones that cost something are at the top, and then stop. The tool does not conclude "this means X for the product". That takes judgement about a particular product, and it belongs to whoever reads the report, or to an agent running the [`analyzing-chromium-uprevs`](skills/analyzing-chromium-uprevs/SKILL.md) skill. chromedrift's job is to make that input complete, ranked and citable.

It is also why nothing in the tool describes *your* codebase. An earlier version took a config file naming the files you patch and the symbols you reference, and added points when a change touched one. It was the right idea and it could not be supplied honestly: with no config the scoring collapsed into a second copy of the severity, its top bucket was unreachable by construction, and 1,384 of 2,800 findings landed in a bucket called "New opportunity" whose rule was "anything added". What is left is what two Chromium trees can establish on their own, and the step it does not take — searching your own tree for the identifier a finding cites — is one command you run yourself.

---

## 2. Quick start

### Requirements

| Item | Requirement |
|---|---|
| Python | 3.9 or newer. No 3.10+ syntax. Tested on 3.14.6 |
| Third-party libraries | None. Standard library only |
| Free disk | ~150 MB for two versions with the default target set |
| Network | Three HTTPS hosts, see the table below. All skippable with an internal checkout |
| Chromium checkout | Not needed |

| Host | Used for | Required |
|---|---|---|
| `chromium.googlesource.com` | Fetching source by tag | Yes |
| `chromiumdash.appspot.com` | Resolving `151` to `151.0.7922.138` | No, if you always write the full version |
| `chromestatus.com` | Feature summaries and spec links | No, skip with `--no-enrich` |

### Installing

There is no build step. Copy the directory to the target machine and it runs:

```bash
tar czf chromedrift.tgz chromedrift/ tests/ skills/ docs/ README.md
# on the target machine
tar xzf chromedrift.tgz && cd chromedrift
python3 -m chromedrift --version
```

On Windows use `py -3` instead of `python3`.

### Checking the machine

Run this first on any new machine. It checks everything that commonly breaks, in one pass, instead of letting you discover each failure two minutes into a run:

```bash
python3 -m chromedrift check
```

```
python
  [OK  ] version 3.14.6
cache directory
  [OK  ] /path/.chromedrift-cache writable — 68 GB free
network
  [OK  ] gitiles (source) — HTTP 200
  [OK  ] chromiumdash (version resolution) — HTTP 200
  [OK  ] chromestatus (enrichment, optional) — HTTP 200

ready
```

Exit code `0` means ready, `1` means there is a FAIL line to deal with — usable in CI as a preflight step.

### Smoke-testing the pipeline (~10 seconds)

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --target-set minimal --no-enrich
```

`minimal` fetches three files — enough to confirm the pipeline is wired up.

### A full run

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

About three and a half minutes on a cold cache. Measured per version: 97 seconds, of which 69 are fetching and 25 are the fourteen directory listings, leaving about 3 for extraction — so two versions plus enrichment. A second run over the same pair of tags is a cache hit, measured at **0.3 seconds** for the whole pipeline: both snapshots read, 3,022 changes compared and ranked, and all three report files written. A released tag's content never changes, so the cache is kept forever, and network speed is the only reason your cold number will differ.

Results land in `out/M148_to_M151/`:

| File | Size | Use it for |
|---|---|---|
| `report.md` | ~118 KB | Pasting into Jira, Confluence, a merge request |
| `report.html` | ~2.0 MB | Opening in a browser; filterable and sortable, fully self-contained |
| `report.json` | ~4.2 MB | Scripts, dashboards, comparing across cycles |

`report.html` loads no external resources, so it works on an air-gapped network and can be attached to an email.

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

Every surface is one or the other:

| Surface | What holds the door | Code change and user-visible change land together? |
|---|---|---|
| `base::Feature`, Blink runtime flags | the flag's own default, per platform | No — usually several releases apart |
| chrome:// screens | a `loadTimeData` boolean, which resolves to a flag | No — same as above |
| Web IDL | `[RuntimeEnabled=Foo]`, on the member **or** its interface | Sometimes — 133 of 220 added members at M148 → M151 are reachable on arrival |
| Mojo | nothing. `[EnableIf]` decides which *platform* compiles it, not who can see it | **Yes** |
| Preferences, command-line switches | nothing | **Yes** |

Both halves are large, and the second carries the higher severities: at M148 → M151, **220 of the 276 Breaking rows are Mojo or web API**. The report is ordered to keep them apart — `report.md` opens with **Who has to do something**, and the first list in it is Mojo.

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

**Step 1.** Compare the settings page list, and `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` is gone. Read naively: "Chromium removed the Local Network Access page" — an important privacy page. Enough to alarm the whole team.

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

- **M148 → M151, Windows:** 145 flags removed — 72 that had shipped, 60 that were abandoned, 6 whose prior state is unreadable. None of the first two groups changes behaviour. Labelling all 145 "feature lost" makes most of the alert list a false alarm.
- **M139 → M143, web layer:** of 202 features that "disappeared", 170 were already stable — the flag was cleaned up after the feature shipped successfully.

A tool that puts 170 false alarms at the top of the list loses all credibility on its first run.

---

### Half two: there is no gate, and nothing warns you

Mojo, preferences and command-line switches have no gate at all. There is no stage A, no remote rollout, no milestone where it quietly becomes true. **The declaration is the contract, and changing it changes the contract on the day you adopt the version.**

What makes this half dangerous is not that it is fast. It is that **nothing tells you**:

```
blink.mojom.PublicKeyCredentialRequestOptions.challenge
    array<uint8>?  →  array<uint8>
```

A WebAuthn message field stopped being nullable. Nothing in Chromium warns about this, and it does not break the build: both ends of a Mojo interface are generated from this same file, so they always agree with each other. It breaks whatever is on the *other* side that was not regenerated — which is why the tool scores it 80 and why trap 10 exists to say who that other side actually is.

Preferences and switches fail the same way, one step further out. Chromium **ignores a command-line switch it does not recognise** — no warning, no error, no log line — so a launch script keeps starting the browser exactly as before and the flag it passes stops doing anything at all.

For this half, the questions from half one are not just unhelpful, they are misleading. "Did the flag state change?" has no answer here, and answering "no" reads as "then nothing happened". Traps 9 to 12 are written for these surfaces, and the per-owner decision procedure in the skill branches on the surface before it asks anything.


### Assembling the fragments into one story

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

Read line by line they contradict each other: one says a page was removed, the next says a page appeared. Read as one group they say something simple and true.

`cluster.py` groups them using **links the data itself declares**, not name similarity:

```
route  --names its guard-->  gate  --names its feature-->  base_feature
control  --names its label-->  route
feature_param  --names its owning feature-->  base_feature
blink  --names its base_feature-->  base_feature
```

Each arrow is a real field. The seventh fragment — `blink_runtime LocalNetworkAccessSplitPermissions` — deliberately stands apart, because its fact declares `base_feature: "none"`: Chromium is saying outright that this flag has no matching C++ feature. A similar name is not a relationship.

On the M148 → M151 run: **72 clusters, the largest 7 fragments**. The report has a *Related changes, grouped* section ordered by the highest score in each cluster.

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
| `webui_routes.py` | `route.ts` | The page list of a `chrome://` surface, with its visibility conditions |
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

**What counts as a control is a rule, not a list of names.** It used to be 27 tag names typed out by hand, and it decayed the way every hand-written list here has decayed. Measured at M151 across the eight surfaces the default target set reads, 471 distinct custom elements appear in the templates 2,462 times, and the list matched 902 of those (36%) — while 41 of the misses bind a real preference, which makes them controls by definition. `settings-collapse-radio-button` writes one 27 times, and `report/wording.py` already carried a display word for that exact tag, so the renderer knew about a control the extractor never produced.

An element is a control when it binds a preference; or when a hyphen-separated segment of its tag names an interactive component *and* it has a stable identity (an element id or a label); or when it is one of the structural units a page is built from. Matching segments rather than substrings is what separates `cr-icon-button` from `cr-icon`. Requiring an identity is what makes widening free: an element with no preference, no id and no label can only be identified by its position, which churns whenever a template is reordered. The rule beats the list it replaced on every axis — 971 controls against 971, 190 preference-bound against 156, and position-only identities down from 130 (14%) to 15 (1%).

**Identity has to be specific enough to tell things apart.** A loadTimeData key is not unique: at M151, 62 of 668 keys are set by more than one handler — `undoDescription` by both `bookmarks_ui.cc` and `downloads_ui.cc` — and 27 of those set different values. Controls are the same: 98 of 1,256 keys collide between files in the same directory, like `id:nicknameInput` existing in both `credit_card_edit_dialog` and `iban_edit_dialog`. When keys collide one copy is dropped, and which one survives depends on directory walk order. So a gate carries its handler name and a control carries its file name: that recovered 318 declarations that were being thrown away. Routes still join to gates by the bare key, so the three-hop chain is unchanged.

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

The second row is why the tool exists: reading the wrong one is not a small error, it inverts the conclusion. The third row matters too: when the condition depends on a non-platform buildflag, the three-valued evaluator answers "undecidable" rather than guessing.

### The platform is fixed, not an option

The product is a desktop browser on Windows, so **there is no `--platform` option**. That is deliberate: an option nobody checks is a way to be silently wrong, and as above, being wrong here inverts the conclusion.

Other platforms' macros are still recognised, but so they evaluate to *false* rather than "undecidable":

```python
eval_condition("BUILDFLAG(IS_WIN)")          # True
eval_condition("BUILDFLAG(IS_ANDROID)")      # False  — definitely not us
eval_condition("BUILDFLAG(ENABLE_PLUGINS)")  # None   — no guess
```

Build conditions are resolved for Windows everywhere they appear, not only in feature macros: an `#if` around a pref or switch constant (115 keys at M151 are not in the Windows build), and a GRIT `<if expr="...">` around a WebUI control (14 controls). One three-valued evaluator, two dialects — `not is_win` and `!BUILDFLAG(IS_WIN)` ask the same question.

Other platforms' trees (`ash/`, `chromeos/`, `ios/`, `fuchsia/`) are skipped, **with one exception**: string constants are read wherever they live. A pref key is identified by its string, and Chromium is currently splitting `chrome/common/pref_names.h` apart. When a key moves into a ChromeOS file we cannot see, the tool reports it as deleted — and a deleted pref means every existing user's stored value is orphaned. Measured M148 → M151: of 141 keys that vanished, 100 had simply moved there.

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

Every attribute that gets compared can produce a label like this. That is a rule, not an aspiration: an attribute is in the whitelist because someone decided it means something, so if it moves and the report says nothing, that row is unreadable. Measured M148 → M151, **380 of 709 "modified" changes used to arrive that way**; a test now blocks it, and the same test found nine more attributes drifting out from under it — a `base::Feature`'s build guard among them, 55 rows in M143 → M148.

The last four labels are the dangerous kind: **compiles clean, tests green, and breaks in the field** — or breaks the build right after the merge, at the latest possible moment.

`diff.py` also detects renames. For prefs and switches, identity is the string, while the C++ variable name stays put; so a rename shows up as an unrelated removal plus an unrelated addition. Pairing them by variable name reveals what really happened. A real case:

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);   // lowercase r
// M143 — the macro derives the name from the variable
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   the string name is now "FedCmIdPRegistration"                  // uppercase R
```

Nobody edited a name — changing the macro changed it. Every server-side field-trial config and every `--enable-features` flag using the old spelling **silently stopped working**. No compile error, no warning.

When a pref or switch disappears and cannot be paired, the tool does **not** claim it was deleted. It labels it `pref_left_scan` / `switch_left_scan`, meaning "left the scanned scope" — possibly deleted, possibly moved to a file we do not read. On the M148 → M151 run with the default target set, all 139 vanished prefs carried that label.

---

## 5. Coverage: how much of the tree gets read

### Every run measures it

A hand-written file list is only correct for the version it was written against. Build the list as it stood at M130 and run it at M151, twenty-one milestones later, and it misses 27% of the pref files and 34% of the feature files that exist there. A third of the coverage evaporates over two years, silently — a file nobody listed is a file nobody notices.

So on every run the tool asks that version's own tree what exists, and measures the target set against it. Gitiles returns a recursive listing of a directory in one request, so fourteen roots cost about 24 MB and 21 seconds, cached forever because a tag's tree never changes.

The result is printed on every run, stored on the snapshot, and carried into the report — `report.json` at `meta.coverage` (`{from, to}`, one measurement per side) together with the unread paths at `meta.uncovered_files`, and `report.md` in its closing *How this was produced* section:

```
coverage: reads 3677 of 8366 files in this tree that could declare (43% of files)
  largest gaps: chrome/browser/ (251 files), components/enterprise/ (50 files)
  to read these too, run `--target-set wide`: about 337 MB per version instead of 40
```

**The numbers in this document are a measurement taken at M151. The number to trust is the one your run prints.**

### Three target sets

| | Downloaded | Kept on disk | Declaration files read | Use it for |
|---|---:|---:|---:|---|
| `minimal` | ~300 KB | ~1 MB | 3 files | Smoke tests, CI wiring checks |
| `default` | ~40 MB | ~38 MB | 3,677 / 8,366 (43%) | Day-to-day work |
| `wide` | ~337 MB | ~110 MB | **8,295 / 8,366 (99%)** | The widest read available |

5% sounds terrible, but **file count is not declaration count**. The hand-picked files are the big ones. Measured at M151:

| | `default` | `wide` |
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
| **Total facts** | **29,118** | **54,298** |

So `default` reads 43% of the files but more than half of the `base::Feature` declarations, and the share is very uneven between surfaces: nearly all the Web IDL, a quarter of the Mojo, a fiftieth of the pref and switch files. That is a deliberate trade, not a defect — but when the answer genuinely matters, run `wide`.

`wide` reads 99%, and the figure is worth explaining because it has been wrong twice, in the same way both times: **the denominator was a second list, maintained beside the thing it was meant to measure.** First it counted the roots the fetch list lived under rather than the tree, so 139 files the rule admits sat outside the measurement. Then it counted only two filename conventions — prefs, and features-and-switches — while the extractors grew to read `.mojom`, `.idl` and the WebUI templates. That let it report `1,164 / 1,164 (100%)` while 3,798 files carrying **72% of a report's facts** were not being counted at all.

There is no second list now. The denominator asks each extractor whether it would read the file, so an extractor added tomorrow widens the denominator by existing, and the two cannot disagree. The remaining 1% has names — `chrome/services/`, `chrome/credential_provider/`, `chrome/installer/` — and the run prints them.

What was wrong was the **denominator**. It was built from the fourteen directory roots the fetch targets happen to live under, so the measurement graded `wide` against exactly the ground `wide` already covered and could only ever return 100%. `chromedrift catalog`, which walks the real tree, counted 1,192 files the same rule admits. The 153 in the gap were invisible to every run however wide, and they were not obscure — `base/base_switches.h`, `base/features.cc`, `cc/base/features.cc` (the compositor), `device/fido/public/features.cc` (WebAuthn), `sandbox/policy/features.cc`, `google_apis/gaia/gaia_switches.cc`. Three of those files alone held 88 `base::Feature` declarations no target set was reading.

Once the denominator became the tree, the answer came back 88%, and the 139 files it was missing had names. They are now fetched — `base/`, `device/`, `cc/`, `sandbox/`, `storage/`, `google_apis/`, `pdf/`, `mojo/` and Blink's `renderer/platform` — for 22 MB per version on top of 315. Two of them were free: the Blink `renderer/core` and `renderer/modules` archives were already being downloaded for their `.idl`, and the 22 declaration files inside them went unread only because the filter asked for one suffix.

```
coverage: reads 8295 of 8366 files in this tree that could declare (99% of files)
  largest gaps: chrome/services/ (24 files), chrome/credential_provider/ (15 files)
```

Fourteen files went the other way, excluded by name rather than fetched: the headless shell, Chrome Remote Desktop, the updater, the enterprise companion, the Windows services, and Fuchsia's own tree, which the platform rule had been missing by one suffix. They are binaries that ship beside the browser rather than being it, so their switches reach none of our users — the same reason `content/shell/` has always been excluded.

Vendored third-party projects — abseil, grpc, zlib, the WebRTC overrides — are excluded by name rather than by falling outside a root. Fourteen of their files match the naming conventions, they are other people's libraries rather than Chromium's product surface, and naming the exclusion is what keeps `catalog` and the per-run measurement describing one population.

That suffix list now exists exactly once (`targets.READABLE_SUFFIXES`), shared by `wide` and `--complete`, because both ask the same question: which filename shapes can an extractor read.

### Partitions: bounding what is fetched and scanned

When you only care about one area, `--partition` bounds both the fetching and the reading:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --partition downloads
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --partition settings --partition bookmarks
```

Available: `settings, downloads, bookmarks, history, extensions, passwords, printing, newtab, webplatform, network, media`.

A partition is a **filter over the target list**, not a second list to maintain — add a target and it flows into whichever partitions its path matches. A few entries are kept in every partition because they are cheap and relevant to everything: `pref_names.h`, `flag-metadata.json`, `content_switches.cc`.

A partitioned run prints its own coverage, measured against exactly the roots that partition fetches:

```
$ python3 -m chromedrift snapshot 151.0.7922.138 --partition downloads
coverage: reads 3 of 6 files in this tree that could declare (50% of files)
snapshot: 2692 facts
```

**The trade has to be stated plainly:** a partition is faster and less complete, in one direction only. Chromium is not organized by product feature — a change affecting Downloads can live in `content/`, in a Mojo interface, or in a flag file matching no partition at all. Right while iterating on one area; **wrong as a release gate**.

Add `--complete` and the partition fetches whole directory roots instead of filtering a file list, so coverage inside those directories is complete by construction. Measured at M151: `--partition extensions --complete` reads 19 of 19 files. The option is refused for partitions whose roots are entire subsystems (`webplatform`), because Gitiles serves a whole directory or nothing.

### Measuring with a blobless clone — the `catalog` command

`catalog` answers the same question from a different source: a clone that downloads no file contents gets Chromium's entire tree structure in seconds.

```bash
python3 -m chromedrift catalog 151.0.7922.138
```

It uses **the same rule** as the per-run measurement, so the two numbers describe the same population, and it names every missing file so they can be added in priority order.

### Two meanings of "complete"

| Question | Can it be answered |
|---|---|
| Did we read every declaration **inside** an area's directories? | **Yes** — with `--complete`, or `--target-set wide` for the whole tree |
| Did we read every feature that **belongs to** that area? | **No** — every area references things outside itself |

For example: every declaration in `chrome/browser/resources/settings` is readable, but a feature shown on the Settings page may be controlled by a flag declared in `content/`. That is why the report has a *reference closure* section — it walks every link the data itself declares and lists the ones pointing at something absent from the snapshot.

---

## 6. Seven commands

```bash
python3 -m chromedrift check      # verify this machine can run the pipeline
python3 -m chromedrift snapshot   # extract the feature surface of ONE version
python3 -m chromedrift diff       # semantic comparison between TWO versions
python3 -m chromedrift run        # the whole pipeline: snapshot → diff → rank → report
python3 -m chromedrift report     # re-render a saved report.json
python3 -m chromedrift catalog    # measure which files the target set is missing
python3 -m chromedrift figures    # write docs/figures.json from a report
```

Splitting them up is not decoration. The expensive stage (fetching) and the stage you tune repeatedly (ranking, reporting) have completely different cost profiles. Being able to re-run the cheap half against a warm cache is the difference between a tool people tune and a tool people run once.

`figures` exists because every measurement in this README and in `pipeline.html` used to be maintained by hand, and six of them were corrected in a single working session — four having been written wrong by the same hand that corrected them. The numbers now live in `docs/figures.json`, written from a real run, and a test holds the prose to that file. It needs no report of your own to run, so it works on a fresh clone; when a report *is* present it also checks the file against it, so the file cannot become the thing that goes stale.

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --out out
python3 -m chromedrift figures out/report.json --wide out-wide/report.json
```

Each command accepts only the options it actually uses. `catalog` has no `--local-src`, `check` has no `--partition` — a command that accepts a flag and ignores it is a bug, and a test blocks it.

---

## 7. How a change is ranked

Two numbers travel with every finding, and the gap between them is the point.

### Severity: what this kind of change costs

Severity comes from the **leading signal** — the label with the highest weight among the ones the comparison attached. When a change carries no signal at all, and only then, it comes from a coarse prior on the kind and the direction.

That order matters, and it used to be the other way round. Severity was `max(prior, signal)`, so the guess overrode the statement whenever the guess was higher — which is exactly when the guess was wrong:

| Change | Prior | Signal says | Old | Now |
|---|---:|---|---:|---:|
| Mojo method, signature moved | 75 | `ipc_signature_change` | 80 | 80 |
| Mojo method, `[EnableIfNot=is_win]` added | 75 | `build_gate_changed` | **75** | **35** |
| chrome://flags removal date slipped | 15 | `flag_expiry_moved` | **15** | **10** |
| Blink flag moved test → experimental | 40 | `web_api_status_moved` | **40** | **25** |

Measured against two real pairs, the prior overrode the signal on 267 of 2,800 findings at M148 → M151 and 345 of 6,787 at M143 → M151 — every one of them upwards. The largest group is the smallest change the tool reports, and the most wrong is four Mojo methods ranked as ABI breaks for a build condition moving.

### Score: what it costs *here*, on *this* run

Score is the severity after two adjustments, both of them facts rather than opinions:

**A declaration Chromium keeps out of the Windows build on every side of the change scores zero.** It cannot move anything in a binary it is not in. 187 of 3,022 findings at M148 → M151 are in that state.

Chromium says this in three different ways, and for a long time the tool read only the first:

| How Chromium says it | Looks like | Read since |
|---|---|---|
| A preprocessor guard | `#if BUILDFLAG(IS_WIN)` | always |
| A mojom attribute | `[EnableIf=is_android]` | schema 27 |
| A directory name | `chrome/browser/ash/`, `.../android/` | schema 28 |

The second and third are not variations on the first. A `.mojom` file has no preprocessor, and a directory Chromium excludes in BUILD.gn contains **no guard anywhere** — the path is the only evidence there is. So `platform_state` sat on four of the sixteen fact kinds, none of them Mojo, and an Android-only field changing type scored 80 at the top of a Windows report. On a wide M148 → M151 run, 164 findings were declared under a platform we do not build and not one of them scored zero.

The directory rule applies only when *every* declaration of a key sits under one, because five keys at M151 sit both inside and outside — and deduplication keeps the copy we do not build.

The words *every side* carry the whole rule. A declaration that **enters or leaves** the Windows build keeps its full severity, because that is the change. The previous version read the new side only, so a feature whose Windows guard closed — the case where we lose the feature — was scored *down* 45 points for not being in the Windows build.

**An unconfirmed removal loses 15.** A removal is an inference from absence, and absence from a tree the run read part of is a much weaker claim than absence from one it read all of. So a removal is discounted unless the run read essentially the whole tree, and the finding says which:

```
severity 35 — Preference no longer in the file we read — it may have been
    deleted, orphaning stored values, or simply moved to one of the ~100
    pref files outside the scan
-15 unconfirmed: this run read 1% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    housekeeping rather than breaking — --target-set wide settles it
```

Additions are not discounted. An addition is a thing seen rather than a thing not seen, and "it may have existed in a file we did not open" does not make it any less present in the version being adopted. The asymmetry is the documented failure mode of this tool, not a hypothetical one: what goes wrong on a partial read is removals reading as deletions.

**Nothing raises a score.** Severity is the ceiling — the most this kind of change can cost — and the adjustments only take away, each with a sentence beside it. So a reader who understands the signal table understands the ranking, and every point of difference between the two numbers can be argued with.

### The five owners

The leading signal also decides **whose desk a finding lands on**, which is the axis that decides whether a reader keeps reading. The bucket says how bad and the consequence group says what kind of consequence; neither says whether a row is yours.

| Owner | What it holds | M148 → M151 | of which Breaking |
|---|---|---:|---:|
| Process boundaries | Mojo interfaces, methods, structs, fields, enums | 339 | **126** |
| Web platform | Blink IDL and the runtime flags gating it | 719 | 94 |
| Browser C++ | feature flags, prefs, switches, chrome://flags entries | **1,157** | **2** |
| WebUI front-end | routes, templates, the booleans gating them | 277 | 1 |
| Outside the repository | Finch configs, launch scripts, automation, policy | 530 | 53 |

The two middle columns point opposite ways, which is the reason to split at all: the longest list carries two of the 276 Breaking rows and the second shortest carries 126.

Routing is by surface, except where the fix is somewhere other than the declaration. A renamed C++ constant stops the build and is fixed in the file beside it; a renamed Finch string compiles perfectly and is fixed in a server-side config nobody can see from this repository. Those are one event to a diff and two jobs on two desks, and only the second can sit unnoticed for a milestone — so eight signals override their surface and route to **Outside the repository**, which owns nothing and is where the silent failures collect.

### The four buckets

The leading signal also decides which bucket a finding is filed under, so a row is filed under the sentence it was ranked by.

| Bucket | Meaning | M148 → M151 |
|---|---|---:|
| **Breaking** | Something outside the binary stops working, and nothing warns you: stored user data, launch scripts, Finch configs, live websites, the other process | 276 |
| **Behaviour change** | The Windows build behaves differently. Someone can see a difference | 469 |
| **New surface** | Surface that did not exist before. Nothing is switched on by it on its own | 1,240 |
| **Housekeeping** | Chromium tidying up after itself, and scheduling. Nothing observable moved, or the tool cannot tell that anything did | 1,037 |

Two placements are worth arguing about explicitly, because both are the difference between a report people read and a report people stop opening:

**Retired flags are Housekeeping, not Breaking.** At M148 → M151, 145 `base::Feature` flags are removed — 72 that had shipped, 60 that were abandoned — and not one of them changes what a user sees. Filing them as breakage puts 132 rows at the top of the report of which none is actionable. The label still says the flag is gone.

**An unconfirmed disappearance moves bucket with the coverage.** `pref_left_scan` says "deleted, or moved to a file outside the scan", and which of those it is depends entirely on how much of the tree the run read. Measured on the same pair of versions:

| | Coverage | `pref_left_scan` | Bucket | Score |
|---|---:|---:|---|---:|
| `default` | 5% | 139 | Housekeeping | 20 |
| `wide` | 100% | 171 | **Breaking** | **35** |

A rule that produced the same answer either way would be wrong in one of the two directions, and the honest thing is for the report to say which run it is.

### Changing the ranking

`SIGNAL_SEVERITY`, `BASE_SEVERITY` and `SIGNAL_BUCKET` in `chromedrift/diff.py`, and the two constants in `chromedrift/score.py`, are all plain data. A test holds the three tables to the same set of signals, so a new signal cannot be added to one and forgotten in the others.

---

## 8. Reading the report

### The four counts at the top

```
Breaking             276   ← something outside the binary stops working, silently
Behaviour change     469   ← the Windows build behaves differently
New surface         1240   ← surface that did not exist. Nothing is on by it
Housekeeping        1037   ← Chromium tidying up after itself
```

Read in that order. `report.md` gives the first three a table each and deliberately gives Housekeeping none: it is the largest bucket in every report and the one nothing in it needs doing about, so `report.json` and the sortable table in `report.html` hold it instead.

One thing inside Housekeeping is worth filtering for on purpose. `flag_expiring` rows are `chrome://flags` entries Chromium has scheduled for deletion in the next milestone or two — 57 of them at M148 → M151 — and they are the only rows in the report about work that has *not* happened yet. Everything else in the bucket is about work that has, and did not matter.

What decides a bucket, and the two placements worth arguing about, are in §7.

`report.json` also carries `meta.missing_targets`, one list per side, naming any file the target set asked for that the source did not have. A target absent from one side and present on the other is the shape that reads as a mass deletion, so the count is restated on every run — including the cached ones, where it used to disappear along with the rest of the first run's output — and `report.md` names them in *How this was produced*.

Every finding cites **`path:line`** on both sides, not just a filename. `content_features.cc` declares nearly two hundred features, so citing the file leaves the reader to do the finding.

### One table, and every row says what it is

`report.html` is **a single table**, filterable and sortable. Two other layouts were tried on top of it and both were worse — recorded here so nobody goes back:

- **Grouping every finding by signal on one long scrolling page.** It became twenty-one collapsed bars whose titles are near-synonyms in Chromium's own vocabulary: `Default flipped on`, `Now ON by default on Windows`, `New feature, on by default` are three different entries. Eighty bars, three levels deep, before the reader reaches one readable row.
- **Putting those behind a per-team menu.** The accordion wall went away, and so did the one thing a table is good for: seeing everything at once, sorting it, searching it.

What was missing was never the shape. It was that a row said `id:cancelButton` and left the reader to work out which page, added or removed, what kind of control, and whether it concerns them. So the table keeps its shape and every row carries the answer:

```
~  feature flag PrefetchPrerenderIntegration — off → on for Windows
   disabled → enabled
                    Now ON by default on Windows │ content/public/common │ 75
```

The marker at the start of the cell: `+` new, `~` changed, `−` gone.

The "what happened" sentence is **the label of the signal that set the severity** for that finding, not the first signal in the list. Pick the wrong one and a row carries one sentence while being ranked by another. A finding with no signal at all — something that just appeared, with no default to move — uses its direction and kind as the sentence (`New feature flag`, `Removed chrome://flags entry`), so every row has one.

### Four clickable triage cards

The four cards at the top are filters: click one and the table below filters to that bucket. The number on the card and the number of filtered rows always match — a test holds that.

### What changed on each screen

The **Where** column answers "where is this" for every row: `settings › privacy_page` for a control, the declaring directory for everything else. `report.md` additionally has a whole section grouped by screen, because the markdown version is read top to bottom and cannot be filtered:

```
settings › ai_page — 13 new · 1 changed · 5 gone
  + section    aiPageTitle
  + link row   skillsSettingLabel
  ~ toggle — glicExperimentalTriggering  (writes glic.experimental_triggering_enabled)
  − page /localNetworkAccess
```

The data for that was already on the facts and simply never displayed: every control carries its surface, page, file, tag and the pref it writes; every route carries its path and guard; every gate carries the handler that sets it. The same loadTimeData key appears once per handler that sets it, so without this column `webuiRefresh2026` shows up as nine identical rows.

### The table: an identifier is not a description

The table has six columns, and three of them used to be reachable only by expanding a row, or not present at all:

| Column | Answers |
|---|---|
| Score | The ranking, with every point explained |
| Bucket | Which triage bucket it falls in |
| What | The direction (`+` / `~` / `−`) and the thing **in words**, not a bare identifier: `feature flag AAPMBlocksWebGPU — off → on for Windows` |
| What happened | The sentence describing what happened |
| Where | The screen, or the declaring directory |
| Surface | The fact kind, with its meaning group |

The old `Change` column is gone: direction is now a coloured marker at the start of the What cell, because `~` takes one character and a pill took 112px.

### Every score is explainable

```
severity 75 — Now ON by default on Windows
```

```
severity 35 — Preference no longer in the file we read — it may have been
    deleted, orphaning stored values, or simply moved to one of the ~100
    pref files outside the scan
-15 unconfirmed: this run read 1% of that surface at refs/tags/151.0.7922.138,
    so "gone" may mean "moved into a file we never opened"; filed as
    housekeeping rather than breaking — --target-set wide settles it
```

A web API removed on the same run keeps its full 70, because the surface it
vanished from was read at 99%. The deduction is per surface, not per run.

A ranking nobody can argue with is a ranking that gets ignored the first time it is wrong. Nothing raises a score, so the first line is always the ceiling and every line under it is a deduction with a reason. §7 says where the numbers come from and how to change them.

### Analyse everything, render at read time

`report.json` always holds every finding, including Housekeeping, and the two rendered files are views of it:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138
python3 -m chromedrift report out/report.json --format both --out out/again
```

Size is not the constraint: the whole of an uprev is about 4 MB of JSON and `report.md` is about 118 KB. The constraint is human reading time, which is what the buckets and the *What happened* section exist to bound.

### Sixteen fact kinds, three meaning groups

The report groups its filter by *what a change means*, rather than presenting sixteen kinds as a flat list:

| Group | Contains | A change here means |
|---|---|---|
| Behaviour switches | feature flag, feature param, Blink runtime | Behaviour itself changed |
| External contracts | pref, switch, Web IDL, and all five Mojo kinds | Something outside the binary breaks, silently: stored user data, launch scripts, live websites, the other process |
| UI and scheduling | WebUI route/control/gate, `chrome://flags` | What the user sees changed, or the date something is scheduled for removal moved |

On a real M139 → M143 report, 3,120 findings split 34% / 35% / 30%. So **two thirds of a report is not about features being turned on or off** — reading it as sixteen kinds of "feature" is the most common misreading.

The three groups appear in two places in `report.html`: as a sub-line under each row's `Surface` column, and as the option groups of the `All surfaces` dropdown. `report.md` orders its sections by them, because markdown is read sequentially and cannot be filtered. A test holds every fact kind to exactly one group — miss one and its `Surface` column renders empty.

### And an `All owners` filter, because "is this mine" is a different question

A group tells a reader what kind of consequence a change has. It does not tell them whether to keep reading, and a 3,000-row report is read by several people who each own a fifth of it. So `report.html` carries a fifth dropdown, `All owners`, and `report.md` opens with a **Who has to do something** section: a count per owner across the four buckets, then the top rows of each owner's actual list.

The section is placed before *What happened* on purpose. It is the first question a reader has and the cheapest one to answer, and answering it first means four people can each read a fifth of a report instead of one person reading all of it badly.

`summary.by_owner` in `report.json` carries the same counts for scripting. All three go through `owner_of` and nothing computes an owner locally — a test renders both formats and asserts the three agree, because one fact derived in three places is exactly the shape that has drifted here before.

### Context from chromestatus

`enrich/chromestatus.py` fetches the human-written feature descriptions. Matching them per finding barely works (~2% hit rate) because their names are prose and ours are identifiers. So instead of forcing a match, the tool carries the whole "what Chromium shipped in this window" list into the report as background. It is the one source that says what Chromium *intended* to ship, so it sits in the report as context, never as a second opinion on any individual row.

The window is counted back from the version being adopted, and the list is ordered newest milestone first. Both used to be the other way round, and the result was that a 143 → 151 report carried 200 entries covering M144 to M150 and **nothing at all from M151** — the milestone actually being adopted. Truncation now happens only in the renderer, which is the only place that knows what it cut, so the count shown is true and `report.json` really does hold the rest.
---

## 9. Limits

Stated plainly, so nobody reads a clean report as a clean upgrade.

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

Measured over 332 template files across the eight surfaces: 602 conditional blocks, 460 `hidden="[[...]]"` bindings, and **37% of controls sit inside a conditional block**. So roughly a third of controls have a visibility condition the tool cannot resolve.

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
- **Extension APIs.** The `.idl` extension serves three different languages in the Chromium tree: Blink's Web IDL, Chrome Extensions IDL (`chrome/common/extensions/api/`, `extensions/common/api/`) and MIDL (`ichromeaccessible.idl`). The extractor understands only the first, so it reads only under `third_party/blink/renderer/`. It used to read all three and produced 1,081 wrong facts at M151 — 96 of them with an entire nested declaration inside their own signature, the rest labelled "Web API" when no website can call `chrome.fileManagerPrivate`. Reading a dialect wrongly is worse than not reading it; covering the extension surface needs its own extractor and its own fact kind.
- **Everything outside the repository:** server-side Finch configs, launch scripts, test automation.
- **Rendered UI** — no screenshots, no layout, no visual regressions.

### What can still be extended

The default target set tracks eight `chrome://` surfaces (`wide` reads all 132). Chromium has 132 directories under `chrome/browser/resources/`, but that number is misleading: 39 are debug pages users never see and 9 are ChromeOS-only. **The number worth considering is about 29**, for example `autofill`, `certificate_manager`, `enterprise`, `lens`, `pdf`, `side_panel`, `signin`, `tab_search`, `webauthn`.

Adding a surface is one line in `chromedrift/targets.py`:

```python
WEBUI_SURFACES = (
    "settings",
    "history",
    ...
    "pdf",        # ← this line is the whole change
)
```

No new parser needed — the three WebUI extractors are general across surfaces.

### Adding a new source of truth

Write an extractor with two pure functions, `applies_to(path)` and `extract(text, path)`, register it with one line in `chromedrift/extract/__init__.py`, and declare the files to fetch in `chromedrift/targets.py`. Nothing else changes.

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
python3 -m chromedrift check          # prints the proxy in use
```

If the proxy terminates TLS and you get `CERTIFICATE_VERIFY_FAILED`, point Python at the internal CA:

```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-internal.pem
```

### Fully air-gapped

Two options.

**Use an internal checkout or mirror.** `--local-src` applies to both refs, so when the two versions live in different directories use `--from-src` and `--to-src`:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /mirror/chromium-148/src \
  --to-src   /mirror/chromium-151/src \
  --no-enrich
```

**Move the cache from a networked machine.** Snapshots are plain JSON:

```bash
# on the networked machine
python3 -m chromedrift snapshot 151.0.7922.138
# copy .chromedrift-cache/snapshots/*.json to the air-gapped machine
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
| `scope: N FILE(S) OUT OF SCOPE` | The tree cache still holds files from a wider earlier run | Re-run that side with `--refresh` |
| `Breaking: 0` on a default run | Normal, and not a clean bill of health | The default set reads under half the tree and a fiftieth of the pref files, and an unconfirmed removal is filed as Housekeeping there by design. Run `--target-set wide` before concluding anything |
| A finding scores 0 | Chromium's build conditions keep the declaration out of the Windows binary on both sides | Working as intended. Its reasons line says so, and the row is still in the JSON and the HTML table |
| Different result from the last run | A bare milestone number was used | Always pin the full version for anything official |
| (Windows) `FileNotFoundError` while unpacking | Hitting the 260-character limit | Put the project on a short path, or `set CHROMEDRIFT_CACHE=C:\cdcache` |
| (Windows) `python3` is not a command | Windows names it differently | Use `py -3` or `python` |

### Cache and logs

```bash
CHROMEDRIFT_DEBUG=1 python3 -m chromedrift run …   # print full tracebacks
python3 -m chromedrift run … --refresh             # ignore the cache and refetch
export CHROMEDRIFT_CACHE=/shared/chromedrift-cache # put the cache elsewhere
```

A shared cache makes later CI jobs nearly instant. A released tag's snapshot never changes, so it can be shared freely between jobs and between teams.

### Running in CI

```bash
#!/bin/bash
set -euo pipefail
export CHROMEDRIFT_CACHE=/shared/chromedrift-cache

FROM="148.0.7778.217"        # pinned, not a bare milestone number
TO="151.0.7922.138"

python3 -m chromedrift check
python3 -m chromedrift run "$FROM" "$TO" \
  --target-set wide \
  --out "reports/${FROM}_to_${TO}"

# Block the merge until someone has looked at the breaking changes
BREAKING=$(python3 -c "import json,sys; \
  print(json.load(open(sys.argv[1]))['summary']['by_bucket'].get('breaking', 0))" \
  "reports/${FROM}_to_${TO}/report.json")
[ "$BREAKING" -eq 0 ] || { echo "$BREAKING breaking changes to triage"; exit 1; }
```

---

## 11. Tests

```bash
python3 -m unittest discover -s tests
```

**362 tests, running in about three seconds, with no network.**

The fixtures are shortened but structurally accurate excerpts of real Chromium files, including the awkward shapes that broke earlier versions of the parsers: two-argument macros, defaults wrapped in preprocessor conditions, per-platform states.

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
- No score may exceed its own severity. Severity is the ceiling and the adjustments only subtract, so a score above it would mean a rule had been added without a sentence to explain it.
- Every reason line quoted in a document must be a line the scorer actually emits. A sample of a finding's reasoning is a second copy of a string the code owns, and it drifted within an hour of being written.
- The source map in §12 must name every module, not only get their sizes right. A map that quietly stops listing a file is the same defect as one with a wrong number, and harder to see.
- Nothing shipped may carry Vietnamese. These documents were translated, and the translation was reported complete twice while `pipeline.html` still held six strings — a CSS comment and five inside an interactive widget, which a proof-reader sees rendered rather than in the prose.
- Every tag the control rule can admit must have a display word, and every word must name a tag the rule admits.
- Every measured number written into a document must match the snapshot on disk, and the source map in §12 must match the source.
- Every fact must point at the line that declares it, and that line number must survive into the report.
- No command may accept a flag and then ignore it.
- The coverage denominator is the tree, not the roots the fetch list happens to live under. A rule that admits a file and a measurement that cannot see it is how a percentage learns to flatter itself.
- Two sides of a comparison must have read comparable amounts. Refusing a truncated tree is the same reasoning as refusing two different target sets, one derivation further along.
- No display string may hard-code a coverage number — every run measures and prints its own.

### Checking against real data

Unit tests only prove the code does what its author thought. To check it against reality, the extractor was rewritten by a deliberately different method — strip every preprocessor directive, split on `;`, different regexes — and run over `content_features.cc` between M148 and M151:

```
Independent method :  19 added,  9 removed
The tool reported  :  19 added,  8 removed
```

Tracking down the difference showed **the tool was right and the cross-check was wrong**: the feature was not deleted, it moved from `content_features.cc` to `media_switches.cc`, and the tool correctly reported `declaration_moved`. The cross-check only looked at one file, so it could not see that.

---

## 12. Source layout

```
chromedrift/
  acquire.py      566 lines  fetch source over Gitiles or from a local checkout
  targets.py      783        declares which files to fetch and why; partitions; coverage rules
  snapshot.py     188        combines fetch + extract into one cached snapshot
  extract/      2,890        9 extractors + the C++/GRIT/mojom condition scanner
  diff.py       1,589        semantic comparison, labelling, severity, bucketing, ownership
  cluster.py      214        assemble scattered fragments into one story
  score.py        369        the two run-dependent adjustments, and the reasons
  catalog.py      362        measure what the target set is missing; check reference closure
  model.py        971        shared data structures, the four buckets, the five owners, JSON read/write
  eligibility.py   73        one policy for what is product code, shared by discovery and extraction
  jsonc.py        259        hand-written JSON5 reader
  report/       1,733        markdown + self-contained HTML dashboard;
                             groups findings by what happened and by screen
  enrich/         194        context from chromestatus
  cli.py          681        6 command-line commands
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

- **[docs/pipeline.html](docs/pipeline.html)** — the pipeline end to end, following one real change. Opens directly in a browser, no network, no server.
- **[skills/analyzing-chromium-uprevs/SKILL.md](skills/analyzing-chromium-uprevs/SKILL.md)** — the knowledge pack for an agent: the triage procedure, the signal reference, and the traps verified against real data. The valuable part is not how to run the commands, but the knowledge that stops an agent reaching a wrong conclusion.
