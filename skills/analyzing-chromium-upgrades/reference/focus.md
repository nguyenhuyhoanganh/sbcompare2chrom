# Retrieve evidence for a selected area

Use this procedure after confirming the user scope. It reduces repeated
retrieval work; it does not identify final events or prove complete discovery.
MUST read [scoping.md](scoping.md) and [investigation.md](investigation.md) first.

## Build a focus packet

Choose exact source prefixes from `review overview` and the relevant source.
Use the existing broad review where available. The prefixes below are examples
of user-selected inputs, not built-in discovery rules:

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix chrome/browser/resources/settings \
  --path-prefix chrome/browser/ui/webui/settings \
  --fact-kind base_feature --fact-kind mojo_method --fact-kind webui_control \
  --output out/upgrade/review/area-focus.json
```

Repeat `--fact-kind` for the user's preferred declaration kinds. These mark
`requested_kind` on candidates; they do not discard supporting kinds. In
particular, a preference change can explain a WebUI change even when the user
did not select preferences. Omitting the option marks all retrieved kinds as
requested. The output path must be new; the command refuses to overwrite it.

The command:

- starts from declarations and source under the selected prefixes, including
  unchanged files and facts;
- scans those source files at both exact refs for identifiers of extracted
  C++ features, qualified Mojo symbols and Mojo includes/imports;
- follows declared dependencies and members of referenced interfaces/structs,
  retaining both sides of the comparison;
- retains source deltas in the selected paths and referenced files, including
  files with no parsed finding;
- records ambiguous matches, missing declarations/source and dependency depth
  limits. `--hops` controls declared traversal depth (default 3, maximum 8), not
  semantic completeness.

There is no score cutoff or feature-name allowlist. Sharing an import, file,
flag or contract does not mean candidates belong to one event. Imports can
expose several unrelated changes. Test and inactive code can produce lexical
matches. MUST check the actual consumer and its conditions before claiming
that a candidate affects the selected product area.

## Read the packet in sections

```bash
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json --section findings --limit 20
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json --section files --limit 20
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json --section unresolved --limit 20
```

Continue each selected section using `--cursor` until `next_cursor` is null.
`findings` contains compact before/after values, deltas and reference IDs.
`files` lists entire source deltas, not just hunks represented by findings.
Rows in both sections also carry the item's current ledger `status`, so a
section shows which of its candidates already have a decision.
`references` holds two row shapes: a source match carries `targets`, a declared
link carries `source` and `target`. Both carry `certainty`. It is
`declared_reference` for a link the parser recorded, `lexical_lead` for a single
source match, `ambiguous_lead` when several declarations share the name, and
`unmatched` when nothing in the index matches. Every `unmatched` row also
appears in `unresolved` with the next check it needs. `sources` records
the exact side, source origin and hash of the input files scanned.

For files inside the confirmed scope, inspect every changed hunk. For shared
dependency files outside that scope, start with the referenced declarations
and consumers, then follow related hunks. Do not read every unrelated change
in a central declaration file merely because one relevant flag is declared
there. Do not mark that entire file explained if other hunks remain unread;
the whole-index review may remain partial while the scoped result is reported.

To inspect a candidate's immediate references without listing all references:

```bash
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json --section references --item 'KIND:KEY'
```

Use real IDs. `--item` also accepts a reference ID, or `file:PATH` for matching
source-file records. For a reference chain, follow the stored source/target
IDs. A preview marked `truncated` MUST be expanded with `review inspect UID`
before relying on omitted fields. Use `review source` to examine the actual
before/after implementation, not just the compact declaration values.

The packet is not the review ledger. Save conclusions with `review record`
using the original item IDs, then run `review check` and render as usual.
Reading a packet never marks its candidates reviewed or the remainder excluded.

## Limits that affect completeness and context

MUST examine the `unresolved` section and packet limits. Source matching is
lexical, not a compiler or complete call graph. Only the original selected
source paths are scanned for lexical references. Follow additional consumers,
imports or helper functions manually when their evidence is needed; add
observed prefixes and build a new packet if that is useful. Generated runtime
bindings and unsupported expressions can hide relationships.

`summary.serialized_characters` measures each serialized section in characters.
It is not a token count. `token_count` stays null without measurement by the
actual model's tokenizer. Skill instructions, conversation, opened source,
CLs, reasoning/output allowance and repeated tool responses also need budget.
Do not claim a 200k-context pass from these size figures alone.

Inputs and packet contents are checked for freshness. After source/report
changes, use the configuration-preserving review refresh, then create a new
packet. Do not edit the generated candidates to make counts or evidence fit
a preferred answer. Neither freshness checks nor complete ledger accounting
establish that all important changes were discovered.
