# Chromium 148 → 151: Downloads and Bookmarks

## 1. What this run looked at

| | |
|---|---|
| From | `refs/tags/148.0.7778.217` |
| To | `refs/tags/151.0.7922.138` |
| Platform | Windows. The comparison evaluates Windows build and runtime conditions only, and has no option to change that. |
| Areas requested | Downloads, Bookmarks |
| Declaration kinds requested | Feature flags, Mojo interfaces, WebUI controls and routes. Preferences and other kinds appear where they explain one of those three. |
| Decisions requested | All three: what the product must adapt to, what users will notice, and new capabilities. |
| Review directory | `out/review-downloads-bookmarks/` (request: `request.md`, full report: `review.md`, ledger: `review.json`) |
| Report used | `out/M148_to_M151_wide/report.json`, target set `wide`, no partitions, 6064 findings |
| Evidence fingerprint | `30277b7bb0496db1f0a0229226bc6c1c43daee9a29e8adf6ed8f90d58efd52ba` |
| Scope accounting | COMPLETE for the 154 selected items (19 events, 0 provisional). Whole index remains PARTIAL: 9278 of 9437 items belong to other areas and were not decided. |

Source links in the Evidence column follow the pattern
`https://chromium.googlesource.com/chromium/src/+/refs/tags/<version>/<path>#<line>`.

## 2. The changes

Rows are ordered by what this product has to do about them: work the fork must
absorb first, then what a user will notice, then capabilities that are only
available if the product asks for them. They are not ordered by the tool's score.

