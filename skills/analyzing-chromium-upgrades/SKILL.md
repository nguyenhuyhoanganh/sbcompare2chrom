---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions with the chromiumdiff scripts and explains what changed, what it affects and what to verify or update, scoped to the product areas the user names, then publishes the result to Confluence or hands it back as a document. Use when analyzing a Chromium upgrade or version bump, interpreting a chromiumdiff report.json or review directory, or reviewing one area such as Settings, WebUI, Mojo or feature flags across two milestones. Use investigating-chromium-root-causes instead to trace one identifier or one reported symptom back to its cause.
---

# Analyzing Chromium upgrades

Every command is `python3 -m chromiumdiff ...`, and the commands belong to the
tool rather than to a skill. Read references from this skill's own `reference/`
directory. To hand work to another skill, name that skill and its task; do not
read its reference files or run anything inside its directory.
Read [reference/handoff.md](reference/handoff.md) when transferring a task.

The script reads declarations out of two Chromium versions and lists the
differences. You work out what each difference means, what it affects, and
what the user has to check or change. Buckets, scores, signals and clusters
only tell you what to look at first. They are never the answer.

## The workflow

Copy this checklist into your reply and tick each line as you finish its step:

```
Chromium upgrade review:
- [ ] 1 Get the versions and the scope -- read reference/scoping.md first
- [ ] 2 Build or open the comparison
- [ ] 3 Take the whole-index inventory
- [ ] 4 Retrieve evidence for the scope -- read reference/focus.md first
- [ ] 5 Read the evidence -- read reference/traps.md first
- [ ] 6 Group into events and record decisions -- read reference/investigation.md first
- [ ] 7 Repeat 4 to 6 until the scope is accounted for
- [ ] 8 Render the review
- [ ] 9 Publish the result
```

Each step ends with a **Checkpoint**: something that must be true, and what to
do when it is not. Do not start a step until the checkpoint before it is true.
Do not tick a line until you have checked its checkpoint yourself.

Read the whole reference named on a step before you start that step. If you
already read it in this run, you do not need to open it again. Three more
references are read during step 5, when you hit their subject:
[signals.md](reference/signals.md) for what the classifier labels mean,
[settings-screen.md](reference/settings-screen.md) for WebUI routes, controls
and when they show, and [history.md](reference/history.md) for CLs and bugs,
and before you say why a change was made or that it was split, reverted or
merged.

`MUST` means you have to do it. Run every command from the project root;
`python3 -m chromiumdiff` fails anywhere else. Reading this file, copying a
command out of it, or reading `report.md` on its own is not enough to pass any
checkpoint.

## Terms

- **Fact**: a declaration extracted from one version; it may be unchanged.
  `--fact-kind` selects by its kind.
- **Finding**: a difference between extracted facts, identified by `kind:key`.
- **Source delta**: a difference in file contents, including code no parser
  understands. A **hunk** is one section of a file diff.
- **Event**: one change you explain in the final report. It can cover one
  finding or several, across several files and commits.
- **Consumer**: code or an external system that calls an API, reads a value,
  implements an interface or otherwise depends on the changed behaviour.
- **Gate**: a condition that decides whether code or an API can be used.
  **Rollout** is whether it is really available in a shipped product. That can
  differ from the default written in the source.
- **Scope**: the areas and decisions the user gives you at step 1.
  **Acquisition** is a different thing: how much of Chromium the script
  downloads and reads, set by `--target-set` and `--partition` at step 2.
- **Selection**: the list of indexed items whose decisions must be complete for
  that scope, recorded at step 7. The scope is in the user's words; the
  selection is in item IDs, which is what a gate can count. `out_of_scope` is
  neither of the two: it is one decision you record on a single item.

## Step 1 — Get the versions and the scope

MUST ask for anything missing before running a comparison or analyzing
findings. Ask all of it in one exchange, in the user's language:

> 1. Which two versions? Full version numbers are best, like
>    `148.0.7778.217` and `151.0.7922.138`. A milestone on its own, like
>    `148`, also works: it becomes the newest stable Windows release of that
>    milestone at the moment I run it, so the same request can give a
>    different release if we run it again later.
> 2. Which areas should I review: Settings, History, Bookmarks, Extensions,
>    Downloads, other areas you name, or a broad comparison? You can pick
>    several.
> 3. Which kinds of declaration matter: feature flags, preferences,
>    command-line switches, Mojo interfaces, Web IDL, WebUI controls and
>    routes — or all of them? Answer "all" if you are not sure.
> 4. What matters most: changes users will notice, new capabilities, or
>    changes your product must adapt to?

Those areas are examples, not a list of things to go and find. Question 3 only
narrows what gets marked as asked for; a kind you did not pick still appears
when it explains one you did, so nothing is lost by answering "all". Do not
make the user classify code: a product-language answer is enough.

