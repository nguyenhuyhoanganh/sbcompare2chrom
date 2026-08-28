# ChromeDrift Code Review, Testing, and Project Audit

> Initial assessment: August 21, 2026  
> Follow-up review: August 22, 2026  
> Provenance-stage review: August 28, 2026  
> Latest reviewed baseline: commit `71cba61` — schema `40`  
> History reviewed through that baseline: all 90 of 90 commits, from `d9fca08` through `71cba61`, including subjects, bodies, and the diffs behind the major decisions.  
> Scope: all Python source, extractors, targets, caching, snapshots, diffing, scoring, reports, tests, and the cached M130/M136/M139/M143/M147/M148/M151 data available in the project.

> **How to read this version of the report:** The original analysis has been retained to show where each issue came from. The review of `8ced148` is in Section 27, `b844108` in Section 28, `5edc91e`/`a88f5fc` in Section 29, `cd1ee05` through `0933dcd` in Section 30, `843dd96`/`bee9e7d` in Section 31, and `f56bafa` in Section 32. The closure review of `a4f13ec` is in Section 33. The review of the provenance stage added in `ab0eb47` through `25745ed` is in Section 34, and the review of the commit answering it, `71cba61`, is in **Section 35**, which supersedes earlier verdicts. Earlier sections preserve the reasoning as it stood at each baseline.

## 1. Start here if you are not deeply technical

ChromeDrift is designed to answer a question like this:

> “When Chromium moves from version A to version B, which technical declarations changed, and which changes should the product team investigate first?”

The tool already does many things well. It reads Chromium source, extracts tens of thousands of structured records, compares two versions, and produces a prioritized report.

The most important conclusion from this review is:

> **ChromeDrift meets its goal as an early-warning radar: it detects a useful subset of noteworthy changes so that people can investigate them before an uprev. The project neither needs to prove, nor currently claims to prove, that it finds 100% of all changes or can automatically declare an uprev safe.**

The project owner clarified that an **automated release gate is not part of the current acceptance criteria**. Older passages saying the project “does not yet meet release-gate requirements” should therefore be read as usage boundaries, not as a project-failure verdict. The correct standard for the current baseline is:

- Does it catch a useful set of changes early enough?
- Does each finding lead the reader to evidence they can verify?
- Is the output deterministic and stable enough for repeated use?
- Are blind spots and uncertainty stated clearly, rather than turning “not observed” into “definitely absent”?

Against that standard, the verdict is **pass**.

After reviewing the full commit history, the assessment of engineering quality is also more positive than it was initially:

- Many rules were not chosen arbitrarily. Commit bodies record measurements across M130–M151, approaches that were tried and rejected, and tests that preserve the resulting invariants.
- Removing AI judgment, fork/product scoring, and provenance from the core was deliberate. The core stops at evidence instead of pretending to understand product-specific usage.
- Determinism, scope guards, reference closure, and the score ceiling all have documented rationale and supporting tests.
- Function bodies, TypeScript behavior, `.grd` resources, and GN configuration schemas are documented exclusions, not areas the author forgot to implement.

Commit `f56bafa` closed the last duplication issue with meaningful yield: on M143 → M147 wide, stability findings fell from 196 rows to the correct 32 container rows, with all 164 duplicate method/field rows removed. Commit `a4f13ec` replaced two weak assertions with real behavioral seams/tests and constrained the scope of `PAIRED_ATTRS`. Bare `unittest discover` now runs all **368 tests** on both Python 3.14 and 3.9.

For the early-detection goal, the current baseline is **good enough to use now, and this audit is closed**. Across the full six-run matrix, no Breaking row is based solely on a `position` disappearing without type or ordinal evidence, and no member-level stability duplication remains. Per-surface first-match bias has been removed, current overload locations are rendered, both coverage sides are protected by behavioral tests, and `position` pairing is restricted to the two intended Mojo kinds. Unsupported grammar is disclosed. Parser edge cases with no current yield do not need immediate work.

In plain language:

- If ChromeDrift reports a dangerous change, open the source and verify it. The warning may be correct, but it can also be a false alarm.
- If ChromeDrift reports nothing dangerous, that still does not prove the uprev is safe. The tool may not have downloaded the file, the parser may not understand the syntax, or two different declarations may have been collapsed into one.
- M151 `wide` coverage is currently `8,295 / 8,366 (99%)`, leaving 71 files. This is file-scope coverage, not parser or product completeness. The raw M151 inventory still contains 85 callback definitions, 144 typedefs, 200 `includes` relations, 18 Mojo `feature` blocks, and hundreds of Mojo constants without corresponding fact kinds. For the current goal, documenting this known scope is enough; there is no need to implement every extractor immediately.
- A score of `75` does not mean “a 75% chance of failure.” It is a manually assigned weight used to order the report.

This is not a judgment that the project is poor. On the contrary, it contains several strong ideas, a substantial test suite, and disciplined code. The important thing is to keep describing it accurately as an early-warning inventory and never treat one instance of “not found” as proof of “does not exist.”

### If you do not want to read the entire report

Use this reading path:

- To understand what the tool does: Sections 2, 3, and 4.
- To assess whether the targets are sufficient: Section 5.
- To assess extractor completeness: Section 6.
- To understand conflicts across versions: Section 7.
- To understand facts and scoring: Sections 9, 10, and 11.
- To understand decisions recorded in commit history: Sections 17 and 18.
- To see which issues originally required the earliest attention: Sections 19, 20, and 21.
- To see the latest conclusion and recommended stopping point: Section 35.
- To understand the CL-and-issue provenance stage and what it can be trusted for: Section 34.

### Quick answers

| Question | Shortest accurate answer |
|---|---|
| Is the `default` target sufficient? | **Yes for a fast scan.** It is intentionally sampled rather than exhaustive. |
| Is the `wide` target sufficient? | **Yes for a broad scan under the current rules:** 8,295 / 8,366 candidate files. That is not 100% parser or product coverage. The 378 multi-surface files are now counted correctly for every relevant surface. |
| Does the tool extract everything from downloaded source? | No, and the current goal does not require it to. Overload signatures, gates, extended attributes, and locations are preserved better than before. Web IDL callbacks/typedefs/includes and Mojo features/constants remain documented, unmodeled scope. |
| How are two versions matched? | By `kind:key`, followed by comparison of an attribute allowlist. |
| How are conflicts within one version handled? | Most duplicates retain the lowest path/line. Web IDL overloads now merge signatures, gates, extended attributes, and variant locations. Locations do not participate in semantic diffing, which is correct. Current changed groups have at most five locations, all of which are rendered. |
| Are facts enough for a release verdict? | No. They are sufficient for inventory and manual triage. |
| Does the tool meet the goal of partial early warning? | **Yes.** It detects thousands of changes across real versions and provides evidence and prioritization for human triage. |
| Is score a failure probability? | No. It is a heuristic reading-order weight. |
| Do 368 passing tests prove completeness? | No test suite proves 100% completeness, but behavioral boundary tests plus the full six-run matrix provide strong enough evidence for the early-detection goal. |
| Should the project be used? | **Yes**, for early detection and manual triage. Continue prioritizing fixes that create noise or mislabel findings. |

## 2. A familiar analogy for the entire system

Imagine that we want to compare two supermarkets, A and B.

ChromeDrift follows a process much like this:

1. A **target** is the list of areas employees are instructed to inventory.
2. An **extractor** is an employee trained to read a particular kind of shelf: beverages, food, or electronics.
3. A **fact** is one inventory card, such as “the beverage shelf contains product X, 500 ml, priced at 20,000 VND.”
4. A **snapshot** is the full set of inventory cards for one supermarket at one point in time.
5. The **diff** places snapshots A and B side by side and finds products that were added, removed, or changed.
6. The **score** assigns a review priority to each difference.
7. The **report** presents those differences so a person can decide what to inspect first.

Historically, ChromeDrift's problems resembled these situations:

- The target list forgot several warehouses but still claimed the inventory was 100% complete.
- An employee recognized labels only in the form `Name(...)`, so labels written as `Name@0(...)` were missed.
- Two products with the same name but intended for different countries were collapsed into one; the tool kept whichever product sat on the alphabetically earlier shelf.
- A product sold only on Android appeared in a Windows report.
- An employee failed to read a shelf, made a small note, and continued; the final report was still generated as if nothing fundamental had gone wrong.
- Priorities came from general rules and did not know whether SB-AXon actually used a given product.

With this analogy in mind, the technical sections below are easier to follow.

## 3. Common terms

### 3.1. Ref and version

A `ref` identifies a Chromium source state.

Examples:

- `151`: an abbreviated milestone.
- `151.0.7922.138`: a full version.
- `refs/tags/151.0.7922.138`: a concrete Git tag.
- A branch or commit SHA can also be used as a ref.

A full version or commit SHA is more stable than a branch. A branch can point to different content over time even when its name does not change.

### 3.2. Target

A target tells the program which Chromium files or directories to download or read.

The project has three target sets:

- `minimal`: only a few files, used to verify that the pipeline works.
- `default`: a curated selection of files and directories, optimized for speed.
- `wide`: a much broader set of directory archives.

A target is not a fact. It only defines where extractors are allowed to look for facts.

### 3.3. Extractor

An extractor reads one family of source syntax. The project currently has nine main extractors:

1. `base_features`: `base::Feature` declarations and feature parameters.
2. `blink_runtime`: Blink runtime-enabled features from JSON5.
3. `web_idl`: Web IDL.
4. `mojom`: Mojo interfaces, methods, structs, fields, and enums.
5. `constants`: preference keys and command-line switches.
6. `flags_metadata`: `chrome://flags` metadata.
7. `webui_routes`: WebUI routes.
8. `webui_controls`: controls and preference bindings in WebUI templates.
9. `webui_gates`: data passed from C++ into WebUI through `AddBoolean`, `AddString`, and similar functions.

Extractors do not compile Chromium. Most rely on regular expressions and small custom parsers. This makes them fast, but they cannot understand every construct as fully as a compiler can.

### 3.4. Fact

A fact is a normalized record.

```json
{
  "kind": "base_feature",
  "key": "DeviceBoundSessions",
  "path": "components/.../features.cc",
  "attrs": {
    "default_state": "enabled",
    "platform_state": {"windows": "enabled"}
  }
}
```

A fact generally contains:

- `kind`: the type of fact;
- `key`: the identity used to match the fact across versions;
- `path` and `line`: the evidence location in source;
- `attrs`: the specific attributes that may be compared.

### 3.5. Snapshot

A snapshot is the complete list of facts extracted for one version, plus metadata such as target set, coverage, and extraction-error counts.

It is not a complete copy of Chromium. It is only what the tool saw and understood.

### 3.6. Diff

The diff compares facts from the old and new versions.

Two facts are treated as the same object when they share:

```text
kind:key
```

For example:

```text
base_feature:DeviceBoundSessions
mojo_method:network.mojom.CookieManager.GetAllCookies
idl_member:AudioNode.disconnect
```

After matching the two sides, the tool compares only attributes designated as meaningful. It does not compare every byte of source.

### 3.7. Signal, severity, score, and bucket

- **Signal:** a specific explanation of what changed, such as a Mojo method signature change.
- **Severity:** the initial weight assigned to the signal or fact type.
- **Score:** severity after policy adjustments.
- **Bucket:** the report group, such as Breaking, Behaviour change, New surface, or Housekeeping.

Score and bucket are related, but they are not the same concept.

## 4. How ChromeDrift runs, step by step

Assume this command:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --target-set wide \
  --no-enrich
