---
name: analyzing-chromium-uprevs
description: Compares two Chromium versions - feature flags, web APIs, prefs, switches, Mojo interfaces, settings surface - separating real behaviour changes from cleanup, and produces a ranked report of what moved, routed to the team that would make each fix. Use when planning or reviewing a Chromium uprev such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when asked whether a Chromium change breaks anything, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
---

# Analyzing Chromium uprevs

Run `chromedrift` over two Chromium versions, then classify what it found and
report it per owner. The tool ranks; deciding what a change means for a
particular product is the job this skill describes.

**Most apparent changes are not changes.** The classification step exists to
stop confident wrong conclusions, and it fails in two opposite ways depending
on the surface.

## The two halves

| Surface | Gate between code and user | Fails by |
|---|---|---|
| `base::Feature`, Blink runtime, chrome:// screens | the flag's default, per platform | looking like a change when it is not |
| Web IDL | `[RuntimeEnabled]`, on the member or its interface | either |
| **Mojo, preferences, command-line switches** | **none** | **looking like nothing when it is a break** |

Half one moves through three stages, usually milestones apart: code lands with
the flag off (users see nothing), the flag flips on (**the change**), the flag
is deleted (users see nothing). A diff mostly shows the first and third, so
never report "X changed" here without checking the flag state.

Half two has no stages. The declaration is the contract and it changes when the
version is adopted, silently: both ends of a Mojo interface are generated from
the same file so a changed signature never breaks the build, and Chromium
ignores an unrecognised command-line switch without a word.

At M148 → M151, 220 of the 276 Breaking rows are half two. Applying half one's
questions to them is the failure this skill prevents.

## Workflow

```
- [ ] 1. Confirm platform and exact versions
- [ ] 2. Run chromedrift
- [ ] 3. Read the report in order
- [ ] 4. Classify each finding by owner
- [ ] 5. Report per owner, with limits
```

### Step 1: Confirm inputs

- **Platform is Windows and is not a question.** There is no `--platform`
  flag. Read `platform_state.windows`, never `default_state`.
- **Exact versions, never bare milestone numbers.** `151` resolves to whatever
  is newest stable today. `ServiceWorkerAutoPreload` is ENABLED in
  143.0.7499.40 and DISABLED in 143.0.7499.194.
- **Which target set**, below. If the question is "can we ship this uprev", the
  answer is `wide`.

Ask for anything missing.

### Step 2: Run

```bash
python3 -m chromedrift check          # verify machine, network, cache

python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

Pure Python 3.9+ stdlib, no install, no Chromium checkout. About three and a
half minutes cold for a pair; half a second cached.

| `--target-set` | Per version | Files read | Use for |
|---|---:|---:|---|
| `minimal` | ~1 MB | 3 | smoke test |
| `default` | ~40 MB | 43% of files, over half the flags | day to day |
| `wide` | 337 MB fetched | **99% of files** | the widest read available |

Outputs: `report.md` (paste into a ticket), `report.html` (filterable),
`report.json` (scripting). Every finding cites `path:line` under
`change.locations` — quote it, never paraphrase the file name.

**`report.html` alone answers *what* changed, never *why*.** Opened as a file
it is a complete, offline table; the per-row "why did this change" lookup
cannot run there, because a page on `file://` may not call
`chromium-review.googlesource.com` and the browser blocks it before it is
sent. Serving the directory changes who asks — the page calls localhost, and
Python asks Gerrit:

```
python3 -m chromedrift serve out          # prints http://127.0.0.1:8787/
```

Offer this whenever someone asks why a row changed, what a flag was for, or
which review to read. You can start it yourself and hand over the URL. Opening
`report.html` directly and reporting that the lookup does nothing is the
failure this note exists to prevent.

**The tool does not judge.** It stops at extracted evidence and a deterministic
rank. It knows nothing about what anyone patches, ships or overrides: a
**Breaking** row says a contract moved, not that anyone had signed it.

**Every run prints the coverage it achieved.** Quote that number in the report;
never quote one from this file.

```
coverage: reads 3669 of 8349 files in this tree that could declare (43% of files)
```

**Coverage changes the answer, not just the confidence.** A removal is an
inference from absence, so on a partial read it loses 15 points and a
`pref_left_scan` is filed as Housekeeping rather than Breaking. Measured on one
pair: `default` gives 139 of those at 20 points, `wide` gives 171 at 35.
**`Breaking: 0` on a default run is not a clean bill of health.**

