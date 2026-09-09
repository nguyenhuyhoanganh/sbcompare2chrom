# Preserving review inputs

## Read the saved configuration

Run this from the project root, replacing only the review directory. It prints
selected fields without placing the complete index in context.

```bash
python3 - out/upgrade/review <<'PY'
import json
import sys
from pathlib import Path

index = json.loads((Path(sys.argv[1]) / "review-index.json").read_text(encoding="utf-8"))
keys = ("report", "refs", "cache", "source_roots", "source_scope",
        "platform", "target_set", "partitions", "coverage")
print(json.dumps({key: index["inputs"].get(key) for key in keys}, indent=2))
print(json.dumps({"warnings": index["warnings"]}, indent=2))
PY
```

`source_scope.mode` distinguishes cached files from a Git repository.
`source_roots` identify cached trees. In Git mode, read the recorded commits
from the repository; do not assume the working checkout matches either ref.
Keep the printed cache path for `why.py` and `cl.py` lookups.

## Refresh after saving new evidence

`why.py --save` changes `report.json`. Refresh the review before continuing,
using its saved configuration. The CLI does not automatically retain a prior
`--cache` or `--source-repo` when they are omitted on `review init --refresh`.

Run the following from the project root after saving the lookup. It preserves
both cached-only and Git-backed reviews without guessing their paths:

```bash
python3 - out/upgrade/review <<'PY'
import json
import subprocess
import sys
from pathlib import Path

directory = Path(sys.argv[1]).resolve()
index = json.loads((directory / "review-index.json").read_text(encoding="utf-8"))
inputs = index["inputs"]
command = [sys.executable, "-m", "chromiumdiff", "review", "init",
           inputs["report"], "--directory", str(directory),
           "--cache", inputs["cache"], "--refresh"]
scope = inputs["source_scope"]
if scope["mode"] == "git":
    command.extend(["--source-repo", scope["repository"]])
subprocess.run(command, check=True)
PY
```

Read the result's warnings. With identical evidence, previous decisions are
preserved. Ranking or input-order changes alone do not invalidate them.
Context-only changes archive the old decisions, mark related events
provisional and related non-event decisions unresolved. Unrelated decisions
remain; new items are pending. This dependency check may revisit many events
under a shared condition, but does not mean those events should be merged.

Changes to source, snapshots or scope archive and reset the decisions.
If such a change was not intended, inspect the configuration before starting
another analysis. Additional files fetched by `review source --fetch` use a
separate cache and do not expand the baseline source inventory.