MUST wait while any of it is missing. Do not pick the versions, the areas or
the kinds yourself, and do not fall back to the top N rows or the highest
scores. If the user already gave explicit answers, use them without asking
again; on resume, keep the recorded ones unless the user changes them.

A broad review is a valid answer, covering new capabilities, behaviour
changes, API changes, migrations and scheduled work, not only compatibility
problems.

[reference/scoping.md](reference/scoping.md) lists the fields to record in
`review/request.md` and how to choose acquisition without dropping the
dependencies a selected area needs.

**Checkpoint 1.** Both versions are known and `review/request.md` exists and
answers every field scoping.md lists. If you guessed a version, an area or a
kind, or picked one yourself, this does not pass: stop and ask the user.

## Step 2 — Build or open the comparison

Python 3.9 or newer is enough. Install nothing. The script only compares the
Windows build and has no option to change that. Write down the exact
`from_ref` and `to_ref` the report gives back, because a plain milestone
number can point at a different release the next time you run it.

For a new comparison:

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Replace FROM/TO and the paths with the versions the user asked for. A run
downloads about 315 MB per version and reads every file its targets cover. It
still does not read all of Chromium, and it does not understand every kind of
code it downloads. `--target-set smoke` reads only three files; use it to
check the tool works, never to compare two versions. `--partition` downloads
less, and you use it only after the user agrees to read less.

If a report exists but no review, run `review init` with that report's own
cache. If a review already exists, go to step 3. Only run `review init` again
if its inputs changed, and read
[reference/investigation.md](reference/investigation.md) first: a refresh has
to reuse the saved cache and Git source.

If the user has a local Chromium Git checkout, add
`--source-repo /path/to/chromium/src` to `review init`. It then gets the full
list of changed files at both versions. It reads Git objects and does not
change the checkout. Without it, the comparison only sees files already in the
cache, and a file missing from the cache means you do not know what is in it,
not that Chromium deleted it.

The run writes:

- `report.md`, a summary. Its tables may leave rows out.
- `report.json`, every finding. Query it. Do not load the whole file, and a
  text search over it is not a review.
- `review-index.json`, the settings the run used, plus the findings, the facts
  that did not change, the links between them and the file diffs.
- `review.json`, your events and evidence, and a decision for every item.
  Step 8 turns it into `review.md`.

**Checkpoint 2.** `review init` exited 0 and the review directory holds
`review-index.json` and `review.json`. If it failed, fix the inputs and run it
again. Working from `report.md` alone does not pass.

## Step 3 — Take the whole-index inventory

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` exits 1 while there is still work left. That is normal here. Read the
JSON it prints. `overview` counts the whole saved index inside the script and
prints only numbers, never rows or diffs. Pick your next queries from those
numbers, so you do not pull thousands of rows into context to find out what is
there.

The count covers everything, including low scores, findings with no signal,
file diffs and milestone summaries. To leave something out you need a reason
that comes from the user's scope. "My keyword did not match" and "my path did
not match" are not reasons. scoping.md lists the `--path-prefix`,
`--item-kind` and `--fact-kind` filters and says what each one leaves out.

**Checkpoint 3.** You have read the JSON from `check` and `overview`, you know
`index_total`, and your queries come from those numbers. Picking them from the
tables in `report.md` does not pass.

## Step 4 — Retrieve evidence for the scope

MUST follow [reference/focus.md](reference/focus.md) before you treat a path
filter as all the evidence. Filtering by path misses things declared somewhere
else, such as a Mojo interface that a Settings file calls but that lives in
`services/`.

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix PREFIX --output out/upgrade/review/area-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json
```

Take PREFIX from what step 3 printed. focus.md explains the other options, the
sections of the packet and how to read through them.

Use `review related` too. It shows the links the parser recorded, on both
versions, including declarations that did not change. Two items sharing a
flag, a path prefix, a screen, an interface or a CL is a reason to look, not
proof that they are one event. The packet is only evidence you collected:
reading it does not mark anything as reviewed and does not rule anything out.

**Checkpoint 4.** The packet file exists, and for every section you chose you
kept reading until `next_cursor` came back null, `unresolved` included. If you
stopped a section part-way, you have not read that evidence.

## Step 5 — Read the evidence

Read [reference/traps.md](reference/traps.md) before you conclude anything
from the source, from whether something is available, or from something being
missing.

Read the source before and after, and the code that uses it. For a file inside
the scope, look at every changed hunk, even the ones that already have a
finding. For a shared file outside the scope, start at the declarations the
packet points to and follow the hunks around them, as focus.md describes; do
not mark the whole file reviewed while hunks in it are unread. Chase the
identifiers the parser could not resolve. A change with no finding still needs
looking at.