```

### Step 1: Normalize the version

A full version becomes a tag:

```text
151.0.7922.138
→ refs/tags/151.0.7922.138
```

If the user supplies only `151`, the program asks ChromiumDash for the latest Windows stable patch in milestone 151 at run time. The same abbreviated milestone command can therefore resolve differently after the stable patch changes.

### Step 2: Select targets

The target set determines which files and directories are downloaded.

`default` uses a curated list. `wide` pulls larger directory archives such as `components/`, `chrome/browser/`, `services/`, parts of `content/`, `third_party/blink/`, and other roots.

### Step 3: Materialize source into the cache tree

Source from Gitiles or a local checkout is copied or extracted into a ref-specific cache directory.

### Step 4: Run extractors

Each file is tested against the extractor registry. If the path matches an extractor's `applies_to()` predicate, the extractor reads the text and creates facts.

### Step 5: Attach platform information and deduplicate

The tool attempts to determine whether each declaration belongs to Android, ChromeOS, iOS, or another platform. Facts with duplicate UIDs are then merged.

### Step 6: Save the snapshot

Deduplicated facts are written to the snapshot JSON cache.

### Step 7: Compare snapshots

Facts are matched by UID and classified as:

- `added`: present only in the new version;
- `removed`: present only in the old version;
- `modified`: present in both versions, with different meaningful attributes.

### Step 8: Detect selected renames and repoints

Several special cases are paired after the basic diff:

- A preference or switch was renamed while retaining the same C++ variable.
- A WebUI control changed the preference it writes.

Other forms of rename may still appear as one removal and one addition.

### Step 9: Score and render the report

The strongest signal determines severity. The scorer adjusts for platform and coverage, then renders Markdown, HTML, and JSON reports.

## 5. Are the targets sufficient?

### Short answer

**They are much better than they were at the start of the review, but they are not literally complete.**

- `minimal` is intentionally insufficient.
- `default` deliberately trades completeness for speed.
- `wide` reaches `8,276 / 8,349` candidate files at the schema-29 baseline, or roughly `99.1%`; 73 files that the denominator itself considered capable of declaring facts remained outside its reach.

### What commit `46dae58` fixed correctly

Before this commit, the denominator understood only two filename families: preferences and features/switches. `.mojom`, `.idl`, JSON5, and WebUI templates were not counted. The reported `1,164 / 1,164 (100%)` therefore graded the tool against a population that was far too narrow.

After the fix, `_discovery_rules()` derives predicates directly from all nine extractors in `REGISTRY`. Adding an extractor now expands the denominator automatically. This was an architectural improvement, not a cosmetic change.

Measurements from the M151 schema-29 cache were:

| Target set | Deduplicated facts | Candidate files reached | Total candidates | Share |
|---|---:|---:|---:|---:|
| `default` | 29,118 | 3,669 | 8,349 | 43.9% |
| `wide` | 54,451 | 8,276 | 8,349 | 99.1% |

The 73 missing candidates were concentrated under `chrome/services/`, `chrome/credential_provider/`, `chrome/installer/`, and a few smaller paths. Naming those paths was a substantial improvement: the gap became visible instead of being hidden behind 100%.

### Why denominator and extraction could still disagree

Although they shared `applies_to()`, the global file-eligibility policy still existed in two forms:

- `targets.py` used `_TEST_RE`, `_NOT_THE_PRODUCT_RE`, `_VENDORED_THIRD_PARTY_RE`, and `_OTHER_PLATFORM_RE`;
- `extract/__init__.py` used `SKIP_DIR_PARTS`, `SKIP_FILE_RE`, and `_other_platform()`.

A targeted check against the M151 listing found disagreement in both directions:

- The denominator counted two `content/web_test/common/*.mojom` files, while extraction intentionally skipped `/web_test/`. Those two files appeared among the 73 “unread” files even though extraction policy correctly considered them test code.
- The denominator excluded any filename containing `_test_`. That removed at least nine valid product APIs, including `cc/mojom/hit_test_opaqueness.mojom`, two Mojo files under `services/viz/.../hit_test/`, and six `xr_hit_test_*.idl` Web IDL files. The `wide` snapshot still contained facts from them.

The test at that time verified only that `rule.applies is extractor.applies`. It did not exercise the exclusions wrapped around those predicates.

In simpler terms, both paths asked the same question—“does this file have the right shape for the extractor?”—but still used different answers to “is this test or platform noise?” The claim that there was “no second list” was true for the file-type predicate, not yet for the full eligibility policy.

### What “read” actually meant

`coverage_against()` checked whether target scope could **reach** a candidate path. It did not prove that the file downloaded successfully, parsed successfully, or yielded every declaration as a fact.

So this message:

> “reads 8,276 of 8,349 files”

meant:

> “The declared target set can reach 8,276 candidate paths.”

It did not mean:

> “8,276 files were parsed perfectly and no declarations were lost.”

Missing targets and extraction errors were recorded separately, but the scorer initially received only a coverage scalar. A run could exceed 95% and confirm a removal even when one specific target failed to download; the report warned about the failure, but scoring did not consume it.

### Reference closure was also incomplete

After extraction, the tool checked selected links such as:

```text
WebUI route → gate
gate → base feature
control → preference
Blink runtime feature → base feature
feature parameter → owning feature
```

M151 results:

- `default`: 180 unresolved references.
- `wide`: 89 unresolved references.

Even according to the relationship graph the tool itself understood, the snapshots were not fully self-contained.

### Target conclusion

Do not say:

> “Wide covers 99%, so every absence is definitely a removal.”

Say:

> “Wide reaches 99.1% of candidate paths under the current policy. It is the broadest built-in target, but 73 paths, eligibility mismatches, parse completeness, and missing-target state must still be considered before confirming a removal.”

## 6. Does extraction capture everything?

### Short answer

**No. Both false negatives and false positives have existed.**

- A false negative occurs when source contains a changed declaration but no fact is created.
- A false positive occurs when a fact is created or interpreted incorrectly, producing a warning that does not apply to the product.

### 6.1. Mojo ordinal: extraction was fixed before comparison was fixed

Commit `46dae58` updated the parser to recognize both:

```text
MethodName(...)
MethodName@0(...)
```

That part worked. M151 contained 269 raw declarations with explicit ordinals across 23 files. After platform and test filtering, the `wide` snapshot increased from 5,903 to 6,099 `mojo_method` facts.

However, the commit also said the ordinal was “now a compared attribute.” At that baseline, this was not true.

`mojom.py` stored `ordinal` in `Fact.attrs`, while `diff.py` compared only:

```python
("signature", "params", "response", "attrs")
```

The ordinal was absent from the tuple, and the normalized signature did not include it.

Minimal probe:

```mojom
// old
interface I { Foo@0(int32 x); };

// new
interface I { Foo@1(int32 x); };
```

Result on `46dae58`:

```text
old fact ordinal: 0
new fact ordinal: 1
diff changes: 0
```

The new test asserted only that extraction stored `ordinal`; it did not compare two snapshots. Its comment claimed more than its assertion proved.

This was serious because wire ordinals sit directly on the process-boundary surface the project assigns its highest severities. The minimal correction was to add `ordinal` to `MEANINGFUL_ATTRS[KIND_MOJO_METHOD]` and add a regression test requiring `@0 → @1` to produce a `MODIFIED` change and the appropriate signal. Later commits did exactly that.

### 6.2. Web IDL: `margin-top` was fixed, while overloads still collapsed

Consider:

```webidl
disconnect();
disconnect(AudioNode destination);
disconnect(unsigned long output);
```

All three declarations were initially keyed as:

```text
AudioNode.disconnect
```

The maintainer's response was correct about one important issue: not every collision was an overload. The old regex parsed `margin-top` as `top`. Adding signatures to identity would have hidden the collision while leaving the name wrong. Fixing the parser first was the right decision.

The earlier report therefore should not have described all 133/138 collisions as overloads.

Even after the parser correction, an independent overload problem remained. A scan of raw M151 schema-29 facts found:

- 12,158 raw `idl_member` facts;
- 11,964 member UIDs;
- 121 UIDs with multiple declarations that differed on attributes the diff cared about.

Comparing raw overload sets between M148 and M151 showed:

- 109 UIDs existed on both sides but changed overload sets;
- deterministic dedupe happened to expose 107 because the selected overload also changed;
- two changes disappeared completely because the lowest `(path, line)` declaration remained unchanged.

The two reproduced false negatives were:

- `Navigator.install`: M151 added `install(InstallParams params)`, while `install()` remained the selected declaration on both sides.
- `Document.parseHTMLUnsafe`: overloads, options, and gates changed, while the selected declaration stayed the same.

The fair conclusion was:

1. Fixing the name parser before identity was correct.
2. Dedupe could still lose overload changes, and two real M148–M151 false negatives proved it.
3. The right next step was to retain a stable variant or overload set after parsing the correct member name, not blindly embed the raw signature in the UID.

### 6.3. Unmodeled Web IDL forms

The parser did not fully model:

- callback definitions;
- typedefs;
- `A includes B;` relations;
- complete mixin relationships;
- selected extended attributes on partial interfaces.

M151 contained at least:

- 91 callback definitions;
- 137 typedefs;
- 200 `includes` statements;

without corresponding model records at that baseline. `includes` is especially important because it determines which concrete interfaces receive a mixin's members.

### 6.4. Runtime gates on partial interfaces were not inherited by members

Conceptually:

```webidl
[RuntimeEnabled=ExperimentalFeature]
partial interface Navigator {
  void experimentalMethod();
};
```

`experimentalMethod` must inherit the partial interface's gate. The parser read attributes on the interface, but members initially received only attributes written directly before the member. A gated API could therefore appear as ordinary, reachable surface.

M151 contained 59 runtime-gated partial definitions with 100 members.

### 6.5. Parser failures could be swallowed

When an extractor raised an exception, the pipeline:

1. incremented an error counter;
2. logged the error;
3. skipped the file;
4. continued producing a snapshot and report.

Some JSON5/metadata parsers caught errors internally and returned an empty list, so the outer error count could still remain zero.

The failure mode was:

```text
Old parser does not understand new syntax
→ file produces zero facts
→ old facts appear removed
→ report emits a false Breaking change
```

For an automated gate, parse errors would need to make completeness unknown or fail the run. For the current early-warning role, they must at least be disclosed.

## 7. What happens when versions conflict?

There are three different kinds of conflict.

### 7.1. The same fact changes across old and new versions

This is normal:

```text
M148: base_feature:X = disabled
M151: base_feature:X = enabled
```

Both facts share `kind:key`, so they match and become a `modified` change. Neither side “wins”; the report preserves `before`, `after`, and the delta.

### 7.2. An object is renamed or changes identity

If the old key disappears and a new key appears, the default result is:

```text
removed old-key
added new-key
```

The project has specialized pairing for selected preference/switch renames through the C++ variable, and for WebUI control repoints. Other kinds do not all have equivalent rename detection.

A file move is usually harmless if `kind:key` is preserved, but a rename can appear as two separate events.

### 7.3. Multiple declarations conflict within one version

This is the more serious case.

Chromium often contains code like:

```cpp
#if BUILDFLAG(IS_WIN)
BASE_FEATURE(kExample, "Example", base::FEATURE_ENABLED_BY_DEFAULT);
#else
BASE_FEATURE(kExample, "Example", base::FEATURE_DISABLED_BY_DEFAULT);
#endif
```

The two declarations share a feature key but differ because they target different platforms.

ChromeDrift historically deduplicated by keeping the fact with the lowest `(path, line)`. This was deterministic but not semantic. It was equivalent to resolving contradictory documents by keeping the one stored in the alphabetically earlier drawer.

At the M151 schema-28 baseline before `46dae58`:

- 54,676 raw facts before dedupe;
- 54,255 facts after dedupe;
- 298 duplicate UIDs;
- 258 duplicate UIDs with different meaningful attributes.

The largest groups included:

- 133 IDL members;
- 25 WebUI controls;
- 23 WebUI gates;
- 20 base features;
- 19 feature parameters;
- 15 switches;
- 14 preferences;
- plus Mojo fields/methods and WebUI routes.

Real examples included:

- `GlicActor`: disabled on Android and enabled elsewhere;
- `DeviceBoundSessions`: enabled on Windows and disabled in another branch;
- `mojo_base.FilePath.path`: `string` or `array<uint16>` depending on build flags;
- `SocketBroker.CreateTcpSocket`: different signatures on Windows and non-Windows;
- WebUI key `disableAnimations`: true and false in different branches.

### Correct approaches

There are two defensible designs:

1. **Variant-aware model:** retain every variant and its condition.
2. **Platform projection:** resolve build conditions for Windows first, then retain only the variant compiled for Windows.

In either design, semantic conflicts must not disappear silently. A report should surface unresolved declarations as ambiguous or conflicting evidence.

## 8. Platform projection: the main defects were fixed

> **Status at `46dae58`: fixed for the two reviewed cases.** This section records the earlier failure and why the correction was sound.

### Intended behavior

If a declaration is excluded from Windows in both versions, its finding should score zero and fall under Housekeeping.

### Earlier failure

The base-feature extractor stored:

- `platform_state`, derived mainly from the macro body;
- `conditions`, representing enclosing `#if` directives.

The scorer used `platform_state`, but the extractor had not fully combined enclosing conditions into it.

```cpp
#if BUILDFLAG(IS_ANDROID)
BASE_FEATURE(kAndroidOnly,
             "AndroidOnly",
             base::FEATURE_ENABLED_BY_DEFAULT);
#endif
```

The parser could see `FEATURE_ENABLED_BY_DEFAULT` and record the feature as enabled, even though the entire declaration was Android-only.

### Measurements before the fix

In M151 `wide`:

- 441 base features had enclosing conditions excluding Windows;
- 428 were still recorded as actively enabled or disabled rather than `not_compiled`.

For M148 → M151:

- 141 findings whose source guards all excluded Windows still scored above zero;
- 28 scored 75;
- 19 scored 55.

Examples included Android-only `AccessibilityAtomicLiveRegions` and Mac-only `ApplicationAudioCaptureMac`.

The old path detector also missed exact `/mac/` and `/linux/` directory components. At least 79 Mojo facts in M151 sat in exact Mac/Linux directories without being marked `not_compiled` for Windows.

### Results after the fix

- `base_features._platform_states()` now combines macro default state with enclosing `#if` conditions.
- `PLATFORM_DIR_RE` includes exact `/mac/` and `/linux/` directories.
- The 79 M151 Mac/Linux Mojo facts now carry `platform_state.windows = not_compiled`.
- Default M148 → M151 score-zero findings rose from 118 to 187, reproduced from schema-29 snapshots.
- Regression tests distinguish Android-only declarations, Windows-relevant declarations, and undecidable conditions.

No concrete regression was found in these two corrections. Both can be marked **fixed**.

## 9. Are current facts sufficient for compatibility analysis?

### What the fact model does reasonably well

- Extracts and compares many common declarations.
- Provides source paths and lines as evidence.
- Separates features, Mojo, IDL, preferences, switches, flags, and WebUI.
- Makes it practical to explore thousands of differences between milestones.

### What the fact model does not prove

| Question | Can current facts answer it? | Why? |
|---|---|---|
| Did a `base::Feature` default change? | Usually | Enclosing platform guards were fixed, though conditions outside the supported grammar can remain `conditional`. |
| Did a common Mojo signature change? | Usually | Explicit-ordinal methods are now extracted; at the earlier baseline the ordinal itself was not yet compared. |
| Did a Web IDL overload change? | Historically unreliable | Same-name overloads were collapsed until later schemas retained variant sets. |
| Is an API actually exposed on Windows? | Not always | Build conditions and runtime gates are not universally complete. |
| Does SB-AXon use this symbol? | No | There is no product dependency or usage scan in the core. |
| Did C++ or TypeScript implementation behavior change? | No | The tool primarily reads declarations. |
| Is Finch enabling the feature for users? | No | Finch/server configuration is outside the source snapshot. |
| Does enterprise policy or automation depend on a switch or pref? | Not comprehensively | External consumers and configurations are not scanned. |
| Did a UI layout break? | No | The tool does not render or test interactions. |
| Will a Mojo change break a deployed peer? | Not completely | Lifecycle, version negotiation, and deployment topology are not fully modeled. |

### A high fact count does not prove completeness

M151 `wide` schema 29 contained 54,451 facts. That is a large number, but absolute count does not establish completeness.

For example, the parser added 196 explicit-ordinal methods to the snapshot, while the comparison layer still missed ordinal-only changes. Extraction count could improve while semantic diffing remained incomplete.

### Conclusion

Facts are sufficient for:

> “Give me a structured inventory of declarations the tool observed changing.”

They are not sufficient for:

> “No Breaking finding means the uprev is definitely safe.”

## 10. Comparison and scoring in plain language

### 10.1. Select meaningful attributes

Each kind has its own meaningful-attribute list. Examples:

- Base feature: default state, platform state, conditions, and C++ variable.
- IDL member: signature, member type, extended attributes, and runtime gate.
- Mojo method: signature, parameters, response, and attributes.
- Mojo field: type, ordinal, default, and attributes.
- Preference/switch: variable and platform state.
- WebUI route: path, parent, and guards.

Attributes outside the allowlist do not create modified findings.

### 10.2. Generate signals

The code derives a signal from change direction and deltas:

```text
Mojo method signature changed
→ Mojo ABI/signature signal

base feature disabled → enabled
→ default behavior enabled signal

preference appears only in old version
→ pref left scan signal
```

### 10.3. Choose severity

If a finding has signals, the highest-weight signal wins. Otherwise, severity comes from a base table keyed by `(kind, added/removed/modified)`.

Signals do not add together. Equal weights are resolved by signal name so output remains deterministic.

### 10.4. Adjust for platform

If every existing side has:

```text
platform_state.windows = not_compiled
```

the score becomes zero and the finding moves to Housekeeping.

This rule is sensible; its reliability depends on the accuracy of platform extraction.

### 10.5. Adjust removal confidence using coverage

At the earlier baseline, if a finding was `removed` and new-version coverage was below 95%:

```text
score = severity - 15
```

The reason is that absence in an incomplete scan can mean “moved to an unread file” rather than “deleted.” `pref_left_scan` and `switch_left_scan` also moved to Housekeeping when absence remained unconfirmed.

### 10.6. Simplified formula

```text
severity = strongest signal weight
           or base score when there is no signal

if definitely outside Windows on every side:
    score = 0
else if removal and coverage < 95%:
    score = severity - 15
else:
    score = severity

final score is clamped to 0..100
```

Later schemas refined this to use per-surface and direction-aware evidence, but the central principle remained the same: severity is a ceiling, and evidence can only reduce it.

### 10.7. Examples

#### Example A: Mojo signature change

If the signal table assigns severity 75:

```text
severity 75
not excluded from Windows
not a removal
→ score 75
```

This means only that the ranking policy puts the item near the top. It does not mean a 75% chance of application failure.

#### Example B: A declaration disappears from the default scan

With initial severity 65 and coverage below 95%:

```text
65 - 15 = 50
```

If coverage does not represent the relevant kind, even that 15-point reduction does not accurately express confidence.

#### Example C: Android-only feature

Intended result:

```text
not compiled on Windows
→ score 0
```

If platform state is parsed incorrectly, the finding can remain at 75 even though Windows never compiles it.

### 10.8. Why scoring alone cannot make a release decision

Scoring does not know:

- whether SB-AXon uses the API, flag, or preference;
- how many users exercise the code path;
- whether a fallback exists;
- whether Mojo endpoints deploy together;
- whether a similar change has caused incidents;
- the parser confidence of the fact;
- kind-specific coverage.

The score is therefore a **reading order**, not a **risk probability**.

## 11. How the coverage scalar distorts scores

The scorer currently receives one global coverage scalar for the new version. Commit `46dae58` fixed the global denominator, so the `default` scalar changed from an artificial value of roughly 5% to a more meaningful 43.9%. However, the underlying problem—using one scalar for every fact kind—remains.

Comparing M151 against the predicates used by the nine extractors and the current target scope gives the following picture:

| Extractor/surface | `default` | `wide` |
|---|---:|---:|
| Base feature | 363 / 3,003 = 12.1% | 2,963 / 3,003 = 98.7% |
| Blink runtime JSON5 | 1 / 1 = 100% | 1 / 1 = 100% |
| WebIDL | 2,161 / 2,165 = 99.8% | 2,161 / 2,165 = 99.8% |
| Mojo | 367 / 1,462 = 25.1% | 1,436 / 1,462 = 98.2% |
| Pref/switch constants | 9 / 529 = 1.7% | 526 / 529 = 99.4% |
| Flags metadata | 1 / 1 = 100% | 1 / 1 = 100% |
| WebUI routes | 1 / 1 = 100% | 1 / 1 = 100% |
| WebUI controls | 434 / 1,031 = 42.1% | 1,031 / 1,031 = 100% |
| WebUI gates | 534 / 534 = 100% | 534 / 534 = 100% |

Rows may overlap because one file can match more than one extractor. This is why the global total is not a simple sum of the table.

### Where response B3 is correct

The maintainer is right that:

- coverage currently affects scoring only on the removal path;
- file share is not the probability that a declaration was missed;
- the 12.1% figure should not be multiplied directly into severity as though it were a probability.

The flat `-15` penalty still has a reasonable rationale and does not need to be replaced with linear scaling.

### What response B3 does not resolve

Before applying the flat `-15`, the scorer must answer a yes/no question: **has absence been confirmed for this kind?** The answer must use coverage for that specific kind.

For example, under `default`:

- WebIDL reaches 99.8%, above the 95% confirmation threshold. An IDL removal should not be labelled “the tree was not read deeply enough” merely because global coverage is 43.9%.
- Pref/switch coverage is only 1.7%, while Mojo is 25.1%. Removals in those groups genuinely remain unconfirmed.
- WebUI gate coverage is 100%, yet it receives the same global state as pref/switch facts.

The new commit only logs the number of candidate files per rule, for example, “N file(s) could declare: web API definitions.” That is only a per-rule denominator. There is no numerator such as `target reaches N of M`; the value is neither stored in the snapshot nor passed to `Scope`.

“Per-extractor coverage” is therefore not a new scoring formula. It is the input required to apply the existing flat yes/no rule to the correct surface. The `-15` penalty can remain if that is the intended policy.

File-scope coverage also needs a separate parse-status axis: `parsed`, `unsupported`, `error`, or `skipped`. Reaching a file does not prove that the parser understood all of it.

## 12. Other sources of false positives

### 12.1. Mojo tests and fuzzers appearing in the product report

Commit `46dae58` added `/fuzzers/`, `/fuzzer/`, `/web_test/`, and `/web_tests/`, plus a filename regular expression covering `_test`, `_unittest`, `_browsertest`, `_fuzzer`, and `_test_api`, as well as an exact match for `fuzz.mojom`. The new regression examples are excluded correctly, and most of the original 151 noisy facts disappeared.

The filter still does not cover the common `_test_service.mojom` naming pattern. The M151 `wide` snapshot under schema 29 still contains 22 deduplicated facts from eight files whose names clearly identify test services, including:

- `components/media_router/.../media_router_traits_test_service.mojom`;
- `services/network/.../network_traits_test_service.mojom`;
- `ui/gfx/.../traits_test_service.mojom`;
- `ui/gl/.../traits_test_service.mojom`;
- `ui/ozone/.../wayland_overlay_config_traits_test_service.mojom`.

The accurate status is therefore **partially fixed**, not “test/fuzzer declarations never reach a product report,” as the current test name claims.

The solution should not be a broad rule that drops any filename containing `test`. Chromium has legitimate product APIs such as `hit_test_region_list.mojom` and `xr_hit_test_source.idl`. The broad `_TEST_RE` used by coverage currently excludes those files incorrectly. A shared eligibility policy needs tests in both directions:

- definite test services and fuzzers must be excluded;
- product terms containing `hit_test` must remain included.

### 12.2. Every `AddString` is labelled a visibility gate

The WebUI extractor accepts:

```cpp
AddBoolean(...)
AddInteger(...)
AddString(...)
AddDouble(...)
```

and labels all of them as gates.

However, `AddString("undoDescription", text)` is display content, not a visibility condition. A URL, metric name, background position, or error message is not a gate either.

M151 contains 764 facts of this form:

- 405 booleans;
- 319 strings;
- 40 integers;
- 655 with no reference to a base feature.

In the M148 → M151 diff, some string changes are described as “visibility condition changed.” The extracted text may be accurate, but the semantics are not.

These facts should be separated into at least:

- boolean visibility/capability gates;
- load-time data values;
- display strings;
- URL, metric, or config values.

### 12.3. Route guards lose negation

The following conditions mean opposite things:

```ts
if (loadTimeData.getBoolean('isGuest')) { ... }
if (!loadTimeData.getBoolean('isGuest')) { ... }
```

The parser stores only `isGuest`, not its polarity. The report therefore cannot tell whether the route is visible to guests or to non-guests.

### 12.4. String constants are classified too broadly

If a filename looks like a preference file, every matching string constant is treated as a preference. If it looks like a switch file, every matching string constant is treated as a switch.

That can turn option tokens such as:

```text
enabled
disabled
d3d11
bgra
auto
0
1
```

into command-line switches even when they are merely values accepted by an option.

Likewise, nested dictionary keys such as `name`, `id`, `hash`, and `install_time` can be labelled preference paths. A nested stored-data key may matter, but changing it does not have the same consequences as renaming a registered top-level preference.

### 12.5. Clusters can join unrelated findings

The code intends to join a Blink runtime feature to a base feature only when Chromium declares that relationship.

After that check, however, it still joins facts with the same name. For a Blink fact whose `base_feature` is `"none"`, matching names do not prove a relationship.

The M148 → M151 diff contains at least eight pairs clustered in this way.

An incorrect cluster does not alter the raw diff, but it can make the report tell a false “change story” and lead readers to assume that several findings share one cause.

## 13. Cache and reproducibility

### What currently works well

- A full version resolves to a concrete tag.
- Snapshot caches carry a schema version.
- The target set, partition, and `complete` flag are included in the snapshot name.
- The diff rejects snapshots with incompatible target configurations.
- For sufficiently large snapshots, the diff rejects a pair when one side contains fewer than half as many facts as the other.

### What is still missing

The cache key does not include:

- source type: Gitiles or local checkout;
- local checkout path;
- local checkout HEAD SHA;
- content/tree hash;
- platform;
- target-definition hash;
- extractor code hash/version beyond the manually maintained schema number.

### Failure scenarios

#### Scenario A: two local checkouts use the same ref label

```text
Run 1: ref M151 + checkout A
→ stores snapshot M151

Run 2: ref M151 + checkout B
→ cache hit occurs before checkout B is inspected
→ returns A's snapshot while the user believes it came from B
```

#### Scenario B: refresh leaves a deleted file behind

Materialization currently copies new files into a shared existing tree. It does not build an empty tree and replace the old one atomically.

```text
The previous tree contained old_file.mojom
The new source no longer contains that file
refresh copies only files that currently exist
old_file.mojom may remain in the cached tree
the extractor continues to see the old fact
```

#### Scenario C: a raw branch moves

A branch with the same name can point to a new commit. A cache keyed by branch name cannot distinguish the old commit from the new one. Separate fetch requests are also not proven to have come from the same commit if the branch moves during a run.

#### Scenario D: an old report schema

The report-rendering command reads JSON into the model without checking its schema. An old report produced with different scoring or bucket semantics can therefore be rendered by the current code as if it were current.

### A safer design

Every artifact should record:

```text
requested_ref
resolved_ref
resolved_commit_sha
source_kind
source_path or source URL
tree/content hash
target-definition hash
extractor/schema version
platform
creation time
```

The cache should be stored under the commit SHA and built in a temporary directory, followed by an atomic rename when complete.

## 14. Security issues

### 14.1. Inline `</script>` injection is fixed; unsafe spec URLs remained open

The HTML report embeds finding JSON directly in JavaScript:

```html
<script>window.__FINDINGS__=...;</script>
```

Before `46dae58`, `json.dumps()` did not escape the string `</script>`. If a fact name or report value contained:

```html
</script><script>/* JavaScript code */</script>
```

the browser could end the data script early and execute the injected script when the report was opened.

Escaping the DOM later would not fix this because the payload had already escaped the script element while the HTML was being parsed.

The current fix uses `_embed()` to escape `<`, `>`, `&`, U+2028, and U+2029 before placing JSON inside the inline script. The targeted payload no longer contains a literal `</script>` and still parses back into the original JSON. The original zero-click/script-breakout issue can be marked **fixed**.

Another HTML path still needed attention: `summary.milestone_brief[].spec` was HTML-escaped and inserted directly into `href`. HTML escaping prevents quote breakout but does not block a dangerous URL scheme.

A probe using:

```json
{"spec": "javascript:alert(1)"}
```

produced:

```html
<a href="javascript:alert(1)" rel="noreferrer">...</a>
```

This is a click-triggered risk and less severe than a `</script>` payload that runs as soon as the file is opened. It still should not exist in a report whose data may be edited manually or supplied through remote enrichment. Links should be rendered only for `https:` and `http:` URLs; other schemes should appear as plain text.

### 14.2. The main cache traversal is fixed; the sanitizer remains duplicated

`snapshot._safe_name()` now uses an `[A-Za-z0-9._-]` allow-list, replaces backslashes and unusual separators, and collapses `..`. The probe `..\..\victim` can no longer escape the snapshot/tree cache. Existing names such as `refs_tags_151.0.7922.138` remain unchanged. The original serious issue can be marked **fixed**.

The project still has a second `_safe_name()` in `acquire.py` for the listing cache. This version continues to return the exact string `..` unchanged:

```text
acquire._safe_name("..") == ".."
```

As a result, a listing path can move from `cache/listings/<ref>/...` up to `cache/...`. In this probe it is no longer the original whole-source-tree unpack path and does not escape the entire cache root, so the severity is lower. Still, maintaining two sanitizers for the same trust boundary invites future drift.

The best fix is one shared function, or a hash, for every cache component; reject `.`/`..` and Windows reserved names, then check `commonpath` where the path is constructed.

### 14.3. Proxy credentials: fixed

`_redact_proxy()` now preserves the scheme, host, and port while replacing user information with `<redacted>`. Both credentialed and non-credentialed cases have tests. No other CLI path that prints the proxy was found.

```text
http://user:password@proxy.corp:8080
→ http://<redacted>@proxy.corp:8080
```

## 15. What do the current tests prove?

### Positive results

The command documented in the README:

```bash
python3 -m unittest discover -s tests -q
```

runs **316 tests**, all of which pass on Python 3.14.6.

In addition:

- the Python source compiles;
- the CLI starts;
- the report JavaScript has no syntax errors;
- the Git whitespace check is clean;
- the available M143/M147/M148/M151 snapshots report neither extraction errors nor missing targets in their current metadata.

### What 316 tests do not prove

Many tests check internal consistency. For example:

```text
README says 54,451 facts
snapshot also contains 54,451 facts
→ test passes
```

If the extractor had always missed the same family of declarations, however, the README and snapshot would still agree. Such a test does not compare the output against an independent compiler/AST oracle or a complete Chromium inventory.

The 11 new tests are valuable improvements and catch the specific payloads and cases introduced by the commit. They still do not cover:

- a changed Mojo method ordinal for which comparison returns zero changes;
- 121 collapsed WebIDL overload UIDs and the two M148–M151 false negatives;
- disagreement between global eligibility rules used by coverage and extraction;
- `_test_service.mojom` files that still pass the filter;
- per-kind coverage not being passed to `Scope`;
- duplicate raw UIDs with different semantics;
- an unsafe URL scheme in a spec link;
- the duplicate sanitizer in the listing cache;
- cache reuse between two different local sources;
- report JSON with an incompatible schema;
- differing default unittest-discovery behavior across Python versions.

### A green command can still discover zero tests

From the repository root:

```bash
python3 -m unittest discover
```

the runtime used for this review produced:

```text
Python 3.14.6
Ran 0 tests
NO TESTS RAN
exit code 5
```

The earlier report statement that this command “completed successfully” is therefore **incorrect for the current runtime**. Maintainer response B1 is correct on that point.

The compatibility risk is still real: [CPython 3.12](https://github.com/python/cpython/blob/3.12/Lib/unittest/main.py) added `_NO_TESTS_EXITCODE = 5`, while [CPython 3.11 source](https://github.com/python/cpython/blob/3.11/Lib/unittest/main.py) does not contain that branch. The project README lists Debian with Python 3.9 as fully working. Across part of the runtime range in the project's own compatibility matrix, zero-test discovery may therefore still exit with code 0.

The accurate conclusion is that CI is not guaranteed to remain green on every runtime, but the default command is still unreliable because it discovers no tests; the exit code only determines whether the surrounding system notices.

CI should have an explicit guard:

```text
test count must be greater than 0
```

and `tests/` should either become a package or use a standard configured runner. The guard remains useful even when newer Python versions already return code 5, because it makes the project contract independent of standard-library version behavior.

## 16. What the project does well

For balance, the project has a substantial foundation worth retaining:

- The pipeline is divided into clear modules: acquire, target, extract, snapshot, diff, score, cluster, and report.
- The Fact model lets reports cite path and line evidence instead of presenting vague prose.
- Extraction and output are sorted to reduce nondeterminism.
- Snapshots carry a schema version.
- A guard prevents comparison between incompatible target sets or partitions.
- A lopsided fact-count guard blocks severely truncated checkouts.
- Missing targets generate warnings.
- Some surfaces support rename/repoint detection.
- Reports explain the reasons behind a score.
- Tar extraction checks for path traversal, and subprocess calls do not use shell strings.
- The test suite is substantial for a Python project using only the standard library.
- Code comments preserve many historical bugs and design reasons, which helps maintenance.

This foundation is worth developing further. The parts that need revision are the definitions of completeness, identity/variants, and provenance; the entire project does not need to be rewritten.

## 17. What does the full 66-commit history tell us?

### 17.1. Why the commit messages in this repository matter

In many repositories, commit messages say little more than “fix bug” or “update docs.” This repository is different: commit bodies usually document:

- the question the author was trying to answer;
- measurements from real milestones;
- the first approach attempted and why it was wrong;
- the accepted trade-off;
- the invariant and test added to preserve the decision;
- the schema that needed to be bumped;
- what was deliberately left out.

Reading only the source at `HEAD` can therefore lead to an unfair assessment. Looking at `score.py` alone, for example, the `-15` penalty may appear arbitrary; the body of commit `bafc44a` explains why it is not scaled by file coverage and provides data from six real comparisons. Conversely, commit messages also help expose bugs: `47e6dae` says a Blink flag with `base_feature: "none"` will not be clustered by name similarity, yet the source added in that same commit still joins matching names immediately after the guard.

The history is a straight line of 66 commits with no merge commits, produced mainly by one author from the evening of 16 August through 22 August 2026. In roughly five days, the project grew from 60 to 316 tests and reached schema 29. This is the pace of a prototype under concentrated audit, not evidence of a release gate that has been stable for a long time.

### 17.2. Phase 1 — building the pipeline and identifying the product-integration problem

| # | Commit | Decision recorded in the commit message | Relevance to this review |
|---:|---|---|---|
| 1 | `d9fca08` | Created ChromeDrift; download a small tarball rather than a full checkout, normalize before diffing, and make stages deterministic before allowing AI to judge a shortlist. | Established a sound semantic-diff foundation, although several current parser grammars also began here. |
| 2 | `bdeccf3` | Rewrote the README from scratch to explain why Chromium diffs are hard to read. | Documentation was treated as part of the product from the beginning. |
| 3 | `85b4b29` | Removed the top-findings cap; route by product/infra/platform because feature-based scope hid 1,802 of 2,226 findings. | The author measured and avoided filtering out high-severity rows. |
| 4 | `47e6dae` | Added WebUI routes, controls, and gates, plus union-find clustering by declared edges rather than name similarity. | The intent is correct; the implementation in the same commit contradicts it for Blink `base_feature:none`. |
| 5 | `67ec4a1` | Separated “not read” from “deliberately not read”; stated explicitly that TypeScript behavior is outside the model. | Function bodies and TS logic are declared scope boundaries, not forgotten bugs. |
| 6 | `85be946` | Added fork mode and separate checkouts for each side; uprev and fork comparisons need opposite vocabulary. | Shows that the author tested real product/fork semantics. |
| 7 | `b8aab1d` | Added provenance states to distinguish stale merge debt from deliberate divergence. | A two-way diff cannot infer intent; the history already recognized this. |
| 8 | `9a3ee25` | Recognized that forks commonly shadow upstream with build flags; added enclosing conditions. | Build conditions became important facts early in the project. |
| 9 | `7ace48b` | Wrote a HANDOFF for work requiring internal source, an LLM, and merge history; openly listed what had never been run. | Good transparency; the repository cannot measure product evidence by itself. |
| 10 | `c7b2805` | Measured the target gap: 964 missing features and Lit templates; keyed the cache marker by filter hash. | Began the recurring principle: do not guess completeness. |
| 11 | `062e7a2` | Expanded feature filename rules while excluding test declarations. | Clear policy: test code must not enter the product report. |
| 12 | `db760d6` | Added `catalog` through a blobless clone, turning the coverage gap into a measurable list. | A strong architectural decision that remains valuable at `HEAD`. |
| 13 | `cc61534` | Fixed the platform to Windows desktop; added partitions and included the partition in the cache key. | Windows is a core contract, not a decorative option. |
| 14 | `2c96550` | Fixed fork mode being lost between stages, 404 cache poisoning, and CLI flags that were accepted but ignored. | Cross-stage drift is a recurring defect class. |
| 15 | `3839704` | Unified meaningful attributes, added an orphaned state, normalized legacy feature shapes, and rejected the wrong platform profile. | “One fact, one definition” became a design principle. |
| 16 | `d8e7728` | Corrected a skill that overstated capability; disclosed low coverage; measured WebIDL overload and Mojo key collisions. | WebIDL overloads became a known limitation, while Mojo ordinals were not yet checked. |

### 17.3. Phase 2 — bounded completeness, independent oracles, and removing AI judgement

| # | Commit | Decision recorded in the commit message | Relevance to this review |
|---:|---|---|---|
| 17 | `7f76597` | Added `--complete` using roots and reference closure; completeness can be proven only over a bounded surface. | A better definition of completeness than one global scalar. |
| 18 | `18a119e` | Documented coverage and the pipeline, including evidence layers and material outside the model. | Made the declaration-only boundary explicit. |
| 19 | `0dde1fc` | Explained mechanisms with real output: guards, the three-valued evaluator, diff passes, renames, and clustering. | Improved auditability and reproducibility. |
| 20 | `4dffad3` | Discovered vendor files by marker instead of relying on user memory; separated FIXABLE from OUT OF MODEL. | Correctly recognized that fetching more does not help if the parser cannot read it. |
| 21 | `c51c754` | Measured an HTML freeze with 3,120 findings; added paging, lazy details, debounce, and event delegation. | Report performance was measured empirically; this commit also inserted JSON directly into a script, creating the later XSS issue. |
| 22 | `6b646df` | Reduced table layout cost on low-powered Windows machines and explicitly stated that no real browser was available locally for testing. | The commit body distinguishes measured results from inference. |
| 23 | `6e465d5` | Built an independent oracle for Settings routes, gates, and preference-bound controls, reaching 100% recall within that scope. | Stronger test quality than self-consistency alone, though the oracle covers only one surface. |
| 24 | `7f970b8` | Created a walkthrough of nine declaration sources and explained why function bodies are not read. | Reinforced a deliberate scope boundary. |
| 25 | `895f2ec` | Made the pipeline HTML standalone, UTF-8, and offline. | Air-gapped/offline use is a genuine requirement. |
| 26 | `e94a65c` | Made comparison and scoring interactive instead of merely descriptive; checked scenarios in code. | Documentation gained executable consistency. |
| 27 | `34d3297` | Generated a Confluence-ready pipeline PNG from editable HTML. | Primarily documentation/UX; later removed to prevent duplicated copies from drifting. |
| 28 | `7ffc0fa` | Removed all AI judgement; the tool stops at evidence because an AI failure can look like a clean result. | A sound decision; the core should not be expected to make the product verdict itself. |
| 29 | `55dee51` | Rewrote the pipeline for readers outside the project, retained technical vocabulary, and added identity rules. | Readability is an explicit goal. |
| 30 | `1868c48` | Grouped 13 fact kinds by consequence rather than calling everything a feature. | Reduced semantic mislabelling in the report. |
| 31 | `d5bf1e3` | Carried the suffix filter from fetching into extraction; fixed 803 false Mojo removals caused by a cached tree broader than the active scope. | Scope isolation has strong supporting evidence. |
| 32 | `7e0e66d` | Read every preference-name file; 892 of 1,575 keys had been missing; changed uncertain deletion to `left_scan`. | Absence uncertainty was understood in depth. |

### 17.4. Phase 3 — unifying definitions, determinism, and report-layout experiments

| # | Commit | Decision recorded in the commit message | Relevance to this review |
|---:|---|---|---|
| 33 | `7d549e1` | Audited six versions; fixed symbol renames, control repoints, `*_prefs`, false preference bindings, and Blink attributes. | Kind-by-kind comparison caught several real defects. |
| 34 | `afe7e44` | Measured candidates from the tree on each run; added default/wide modes and printed coverage. | The two current `DISCOVERY_RULES` groups began here. |
| 35 | `e739567` | Kept the minimal mode small, measured partitions separately, synchronized docs, and disclosed Mojo/WebUI/content gaps. | Scope modes have clear meanings. |
| 36 | `095990a` | Expanded Mojo/WebUI/content and the ChromeOS preference exception; first described `wide` as 100%. | The coverage label began to exceed its real denominator. |
| 37 | `d44aa5a` | Unified scope and candidate rules; fixed bare `switches.cc`, the flags denominator, and ignored CLI flags. | Continued the effort against duplicated definitions. |
| 38 | `04b7d86` | Introduced one `READABLE_SUFFIXES`, separated tree coverage from area coverage, and unified `kFoo→Foo`. | A good single source of truth, though `READABLE_SUFFIXES` still does not represent the full extractor registry. |
| 39 | `5a34072` | Sorted traversal and deterministic dedupe; fixed gate/control identity; documented every meaningful attribute. | Reproducibility was fixed correctly; arbitrary semantic selection was acknowledged. |
| 40 | `6e71be2` | Fixed line evidence; stopped reading Extensions IDL and MIDL as WebIDL; sorted every traversal. | “Reading the wrong dialect is worse than disclosing a gap” is a sound principle. |
| 41 | `f57ad95` | Added per-screen summaries and human-friendly wording. | Improved readability without changing fact counts. |
| 42 | `4a62ed7` | Tried a layout organized around reader questions, grouped by signal and surface. | Centralized derived values to prevent renderer drift. |
| 43 | `c08ea00` | Removed vendor names from the tool; stopped guessing a marker when input is missing. | Made the core a generic Chromium comparator. |
| 44 | `e948063` | Tried a team/surface menu because there were too many signal headings. | A UX experiment backed by measurement and browser verification. |
| 45 | `bc32bf9` | Removed the menu and returned to one table because it broke global search and sorting. | The author was willing to revert an ineffective design. |
| 46 | `2f5a04b` | Removed the change column but retained the direction glyph at the start of each row. | Reduced clutter without losing information. |
| 47 | `cf658e0` | Increased spacing between cards and filters. | Presentation-only change. |
| 48 | `7830a05` | Standardized the HTML report design system. | Presentation/offline UX change. |

### 17.5. Phase 4 — a second coverage audit, evidence-only scoring, and Mojo data

| # | Commit | Decision recorded in the commit message | Relevance to this review |
|---:|---|---|---|
| 49 | `725ce2e` | Replaced the severity bar with a color wash because rounded corners made the bar look broken. | Presentation. |
| 50 | `e96b9fa` | Tried a glass design, including fallback and performance/offline considerations. | Presentation experiment. |
| 51 | `0c6816b` | Reverted the glass design immediately afterward. | The history preserves rejected decisions as well. |
| 52 | `c775a3d` | Synchronized documentation with the single-table layout and recorded why two layouts were rejected. | The commit body serves as a design record. |
| 53 | `9afafdd` | Took the WebUI handler root from the extractor rather than repeating a literal. | A precise single-definition fix. |
| 54 | `0be4212` | Audited M143/M147/M148/M151; replaced curated lists with rules and fixed params, prefs, Blink attrs, enrichment, and reporting. | One of the strongest audit commits; bumped schema to 22. |
| 55 | `8727f7f` | Found that the denominator graded only known scope roots, moved it to the whole tree, blocked truncated checkouts, and surfaced missing targets in reports. | The history had already encountered the same “false 100%” defect class under review. |
| 56 | `b57bc54` | Added 13 roots to reach 1,164/1,164 under the current rules and called `wide` a release gate. | Success under a narrow rule, but a promise broader than that rule. |
| 57 | `40f493c` | Synchronized all documented figures and behavior after the two coverage commits. | Documentation was managed seriously. |
| 58 | `bafc44a` | Removed fork/profile/provenance/product vocabulary; the core now compares only two Chromium versions; rewrote severity, score, and buckets. | The evidence-only boundary is central to `HEAD`. |
| 59 | `8beed19` | Defined the `flag_expiring` exception within Housekeeping. | Refined reading order for the use case. |
| 60 | `3283289` | Added Mojo structs, unions, fields, and enums; fact counts became 29,118/54,255; schema 26. | Greatly increased semantic coverage without expanding the file-coverage denominator. |
| 61 | `0e91541` | Asked surface-specific questions; added Mojo platform gates, WebIDL live/gated signals, and owner routing. | Strong platform/gate architecture that also exposed the base-feature integration gap. |
| 62 | `70772fa` | Unified path-platform rules and marked a UID only when all its declarations were outside Windows. | Fixed 164 false positives; the “all declarations outside Windows” principle is worth retaining. |
| 63 | `7a695de` | Stopped treating flag lifecycle as the whole story; separated gated and ungated contracts. | Better framing: Mojo, prefs, and switches do not follow a flag's lifecycle. |
| 64 | `9ca63f1` | Reduced the skill to a procedure and moved evidence into the README. | Baseline of the first review: 304 tests and an evidence-first workflow. |

### 17.6. Phase 5 — responding to external review

| # | Commit | Decision recorded in the commit message | Relevance to this review |
|---:|---|---|---|
| 65 | `a864787` | Fixed four stale headline figures and added tests that read prose in the README, pipeline, and skills. | Proactively turned part of the documentation into a checked contract, but the matcher covered only three sentence patterns, so many stale 5%/100% figures and the old bucket table still passed. |
| 66 | `46dae58` | Independently verified each external-review claim against M151; fixed the denominator, platform handling, parser, security/cache/logging, and added 11 tests. | A serious response with many correct schema-29 fixes. The message also became an oracle for omissions: it says Mojo ordinal is compared, while `diff.py` and a probe show that it is not. |

## 18. Reassessment after reading the commit history

### 18.1. Criticisms that should be reduced

#### No product-specific score

At first this may look like an omission. The history shows that it is an appropriate boundary: the project once had fork/profile/AI stages, measured that the buckets lost meaning, and deliberately removed them. Core evidence should not guess SB-AXon usage.

> This is not a correctness bug. It is why the tool should supply input to the release workflow rather than replace the entire workflow.

#### Deterministic dedupe

The `(path,line)` rule is arbitrary, but it fixed a real problem: diffing a tree against itself once produced 68 phantom changes because of filesystem order. Determinism should not be removed before a better variant model exists.

> Reproducibility is good. Semantic conflict resolution remains incomplete.

#### Flat removal penalty and leading signal

Both have measurements and rationale. The leading signal fixed hundreds of over-ranked rows; the flat `-15` avoids pretending that file coverage is a probability.

> The heuristic ranking is better designed than the code may initially suggest; missing per-kind confidence is a separate issue.

#### Cache behavior in general

The full immutable-tag workflow has accumulated markers, schema checks, scope checks, and lopsided-count guards across multiple commits.

> Pinned-tag caching is reasonably strong; provenance for local checkouts and raw refs remains weak.

#### Function bodies, TypeScript, GN, and UI layout

These have been documented exclusions from early in the project.

> They should not be called extractor defects. They do, however, show why the tool cannot make a comprehensive release verdict on its own.

### 18.2. Issues whose severity should be raised

#### The coverage contract and release-gate wording

The history twice discovered denominators that graded only the region already known to the tool. Commit `46dae58` correctly fixed the larger issue by deriving predicates from the full extractor registry; `wide` now covers 99.1% of 8,349 candidates.

> The criticism can be reduced: the core denominator fix is good. The remaining issues are shared eligibility, per-kind/parse completeness, and a lingering release-gate promise in the CLI.

#### Explicit Mojo ordinal

The history treats Mojo as a high-severity runtime contract. The parser now reads explicit method ordinals, but the diff allow-list still omits `ordinal`.

> This remains a correctness blocker, though the defect has moved from extraction to comparison. It needs a regression test that crosses both snapshots.

#### Windows projection for base features

Several commits built one platform verdict shared by C++ `#if`, Mojo `[EnableIf]`, and paths. Commit `46dae58` connected the base feature's enclosing `#if` to that verdict.

