---
name: analyzing-chromium-uprevs
description: Analyzes what changed between two Chromium versions for a downstream browser fork - feature flags, web APIs, prefs, switches, Mojo interfaces, settings surface - and separates real behaviour changes from upstream cleanup. Produces a triaged report of what the fork must fix. Use when planning or reviewing a Chromium uprev such as M148 to M151, when asked what is new, removed, or changed between two Chromium milestones, when interpreting a raw Chromium diff, or when deciding what work a rebase requires.
---

# Analyzing Chromium uprevs

Compare two Chromium versions from a downstream fork's point of view and report
what the team must actually do.

Finding differences is easy and useless: a four-milestone gap changes millions
of lines. **Most apparent changes are not changes.** This skill's main job is to
stop confident wrong conclusions.

## The rule that governs everything

Chromium gates every feature behind a flag and moves it through three stages,
normally **several milestones apart**:

| Stage | Code | Users see |
|---|---|---|
| A | New code lands, flag default OFF | nothing |
| B | Flag default flips ON | **the change** |
| C | Old path and flag deleted | nothing |

So a diff between two versions mostly shows stages A and C. **A code change and
a user-visible change almost never land in the same milestone.**

Therefore never report "X changed" alone. Always answer two separate questions:

1. Did the **flag state** change on our platform? → behaviour changed
2. Did only **code** change? → cleanup; matters only if we reference the symbol

These are two lists with different owners and urgency. Keep them separate.

## Workflow

Copy this checklist and track progress:

```
- [ ] 1. Confirm platform, exact versions, and profile
- [ ] 2. Run chromedrift
- [ ] 3. Triage Must fix and Needs review
- [ ] 4. Classify each finding (decision procedure below)
- [ ] 5. Write the report, including limits
```

### Step 1: Confirm inputs

Ask for anything missing. Never guess the platform.

- **Platform**: the one the product ships (`Windows` for Samsung Browser on
  Windows). Chromium wraps defaults in `#if BUILDFLAG(IS_WIN)`; a feature can
  read enabled globally and be disabled on your platform. Wrong platform
  inverts conclusions.
- **Exact versions**, never bare milestone numbers. `151` resolves to whatever
  is newest stable today and drifts between runs. Real example:
  `ServiceWorkerAutoPreload` is ENABLED in 143.0.7499.40 and DISABLED in
  143.0.7499.194 — same milestone, different patch release.
- **Downstream profile** (`config/sb-profile.json5`) pointing at real patches or
  fork source. Without it **nothing can reach Must fix**, and a report showing
  `must fix: 0` means "no evidence supplied", not "clean uprev".

### Step 2: Run

```bash
python3 -m chromedrift check          # verify machine, network, configs

python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --profile config/sb-profile.json5 \
  --llm config/llm.json5 \
  --out out/M148_to_M151
```

Pure Python 3.9+ stdlib, no install, no Chromium checkout (pulls ~40 MB of
declaration files per version). Cold run about two minutes; cached runs seconds.

Outputs: `report.md` (paste into a ticket), `report.html` (filterable, fully
self-contained), `report.json` (scripting).

Options: `--no-ai` skip the model stage, `--no-enrich` skip network lookups,
`--top N` bound findings sent to the model, `--target-set minimal` fast smoke
run.

### Step 3: Triage

Read **Must fix**, then **Needs review**. Skip **FYI** unless searching for a
specific symbol.

Bucket comes from *evidence*, not severity: Must fix requires that the profile
shows the fork references the symbol.

### Step 4: Classify each finding

Stop at the first question that settles it.

1. **Did the flag state change on our platform?** Check `platform_state` in the
   finding. `disabled → enabled` or the reverse is a real behavioural change.
   Report and stop.
2. **Did the flag disappear?** Check the state it held *before*. Signals
   `flag_retired_on` / `flag_retired_off` mean behaviour did not change here.
   Remaining question is only whether we reference it.
3. **Do we reference it?** `we_patch` / `we_reference` fields. If yes there is
   work regardless of behaviour: a build break, or an override that now
   silently does nothing.
4. **Is it a rename?** `feature_string_renamed`, `pref_renamed`,
   `switch_renamed` compile fine and fail silently in the field. Always
   actionable if the old name appears anywhere, including server-side Finch
   configs, launch scripts and test automation, which the tool cannot see.
5. Otherwise it is upstream churn. Record, do not escalate.

Signal meanings: **see [reference/signals.md](reference/signals.md)**.

### Step 5: Report

Structure, in this order:

1. **Verdict** — one sentence on the risk of this uprev
2. **Behavioural changes** — flag state actually moved on our platform
3. **Build and integration breaks** — symbols we reference, removed or renamed
4. **Silent breaks** — renames that compile cleanly and fail in the field
5. **New capability** — what we could adopt; product input, not a blocker
6. **Limits** — what was not examined

Always state the exact versions and platform compared.

Every finding needs three parts: **what moved**, **whether users see a
difference**, **what we must do**. The middle part decides priority and a raw
diff cannot supply it.

Bad: *"`LocalNetworkAccessChecksSplitPermissions` was removed in M151."*

Good: *"Local Network Access moved to split permissions. The flag was already
ENABLED at M148, so users saw this before our current base; M151 only retires
the flag. No behavioural change for us. Action: update any reference to
`kLocalNetworkAccessChecksSplitPermissions` or the `/localNetworkAccess`
route."*

If the AI stage failed or ran with the offline `echo` stub, the report says so
at the top. **Never present empty verdict columns as a clean result** — an
unrun analysis looks exactly like a passing one.

## Known traps

Every one of these produced a wrong conclusion before it was handled. Read
**[reference/traps.md](reference/traps.md)** before interpreting any removal.

Summary: retired flags read as removed features; declarations that moved read
as deleted; a macro migration that renamed features nobody edited;
platform-divergent defaults; declarative files that declare more than ships.

## Scoping to settings

Settings live in different places per platform and share no code. Desktop is a
WebUI page; Android is preference XML. Sources, the three-hop chain from a
settings page to its flag, and how to size a "feature" (control / page /
capability): **see [reference/settings-surface.md](reference/settings-surface.md)**.

## What the tool cannot see

State these limits in every report. A clean report does not imply a clean uprev.

- **Implementation-only changes.** The tool reads declarations (macros, IDL,
  mojom, string constants, JSON/JSON5 manifests). Behaviour changed entirely
  inside a function body is invisible.
- **WebUI surfaces beyond the eight tracked.** Page routes, controls and
  visibility gates are read for settings, history, downloads, bookmarks,
  extensions, password_manager, new_tab_page and print_preview. Chromium has
  roughly 130 such surfaces; the rest are unread until added to `targets.py`.
- **Page behaviour.** Only the declarative parts of a WebUI surface are read:
  the route table and the HTML templates. Logic in the accompanying TypeScript
  is not.
- **Fork divergence.** The tool compares upstream to upstream. `--profile` is
  evidence *matching*, not a diff of the fork against Chromium.
- **Anything outside the repository**: server-side Finch configs, launch
  scripts, test automation, store metadata.
- **Rendered UI.** No screenshots, no layout, no visual regressions.

## Comparison methods

Use flags plus declarations to *discover*, targeted code reading to *explain*,
screenshots only to *confirm* a short list. Screenshot comparison is the
slowest and most brittle method and cannot say why something changed; using it
to discover changes is the most common mistake.