A finding's `change` holds `before`, `after`, `deltas`, `paths`, `locations`
and `signals`. `unconfirmed` means the run did not read enough to be sure the
thing is really gone. Read the coverage numbers and the reasons before you say
a declaration was removed.

What each kind of evidence can and cannot tell you:

- Flags and APIs: compare the Windows state that was recorded, plus every
  build and runtime condition around it. A default written in the source is
  not proof of what shipped to users.
- Removed declarations: look for a replacement declaration, and look at the
  code that used it, before you say the feature is gone.
- API or IPC signatures: this tells you a declaration changed. Find out which
  code uses it, and which version pairs matter, before you say a build or a
  run will break.
- Prefs, switches and parameters: find the code that reads it, the code that
  writes it, any migration, and anything outside the binary that can override
  it. If no gate is recorded, that does not mean the code always runs.
- Two versions of the source tell you the difference between those two
  versions. If you want to say something was split up, reverted, or merged
  later, you need the commit history for that.

Read [signals.md](reference/signals.md) before you read anything into the
classifier labels. Read [settings-screen.md](reference/settings-screen.md) when
you follow WebUI routes, controls and the conditions that show or hide them.
Read [history.md](reference/history.md) when you cannot tell why a change was
made or in what order things happened; it covers looking a CL up from a
finding, and reading the file history directly when `chromiumdiff why` finds no
row. Check a milestone summary against the two exact versions: its date alone
does not tell you the feature was in either of them.

The commands for `index`, `inspect`, `related` and `source` are explained at
the end of this file.

**Checkpoint 5.** For every candidate in the batch you have read the source
before and after, and you know the conditions around it. Every item you could
not answer says what to check next. A preview marked `truncated` does not
count as read: open it with `review inspect` first.

## Step 6 — Group into events and record decisions

Read [reference/investigation.md](reference/investigation.md) first. It gives
the format for a decision, the states an item can be in, and how to work
through the pending list.

Put items in the same event only when the evidence says they are one change,
and say what each item adds. Keep unrelated changes apart even when the tool
grouped them. Say three things separately: what you saw in the source, what
you think it was for, and what it means for this product.

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

Save events and unanswered questions in each batch. Read the saved event list
and compare new evidence against earlier decisions, revising a group when the
evidence says it should be joined or split. Do not split one event in two just
because you happened to look at its parts in different batches.

**Checkpoint 6.** `review record` accepted the batch, and the `review check`
you ran after it shows the pending count go down by the number of items you
decided. If it did not go down, read what `record` returned. Going off and
recording a different set of items instead does not pass.

## Step 7 — Repeat 4 to 6 until the scope is accounted for

For a selected area, record its indexed items using
[reference/selection.md](reference/selection.md). Include source deltas and
required supporting items, not just findings returned by a path or kind
filter.

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

Keep the same path and kind filters for the scope each time you run that
query. Look at supporting source and dependencies outside those filters
separately. investigation.md gives the cursor rules that stop a shrinking
pending list from skipping items.

You may stop before the whole index is decided for one reason only: the scope
the user gave you is done. Rows that look interesting, a score cut-off and a
page count are not reasons to stop. A small batch limits how much you hold in
context at one time; it does not limit how much of the scope you review. So do
not stop after the first page, and do not decide in advance how many events
you will find. Do the same for identifiers you have never seen: the examples
in the references and the signal names are not a list of things to go and
find.

A filtered query returning nothing does not mean the work is done. `review
unresolved` lists references the parser could not resolve, which are not the
same as decisions you have not made; for those use `index --status
unresolved`. Go back to events you marked provisional. Re-check the pending
list after you change an event or refresh the review, because both can put
items back to pending.

**Checkpoint 7.** `index --status pending` with the scope's filters returns no
rows, you have gone back to the provisional events, and you have read `review
check` for the whole-index numbers. An empty filtered query on its own does
not pass: the filter may be wrong instead of the work being finished. If you
recorded an item selection, `review check --selection` must also pass against
it. Confirm that selection still covers the user's request.

## Step 8 — Render the review

```bash
python3 -m chromiumdiff review render out/upgrade/review
```

Add `--require-complete` when you reviewed the whole index. For a recorded item
selection, use `--require-selection-complete` instead. Both refuse to write
while their respective work is unfinished. The selection gate keeps whole-index
PARTIAL visible and reports the selection's completion separately. If you had to
stop early because you ran out of budget or because evidence was missing, say
which of the two it was, and give the numbers and what to check next. Never
get past a failed check by changing items you did not look at to `explained`
or `out_of_scope`.