> This item is fixed; it remains in the history to explain the change in zero-score counts.

#### Mojo test/fuzzer facts

Commit `062e7a2` and comments from `095990a` both say test code is noise and must be excluded. The new filter removes most `_test.mojom`/fuzzer facts, but 22 `_test_service.mojom` facts remain.

> This is a partial fix. It needs a shared, bidirectional eligibility test that excludes `_test_service` while retaining `hit_test` product APIs.

#### Blink clusters with `base_feature:none`

Commit `47e6dae` explicitly says not to join by name similarity when the source declares `none`; the code introduced by that commit still performs an unconditional same-name join immediately after the correct guard.

> This is a definite bug and does not depend on product-semantics interpretation.

### 18.3. Conclusion after reading the history

Before reading the history, the project can look like a prototype full of lightly considered heuristics. After reading the subjects, bodies, and diffs, a fairer description is:

> **This is a prototype with strong engineering discipline, a good measurement culture, and many sound decisions. However, it evolved too quickly in under five days, so contracts among target selection, extraction, coverage, platform handling, and reporting continued to drift.**

The history increases confidence in path/line evidence, deterministic output, basic semantic normalization, and usefulness for manual review. It does not prove that `wide` fetches everything, that absence always means removal, that Windows scores are correct for every kind, or that a clean report means an uprev is safe.

The release-gate verdict therefore remains **not ready**, while the engineering-quality verdict rises from “fair” to **“good, but not mature.”**

## 19. Current assessment matrix

| Area | Assessment | Short explanation |
|---|---|---|
| Code structure | Good | Clear modules; the pipeline is easy to trace. |
| Design rationale in commit history | Good | Decisions usually include measurements, rejected alternatives, and an accompanying invariant/test. |
| Determinism | Good | Sorting and deterministic dedupe remove phantom diffs; semantic variants are still not resolved correctly. |
| Target completeness | Greatly improved, not complete | `wide=99.1%` over 8,349 candidates; 73 paths remain and eligibility policy is still duplicated. |
| Extraction completeness | Not complete | Mojo methods are now extracted but ordinal changes are not diffed; WebIDL forms/overloads and fail-open parsing remain. |
| Windows platform handling | Ready for the reviewed findings | Base-feature enclosing guards and exact `/mac/`/`/linux/` matching were fixed, with tests and real data. |
| Cross-version diff | Reasonable for simple cases | `kind:key` is easy to understand, but rename and variant handling are incomplete. |
| Fact model | Partial | Good for inventory, insufficient for a compatibility verdict. |
| Core scoring | Fair to good for evidence triage | Leading-signal and score-ceiling choices are measured; per-kind confidence is absent. |
| Product relevance | Deliberately out of scope | Correct for the core; a downstream integration layer is needed in a release workflow. |
| Cache with a full tag | Fair to good | Schema/scope/marker guards are useful; commit/content hashes should still be recorded. |
| Cache with a local/raw ref | Not ready | HEAD/content is not pinned, and stale overlay/reuse is possible. |
| Report UX | Fair | Evidence and grouping are useful, but some labels are semantically wrong. |
| Security | Main issues fixed, residual risk remains | Inline script breakout, main cache traversal, and proxy leakage are fixed; unsafe spec schemes and the duplicate listing sanitizer remain. |
| Documentation contract | Inconsistent | The README has the 43%/99% table, but active passages still say 4–5%/100%; the CLI still calls `wide` a release gate. |
| Tests | Good for regression, insufficient for completeness | 316 pass; new tests are valuable, but the Mojo test stops at extraction, the coverage test ignores global filters, and prose tests match only a few sentences. |
| Release gate | Not ready | False negatives and false positives are not controlled sufficiently. |

## 20. Recommended order of fixes

### Phase 0: Prevent false conclusions and close obvious vulnerabilities

Prioritize these immediately:

1. Remove the remaining release-gate promise from the CLI and correct every active passage that still says 4–5%/100%.
2. Validate URL schemes for spec links; inline JSON escaping is already fixed.
3. Share one cache sanitizer across snapshot/tree/listing and reject special path components; the main Windows traversal is already fixed.
4. Validate schema when reading snapshots and reports.
5. If there is an extraction error or missing target, mark the report `incomplete`; the scorer must not confirm a removal from scope coverage alone.
6. Make CI assert that the test count is greater than zero on every supported Python version.

### Phase 1: Fix core correctness

1. Add `ordinal` to Mojo method comparison and test `@0 → @1` at the diff layer.
2. Unify all eligibility, skip, and platform policy between coverage and extraction, not just `applies_to()`.
3. Store coverage per extractor/kind and use it for removals of the corresponding kind.
4. Give every file a status: `parsed`, `skipped`, `unsupported`, or `error`.
5. Redesign the IDL representation to retain overload variant sets after the parser returns the correct name.
6. Parse callbacks, typedefs, and `includes`.
7. Propagate partial-interface gates to members.
8. Complete test/fuzzer filtering with bidirectional rules, including `_test_service` while retaining `hit_test` product APIs.

### Phase 2: Fix conflicts and provenance

1. Do not drop conflicting fact variants.
2. Include condition/platform in identity or a variant set.
3. Pin snapshots to commit SHAs.
4. Verify that a local checkout's HEAD matches the requested ref.
5. Include target/extractor/config hashes in the cache key.
6. Build a new tree in a temporary directory instead of overlaying the existing one.
7. Add a file lock for concurrent runs.

### Phase 3: Add downstream evidence specific to SB-AXon

Do not put product guesses back into core scoring. Keep the core as evidence between two Chromium versions, then add an optional layer that accepts evidence supplied by SB-AXon.

Keep these axes separate and display them independently:

```text
severity: how serious could the consequence be if the change is real?
extraction confidence: how certain are we that extraction/diff captured it correctly?
product relevance: is there evidence that SB-AXon uses this contract?
exposure: how broad is the affected code path or user population?
```

Then add:

- an SB-AXon dependency/usage scan;
- config, policy, and automation inputs;
- endpoint ownership;
- release telemetry or incident history;
- an allow-list for expected changes;
- regression/integration tests against the real binary.

Do not multiply these four values into one number until they are calibrated. Maintainer response B4 is correct: doing so would reintroduce product guesses into ranking under a different name and make an `unknown` value difficult to represent.

A better display is:

```text
severity: 75 / 80 ceiling
extraction confidence: low | medium | high
product relevance: unknown | referenced | confirmed-used
exposure: unknown | bounded | broad
```

The UI can sort using an explicit policy or filter on each axis while preserving the underlying evidence instead of treating ordinal labels as fake probabilities.

## 21. Acceptance criteria before calling it a release gate

A run should qualify as a release gate only when all of the following are true:

- Both refs resolve to commit SHAs, which are recorded in the artifact.
- Each local checkout HEAD matches its ref, unless the user explicitly confirms an override.
- Target, config, and extractor hashes are stored.
- There are no missing targets outside a documented allow-list.
- There are no silent parser errors.
- Coverage is 100% for extractor-relevant candidates within the declared scope, separately for each extractor.
- Unsupported syntax is counted and shown rather than silently producing zero facts.
- There are no unresolved references outside an allow-list.
- No conflicting UID is dropped; every variant is resolved or marked ambiguous.
- Windows platform projection has golden tests for `#if/#elif/#else`, line continuations, and platform paths.
- Mojo ordinals and WebIDL overloads have regression tests.
- Test/fuzzer facts do not enter the product report.
- The report schema is valid and the HTML handles untrusted strings safely.
- The test suite runs on Linux and Windows, and the test count is checked.
- An independent oracle exists for several Chromium milestones, rather than relying only on generated snapshots.
- High-ranked findings are connected to SB-AXon usage/dependencies or marked `product relevance unknown`.

If any condition is not met, a report may still be generated but should be labelled:

```text
INCOMPLETE — FOR MANUAL TRIAGE ONLY
```

## 22. How to use the project safely in its current state

If ChromeDrift must be used now:

1. Always provide a full version or commit SHA; avoid raw branches.
2. Use a fresh cache directory for each important audit instead of relying entirely on `--refresh`.
3. Run `wide`, but do not call it complete.
4. Inspect metadata for missing targets, extractor errors, raw/deduplicated counts, and unresolved references.
5. For every important Breaking/Behaviour finding, inspect the source in both versions.
6. Check the enclosing `#if`, GN target, and actual platform.
7. Check whether SB-AXon calls or uses the symbol.
8. For removals, search the full tree to distinguish deletion from a move outside the target.
9. For overloaded IDL methods, inspect every signature with that name.
10. For Mojo, check for method ordinals and version attributes; an ordinal change can still be omitted by the diff at this stage.
11. Inline `</script>` breakout has been fixed, but do not click spec links in an untrusted report until URL schemes are validated.
12. Save the exact command, commit SHAs, cache path, and artifact hash so the audit can be repeated.

Interpret a current report as follows:

```text
Breaking
→ review first; it does not mean that breakage is certain

Behaviour
→ behavior may change; verify usage and platform

New
→ the tool saw a new declaration; this does not prove the product can use it or that it is enabled by default

Housekeeping
→ lower priority or absence is unconfirmed; it does not mean the change is certainly harmless
```

## 23. Frequently asked questions

### “All 316 tests pass. Why is it still considered unsafe?”

Because the tests mostly prove that the code behaves according to its current rules. If the coverage or identity rule itself is wrong, tests can pass while the real-world conclusion remains wrong.

### “Wide contains more than 54,000 facts. Do a few hundred missing facts matter?”

They can. Importance does not depend on volume. One missed method contract can matter more than thousands of housekeeping constants.

### “If the target does not fetch a file, are all facts in that file lost?”

Yes. Extractors can read only files that were materialized and remain within target scope.

### “What if the file is fetched but the parser does not understand it?”

Facts can still be lost. Target coverage and parser coverage are different measures.

### “If a fact is marked removed, was it definitely deleted from the source?”

No. At least four explanations are possible:

1. the source genuinely removed it;
2. the declaration moved to a file outside the target;
3. the parser understood only one side;
4. dedupe selected a different variant.

### “Is a moved file reported as removed?”

Usually not if `kind:key` remains unchanged and the extractor reads the destination. It can appear removed if the destination is outside the target, the key changes, or parsing differs.

### “Does a higher score mean greater certainty?”

No. The score primarily represents heuristic severity, not extraction confidence or product relevance.

### “Does the Breaking bucket mean a crash is certain?”

No. It means the signal belongs to the highest-attention group. The reviewer must still determine whether the product uses the contract and whether the change applies to Windows.

### “Can I compare abbreviated milestones such as 148 and 151?”

Yes, but a milestone resolves to the stable patch available at run time. Record a full version or commit SHA for a reproducible audit.

### “Can I use a local Chromium checkout?”

Yes, but the tool currently does not prove that the checkout HEAD matches the ref label, and the cache may reuse an older snapshot. Use a new cache and record the SHA of both checkouts yourself.

### “Is the HTML report safe?”

It is safer than before: a `</script>` payload no longer escapes the inline JSON. At this historical point, however, a spec URL could still retain a `javascript:` scheme and run when clicked. An untrusted report could be opened for reading, but external/spec links should not be clicked until the renderer allows only `http:`/`https:`.

### “Does the tool know which APIs SB-AXon uses?”

No. Scoring is Chromium-centric, not product-specific.

### “Is the project worth keeping?”

Yes. The pipeline, Fact model, and reporting are a useful foundation. Treat it as a maturing static change inventory rather than discarding it. Completeness, variants, platform handling, and provenance need improvement before its role is expanded.

## 24. Conclusion at this audit stage

ChromeDrift answers this question reasonably well:

> “Among the source files I downloaded and the parser understood, which declarations appear to have changed?”

It does not yet answer this question with confidence:

> “Is upgrading Chromium from A to B safe for SB-AXon?”

The three main reasons are:

1. **Completeness is not proven:** `wide` reaches 99.1% file-scope coverage but still misses 73 candidates, has eligibility mismatches, and lacks parse/per-kind completeness.
2. **Semantics are not fully preserved:** Mojo ordinals are extracted but not compared; WebIDL overloads/variants and some syntax are lost.
3. **The core deliberately stops before the product verdict:** this is a reasonable boundary, but it means the release workflow requires a downstream step that checks whether SB-AXon uses the change.

After reading the entire commit history, the fairest description is:

> ChromeDrift has stronger engineering discipline and design rationale than a typical prototype. Precisely because the core is designed to stop at evidence, it is useful for manual review but cannot yet serve as a release gate on its own.

The practical decision at this stage was:

- Use ChromeDrift to build an inventory and prioritize manual review: **Yes**.
- Use `default` to conclude that a release is safe: **No**.
- Use the then-current `wide` mode as an automated release gate: **No**.
- Continue investing in the project: **Yes—the existing foundation is good enough to improve incrementally rather than rewrite from scratch**.

## 25. Source map for verification

Important locations referenced in this document:

- Target and coverage rules: [`chromedrift/targets.py`](../chromedrift/targets.py)
- Ref resolution and local materialization: [`chromedrift/acquire.py`](../chromedrift/acquire.py)
- Snapshots/cache: [`chromedrift/snapshot.py`](../chromedrift/snapshot.py)
- Extractor registry and error handling: [`chromedrift/extract/__init__.py`](../chromedrift/extract/__init__.py)
- Base-feature extraction: [`chromedrift/extract/base_features.py`](../chromedrift/extract/base_features.py)
- Mojo extraction: [`chromedrift/extract/mojom.py`](../chromedrift/extract/mojom.py)
- WebIDL extraction: [`chromedrift/extract/web_idl.py`](../chromedrift/extract/web_idl.py)
- Platform parsing: [`chromedrift/extract/_cpp.py`](../chromedrift/extract/_cpp.py)
- Constant classification: [`chromedrift/extract/constants.py`](../chromedrift/extract/constants.py)
- WebUI routes/gates: [`chromedrift/extract/webui_routes.py`](../chromedrift/extract/webui_routes.py), [`chromedrift/extract/webui_gates.py`](../chromedrift/extract/webui_gates.py)
- Fact dedupe: [`chromedrift/model.py`](../chromedrift/model.py)
- Diff and severity signals: [`chromedrift/diff.py`](../chromedrift/diff.py)
- Scoring and coverage adjustment: [`chromedrift/score.py`](../chromedrift/score.py)
- Clustering: [`chromedrift/cluster.py`](../chromedrift/cluster.py)
- Reference closure: [`chromedrift/catalog.py`](../chromedrift/catalog.py)
- HTML reporting: [`chromedrift/report/html.py`](../chromedrift/report/html.py)
- CLI and report loading: [`chromedrift/cli.py`](../chromedrift/cli.py)
- Test suite: [`tests/`](../tests/)

## 26. Follow-up review of commit `46dae58`

This section supersedes the preceding conclusion. It was written after:

- reading the complete commit messages and diffs for `a864787` and `46dae58`;
- rechecking the source at schema 29;
- running all 316 tests;
- recreating default and wide reports in memory from cached snapshots;
- scanning raw M148/M151 IDL facts before deduplication;
- running targeted probes for Mojo ordinals, HTML embedding/links, test filenames, and cache sanitization;
- comparing current `unittest` behavior with the official CPython 3.11/3.12 source.

### 26.1. Short conclusion

This commit is a good response to review feedback. Rather than merely adjusting numbers, it opened the M151 tree, measured each claim, bumped the schema, and added regression tests. The maintainer's main figures are reproducible.

One important claim, however, was still incorrect:

> Mojo `ordinal` was extracted, but **not compared**.

As a result, `Foo@0 → Foo@1` disappeared entirely from the report. This alone was enough to preserve the “not ready for use as an automated release gate” verdict: the defect concerns a process-boundary ABI, and the new test created the impression that behavior was locked down while covering only the first half of the pipeline.

Beyond that blocker, the coverage architecture improved substantially, but per-kind scope and shared eligibility remained incomplete. Real WebIDL-overload false negatives, test-service noise, unsafe spec links, and documentation-contract inconsistencies also remained.

### 26.2. Assessment of the nine listed changes

| Item | Follow-up conclusion | Short evidence |
|---|---|---|
| Coverage omitted `.mojom`/`.idl` | **Core denominator fixed; overall status partial** | The registry predicate is shared; `wide` reaches 8,276/8,349. Global skip policy remains duplicated and the scorer still uses one scalar. |
| Base-feature enclosing `#if` | **Fixed** | An Android-only fixture became `not_compiled`; default zero-score findings rose from 118 to 187. |
| Mojo `Foo@0(...)` | **Partial, with a remaining blocker** | 6,099 methods are extracted, but `ordinal` is absent from `MEANINGFUL_ATTRS`; `@0 → @1` produces zero changes. |
| `/mac/`, `/linux/` | **Fixed** | 79 M151 Mojo facts are stamped `not_compiled` for Windows. |
| WebIDL `margin-top` | **Parser bug fixed** | `margin-top` and `top` become separate UIDs. Another 121 overload collisions remain, so the broader identity issue is not fixed. |
| Test/fuzzer filenames | **Partial** | Three new fixtures are skipped; schema 29 still contains 22 facts from eight `*_test_service.mojom` files. |
| Inline `</script>` | **Fixed** | `<`, `>`, `&`, U+2028, and U+2029 are escaped; the payload no longer contains a literal closing script. Unsafe spec URL schemes are a separate residual issue. |
| Windows cache traversal | **Fixed on the main snapshot/tree paths** | `..\..\victim` is sanitized. The listing cache uses a second sanitizer that preserves exact `..`. |
| Proxy credentials | **Fixed** | User information is replaced with `<redacted>` while host/port remain available for debugging. |

Using the narrow bug described in each row, six items were fully fixed and three were partial. The “8/9” figure is understandable if it means “eight items received a code change,” but it should not mean that eight correctness contracts were closed.

### 26.3. Blocker 1 — Mojo ordinals exist in facts but are ignored by comparison

The pipeline has two separate gates:

```text
source → extractor creates a Fact → diff selects attributes to compare → signal/score/report
```

The new commit opened the first gate. In `mojom.py`:

```python
"ordinal": parsed["ordinal"]
```

The second gate in `diff.py` remained:

```python
KIND_MOJO_METHOD: ("signature", "params", "response", "attrs")
```

`ordinal` is absent. The signature, generated as `Foo(int32 x)`, does not contain `@0` either.

The probe produced:

```text
old attrs ordinal = 0
new attrs ordinal = 1
diff_snapshots(...) = []
```

This clearly illustrates why “tests prove internal consistency, not necessarily correctness.” A new test contained the comment:

```text
The ordinal is part of the wire contract, so it is compared
```

but its assertion checked only that the key existed in the fact. Both the comment and commit body said comparison worked, while the actual code path was never invoked by the test.

The required fix and test were:

```python
KIND_MOJO_METHOD: (
    "signature", "params", "response", "attrs", "ordinal"
)
```

Then construct old/new snapshots and assert that:

- exactly one `MODIFIED` change exists;
- the delta is `ordinal: ["0", "1"]`;
- the signal/severity describes a wire-contract change;
- HTML and Markdown explain the reason clearly.

### 26.4. Where the new coverage is better, and where it remained wrong

#### What was correct

The denominator was no longer limited to preferences and features. It queried all nine extractor predicates, bringing `.mojom`, `.idl`, JSON5, and WebUI templates into the measurement. The 43%/99% figures represented target scope far better than the old 5%/100% figures.

#### Policy was still duplicated

Coverage and extraction still had two global exclusion sets. Two opposing examples were:

```text
content/web_test/common/mojo_echo.mojom
coverage: candidate
extraction: skipped because of /web_test/
```

```text
cc/mojom/hit_test_opaqueness.mojom
coverage: excluded because the regex sees _test_
extraction: read, and facts exist in the snapshot
```

Saying “the predicate is the same object” was not enough to prove that the pipelines could not disagree, because each still wrapped the predicate in a different policy.

The design needed one shared function, for example:

```text
eligibility(path, extractor, platform)
→ candidate | intentional_skip(reason) | out_of_scope(reason)
```

Coverage and extraction should call the same function. A test should use a real M151 listing and verify both directions:

- every candidate reached by the target and present on disk is attempted by at least one extractor;
- every file actually read by an extractor appears in the denominator or has an explicit reason for being auxiliary evidence outside it.

#### Per-kind coverage remained necessary

The global `default = 43.9%` concealed very large differences:

```text
WebIDL       99.8%
WebUI gates 100.0%
Mojo         25.1%
base feature 12.1%
pref/switch   1.7%
```

The flat `-15` was not wrong: it was a policy step, not a probability. The error was using one scalar to decide whether the step should run. A WebIDL removal with almost 100% file-scope coverage should not receive the same “unconfirmed” state as a preference removal with 1.7% coverage.

