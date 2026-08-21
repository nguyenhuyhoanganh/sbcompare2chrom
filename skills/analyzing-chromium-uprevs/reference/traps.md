# Known traps

Each trap below produced a wrong conclusion against real Chromium data before
it was handled. Expect them; check for them before reporting any removal.

## Contents

- 1. Retired flag read as removed feature
- 2. Declaration moved, not removed
- 3. Macro migration invents thousands of changes
- 4. Macro migration silently renames features
- 5. Platform-divergent defaults
- 6. Declarative files declare more than ships
- 7. Bare milestone numbers drift
- 8. Mixed target sets and partitions produce plausible nonsense

## 1. Retired flag read as removed feature

**Symptom:** a `base::Feature` or Blink runtime feature disappears; the diff
reads as lost capability.

**Reality:** Chromium deletes the flag once the outcome is settled. The state
the flag held *just before* deletion says which outcome that was.

**Evidence:** M148 → M151 Windows removed 90 flags, split exactly 45 shipped /
45 abandoned. M139 → M143 removed 202 Blink runtime features, 170 of which had
been `stable`.

**Check:** read the prior state. `flag_retired_on` means behaviour is now
permanent and unremovable; `flag_retired_off` means the code is gone. Neither
changes behaviour at this uprev — which is why both are filed under
Housekeeping — but both break the build of anything naming the symbol, and both
silently kill any override that was setting the flag from outside the binary.

## 2. Declaration moved, not removed

**Symptom:** an entry vanishes from a file.

**Reality:** it usually reappears elsewhere, often behind a different flag.
M148 → M151 "lost" the route `SITE_SETTINGS_LOCAL_NETWORK_ACCESS`. It had not
been lost: Chromium was mid-migration and declared both versions of the page at
M148, each behind its own guard, then deleted the old one once the new guard
had shipped. Because `kLocalNetworkAccessChecksSplitPermissions` was already
enabled by default at M148, users were seeing the *new* page one milestone
before the old route disappeared from the file.

**Check:** search the whole tree for the key before reporting a removal, and
read the `guards` attribute on both sides. If it exists elsewhere, this is a
move, and the user-visible change happened whenever the controlling flag
flipped — usually earlier than either version compared. The tool groups these
fragments for you: that migration arrives as seven separate findings across
routes, gates, controls and flags, and the report's "Related changes, grouped"
section reassembles them.

## 3. Macro migration invents thousands of changes

**Symptom:** an entire file appears rewritten.

**Reality:** between M139 and M143 the `BASE_FEATURE` macro dropped its
string-name argument:

```cpp
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);  // <= M141
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);                      // >= M142
```

In `content_features.cc`, M139 has 170/170 declarations in the old form and
M143 has 12/187. A parser keyed on source text reports every feature as removed
and re-added. After normalizing `kFoo` → `"Foo"`, the true delta is 152
unchanged, 18 removed, 35 added.

**Check:** the tool handles this. If writing a new parser, key on the semantic
name, never the source text.

## 4. Macro migration silently renames features

**Symptom:** nothing — this one is invisible.

**Reality:** the two-argument macro derives the feature string from the
variable name. Where those disagreed, the Finch name changed with no edit:

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);   // lowercase r
// M143 - macro derives from the variable
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   feature string is now "FedCmIdPRegistration"                    // uppercase R
```

Every server-side field trial and `--enable-features` flag keyed on the old
spelling now does nothing. No compiler warning, no test failure.

A second real case: M139 declared
`BASE_FEATURE(kAccessibilityPopulateSupplementalDescriptionApi,
"kAccessibilityPopulateSupplementalDescriptionApi", ...)` — the author left the
`k` prefix inside the string. The macro migration corrected it, which is still
a rename with the same consequence.

**Check:** the tool pairs removals and additions sharing a C++ variable and
emits `feature_string_renamed`. Verify Finch configs and launch scripts
separately; those live outside the repository.

## 5. Platform-divergent defaults

**Symptom:** a feature reads as enabled, but not on the platform you ship.

**Reality:** defaults are wrapped in preprocessor conditionals:

```cpp
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
```

In `content_features.cc` alone, 14 of 187 features have platform-divergent
defaults.

**Check:** read `platform_state.windows`, never `default_state`. The platform is
fixed to Windows and is not selectable — reading the wrong one does not blur the
answer, it inverts it, so there is no option to get wrong. A value of
`conditional` means the guard depends on a non-platform build flag the tool
cannot decide — report it as undetermined rather than guessing.

## 6. Declarative files declare more than ships

**Symptom:** a settings page or entry exists in the declaration but users never
see it, or two competing versions both appear.

**Reality:** at M148 the desktop route table declared **both** pages during a
migration:

```js
if (loadTimeData.getBoolean('enableLocalNetworkAccessSetting')) {
    r.SITE_SETTINGS_LOCAL_NETWORK_ACCESS = r.SITE_SETTINGS.createChild('localNetworkAccess');
}
if (loadTimeData.getBoolean('enableLocalNetworkAccessSplitPermissions')) {
    r.SITE_SETTINGS_LOCAL_NETWORK = r.SITE_SETTINGS.createChild('localNetwork');
}
```

At M151 only the second survives, and
`kLocalNetworkAccessChecksSplitPermissions` — ENABLED at M148 — is gone
entirely. So Local Network Access was **not removed**; it moved to split
permissions, users already had it at M148, and M151 only retired the flag.

**Check:** never conclude a page exists or does not exist from a declaration
file alone. Follow the guard to its flag.

## 7. Bare milestone numbers drift

**Symptom:** two runs of the same command disagree.

**Reality:** `151` resolves to the newest stable release *at run time*.
`ServiceWorkerAutoPreload` is ENABLED in 143.0.7499.40 and DISABLED in
143.0.7499.194 — same milestone, reverted in a patch release.

**Check:** pin full versions for anything recorded in a ticket. Bare milestones
are for exploration only.

## 8. Mixed target sets and partitions produce plausible nonsense

**Symptom:** a run reports thousands of additions that look real.

**Reality:** the per-ref source cache is shared across target sets. A
`--target-set minimal` run inside a cache a previous `default` run populated
once produced a "minimal" snapshot containing the full 21,595 facts, inventing
roughly 20,000 phantom additions with no error and no warning.

**Check:** the tool now scopes extraction to the declared target set and
refuses to diff snapshots built from different ones. If you see
`cannot diff snapshots built from different target sets`, rerun with a
consistent `--target-set` or add `--refresh`.

The same trap applies to `--partition`, which is part of the snapshot cache key
for exactly this reason: a partitioned snapshot covers a fraction of the surface
and must never be reused as if it were a full run. A partitioned run is a
smaller question, not a cheaper answer to the same one — never use one as a
release gate, and say in the report which partitions were scanned.