| Change | What it means | Evidence | Verify |
|---|---|---|---|
| The bookmarks side panel is rewritten from Polymer to Lit and split into app, header and row components | Every `.html` template under `side_panel/bookmarks/` becomes a `.html.ts`, and the toolbar splits across three new components. Any fork patch, test or UI automation that selects `#addCurrentTabButton`, `#deleteButton`, `#contextMenu`, `#editButton`, `#sortMenu`, `#viewButton` or a `#bookmark-<id>` row inside `power-bookmarks-list` will not find them. Polymer `[[…]]` bindings must be ported to Lit `${…}`. The row tree is also flattened: rows are now siblings in one virtualized list with an explicit depth, not nested elements. | 30 `webui_control` findings, e.g. `webui_control:side_panel/bookmarks/power_bookmarks_list/id:addCurrentTabButton` and `webui_control:side_panel/bookmarks/power_bookmarks_list_header/id:editButton` · from `chrome/browser/resources/side_panel/bookmarks/power_bookmarks_list.html:389` → to `.../power_bookmarks_app.html.ts:63` and `.../power_bookmarks_list_header.html.ts:37` | Not verified |
| `network.mojom.URLResponseHead.headers` becomes nullable | An IPC contract change on a struct every network consumer deserializes. Generated C++ makes the field optional, so product code that reads `URLResponseHead::headers` without a null check stops compiling. Chromium's own download path was already null-safe. This is a whole-tree task, not a downloads task. | `mojo_field:network.mojom.URLResponseHead.headers` · from `services/network/public/mojom/url_response_head.mojom:54` → to `:57` | Not verified |
| The bookmarks WebUI handler moves off `Browser*` to `BrowserWindowInterface` and the browser collections | `chrome::FindLastActiveWithProfile` and `chrome::FindBrowserWithTab` are replaced by `ProfileBrowserCollection::GetForProfile(...)->GetLastActiveBrowser()` and `GlobalBrowserCollection::GetInstance()->FindBrowserWithTab(...)`; the legacy pointer is now reached through `GetBrowserForMigrationOnly()`. The same substitution lands in `downloads_dom_handler.cc`, where `browser->window()` becomes `BrowserWindow::FromBrowser(browser)` and `browser->profile()` becomes `browser->GetProfile()`. Any fork code around these handlers must be ported, and the accessor name says the legacy `Browser*` is itself going away. | `file:chrome/browser/ui/webui/bookmarks/bookmarks_message_handler.cc` · from `chrome/browser/ui/webui/bookmarks/bookmarks_message_handler.cc:342` → to `:415` | Not verified |
| `BookmarksUI` becomes a `MojoWebUIController` with `chrome.send` still enabled | The base class of the `chrome://bookmarks` controller changes; a fork subclass or patch must change its own base initializer and include. `enable_chrome_send=true` keeps the existing message traffic working, so no runtime behaviour changes by itself. | `file:chrome/browser/ui/webui/bookmarks/bookmarks_ui.cc` · from `chrome/browser/ui/webui/bookmarks/bookmarks_ui.cc:176` → to `:180` | Not verified |
| Saving a page as MHTML switches from a duplicated file handle to a Mojo data pipe, and refuses to follow symlinks | The renderer no longer receives a writable handle to the target file; a `MHTMLDataPipeReader` on the download sequence drains a data pipe instead. `FLAG_NO_FOLLOW` is added, so a save through a symlink now fails rather than writing through it. A fork patch in this file will conflict substantially. | `file:content/browser/download/mhtml_generation_manager.cc` · to `content/browser/download/mhtml_generation_manager.cc:102` (file flags) and the added `MHTMLDataPipeReader` class | Not verified |
| Save-page quarantine stops passing the source URL for off-the-record saves | The quarantine callback becomes `OnceCallback<void(const GURL&)>` and `QuarantineItem` gains an `is_off_the_record` parameter, keeping the same suppression but deciding it at call time. Windows Mark-of-the-Web metadata is what this writes, and any fork patch here must adopt the new signature. | `file:content/browser/download/save_file_manager.cc` · from `content/browser/download/save_file_manager.cc:394` → to `:393` | Not verified |
| The bookmarks side panel now opens in compact view by default instead of expanded | The registered default of `kBookmarksViewType` changes from `ViewType::kExpanded` to `ViewType::kCompact`. A profile that never touched the view toggle sees the compact list after the upgrade; a profile that wrote the pref keeps its own value. This is the clearest end-user-visible change in the two areas. | `file:chrome/browser/ui/webui/bookmarks/bookmark_prefs.cc` · from `chrome/browser/ui/webui/bookmarks/bookmark_prefs.cc:25` → to `:25` | Not verified |
| Clearing downloads on `chrome://downloads` now permanently deletes items still being scanned | `RemoveDownloads` now also calls `Remove()` when the danger type is `DOWNLOAD_DANGER_TYPE_ASYNC_SCANNING` or `..._ASYNC_LOCAL_PASSWORD_SCANNING`. A user who clears the list while a file is being scanned loses that download instead of being able to undo it. No flag guards this. | `file:chrome/browser/ui/webui/downloads/downloads_dom_handler.cc` · from `chrome/browser/ui/webui/downloads/downloads_dom_handler.cc:565` → to `:569`; new test `RemoveDownloadsAsyncScanning` | Not verified |
| Downloads served by a service worker are no longer resumed through the in-progress download manager | The resume path returns early unless `params->skip_service_worker_interception()`, because resuming a service-worker-served download against the network factory would fetch unrelated bytes and corrupt the file; `DownloadResponseHandler` now records and propagates `was_fetched_via_service_worker`. A user resuming such a download gets a correct file. | `file:components/download/internal/common/in_progress_download_manager.cc` · to `components/download/internal/common/in_progress_download_manager.cc:475`; `file:components/download/internal/common/download_response_handler.cc` | Not verified |
| Bookmarks sync gains a no-op conflict resolution that keeps the local state | Two new branches on `MatchesBaseData` let a local deletion or a local edit win over a remote update that matches the base data, recorded as `ConflictResolution::kIgnoreRemoteNoOpUpdate`; `AckSequenceNumber` moves out of the common path so the pending local commit is not squashed. A synced user is less likely to see a rename or deletion reverted. | `file:components/sync_bookmarks/bookmark_remote_updates_handler.cc` · to `components/sync_bookmarks/bookmark_remote_updates_handler.cc:712` | Not verified |
| A new syncable `bookmark_bar.visibility_state` preference is added, and the `BookmarkBarEnabled` policy writes it | A three-state integer pref (`kAlwaysShow=0`, `kOnlyShowOnNtp=1`, `kAlwaysHide=2`) joins the existing boolean, and a new `BookmarkBarPolicyHandler` sets both from the policy. It is syncable, so it travels between devices. Code that reads only `bookmark_bar.show_on_all_tabs` will not see a user who picked "only on the new tab page" once `kNtpSimplificationBookmarkBar` is enabled; that flag is disabled by default at both versions. | `pref:bookmark_bar.visibility_state` · to `components/bookmarks/common/bookmark_pref_names.h:49`; `file:chrome/browser/bookmarks/bookmark_bar_policy_handler.cc` (new at 151) | Not verified |
| The `BookmarksTreeView` experiment is removed from the tree | The flag, its header declaration, its `chrome://flags#bookmarks-tree-view` entry, its flag-metadata row, the `bookmarksTreeViewEnabled` handler boolean and the template binding all disappear. It was disabled by default on Windows at 148, so nothing shipped changes; any field-trial or launch config that still names it is now dead configuration. | `base_feature:BookmarksTreeView`, `webui_gate:bookmarks_side_panel_ui/bookmarksTreeViewEnabled` · from `chrome/browser/browser_features.cc:26` and `chrome/browser/ui/webui/side_panel/bookmarks/bookmarks_side_panel_ui.cc:208` → absent at 151 | Not verified |
| The dangerous-download warning metric is only recorded for downloads that are actually dangerous | `MaybeRecordDangerousDownloadWarningShown` is now wrapped in `if (download_model.IsDangerous())`. No user-visible change, but a dashboard comparing 148 with 151 will show a step change that is a measurement fix, not a behaviour change. | `file:chrome/browser/ui/webui/downloads/downloads_list_tracker.cc` · from `chrome/browser/ui/webui/downloads/downloads_list_tracker.cc:501` → to `:501` | Not verified |
| A new bookmarks Mojo API (`bookmarks_api.mojom`) is added, and the experimental WebUI browser is its first consumer | `BookmarksService` (6 methods, all returning `result<T, Error>`) plus a `BookmarksObserver` update stream handed back inside the `GetBookmarks()` reply. Nodes are identified by `Uuid`, an unset id means "create". This is a new capability the fork can build on instead of extension plumbing; it is not a compatibility break, because nothing at 148 could call it. It carries no `[Stable]` annotation, so both peers must come from the same revision. | `mojo_interface:bookmarks_api.mojom.BookmarksService`, `mojo_interface:bookmarks_api.mojom.BookmarksObserver` and 47 further declarations · to `components/browser_apis/bookmarks/bookmarks_api.mojom:102`; consumer: `chrome/browser/resources/webui_browser/bookmarks/` (new at 151) | Not verified |
| Download history loading can be deferred, and `chrome://downloads` forces it to initialize when the page opens | `kDeferredDownloadHistoryLoading` is new and disabled by default on Windows, with no `chrome://flags` entry, so it is trial-only. `DownloadsUI::CreatePageHandler` now calls `InitializeHistory()` unconditionally, which is the counterpart that keeps the page correct if the deferral is turned on. With the flag off, behaviour is unchanged. | `base_feature:DeferredDownloadHistoryLoading` · to `components/download/public/common/download_features.cc:91`; `file:chrome/browser/ui/webui/downloads/downloads_ui.cc` · to `:316` | Not verified |
| `chrome://bookmarks` and `chrome://downloads` join the 2026 WebUI refresh and the rounded-icons rollout | Both handlers now publish `webuiRefresh2026`, and both page shells stamp `$i18n{webuiRefresh2026}` and `$i18n{roundedIconsAttribute}` on `<html>` with a matching background rule. `IsWebuiRefresh2026Enabled()` is `kDesktopGlowUp || kWebuiRefresh2026`, both disabled by default at 151 and both reachable from `chrome://flags`. No user-visible change at the source default; a new styling hook and two new i18n keys for a fork page shell. | `webui_gate:bookmarks_ui/webuiRefresh2026`, `webui_gate:downloads_ui/webuiRefresh2026` · to `chrome/browser/ui/webui/bookmarks/bookmarks_ui.cc:154`, `chrome/browser/ui/ui_features.cc:100`, `ui/base/ui_base_features.cc:505` | Not verified |
| A `menuSimplification` gate is exposed to both bookmarks pages | Both `chrome://bookmarks` and the bookmarks side panel now publish `menuSimplification` from `IsMenuSimplificationEnabled()`, which is `kDesktopGlowUp || kMenuSimplification`; both are disabled by default. Worth knowing that forcing `desktop-glow-up` on for the toolbar work also turns on menu simplification and the 2026 refresh in these pages. | `webui_gate:bookmarks_ui/menuSimplification`, `webui_gate:bookmarks_side_panel_ui/menuSimplification` · to `chrome/browser/ui/ui_features.cc:90` | Not verified |
| The bookmarks batch-upload promo is un-gated on ChromeOS | The `<if expr="not is_chromeos">` wrapper and the matching `#if !BUILDFLAG(IS_CHROMEOS)` guards are removed. Nothing changes on Windows, where the promo was already compiled and shown. Recorded so the removal of a platform guard is not mistaken for a new Windows feature. | `file:chrome/browser/resources/bookmarks/list.html.ts` | Not verified |
| The WebUI browser bookmark bar gets its initial state and reacts to bookmarks moving | The handler now pushes the browser's bookmark bar state on construction and refreshes the page when a bookmark moves in or out of the bar, replacing a `TODO(webium)` stub. Affects only the experimental WebUI browser surface. | `file:chrome/browser/ui/webui_browser/bookmark_bar_page_handler.cc` · to `chrome/browser/ui/webui_browser/bookmark_bar_page_handler.cc:68` | Not verified |

