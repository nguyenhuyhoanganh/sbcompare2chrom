# From a symptom to an identifier

## Contents

- Why grepping the report for the complaint fails
- The routing table: symptom → kind → how to search
- Working a symptom that names no identifier
- The three-hop chain behind a settings screen
- When the symptom is a build break

## Why grepping the report for the complaint fails

The report is indexed by **declaration name**. Nobody named a declaration
"downloads page lost its toggle". Searching for the words in a complaint returns
nothing, and that nothing means only that the complaint was phrased in English.

So the first move is never a search. It is deciding **which surface** the symptom
lives on, because the surface names the `kind`, and the `kind` narrows the search
to a few dozen rows instead of three thousand.

## The routing table

Counts are from one real M148 → M151 run, to show where the mass sits.

| Symptom sounds like | Surface | `kind` to search | Rows |
|---|---|---|---|
| A feature turned on or off; behaviour differs with no UI change | Browser C++ | `base_feature` | 507 |
| A knob inside a feature moved (timeout, threshold, variant) | Browser C++ | `feature_param` | 184 |
| A web page stopped working; a JS API is missing or new | Web platform | `idl_member`, `idl_interface` | 477 |
| A web feature is present but inert, or shipped to everyone | Web platform | `blink_runtime_feature` | 285 |
| Two processes disagree; a renderer crashes on a message; out-of-tree code fails to build | IPC | `mojo_method`, `mojo_field`, `mojo_struct`, `mojo_enum`, `mojo_interface` | 339 |
| A setting is not remembered; a profile value is ignored | Browser C++ | `pref` | 163 |
| A launch script or automation flag stopped taking effect | Outside repo | `switch` | 7 |
| A `chrome://flags` entry vanished or is scheduled to | Housekeeping | `flag_entry` | 783 |
| A control disappeared from a settings screen | WebUI | `webui_control` | 100 |
| A settings page or subpage is gone or moved | WebUI | `webui_route` | 8 |
| A screen renders but a section is hidden | WebUI | `webui_gate` | 169 |

Search within one kind by passing the prefix:

```bash
python3 skills/investigating-chromium-root-causes/scripts/why.py out/DIR webui_control:
```

That lists every row of that kind, ranked. Pick the one whose name matches the
screen, then re-run with its full uid.

## Working a symptom that names no identifier

Three moves, in order. Stop at the first that produces a name.

1. **Read the symptom for a proper noun.** Product features carry their flag
   name closely — "back/forward cache", "local network access", "autofill AI".
   Search that.

2. **Find the code that renders it, then read what gates it.** For a UI symptom
   this is faster than searching the report. Locate the template or the page in
   Chromium, find the `if` around the missing thing, and the guard names the
   flag or the pref. That name is the identifier.

3. **Search the report by path.** If you know roughly where the code lives, the
   script matches path fragments:

   ```bash
   python3 skills/investigating-chromium-root-causes/scripts/why.py out/DIR downloads
   ```

If none of the three produce a name, the symptom may not be a declaration change
at all — see `no-row.md`, Part A.

## The three-hop chain behind a settings screen

A WebUI symptom almost never has its cause on the WebUI surface. The chain runs:

```
control on the screen   →   the pref or gate it is bound to   →   the base::Feature behind that
   webui_control                 pref / webui_gate                      base_feature
```

**The user-visible moment is at the far end.** A control that vanished usually
moved behind a different guard, and what users noticed was the flag flipping,
which is a `base_feature` row somewhere else entirely.

So investigate all three hops before answering, and expect the CL to attach to
the last one. [reading-a-finding.md](reading-a-finding.md) walks the chain
in detail.

## When the symptom is a build break

A Mojo change breaks the build of code outside the tree, not inside it — both
ends inside Chromium are generated from the same `.mojom`, so a changed
signature compiles cleanly on both sides and fails only where someone else
implements the interface.

That makes the identifier easy: the compiler already named it. Take the symbol
from the error, convert it to the Mojo path (`blink.mojom.Interface.method`), and
search that.

The same is true in reverse for a **silent** break: `ipc_shape_changed` and
`ipc_signature_change` alter deserialization without any build error at all. If
a symptom is "messages stopped arriving" with a clean build, search the Mojo
kinds first.