Each coverage row needed at least:

```json
{
  "web_idl": {"candidates": 2165, "read": 2161},
  "mojom": {"candidates": 1462, "read": 367}
}
```

and `Scope.confirms_absence(kind)` instead of `Scope.confirms_absence()`.

### 26.5. WebIDL: accept the rebuttal without closing the wrong finding

Response B2 helped identify a real parser defect: `margin-top` was truncated to `top`, and fixing the earlier regex was correct. This review retracts wording that could imply every collision was an overload.

After the fix, raw M151 still contained 121 `idl_member` UIDs with multiple semantic variants. A scan across M148–M151 found 109 UIDs present on both sides whose overload sets changed. Dedupe completely hid two changes:

```text
Navigator.install
M151 adds install(InstallParams params)
selected overload install() is unchanged
→ current diff reports nothing
```

```text
Document.parseHTMLUnsafe
overload/options/gate set changes
selected one-argument overload is unchanged
→ current diff reports nothing
```

Both statements are therefore true:

- do not use signature identity to hide a parser bug;
- once parsing is correct, retain overload variants rather than dropping them deterministically.

Deterministic dedupe solves “two machines must produce the same result.” It does not solve “the retained result must preserve all semantics.”

### 26.6. Test/fuzzer filtering must avoid false positives and false negatives

The new regex reduced noise substantially, but the current snapshot still contained 22 facts from eight `_test_service.mojom` files. This is a false positive: a test-only interface can be assigned Mojo-level severity.

In the opposite direction, coverage's `_test_` regex was too broad and excluded real product concepts such as `hit_test`. Making the regex even broader would merely trade false positives for false negatives.

A better policy would combine:

- exact directory conventions;
- clear suffix conventions such as `_test`, `_unittest`, `_browsertest`, `_test_service`, and `_fuzzer`;
- explicit exceptions/fixtures for domain terms such as `hit_test`;
- BUILD target metadata, rather than filename alone, if greater precision is required.

### 26.7. Security follow-up

#### Inline JSON

Fixed. `_embed()` correctly handles the reported attack class.

#### Spec links

A click-triggered unsafe scheme remained:

```text
input spec = javascript:alert(1)
output href = javascript:alert(1)
```

HTML escaping protects attribute structure; it does not make the URL scheme safe. Allow only `http:`/`https:`, or render plain text.

Browser automation could not run during this audit because the browser runtime returned a metadata error before opening a tab. This residual-link conclusion therefore came from exact renderer output and browser URL semantics, not a completed browser end-to-end test.

#### Cache sanitizer

Traversal through the main `snapshot_path`/`tree_path` was fixed. The residual issue in `acquire._safe_name()` was smaller but worth removing so that two security policies did not share the same name.

#### Proxy

Fixed; targeted cases exposed neither user nor password.

### 26.8. Responses B1–B4, item by item

#### B1 — agree and correct the report

The maintainer was right: on current Python, zero discovered tests return exit code 5, not success. A local Python 3.14.6 run confirmed it. CPython 3.12 source also contains `_NO_TESTS_EXITCODE = 5`; CPython 3.11 does not.

The remaining point was that the default command still ran zero tests, while the README included Python 3.9 in the compatibility matrix. A `test_count > 0` guard remained useful so CI behavior would not depend on the standard-library version.

#### B2 — agree in part

The `margin-top` parser diagnosis and the decision to fix the parser first were correct. That did not remove the overload finding: 121 collisions and two real false negatives remained afterward.

#### B3 — agree with the flat-penalty rationale, not with closing per-kind coverage

Do not linearly scale score by file percentage. But the yes/no question “is this removal confirmed?” must use coverage for the corresponding kind. A logged candidate count is not per-kind coverage and was not yet stored in the snapshot or supplied to the scorer.

#### B4 — fully agree with the formula criticism

The earlier report proposed:

```text
severity × extraction_confidence × product_relevance × exposure
```

That proposal contradicted its own advice not to put product guesses back into core scoring. It also multiplied uncalibrated values as though they were ratio-scale quantities. The formula was removed from Section 20.

The revised direction was to keep severity, extraction confidence, product relevance, and exposure as separate columns or axes. Product relevance defaults to `unknown` and changes only when downstream SB-AXon evidence proves usage.

### 26.9. Which figures were confirmed?

From snapshots and an in-memory diff at `46dae58`:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28,487 → 29,118 | 3,027 | 282 | 468 | 1,240 | 1,037 | 187 |
| `wide` | 52,519 → 54,451 | 6,071 | 804 | 696 | 2,980 | 1,591 | 441 |

M151 coverage:

```text
default: 3,669 / 8,349, missing 4,680
wide:    8,276 / 8,349, missing 73
```

Tests:

```text
python3 -m unittest discover -s tests -q
Ran 316 tests
OK
```

The maintainer's bucket, fact, and coverage figures matched this independent measurement.

### 26.10. Documentation remained self-contradictory despite green tests

Commit `a864787` added tests for several headline sentences, but the matcher covered only three specific patterns. All 316 tests therefore passed while the following active passages contradicted the new table:

- The README contained a `default 43% / wide 99%` table, followed by passages saying “5%” and then “4%.”
- README score examples and the comparison table still said `default 5% / wide 100%`.
- `docs/pipeline.html` retained several 5%/100% labels.
- `reference/signals.md` still said default 5%.
- A `score.py` comment still said “a twentieth.”
- CLI help for `--target-set` still said wide “reads everything an extractor understands. Use it for a release gate.”
- CLI partition help still advised using the full set for a release gate.
- The same M148→M151 story in the README said `226 of 282 Breaking`, while another sentence still said “two of the 315 Breaking rows” and the old bucket table remained 239/492/1,148/921.

This did not make the extractor wrong, but it made the user contract wrong. The maintainer correctly said the target table no longer used the words “release gate”; the promise still appeared in the CLI, which users read immediately before running the tool.

Documentation tests should check stable semantic facts rather than a few literal sentences. For example, generate a canonical data block and render README/pipeline examples from it, or parse every active coverage/bucket table and fail if more than one current value exists.

### 26.11. Release-gate verdict after this commit

The verdict remained **not ready**, but for narrower and more concrete reasons than in the initial review:

1. A reproducible false negative existed for Mojo ordinal changes.
2. Two real WebIDL-overload false negatives existed between M148 and M151.
3. Removal confidence used global coverage instead of kind-specific coverage and did not integrate parsing/missing-target completeness.
4. Test/fuzzer eligibility still disagreed across stages, and test-service facts remained.
5. The CLI still promised a release gate while `wide` missed 73 candidates and the completeness layers above remained open.

Base-platform handling, Mac/Linux paths, inline JSON, main cache traversal, and proxy leakage were no longer blockers after this commit.

### 26.12. Shortest fix sequence from this point

1. Add Mojo method `ordinal` to comparison and a regression test at the diff/report layer.
2. Retain WebIDL overload variant sets; test the `Navigator.install` and `Document.parseHTMLUnsafe` false negatives.
3. Create one shared eligibility policy for discovery and extraction; add `_test_service` while retaining `hit_test`.
4. Store per-extractor coverage and call `confirms_absence(kind)`.
5. When targets are missing or extraction fails, do not confirm removals from scope coverage alone.
6. Validate the `spec` URL scheme and unify cache sanitizers.
7. Remove the remaining release-gate wording and correct every active 4–5%/100% example.
8. Add a test-count guard or package discovery so bare `unittest discover` actually runs tests.

After steps 1–5, rerun the real-version matrix for at least M143/M147/M148/M151 and compare the raw grammar inventory with deduplicated snapshots. Only then should release-gate readiness be reassessed; passing all regression tests is not sufficient by itself.

## 27. Follow-up review of commit `8ced148` — schema 30

### 27.1. Conclusion first

This commit was genuine progress. The maintainer acknowledged the defect introduced in the previous commit and fixed it directly. The new explicit-Mojo-ordinal regression test crosses all three layers—`extract → diff → score`. Bare `unittest discover` was also fixed correctly, including on Python 3.9, the project's stated minimum version.

The statement that “all three partial items are now closed” was still premature. The independent review found:

| Area | New review result | Status |
|---|---|---|
| `Foo@0 → Foo@1` | Produces an `ordinal` delta, signal `ipc_ordinal_changed`, score 80, and Breaking | **Fixed** |
| Mojo ordinals in general | Implicit ordinals derived from position are still neither stored nor compared | **Partial** |
| Shared eligibility | Test/vendor/product filtering is unified; platform policy intentionally differs, and 17 test-only facts still pass | **Partial** |
| Per-surface removal confidence | The scorer queries the correct surface; two surface denominators miss membership because each path retains only its first surface | **Partial** |
| Per-surface coverage display | Present in snapshot/report JSON, but absent from normal CLI, Markdown, and HTML output | **The claim that it is “printed” is inaccurate** |
| `javascript:` in spec | Non-HTTP(S) values render as text, not links | **Fixed** |
| Second cache sanitizer | Unified into `acquire.safe_name`; the old traversal is blocked | **Fixed**, with portability/collision edge cases remaining |
| Bare `unittest discover` | Runs all 327 tests on Python 3.14 and 3.9 | **Fixed** |
| “Docs tests scan every labelled number in every document” | Tests recognize only three sentence forms and four bucket labels; many active values remain stale | **Not fixed** |
| WebIDL overload | Acknowledged by the maintainer but not fixed | **Open** |
| Missing target/parse error affects absence confidence | Acknowledged by the maintainer but not fixed | **Open** |

The release-gate verdict remained **not ready**. Explicit ordinals were closed, but process-boundary comparison still had two reproducible false-negative classes: **implicit ordinals** and **enclosing build guards**.

### 27.2. What was rechecked?

At the start of measurement, the baseline was exactly:

```text
HEAD             8ced148
main             8ced148
origin/main      8ced148
source tree      clean
schema           30
commit history   67 commits
```

While this audit file was being completed, another process in the same workspace created WebIDL-overload and absence-completeness changes and committed/pushed them as `b844108`. I did not create, edit, or push that commit. Those changes appeared after measurement was complete, so Section 27 reviews the requested `8ced148` baseline; items marked Open below are not an assessment of their implementation in `b844108`.

Both test-discovery forms ran real tests:

```text
python3 -m unittest discover -q
Ran 327 tests
OK

python3 -m unittest discover -s tests -q
Ran 327 tests
OK
```

Bare discovery was also run with `/usr/bin/python3` 3.9.6 and still returned 327 tests with exit code 0. The `tests/__init__.py` fix therefore worked both on Python 3.14.6 and on the README's Python 3.9 lower bound.

Recomputing M148 → M151 from schema-30 cached snapshots, with `target_milestone` supplied as in the real CLI path, produced:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28,507 → 29,138 | 3,027 | 282 | 468 | 1,240 | 1,037 | 187 |
| `wide` | 52,367 → 54,298 | 6,069 | 804 | 695 | 2,979 | 1,591 | 441 |

M151 coverage:

```text
default: 3,677 / 8,366, missing 4,689
wide:    8,295 / 8,366, missing 71
```

The maintainer's figures were correct. One detail matters: there was no real explicit-ordinal delta in M148 → M151. M151 `default` had no method fact with an `ordinal`; `wide` had 196, but no common `@N` method changed from one number to another. The new signal was therefore proven by a synthetic contract test, not by a bucket-count change in the real report.

Per-surface scoring also behaved as described:

- 77 WebIDL removals no longer received the `-15 unconfirmed` line.
- 45 removals remained at score 70; 32 remained at score 30 because of build/platform evidence, not coverage.
- `default` contained 139 `pref_left_scan` and one `switch_left_scan`; because that surface was barely read, confidence was still reduced.
- `wide` did not apply the unconfirmed penalty to those pref/switch removals.

### 27.3. Explicit ordinals were fixed correctly

The previous test asked only:

> “Does the Fact contain an `ordinal` key?”

That checked extraction alone. The new test covered the complete chain:

```text
old mojom: Foo@0(int32 a)
new mojom: Foo@1(int32 a)
        ↓
diff_snapshots
        ↓
deltas = {"ordinal": ["0", "1"]}
signal = ipc_ordinal_changed
score  = 80
bucket = Breaking
```

This is the right kind of regression test: if the parser continues to extract the value but `MEANINGFUL_ATTRS` later drops `ordinal`, the test fails. The comment and assertion now prove the same claim.

A dedicated signal is also clearer than folding this into `ipc_signature_change`: the textual signature may remain unchanged while the wire-routing number changes. The report label explains the consequence directly.

### 27.4. New blocker: explicit ordinals are not the whole ordinal model

#### Minimal example

Mojom allows `@N` to be omitted:

```mojom
// Old version
interface I {
  Foo();  // implicit ordinal 0
  Bar();  // implicit ordinal 1
};

// New version
interface I {
  Bar();  // implicit ordinal 0
  Foo();  // implicit ordinal 1
};
```

Both methods retain the same name, parameters, and response, and neither Fact has an `ordinal` field. A probe against the current code returned:

```text
implicit method reorder changes: []
```

In plain terms, the new commit checks seat numbers when they are printed on the ticket. When the theater numbers seats from their order in the row, ChromeDrift does not store that order, so swapping two seats appears to be no change.

This was not an assumption unique to the review. Official Mojom documentation says implicit ordinals are assigned by lexical position and explicit ordinals must be used consistently in a declaration; see [Mojom IDL documentation](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/README.md).

Methods also have a build-time layer:

- the bindings generator walks methods in order and uses the index for methods without explicit ordinals; see the [Mojom bindings generator](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom_bindings_generator.py);
- desktop Chromium normally scrambles message IDs using `chrome/VERSION`, and an individual GN target can disable it with `scramble_message_ids`; see [mojom.gni](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom.gni).

The actual wire ID may therefore depend on:

```text
explicit @N, when present
or lexical position, when absent
+ generator salt/version
+ GN target configuration
```

ChromeDrift saw only the first line.

#### Measurement on real M148 → M151 data

Positions were reconstructed from `path + line`, considering only facts present in both versions without an explicit `ordinal`:

| Kind | Existing fact whose implicit position changed | Affected containers | No diff row for that fact | Row exists, but for another attribute |
|---|---:|---:|---:|---:|
| Mojo method | 503 | 48 interfaces | 485 | 18 |
| Mojo field | 607 | 72 structs/unions | 602 | 5 |

This table must not be read as “there are certainly 1,110 breaking changes.” Risk depends on:

- whether a declaration has `[Stable]`;
- whether the peers are built and deployed together or can have version skew;
- whether the GN target scrambles message IDs;
- whether the change is a safe append or an insertion/reorder before an existing member;
- whether the interface crosses a boundary relevant to the product.

The table does prove one narrow point: **the comparison model could not detect or explain this class of change**. No finding did not mean safe.

#### Appropriate fix

The parser should store at least:

```text
ordinal_source: explicit | implicit
declared_ordinal: N | null
lexical_index: N
```

Comparison should then distinguish:

1. An explicit `@N` changes: retain the current strong signal.
2. An existing implicit member changes `lexical_index`: emit a separate signal warning that compatibility depends on build configuration and version skew.
3. A new member is appended at the end: do not assign the same severity as reordering or inserting before an existing member.

To call this a wire-compatible release gate, the tool would also need to read or receive GN policy and preserve `[Stable]` evidence. Without that data, the report should say “implicit wire order changed; compatibility depends on generated binding policy,” rather than assigning every case a confidently interpreted score of 80.

### 27.5. Second new blocker: enclosing Mojo guards are extracted but not compared

Probe:

```mojom
// old
[EnableIf=is_android]
interface I { Foo(); };

// new
[EnableIf=is_win]
interface I { Foo(); };
```

The facts show that extraction did its job:

```text
old Foo: conditions=[EnableIf=is_android], windows=not_compiled
new Foo: conditions=[EnableIf=is_win],     windows=compiled
```

The diff nevertheless returned:

```text
enclosing guard changes: []
```

The cause closely resembled the ordinal defect:

| Kind | Does the extractor store the guard? | Does `MEANINGFUL_ATTRS` compare it? |
|---|---|---|
| `mojo_interface` | Yes: `conditions`, `platform_state` | No; empty tuple |
| `mojo_method` | Yes: inherited `conditions`, `platform_state` | No; only signature/params/response/attrs/ordinal |
| `mojo_struct` | Yes | No; only `mojo_kind` |
| `mojo_field` | Yes | No; only type/ordinal/default/attrs |
| `mojo_enum` | Yes | No; only values |

M151 `wide` had many facts with enclosing conditions:

| Kind | With `conditions` | Total facts |
|---|---:|---:|
| Interface | 28 | 1,479 |
| Method | 288 | 6,012 |
| Struct/union | 53 | 2,867 |
| Field | 314 | 13,015 |
| Enum | 24 | 1,477 |

For the current M148 → M151 pair, no additional pure enclosing-guard transition was found that would alter bucket counts: observed rows with condition/platform deltas also had a direct attribute or signature delta. This was therefore a **contract false negative reproduced with a fixture**, not a claim that exactly N real rows were missing.

A fix should avoid producing hundreds of duplicate rows. When an interface guard changes, every child method's effective platform state changes. A cleaner model stores:

```text
own_conditions
inherited_conditions
effective_platform_state
```

Then:

- an interface/struct guard change emits one container-level finding;
- a direct method/field guard change emits a member-level finding;
- children carry inherited evidence for explanation without duplicating the same finding;
- comparison uses effective state for the reviewed platform, with raw condition text as supporting evidence.

### 27.6. Per-surface scoring moved in the right direction, but the denominator was not truly per-surface

The scorer's central logic was fixed correctly:

```text
removal kind
    ↓ KIND_SURFACE
surface coverage row
    ↓
>= 95%  → absence confirmed; no 15-point deduction
<  95%  → deduct 15; some pref/switch inferred removals move to Housekeeping
```

The defect occurred earlier while rows were built. `discover_candidates()` returned `Dict[path, note]` and used:

```python
found.setdefault(path, rule.note)
```

A file can be read by feature, pref, and WebUI-gate extractors, but `setdefault` preserves only the first matching extractor note. The file then disappears from the other surface denominators.

The M151 listing contained **378 paths matching more than one surface**:

| Overlap | Files |
|---|---:|
| feature flags + chrome:// visibility gates | 194 |
| feature flags + preference keys and switches | 181 |
| preference keys and switches + visibility gates | 3 |

Comparing stored rows with independent per-extractor membership counts:

| Surface | Stored `default` row | Membership-based `default` | Stored `wide` row | Membership-based `wide` |
|---|---:|---:|---:|---:|
| Preference keys and switches | 4 / 348 = 1.1% | 9 / 529 = 1.7% | 345 / 348 = 99.1% | 526 / 529 = 99.4% |
| Visibility gates | 340 / 340 = 100% | 537 / 537 = 100% | 340 / 340 = 100% | 537 / 537 = 100% |

Feature flags appeared first, so they retained overlapping files; their row remained 363 / 3,011 for `default` and 2,971 / 3,011 for `wide`.

This did not yet change `confirms_absence` decisions:

- `default` pref coverage was below 95% either way;
- `wide` pref coverage was above 95% either way;
- visibility gates remained at 100%.

Scores for this pair therefore still matched the selected threshold. But the “preference keys and switches coverage” label described the wrong population, and a surface near 95% could change outcome merely because of registry order.

The fix was:

```text
path -> set(surface)
```

Global coverage should continue to deduplicate paths to 8,295 / 8,366. For individual surfaces, a path must count toward every surface whose extractor can read it. Surface candidate totals may exceed the global total because the overlap is real, not a double-counting bug.

In addition, `_EXTRACTOR_NOTES` in `targets.py` and `KIND_SURFACE` in `score.py` were mappings that had to be updated manually in tandem. A new unmapped kind silently fell back to global coverage. A better registry declares once:

```text
extractor name
candidate surface
fact kinds produced
```

and an invariant test requires every fact kind to have an explicit surface instead of treating global fallback as valid behavior.

### 27.7. “Per-surface coverage is now printed” was not true for normal output

What existed:

- `snapshot.meta.coverage.by_surface` contained the data;
- report JSON preserved it at `meta.coverage.from/to.by_surface`;
- `Scope` used the corresponding row to score removals.

What did not exist:

- snapshot logs printed only overall `read / candidates`;
- Markdown reports printed only overall coverage and the three largest directory gaps;
- HTML contained no surface-coverage table;
- across the source, `by_surface` appeared only in targets, scoring, and tests—not renderers.

The maintainer's table could be derived from JSON, but ordinary users did not see it after running the command. The accurate claim was:

> “Per-surface coverage is stored and used for scoring; the UI/report table does not expose it yet.”

Generated `out/report.md` also retained this overclaim:

```text
Run --target-set wide to read every file an extractor understands.
```

The same run showed `wide` at 8,295 / 8,366 with 71 files missing. Better wording was: “use the widest built-in target set; the report will still identify remaining gaps.”

### 27.8. Shared eligibility improved, but its boundary needed accurate wording

`eligibility.py` correctly addressed the previously reported two-way defect:

- exact directory components exclude `web_test/`;
- suffix-before-extension rules exclude `_test_service.mojom`;
- `hit_test_opaqueness.mojom` is no longer caught by a substring `_test_` match;
- discovery and extraction share one test/vendor/product filter.

The pipelines still intentionally differed on platform directories:

- discovery excluded Android/Ash/iOS/Mac/Linux from the denominator for a Windows run;
- extraction still allowed the `constants` extractor to read those files to find prefs/switches moved to another platform.

The full cached M151 listing contained 68 such files readable by `constants`:

```text
default reaches 1 / 68
wide reaches   64 / 68
```

The four remaining files were under `fuchsia_web/`. These files were absent from the per-surface denominator even though facts from 64 of them could prevent a false conclusion that a preference had been deleted. This can be a correct design: they are **auxiliary cross-platform evidence**, not Windows product candidates. The contract needed to say so; “both pipelines have one eligibility policy” overstated the code.

Filename-based eligibility also did not eliminate all test-only source. M151 `wide` retained 17 Mojo facts from four clearly test-oriented files:

| File | Facts | Evidence in name/comment |
|---|---:|---|
| `components/autofill/core/common/mojom/test_autofill_types.mojom` | 9 | Interface `TypeTraitsTest` |
| `components/heap_profiling/in_process/mojom/test_connector.mojom` | 4 | Comment says it is used for a multiprocess test |
| `services/audio/public/mojom/testing_api.mojom` | 2 | Comment says it is exposed only in the testing environment |
| `services/video_capture/public/mojom/testing_controls.mojom` | 2 | Comment says it is for integration testing |

A generic rule excluding every filename beginning with `test_` across every extractor would be unsafe: valid WebIDL names can contain `test_`, turning false positives into false negatives. Safer options were:

1. Language/extractor-specific conventions.
2. When a full Chromium checkout is available, inspect `BUILD.gn` for `testonly = true` or target reachability.
3. Allow explicit include/exclude overrides and show the reason in the catalog.

Those four files produced no findings in M148 → M151, so they did not alter current bucket counts; they demonstrated that the eligibility contract still had a gap.

### 27.9. Documentation tests again proved less than their comments claimed

The commit message said:

> “The figures test now scans every labelled number in every document.”

The code did not. `TestTheDocumentedM148FiguresAreStillTrue` checked:

- three specific sentence regexes;
- four bucket labels: Breaking, Behaviour change, New surface, and Housekeeping;
- one invariant that the retired-flag total equals 132.

It did not check every labelled number, did not understand schema/test/fact/coverage counts, and its label regex depended on a few Markdown layouts where the label immediately preceded the number. Different HTML markup could evade it.

More importantly, the test called `skipTest` if `out/report.json` did not exist or did not match the pair/target. Since `out/` was in `.gitignore`, a fresh checkout did not automatically have this oracle unless CI generated a report first. The docs guard was an optional local check, not a self-contained CI contract.

All 327 tests passed while active documentation retained stale values:

| Location | Documented | Schema-30 measurement |
|---|---:|---:|
| README default coverage | 3,669 / 8,349 | 3,677 / 8,366 |
| README wide coverage | 8,276 / 8,349 | 8,295 / 8,366 |
| README default facts | 29,118 | 29,138 |
| `docs/pipeline.html` default facts | 29,118 | 29,138 |
| `docs/pipeline.html` coverage | 3,669 / 8,349 and 8,276 / 8,349 | 3,677 / 8,366 and 8,295 / 8,366 |
| Skill coverage example | 3,669 / 8,349 | 3,677 / 8,366 |

The README still said “5% sounds terrible” immediately after a table showing 43%. Its scoring table still used `default 5% / wide 100%` for `pref_left_scan`; the new semantics should have used pref/switch-surface coverage, roughly 1% / 99%, not global coverage. `docs/pipeline.html` still illustrated a deduction with a global 44% widget after the scorer had moved to per-surface coverage.

The durable solution was not a fifth regex. It was a canonical machine-readable measurement fixture, followed by one of these approaches:

- generate README/pipeline/skill tables from the fixture;
- or parse every code block/table marked explicitly, for example `data-audit-figure="m148-m151"`;
- require CI to build or fetch the fixture rather than silently skipping;
- fail if current-value blocks exist outside the canonical renderer.

Historical values can remain when clearly labelled with their commit/schema. What must be prevented is two different values both claiming to describe the current state.

### 27.10. Mojo attributes were not rich enough for correct semantics

The parser divided attributes too coarsely:

- on interfaces, structs, and enums, `_conditions()` kept only `EnableIf*`; other attributes were dropped;
- on methods, all direct attributes were kept in one `attrs` dictionary;
- any pure method-level `attrs` delta was labelled `build_gate_changed`.

Mojom attributes do not all mean the same thing:

| Group | Examples | Approximate meaning |
|---|---|---|
| Build availability | `EnableIf`, `EnableIfNot` | Whether the declaration is compiled |
| Wire/versioning | `Stable`, `Extensible`, `MinVersion` | Version-skew and compatibility contract |
| Sandbox/context | `AllowedContext`, `RequireContext`, `ServiceSandbox` | Which context may bind/call the service |
| Call behavior | `Sync` and other attributes | How the call/binding behaves |

Across the 8,295 candidate files actually fetched by `wide` for M151, scanning attribute blocks after masking comments found, for example:

```text
Stable          215 occurrences / 58 files
Extensible      149 occurrences / 33 files
AllowedContext   18 occurrences / 9 files
RequireContext   20 occurrences / 16 files
```

Mojom documentation uses `[Stable]` to identify types/interfaces suitable for independently updated, version-skewed binaries. That evidence is highly relevant when deciding which implicit-ordinal changes deserve stronger warnings, yet ChromeDrift discarded it at the container level.

One real M148 → M151 finding was misclassified:

```text
network.mojom.NetworkContext.CreateNetLogExporter
attrs: {} → {AllowedContext=sandbox.mojom.Context.kBrowser}
```

The tool reported:

```text
signal: build_gate_changed
score: 35
reason: declaration may no longer be in the binary we ship
```

This is a context/sandbox restriction, not a Windows build condition. It may still warrant review, but the explanation describes the wrong mechanism.

Attributes should be parsed into typed fields such as `build_conditions`, `stability`, `min_version`, and `sandbox_context`, then mapped to signals by semantic group. All `attrs` deltas should not share one `elif` branch.