**Two refusals, one meaning.** `cannot diff snapshots built from different
target sets` and `cannot diff: X holds N facts against Y's M` both say one side
read a fraction of the other. Neither is a bug to work around: check that
`--local-src` / `--from-src` / `--to-src` points at a full Chromium `src/`.

`--partition settings` (repeatable: `downloads`, `bookmarks`, `history`,
`extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`,
`media`) fetches and scans one part of the product. Right while iterating on one
surface, wrong as a release gate — Chromium is not organised by product, so a
change affecting downloads can live in `content/` and match no partition.

Also: `chromedrift report <report.json> --format both` re-renders without
re-running; `chromedrift catalog <ref>` measures what the target set is
missing; `chromedrift figures <report.json>` writes the measurements the
project's own documents quote, which is how they stay true.

### Step 3: Read the report in order

1. **Who has to do something** — the per-owner counts, at the top of
   `report.md`. Start here; it says which lists exist and how long they are.
2. **What happened** — every finding grouped under the signal that set its
   severity, so a 3,000-row report is about forty things.
3. **Breaking**, then **Behaviour change**, then **New surface**.
4. **Housekeeping**: skip, with one exception. Filter it to `flag_expiring`
   before closing — those are `chrome://flags` entries Chromium has scheduled
   for deletion, the only rows about work that has not happened yet.

### Step 4: Ask why a row changed

Expanding a row in the served page looks up the review that made the change.
It reads the CLs that touched the declaring file inside the milestone window,
then keeps the ones a diff ties to *this* identifier — a declaration file is
shared, and 500 merged CLs touched `about_flags.cc` between M148 and M151, so
the file alone answers nothing.

What comes back is a CL, the issue that CL cites, and the other CLs that cite
the same issue — which is the fix history for the bug behind the change. Each
CL carries the verdict that put it there, and the verdicts are never merged
into a score:

| Verdict | What it claims |
|---|---|
| `introduced` | an added line **inside this declaration** carries the value the fact ends up with — the CL *is* the change |
| `exact` | a line the CL changed carries the identifier |
| `moved` | the file was renamed and the fact came with it; no line changed |
| `declares` | the CL edited the declaration's body, not the line naming it |
| `described` | the CL's own title or description names it; no diff was read |
| `crowded` | several CLs edited this declaration, so none singles it out — read as that declaration's history, oldest first |
| `touched` | nothing matched the identifier; these merely touched the file |

The last two name no fact. Never quote them as the cause; say what they are.

Lookups are written back to `report.json`, so they survive a restart and reach
`report.md` on a re-render. `--click-budget N` caps diffs read per row
(default 600), `--no-save` leaves the file alone. An issue's history is not
fetched with the row: click the issue on the CL you believe, and it opens
under that CL.

**A restricted issue is normal and not a failure.** Around three in ten linked
issues answer HTTP 403 — they sit in a security, abuse or Google-internal
tracker component. The panel says so and keeps the link, because the reader
may be the one person who can open it. **The CLs stay readable either way**:
they live on Gerrit, they are public, and their subjects carry what the issue
was about. Report the fix history, not the closed door.

**An empty answer is a statement about this search, never about Chromium.**
The two trees differ, so something landed. The file is asked three ways — on
main, then off it for merge-backs, then the whole window's commit messages —
and if all three miss, the CL is recorded under a name or path this report
does not hold. Say that; do not report that a declaration changed by itself.

| Bucket | Means |
|---|---|
| Breaking | Something outside the binary stops working, silently |
| Behaviour change | The Windows build behaves differently. Someone can see it |
| New surface | Surface that did not exist before. Nothing switches it on |
| Housekeeping | Chromium tidying up, and scheduling |

**Retired flags are Housekeeping and that is deliberate** — 132 at M148 → M151,
72 that had shipped and 60 abandoned, none user-visible. Reporting one as a lost
feature means re-reading the traps.

**Severity versus score.** Severity is what the kind of change costs; score is
that after two deductions (not in the Windows build on either side → 0;
unconfirmed removal → −15). Nothing raises a score, so a score below its
severity always has a sentence in `reasons`. Quote the sentence, not the number.

### Step 5: Classify each finding by owner

`owner` is on every finding. Branch on it, then ask that surface's question.

**Process boundaries** (`ipc`) — Mojo

1. `platform_state.windows` — `not_compiled` already scores zero;
   `conditional` is undetermined, not ours-by-default. A declaration under
   `android/`, `ash/`, `chromeos/` or `ios/` carries no guard at all.
2. **Who is on the other side?** Both ends compile from the same tree, so this
   is a build break for out-of-tree code before it is a runtime break. Trap 10
   lists when it is a runtime break. Say which applies.
