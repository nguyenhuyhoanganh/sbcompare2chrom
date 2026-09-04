# When the answer comes back empty

## Contents

- The one sentence you may never write
- Part A — no row in the report at all
- Part B — a row exists, but no CL
- Deciding which shape you are in
- What to do about each

## The one sentence you may never write

> *"No CL touched this file, so nothing changed."*

The two trees differ. Something landed. An empty answer is a fact about **this
search**, never about Chromium, and phrasing it as an absence invites the reader
to conclude a declaration changed on its own — which cannot happen.

Every shape below has an honest sentence. Use it instead.

## Part A — no row in the report at all

`why.py` printed `nothing ... matches`. Several distinct causes, and only the
last one is "it did not change".

### A1. The name is not what the report calls it

The report is indexed by `kind:key`. A feature is keyed by its **string name**
(`BackForwardCache`), not its C++ symbol (`kBackForwardCache`); a Mojo field by
its fully qualified path (`blink.mojom.CommitNavigationParams.early_hints_...`).

Try the search again against a path fragment instead:

```bash
python3 skills/investigating-chromium-root-causes/scripts/why.py out/DIR features.cc
```

### A2. The declaring file was outside the target set

`default` reads under half the candidate files. A declaration in a file this run
did not fetch produces no fact on either side, so it produces no row and no
`removed` either. Re-run `--target-set wide` before concluding anything.

Check what the run actually read — every run prints it:

```
coverage: reads N of M files in this tree that could declare (P% of files)
```

### A3. The declaration is a class the extractors do not turn into facts

Measured at M151, in files the tool otherwise reads completely: 85 Web IDL
`callback` definitions, 144 `typedef`s, 200 `Interface includes Mixin`
relations, 18 Mojo `feature` blocks, 311 Mojo constants. **"Reads 99% of the
files" is a statement about files, not about grammar.**

If the thing you are chasing is one of those, the report will never hold it, at
any target set. Read the two versions of the file directly.

### A4. It changed inside a function body

The tool reads declarations. A behaviour rewritten inside an implementation with
no declaration touched is invisible here and always will be.

### A5. It genuinely did not change between these two versions

Reachable only after A1–A4 are excluded. Say it with the coverage figure
attached, because on a partial read A2 is the more likely explanation.

## Part B — a row exists, but no CL

`why.py` printed the finding, then `No CL was tied to this finding.` The script
names which shape it is. They license very different sentences.

### B1. Nothing was looked up

No provenance block at all. The row was never asked about.

> "Not yet investigated."

### B2. The lookup could not reach Gerrit

Printed as `! the lookup could not reach Gerrit`. Network, proxy, or the host
being unreachable. Nothing was established at all — this is not a result.

> "The lookup failed before it established anything. Retry."

Verify the host: `python3 -m chromiumdiff check`.

### B3. The diff budget declined the file

Printed as `Nobody looked: N CLs touched this file, past the diff budget.`

Nobody read the diffs, so the verdicts that name a fact were never attempted.
This is **not** the same as "no CL matched".

> "Not searched — N CLs touched this file, more than the budget would open."

Fix it: re-run with `--budget 0` for that one row.

### B4. Requests were lost mid-lookup

Printed as `! N request(s) to Gerrit failed`. Whatever came back is real but
partial — a diff that failed and a diff that genuinely does not mention the
identifier are indistinguishable at the point of use.

> "Partial: N requests failed, so what follows is not a finished search."

Retry the same command; the cache keeps what already succeeded.

### B5. The candidate list hit Gerrit's page cap

Gerrit stops at 500 rows for an anonymous query and gives no marker. The run
splits the window to establish the count, but where the list is still trimmed
the row says so.

> "The window may hold CLs this list does not."

### B6. All three questions were asked and missed

The only shape that is a finished result. The file was asked on `main`, then
with the branch pin removed for merge-backs, then the whole window's commit
messages were searched for the identifier — and all three missed.

This is a real conclusion, and it is a narrow one:

> "The CL that made this change is recorded under some other name or path than
> the ones this report holds — a generated file, a path Gerrit indexes
> differently, a rename, or a third-party roll."

It licenses a next step, not a shrug: search Chromium's git log directly for the
identifier, or open the declaring file's history on
`chromium.googlesource.com`.

## Deciding which shape you are in

The script tells you. If you are reading a raw block instead, in
`enrichment.gerrit`:

| Field | Shape |
|---|---|
| block absent | B1 |
| `diffs_read: false` | B3 |
| `failed_fetches > 0` | B4 |
| `search_incomplete` | B5 |
| `changes: []`, `diffs_read: true` | B6 |
| `found_by: "message"` | answered by question 3, not by the file |

## What to do about each

| Shape | Next command |
|---|---|
| A1 | search again by path fragment, or by `kind:` prefix |
| A2 | re-run the pipeline with `--target-set wide` |
| A3, A4 | read the two versions of the file; the tool will not help |
| A5 | report it, with the coverage figure |
| B1 | run the lookup |
| B2 | `python3 -m chromiumdiff check`, then retry |
| B3 | retry with `--budget 0` |
| B4 | retry; the cache keeps the successful half |
| B5 | report the number, and read the CLs you did get |
| B6 | leave the tool: search Chromium's git history for the identifier |