### 27.11. Security: URL handling was good; old traversal was closed, with sanitizer edge cases remaining

#### Spec URLs

The real HTML renderer output was tested with:

```text
javascript:alert(1)
data:text/html,...
https://example.test/spec
```

Parsing the DOM with `html.parser` showed:

- the first two schemes appeared as visible text without an `<a>` element;
- only HTTPS produced an anchor;
- a payload containing `<script>` was escaped and did not become an element.

The scheme allow-list therefore worked in renderer output, not merely in a helper predicate. This was not called a browser end-to-end test because the review environment's browser connector failed before opening the page due to missing `sandboxPolicy` metadata; that was an environment limitation, not a project defect.

#### Cache names

Removing the second `_safe_name` and using one allow-list closed the previously reported `..\..\` Windows path. The helper still had three edge cases:

```text
safe_name(".")   -> "."
safe_name("a/b") -> "a_b"
safe_name("a:b") -> "a_b"
safe_name("a\b") -> "a_b"
safe_name("CON") -> "CON"
```

Consequences:

- the filesystem normalizes `trees/.` to the `trees/` container itself rather than a distinct child;
- several different refs collide into one cache key;
- `CON`, `NUL`, `COM1`, and names ending with a dot are reserved or problematic on Windows.

This was no longer a traversal blocker, but it remained a reliability and cache-isolation issue. A simple design is a readable slug plus a short hash of the raw value, while rejecting `.` and Windows reserved basenames.

### 27.12. Two blockers acknowledged by the maintainer remained unchanged

#### WebIDL overload/variant identity

Fixing `margin-top` was correct but did not address overloads. The raw M151 inventory still contained 121 colliding UIDs and the pair had two real false negatives:

- `Navigator.install`
- `Document.parseHTMLUnsafe`

Putting the signature directly into the UID would not finish the work: it could turn a signature change into remove + add and hide parser collisions. The model needs a variant set under a stable declaration identity, followed by multiset/signature-set comparison.

#### Parse/missing-target completeness

`coverage >= 95%` said only that most candidate filenames had been fetched. It did not cover:

- a requested target failing to fetch;
- an extractor exception;
- an encountered declaration the parser did not understand;
- dedupe collapsing two variants;
- a read file unexpectedly producing zero facts.

`meta.missing_targets` and `extract_stats._errors` did not yet make `confirms_absence(kind)` fail closed. A removal could therefore be confirmed from high file coverage even when an important file was missing or failed to parse.

Confidence needs multiple evidence columns rather than one percentage:

```text
file_scope_complete
fetch_complete
parse_complete_for_kind
identity_collision_free
comparison_attribute_complete
```

Only when the required columns pass should the report use the words “confirmed removal.”

### 27.13. Current scoring mechanism, in brief

The real path of a finding was:

```text
Old Fact + new Fact
        ↓ matched by kind:key
Meaningful attribute delta
        ↓ signal
Leading signal selects severity ceiling and bucket
        ↓ policy deductions
not compiled → score 0
unconfirmed removal → -15; some signals move to Housekeeping
        ↓
final score 0..100 + reason lines
```

Strengths:

- the `leading signal` keeps explanation and severity aligned;
- scores only decrease from an evidence ceiling rather than adding product guesses;
- out-of-build facts fall to zero;
- per-surface absence is clearly better than one global scalar.

Still open:

- signals are only as complete as `MEANINGFUL_ATTRS`; implicit ordinals and enclosing guards did not pass that gate;
- generic Mojo `attrs` produced semantically wrong signals;
- coverage rows were biased by first match;
- fetch/parse errors did not reduce confidence;
- a score of 80 was still a heuristic priority, not an “80% chance of breakage.”

Keeping severity and confidence as separate columns remained the right direction. They should not be multiplied by product relevance; the core should leave product relevance `unknown` until downstream SB-AXon evidence fills it in.

### 27.14. Release-gate verdict and revised fix order

#### P0 — correctness before adding new surfaces

1. Model implicit ordinals for methods and fields; retain explicit/implicit provenance, lexical index, and `[Stable]` evidence.
2. Compare Mojo effective platform state while separating own and inherited guards to prevent duplicate findings.
3. Fix WebIDL variant identity and lock the two real false negatives with end-to-end tests.
4. Make missing targets, fetch errors, extractor errors, and parser anomalies fail absence confidence closed per kind.

#### P1 — make coverage and eligibility match their names

5. Change the candidate map to `path -> set(surface)` while keeping the global total unique.
6. Put extractor → fact kinds → coverage surface in one registry with invariant tests.
7. Expose the per-surface table in CLI, Markdown, and HTML; remove “wide reads every file.”
8. Document auxiliary cross-platform evidence; add extractor-specific test-only policy or BUILD ownership.

#### P1 — keep documentation and tests honest

9. Replace the optional regex-based docs test with a canonical generated measurement fixture used in CI.
10. Correct every active 3,669/8,349, 8,276/8,349, 29,118, 5%/100%, and global-44% scoring example.

#### P2 — hardening

11. Classify Mojo attributes by semantics instead of generic `attrs`.
12. Make cache keys collision-resistant and Windows-safe.
13. Add browser-level security tests when CI has a browser runtime, while retaining DOM-level regression tests.

### 27.15. Final verdict after `8ced148`

The maintainer was correct on four important points:

- the explicit-ordinal bug was acknowledged and fixed correctly;
- per-surface scoring was the right direction and corrected 45 Web API removals;
- bare discovery now actually ran the tests;
- URL schemes and the duplicate-sanitizer issue were handled seriously.

The new review also found the exact pattern the commit sought to eliminate:

> Comments made broader claims than the assertions and actual data model supported.

Three examples:

1. “Compare ordinal” covered explicit `@N`, not implicit position.
2. “One eligibility policy” excluded platform/auxiliary policy and still admitted other test-only naming forms.
3. “Scan every labelled number in every document” meant three sentence regexes plus four bucket labels and could skip entirely when `out/report.json` was absent.

The fairest assessment was:

> **Commit `8ced148` correctly closed explicit ordinals, bare discovery, and spec-link security, and it fixed the scoring decision for per-surface coverage. It did not close process-boundary comparison completeness, coverage-membership completeness, the documentation-correctness contract, or release-gate readiness.**

The project remained worth continuing. The maintainer's greatest strength was willingness to measure, record rationale, and retract inaccurate claims. The next step should apply the same discipline to implicit ordinals and enclosing guards: use a small fixture to prove the mechanism, measure real versions to establish scale, and only then choose the signal and score.

## 28. Follow-up review of commit `b844108` — schema 31

### 28.1. Short conclusion

Both changes in this commit were valuable, but they closed different amounts of work:

| Claim | Independent review result | Status |
|---|---|---|
| The two specific WebIDL false negatives now appear | Correct: `Document.parseHTMLUnsafe` is 60/Breaking; `Navigator.install` is 25/New | **Fixed for those two cases** |
| Facts retain the “whole overload set” | Signature sets are retained; per-overload attributes, runtime gates, paths, and lines are not | **Partial** |
| Signals are separated correctly by direction | Only when the representative signature is unchanged; removing the first and last overload produces different scores | **Partial / order-dependent** |
| Adding an overload cannot break an old call site | Not generally true under WebIDL overload resolution | **Rationale is too strong** |
| Missing targets/parse errors prevent confirmed absence | Correct for whole-fact `REMOVED` changes when the new snapshot is incomplete | **Narrow fix** |
| Every absence-shaped change is guarded | Overload removal is `MODIFIED` and bypasses the guard; a hole in the old snapshot still creates a false addition | **Not fixed** |
| The fix changes the current report | Overloads add two findings; the completeness latch changes nothing because all current error counts are zero | **Correct** |
| 335 tests | All run on Python 3.14 and 3.9 | **Verified** |

The release-gate verdict remained **not ready**. The commit closed two known WebIDL false negatives but not the broader overload contract. The missing-target latch was a good safety improvement, but covered only one direction and one change type.

### 28.2. Verified figures

Baseline:

```text
HEAD             b844108
origin/main      b844108
schema           31
commit history   68 commits
```

Tests:

```text
python3 -m unittest discover -q
Ran 335 tests
OK

python3 -m unittest discover -s tests -q
Ran 335 tests
OK

/usr/bin/python3 -m unittest discover -q   # Python 3.9.6
Ran 335 tests
OK
```

Schema-31 snapshots and real reports:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28,507 → 29,138 | 3,029 | 283 | 468 | 1,241 | 1,037 | 187 |
| `wide` | 52,367 → 54,298 | 6,071 | 805 | 695 | 2,980 | 1,591 | 441 |

The cached M143, M147, M148, and M151 snapshots all had `missing_targets = 0` and `extract_stats._errors = 0` for the measured targets. The maintainer was therefore correct that the latch did not change current scores.

After eligibility filtering, WebIDL counts were:

```text
M148: 122 members with more than one signature
M151: 121 members with more than one signature
```

Comparing full signature sets for members present on both sides found 56 changed sets. In 54, the representative `signature` had already changed and the old code already produced a row; the two whose representative remained unchanged were the known false negatives. This is more precise than wording that might imply “56 of the 121 overload groups changed.”

After schema 31, the real diff had four rows with a `signatures` delta:

- two still received `web_api_signature_change` because the representative also changed;
- one `web_api_overload_removed`: `Document.parseHTMLUnsafe`;
- one `web_api_overload_added`: `Navigator.install`.

### 28.3. What the WebIDL change fixed correctly

Keeping one stable member identity with an internal variant set is better than adding the signature to the UID:

```text
idl_member:Navigator.install
    signatures:
      - install()
      - install(USVString)
      - install(InstallParams)
```

Advantages:

- a new signature does not become a completely new member;
- losing one overload does not look like deleting the whole member;
- partial declarations across multiple files can still aggregate under one member;
- fact counts do not explode;
- bumping the schema to 31 was correct because serialized Facts changed.

The two new regression tests crossed extraction, dedupe, diff, and scoring, making them stronger than tests that inspect only a Fact key. The two real rows also appeared correctly:

```text
Document.parseHTMLUnsafe  web_api_overload_removed  60  Breaking
Navigator.install        web_api_overload_added    25  New surface
```

In short, **the two previous false negatives were genuinely closed**. The findings below concern the broader contract and do not negate that result.

### 28.4. Most important new defect: score depended on whether the removed overload came first or last

The code checked conditions in this order:

```python
if "signature" in change.deltas:
    web_api_signature_change
elif "signatures" in change.deltas:
    web_api_overload_removed / added
```

`signature` was the declaration with the smallest `(path, line)`. Removing the first overload changed the representative and triggered the generic branch. Removing the last left the representative unchanged and triggered the overload branch.

A probe with identical semantics showed:

| Case | Old | New | Signal | Score |
|---|---|---|---|---:|
| Remove first overload | `f(long); f(DOMString)` | `f(DOMString)` | `web_api_signature_change` | 50 |
| Remove last overload | `f(long); f(DOMString)` | `f(long)` | `web_api_overload_removed` | 60 |

Both cases remove exactly one argument list. Source position should not determine severity or wording.

Real M148 → M151 data already had two rows of the same shape that remained on the generic score-50 signal:

- `GPUQueue.copyElementImageToTexture`: three old overloads replaced by one new form;
- `WebGLRenderingContextBase.texElementImage2D`: four old overloads replaced by one new form.

Both had `signature` and `signatures` deltas, but the dedicated removal signal never ran because it was in an `elif`. The implementation therefore did not truly separate all overload changes by direction; it did so only when the representative happened not to change.

A concise fix was:

```text
if signatures delta:
    if old - new is non-empty: append overload_removed
    if new - old is non-empty: append overload_added

if there is only a signature delta and no variant-set delta:
    append web_api_signature_change
```

When variants are both removed and added, preserve both signals. `leading_signal` can select removal 60 as the headline while addition 25 remains as evidence. A permutation test should prove that changing declaration order does not alter signal or score.

### 28.5. `signatures: [string]` was not a complete variant set

An overload includes more than its signature. It also has its own extended attributes, runtime gate, declaration path, and line.

Measurement over the eligible raw M151 population:

| Among 121 overload groups | Groups |
|---|---:|
| Overloads with different `ext` | 42 |
| Overloads with different `runtime_enabled` | 12 |
| Overloads spread across multiple files | 1 |

The surviving Fact retained:

```text
signatures = all signature strings
ext/runtime_enabled/path/line = only those of the earliest representative
```

This created three problems.

#### 1. An overload's gate was lost

In M148, `Document.parseHTMLUnsafe` had:

```text
line 88  parseHTMLUnsafe(html)
         runtime gate: none

line 92  parseHTMLUnsafe(html, SetHTMLUnsafeOptions)
         runtime gate: SanitizerAPI
```

The removed variant was the gated one at line 92. The Fact retained attributes from line 88, so the scorer did not know the gate of the thing that disappeared. `SanitizerAPI` was stable in this pair, making Breaking a reasonable conclusion, but the data model did not support that conclusion—it happened to be correct despite losing the gate.

M151 added variants at lines 92 and 93, one depending on the experimental `TrustedTypesCreateParserOptions`. The row only said the member was modified and could not distinguish the live overload from the experimental one.

#### 2. Location cited an unchanged declaration

The `Document.parseHTMLUnsafe` change cited:

```text
third_party/blink/renderer/core/dom/document.idl:88
```

Line 88 was unchanged. The removed overload was at old line 92; the two added variants were at new lines 92 and 93. The reader reached the correct file but the wrong declaration.

#### 3. A cross-file example proved that per-variant provenance was needed

`URL.createObjectURL` spanned two files, as the commit message noted, and its overloads had different `Exposed` values. Aggregation in `dedupe_facts` was appropriate, but retaining only one representative's path and attributes discarded the very information that made cross-file aggregation necessary.

The Fact should contain variant records, not only strings:

```json
"variants": [
  {
    "signature": "...",
    "ext": {"RuntimeEnabled": "..."},
    "runtime_enabled": "...",
    "path": "...",
    "line": 92
  }
]
```

Identity remains one member, with little snapshot growth because M151 had only 121 such groups. The diff can then identify the exact removed/added variants, gate, and line.

### 28.6. “Adding an overload cannot break an existing call site” was too strong

WebIDL does not choose an overload by name alone. It builds an effective overload set and chooses a callable based on the number and types of JavaScript arguments. This is defined by the [Web IDL overload resolution algorithm](https://webidl.spec.whatwg.org/#dfn-overload-resolution-algorithm).

Minimal example:

```webidl
// old
undefined f(DOMString value);