`Verify` is for a person to fill in after checking the row. Every row says
`Not verified` because the tool cannot perform that check and neither can the
agent that wrote this page.

### Changes deliberately left out of the table

These were inspected and decided, not overlooked.

- **Android-only:** `DownloadsCompactListView`, `RemapGenericMimeType` and
  `OpenDownloadInFilesAppIfNoHandlerFound` are declared inside
  `#if BUILDFLAG(IS_ANDROID)` and are recorded `not_compiled` for Windows.
  `IsApkFile` in `download_ui_safe_browsing_util.cc` and the new
  `bookmarks_ui_android.cc` are the same case.
- **ChromeOS-only:** the `DownloadPrefs::DriveHandler` that resets the download
  directory when DriveFS is disabled, and the `ash::prefs::` namespace move in
  `download_dir_policy_handler.cc`.
- **No Windows change despite a recorded delta:** `BookmarksMigrateUiChanges`.
  Its `default_state` moves from disabled to enabled, but that is the ChromeOS
  branch of the old `#if` disappearing; `platform_state.windows` reads `enabled`
  at both versions, so Windows behaviour is unchanged.
- **Non-behavioural:** the unreferenced `shield` icon removed from
  `chrome/browser/resources/downloads/icons.html` (rows use
  `downloads-internal:gshield`, which still exists), a typing-only change in
  `manager.html.ts`, an include move in `bookmarks_page_handler.cc`, and a
  test-only include removal in `downloads_handler_unittest.cc`.
