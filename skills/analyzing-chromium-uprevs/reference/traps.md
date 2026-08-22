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
- 9. A platform-gated declaration is not ours, and it may say so only by its path
- 10. A Mojo ABI break has to break it for somebody
- 11. A new web API can be unreachable
- 12. A removed switch fails silently; a removed pref may orphan data

Traps 1 and 3 to 5 are about feature flags, 2 and 6 about declarative files,
7 and 8 about running the tool. Traps 9 to 12 are the other surfaces, which
carry the highest severities the tool reports: at M148 → M151, 227 of the 283
Breaking rows are Mojo or web API.

## 1. Retired flag read as removed feature

**Symptom:** a `base::Feature` or Blink runtime feature disappears; the diff
reads as lost capability.

**Reality:** Chromium deletes the flag once the outcome is settled. The state
the flag held *just before* deletion says which outcome that was.

**Evidence:** M148 → M151 Windows removed 145 flags: 72 that had shipped, 60
abandoned, 6 whose prior state is unreadable. M139 → M143 removed 202 Blink runtime features, 170 of which had
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

## 9. A platform-gated declaration is not ours, and it may say so only by its path

**Symptom:** a change scores 60 to 80 at the top of a Windows report, and the
thing it names is Android or ChromeOS.

There are two ways a declaration can be out of our build and neither is the
`#if BUILDFLAG(IS_WIN)` chain that trap 5 covers.

### 9a. A mojom attribute rather than a preprocessor line

**Reality:** mojom has its own build conditions, spelled as an attribute rather
than a preprocessor line:

```
[EnableIf=is_android]
struct AndroidPayload {
  int32 imei;
};

interface Renderer {
  [EnableIf=is_android] OnRegisteredFontsChanged();
};
```

Measured at M151: 256 declarations are `EnableIf=is_android` and 186 are
`is_win`. Conditions are inherited — a field or a nested enum inside an
Android-only struct is Android-only too.

**Check:** the tool resolves these now and scores them zero, the same as a C++
declaration behind `#if BUILDFLAG(IS_ANDROID)`. Before it did, `platform_state`
existed on four of the sixteen fact kinds and none of them were Mojo. Read
`platform_state.windows` on the finding, exactly as for a flag. A value of
`conditional` means the attribute names a build flag rather than a platform —
`enable_print_preview`, `webnn_enable_graph_dump` and 40 others — and is
undetermined, not ours-by-default.

### 9b. A directory excluded in BUILD.gn, with no guard anywhere

Chromium keeps whole platforms in their own directories and excludes them at
the build-system level, so **nothing inside them carries a guard at all**:

```
chrome/browser/flags/android/chrome_feature_list.cc   Android only
chrome/browser/ash/login/login_pref_names.h           ChromeOS only
ash/  chromeos/  ios/  fuchsia/  android_webview/  chromecast/
```

There is no `#if` for a preprocessor scanner to find. The path is the only
evidence there is, and it is conclusive.

Measured on a wide M148 → M151 run before this was read: **164 findings** were
declared under one of those directories and not one scored zero, topped by
`AndroidNewMediaPicker` at 75 points in **Behaviour change**. It bites only on
`wide`, because the default target set does not fetch those directories — which
means it bit exactly when the report was being used as a release gate.

**Check:** the tool resolves this now, into the same `platform_state` a guard
produces, and only when *every* declaration of the key is under such a
directory. Five keys at M151 are declared both inside and outside one, and
deduplication keeps the ChromeOS copy — so a per-file rule would take a real
preference out of the report. Three findings on that pair still score, all of
them correctly: they carry a second declaration in `components/`.

## 10. A Mojo ABI break has to break it for somebody

**Symptom:** 40 rows at 80 points saying "Mojo method signature changed
(ABI)", read as 40 runtime breakages in the next release.

**Reality:** both ends of a Mojo interface are compiled from the same tree.
The browser process and the renderer process of one Chromium build always
agree, because the generated bindings on both sides came out of the same
`.mojom` file. Between two stock versions nothing at runtime is talking across
that boundary at two different versions.

So an `ipc_signature_change` between M148 and M151 is a **build break for code
outside this tree**, not a runtime break — unless one of these is true:

- something ships separately from the browser and speaks the same interface
- an install can end up part-updated, so two versions run side by side
- there is out-of-tree code implementing or calling the interface, which is the
  usual case and the reason the severity is what it is

**Check:** say which of those applies before calling it a runtime break. The
tool cannot tell — it compares Chromium against Chromium, and a **Breaking**
row says a contract moved, not that anyone had signed it.

## 11. A new web API can be unreachable

**Symptom:** 347 rows of new web API surface, read as 347 new capabilities.

**Reality:** this is trap 1 on a different surface. Blink gates IDL members
with `[RuntimeEnabled=Foo]`, and `Foo` moves through the same three stages a
`base::Feature` does. The attribute alone settles nothing — a gate whose flag
already reached stable is an open gate.

Measured M148 → M151 on 220 added `idl_member` rows: 133 are reachable by a
page on arrival and 87 are not. The gate can also sit on the *interface* rather
than the member, which accounts for 51 of them.

**Check:** the tool resolves this now, into `web_api_added_live` and
`web_api_added_gated`, with `web_api_added` kept for the case where the gating
flag was outside what the run read. The same applies backwards:
`web_api_removed_gated` is a removal no page could reach, 32 of the 77 removals
on that pair.

## 12. A removed switch fails silently; a removed pref may orphan data

**Symptom:** `switch_left_scan` or `pref_left_scan`, read as low-priority
because nothing broke.

**Reality:** Chromium **ignores command-line switches it does not recognise**.
No warning, no error, no log line. A launch script, a test runner or an
enterprise deployment keeps starting the browser exactly as before, and the
flag it passes silently stops doing anything. This is the same failure mode as
`feature_string_renamed`, on a surface people rarely check.

A removed preference is different: the key in a user's `Preferences` file stays
on disk. Whether that matters depends on whether Chromium wrote a migration for
it, in `chrome/browser/prefs/browser_prefs.cc`.

**Check:** for a switch, search launch scripts and test automation for the
string — the tool cannot see either. For a pref, `browser_prefs.cc` is read on
a `wide` run and not on a `default` one, so run `wide` before concluding a key
was dropped without a migration. And read trap 2 first: on a `default` run,
100 of 141 vanished keys at M148 → M151 had simply moved.