// new
undefined f(DOMString value);
undefined f(Node value);
```

Previously, an object could be converted to a string and passed to the old overload. After adding the `Node` overload, a Node object can dispatch to the new callable. The call still runs but does not necessarily “match the overload it always matched.”

For `Navigator.install`, the new variant accepts an `InstallParams` dictionary alongside `USVString` variants. An old call passing an object may be handled differently by overload resolution once the dictionary variant exists. This is an inference from the specification's algorithm, not a claim that a specific Chromium M151 site definitely breaks.

The New surface bucket may remain an acceptable policy, but the label and reason should be more accurate:

> “A new argument shape is available; existing calls with values distinguishable as that shape may resolve differently.”

Avoid the absolute statement “every existing call still matches the overload it always did.” If score 25 remains, the documentation should identify it as a heuristic, not proof of non-breakage.

### 28.7. Signature normalization still produced false positives

`collapse_ws()` collapsed runs of whitespace but did not canonicalize spacing around punctuation. M148 → M151 `wide` contained **seven WebIDL rows** whose old/new signatures differed only in whitespace, each receiving:

```text
web_api_signature_change
score 50
Breaking
```

Example:

```text
SubtleCrypto.importKey(
→ SubtleCrypto.importKey(␠
```

After removing whitespace, the strings were identical. Other affected methods were `deriveBits`, `unwrapKey`, `decapsulateBits`, `decapsulateKey`, `encapsulateBits`, and `encapsulateKey`.

This was a pre-existing parser-normalization issue, not a regression from `b844108`. Schema 31 now used signature strings as set elements, so the issue affected both representative comparison and variant-set comparison. The fix should be canonical token serialization for WebIDL, not deleting every space, because boundaries such as `unsigned long` and identifiers still matter.

### 28.8. The absence latch: what was good and what four gaps remained

#### What was good

`cmd_run` now read `missing_targets` and `extract_stats._errors` from the new snapshot, converted them into a reason, and passed that reason into `Scope`. For a whole-fact removal:

```text
new snapshot incomplete
        ↓
confirms_absence(kind) = false
        ↓
-15 and a reason naming the missing target or parse failure
```

This was reasonable fail-closed behavior. New tests proved that the helper built the correct reason and reduced confidence for a whole preference removal.

#### Gap 1 — overload removal was `MODIFIED`, so it bypassed the latch

The scoring condition was:

```python
if change.change_type == REMOVED and not scope.confirms_absence(...):
```

Losing one overload does not remove the member, so its change type is `modified`. Probe:

```text
old: f(long); f(DOMString)
new: f(long)
new snapshot: 1 file would not parse

result:
  change_type = modified
  signal      = web_api_overload_removed
  score       = 60
  bucket      = Breaking
  unconfirmed reason = none
```

This was a direct interaction between the two new features: variant absence had been added, but the safety latch did not apply to it. For a cross-file overload such as `URL.createObjectURL`, losing one partial file could create exactly this shape.

Confidence must be based on a **removal-like semantic delta**, not only top-level `change_type`. At minimum, `web_api_overload_removed` must pass through the absence guard. Enum-member and other variant-set removals should eventually share the same abstraction.

#### Gap 2 — a hole in the old snapshot still produced a confident “New surface”

`cmd_run` called only:

```text
incomplete = _incomplete_reason(new)
```

Probe:

```text
old snapshot: a missing target contains N.install, so there is no Fact
new snapshot: complete and contains N.install

result:
  change_type = added
  signal      = web_api_added_live
  score       = 35
  bucket      = New
  confidence warning = none
```

Presence in the new version is certain, but the claim that it was “added between versions” is not; it may already have existed in a file the old run did not read. An older comment in `snapshot.py` itself said missing targets distinguish “feature was added” from “we never fetched the file declaring it.”

Scope needs both sides:

```text
REMOVED / removed variant  → query new-side completeness
ADDED / added variant      → query old-side completeness for novelty
MODIFIED value             → both facts exist, so usually no absence check
```

If the project cares only that an item is present in the adopted version, the label should be “observed in new snapshot,” not “New surface.”

#### Gap 3 — the reason gave the wrong advice

Whether the cause was a parse error or missing target, the code appended:

```text
— --target-set wide settles it
```

A real probe produced:

```text
-15 unconfirmed: 1 file(s) that would not parse ...
— --target-set wide settles it
```

Running `wide` does not fix a parser, restore a missing target, or help when the current run is already `wide`. The new test asserted the presence of `would not parse` and absence of `of that surface`, but did not check the sentence's final advice—another case where the comment was stronger than the assertion.

Advice should depend on the reason:

- coverage gap and a target not yet wide: suggest wide;
- parse error: name the file/extractor and ask for a parser fix;
- missing target: verify the tree listing or path migration;
- already wide: do not recommend rerunning the same command.

#### Gap 4 — `_errors = 0` did not mean parsing was complete

The WebIDL extractor explicitly skipped syntax it did not understand instead of failing the file. Those silent skips did not increase `_errors`. The count was also global: one WebUI extractor exception could make all WebIDL/Mojo removals unconfirmed, even though per-surface coverage had been introduced to avoid exactly that kind of cross-surface mixing.

A release-grade completeness model needs at least:

```text
from/to side
surface or extractor
missing target paths
fetch failures
extractor exceptions
parser warnings / unmatched candidate declarations
variant/identity collisions
```

If any error should invalidate the whole report, place a `comparison incomplete` banner at the top. Silently deducting 15 points from each whole removal is not a substitute for release-validity status.

### 28.9. Documentation again proved that tests did not scan “every number”

The commit correctly updated headline buckets from 282 to 283, New from 1,240 to 1,241, and test count from 327 to 335. Yet all 335 tests passed while other active figures disagreed:

| Location | Documented | Actual schema 31 |
|---|---:|---:|
| README cold/warm-run story | 3,027 changes | 3,029 |
| README owner table — Web platform | 724 | 726 |
| README owner-table total | 3,027 | 3,029 |
| `reference/signals.md` denominator | 3,027 | 3,029 |
| README/pipeline/skill coverage | still 3,669/8,349 and 8,276/8,349 | 3,677/8,366 and 8,295/8,366 |

Schema-31 `out/report.json` had `by_owner.webplatform = 726`, so this was not a grouping difference. Both overload findings belonged to Web platform; the table had simply not been updated.

The cause remained the same as in Section 27.9:

- the docs test matched only three sentence patterns and four bucket labels;
- `out/report.json` was ignored and the test could skip on a fresh checkout;
- owner, fact, coverage, and performance totals were outside the contract.

This commit supplied another example of the suite proving what its matcher knew how to inspect, not that the whole document was correct. Canonically generated figures remained the necessary fix.

### 28.10. Status of earlier blockers

| Earlier finding | After `b844108` |
|---|---|
| Two silent WebIDL cases | **Closed** |
| Complete WebIDL variant contract | **Not closed**: order, attributes, gates, locations, and overload-resolution semantics |
| Missing targets/extractor errors do not affect confidence | **Partly closed** for whole removals on the new side |
| Implicit Mojo method ordinal | Unchanged: 503 position changes, 485 without a row |
| Implicit Mojo field ordinal | Unchanged: 607 position changes, 602 without a row |
| Enclosing Mojo build guard | Unchanged: synthetic `not_compiled → compiled` still yields an empty diff |
| First-match per-surface candidate membership | Unchanged: 378 multi-surface paths |
| Per-surface coverage absent from normal reports | Unchanged |
| Mojo semantic attributes / `AllowedContext` mislabel | Unchanged |
| 17 obvious test-only Mojo facts | Unchanged |
| Cache key `.` / collisions / Windows reserved names | Unchanged |

`b844108` reduced WebIDL false-negative risk, but process-boundary comparison completeness remained the largest blocker.

### 28.11. Fix order after schema 31

#### P0 — close the overload contract properly

1. Replace `signatures` with variant records containing signature, extended attributes, runtime gate, path, and line.
2. Compute added/removed variants independently of the representative; preserve both signals when a set loses and gains variants.
3. Add a permutation test: removing the first or last overload must produce the same signal and score.
4. Test gated and cross-file overloads; reports must cite the exact declaration line.
5. Reword overload additions so they do not promise unchanged dispatch for existing calls.

#### P0 — make completeness directional and semantic

6. Keep `from` and `to` completeness in Scope.
7. Apply confidence to removal-like deltas such as `web_api_overload_removed`, not only `change_type == removed`.
8. An old-side hole must reduce confidence in an `added/new` claim or change its label to “newly observed.”
9. Remove “wide settles it” advice when the cause is parsing/missing targets or the run is already wide.
10. Store errors per extractor/surface and add parser-anomaly counters.

#### Remaining P0 items from the previous review

11. Model implicit Mojo ordinals and `[Stable]`/GN evidence.
12. Compare enclosing Mojo guards with own/inherited provenance.

#### P1

13. Canonicalize WebIDL tokens to eliminate seven whitespace-only Breaking rows.
14. Fix multi-surface coverage membership and expose the table in reports.
15. Generate documentation figures from one canonical artifact in CI.

### 28.12. Direct response to the maintainer's assessment

#### “The overload issue is real but not a blocker”

If this refers only to the two silent rows in M148 → M151, the blast-radius assessment is reasonable: the commit added two of 3,029 findings, one of them Breaking.

If it means the overload model is now sufficiently safe, it is not. New probes showed:

- the same overload removal could score 50 or 60 depending on source order;
- 42 of 121 overload groups had variant-specific attributes that the Fact did not map;
- an incomplete snapshot did not reduce confidence for overload removal because it was `modified`;
- an addition could change overload dispatch for an existing call.

Overloads were not the project's largest blocker, but schema 31 remained a **partial correctness fix**, not a closed contract.

#### “`missing_targets` has never been a problem; this is only a safeguard”

Agreed for current data: every measured run had zero missing targets, so the latch changed no current finding.

The safeguard itself was not complete. It examined only the new snapshot, applied only to whole removals, and sometimes gave the wrong advice. The precise description was:

> “A fail-closed latch was added for whole-fact removals when the new snapshot reports hard extraction incompleteness.”

That was a valuable improvement, but narrower than the general statement that “absence requires more than coverage.”

#### Verdict

> **`b844108` genuinely fixed two WebIDL false negatives and added a new-side safety latch for whole removals. It did not close overload-variant semantics or bidirectional, semantic absence confidence. The release-gate verdict remained not ready.**

## 29. Follow-up review of commits `5edc91e` and `a88f5fc` — schema 33

### 29.1. Short conclusion

These commits continued to fix several real defects, but the statement that “everything on the list is now either closed or supported by a measured rationale” remained premature.

| Maintainer claim | Independent verification | Status |
|---|---|---|
| Overload removal no longer depends on the representative | The old 50/60 probes now both score 60 | **Original defect fixed** |
| The same declared arity can shadow an old call | Correct for `Navigator.install` | **Current case fixed** |
| A new declared arity cannot receive an old call | Incorrect: extra arguments may be ignored, and optional/variadic declarations create several effective arities | **New policy is wrong** |
| Seven whitespace-only Breaking rows disappeared | Correct: 7 → 0 and Breaking 283 → 276 | **Current pair fixed** |
| The new normalization removes only formatting | Incorrect: it also rewrites string literals/defaults and can hide semantic changes | **New regression** |
| Completeness is latched in both directions | `from_incomplete` exists, but directions are mixed; old-side coverage does not exist and the false New label remains | **Partial** |
| `platform_state` is compared for every kind that needs it | All ten kinds currently carrying it are now compared | **Mechanism fixed** |
| That fix reveals 14 previously invisible findings | Incorrect: it adds zero rows to the real pair; 14 is the total of pre-existing build-gate rows | **Measurement claim is wrong** |
| The reviewer was wrong about Mojo ordinals | The audit explicitly discussed implicit ordinals and had already credited the explicit fix | **Rebuttal targets the wrong claim** |
| Ordinal measurements were 1,460 interfaces / 50 shifted interfaces | Report snapshots contain 1,396 common interface facts, 1,357 common method-bearing interfaces, and 48 shifted interfaces | **Not reproducible** |
| Per-overload runtime gates are retained | A non-representative gate change now produces `web_api_exposure_changed` | **Fixed** |
| The final variant issue is closed | Per-overload extended attributes and provenance are still lost; a synthetic attribute change yields an empty diff | **Not closed** |
| The README issue concerned schema 27/28 in a changelog | The audit never criticized those labels; active counts, coverage, and owner tables remained stale | **Rebuttal addresses a different issue** |
| 340 tests | Bare and explicit discovery run all tests on Python 3.14 and 3.9 | **Verified** |

The verdict remained **not ready as a release gate**. The maintainer deserved credit for continuing to verify and fix issues quickly. What needed greater precision was the distinction among these three statements:

1. the code now carries additional evidence;
2. the current M148 → M151 report contains additional rows;
3. the correctness contract is closed.

They are not automatically equivalent.

### 29.2. Baseline and rerun results

```text
HEAD             a88f5fc
origin/main      a88f5fc
schema           33
commit history   70 commits
working tree     clean before this audit update
```

Tests:

```text
Python 3.14.6  python3 -m unittest discover -q
Ran 340 tests — OK

Python 3.14.6  python3 -m unittest discover -s tests -q
Ran 340 tests — OK

Python 3.9.6   /usr/bin/python3 -m unittest discover -q
Ran 340 tests — OK
```

Schema-33 snapshots and reports:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28,507 → 29,138 | 3,022 | 276 | 469 | 1,240 | 1,037 | 187 |
| `wide` | 52,367 → 54,298 | 6,064 | 798 | 696 | 2,979 | 1,591 | 441 |

M151 coverage was unchanged:

```text
default  3,677 / 8,366
wide     8,295 / 8,366
```

Actual schema-33 default owner totals:

```text
ipc             339
webplatform     719
native        1,157
webui           277
config          530
```

### 29.3. The order-dependent 50/60 defect was fixed, but the overload model gained a threshold bug

First, the correct part: the `signatures` branch was no longer an `elif` under `signature`. For members with multiple overloads on both sides, the removal signal was emitted even when the representative signature also changed. Two real rows previously on the generic score-50 signal now received the dedicated score-60 removal signal:

- `GPUQueue.copyElementImageToTexture`;
- `WebGLRenderingContextBase.texElementImage2D`.

The original “remove the first or last overload” probes now both produced `web_api_overload_removed` at score 60. The order dependence reported in Section 28.4 was closed.

However, `signatures` was stored only when a member had **more than one** signature. A 1 → 2 transition looked like:

```text
old.signature   = f(DOMString)
old.signatures  = absent

new.signature   = f(DOMString)
new.signatures  = [f(DOMString), f(Node)]
```

`_overload_signals()` saw the `signatures` delta and treated the old side as an empty set. It did not know that `f(DOMString)` already existed.

Probe:

```webidl
// old
void f(DOMString x);

// new
void f(DOMString x);
void f(Node x);
```

Schema 33 result:

```text
signal  web_api_overload_added
score   25
bucket  New surface
```

This is the same-arity shadowing that signal 45 was designed to catch. The new test missed it because fixture `ONE` already had two overloads before adding the third.

Facts should always carry a canonical variant set, including singletons. If the serialized shape should not change for every member, the diff must at least reconstruct a singleton set from `signature` when `signatures` is absent.

### 29.4. Declared arity is not the effective overload set

`_arity()` counted only parameters written in the signature. WebIDL is not that simple.

The [Web IDL Standard](https://webidl.spec.whatwg.org/#dfn-effective-overload-set) constructs an **effective overload set**; optional and variadic arguments give one declaration several argument-count shapes. The resolution algorithm also says that when JavaScript supplies more arguments than the longest overload accepts, trailing arguments are ignored before overload selection.

That directly contradicted the new test comment:

> “No existing call can reach it, because resolution counts first.”

Even without optional arguments:

```webidl
// old
void f(DOMString x);

// new
void f(DOMString x);
void f(DOMString x, Node y);
```

An old call `f("x", node)` could call the old API with its second argument ignored. After the two-parameter overload appears, the same call may enter the new callable. A “new argument count” therefore does not prove non-breaking behavior.

Three additional probes all scored 25/New despite real overlap:

| Old | Added overload | Why they overlap |
|---|---|---|
| `f(DOMString, optional DOMString)` | `f(Node)` | the old declaration accepts one or two arguments |
| `f(DOMString)` | `f(Node, optional long)` | the new declaration accepts one or two arguments |
| `f(DOMString...)` | `f(Node, Node)` | the variadic old declaration accepts two arguments |

Measurements over cached M130/M136/M139/M143/M147/M148/M151 data found:

- four singleton-to-overload-set additions with the same declared arity were scored 25 instead of 45 because of the threshold bug: two in M136 → M139 and two in M143 → M147;
- `Document.write` and `Document.writeln` in M130 → M136 had effective-arity overlap through variadic arguments, which declared-count heuristics did not detect.

M148 → M151 had only one pure overload addition, `Navigator.install`; its old side already had three signatures, so this pair happened to receive the correct 45 classification. This explains why current buckets were correct while the general contract remained wrong.

Safer options were:

- treat every overload addition as at least Behaviour change;
- or correctly implement effective argument-count ranges, optional/variadic arguments, and extra-argument behavior;
- do not call a branch “safe” based only on declared parameter count.

### 29.5. The whitespace fix removed seven false positives but introduced a new false negative

The current-pair measurement was correct:

```text
whitespace-only signature rows   7 → 0
Breaking                       283 → 276
```

But `_normalize_signature()` used global `str.replace()` around `(`, `)`, comma, `<`, and `>`. It did not know whether a token was syntax or part of a string literal.

Probe:

```webidl
// old
void f(optional DOMString x = "a,b");

// new
void f(optional DOMString x = "a, b");
```

These defaults are different strings. Schema 33 returned:

```text
NO CHANGE
```

The normalizer rewrote both into the same string. A space after `(` inside a quoted default could similarly disappear. The formatting fix therefore traded seven current false positives for a new class of false negatives.

`5edc91e` added no normalization test. Canonicalization must be token-aware: preserve string, escape, and comment tokens while normalizing whitespace only between syntax tokens.

### 29.6. Directional completeness was still not truly directional

`cmd_run` now passed:

```text
incomplete       = hard errors in the new snapshot
from_incomplete  = hard errors in the old snapshot
```

That was a useful step. But `Scope.confirms_absence()` returned false if **either** value was non-empty, regardless of which side a finding depended upon.

Schema-33 probes:

| Change | Side containing the hole | Current result | Problem |
|---|---|---|---|
| Whole removal | old only | 35 → 20 | an old-side hole does not weaken new-side absence |
| Overload removal | old only | 60 → 45 | same directional error |
| Overload addition | new only | 25 → 10 | new presence is observed; novelty depends on the old side |
| Whole addition | old only | score reduced but bucket still `New` | the bucket name still claims novelty |

Additional issues:

1. Scope stored per-surface coverage only for `to`; 1% old-side coverage could not be represented.
2. Every `signatures` delta was treated as the same absence shape; added and removed variants were not separated.
3. When both sides had errors, the reason used only `new or old`, losing one side from the explanation.
4. The class docstring still said “Only the new side matters, and only for removals,” contradicting the new code.

With a hard hole on the old side, an added Web API was still labelled “Web API added” in the New bucket; only its score dropped. The latch reduced reading priority but did not prevent false novelty.

No test contained `from_incomplete`. `5edc91e` added only two overload tests; completeness, normalization, and platform-state changes had no new regression tests.

The model needs a directional API, for example:

```text
scope.confirms_absence(side="to", kind=...)    # removal
scope.confirms_absence(side="from", kind=...)  # novelty
```

For variant sets, the diff should pass explicit `removed_variants` and `added_variants` rather than infer direction merely from the existence of a `signatures` delta.

### 29.7. `platform_state`: mechanism fixed, but “14 new findings” was a counting error

Schema-33 M151 stored `platform_state` on exactly ten kinds:

```text
base_feature, feature_param,
mojo_interface, mojo_method, mojo_struct, mojo_field, mojo_enum,
pref, switch, webui_control
```

Before the commit, three were compared; the commit added the other seven. The mechanism therefore connected every kind that actually carried `platform_state`. This was a correct fix.

Its yield on M148 → M151 was not 14 new findings:

| Target | Rows before/after removing the seven new attributes from `MEANINGFUL_ATTRS` | New rows | Existing rows changing signal/bucket |
|---|---:|---:|---:|
| `default` | 3,022 / 3,022 | 0 | 0 |
| `wide` | 6,064 / 6,064 | 0 | 0 |

In `wide`, exactly one existing Mojo row gained a `platform_state` delta:

```text
optimization_guide.mojom.ModelBroker.AddModelDownloadProgressObserver
```

That row already had `signature`, `params`, and `attrs` deltas and signal `ipc_signature_change` 80; its score, bucket, and signal did not change.

The number 14 was the total of existing `build_gate_changed` findings in the current default report:

- 12 `webui_control` rows already had `build_conditions` deltas;
- two `base_feature` rows already had `conditions` deltas.

All 14 predated the platform-state patch. The report totals proved it: schema 31 had 3,029 rows, and removing seven whitespace-only rows yielded exactly 3,022, with no intermediate addition of 14.

Accurate wording would have been:

> “Connected comparison for the remaining seven kinds; measured yield on this pair was zero new rows, with one existing row receiving additional evidence.”

This remained a worthwhile mechanism fix, like the completeness latch and overload-gate work. Calling 14 rows “previously invisible” simply misattributed the measurement.

### 29.8. `overload_gates` preserved gates correctly; extended attributes were still lost

Remeasuring raw WebIDL produced the same figures as the commit message:

```text
M151 overload groups                         121
groups with differing runtime gates           12
groups with differing extended attributes     42
full (signature, gate, ext) tuple changed
  while signature set stayed the same         53
schema 32 already had a row                    53
schema 32 silent                                0
```

The conclusion that current yield was zero was correct. The commit-body explanation was less precise: all 53 rows already existed because representative `ext` changed; 19 also had a representative `runtime_enabled` change. None depended on a “bare signature-set move,” because this population was defined as having an unchanged signature set.

The `a88f5fc` implementation handled runtime gates correctly:

- when overloads differed by gate, the Fact stored a `signature [gate]` mapping;
- changing a non-representative gate produced an `overload_gates` delta;
- the signal was `web_api_exposure_changed` at 45/Behaviour;
- it was not misrepresented as `web_api_overload_removed` at 60;
- M148 → M151 had only one `overload_gates` delta, on `Document.parseHTMLUnsafe`, so buckets remained unchanged as expected.

The commit did not store per-overload `ext`. Probe:

```webidl
// old
void f(long x);
void f(double x);

// new
void f(long x);
[SecureContext] void f(double x);
```

The first overload was the representative, signatures did not change, and both runtime gates were empty. Schema 33 returned:

```text
NO CHANGE
```

This was the same “two gates” defect with an extended attribute other than `RuntimeEnabled`. WebIDL defines extended attributes as annotations controlling how bindings process a definition/member, and the tool already treated representative `ext` changes as `web_api_exposure_changed`. Preserving runtime gates while dropping the attribute dimension present in 42 groups did not close the variant contract.

Locations were also not always “within a few lines.” Among 120 same-file groups:

```text
median span       2 lines
p75               5 lines
15 groups        >10 lines
7 groups         >25 lines
2 groups        131 lines
```

`Document.createElement` and `createElementNS` spanned 131 lines. `URL.createObjectURL` spanned two files. The 120/121 same-file figure was correct, but the categorical claim that the reader would land in the right file “within a few lines” was not.

The correct variant shape remained structured records:

```json
{
  "signature": "...",
  "runtime_enabled": "...",
  "ext": {"...": "..."},
  "path": "...",
  "line": 92
}
```

### 29.9. The Mojo-ordinal rebuttal targeted the wrong claim and omitted field ordinals

Section 27 of this audit explicitly stated:

> “Compare ordinal now compares explicit `@N`, not implicit position.”

It also included a `Bar(); Foo();` → `Foo(); Bar();` fixture, separate method/field tables, and credited the explicit fix in schema 30. Rerunning an explicit-ordinal case therefore did not rebut the review finding.

Independent schema-33 `wide` measurement:

| Measurement | Result |
|---|---:|
| `mojo_interface` facts in M148 | 1,407 |
| `mojo_interface` facts in M151 | 1,479 |
| Interface facts present in both | 1,396 |
| Interfaces with methods on both sides | 1,357 |
| M151 methods | 6,012 |
| Methods with explicit `@N` | 196 |
| Implicit methods whose lexical index changed | 503 |
| Interfaces containing those shifts | 48 |
| Common methods actually reordered | 0 |
| Explicit ordinal value changes | 0 |

The maintainer's final two figures were correct; `1,460 common interfaces` and `50 shifted interfaces` could not be reproduced from the report's snapshots. The audit's earlier 503/48 figures still matched.

As policy, documenting trap 13 was better than leaving the hazard silent. Documentation did not make the hazard fixed. [Mojom IDL documentation](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/README.md#Versioning) says implicit ordinals are assigned by lexical position and existing ordinals must remain stable for backward compatibility. The [bindings generator](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom_bindings_generator.py) also walks method order when generating scrambled ordinals for methods without an explicit value.

The argument that both endpoints build from one tree is valid for a stock same-version process pair. Yet the project's own trap 10 and Mojo score 80 retain these changes because a peer may be shipped separately, partially updated, or out of tree. If that rationale justifies reporting signature changes, it also justifies preserving evidence of an implicit wire-ID shift. Not all 503 rows need score 80; the right answer is to model `[Stable]`, `MinVersion`, and explicit/implicit provenance and display a separate confidence/risk tier—not discard the evidence.

More importantly, the rebuttal discussed only **methods** and omitted the field finding:

| Field measurement M148 → M151 | Result |
|---|---:|
| M151 fields | 13,015 |
| Fields with explicit ordinals | 121 |
| Implicit fields whose lexical index changed | 607 |
| Affected struct/union containers | 72 |
| Shifted fields without a diff row | 602 |

Mojom documentation specifically requires new fields to be appended and existing field ordinals to remain stable in versioned structs. Trap 13 did not mention fields, so “everything on the list is either closed or justified” was inaccurate even under a documentation-only strategy.

### 29.10. The documentation rebuttal answered a different issue

Correctly, `schema 27` and `schema 28` in the “Chromium says this in three different ways” table described historical capabilities, not the current schema number. The audit never requested that those labels be changed.

Section 28.9 concerned **active figures**, which remained wrong after schema 33:

| Active document figure | Documented | Actual schema 33 |
|---|---:|---:|
| README warm-run changes | 3,027 | 3,022 |
| README/pipeline default coverage | 3,669 / 8,349 | 3,677 / 8,366 |
| README/pipeline wide coverage | 8,276 / 8,349 | 8,295 / 8,366 |
| README/pipeline Web platform owner | 724 | 719 |
| README/pipeline Browser C++ owner | 1,386 | 1,157 |
| README/pipeline Outside repository owner | 301 | 530 |
| `signals.md` no-signal fraction | 971 / 3,027 | 981 / 3,022 |

The owner table still summed to 3,027, clearly making it an old snapshot figure rather than a changelog. Bucket headlines and `187 / 3,022` had been updated correctly: values visible to the matcher were green, while values outside it remained stale.

All 340 tests passed because the docs contract scanned only three sentence patterns and four bucket labels. Owner, overall-story, coverage, and no-signal figures were absent from the assertions. The test could also skip when `out/report.json` did not exist in a fresh checkout.

The documentation finding therefore remained. “Schema 27/28 are changelog entries” was a correct rebuttal to a claim the reviewer did not make.

### 29.11. Quality of the five new tests

`5edc91e` raised the count from 335 to 337 with two tests:

1. same-arity `Navigator.install`;
2. a removal whose representative changes still scores 60.

`a88f5fc` raised 337 to 340 with three gate tests:

1. a non-representative runtime-gate change is visible;
2. a gate change does not become an overload removal;
3. overloads sharing one gate do not carry a redundant list.

The gate tests were end-to-end and protected the intended mechanism. The two `5edc91e` tests were also useful, but left two gaps:

- “verdict does not depend on which copy survived” was not a permutation test: the second case removed two signatures and added a new one, rather than expressing the same semantic event in a different source order;
- the same-arity test began with a member that already had two overloads, so it never crossed the 1 → 2 threshold.

No new test protected:

- elimination of the seven whitespace-only rows while preserving string literals;
- the `from_incomplete` direction matrix;
- `platform_state` on any of the seven newly compared kinds;
- old-side per-surface coverage;
- optional, variadic, or extra-argument overload behavior;
- per-overload non-runtime extended attributes;
- implicit Mojo field ordinals.

All 340 passing tests therefore demonstrated internal consistency for the selected test population, not a correctness contract for all five claimed changes.

### 29.12. Fix order after schema 33 and verdict

#### P0 — WebIDL overload model

1. Always reconstruct complete old/new variant sets, including singletons.
2. Remove the conclusion that “a new declared arity is safe”; either classify every addition as Behaviour or implement the specification's effective overload set.
3. Variant records must include signature, runtime gate, full extended attributes, path, and line.
4. Use token-aware normalization that does not rewrite string/default literals.
5. Add tests for singleton → two, optional, variadic, extra trailing arguments, permutations, and quoted defaults.

#### P0 — completeness

6. Store `from` and `to` coverage/errors per surface.
7. Query the correct side for whole/variant additions and removals.
8. Do not retain a confident `New` label/bucket when old-side absence is unconfirmed.
9. Test the matrix of old-hole/new-hole × added/removed/variant-added/variant-removed.

#### P0 — process-boundary completeness

10. Store implicit lexical indexes for methods and fields.
11. Preserve container `[Stable]`, `MinVersion`, and provenance so risk can be tiered rather than assigning 80 uniformly.
12. Close enclosing guards with own/inherited provenance.

#### P1

13. Generate every measured documentation figure from a canonical report artifact.
14. Make the documentation contract work on a fresh checkout rather than relying on optional `out/report.json`.
15. Fix first-match per-surface membership and expose the table in normal reports.

#### Final verdict

> **`5edc91e` genuinely fixed order-dependent removal, the seven current whitespace false positives, same-arity `Navigator.install`, and the platform-state comparison mechanism. `a88f5fc` genuinely fixed per-overload runtime gates. However, the new declared-arity policy did not match WebIDL, the normalizer introduced a false negative, completeness still mixed directions, extended attributes and provenance remained absent, implicit field ordinals remained unanswered, and the documentation rebuttal addressed the wrong claim. The list was not closed; release-gate readiness remained unmet.**

## 30. Final review of the `cd1ee05` → `3f28ac8` → `0a9638e` → `0933dcd` sequence — schema 37

### 30.1. Short conclusion

This four-commit sequence **genuinely fixed many items**. Once the project owner clarified that the goal was partial early warning—not an automated release gate or 100% coverage—the verdict needed to be reframed:

> **Schema 37 met the current goal: detect a useful subset of changes early, prioritize them for human review, and preserve traceable evidence.**

The statement that “the entire list is finished” was still inaccurate because the full version matrix exposed a real regression in M143 → M147. That regression belonged in the radar's precision backlog; it did not make the tool useless or prevent it from meeting its product goal.

| Maintainer claim | Independent verification | Status |
|---|---|---|
| Singleton → overload set is handled correctly | The old singleton signature is reconstructed; a same-arity addition becomes 45/Behaviour | **Fixed** |
| Optional and extra-argument behavior is handled | New fixtures are correct; a longer overload is no longer labelled safe | **Main part fixed** |
| Whitespace normalization does not rewrite literals | Simple literals are preserved | **Reported case fixed; escaped quotes remain open** |
| Per-overload extended attributes are retained | `overload_traits` carries signature + gate + ext; a non-representative ext probe produces a row | **Fixed** |
| Directional hard-hole matrix | All 16 whole/variant × old/new/both/no-hole combinations behave correctly in `Scope` | **Fixed in the unit API** |
| Pipeline supplies coverage for both sides | `cmd_run` still creates `Scope({"to": ...})` and omits old coverage | **Not wired** |
| The New bucket no longer claims novelty when the old snapshot has a hole | Correct for a hard missing/parse hole; partial old coverage is still ignored | **Partial** |
| `[Stable]`/`MinVersion` now forms the right tier | A Stable transition creates 164 false child Breaking rows in real M143 → M147; method MinVersion lacks a dedicated field | **High-priority precision bug** |
| Own/inherited guard provenance is closed | Only methods/fields retain `inherited_conditions`; child findings fan out and nested containers remain silent | **Not closed** |
| Per-surface first-match is resolved | Code still `continue`s on the second claimant and records “under the first” | **Not fixed; only documented** |
| Every documentation figure is generated from the artifact | The artifact is correct for selected figures; many active values remain outside it, and a clean checkout still skips the report oracle | **Partial** |
| A row points to every overload | JSON retains all locations; Markdown/HTML truncate after three | **Data fixed; output incomplete** |
| 360 tests pass | 360/360 on Python 3.14 and 3.9 | **Verified, but the interaction escaped them** |

Verdict:

> **Accept schema 37 for early warning and manual triage. Do not accept the narrower claim that every correctness backlog item is closed. Stable transitions, novelty confidence, and guard aggregation should improve; missing parser grammar is known scope rather than a blocker when documented clearly.**

### 30.2. Baseline, tests, and the full real-version matrix

Baseline:

```text
HEAD / origin/main   0933dcd
schema               37
commit history       74 / 74 commits
working tree         clean before this audit update
```

Tests:

```text
Python 3.14.6  python3 -m unittest discover -q
Ran 360 tests — OK

Python 3.9.6   /usr/bin/python3 -m unittest discover -q
Ran 360 tests — OK
```

Schema 37 was rebuilt for M143 and M147, including `wide`, and all three adjacent pairs were run rather than only M148 → M151.

#### Default

| Pair | Facts | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 | `to` coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M143 → M147 | 28,133 → 28,531 | 4,023 | 339 | 923 | 1,426 | 1,335 | 189 | 3,578 / 8,019 |
| M147 → M148 | 28,531 → 28,507 | 1,273 | 79 | 252 | 434 | 508 | 159 | 3,605 / 8,094 |
| M148 → M151 | 28,507 → 29,138 | 3,022 | 276 | 469 | 1,240 | 1,037 | 187 | 3,677 / 8,366 |

#### Wide

| Pair | Facts | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 | `to` coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M143 → M147 | 50,535 → 52,030 | 8,045 | 1,330 | 1,266 | 3,278 | 2,171 | 517 | 7,949 / 8,019 |
| M147 → M148 | 52,030 → 52,367 | 2,250 | 276 | 330 | 966 | 678 | 245 | 8,024 / 8,094 |
| M148 → M151 | 52,367 → 54,298 | 6,064 | 798 | 696 | 2,979 | 1,591 | 441 | 8,295 / 8,366 |

Every snapshot had:

```text
missing_targets = 0
extract_stats._errors = 0
```

Current M148 → M151 counts and buckets reproduced the commit message. Regenerating `docs/figures.json` from the real default and wide reports also produced the same byte-level data structure. The issues were interactions on another pair and populations not modeled by an extractor—not incorrect current headlines.

### 30.3. What the four commits fixed correctly

This deserves explicit treatment so the review does not become “every fix is rejected.”

1. **Singleton → two overloads.** Even when old `signatures` is `None`, signal code reconstructs it from `old_fact.signature`. A one-parameter string plus one-parameter object case now becomes `web_api_overload_shadowed`, 45/Behaviour.
2. **Optional and extra trailing arguments.** `_arity_range()` models the required-to-declared range, and an overload above the old ceiling is treated as potentially capturing an old call. The schema-32/33 mistakes were corrected.
3. **Simple quoted literals.** Normalization protects literals before adjusting whitespace; probes for `"a,b"` and `"a, b"` no longer compare equal.
4. **Per-overload extended attributes.** `overload_traits` retains signature, runtime gate, and extended attributes. A change to a non-representative gate/ext produces `web_api_exposure_changed` rather than a false overload removal.
5. **Hard-hole direction.** Whole and overload additions/removals ask the correct old/new hard-hole question in `Scope`; `--target-set wide` advice is no longer appended to parse/missing-target reasons.
6. **New bucket under a hard hole.** If the old source genuinely has a missing target or parse failure, an addition no longer remains in `New surface`.
7. **Location data.** Schema-37 snapshots retain `overload_locations`; the M148 → M151 `report.json` contains the full union of old/new locations for all four current overload-set changes.
8. **Current figures.** When invoked correctly with real default and wide reports, regenerated figures exactly match the committed artifact.

These are meaningful improvements. The following sections explain why they did not amount to full correctness closure.

### 30.4. High-priority precision defect: `[Stable]` appearing or disappearing creates ordinal changes by itself

#### Failure mechanism

The extractor recorded `position` on children only when the container had `[Stable]`:

```text
old container [Stable]   child.position = N, child.stable = true
new ordinary container   child.position = absent, child.stable = absent
```

The diff could not tell that the field was absent because of serialization policy. It saw:

```text
position: N → None
stable:   true → None
```

Because `position` was meaningful:

- methods received `ipc_ordinal_changed`, 80/Breaking;
- fields received `ipc_shape_changed`, 80/Breaking.

The lexical position could be completely unchanged. This should have been a **container stability-promise change**, not N simultaneous method/field wire-ordinal changes.

#### Real M143 → M147 `wide` measurement

| Measurement | Result |
|---|---:|
| Rows with a `stable` delta | 225 |
| Breaking | 193 |
| Behaviour | 32 |
| Child method/field rows | 183 |
| Child rows with only `stable + position` | **164** |
| Among those 164, lexical index actually unchanged | **164 / 164** |
| Annotation rows raised from 35 to 80 by `position` | 14 |
| Rows with a real type change that still warranted 80 | 5 |
| Pure container-stability rows | 32 |

The full matrix therefore exposed:

- **164 extra Breaking rows** with no signature, type, ordinal, or lexical-order change;
- **14 real annotation changes incorrectly raised to 80**;
- only five child rows with a real type change sufficient to retain 80.

Example:

```text
device.mojom.HidCollectionInfo.children
position: 6 → None
stable: true → None
signal: ipc_shape_changed + ipc_stability_changed
score/bucket: 80 / Breaking

raw lexical index: 6 → 6
```

This was not an imagined edge case: `PhotoSettings` alone produced 47 child rows, `PhotoState` 33, and `HidReportItem` 25.

#### Container signals were also inaccurate

A pure stability delta on an interface was correctly labelled `ipc_stability_changed` 40. Structs and enums, however, went through:

```python
elif any(a in deltas for a in ("default", "attrs", "min_version", "stable")):
    ipc_field_annotated
```

Thus 17 struct and ten enum pure-stability rows were described as “field default or version annotation changed,” even though the row was a container with no field default.

#### `MinVersion` was still partial

Fields had a dedicated `min_version`; methods did not. M151 `wide` contained:

```text
Mojo fields with MinVersion    97 — dedicated key: 97
Mojo methods with MinVersion   55 — dedicated key: 0
```

Methods retained `{"MinVersion=10": true}` inside generic `attrs`. A probe from `MinVersion=1 → 2` produced:

```text
signal: build_gate_changed
```

That label was wrong: MinVersion is a version annotation, not a build condition.

#### Correct direction

Do not serialize position on only one side and compare field presence. Instead:

1. always retain the raw lexical index and provenance in the Fact;
2. decide **whether to compare the index** from the container's Stable tier;
3. emit one container row when Stable appears/disappears;
4. emit child ordinal/shape rows only when the raw index actually changes;
5. parse method MinVersion into a dedicated field and use the correct signal.

### 30.5. Own/inherited guard provenance was still incomplete and fanned out

Commit `0a9638e` added `inherited_conditions` to `mojo_method` and `mojo_field`. Preserving provenance was the right idea, but the implementation did not reach the audit's intended design.

#### Only children retained provenance

`mojo_interface`, `mojo_struct`, and `mojo_enum` did not compare `inherited_conditions`. As a result:

- a member knew that a guard came from its container;
- a nested container did not know whether a guard belonged to it or an ancestor;
- moving a guard between a nested struct and an enclosing interface could remain silent.

Probe:

```mojom
// old
interface I {
  [EnableIf=is_win] struct S { int32 x; };
};

// new
[EnableIf=is_win] interface I {
  struct S { int32 x; };
};
```

Neither `S` nor `S.x` had a provenance delta. Only the interface received a generic platform row because of the absent → compiled representation.

#### A container guard was duplicated onto every child

Moving a guard from a field to a two-field struct produced three rows:

```text
field a   attrs + inherited_conditions
field b   inherited_conditions + platform_state
struct S  platform_state
```

With N fields, the pattern was container + N children—the duplicate fan-out Section 27.5 had warned against.

Real M143 → M147 `wide` had seven rows with an `inherited_conditions` delta. Six belonged to `UpdateScrollbarThemeParams` alongside a container guard change. One existed only because of provenance:

```text
proxy_resolver.mojom.SystemProxyResolver.GetProxyForUrl
inherited: EnableIf=is_win → EnableIf=is_win|is_mac
Windows verdict: compiled → compiled
score/bucket: 35 / Behaviour
```

The product platform was fixed to Windows. This row did not change whether the declaration existed in the Windows binary, yet its label still said it “may no longer be in the binary we ship.”

The cleaner design remained:

- a container-guard change emits one container-level row;
- a direct member-guard change emits a member-level row;
- children retain inherited provenance for explanation, but provenance-only changes do not fan out automatically;
- compare the effective product verdict separately from source-ownership provenance.

### 30.6. Directional completeness: hard holes improved, but novelty confidence was still wrong

#### `Scope` was better, but the product path did not supply old coverage

`Scope` had `shares["from"]` and `shares["to"]`. Unit tests passed both directly. Yet `cmd_run` still wired:

```python
Scope({"to": new.meta["coverage"]}, ...)
```

Report metadata retained both sides, but the scoring path supplied only `to`. This was another “two gates” defect: the data model had the capability, while the real pipeline did not use it.

Current counts did not change because partial coverage was deliberately ignored for additions; only an old hard hole affected them. That did not make the wiring correct.

#### “An addition is something we observed” did not prove novelty

The maintainer was half right:

- a declaration **present in the new snapshot** is an observed fact;
- a declaration **absent from the old version** is an absence-based claim.

The `New surface` bucket asserted both, not just the first.

Comparing default additions against the old `wide` M148 snapshot showed:

| Default row | Default report says | Old `wide` truth | Correct wide diff |
|---|---|---|---|
| `IncomingCallNotifications` | Added, on by default | Already existed and was enabled in the old version | Only `declaration_moved` |
| `Prerender2FallbackPrefetchSpecRules` | New feature, on by default | Already existed disabled in the old version | `default_flip_on` + moved |
| `NewTabPageCustomizationThemeSync` | Added | Old copy was Android-only, not compiled on Windows | Windows availability was genuinely new |
| `NewTabPageCustomizationV2` | Added | Old copy was Android-only, not compiled on Windows | Windows availability was genuinely new |

The current default report therefore contained at least **two false novelty claims** disproved by the wide snapshot itself. Moving all 1,240 New rows to Housekeeping would have damaged usefulness, as an earlier attempt showed. The proper distinction was:

```text
observed_presence = certainly present in the new snapshot
novelty_confidence = whether the old surface was complete enough to prove prior absence
```

Alternatively, under partial reading use “newly observed in this scope,” not the categorical “New surface.”

#### Hard holes were fixed

When the old snapshot had a genuine missing target or parse error, whole/variant additions received a penalty and left the New bucket. When the hole was on the side irrelevant to the claim, scores stayed unchanged. The 16-case matrix correctly protected this behavior.

### 30.7. Per-surface first-match was not fixed

The code still did:

```python
if path in found:
    shared += 1
    continue
found[path] = rule.note
```

The commit did not change membership. It decided that per-surface rows should partition the global denominator and added the note “under the first.” But the two measurements answer different questions:

- global denominator: how many unique files are there? Paths must be deduplicated;
- surface denominator: which surfaces could this file declare? A file must belong to every matching surface.

M151 measurements:

```text
unique global candidates       8,366
multi-surface paths              378
extra memberships                378
```

The M151 value was 378, not 368; 368 belonged to the old M148 side. The pair moved from 368 to 378.

Two surfaces were distorted:

| Surface / target | Current first-match | Correct multi-membership |
|---|---:|---:|
| Pref/switch — default | 4 / 348 (1.15%) | 9 / 529 (1.70%) |
| Pref/switch — wide | 345 / 348 (99.14%) | 526 / 529 (99.43%) |
| Visibility gates — default | 340 / 340 | 537 / 537 |
| Visibility gates — wide | 340 / 340 | 537 / 537 |

The 95% threshold happened to produce the same yes/no result, so bucket counts did not change. The denominator and population remained wrong; a future target/rule could cross the threshold because of this ordering choice.

Normal `report.md` and `report.html` still showed only overall coverage. None of the six surface labels appeared in either report; `by_surface` existed only in JSON metadata.

Conclusion: item #3 in the remaining list was unchanged. The commit documented disagreement but did not implement the requested behavior.

### 30.8. Per-overload locations: data fixed, renderer not fixed

The decision **not to put line numbers in `MEANINGFUL_ATTRS` was correct**. Lines moving because code above them changes is not a Web API change.

The schema-37 data layer also handled most of the problem correctly:

- M151 had 121 overload groups;
- every multi-signature group had `overload_locations`;
- `Change.locations` contained the union of old/new positions;
- current report JSON contained all locations for the real rows.

The commit said the reader would land on the right lines and that a row pointed to every overload. The renderers still truncated:

```python
Markdown detail: where[:3]
HTML data:       paths[:3]
Markdown table:  where[0]
```

Real examples:

| Finding | JSON locations | Markdown detail | HTML |
|---|---:|---:|---:|
| `Navigator.install` | 5 | 3 | 3 |
| `WebGLRenderingContextBase.texElementImage2D` | 4 | 3 | 3 |

For the WebGL row, line 651 was a genuinely removed overload omitted by the renderer. The new test asserted only a two-location fixture and did not render a finding with four or five.

A small fix would either:

- render every changed-variant location;
- or show the first three plus an expandable “and N more.”

Tests should cover JSON **and** Markdown/HTML for a group with four or five variants.

### 30.9. `docs/figures.json`: a real improvement, but not the single source for every figure

#### What was correct

Regenerating with:

```bash
chromedrift figures out/report.json --wide <wide-report.json>
```

produced exactly the committed `docs/figures.json`. Selected current metrics were not stale:

```text
total          3,022
buckets        276 / 469 / 1,240 / 1,037
owners         339 / 719 / 1,157 / 277 / 530
no_signal      981
coverage       3,677 / 8,366; 8,295 / 8,366
```

Three document-to-artifact tests also ran on a clean checkout.

#### A clean checkout still skipped the oracle

Running the test class alone inside a clean `git archive HEAD` produced:

```text
Ran 4 tests
OK (skipped=1)
```

The skipped test was the artifact-to-real-report oracle:

```text
no out/report.json; run the pair to check the artifact
```

A fresh CI run therefore proved that docs matched the committed artifact, not that the artifact matched current code and Chromium data. No release/CI step automatically ran the report and `figures` command.

#### The wide oracle was not tested

The artifact-to-report test opened only default `out/report.json` and compared only `coverage.default`. `_WIDE_READ = 8295` was declared but unused. Even if `out-wide/report.json` existed, the test did not read it.

The command did not validate inputs either. Passing the default report itself as `--wide` was accepted and wrote:

```json
"wide": {"read": 3677, "candidates": 8366}
```

instead of rejecting the wrong target set.

#### Not every measured figure was in the artifact

The artifact covered totals, buckets, owners, Breaking-by-owner, no-signal, and overall coverage. Several active measurements remained handwritten and outside the matcher, including:

- `220 of 276 Breaking rows are Mojo or web API`;
- control inventory `971 / 955 / 190 / 156 / 130 / 15`;
- `14 of 187` platform-divergent flags;
- ordinal/Stable tables in `traps.md`.

The accurate description was:

> “A canonical artifact now exists for the current headline figures.”

It was not yet accurate to say that every documentation figure came from the report or no manual updates were required.

### 30.10. Two residual mechanisms in effective arity and normalization

#### Variadic ranges were recognized but used incorrectly

`_arity_range("void f(long... a)")` correctly returned `(0, None)`. `_overload_signals()` nevertheless added only `low` to `served` and set `ceiling = None`. Adding an overload above `low`:

```webidl
// old
void f(DOMString... xs);

// new
void f(DOMString... xs);
void f(long x, long y);
```

could capture a two-argument call already accepted by the old variadic declaration. The current result remained:

```text
web_api_overload_added — 25 / New
```

instead of shadowing/Behaviour. Four real M151 overload groups had a variadic signature, but no observed addition in the M143–M151 pairs matched this failure shape, so this was a contract gap without current yield.

`_arity_range()` also split on commas without preserving string literals. A signature with a default string containing a comma could therefore receive the wrong parameter count—another instance of the lexer problem.

#### The literal regex did not understand escaped quotes

Simple `"a,b"` was fixed. `_LITERAL_RE = r'"[^"]*"|...'` did not understand escapes. Probe:

```webidl
"a\",b"  →  "a\", b"
```

still normalized to the same string. No real M143–M151 row used this shape; a small tokenizer and regression test were needed before calling the normalization contract closed.

### 30.11. Raw grammar inventory: `0 parser errors` did not mean the grammar was fully read

The maintainer had already listed this as “worth doing next,” and the result explains clearly why 359 of the 360 tests were not an oracle.

#### Extracted facts before and after dedupe

| Version wide | WebIDL raw output → deduped | Mojo raw output → deduped | Extract errors |
|---|---:|---:|---:|
| M143 | 14,323 → 14,134 | 22,569 → 22,563 | 0 |
| M147 | 14,505 → 14,303 | 23,521 → 23,513 | 0 |
| M148 | 14,567 → 14,371 | 23,829 → 23,821 | 0 |
| M151 | 14,763 → 14,569 | 24,858 → 24,850 | 0 |

The WebIDL dedupe loss was mostly overload and duplicate UIDs; schema 37 retained signatures, traits, and locations better than earlier schemas. This table still counted only what the extractor **recognized**.

#### WebIDL grammar with no fact kind

Across the 2,166 M151 IDL files that were fetched and read, the lexical inventory contained:

| Top-level grammar | M151 records | M148 → M151 changes |
|---|---:|---:|
| Callback function definitions | 85 | 0 |
| Typedefs | 144 | +1 |
| `Interface includes Mixin` relations | 200 | +7 / −7 |

That is **429 records with no fact kind**. `includes` matters most: mixin members are keyed under the mixin, but the relation is what states which concrete interface actually receives those members.

The current pair contained 14 `includes` relation moves. The tool reported several related mixin/member additions and removals, but stored no `HTMLElement includes ...` or `SVGElement includes ...` relation. The `SanitizerPI` typedef was added and members using that name produced rows, but the typedef shape itself produced none.

A concrete historical false negative:

```text
M143 → M147
typedef LanguageModelMessageValue changed underlying union
ChromeDrift rows mentioning that identity: 0
```

The member signatures kept using the alias name, so the allowlist comparison never saw the underlying type change.

#### Mojo grammar with no fact kind

The materialized M151 `.mojom` inventory contained:

```text
feature blocks             18
const identities          311
const declaration variants 337
```

The extractor modeled only interface/method/struct/union/field/enum. The M148 → M151 lexical inventory showed:

```text
feature  +1 / -2 / ~1
const    +4 / -12 / ~3
```

`kWebNNCompilerProcess` was added, `kWebNNDirectML` was dropped, and `kWebNNLiteRT` changed body; no fact in the M151 wide snapshot contained any of those identities. The files were still counted as process-boundary candidates that had been read.

Not every constant needs a high severity. But one of two honest options had to be chosen:

1. add the fact kinds and grammar support;
2. document the exclusion and stop using “read 99% of process-boundary interfaces” as evidence of parser completeness.

The main point:

> `_errors = 0` only meant that the extractor did not throw on the grammar it attempted. It did not prove that the extractor recognized every declaration class in the file.

### 30.12. Test quality, fix order, and final verdict

#### Why 360 passing tests still missed the defects above

The new tests were better than earlier ones because many fixtures ran through extract → dedupe → diff → score. They still locked each local behavior in isolation:

- the Stable reorder test captured two stable snapshots, not a Stable → non-Stable transition;
- the location test used exactly two locations and never crossed the renderer's limit of three;
- the coverage test built `Scope` directly instead of going through `cmd_run` wiring;
- the documentation test had a ready-made artifact and never generated its own oracle report;
- the first-match test locked the first-match policy itself, not semantic membership;
- grammar that is never extracted cannot be seen by a snapshot-based test at all.

The full matrix was the most valuable defect-finding step of this round: the current M148 → M151 pair had zero stability rows, which made the mechanism look safe, while M143 → M147 immediately produced 225 stability delta rows and exposed 164 false ones.

#### Recommended fix order

##### High priority — reduce radar noise and avoid wrong labels

1. Fix Stable transitions: always keep the raw lexical index, compare by container tier, and stop duplicating container stability down to children.
2. Separate `stable` from `ipc_field_annotated`; parse method `MinVersion` separately and signal it correctly.
3. Redesign guard provenance around container/member aggregation; do not fan out inherited-only rows.
4. Pass both old and new coverage into `Scope` from `cmd_run`; separate observed presence from novelty confidence.
5. Add regressions built from the two current false novelty facts (`IncomingCallNotifications`, `Prerender2FallbackPrefetchSpecRules`).
6. Document the coverage contract for WebIDL callback/typedef/includes and Mojo feature/const grammar; add new extractors only when those surfaces have real value for users.

##### Next priority — report and infrastructure

7. Per-surface multi-membership: global dedupe, surface overlap, and the table printed in the normal report.
8. Renderer shows every changed overload location or an expandable “N more”.
9. `figures` validates pair, schema, and target set; test the wide report; run artifact generation and checking in CI or release.
10. Extend the artifact and templates to the active measured figures still written by hand.
11. Make the arity parser quote-, escape-, and variadic-aware, and add an escaped-literal regression.

#### Final verdict

> **Schema 37 was clearly better than schema 33, the current M148 → M151 headline figures were reproducible, and the project met its goal of being a static early-warning inventory for manual triage. The full matrix still proved that Stable modeling created false Breaking rows at scale; first-match, guard aggregation, CLI old-coverage wiring, and renderer locations remained backlog. Raw grammar showed which surfaces the tool did not read, but for a partial-detection goal that is known scope to document and prioritize by value, not a requirement to reach 100%.**

## 31. Review of `843dd96` and `bee9e7d` — defining “good enough” for early detection

### 31.1. Conclusion in plain terms

The goal had been settled as:

> Finding 100% of changes is not required. What is required is catching a useful subset early, with few serious false alarms, pointed precisely enough for a person to check, and with a clear statement of what was not read.

Measured against that goal:

> **Schema 39 was good enough to use as it stood. No defect was found that required suspending use.**

The two new commits closed exactly the serious defects the previous audit had found. In the full matrix no row was pushed into Breaking merely because `position` disappeared along with `[Stable]`, and the current overload findings no longer hid declaration locations. What remained fell into three quite different categories:

1. one duplication bug worth fixing soon to reduce radar noise;
2. a few known-scope items and edge cases that only needed documenting while waiting for real yield;
3. infrastructure that could improve later without affecting use of the tool today.

### 31.2. Independent verification of the two commits

Baseline:

```text
HEAD / origin/main   bee9e7d
schema               39
history              76 / 76 commits
Python 3.14           362 / 362 tests pass
Python 3.9            362 / 362 tests pass
```

#### `843dd96`: the false Breaking rows were fixed correctly

The mechanism was right: `position` counts as ordinal evidence only when both sides have a position to compare. A `[6, None]` delta no longer turned itself into an 80-point `ipc_shape_changed`/`ipc_ordinal_changed`.

Schema 39 rerun results:

| Pair | Default Breaking | Wide Breaking | Breaking from `position → None` alone |
|---|---:|---:|---:|
| M143 → M147 | 339 | 1,152 | 0 / 0 |
| M147 → M148 | 79 | 276 | 0 / 0 |
| M148 → M151 | 276 | 798 | 0 / 0 |

The five M143 → M147 wide Breaking rows that still carried `position` each had an independent `type` delta, so keeping them at 80 points was correct.

This was the most important fix of the two, because a radar that reports false Breaking rows in bulk quickly trains its users to stop reading it.

#### `bee9e7d`: all five main changes were sound

1. **Both coverage sides reached the real pipeline.** `cmd_run` passes both `old.meta.coverage` and `new.meta.coverage` to `Scope`; the data model no longer knows about both sides while the call site supplies only `to`.
2. **The Windows verdict is compared instead of how the guard is written.** `absent` and `{windows: compiled}` normalize to the same state. A probe guard moved from a field up to its struct no longer makes a field that is unchanged on Windows count as “may no longer be in our binary.”
3. **Inherited provenance no longer creates child rows.** `inherited_conditions` is still stored for explanation but left the comparison allowlist. Six real-version runs produced zero `inherited_conditions` delta rows.
4. **Per-surface membership answers the right question.** Global still counts 8,366 unique files, and a file is counted in every surface whose extractor read it. Actual M151:

```text
pref/switch default     9 / 529
pref/switch wide      526 / 529
visibility gates      537 / 537
multi-surface files          378
```

5. **The renderer is sufficient for current findings.** `Navigator.install` has 5 locations and `WebGLRenderingContextBase.texElementImage2D` has 4; both render completely. Markdown shows six and then writes `and N more`. HTML keeps six.

### 31.3. One code item still worth fixing soon

#### `[Stable]` no longer reported false Breaking, but still repeated 164 Behaviour rows

M143 → M147 wide contained:

```text
196 ipc_stability_changed findings
 32 container rows
164 method/field rows whose deltas were only {stable, position}
```

All 164 child rows came from three files and retold the same event—the container losing `[Stable]`:

```text
image_capture.mojom          74
hid.mojom                    66
video_capture_types.mojom    24
```

This was no longer as harmful as before:

- it was not in Breaking;
- it did not claim the ABI ordinal had changed;
- it was roughly 2% of the 8,044-row wide report.

Within the Behaviour bucket alone, however, 164 rows is more than 11%. A single upstream annotation edit still consumed too much reading attention. Given the early-warning radar goal, this was **the code item with the clearest yield to do next**.

An approach sufficient for the purpose, with no large redesign:

- the container emits one `ipc_stability_changed` row;
- a child whose `stable`/`position` changed only because the container lost or gained `[Stable]` emits nothing of its own;
- a child still emits when its raw type, explicit ordinal, or lexical position genuinely changed.

With that fixed, the current correctness round could stop.

### 31.4. Tests missing for the new commit itself

`bee9e7d` changed five behaviors but added only one new test, for multi-surface membership. The existing tests kept the suite green without directly locking the other four boundaries.

Four small regressions were needed:

1. a test that goes through `cmd_run`, or a helper that builds `Scope`, asserting that both coverage sides are actually passed;
2. `absent ↔ compiled` guards produce no row while `compiled ↔ not_compiled` still does;
3. a guard move creates no inherited-only fan-out;
4. Markdown and HTML both render a finding with 4–5 locations.

This was cheap and worth doing. The history already contained three instances of “the capability exists at the front door and the real pipeline does not use it at the back”; locking boundaries matters more than raising the count of generic tests.

### 31.5. Items to know and document rather than build extractors for

#### Grammar not yet modeled

M151 contained declaration classes the tool did not turn into facts:

| Known scope | Count |
|---|---:|
| WebIDL callback definitions | 85 |
| WebIDL typedefs | 144 |
| WebIDL `includes` relations | 200 |
| Mojo `feature` blocks | 18 |
| Mojo constants | 311 identities |

There were real missed examples, such as `LanguageModelMessageValue` changing its underlying union in M143 → M147 and `kWebNNDirectML` disappearing in M151. The current goal, however, does not require parser completeness.

The reasonable decision at this point:

1. add this list to the “What the tool does not read” section of the README and the report;
2. change any wording that still implies the input is “complete” to “bounded and measured”;
3. write an extractor only when a real review proves that the surface regularly produces actionable findings.

If only one is ever chosen, `includes` or `typedef` has clearer yield than callbacks. There is no need to do all five at once.

#### Parser edge cases with no current yield

- a variadic overload may be called `added` rather than `shadowed`;
- the parameter splitter does not understand commas inside quoted defaults;
- the literal normalizer does not fully understand escaped quotes.

None of the four real milestones hit the failing shape. Record them in the backlog and add fixtures when the parser is fixed; they need not block use of schema 39.

### 31.6. Infrastructure that can wait

- `docs/figures.json` is sufficient for the headline numbers. A Chromium download in every commit hook is unnecessary.
- The artifact-to-report oracle can be a manual step run once before a large documentation publish.
- HTML caps at six locations and does not write `N more`; the largest current changed group is five, so this is not yet a real defect.
- Line numbers do not need to be compared as semantic data; keeping them only to guide the reader is the right call.
- Neither 100% coverage nor an automated release verdict needs to be pursued.

### 31.7. Two “new” labels in default were not fully certain—but not a serious defect

`cmd_run` passes old coverage now, but scoring deliberately does not downgrade every addition merely because the old-side default scan read little. Doing so once dropped `New surface` from 1,240 to 0 and made the report useless.

The remaining consequence: default M148 → M151 calls `IncomingCallNotifications` and `Prerender2FallbackPrefetchSpecRules` added or new-on-by-default, while the wide scan sees the older declaration and classifies them accurately as a move and a default flip.

For early detection this is still a useful signal: a real change exists, and the wide scan corrects the story. The score does not need to change now. For tighter wording, the default report could say “newly observed in this scan” instead of the absolute claim “did not exist before.”

### 31.8. Recommended stopping point

Three items were enough to close this round:

1. merge or suppress the 164 stability-only child rows;
2. add the four boundary regression tests for `bee9e7d`;
3. publish the five unread grammar classes in user-facing documentation.

After that, **stop expanding against hypothetical audit findings**. Use the tool on real uprevs and record:

- which top findings helped discover something real;
- which false positives wasted a reader's time;
- which important changes people found and the tool missed.

Add a new extractor or scoring rule only when there is a real example with a clear expected action. That is how an early-warning tool is tuned; turning it into a complete parser is not.

#### Final verdict for schema 39

> **Usable as it stood. No known false Breaking regression and no current overload location hidden. The code item most worth fixing was the 164 repeated stability child rows; the unread grammar needed documenting, not resolving. After one small fix, four boundary tests, and a scope note, the project was “good enough” for its early-warning goal and should shift from audit-driven expansion to learning from real uprevs.**

## 32. Final review of `f56bafa` — schema 40

### 32.1. Verdict

> **The three items Section 31 held open were done correctly. Schema 40 has no known serious runtime defect for the early-detection goal. The audit round can close after tightening two small test assertions; no new extractor, scoring rule, or infrastructure is needed at this point.**

Baseline verified:

```text
HEAD / origin/main   f56bafa
schema               40
history              77 / 77 commits
Python 3.14           366 / 366 tests pass
Python 3.9            366 / 366 tests pass
```

### 32.2. The stability duplication is genuinely closed

The implementation fixed this at two levels:

- `stable` left the meaningful attributes of methods and fields; the promise belongs to the container;
- `position` became paired evidence: a delta appears only when both sides have a position.

Full schema-40 matrix:

| Pair | Target | Findings | Breaking | Behaviour | Stability rows | Member stability rows |
|---|---|---:|---:|---:|---:|---:|
| M143 → M147 | default | 4,023 | 339 | 923 | 0 | 0 |
| M143 → M147 | wide | 7,880 | 1,152 | 1,279 | 32 | **0** |
| M147 → M148 | default | 1,273 | 79 | 252 | 0 | 0 |
| M147 → M148 | wide | 2,250 | 276 | 330 | 0 | 0 |
| M148 → M151 | default | 3,022 | 276 | 469 | 0 | 0 |
| M148 → M151 | wide | 6,064 | 798 | 696 | 0 | 0 |

Breaking rows carrying `position` with no type, ordinal, or mojo-kind evidence: **0 across all six runs**.

The main claims therefore reproduced:

```text
stability findings        196 → 32
member repetitions        164 → 0
Behaviour M143→147 wide 1,443 → 1,279
```

One sentence in the commit message is not literally true: “a member no longer carries `stable` at all.” The extracted fact still carries `stable` to preserve provenance; only the comparison allowlist stopped reading it. The implementation is better than that wording, and this is not a bug.

### 32.3. The scope documentation is sufficient

Both the README and the skill state explicitly:

- 85 WebIDL callback definitions;
- 144 typedefs;
- 200 `includes` relations;
- 18 Mojo feature blocks;
- 311 Mojo constants;
- two real missed examples;
- coverage counts files, not grammar;
- `_errors = 0` means no extractor threw, not that every declaration was recognized.

That is the level of transparency early detection calls for. Writing five extractors merely to raise a number is unnecessary.

### 32.4. Four boundary tests: two good, two that need tightening

Two tests lock the behavior correctly:

1. `absent ↔ compiled` guards produce no row, while `absent ↔ not_compiled` still does;
2. a guard or stability edit on a container does not fan out to its members.

The other two claim more than they prove.

#### The coverage test can stay green if `Scope` again receives only `to`

The test currently uses:

```python
source = inspect.getsource(cli.cmd_run)
call = source[source.index("Scope("):]
self.assertIn('"from"', call)
self.assertIn('"to"', call)
```

Replacing only the `Scope` call inside that string with a `to`-only version still passed both assertions, because the code **after** the call still contains `"coverage": {"from": ..., "to": ...}` in the report metadata; that `"from"` occurrence sits 3,129 characters later.

The runtime is correct, but the test does not lock the regression its name says it locks. The cleanest fix is to extract a small helper that builds `Scope` from two snapshots and assert on the returned object, or to mock `Scope` at `cmd_run` and capture the real argument. Source text should not be the thing under test.

#### The five-location test checks only four

The fixture creates exactly five locations, but the assertion iterates over:

```python
findings[0].change.locations[:4]
```

The fifth location (`x.idl:6` in the current fixture) is never checked. The renderer is correct today and real findings top out at five, but the test should assert `len == 5` and then check the whole list in both Markdown and HTML.

Neither fix needs a schema bump, and neither blocks use of schema 40. They only preserve the most important lesson of seven review rounds: a test must prove behavior at the boundary, not merely look as though it is proving it.

### 32.5. Stopping point

After tightening those two tests:

- close the audit;
- use `default` for fast early warning;
- use `wide` when the story needs to depend less on sampling;
- keep a person checking the evidence behind important findings;
- open a new extractor or rule only when a real uprev shows an actionable missed change.

The variadic lexer, escaped quotes, the five grammar extractors, a full Chromium fetch in CI, and 100% coverage are all unnecessary right now.

> **Final conclusion: the schema-40 code reached the point of knowing enough. What remains is fixing two preventive tests, not continuing to expand product scope.**

## 33. Closure review of `a4f13ec` — audit closed

### Results

The two weak tests from Section 32 were fixed correctly, and the warning about the scope of `PAIRED_ATTRS` was fenced. The commit changes no runtime semantics; it splits out a seam so that existing behavior is tested directly.

```text
HEAD / origin/main   a4f13ec
schema               40
history              78 / 78 commits
Python 3.14           368 / 368 tests pass
Python 3.9            368 / 368 tests pass
```

#### Coverage boundary

`scope_for(old, new)` takes two real snapshots. The test no longer reads source text; it checks both directions:

```text
old 1%, new 100%   removal 100% / addition 1%
old 100%, new 1%   removal   1% / addition 100%
```

Drop the `from` side and the mirrored result disappears, so the test fails. This is the right behavioral seam for the “the data model knows but the pipeline does not pass it” defect.

#### Renderer boundary

The fixture creates exactly five overload locations, asserts a count of 5, and checks every location in both Markdown and HTML. The fifth location no longer sits outside the assertion.

#### `PAIRED_ATTRS` scope

A test pins the owner set of `position` to exactly:

```text
mojo_method
mojo_field
```

The same test still proves that a position change is reported when both sides carry evidence. If a new kind reuses the name `position` with a different meaning, the suite forces whoever adds it to make a policy decision instead of silently inheriting the Mojo rule.

### Final verdict

No finding in the current audit round remains to be fixed.

- Schema 40 is usable for early detection and manual triage.
- The known scope is published.
- The full real-version matrix has been run.
- The boundary tests now prove behavior rather than inspecting the shape of source.
- Expanding the parser purely to chase completeness is unnecessary.

From here, reopen the audit only when a real uprev produces one of three kinds of evidence:

1. a top finding is a false positive that wastes a reader's time;
2. a genuinely important change is missed by the tool;
3. the output or evidence is not enough for a triager to check the source.

> **Audit closed at `a4f13ec`, schema 40. The next step is to use the tool, not to keep fixing against hypothetical completeness.**

## 34. Review of `bc472be` … `25745ed` — the provenance stage

> Reviewed: August 28, 2026
> Baseline: commit `25745ed`, schema `40`, 89 of 89 commits
> New since the closure at `a4f13ec`: 11 commits, of which 6 are the provenance stage
> Verified on: Python 3.14.6, 458 of 458 tests pass; real `M148 → M151 default` data throughout

The audit was closed at `a4f13ec` on the understanding that it would reopen when a real uprev produced evidence. It is reopened here for a different reason: a substantial new stage was added, and it is the first stage in the tool that fetches from a third party and asserts a causal claim.

`chromedrift/enrich/gerrit.py` (1,559 lines) and `chromedrift/serve.py` (255 lines) answer a question the two trees cannot: *who made this change, and what were they fixing.* This section reviews that stage and nothing else; the earlier verdicts on extraction, diffing and scoring are unchanged.

### 34.1. What the stage does, and why the design is sound

The chain is four lookups, each of which narrows the previous one:

```
fact  ->  the file that declares it
      ->  every merged CL that touched that file between the two versions
      ->  the CLs whose diff of that file names, or introduces, this identifier
      ->  the Bug: footer, and every other CL citing the same issue
```

Three design decisions are worth recording because they are the difference between a useful answer and a plausible one.

**The file is a candidate generator, not an answer.** 510 merged CLs touched `runtime_enabled_features.json5` in the M148 → M151 window. Handing a reader 510 CLs is worse than handing them none, so the file only produces candidates and the candidates are filtered by what their diffs actually contain.

**Six verdicts, ranked, never summed into a score.** `introduced` > `exact` > `moved` > `declares` > `described` > `crowded` > `touched`, with the last two fenced below `CITES` and printed under a sentence saying they are leads. This is the same discipline the rest of the tool follows — stop at the evidence, label its strength, do not average it into a number that hides which kind it was.

**`introduced` is the strongest idea in the stage.** Every other verdict asks whether a CL *touched* the declaration, which any CL that reformatted the file satisfies. `introduced` asks whether the CL's added lines carry the value the fact ended up with. The report already held both states of every changed declaration and had never spent them. That is a genuine observation, not a heuristic bolted on.

The stage is also correctly scoped. It never runs during `run`, so a report is complete and readable without the network; the page probes `/api/ping` once and stays static if nothing answers; and nothing about `report.html` on a disk changed.

### 34.2. The claims reproduce on real data

Every headline number in README §8 was re-measured against the cached M148 → M151 `default` run. They hold.

| Claim | Reproduced |
|---|---|
| The top 150 findings touch 56 distinct files | 56 |
| `AndroidCaptureKeyEvents` resolves to CL 7885356 | yes, live through the server |
| `TokenError.url` resolves to CL 7982397 `introduced` | yes, `1 of 13` |
| `border_offset` Vector2d → Vector2dF resolves to CL 7757059 | yes |
| The `_enclosing_span` rule picks 1 of 510 on `runtime_enabled_features.json5` | yes, CL 7895296 |
| A row always answers | 60 of 60 enriched rows carry a CL, 0 leads-only |

Verdict distribution over those 60 rows: 37 `introduced`, 24 `exact`, 11 `declares`, 2 `described`. **52 of 60 rows resolve to exactly one CL.**

Spot-checking `introduced` against the delta it was derived from is the sharpest available test of whether the verdict means anything, and it survives it:

```
type ["gfx.mojom.Vector2d" -> "gfx.mojom.Vector2dF"]
  CL 7757059  VT: Avoid transform rounding in style tracker; instead do it in cc.

response ["DeviceAttributeResult result" -> ""]   (five methods)
  CL 7957318  Refactor Device APIService to use mojom result<T, E>

params gained pending_remote<...DownloadObserver>
  CL 7896445  [3/3] Pass download progress observers dynamically in WebPlatform APIs
```

Five `DeviceAPIService` methods resolving to one refactor CL is the correct answer, not five coincidences. The stage does what it says.

### 34.3. The one layer that no test touches

Seven mutations were applied to the module, each reverting a decision the commit messages or README present as deliberate. The suite was run from a cleared `__pycache__` each time.

| Mutation | Suite |
|---|---|
| Count a `{"a":…,"b":…,"common":true}` reindent block as a real edit | **458 pass** |
| Ignore `{"skip": N}` blocks | **458 pass** |
| Never follow a rename, so `moved` can never be reached | **458 pass** |
| Let the container token earn `exact` | 2 failures |
| Take the window from the tag date instead of `Cr-Branched-From` | 1 failure |
| Believe a 500-row page instead of splitting the window | 2 failures |
| Sort citations oldest-first | 2 failures |

The boundary is exact. Everything above the wire format — matching, windowing, paging, ranking, the leads/citation separation — is locked. **`_blocks`, the function that turns Gerrit's diff JSON into lines, is never called by any test**, and neither is the rename follow in `_diff`. No fixture anywhere in `tests/` contains a `common` or a `skip` block.

That matters because README §8 lists four "confident wrong answers" as found and fixed, and three of them live in exactly that unguarded function:

- a reindent counted as an edit, which made a reformatting CL an `exact` match for every declaration in the file — 49 such blocks in a 2,329-diff sample;
- `{"skip": N}` ignored, which silently shortened the file and made a renamed file answer with no evidence;
- the rename follow itself, which is the whole of the `moved` verdict.

Each is a one-line condition. Each can be reverted today with the suite green. This is the project's own recurring failure mode, and the earlier rounds of this audit named it: the fix lands, the reasoning is written down well, and the invariant is not locked. A `_blocks` fixture with one `ab`, one `a`/`b`, one `common:true` and one `skip` block, asserted against the expected `(line, state)` sequence, closes all three at once and costs about twenty lines.

### 34.4. The batch path described everywhere does not exist

`gerrit.enrich()` has exactly one production caller: `serve._State.resolve`, which passes `top=1`, silences the log with `log=lambda m: None`, and discards the return value. `cmd_run` never calls it.

The consequence is that the module's run-level disclosure is computed and thrown away. `enrich()` returns `failed_fetches`, `incomplete_files`, `capped_files`, `issues_restricted`, `findings_leads_only`, `files_left_to_descriptions` — none of these names appears anywhere else in `chromedrift/`. The ten `log()` lines that report them, including

```
! gerrit: N fetch(es) failed and were read as no evidence; a finding may
  have a CL this run did not see.
```

reach no one. That line exists because the module docstring says turning a network fault into a confident "no CL found" is the one thing the stage is not allowed to do. In the shipped path, a rate-limited fetch does exactly that, silently.

The missing caller has a name. `why` is referenced five times — in `serve.py`'s module docstring, in `cmd_serve`'s own docstring ("The complement of `why`, not a replacement"), in `cmd_check`'s user-visible failure text (`" (only \`why\` needs it)"`), and in the report page's own JavaScript, which tells a reader of a static report to *"Re-run `why` with a higher `--gerrit-budget`."* Neither the command nor the flag exists; `git log -S` shows `add_parser("why"` was never added. The three flags named in `enrich()`'s log strings — `--gerrit-budget`, `--gerrit-max-cls`, `--gerrit-issues` — do not exist either. The real ones are `--click-budget` and `--issues` on `serve`, and `max_cls_per_file` is not exposed at all.

This is a design that was fully thought through and then only half wired. The markdown renderer already prints provenance; the summary dict is already shaped for `report.meta`; the budget ordering in `spend_order` is written for a many-file batch and is nearly pointless for a one-row click. Either add the command, or delete the batch scaffolding and the five references to it. The current state tells a reader to run something that will not run.

### 34.5. `cl_read`: the denominator disclosure that never reaches the page

`gerrit.py` sets `block["candidates_read"]` when `--gerrit-max-cls` trims a file's CL list. `html.py::_to_rows` never maps it to `row["cl_read"]`. The key is in `PROVENANCE_KEYS` and the page's JavaScript reads `f.cl_read` in two places; it is always `undefined`. `git log -S 'row["cl_read"]'` returns nothing — the consumer was written for a producer that was never wired up.

Measured on the real run, for the one finding declared in `runtime_enabled_features.json5`:

```
block: candidates 510, candidates_read 500
report.html:  "1 of 510 merged CLs touched this file"
report.md:    "(1 of 510 merged CLs touched this file)"
```

510 CLs were found; 500 were read; the ten oldest were never fetched. Both artifacts state the larger number as the search's denominator and omit the trim. README §8 promises the opposite in as many words: *"the panel prints both numbers: 510 merged CLs touched this file · 500 of them read."*

The code comment beside `total_found` names this defect class itself — *"which is the one kind of rounding this stage is not allowed to do"* — and fixes the half that was noticed. The other half remained: a reader is now told 510 were searched when 500 were. The fix is one line in `_to_rows`.

### 34.6. One finding, several CLs: the list is right, its ceiling is not disclosed

A change is often not one CL. A flag that flips `disabled -> enabled` may have been launched, reverted, relanded, reverted again and relanded, and the diff between two tags shows only the endpoints. The stage handles this correctly in principle: `_prune` keeps every hit that names the fact, not the best one, and `_compact` carries Gerrit's own `revert_of` and `cherry_pick_of_change` so the chain is legible rather than a list of similar subjects.

Measured over the top 150 of the M148 -> M151 `default` run: **28 of 150 findings carry more than one CL**, and the reconstruction is correct where it matters. `NtpComposebox` returns the whole arc:

```
2026-06-29  CL 7791453  [next] Launch Omnibox and NTP Next features
2026-06-30  CL 8017587  Revert "..."                          [reverts 7791453]
2026-07-09  CL 8027107  Reland "..."                          [reverts 8017587]
2026-07-10  CL 8071179  Revert "Reland ..."                   [reverts 8027107]
2026-07-29  CL 8092074  Reland "Reland ..."                   [reverts 8071179]
```

There is a second layer above it. The issue block lists every CL citing the same bug, which reaches past the window: for the same row it shows the `[M151]` and `[M152]` merge-backs and a later revert that the file search cannot see. That block is the right answer to "what is the whole story", and it **discloses its own ceiling**: *"11 CLs cite it, newest 8 shown · 2026-06-30 → 2026-08-05"*.

The CL list directly above it has the identical ceiling and does not disclose it. `_prune` returns `kept[:8]`, and the panel header prints `f.cls.length` against the candidate pool:

```
NtpComposebox:  19 candidates, 15 matched, 8 shown
report.html:    "8 of 19 merged CLs touched this file"
report.md:      "(8 of 19 merged CLs touched this file)"
```

Both formats state the shown count against the candidate count, so 8-of-19 reads as "8 of the 19 candidates matched". Fifteen matched. Seven were discarded, and nothing on the row says a list was cut. The issue block one line below proves the project already knows how to word this.

Two rules do the discarding, and they fail in opposite directions:

**The cap drops the oldest.** `kept.sort(key=lambda h: (strength(h["match"]), _neg_date(h["date"])))` is newest-first, so the eight survivors are the eight most recent. For a citation that is right — the last CL to touch a line is usually the one wanted. For a revert/reland chain it is backwards: the origin is the oldest entry. `_prune` already contains this exact reasoning, but only in the `crowded` branch, where the comment says *"a history read backwards is not a history"* and reverses the order. The strong branch, which is where multi-CL chains actually live, never got it. Here the launch CL survived only because its date happened to fall inside the newest eight; `[ntp-composebox] Add feature flag to switch to ntp-composebox fork` (2026-05-13, `exact`) did not.

**A stronger verdict deletes every weaker one.** When any `introduced`/`exact`/`moved`/`described` hit exists, all `declares` hits are dropped. Across the top 150 that removed every `declares` CL from **18 findings, 40 CLs in total**. As noise control on a single-cause row it is right — an `exact` does make a `declares` redundant. On a multi-CL row it is not, because a CL that edited the declaration's body is a contributor, not a weaker copy of a different CL.

Both are cheap to fix and neither changes a verdict:

- print the matched count, not the shown count — `"15 of 19 matched, newest 8 shown"`, the wording the issue block already uses;
- when a row keeps more than one CL, order it oldest-first, as `crowded` already does, or keep the newest four and the oldest four rather than the newest eight;
- keep `declares` hits on a row that already has several strong ones, ranked below them, instead of dropping them.

**A related precision risk, measured and found small.** Matching is plain substring, so a token that is a prefix of a longer real identifier collects that identifier's CLs: `kNtpComposebox` matches a line declaring `kNtpComposeboxFork`, verified directly against `_match`. 17 of the 792 feature-flag findings in this run have a name that is a substring of another flag's name in the same run. The cost, however, is almost nothing: re-running the whole top 150 with a word-boundary test in place of substring containment changes **201 CLs to 200**, on one finding, with the same 150 of 150 resolved. It is worth hardening — the boundary test can run only on lines the existing substring prefilter already accepted, so it costs nothing measurable — but it is not what is losing CLs today. The cap and the `declares` rule are.

### 34.7. Smaller findings

**`_slug` uses `hash()`, so a cache filename is not reproducible.** A term longer than 120 characters falls to `safe[:100] + "_" + str(abs(hash(text)) % 10 ** 8)`, and `hash()` on a `str` is salted per process. Three runs, same input:

```
..._OR_message__OnScriptLoad_15578263
..._OR_message__OnScriptLoad_24029225
..._OR_message__OnScriptLoad_64166726
```

Reachable through `_by_message`, whose query expression exceeds 120 characters whenever its three longest tokens total about 80. The effect is that those entries never hit the cache and the directory grows one file per run. Declaration paths are safe today only by luck: the longest in the M151 `wide` snapshot is 117 characters. `hashlib.sha1(text.encode()).hexdigest()[:8]` fixes it and costs nothing.

**A CL with no date sorts as the newest.** `_neg_date("")` returns `""`, which sorts first in the ascending sort that `_prune` and `_last_resort` use, and first means newest there. An undated CL therefore displaces genuinely newer ones at the head of the citation list. Rare, since Gerrit returns `submitted` for merged changes, but it is an inversion rather than a degradation.

**`--refresh` fetches every diff twice.** `enrich()` prefetches the plan through a thread pool and then calls `_diff` again in the sequential scan; both pass `refresh`, and `_get_json` skips the cache when it is set. Latent only — no CLI path reaches `serve` with `refresh=True` — but it doubles the request count and the 429 exposure for anyone calling the API directly.

**`_diff`'s docstring is inaccurate in a way that will mislead.** It says "the file as this CL left it", but `_blocks` emits the union of both diff sides: for a real edit block the `a` lines are appended, then the `b` lines. The brace-depth scan in `declaration_span` therefore walks an interleaved sequence. It happens to work — Gerrit emits complete replaced runs per side, and the 60-line cap bounds the damage — but a maintainer reasoning from that sentence will get line indices wrong.

**`container_for`'s docstring is now stale.** It states the container "can only ever reach `declares` … and never `exact`". `_match` adds the container to `search`, which the `introduced` loop also uses, and `introduced` outranks `exact`. The behaviour is intended and produces the right answer on `TokenError.url`; the sentence describing it is no longer true.

### 34.8. Documentation drift, and the tests that used to prevent it

Six test classes were removed across the last four commits, on the stated ground that they check "how documents are written rather than whether what they say is true". For four of them that is correct: frontmatter character limits, body line counts and table-of-contents depth cannot fail in a way that means the tool is wrong, and removing them is right.

Two were in the other category. `TestTheDocumentedSourceMapStillHolds` checked whether a stated number was true, and its own docstring made the argument: *"a reader who checks one and finds it wrong stops trusting the ones they cannot check, like the coverage tables."* It caught a real drift in `fdadffc`, the commit immediately before the series that removed it. `TestTheDocumentedFiguresStillHold` held README prose to `docs/figures.json`.

The drift returned at once. README §12's source map, which §11 lists as an invariant — *"The source map in §12 must match the source"* — is now stale in 4 of its 15 rows:

```
report/    1,861 stated   2,469 actual   +608
enrich/      805          1,753          +948
serve.py     200            255           +55
cli.py       763            738           -25
```

The header count of "11,748 lines" is short by about 1,800. Separately, the figure quoted three times as *"62 CLs touched `content_features.cc`"* measures 72 on the same window today.

None of these numbers changes what the tool does. They are worth fixing for the reason the deleted test gave, and because the same commit series that removed the checks is the one that introduced `why`, `--gerrit-budget` and `--gerrit-max-cls` into user-visible strings for things that do not exist. That is not a coincidence; it is what the checks were for.

### 34.9. Verdict

The provenance stage is a real advance and it works. It resolves 60 of 60 top findings on live data, 52 of them to a single CL, and the `introduced` verdict earns its rank — it identifies the CL that made the change rather than one that stood near it. The evidence ladder never collapses a lead into a citation, the disclosure discipline in the code is the same one the rest of the tool follows, and the decision to keep it out of `run` is correct.

What it needs before it can be relied on is smaller than what it already does:

1. **Test `_blocks` and the rename follow.** Three of the four defects the README presents as fixed are currently revertible with a green suite. One fixture closes all three.
2. **Say when a CL list was cut.** A row that matched 15 CLs and shows 8 prints "8 of 19", and the cut takes the oldest — the origin of a revert/reland chain. The issue block directly below it already words this correctly.
3. **Decide what `why` is.** Either add the batch command the code, the help text and the report page all reference, or remove those references and the run-level summary that has no consumer. As it stands, a reader is told to run a command that does not exist, and a failed fetch is reported to nobody.
4. **Wire `cl_read`.** One line, and it stops both report formats from stating a denominator the search did not cover.
5. Replace `hash()` in `_slug` with a stable digest; treat an empty date as oldest, not newest.
6. Refresh the source map and the `62` figure, and restore the two consistency tests that were checking truth rather than form.

Items 1–4 are the ones that affect what a reader believes. None of them requires a schema bump, and none of them changes a verdict already produced.

> **Reviewed at `25745ed`, schema 40. The stage is sound and measurably correct; its diff parser is unguarded, its batch half is unbuilt, and two of its lists state a count they did not cover.**

## 35. Review of `71cba61` — the Section 34 fixes

> Reviewed: August 28, 2026
> Baseline: commit `71cba61`, schema `40`, 90 of 90 commits
> Verified on: Python 3.14.6, 474 of 474 tests pass; the same real `M148 → M151 default` data as Section 34

One commit answers Section 34. Each claim was re-measured rather than read, and each fix was reverted to see whether a test objects.

### 35.1. What holds

**The diff parser is guarded now.** All three mutations that were green in Section 34 fail:

| Mutation | Section 34 | Now |
|---|---|---|
| Count a `common: true` reindent as a real edit | 458 pass | **1 failure** |
| Ignore `{"skip": N}` blocks | 458 pass | **1 failure** |
| Never follow a rename, so `moved` dies | 458 pass | **1 failure** |

`TestGerritsDiffIsReadAsGerritMeansIt` holds all four block shapes and the rename, which is the fixture the section asked for.

**Both counts reach both reports.** Re-rendered from the current code:

```
report.html   1 of 510 merged CLs touched this file · 500 of them read
report.md    (1 of 510 merged CLs touched this file, 500 of them read)

report.html   15 of 19 merged CLs touched this file · newest 12 shown
report.md    (15 of 19 merged CLs touched this file, newest 12 shown)
```

The row now separates three claims that were one: how many touched the file, how many a diff tied to the fact, how many are printed.

**The chains are whole.** `NtpComposebox` reads forward, and both CLs Section 34 identified as lost are back — CL 7843034, the flag's origin, cut by the old cap, and CL 7909551 `declares`, deleted by the strong-hit rule:

```
2026-05-13  exact     7843034  [ntp-composebox] Add feature flag to switch to fork
2026-06-10  declares  7909551  [ntp-composebox] Enable NTP composebox fork by default
2026-06-29  exact     7791453  [next] Launch Omnibox and NTP Next features
2026-06-30  exact     8017587  Revert "…"                        [reverts 7791453]
2026-07-09  exact     8027107  Reland "…"                        [reverts 8017587]
2026-07-10  exact     8071179  Revert "Reland …"                 [reverts 8027107]
2026-07-29  exact     8092074  Reland "Reland …"                 [reverts 8071179]
2026-08-07  exact     8187722  Remove obsolete useNtpComposeboxFork
```

Rows holding more than one CL went from **28 of 150 to 39 of 150** at a diff budget of 1,600; the figure moves with the budget, so it is a measurement of this run rather than a constant.

**The rest.** `_neg_date("")`, the `--refresh` double fetch, and the `why` / `--gerrit-budget` references all revert to a failing test or are gone from the source. The `--refresh` test is measured at the right boundary: it stubs `_http_get`, keeps a real cache directory, and asserts three diff requests for three CLs. The first version of it counted `_get_json`, which both passes call once by design — the self-correction in the commit is the right one.

### 35.2. `search_incomplete` is written and read by nobody

`serve._warn` records two things on the row. One of them is consumed:

```python
if failed:
    block["failed_fetches"] = failed          # -> row["cl_failed"] -> the panel
if summary.get("incomplete_files"):
    block["search_incomplete"] = True         # -> nothing
```

`search_incomplete` appears exactly once in the tree, at `serve.py:156`. It is not in `_to_rows`, not in `PROVENANCE_KEYS`, and not in the page script. A lookup whose candidate list could not be proven complete — Gerrit's 500-row cap holding even split by day — records that fact and drops it.

This is the same defect the commit fixed for `cl_read`, one commit later, in the code that fixed it. `cl_read` survived three commits because a producer and a consumer were written at different times and nothing tied them together; `PROVENANCE_KEYS` exists precisely to be that tie, and the new key was not added to it.

### 35.3. A failed fetch is disclosed on one row shape out of four

The commit's own statement of the problem is right: *"a dropped fetch then reaches the reader as 'no CL edits this line', which is the one thing this stage exists never to say."* The fix reaches only the case where the whole lookup collapsed.

Rendering the real page script over four constructed rows, each carrying `cl_failed`:

| Row | Panel says |
|---|---|
| pool 0, no CLs | **"2 requests to Gerrit failed … this is not a finished search"** |
| pool 13, no CLs | "No CL among the 13 that touched this file can be tied to this identifier." |
| pool 13, `touched` leads | "No CL mentions this identifier. These are the newest CLs that touched the declaring file." |
| pool 13, an `exact` CL | *(nothing about the failure)* |

Only the first warns, and it is the shape where the *search* request failed — so there were no diffs to lose in the first place. The three that stay silent are the shapes a partial failure actually produces: the search succeeded, some of its diff fetches did not, and the row then reads as a completed scan. The third is the most likely of all, because `_last_resort` guarantees that any row with candidates gets leads rather than an empty panel.

The warning is a property of the lookup, not of how the lookup happened to end, so it belongs above the panel on every shape rather than inside the innermost branch of the empty one.

### 35.4. `_slug` is the one fix with no test

The commit closes with *"Mutation-checked: all ten revert to a failing test."* Ten do. `_slug` is an eleventh change, listed in the same commit under measured smaller fixes, and reverting it to `abs(hash(text))` leaves **474 of 474 green**. No test names `_slug`.

It is a pure function of one string, so the test is a line: assert that a term over 120 characters produces a known digest, which a salted hash cannot. Worth adding for the same reason the fix was worth making — the failure is silent, and the claim in the commit currently covers it without having checked it.

`KEEP_MAX = 12` is also untested; reverting it to 8 leaves the suite green. That one is acceptable and probably right: the invariant is that a cut list says it was cut, and that is locked by three tests. The cap value is a tuning choice, and pinning tuning choices is how a suite becomes a record of what the code says rather than of what it must do.

### 35.5. One trade the fix introduced

The read pass now takes the cache unconditionally:

```python
_Scanned(_diff(cl, path, cache_dir, False, log))
```

That removes the double fetch, which was the point. It also means that under `--refresh`, a warm-pass fetch that failed leaves no new cache entry, and the read pass then serves a stale one from an earlier run — under a flag whose contract is to ignore caches. Narrow, and better than fetching everything twice, but it is a second place where a failed fetch turns into data that looks fine.

### 35.6. Verdict

Section 34's three main findings are closed, and closed the way this project closes things: measured before and after, and locked by a test that fails when the fix is removed. The diff parser went from three silent reverts to none. The chain reconstruction is now the strongest part of the stage — it reads a launch, two reverts and two relands forward, with Gerrit's own revert links, and says what it left out.

What is left is small and of one kind: a disclosure that is computed and not delivered.

1. Map `search_incomplete` onto the row and into `PROVENANCE_KEYS`, or stop recording it.
2. Show `cl_failed` on every row shape, not only on an empty panel with an empty pool.
3. Give `_slug` its one-line test, and drop `_slug` out of the "all ten" claim until it has one.

> **Reviewed at `71cba61`, schema 40. The fixes hold under mutation and on real data. Two new disclosures repeat the defect they were written to fix: one has no consumer, the other reaches one row shape in four.**