- **Word matches from other subsystems:** ChromeOS DLC predownload policy, the
  ash login "app downloading" screen, on-device model download progress,
  trusted-vault key download, and `services/on_device_model/.../download_observer.mojom`.
  They carry the word "download" but are not the Downloads feature.

## 3. What this run did not look at

### What the comparison measured about its own coverage

- From side: 8024 of 8094 candidate declarations read; 70 missed.
- To side: 8295 of 8366 candidate declarations read; 71 missed.
- Directories with the most missed candidates on the to side: `chrome/services` 24,
  `chrome/credential_provider` 15, `chrome/installer` 12, `third_party/blink` 6,
  `chrome/renderer` 3, `chrome/notification_helper` 2, `chrome/browser` 1,
  `chrome/common` 1, and 4 more directories.
- Acquisition: target set `wide`, no partitions. Unconfirmed findings: 0.
  Unresolved declaration references across the whole index: 295.
- Source scope: cached files only, 12160 files on the from side and 12413 on the
  to side. A file missing on one side is unknown, not proof that Chromium added
  or removed it. Uncached code and symlinks were not examined.

### Files no parser reads at all

The extractor only parses these suffixes: `features.cc`, `features.h`,
`switches.cc`, `switches.h`, `feature_list.cc/.h`, `field_trial.cc/.h`,
`fieldtrial.cc/.h`, `flags.cc/.h`, `_handler.cc`, `_util.cc`, `_manager.cc`,
`pref_names.cc/.h`, `prefs.cc/.h`, `.mojom`, `.idl`, `.json5`, `route.ts`,
`routes.ts`, `.html`, `.html.ts`, `flag-metadata.json`. A file outside that list
never produces a finding, whether or not it changed. Most `.cc` and `.ts`
implementation files in these two areas are in that category; they were read only
as source diffs where a finding or a reference pointed at them.

### What this method cannot do at all

- It compares **declarations**, not behaviour. A default written in the source is
  not proof of what shipped.
- **Finch** and any other server-controlled configuration is not visible here. A
  flag that reads "disabled by default" can be on in the field.
- **Configuration outside the binary** — enterprise policy in place, master
  preferences, launch switches — needs its own evidence.
- **Patches this product carries** are not part of the comparison; only upstream
  Chromium was read. Which consumers the fork ships was not asked for in this run,
  so product impact is stated as what the upstream change forces a consumer to do.
- **The UI as rendered** was not opened. Control ids were read from templates, not
  from a running page.

### Open questions recorded against specific events

- Who is allowed to bind `BookmarksService` is unknown: `BookmarksServiceFeature`
  and the `components/browser_apis/bookmarks/BUILD.gn` are not in the cache at
  either version.
- Where `BookmarkBarPolicyHandler` is registered was not read:
  `chrome/browser/policy/configuration_policy_handler_list_factory.cc` is not
  cached at either version, so how `BookmarkBarEnabled` was handled at 148 is
  unknown rather than absent.
- Whether the unchecked `browser->GetBrowserForMigrationOnly()` in
  `HandleOnBatchUploadPromoClicked` can be reached with a null browser.
- How `base::File::FLAG_NO_FOLLOW` behaves for Windows junctions and reparse
  points.

### How much was left outside the requested scope

**9283 of 9437 indexed items** were not decided, because they belong to areas the
user did not select. That is 5972 findings, 3228 source deltas and all 78
milestone summaries. Something absent from the table above may simply be in that
remainder. `review check` passing is accounting, not approval to ship.