3. `ipc_shape_changed` and `ipc_signature_change` break deserialization
   silently. `ipc_enum_changed` is milder: an unknown value is rejected rather
   than misread.

**Web platform** (`webplatform`) — Blink IDL and runtime flags

1. **Can a page reach it?** `web_api_added_live` versus `web_api_added_gated`.
   `web_api_added` means the gating flag was outside what this run read — check
   before reporting either way.
2. `web_api_removed` breaks live sites; `web_api_removed_gated` reached nobody.
3. `web_api_shipped` is the moment users get it.

**Browser C++** (`native`) — flags, prefs, switches

1. **Did the flag state change on our platform?** `platform_state`.
   `disabled → enabled` or the reverse is a real behavioural change. Stop.
2. **Did the flag disappear?** Read the state it held *before*.
   `flag_retired_on` / `flag_retired_off` mean behaviour did not change here.
3. **Is the disappearance confirmed?** `pref_left_scan` / `switch_left_scan`
   mean "not in the files this run read". Search the tree for the key, or
   re-run `wide`, before reporting either outcome.

**WebUI front-end** (`webui`) — the chrome:// screens

1. **Follow the guard to its flag.** A control or page that vanished usually
   moved behind a different guard, and the user-visible change happened when
   that flag flipped. Traps 2 and 6.

**Outside the repository** (`config`) — Finch, launch scripts, automation

1. **Always actionable if the old name appears anywhere.**
   `feature_string_renamed`, `switch_renamed`, `param_removed`,
   `param_rewired` compile fine and stop working in the field. Retired flags
   land here too: they silently kill any override set from outside.
2. The tool cannot see any of these places. This is a list of things to check,
   not a list of things that broke.

Signal meanings: **[reference/signals.md](reference/signals.md)**.

### Step 6: Report per owner

```markdown
## Verdict
[One sentence on risk, and which owner carries most of it.]

## Process boundaries — N to look at
## Web platform — N
## Browser C++ — N
## WebUI front-end — N
[Skip an owner with nothing in Breaking or Behaviour change, and say so.]

## Outside the repository — N
[Always present, always last.]

## New capability
[web_api_added_live only. Product input, not a blocker.]

## Limits
[Coverage figure the run printed, target set, partitions, exact versions.]
```

Every finding needs three parts: **what moved**, **whether users see a
difference**, **what someone must do**. The middle part decides priority and a
raw diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."*

Good: *"Local Network Access moved to split permissions. The flag was already
ENABLED at M148, so users saw this before our current base; M151 only retires
the flag. No behavioural change. Action: update any reference to
`kLocalNetworkAccessChecksSplitPermissions` or the `/localNetworkAccess`
route."*

## Reference

- **[reference/traps.md](reference/traps.md)** — the ways to reach a wrong
  conclusion, each one measured against real Chromium data. Read before
  interpreting any removal; the later traps cover Mojo, web APIs and
  switches.
- **[reference/signals.md](reference/signals.md)** — what each signal means.
- **[reference/settings-surface.md](reference/settings-surface.md)** — the
  three-hop chain from a settings page to the flag behind it, and how to size a
  "feature".

## What the tool cannot see

State these in every report. A clean report does not imply a clean uprev.

- **Whether any of it touches a particular product.** The tool compares
  Chromium against Chromium. Searching your own tree for the identifier a
  finding cites is the step that answers "does this affect us".
- **Implementation-only changes.** It reads declarations. Behaviour changed
  inside a function body is invisible.
- **Five classes of declaration it does not turn into facts**, in files it
  otherwise reads completely. Measured at M151: 85 Web IDL `callback`
  definitions, 144 `typedef`s, 200 `Interface includes Mixin` relations, 18
  Mojo `feature` blocks and 311 Mojo constants. Real examples that produced no
  row: `typedef LanguageModelMessageValue` changing its underlying union at
  M143 → M147, and the Mojo constant `kWebNNDirectML` disappearing at M151.
  **"Reads 99% of the files" is a statement about files, not about grammar.**
- **Anything outside the repository** — Finch configs, launch scripts, test
  automation, enterprise policy, store metadata.
- **Chrome Extensions IDL and MIDL.** Only Blink's own `.idl` is read.
- **Page behaviour.** Only the declarative parts of a WebUI surface: the route
  table and the HTML templates, not the TypeScript.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

Use flags and declarations to *discover*, targeted code reading to *explain*,
screenshots only to *confirm* a short list. Using screenshots to discover
changes is the most common mistake.