`review.md` is the tool's own record: first the coverage limits it measured,
then one section per event with its evidence. Step 9 is built from it, and
`render` overwrites the file, so never edit it by hand.

Having a decision for every item does not mean you found every change that
matters. The cached source may be incomplete, and the parsers only understand
some kinds of code. Configuration outside the binary, patches this product
carries, and the UI as rendered all need their own evidence. `review check` is
not approval to ship.

**Checkpoint 8.** `review render` exited 0 and `review.md` has one section for
every event you recorded. If you did not read the file, this does not pass.

## Step 9 — Publish the result

Ask where the result should go:

> Do you want this on Confluence, or as a document here? For Confluence I
> need the page: a new page under an existing one, or an existing page whose
> content I should replace. Give me the page title or its URL.

For Confluence, use the `managing-confluence` skill and give it the page the
user named. If that skill is not available in this run, say so and write the
document instead. Do not publish any other way. Do not guess a page the user
did not name.

Otherwise write the document to `out/upgrade/review/delivery.md` and tell the
user where it is. `render` does not touch that file.

The page and the document hold the same three parts, in this order.

### Part 1 — What this run compared

Put these at the top:

- the two versions, as the exact `from_ref` and `to_ref`;
- the platform;
- the areas and the kinds of declaration the user asked for at step 1;
- the path to the review directory.

Without these the reader cannot tell what the table below is about.

### Part 2 — The table of changes

One row per event. Put the rows the user said matter most at the top. Do not
sort by score.

| Change | What it means | Evidence | Verify |
|---|---|---|---|
| Feature flag X enabled by default | Windows users get X without turning on a flag | `base_feature:X`, `chrome/browser/x/features.cc:42` | Not verified |

What goes in each column:

- **Change** — what happened. Not the bucket, the score, or the identifier on
  its own.
- **What it means** — what a user will notice, or what this product has to
  change. Write it in the user's language.
- **Evidence** — the finding IDs, and the file and line in each version, so
  the reader can open them.
- **Verify** — always `Not verified` when you write the table.

The `Verify` column is there because the tool only reads code. It never runs
it. Every row says what the source says, and nobody has checked it on a real
build yet. A person fills this column in after they check the row.

On Confluence, use a grey status marker, so the rows nobody has checked are
easy to see. A plain document has no colours, so it just says the words.

You MUST NOT change a row to verified. Only a person can do that check.

### Part 3 — What this run did not compare

Put this under its own heading, on the same page or in the same document. Do
not put it in a small note at the bottom.

Copy these three numbers from `review.md`:

- how many declaration files the run read on each side;
- the directories where it read the fewest;
- the files no target reads at all.

Then say what this method cannot do at all:

- it compares declarations, not what the code does;
- a file no parser understands never appears in the findings, whether it
  changed or not;
- Finch, configuration outside the binary, patches this product carries, and
  the UI as rendered all need their own evidence.

Then say how many items were left outside the scope the user asked for.

This part is what lets the reader tell two different things apart: "nothing
changed here" and "the tool never looked here". Without it, an empty table
reads as good news.

**Checkpoint 9.** The page or the document exists, it has all three parts, and
every row of the table says `Not verified`. A table with no part 1 or no part
3 does not pass.

## Query mechanics

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Use IDs and paths taken from the real index. Every query accepts `--cursor`,
`--limit` and `--max-chars`. That last one counts characters, not tokens. Keep
reading pages until `next_cursor` is null. For `index`, use
`--after NEXT_AFTER` when your decisions change between pages: the pending
list shrinks as you decide items, and a numeric offset into a shrinking list
skips items. Deciding the whole batch and running the query again from cursor
0 also works.

`inspect` gives field names as JSON-pointer paths. Long strings have offsets
and can run over several pages. `events` gives a short list; inspect one event
ID to read all of its saved analysis without loading the whole review.

`related` gives chains of links, each with a type. It does not tell you one
thing caused another, and it does not follow an unclear reference or a weak CL
match on its own. If a node has too many links, query it with `--hops 1` and
read its pages.

`source` gives the exact refs, where the file came from, and SHA-256 hashes.
Its `next_line` is a different thing from `next_cursor`: finish the pages for
one line range before you move to the next range. Use `--side from` or
`--side to` when you want source line numbers, because line numbers in a diff
are not line numbers in the file. If a file is missing, `source --fetch` gets
it at the exact ref. If that fails, say the evidence is missing. Never use the
same file from another version instead.

A keyword search MUST NOT be used as evidence of what the code does or of how
much was covered. To find the code that uses something, read the exact
`inputs.source_roots` value from the index, then:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Search results are places to go and look. They do not prove the code runs. In
Git mode, use the `git grep` steps in `reference/history.md`, which pin the
exact ref, because the checked-out working tree may be a different version.
