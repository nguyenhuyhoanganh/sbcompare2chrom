# Chromium upgrade review

refs/tags/148.0.7778.217 → refs/tags/151.0.7922.138 · windows

Status: PARTIAL

Indexed items: 9437; events: 36; provisional events: 0.

Disposition counts: {"event": 173, "explained": 27, "out_of_scope": 198, "pending": 9039}

Accounting does not establish semantic completeness or product safety.

## Recorded item selection

Extensions ở 148.0.7778.217 → 151.0.7922.138 trên Windows, mức full: flags, mojom, WebUI (thay đổi người dùng thấy, khả năng mới, việc downstream phải thích nghi), cộng pref, handler, source delta và feature file của API cần để giải thích chúng. Biên: 205 item indexed dưới extensions/, chrome/browser/extensions/, chrome/common/extensions/, chrome/browser/ui/webui/extensions/, chrome/browser/resources/extensions/, UI extension của toolbar/side panel và extensions bar của WebUI toolbar (50 finding + 155 file diff), cộng 173 finding dependency và 19 file khai báo dùng chung mà focus packet trả về, cộng device.mojom.SerialPortManager.GetDevices mà chrome.serial dùng. Settings, History, Downloads, Bookmarks đã review riêng.

Selection accounting: COMPLETE
Selected items: 398; outside the selection: 9039.
Disposition counts: {"event": 173, "explained": 27, "out_of_scope": 198}

Only the explicitly selected items are counted. Selection and semantic completeness require review.

## Coverage and limits

This comparison reads declarations the extractor parses. It does not compare behaviour, and a file with no declaration parser is absent from the findings whether or not it changed.

Parsed file suffixes: features.cc, features.h, switches.cc, switches.h, feature_list.cc, feature_list.h, field_trial.cc, field_trial.h, fieldtrial.cc, fieldtrial.h, flags.cc, flags.h, _handler.cc, _util.cc, _manager.cc, pref_names.cc, pref_names.h, prefs.cc, prefs.h, .mojom, .idl, .json5, route.ts, routes.ts, .html, .html.ts, flag-metadata.json.

- from: 8024 of 8094 candidate declaration files read; 70 missed.
- to: 8295 of 8366 candidate declaration files read; 71 missed.
- Candidates missed by directory (to side): chrome/services 24; chrome/credential_provider 15; chrome/installer 12; third_party/blink 6; chrome/renderer 3; chrome/notification_helper 2; chrome/browser 1; chrome/common 1; and 4 more directories
- Acquisition: target set wide; partitions none; unconfirmed findings: 0.
- Unresolved declaration references: 295.
- Source scope: Only cached files, possibly beyond the original scan. A missing side is unknown, not an upstream addition/removal. Uncached code and symlinks are unexamined; .git and acquisition markers are excluded.
- Finch, external configuration, product patches and rendered UI require separate evidence.

These limits bound what the comparison could observe. They are the places a reviewer must check by hand.

## 1. Manifest V2 kết thúc hẳn: bỏ mọi đường lui (cờ developer, danh sách ngoại lệ, miễn trừ theo policy) và xoá pref extensions.manifest_v2

Status: confirmed

Before: 148: ManifestV2ExperimentManager (chrome/browser/extensions) tính "stage" từ cờ — kExtensionManifestV2Unsupported (enabled) → kUnsupported, kExtensionManifestV2Disabled (enabled) → kDisableWithReEnable, còn lại kWarning. Ở kUnsupported, extension MV2 bị tắt và người dùng không bật lại được; nhưng vẫn còn ba lối thoát: extension unpacked được nạp nếu bật kAllowLegacyMV2Extensions, extension có hash trong param Finch kExtensionManifestV2ExceptionList được miễn, và IsExemptFromMV2DeprecationByPolicy (ExtensionManagement, đọc pref extensions.manifest_v2 do policy ExtensionManifestV2Availability đặt) được miễn. chrome://extensions nhận MV2ExperimentStage và có nút "Find alternative" / "Keep for now".

After: 151: ManifestV2ExperimentManager, file stage và năm cờ MV2 bị xoá; ManifestV2Handler mới ở extensions/browser có ShouldDisableLegacyExtensions() luôn trả true (chỉ trừ testing) và tắt mọi extension bị ảnh hưởng với lý do DISABLE_UNSUPPORTED_MANIFEST_VERSION ngay khi ExtensionSystem sẵn sàng. MV2DeprecationImpactChecker mới chỉ còn ba điều kiện: manifest_version < 3, loại là extension / login screen extension / user script, và không phải component. Không còn nhánh unpacked, không còn policy, không còn danh sách ngoại lệ. Pref extensions.manifest_v2 không còn được khai báo hay RegisterIntegerPref; MigrateObsoleteExtensionPrefs xoá thêm các khoá per-extension mv2_deprecation_*. chrome://extensions chỉ còn MV2DeprecationNoticeDismissed (đọc từ handler mới), bỏ các nút "Find alternative" và "Keep for now".

Mechanism: Trạng thái mặc định ở 148 đã là "không hỗ trợ" (cờ kUnsupported bật), nên với người dùng thường không có gì đổi. Cái đổi là ba lối thoát biến mất cùng lúc với code stage: (1) developer không còn nạp được extension MV2 unpacked bằng cờ AllowLegacyMV2Extensions; (2) Google không còn cấp ngoại lệ qua Finch; (3) nhánh miễn trừ theo policy bị xoá khỏi checker — chính policy ExtensionManifestV2Availability đã ghi supported_on chrome.*:110-138 và deprecated: true ngay từ trước 148. Thêm một mở rộng: Manifest::Type::kUserScript nay cũng bị tính là bị ảnh hưởng. Manifest key nacl_modules (max_manifest_version 2) bị xoá khỏi _manifest_features.json.

Impact: Sản phẩm downstream còn phụ thuộc một extension MV2 — kể cả extension nội bộ cài bằng policy, hoặc extension unpacked dùng khi phát triển — sẽ thấy nó bị tắt ở 151 mà không còn cách bật lại bằng cờ hay policy; chỉ component extension (location component) còn được giữ. Patch downstream dựa trên ManifestV2ExperimentManager, MV2ExperimentStage hay kAllowLegacyMV2Extensions sẽ không biên dịch.

Conditions: Windows; không còn cờ hay policy điều khiển. Ngoại lệ duy nhất là extension location component và AllowMV2ExtensionsForTesting trong test.

Action: Kiểm kê mọi extension MV2 mà sản phẩm cài (policy, external, unpacked) và chuyển sang MV3 trước khi lên 151; nếu buộc phải giữ, xem xét cài dưới dạng component extension. Xoá cấu hình ExtensionManifestV2Availability khỏi policy vì không còn tác dụng. Mở chrome://extensions với một extension MV2 để xác nhận nó bị tắt với lý do "unsupported manifest version".

Uncertainties: Chưa đọc code cài đặt component extension của sản phẩm để biết extension nội bộ nào đang ở location component.

- `base_feature:ExtensionManifestV2Unsupported` · [from: extensions/common/extension_features.cc:78](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#78): Cờ enabled bị xoá — stage kUnsupported trở thành hành vi duy nhất.
- `base_feature:ExtensionManifestV2Disabled` · [from: extensions/common/extension_features.cc:83](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#83): Cờ enabled bị xoá — stage kDisableWithReEnable biến mất.
- `base_feature:ExtensionManifestV2ExceptionList` · [from: extensions/common/extension_features.cc:80](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#80): Cờ và param mv2_exception_list bị xoá — hết danh sách ngoại lệ qua Finch.
- `base_feature:AllowLegacyMV2Extensions` · [from: extensions/common/extension_features.cc:111](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#111): Cờ cho phép nạp MV2 unpacked bị xoá — developer mất lối thoát.
- `base_feature:ExtensionsManifestV3Only` · [from: extensions/common/extension_features.cc:115](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#115): Cờ chỉ còn được ExtensionManagement đọc bị xoá.
- `pref:extensions.manifest_v2` · [from: extensions/browser/pref_names.h:132](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/pref_names.h#132): Khai báo kManifestV2Availability rời pref_names.h và không còn RegisterIntegerPref ở 151 (grep cache 151 không còn tên này).
- `webui_gate:extensions_ui/MV2ExperimentStage` · [from: chrome/browser/ui/webui/extensions/extensions_ui.cc:499](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extensions_ui.cc#499): loadTimeData MV2ExperimentStage bị xoá khỏi chrome://extensions.
- `webui_gate:extensions_ui/MV2DeprecationNoticeDismissed` · [from: chrome/browser/ui/webui/extensions/extensions_ui.cc:500](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extensions_ui.cc#500), [to: chrome/browser/ui/webui/extensions/extensions_ui.cc:494](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extensions_ui.cc#494): Boolean đổi nguồn sang ManifestV2Handler::DidUserAcknowledgeNoticeGlobally.
- `file:chrome/browser/extensions/manifest_v2_experiment_manager.cc` · [from: chrome/browser/extensions/manifest_v2_experiment_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/manifest_v2_experiment_manager.cc): File 148 bị xoá ở 151 (upstream_404); đã đọc các đoạn tính stage, chặn cài, và nghe pref policy.
- `file:extensions/browser/manifest_v2_handler.cc` · [to: extensions/browser/manifest_v2_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/manifest_v2_handler.cc): File mới 151 (upstream_404 ở 148); đã đọc toàn bộ.
- `file:extensions/browser/pref_names.h` · [from: extensions/browser/pref_names.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/pref_names.h), [to: extensions/browser/pref_names.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/pref_names.h): Đã đọc hunk duy nhất: xoá kManifestV2Availability.
- `file:chrome/browser/ui/webui/extensions/extensions_ui.cc` · [from: chrome/browser/ui/webui/extensions/extensions_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extensions_ui.cc), [to: chrome/browser/ui/webui/extensions/extensions_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extensions_ui.cc): Đã đọc mọi hunk: bỏ stage, đổi nguồn boolean MV2, bỏ hai chuỗi nút; hunk webuiRefresh2026/ThemeSource/MojoWebUIController thuộc event:ext-webui-refresh-rounded-icons.
- `file:chrome/browser/resources/extensions/mv2_deprecation_panel.html.ts` · [from: chrome/browser/resources/extensions/mv2_deprecation_panel.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/extensions/mv2_deprecation_panel.html.ts), [to: chrome/browser/resources/extensions/mv2_deprecation_panel.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/extensions/mv2_deprecation_panel.html.ts): Đã đọc mọi hunk: bỏ nút Find alternative, Keep for now và Remove trong menu.
- `file:chrome/browser/resources/extensions/detail_view.html.ts` · [from: chrome/browser/resources/extensions/detail_view.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/extensions/detail_view.html.ts), [to: chrome/browser/resources/extensions/detail_view.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/extensions/detail_view.html.ts): Đã đọc mọi hunk: bỏ nút Find alternative và mục Keep for now.
- `file:chrome/browser/resources/extensions/item_list.html.ts` · [from: chrome/browser/resources/extensions/item_list.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/extensions/item_list.html.ts), [to: chrome/browser/resources/extensions/item_list.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/extensions/item_list.html.ts): Đã đọc mọi hunk: bỏ thuộc tính mv2ExperimentStage.
- `file:chrome/browser/ui/webui/extensions/extension_settings_test_base.cc` · [from: chrome/browser/ui/webui/extensions/extension_settings_test_base.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extension_settings_test_base.cc), [to: chrome/browser/ui/webui/extensions/extension_settings_test_base.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extension_settings_test_base.cc): Đã đọc hunk duy nhất: bỏ SetSilenceDeprecatedManifestVersionWarnings.
- `file:extensions/common/extension_features.cc` · [from: extensions/common/extension_features.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc), [to: extensions/common/extension_features.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc): Đã đọc mọi hunk của extension_features.cc: hunk MV2 ở đây; các hunk khác thuộc event:ext-public-mime-handler, event:ext-tab-context-menu, event:ext-browser-namespace, event:ext-webstore-hosted-app, event:ext-webrequest-persistence, event:ext-webrequest-per-context-dispatch, event:ext-alarms-session-and-limit, event:ext-glic-private-api, event:ext-component-private-apis, event:ext-component-worker-chrome-resources, event:ext-search-choice-dialog-param, và out_of_scope cho TelemetryExtensionPendingApprovalApi.
- `file:extensions/common/extension_features.h` · [from: extensions/common/extension_features.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.h), [to: extensions/common/extension_features.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.h): Đã đọc mọi hunk của extension_features.h; phân bổ như .cc.
- [from: chrome/browser/extensions/manifest_v2_experiment_manager.cc:149](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/manifest_v2_experiment_manager.cc#149): 148: stage lấy từ hai cờ Unsupported/Disabled.
- [from: chrome/browser/extensions/mv2_deprecation_impact_checker.cc:75](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/mv2_deprecation_impact_checker.cc#75): 148: miễn trừ theo policy và theo danh sách hash ngoại lệ.
- [to: extensions/browser/mv2_deprecation_impact_checker.cc:28](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/mv2_deprecation_impact_checker.cc#28): 151: chỉ còn ba điều kiện, có thêm kUserScript, không còn policy/ngoại lệ.
- [to: extensions/browser/manifest_v2_handler.cc:110](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/manifest_v2_handler.cc#110): 151: luôn tắt MV2 trừ khi test bật cờ riêng.
- [to: components/policy/resources/templates/policy_definitions/Extensions/ExtensionManifestV2Availability.yaml:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/policy/resources/templates/policy_definitions/Extensions/ExtensionManifestV2Availability.yaml#19): Policy chỉ hỗ trợ tới 138 và đã deprecated.
- [to: extensions/browser/extension_prefs.cc:2667](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc#2667): 151 xoá các khoá per-extension mv2_deprecation_* khỏi Preferences.
- [from: extensions/common/api/_manifest_features.json:378](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/_manifest_features.json#378): 148: manifest key nacl_modules (max_manifest_version 2) — không còn ở 151.

## 2. Extension thường được đăng ký làm trình mở PDF (mime_types_handler + API mimeHandler), bật mặc định và thắng PDF viewer có sẵn

Status: confirmed

Before: 148: manifest key mime_types_handler chỉ dành cho extension trong allowlist (PDF viewer, QuickOffice); không có API mimeHandler; cờ kApiMimeHandler không tồn tại. Tên extension chỉ hiện ở thanh địa chỉ cho URL chrome-extension://.

After: 151: cờ kApiMimeHandler enabled theo source. _manifest_features.json mở mime_types_handler cho mọi extension loại "extension" ở stable (feature_flag ApiMimeHandler) và ở dev không cần cờ; _api_features.json thêm namespace mimeHandler với cùng điều kiện. MimeTypesHandlerParser nhận định dạng dict mới {mime_type: {handler_url, can_embed}}; với extension ngoài allowlist chỉ chấp nhận application/pdf (GetPublicAllowedMIMETypeList). MimeHandlerRegistry mới xếp thứ tự: handler công khai (ngoài allowlist) thắng handler allowlist, trong nhóm công khai extension cài gần nhất thắng; người dùng/extension tắt được từng loại qua pref per-extension mime_handler_enabled. Có MimeHandlerStreamManager mới dưới extensions/browser/mime_handler và GetEnabledExtensionNameForUrl nay trả tên extension đang render tài liệu ở khung chính.

Mechanism: Đây là một khả năng mới trọn vẹn: manifest key, API, parser, registry và luồng stream. Điểm quyết định hành vi là SortByPrecedence — built-in PDF extension nằm trong allowlist nên bị xếp sau mọi handler công khai. plugin_manager.cc và extension_test_util.cc chỉ theo API mới (MimeTypesHandler::Get, GetSupportedMimeTypes; thêm mimeHandler vào danh sách khả năng test).

Impact: Trên Windows 151, một extension người dùng cài khai báo xử lý application/pdf sẽ trở thành trình mở PDF thay cho PDF viewer của Chrome, và thanh địa chỉ hiển thị tên extension đó. Với sản phẩm downstream đây vừa là khả năng mới vừa là rủi ro: cần quyết định có cho phép không (tắt kApiMimeHandler hoặc chặn bằng policy quản lý extension), và kiểm tra các patch vào PDF viewer vẫn được dùng khi có extension như vậy.

Conditions: Windows; kApiMimeHandler enabled theo source; kênh dev/canary luôn bật trừ khi có override tắt. Chỉ application/pdf cho extension ngoài allowlist. Người dùng có thể tắt từng loại (mime_handler_enabled).

Action: Cài một extension thử khai báo mime_types_handler dạng dict cho application/pdf, mở một PDF và xác nhận extension thắng PDF viewer; thử tắt bằng --disable-features=ApiMimeHandler. Quyết định chính sách sản phẩm và, nếu cần, chặn qua ExtensionSettings.

Uncertainties: Chưa đọc UI quản lý/cảnh báo cho người dùng khi một extension chiếm PDF (nếu có) — ngoài các file đã đọc.

- `base_feature:ApiMimeHandler` · [to: extensions/common/extension_features.cc:25](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#25): Cờ mới, enabled theo source trên Windows.
- `file:extensions/common/manifest_handlers/mime_types_handler.cc` · [from: extensions/common/manifest_handlers/mime_types_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/mime_types_handler.cc), [to: extensions/common/manifest_handlers/mime_types_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/mime_types_handler.cc): Đã đọc mọi hunk: định dạng dict, chỉ application/pdf cho extension công khai, cổng theo cờ/kênh.
- `file:extensions/browser/mime_handler/mime_handler_stream_manager.cc` · [to: extensions/browser/mime_handler/mime_handler_stream_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/mime_handler/mime_handler_stream_manager.cc): File mới (upstream_404 ở 148); đã đọc phần đầu và các điểm móc navigation.
- `file:extensions/browser/mime_handler/mime_handler_ui_util.cc` · [to: extensions/browser/mime_handler/mime_handler_ui_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/mime_handler/mime_handler_ui_util.cc): File mới; đã đọc toàn bộ: xác định extension handler khung chính, loại trừ extension plugin allowlist.
- `file:chrome/browser/extensions/extension_ui_util.cc` · [from: chrome/browser/extensions/extension_ui_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/extension_ui_util.cc), [to: chrome/browser/extensions/extension_ui_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/extension_ui_util.cc): Đã đọc mọi hunk: GetEnabledExtensionNameForUrl nhận WebContents và tra MIME handler.
- `file:chrome/browser/extensions/plugin_manager.cc` · [from: chrome/browser/extensions/plugin_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/plugin_manager.cc), [to: chrome/browser/extensions/plugin_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/plugin_manager.cc): Đã đọc mọi hunk: theo API MimeTypesHandler mới.
- `file:chrome/common/extensions/extension_test_util.cc` · [from: chrome/common/extensions/extension_test_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/extension_test_util.cc), [to: chrome/common/extensions/extension_test_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/extension_test_util.cc): Đã đọc mọi hunk: thêm mimeHandler vào danh sách khả năng dùng trong test.
- [to: extensions/browser/mime_handler/mime_handler_registry.cc:238](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/mime_handler/mime_handler_registry.cc#238): Handler công khai thắng handler allowlist; trong nhóm công khai, cài gần nhất thắng.
- [to: extensions/common/manifest_handlers/mime_types_handler.cc:139](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/mime_types_handler.cc#139): Extension công khai chỉ được application/pdf.
- [to: extensions/common/manifest_handlers/mime_types_handler.cc:231](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/mime_types_handler.cc#231): Parse định dạng dict khi cờ bật hoặc kênh dev trở xuống.
- [to: extensions/common/api/_manifest_features.json:351](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_manifest_features.json#351): Manifest key mở cho extension thường ở stable theo cờ ApiMimeHandler.
- [to: extensions/common/api/_api_features.json:505](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_api_features.json#505): Namespace API mimeHandler mới.

## 3. Extension được thêm mục vào menu chuột phải của tab (contextMenus context "tab"), bật mặc định

Status: confirmed

Before: 148: ContextType của contextMenus gồm all, page, frame, selection, link, editable, image, video, audio, launcher, browser_action, page_action, action; không có cờ kExtensionTabContextMenu.

After: 151: ContextType thêm "tab"; cờ kExtensionTabContextMenu enabled theo source ("Enables extension support for the tab context menu").

Mechanism: Khả năng API mới được bật mặc định cùng lúc với giá trị enum mới trong schema context_menus.json.

Impact: Người dùng Windows 151 có thể thấy mục do extension thêm khi bấm chuột phải lên tab. Sản phẩm downstream có menu tab tuỳ biến cần kiểm tra chỗ chèn mục extension và có thể muốn tắt cờ.

Conditions: Windows; cờ enabled theo source; cần extension có quyền contextMenus và đăng ký context "tab".

Action: Cài extension thử tạo mục contextMenus với contexts ["tab"], bấm chuột phải lên tab để xác nhận; kiểm tra menu tab tuỳ biến của sản phẩm.

Uncertainties: Chưa đọc code UI chèn mục vào menu tab (ngoài phạm vi các file đã đọc).

- `base_feature:ExtensionTabContextMenu` · [to: extensions/common/extension_features.cc:147](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#147): Cờ mới, enabled theo source trên Windows.
- [to: chrome/common/extensions/api/context_menus.json:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/context_menus.json#17): 151: enum ContextType có "tab".
- [from: chrome/common/extensions/api/context_menus.json:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/context_menus.json#17): 148: enum ContextType chưa có "tab".

## 4. Chrome Apps trên Windows mất webview, appview, usb và bluetooth: các API này chỉ còn trên ChromeOS; bộ test web_view/app_view gần như bị xoá hết

Status: confirmed

Before: 148: _permission_features.json cấp appview, webview, usb cho platform_app trên chromeos/linux/mac/win; _api_features.json mở bluetooth, bluetoothSocket (chromeos/linux/mac/win), bluetoothLowEnergy (chromeos/linux), usb, appViewEmbedderInternal và API AppView; manifest key bluetooth cho platform_app trên chromeos/win/mac cộng allowlist Linux. Cache 148 có 28 file test data dưới extensions/test/data/web_view và app_view.

After: 151: tất cả mục trên thành "platforms": ["chromeos"]; mục bluetooth của manifest cho win/mac và allowlist Linux bị xoá. Chỉ còn 2 file dưới web_view (accept_touch_events); 27 file kia không tồn tại ở ref 151 (fetch trả upstream_404).

Mechanism: Feature files quyết định API nào có mặt trên nền tảng nào, nên việc đổi platforms tắt các API đó trên Windows bất kể code triển khai còn hay không. Hai quan sát (API chỉ còn ChromeOS và test fixture web_view/app_view bị xoá) cùng nói về một nhóm API và cùng khoảng phiên bản; mối quan hệ nhân quả giữa chúng chưa được xác minh bằng lịch sử commit.

Impact: Chrome App (platform app) chạy trên Windows dùng <webview>, <appview>, chrome.usb hoặc chrome.bluetooth* sẽ không còn các API đó ở 151. Sản phẩm downstream còn phân phối Chrome App trên Windows cần chuyển sang giải pháp khác (Isolated Web App/Controlled Frame, WebUSB, Web Bluetooth). Extension thường (không phải platform app) không bị ảnh hưởng.

Conditions: Windows; áp dụng cho extension_types platform_app.

Action: Kiểm kê Chrome App mà sản phẩm cài trên Windows; thử mở app dùng webview/usb/bluetooth trên 151.

Uncertainties: Chưa xác minh bằng commit history rằng việc xoá test fixture và việc giới hạn nền tảng là cùng một thay đổi.

- `file:extensions/test/data/app_view/apitest/main.html` · [from: extensions/test/data/app_view/apitest/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/app_view/apitest/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/app_view/apitest/media_request/guest.html` · [from: extensions/test/data/app_view/apitest/media_request/guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/app_view/apitest/media_request/guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/app_view/apitest/media_request/main.html` · [from: extensions/test/data/app_view/apitest/media_request/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/app_view/apitest/media_request/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/app_view/apitest/no_embed_request_listener/main.html` · [from: extensions/test/data/app_view/apitest/no_embed_request_listener/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/app_view/apitest/no_embed_request_listener/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/app_view/apitest/skeleton/main.html` · [from: extensions/test/data/app_view/apitest/skeleton/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/app_view/apitest/skeleton/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/system/storage/test_storage_api.html` · [from: extensions/test/data/system/storage/test_storage_api.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/system/storage/test_storage_api.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/empty_frame.html` · [from: extensions/test/data/web_view/apitest/empty_frame.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/empty_frame.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/empty_guest.html` · [from: extensions/test/data/web_view/apitest/empty_guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/empty_guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/guest.html` · [from: extensions/test/data/web_view/apitest/guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/guest_noreferrer.html` · [from: extensions/test/data/web_view/apitest/guest_noreferrer.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/guest_noreferrer.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/guest_redirect.html` · [from: extensions/test/data/web_view/apitest/guest_redirect.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/guest_redirect.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/guest_same_document_navigation.html` · [from: extensions/test/data/web_view/apitest/guest_same_document_navigation.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/guest_same_document_navigation.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/guest_with_inline_script.html` · [from: extensions/test/data/web_view/apitest/guest_with_inline_script.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/guest_with_inline_script.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/apitest/main.html` · [from: extensions/test/data/web_view/apitest/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/apitest/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/close_on_loadcommit/main.html` · [from: extensions/test/data/web_view/close_on_loadcommit/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/close_on_loadcommit/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/dialog/embedder.html` · [from: extensions/test/data/web_view/dialog/embedder.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/dialog/embedder.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/display_none_set_src/main.html` · [from: extensions/test/data/web_view/display_none_set_src/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/display_none_set_src/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/inside_iframe/main.html` · [from: extensions/test/data/web_view/inside_iframe/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/inside_iframe/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/inside_iframe/webview.html` · [from: extensions/test/data/web_view/inside_iframe/webview.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/inside_iframe/webview.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/allow/embedder.html` · [from: extensions/test/data/web_view/media_access/allow/embedder.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/allow/embedder.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/allow/media_access_guest.html` · [from: extensions/test/data/web_view/media_access/allow/media_access_guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/allow/media_access_guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/check/embedder.html` · [from: extensions/test/data/web_view/media_access/check/embedder.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/check/embedder.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/check/media_check_guest.html` · [from: extensions/test/data/web_view/media_access/check/media_check_guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/check/media_check_guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/deny/embedder.html` · [from: extensions/test/data/web_view/media_access/deny/embedder.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/deny/embedder.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/media_access/deny/media_access_guest.html` · [from: extensions/test/data/web_view/media_access/deny/media_access_guest.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/media_access/deny/media_access_guest.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/no_internal_calls_to_user_code/main.html` · [from: extensions/test/data/web_view/no_internal_calls_to_user_code/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/no_internal_calls_to_user_code/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- `file:extensions/test/data/web_view/visibility_changed/main.html` · [from: extensions/test/data/web_view/visibility_changed/main.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/test/data/web_view/visibility_changed/main.html): Test fixture web_view/app_view bị xoá ở ref 151 (upstream_404).
- [to: extensions/common/api/_permission_features.json:746](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_permission_features.json#746): 151: quyền webview chỉ còn chromeos.
- [to: extensions/common/api/_permission_features.json:76](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_permission_features.json#76): 151: quyền appview chỉ còn chromeos.
- [to: extensions/common/api/_permission_features.json:679](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_permission_features.json#679): 151: quyền usb chỉ còn chromeos.
- [to: extensions/common/api/_api_features.json:105](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_api_features.json#105): 151: API bluetooth chỉ còn chromeos.
- [from: extensions/common/api/_permission_features.json:783](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/_permission_features.json#783): 148: quyền webview có win.

## 5. declarativeNetRequest không redirect sang file:// và không chặn request file:// nếu extension chưa được cấp quyền truy cập file

Status: confirmed

Before: 148: rule redirect của DNR có thể trỏ tới file:// và rule có thể khớp request file:// mà không xét quyền "Allow access to file URLs".

After: 151: action redirect/upgrade tới file:// bị bỏ nếu util::AllowFileAccess(extension) false (vẫn che rule ưu tiên thấp hơn của cùng ruleset); request có scheme file:// không còn được đưa vào ruleset của extension chưa có quyền file. Thêm metric Extensions.DeclarativeNetRequest.RedirectAction và UKM cho redirect trang tìm kiếm mặc định.

Mechanism: Hai kiểm tra cùng một nguyên tắc: truy cập file:// qua DNR phải có quyền file như các API khác. Metric là thêm riêng.

Impact: Extension DNR đang redirect sang file:// hoặc chặn/sửa request file:// sẽ ngừng làm vậy trừ khi người dùng bật "Allow access to file URLs". Thay đổi hành vi bảo mật áp dụng ngay.

Conditions: Windows; không có cờ.

Action: Với extension DNR thử: redirect tới file:// và rule khớp file:// khi bật/tắt quyền file URL.

- `file:extensions/browser/api/declarative_net_request/ruleset_manager.cc` · [from: extensions/browser/api/declarative_net_request/ruleset_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/api/declarative_net_request/ruleset_manager.cc), [to: extensions/browser/api/declarative_net_request/ruleset_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/declarative_net_request/ruleset_manager.cc): Đã đọc mọi hunk, gồm các hunk chỉ đổi cách xuống dòng comment.
- [to: extensions/browser/api/declarative_net_request/ruleset_manager.cc:392](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/declarative_net_request/ruleset_manager.cc#392): Bỏ redirect tới file:// khi thiếu quyền file.
- [to: extensions/browser/api/declarative_net_request/ruleset_manager.cc:639](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/declarative_net_request/ruleset_manager.cc#639): Không khớp request file:// khi thiếu quyền file.

## 6. Windows không nạp hosted app Web Store nữa; quyền webstorePrivate cho extension bị xoá, chỉ còn API trên trang chromewebstore.google.com

Status: confirmed

Before: 148: _permission_features.json có quyền webstorePrivate cho extension/legacy_packaged_app/hosted_app trong allowlist Web Store; _api_features.json có ngữ cảnh privileged_extension cho webstorePrivate cùng ngữ cảnh web_page trên chromewebstore.google.com; các quyền system.cpu/memory/storage/display/network có mục riêng cho hosted app Web Store.

After: 151: cờ mới kWebstoreHostedApp — enabled trên ChromeOS, disabled trên Windows/Mac/Linux ("Controls whether the component webstore hosted app is loaded", TODO tắt nốt trên ChromeOS). Quyền webstorePrivate và ngữ cảnh privileged_extension bị xoá; APIPermissionID kWebstorePrivate đổi thành kDeleted_WebstorePrivate; các mục hosted_app Web Store của system.* bị gỡ. webstorePrivate chỉ còn cho web_page tại https://chromewebstore.google.com/*.

Mechanism: Hosted app Web Store (một component app) bị bỏ trên desktop không phải ChromeOS; mọi đặc quyền cấp cho nó theo ID bị gỡ theo.

Impact: Trên Windows không còn app Web Store trong danh sách app; trang chromewebstore.google.com vẫn dùng webstorePrivate như web page. Sản phẩm downstream có trang/app phụ thuộc hosted app đó (ví dụ shortcut) cần gỡ.

Conditions: Windows: platform_state disabled; ChromeOS vẫn nạp.

Action: Kiểm tra chrome://apps và danh sách extension không còn app Web Store; kiểm tra luồng cài extension từ chromewebstore.google.com vẫn chạy.

- `base_feature:WebstoreHostedApp` · [to: extensions/common/extension_features.cc:178](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#178): Cờ mới: enabled chung, disabled trên Windows theo điều kiện IS_CHROMEOS.
- [to: extensions/common/extension_features.cc:176](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#176): 151: enabled chỉ khi IS_CHROMEOS.
- [from: chrome/common/extensions/api/_permission_features.json:1154](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/_permission_features.json#1154): 148: quyền webstorePrivate cho allowlist Web Store — không còn ở 151.
- [to: extensions/common/mojom/api_permission_id.mojom:190](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/api_permission_id.mojom#190): 151: id quyền được đánh dấu đã xoá.

## 7. ProcessManager: frame extension không vào back/forward cache; IPC giảm keepalive không còn trừ được hoạt động khác; sửa UAF khi đóng trang nền

Status: confirmed

Before: 148: frame extension có thể được đưa vào back/forward cache; DecrementLazyKeepaliveCount không kiểm tra hoạt động có được tăng trước không; đóng trang nền gọi ClosePage trong vòng lặp qua frame.

After: 151: RegisterRenderFrameHost gọi BackForwardCache::DisableForRenderFrameHost với lý do kExtensionFrame; DecrementLazyKeepaliveCount trả bool và chỉ trừ khi (activity_type, extra_data) đã được tăng chính xác ("Renderer IPCs are untrusted"); đóng trang nền gom WebContents rồi đóng qua WeakPtr (crbug.com/513156160).

Mechanism: Ba sửa lỗi độc lập trong cùng file; không có cờ. Cái người dùng có thể thấy là back/forward cache.

Impact: Điều hướng quay lại trang của extension (chrome-extension://) sẽ tải lại thay vì khôi phục từ bfcache. Hai sửa còn lại là hardening, không đổi hành vi với renderer bình thường.

Conditions: Windows; áp dụng ngay.

Action: Mở trang extension, điều hướng đi rồi Back để thấy trang tải lại; không cần thay đổi khác.

- `file:extensions/browser/process_manager.cc` · [from: extensions/browser/process_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/process_manager.cc), [to: extensions/browser/process_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/process_manager.cc): Đã đọc mọi hunk.
- [to: extensions/browser/process_manager.cc:250](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/process_manager.cc#250): Frame extension bị loại khỏi bfcache.
- [to: extensions/browser/process_manager.cc:770](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/process_manager.cc#770): Chỉ trừ keepalive đã được tăng.

## 8. Extension cài qua DevTools Protocol không còn tồn tại qua lần khởi động: ExtensionPrefs xoá chúng khi khởi tạo

Status: confirmed

Before: 148: không có bước dọn extension có cờ tạo INSTALLED_VIA_CDP.

After: 151: ExtensionPrefs::Init gọi CleanUpCdpInstalledExtensions(), xoá prefs của mọi extension có creation flag INSTALLED_VIA_CDP.

Mechanism: Extension nạp bằng CDP (Extensions.loadUnpacked) được coi là tạm thời cho phiên đó; dữ liệu cài của chúng bị xoá ở lần khởi tạo prefs tiếp theo.

Impact: Công cụ tự động hoá/test downstream nạp extension qua CDP rồi mong nó còn sau khi khởi động lại trình duyệt sẽ phải nạp lại mỗi lần.

Conditions: Windows; áp dụng extension có cờ INSTALLED_VIA_CDP.

Action: Nạp một extension qua CDP, khởi động lại và xác nhận nó biến mất; cập nhật script tự động hoá nếu cần.

- `file:extensions/browser/extension_prefs.h` · [from: extensions/browser/extension_prefs.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/extension_prefs.h), [to: extensions/browser/extension_prefs.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.h): Đã đọc mọi hunk: khai báo hai hàm dọn; hàm dọn filter trùng thuộc event:ext-webrequest-persistence.
- [to: extensions/browser/extension_prefs.cc:2611](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc#2611): Xoá prefs của extension INSTALLED_VIA_CDP.
- [to: extensions/browser/extension_prefs.cc:2186](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc#2186): Gọi ở lúc khởi tạo.

## 9. chrome.alarms: thêm alarm không lưu qua phiên (persistAcrossSessions), xoá alarm khỏi bộ nhớ khi unload, và cờ giới hạn độ dài input bật mặc định

Status: confirmed

Before: 148: mọi alarm được ghi vào StateStore; alarm của extension chỉ bị xoá khi gỡ cài đặt; không có cờ kApiAlarmsCreateLengthLimit.

After: 151: alarm có trường persist_across_sessions (mặc định true, theo quyết định WECG issue #406); WriteToStorage chỉ ghi alarm persistent; đọc từ storage mà thiếu khoá thì coi là persistent; khi đọc lại, CHECK alarm phải persistent. OnExtensionUnloaded xoá alarm khỏi bộ nhớ (không ghi storage), nên alarm non-persistent mất khi extension bị tắt/nạp lại. Cờ kApiAlarmsCreateLengthLimit enabled theo source ("Controls the limit for alarms.create() API input").

Mechanism: Hai thay đổi đi cùng nhau trong cùng file: loại alarm mới theo đề xuất WebExtensions và vòng đời trong bộ nhớ gắn với load/unload. Hành vi mặc định (persistent) giữ như cũ.

Impact: Extension không dùng persistAcrossSessions: không đổi. Extension đặt persistAcrossSessions:false sẽ mất alarm khi trình duyệt khởi động lại hoặc extension bị unload. Giới hạn độ dài: alarms.create với tên/đối số vượt ngưỡng có thể bị từ chối — ngưỡng nằm ngoài file đã đọc.

Conditions: Windows; cờ giới hạn enabled theo source.

Action: Thử alarms.create với persistAcrossSessions false/true, khởi động lại và kiểm tra; thử tên alarm rất dài để thấy giới hạn.

Uncertainties: Chưa đọc nơi áp dụng kApiAlarmsCreateLengthLimit (alarms_api.cc) nên chưa biết ngưỡng.

- `base_feature:ApiAlarmsCreateLengthLimit` · [to: extensions/common/extension_features.cc:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#19): Cờ mới, enabled theo source.
- `file:extensions/browser/api/alarms/alarm_manager.cc` · [from: extensions/browser/api/alarms/alarm_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/api/alarms/alarm_manager.cc), [to: extensions/browser/api/alarms/alarm_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/alarms/alarm_manager.cc): Đã đọc mọi hunk, gồm các hunk chỉ thêm ngoặc {}.
- [to: extensions/browser/api/alarms/alarm_manager.cc:629](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/alarms/alarm_manager.cc#629): Mặc định persistent theo WECG.
- [to: extensions/browser/api/alarms/alarm_manager.cc:578](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/alarms/alarm_manager.cc#578): Xoá alarm khỏi bộ nhớ khi unload.

## 10. chrome.serial liệt kê/mở cổng không bật hộp thoại Bluetooth hệ thống: chỉ thấy cổng Bluetooth đã được cấp quyền

Status: confirmed

Before: 148: SerialPortManager::GetDevices() không có tham số.

After: 151: device.mojom.SerialPortManager.GetDevices nhận bool allow_bluetooth_system_prompt; extensions/browser/api/serial truyền false ở cả hai chỗ gọi (liệt kê và mở cổng).

Mechanism: Chữ ký Mojo mới cho phép bên gọi chọn; extension chọn không bật prompt hệ thống.

Impact: Extension/Chrome App dùng chrome.serial trên Windows sẽ không làm bật hộp thoại quyền Bluetooth của hệ điều hành; cổng serial qua Bluetooth chỉ hiện nếu đã được cấp quyền trước đó.

Conditions: Windows; áp dụng API serial.

Action: Thử chrome.serial.getDevices với một thiết bị serial qua Bluetooth chưa và đã cấp quyền.

- `file:extensions/browser/api/serial/serial_port_manager.cc` · [from: extensions/browser/api/serial/serial_port_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/api/serial/serial_port_manager.cc), [to: extensions/browser/api/serial/serial_port_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/serial/serial_port_manager.cc): Đã đọc mọi hunk: hai chỗ gọi truyền false.
- `mojo_method:device.mojom.SerialPortManager.GetDevices` · [from: services/device/public/mojom/serial.mojom:165](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/device/public/mojom/serial.mojom#165), [to: services/device/public/mojom/serial.mojom:169](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/services/device/public/mojom/serial.mojom#169): Chữ ký Mojo thêm allow_bluetooth_system_prompt.
- `file:services/device/public/mojom/serial.mojom` · [from: services/device/public/mojom/serial.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/device/public/mojom/serial.mojom), [to: services/device/public/mojom/serial.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/services/device/public/mojom/serial.mojom): File mojom dùng chung; chỉ đọc hunk GetDevices, hunk khác không liên quan extension.
- [to: extensions/browser/api/serial/serial_port_manager.cc:82](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/serial/serial_port_manager.cc#82): Truyền false để tránh prompt.

## 11. Namespace browser và hành vi polyfill của runtime.onMessage thành mặc định vĩnh viễn; thêm cờ mở browser cho trang web

Status: confirmed

Before: 148: kExtensionBrowserNamespaceAndPolyfillSupport (enabled) bật object browser và hành vi giống webextension-polyfill cho tin nhắn một lần (listener onMessage trả Promise, lỗi listener trả về người gửi); polyfill_util.cc loại trừ extension có devtools_page.

After: 151: cờ và polyfill_util.cc bị xoá; one_time_message_handler bật hành vi đó không điều kiện cho mọi extension trừ extension có devtools_page, và luôn bật cho trang web (không phải extension). Cờ mới kExtensionBrowserNamespaceOnWebPages (disabled) để mở browser cho trang web ngay cả khi không externally_connectable.

Mechanism: Cờ đã enabled trước khi xoá — khả năng được giữ, không bị bỏ. Ngoại lệ devtools_page vẫn nguyên, chỉ chuyển từ polyfill_util sang one_time_message_handler.

Impact: Không đổi hành vi mặc định so với 148. Mất cách tắt: sản phẩm từng tắt cờ để giữ ngữ nghĩa cũ của onMessage (không coi Promise là phản hồi) không còn tắt được. Cờ mới về trang web tắt mặc định.

Conditions: Windows; hành vi mới không phụ thuộc cờ; kExtensionBrowserNamespaceOnWebPages disabled theo source.

Action: Nếu sản phẩm có extension nội bộ dựa vào việc listener onMessage trả Promise bị bỏ qua, kiểm tra lại; không cần làm gì nếu đã chạy tốt với 148 mặc định.

- `base_feature:ExtensionBrowserNamespaceAndPolyfillSupport` · [from: extensions/common/extension_features.cc:194](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#194): Cờ enabled bị xoá — graduate.
- `base_feature:ExtensionBrowserNamespaceOnWebPages` · [to: extensions/common/extension_features.cc:233](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#233): Cờ mới, disabled theo source.
- `file:extensions/renderer/polyfill_util.cc` · [from: extensions/renderer/polyfill_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/renderer/polyfill_util.cc): File bị xoá ở 151 (upstream_404); chứa ngoại lệ devtools_page của 148.
- `file:extensions/renderer/api/messaging/one_time_message_handler.cc` · [from: extensions/renderer/api/messaging/one_time_message_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/renderer/api/messaging/one_time_message_handler.cc), [to: extensions/renderer/api/messaging/one_time_message_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/api/messaging/one_time_message_handler.cc): Đã đọc mọi hunk: điều kiện chỉ còn devtools_page, trang web luôn true.
- [to: extensions/renderer/api/messaging/one_time_message_handler.cc:105](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/api/messaging/one_time_message_handler.cc#105): 151: chỉ extension có devtools_page (chrome_manifest_urls::GetDevToolsPage không rỗng) bị loại trừ; trang web luôn true.

## 12. webRequest: listener có filter của service worker luôn lưu qua EventRouter; dọn khoá cũ và filter trùng trong Preferences

Status: confirmed

Before: 148: cờ kWebRequestPersistFilteredEventsViaEventRouter (enabled) chọn lưu listener webRequest có filter qua cơ chế chung của EventRouter; khi tắt thì WebRequestEventRouter lưu riêng dưới khoá web_request.filtered_lazy_listeners.

After: 151: cờ bị xoá — chỉ còn cơ chế EventRouter. MigrateObsoleteExtensionPrefs xoá khoá per-extension web_request.filtered_lazy_listeners (ghi "Added 2026-05"); thêm CleanUpDuplicateSubEventFilters chạy lúc khởi động, với mỗi sub-event (vd webRequest.onBeforeRequest/s0) chỉ giữ filter cuối cùng (crbug.com/502402731, TODO gỡ sau M156).

Mechanism: Cờ đã enabled nên đường cũ chết từ trước; 151 xoá đường đó và dọn dữ liệu nó để lại. Việc dọn filter trùng sửa dữ liệu đã tích luỹ trước khi EventRouter::AddFilterToEvent chuyển sang ghi đè.

Impact: Hồ sơ người dùng lâu năm sẽ bị sửa Preferences một lần ở lần chạy đầu 151: filter webRequest trùng bị gộp còn một. Extension service worker dùng webRequest có filter không nên thấy khác biệt; nếu thấy mất sự kiện thì đây là chỗ cần nhìn.

Conditions: Windows; chạy mỗi lần khởi tạo ExtensionPrefs.

Action: Mở một hồ sơ cũ có extension MV3 dùng webRequest filter, chạy 151 và so sánh Preferences trước/sau; kiểm tra sự kiện vẫn tới.

- `base_feature:WebRequestPersistFilteredEventsViaEventRouter` · [from: extensions/common/extension_features.cc:217](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#217): Cờ enabled bị xoá — graduate.
- `file:extensions/browser/extension_prefs.cc` · [from: extensions/browser/extension_prefs.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/extension_prefs.cc), [to: extensions/browser/extension_prefs.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc): Đã đọc mọi hunk: hunk webRequest ở đây; hunk CDP thuộc event:ext-cdp-installed-cleanup, hunk MV2 (pref, khoá mv2_*) thuộc event:ext-mv2-removal.
- [to: extensions/browser/extension_prefs.cc:2621](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc#2621): Dọn filter trùng, chỉ giữ cái cuối.
- [to: extensions/browser/extension_prefs.cc:2671](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_prefs.cc#2671): Khoá cũ của đường lưu riêng bị xoá.

## 13. glicPrivate cho component extension của Glic bật mặc định nhưng chỉ ở Mỹ; thêm quyền glicPrivate.invoke và cấu hình mở tab từ trang Google

Status: confirmed

Before: 148: kApiGlicPrivate disabled; không có quyền glicPrivate.invoke, không có cờ ApiGlicAccessFromPromotionPage, không có param cho ApiGlicAccessFromGoogleWebpage.

After: 151: kApiGlicPrivate enabled theo source, nhưng IsApiGlicPrivateEnabled() (glic_util.cc mới) chỉ trả true khi quốc gia lưu hoặc mới nhất của variations service là "us", trừ khi cờ bị override. Quyền mới glicPrivate.invoke cho component extension Glic (56D158B3…) theo cờ ApiGlicPrivate. Cờ mới kApiGlicAccessFromPromotionPage (disabled). ApiGlicAccessFromGoogleWebpage có bốn param mới: endpoint prompt, OAuth scope chrome.autobrowse.readprompts, yêu cầu consent, và cách mở tab (mặc định foreground nếu chưa consent).

Mechanism: API chỉ cho component extension Glic trong allowlist; cổng quốc gia nằm trong code chứ không trong feature file.

Impact: Không mở API mới cho extension bên thứ ba. Ngoài Mỹ, API không hoạt động dù cờ bật. Sản phẩm downstream có Glic tắt thì không ảnh hưởng.

Conditions: Windows; component extension Glic; quốc gia "us" theo variations service, trừ khi override cờ.

Action: Nếu sản phẩm dùng Glic: kiểm tra với quốc gia khác "us" và với --enable-features=ApiGlicPrivate.

- `base_feature:ApiGlicPrivate` · [from: extensions/common/extension_features.cc:34](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/extension_features.cc#34), [to: extensions/common/extension_features.cc:40](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#40): disabled → enabled theo source.
- `base_feature:ApiGlicAccessFromPromotionPage` · [to: extensions/common/extension_features.cc:48](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#48): Cờ mới, disabled.
- `feature_param:ApiGlicAccessFromGoogleWebpage/glic_open_new_tab_disposition` · [to: extensions/common/extension_features.cc:76](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#76): Param mới chọn cách mở tab.
- `file:chrome/browser/extensions/glic_util.cc` · [to: chrome/browser/extensions/glic_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/glic_util.cc): File mới; đã đọc toàn bộ.
- [to: chrome/browser/extensions/glic_util.cc:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/glic_util.cc#15): Cổng quốc gia US.
- [to: chrome/common/extensions/api/_permission_features.json:443](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/_permission_features.json#443): Quyền mới cho component extension Glic.

## 14. Bốn API riêng mới cho component extension: contextualTasksPrivate, indigoPrivate, dictationPrivate, glicPrivate.invoke; tài nguyên Indigo và AIM eligibility

Status: confirmed

Before: 148: không có các quyền này; APIPermissionID dừng ở 265 và có kWebstorePrivate = 163.

After: 151: APIPermissionID thêm kGlicPrivateInvoke=266, kIndigoPrivate=267, kContextualTasksPrivate=268, kDictationPrivate=269 và đổi 163 thành kDeleted_WebstorePrivate. chrome_api_permissions.cc đăng ký bốn quyền mới; _permission_features.json giới hạn mỗi quyền cho đúng một component extension theo allowlist (contextualTasksPrivate còn theo cờ ApiContextualTasksPrivate disabled). ChromeComponentExtensionResourceManager thêm tài nguyên AIM eligibility và, khi features::kIndigo bật, tài nguyên và chuỗi của extension Indigo. extension_util thêm IsMojoJsEnabledForExtension (chỉ cho component extension AIM eligibility), IsExtensionForceInstalled và GetExtensionsPageUrl. feature_flags.cc đăng ký ApiMimeHandler và ApiContextualTasksPrivate.

Mechanism: Đây là hạ tầng cho các tính năng AI của Chrome chạy dưới dạng component extension; mọi quyền đều bị khoá bằng allowlist ID.

Impact: Extension bên thứ ba không dùng được. Việc đánh số enum là append-only (giá trị cũ giữ nguyên), nên dữ liệu quyền đã lưu không lệch. Downstream thêm quyền riêng vào APIPermissionID phải chọn số sau 269 để không trùng.

Conditions: Windows; theo allowlist và cờ tương ứng.

Action: Nếu sản phẩm có APIPermissionID tuỳ biến, kiểm tra xung đột số 266–269.

- `base_feature:ApiContextualTasksPrivate` · [to: extensions/common/extension_features.cc:38](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#38): Cờ mới, disabled.
- `mojo_enum:extensions.mojom.APIPermissionID` · [from: extensions/common/mojom/api_permission_id.mojom:20](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/api_permission_id.mojom#20), [to: extensions/common/mojom/api_permission_id.mojom:20](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/api_permission_id.mojom#20): Enum thêm bốn giá trị, đánh dấu một giá trị đã xoá.
- `file:extensions/common/mojom/api_permission_id.mojom` · [from: extensions/common/mojom/api_permission_id.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/api_permission_id.mojom), [to: extensions/common/mojom/api_permission_id.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/api_permission_id.mojom): Đã đọc mọi hunk.
- `file:chrome/browser/extensions/chrome_component_extension_resource_manager.cc` · [from: chrome/browser/extensions/chrome_component_extension_resource_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/chrome_component_extension_resource_manager.cc), [to: chrome/browser/extensions/chrome_component_extension_resource_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/chrome_component_extension_resource_manager.cc): Đã đọc mọi hunk: AIM eligibility và Indigo.
- `file:chrome/browser/extensions/extension_util.cc` · [from: chrome/browser/extensions/extension_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/extension_util.cc), [to: chrome/browser/extensions/extension_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/extension_util.cc): Đã đọc mọi hunk: ba hàm mới.
- `file:extensions/common/features/feature_flags.cc` · [from: extensions/common/features/feature_flags.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/features/feature_flags.cc), [to: extensions/common/features/feature_flags.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/features/feature_flags.cc): Đã đọc mọi hunk: đăng ký ApiMimeHandler (event:ext-public-mime-handler), ApiContextualTasksPrivate, bỏ TelemetryExtensionPendingApprovalApi (out_of_scope ChromeOS).
- [to: extensions/common/mojom/api_permission_id.mojom:293](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/api_permission_id.mojom#293): Bốn id mới.
- [to: chrome/common/extensions/api/_permission_features.json:200](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/_permission_features.json#200): Quyền theo allowlist và cờ.

## 15. Hạ tầng gửi sự kiện webRequest chặn một lần mỗi context (cờ mới, tắt mặc định) và dispatch handler trong renderer

Status: confirmed

Before: 148: renderer chỉ có emitter và argument massager theo tên sự kiện; không có cờ kWebRequestPerContextEventDispatch.

After: 151: cờ mới (disabled) — khi bật, browser gửi sự kiện webRequest chặn một lần mỗi context bằng tên sự kiện gốc thay vì một lần mỗi listener, renderer tự khớp listener và báo kết quả qua webRequestInternal.eventHandled/eventHandlingDone. APIEventHandler có map dispatch_handlers và RegisterEventDispatchHandler (lộ qua APIBindingJSUtil.registerEventDispatchHandler); FireEvent chuyển toàn bộ dispatch cho handler nếu có. Thêm kiểm tra context còn hợp lệ sau khi chuyển đổi đối số (tránh dùng context đã bị huỷ khi getter JS chạy lại).

Mechanism: Phần renderer là hạ tầng chung; nó chỉ có tác dụng khi cờ bật. Kiểm tra IsContextValid là sửa lỗi độc lập áp dụng ngay.

Impact: Mặc định không đổi hành vi. Khi Google bật cờ qua Finch, cách webRequest chặn được gửi đổi căn bản — sản phẩm có patch webRequest cần theo dõi.

Conditions: Windows; cờ disabled theo source.

Action: Theo dõi trạng thái Finch của WebRequestPerContextEventDispatch; nếu bật cho sản phẩm, chạy lại test webRequest blocking.

Uncertainties: Chưa đọc phía browser của per-context dispatch (ngoài file đã đọc).

- `base_feature:WebRequestPerContextEventDispatch` · [to: extensions/common/extension_features.cc:89](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#89): Cờ mới, disabled theo source.
- `file:extensions/renderer/bindings/api_event_handler.cc` · [from: extensions/renderer/bindings/api_event_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/renderer/bindings/api_event_handler.cc), [to: extensions/renderer/bindings/api_event_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/bindings/api_event_handler.cc): Đã đọc mọi hunk: dispatch handler, BuildArgumentsArray, kiểm tra context.
- `file:extensions/renderer/bindings/api_binding_js_util.cc` · [from: extensions/renderer/bindings/api_binding_js_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/renderer/bindings/api_binding_js_util.cc), [to: extensions/renderer/bindings/api_binding_js_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/bindings/api_binding_js_util.cc): Đã đọc mọi hunk: registerEventDispatchHandler.
- [to: extensions/common/extension_features.h:322](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.h#322): Mô tả cơ chế per-context.
- [to: extensions/renderer/bindings/api_event_handler.cc:320](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/bindings/api_event_handler.cc#320): Handler nhận toàn bộ dispatch.

## 16. protocol_handlers của extension tôn trọng quyền chạy ẩn danh và mỗi profile (kể cả OTR) cập nhật registry của chính nó

Status: confirmed

Before: 148: RegisterHandlersIfNeeded đăng ký handler không xét incognito; OnExtensionLoaded/Unloaded dùng browser_context được truyền vào — với manager của OTR, context đó bị ExtensionRegistry chuyển về profile thường.

After: 151: đăng ký kèm allowed_in_incognito = ExtensionPrefs::IsIncognitoEnabled(extension); OnExtensionLoaded/Unloaded dùng browser_context_ của chính manager.

Mechanism: Sửa hai lỗi cùng lúc: handler của extension không bật ẩn danh không nên hoạt động trong cửa sổ ẩn danh, và registry OTR trước đây không được cập nhật đúng.

Impact: Chỉ có tác dụng khi kExtensionProtocolHandlers bật (disabled theo source ở 151). Khi bật: handler giao thức của extension chỉ chạy trong ẩn danh nếu người dùng cho phép extension chạy ẩn danh.

Conditions: Windows; cần kExtensionProtocolHandlers (disabled theo source).

Action: Nếu sản phẩm bật kExtensionProtocolHandlers: kiểm tra handler trong cửa sổ thường và ẩn danh.

- `file:extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc` · [from: extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc), [to: extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc): Đã đọc mọi hunk.
- [to: extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc:117](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/api/protocol_handlers/protocol_handlers_manager.cc#117): Đăng ký kèm quyền ẩn danh.
- [to: extensions/common/extension_features.cc:145](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#145): Cờ vẫn disabled theo source.

## 17. Yêu cầu quyền truy cập site của extension có kết quả trả về và thời gian chờ khi gỡ

Status: confirmed

Before: 148: AddHostAccessRequest không trả gì; RemoveHostAccessRequest trả bool.

After: 151: AddHostAccessRequest trả AddRequestResult, observer chỉ được báo khi thành công; RemoveHostAccessRequest trả RemoveRequestResult và nhận bypass_cooldown (các đường gỡ nội bộ truyền true). Thêm Shutdown() báo OnPermissionsManagerShutdown.

Mechanism: Hạ tầng cho cơ chế cooldown của API permissions.addHostAccessRequest (kApiPermissionsHostAccessRequests enabled theo source).

Impact: Extension gọi addHostAccessRequest/removeHostAccessRequest liên tục có thể bị cooldown từ chối; chi tiết cooldown nằm trong helper ngoài file đã đọc.

Conditions: Windows; kApiPermissionsHostAccessRequests enabled.

Action: Thử thêm/gỡ yêu cầu quyền nhanh liên tiếp.

Uncertainties: Chưa đọc HostAccessRequestsHelper nên chưa biết độ dài cooldown.

- `file:extensions/browser/permissions_manager.cc` · [from: extensions/browser/permissions_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/permissions_manager.cc), [to: extensions/browser/permissions_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/permissions_manager.cc): Đã đọc mọi hunk.
- [to: extensions/browser/permissions_manager.cc:889](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/permissions_manager.cc#889): Đường gỡ nội bộ bỏ qua cooldown.

## 18. chrome://extensions theo giao diện webui refresh 2026 và icon bo tròn

Status: confirmed

Before: 148: extensions.html không có thuộc tính refresh; icon mặc định của extension là kExtensionIcon.

After: 151: chrome://extensions nhận chuỗi webuiRefresh2026 và roundedIconsAttribute trên <html>, thêm ThemeSource, ExtensionsUI kế thừa MojoWebUIController (enable_chrome_send); icon mặc định chọn kExtensionFilledIcon khi IsRoundedIconsEnabled(), ngược lại kExtensionOldIcon.

Mechanism: Cùng cơ chế refresh 2026 đã thấy ở Settings.

Impact: Đổi giao diện khi các cờ UI bật; không đổi chức năng.

Conditions: Windows; phụ thuộc IsWebuiRefresh2026Enabled và IsRoundedIconsEnabled.

Action: Xem chrome://extensions với hai cờ bật/tắt.

- `webui_gate:extensions_ui/webuiRefresh2026` · [to: chrome/browser/ui/webui/extensions/extensions_ui.cc:510](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extensions_ui.cc#510): Chuỗi mới.
- `file:chrome/browser/resources/extensions/extensions.html` · [from: chrome/browser/resources/extensions/extensions.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/extensions/extensions.html), [to: chrome/browser/resources/extensions/extensions.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/extensions/extensions.html): Đã đọc mọi hunk.
- `file:extensions/browser/extension_icon_manager.cc` · [from: extensions/browser/extension_icon_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/extension_icon_manager.cc), [to: extensions/browser/extension_icon_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_icon_manager.cc): Đã đọc hunk duy nhất.
- [to: extensions/browser/extension_icon_manager.cc:96](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/extension_icon_manager.cc#96): Icon mặc định theo cờ.

## 19. Thanh extension của WebUI toolbar: extensions_bar.mojom chuyển sang components/browser_apis, icon truyền bằng IconHandle thay data URL

Status: confirmed

Before: 148: extensions_bar.mojom nằm ở chrome/browser/ui/webui_browser; ExtensionActionInfo mang data_url_for_icon (url); Page.ActionsAddedOrUpdated(actions), ActionRemoved(id); phía WebUI vẽ icon bằng <div id="icon">.

After: 151: file cũ bị xoá; cùng module extensions_bar.mojom nay ở components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom và struct ở extensions_bar_data_model.mojom. ExtensionActionInfo thay data_url_for_icon bằng toolbar_ui_api.mojom.IconHandle icon; ActionsAddedOrUpdated và ActionRemoved nhận thêm mảng IconUpdate. WebUIToolbarExtensionsContainer mới (488 dòng) cài PageHandler cho toolbar WebUI, kèm menu ngữ cảnh, pop-out, và hai phần tử webui-toolbar-extension(s) mới dùng icon-from-table.

Mechanism: Mười finding declaration_moved là cùng interface/method/field đổi file; ba finding thật sự đổi nội dung là data_url_for_icon bị bỏ, icon mới và hai chữ ký có IconUpdate. Icon được gửi một lần qua bảng icon dùng chung rồi tham chiếu bằng handle.

Impact: Không ảnh hưởng toolbar Views mặc định. Chỉ liên quan khi dùng WebUI toolbar/WebUI browser thử nghiệm. Downstream có code nói chuyện với extensions_bar.mojom phải đổi import và cách gửi icon.

Conditions: Windows; phụ thuộc cấu hình WebUI toolbar/browser (thử nghiệm) — chưa đọc cờ bật nó.

Action: Nếu sản phẩm dùng WebUI toolbar, kiểm tra icon extension, click, menu ngữ cảnh và pop-out.

Uncertainties: Chưa xác định cờ bật WebUI toolbar trên Windows.

- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.accessible_name` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:16](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#16), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#15): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.data_url_for_icon` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:22](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#22): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.icon` · [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:21](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#21): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.id` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#15), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:14](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#14): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.is_visible` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:21](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#21), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:20](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#20): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_field:extensions_bar.mojom.ExtensionActionInfo.tooltip` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#17), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:16](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#16): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_interface:extensions_bar.mojom.Page` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:50](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#50), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:38](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#38): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_interface:extensions_bar.mojom.PageHandler` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:36](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#36), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:24](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#24): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_interface:extensions_bar.mojom.PageHandlerFactory` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:29](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#29), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#17): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.Page.ActionPoppedOut` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:61](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#61), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:50](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#50): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.Page.ActionRemoved` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:55](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#55), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:44](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#44): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.Page.ActionsAddedOrUpdated` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:52](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#52), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:40](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#40): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.PageHandler.ExecuteUserAction` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:38](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#38), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:26](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#26): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.PageHandler.ShowContextMenu` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:43](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#43), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:31](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#31): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.PageHandler.ToggleExtensionsMenuFromWebUI` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:46](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#46), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:34](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#34): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_method:extensions_bar.mojom.PageHandlerFactory.CreatePageHandler` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:31](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#31), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#19): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `mojo_struct:extensions_bar.mojom.ExtensionActionInfo` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:11](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#11), [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom:10](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom#10): Khai báo đổi file (declaration_moved) hoặc đổi nội dung như mechanism.
- `file:chrome/browser/ui/webui_browser/extensions_bar.mojom` · [from: chrome/browser/ui/webui_browser/extensions_bar.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom): File 148 bị xoá ở 151 (upstream_404).
- `file:components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom` · [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom): File mới; đã đọc toàn bộ.
- `file:components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom` · [to: components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar_data_model.mojom): File mới; đã đọc toàn bộ.
- `file:chrome/browser/ui/webui/webui_toolbar/webui_toolbar_extensions_container.cc` · [to: chrome/browser/ui/webui/webui_toolbar/webui_toolbar_extensions_container.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/webui_toolbar/webui_toolbar_extensions_container.cc): File mới; đã đọc các hàm chính (ToMojo, ContextMenu, Bind, Notify*).
- `file:chrome/browser/resources/webui_toolbar/extension.html.ts` · [to: chrome/browser/resources/webui_toolbar/extension.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/webui_toolbar/extension.html.ts): File mới; đã đọc toàn bộ.
- `file:chrome/browser/resources/webui_toolbar/extensions.html.ts` · [to: chrome/browser/resources/webui_toolbar/extensions.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/webui_toolbar/extensions.html.ts): File mới; đã đọc toàn bộ.
- `file:chrome/browser/resources/webui_browser/extension.html.ts` · [from: chrome/browser/resources/webui_browser/extension.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/webui_browser/extension.html.ts), [to: chrome/browser/resources/webui_browser/extension.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/webui_browser/extension.html.ts): Đã đọc hunk duy nhất: icon-from-table thay div.
- [to: components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom:40](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/browser_apis/ui_controllers/toolbar/extensions_bar.mojom#40): 151: gửi kèm IconUpdate.
- [from: chrome/browser/ui/webui_browser/extensions_bar.mojom:22](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui_browser/extensions_bar.mojom#22): 148: icon là data URL.

## 20. Cờ mới cho component extension dùng chrome://resources trong worker, bật mặc định

Status: confirmed

Before: 148: không có cờ kComponentExtensionAllowWorkerChromeResources.

After: 151: cờ enabled theo source, mô tả "Controls whether component extensions are allowed to use chrome://resources/ URLs in worker scripts and subresources".

Mechanism: Cờ kiểm soát một khả năng chỉ cho component extension.

Impact: Không ảnh hưởng extension bên thứ ba. Component extension (kể cả của sản phẩm) có thể nạp chrome://resources trong worker.

Conditions: Windows; enabled theo source.

Action: Không cần hành động trừ khi sản phẩm có component extension dùng worker.

Uncertainties: Không tìm thấy nơi đọc cờ trong cache 151 (grep ra rỗng ngoài khai báo) — consumer nằm ngoài inventory đã cache.

- `base_feature:ComponentExtensionAllowWorkerChromeResources` · [to: extensions/common/extension_features.cc:105](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#105): Cờ mới, enabled theo source.
- [to: extensions/common/extension_features.h:132](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.h#132): Mô tả cờ.

## 21. Param mới unlimited_shows cho hộp thoại chọn công cụ tìm kiếm khi extension đổi DSE (cờ cha vẫn tắt)

Status: confirmed

Before: 148: kSearchEngineExplicitChoiceDialog chỉ có param escapable.

After: 151: thêm param bool unlimited_shows mặc định true: hộp thoại hiện lại cho tới khi người dùng chọn thay vì một lần mỗi phiên.

Mechanism: Chỉnh hành vi của một hộp thoại đang thử nghiệm.

Impact: Không đổi mặc định vì kSearchEngineExplicitChoiceDialog vẫn disabled theo source.

Conditions: Windows; cờ cha disabled.

Action: Theo dõi Finch của SearchEngineExplicitChoiceDialog.

- `feature_param:SearchEngineExplicitChoiceDialog/unlimited_shows` · [to: extensions/common/extension_features.cc:253](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#253): Param mới, mặc định true.
- [to: extensions/common/extension_features.cc:244](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/extension_features.cc#244): Cờ cha disabled.

## 22. pdfViewerPrivate.getTextInfo mới cho chú thích văn bản Ink2 của PDF viewer

Status: confirmed

Before: 148: không có getTextInfo, Typeface, GetTextInfoResult; không có struct pdf.mojom.InkTextInfo.

After: 151: pdfViewerPrivate.getTextInfo(textarea, knownFontIds) trả typeface (serialized SkTypeface, bỏ qua font đã biết) và InkTextInfo đã serialize; pdf.mojom thêm struct InkTextInfo (effective_zoom, primary_ascent, text_runs) với EnableIf=enable_pdf_ink2.

Mechanism: API riêng của component extension PDF viewer để đo chữ trong textarea cho tính năng thêm văn bản của Ink2.

Impact: Chỉ PDF viewer dùng. Có hiệu lực khi build có enable_pdf_ink2 (platform_state Windows: conditional).

Conditions: Windows; điều kiện build enable_pdf_ink2.

Action: Nếu sản phẩm patch PDF viewer: kiểm tra chú thích văn bản Ink2.

Uncertainties: Chưa đọc giá trị enable_pdf_ink2 của build sản phẩm.

- `file:chrome/common/extensions/api/pdf_viewer_private.idl` · [from: chrome/common/extensions/api/pdf_viewer_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/pdf_viewer_private.idl), [to: chrome/common/extensions/api/pdf_viewer_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/pdf_viewer_private.idl): Đã đọc mọi hunk.
- `mojo_struct:pdf.mojom.InkTextInfo` · [to: pdf/mojom/pdf.mojom:128](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/pdf/mojom/pdf.mojom#128): Struct mới theo enable_pdf_ink2.
- `mojo_field:pdf.mojom.InkTextInfo.effective_zoom` · [to: pdf/mojom/pdf.mojom:134](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/pdf/mojom/pdf.mojom#134): Trường mới.
- `mojo_field:pdf.mojom.InkTextInfo.primary_ascent` · [to: pdf/mojom/pdf.mojom:136](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/pdf/mojom/pdf.mojom#136): Trường mới.
- `mojo_field:pdf.mojom.InkTextInfo.text_runs` · [to: pdf/mojom/pdf.mojom:130](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/pdf/mojom/pdf.mojom#130): Trường mới.
- [to: chrome/common/extensions/api/pdf_viewer_private.idl:148](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/pdf_viewer_private.idl#148): Hàm mới.

## 23. autofillPrivate: entity Autofill AI có loại pass (public/private) và cờ chỉ đọc

Status: confirmed

Before: 148: EntityType không có passType; entity instance không có isReadOnly; AutofillAI util tự điền từng trường type.

After: 151: enum EntityPassType {PUBLIC_PASS, PRIVATE_PASS}; EntityType.passType tuỳ chọn; EntityInstance(WithLabels).isReadOnly; util dùng EntityTypeToPrivateApiEntityType và gán hộ chiếu/bằng lái/CMND/KTN/redress là private pass, xe/đặt vé máy bay là public pass, đơn hàng/vận chuyển không có pass.

Mechanism: API riêng của trang Settings (Your saved info) mở rộng để hiển thị thông tin Wallet pass.

Impact: Chỉ WebUI Settings dùng. WebUI downstream đọc autofillPrivate nhận thêm trường mới; không có trường bị xoá.

Conditions: Windows.

Action: Không cần hành động trừ khi có WebUI tuỳ biến dùng autofillPrivate.

- `file:chrome/common/extensions/api/autofill_private.idl` · [from: chrome/common/extensions/api/autofill_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/autofill_private.idl), [to: chrome/common/extensions/api/autofill_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/autofill_private.idl): Đã đọc mọi hunk (bỏ NAME_LAST_PREFIX/CORE khỏi enum là thay đổi thứ hai, cũng trong file này).
- `file:chrome/browser/extensions/api/autofill_private/autofill_ai_util.cc` · [from: chrome/browser/extensions/api/autofill_private/autofill_ai_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/api/autofill_private/autofill_ai_util.cc), [to: chrome/browser/extensions/api/autofill_private/autofill_ai_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/api/autofill_private/autofill_ai_util.cc): Đã đọc mọi hunk.
- [to: chrome/common/extensions/api/autofill_private.idl:190](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/autofill_private.idl#190): Enum mới.

## 24. passwordsPrivate: credential có isAutomaticPasswordChangeSupported

Status: confirmed

Before: 148: không có trường này.

After: 151: PasswordUiEntry thêm boolean isAutomaticPasswordChangeSupported (bắt buộc).

Mechanism: API riêng của Password Manager WebUI báo credential nào hỗ trợ đổi mật khẩu tự động.

Impact: Chỉ WebUI Password Manager dùng; WebUI tuỳ biến nhận thêm trường.

Conditions: Windows.

Action: Không cần hành động trừ khi có WebUI tuỳ biến.

- `file:chrome/common/extensions/api/passwords_private.idl` · [from: chrome/common/extensions/api/passwords_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/passwords_private.idl), [to: chrome/common/extensions/api/passwords_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/passwords_private.idl): Đã đọc hunk duy nhất.
- [to: chrome/common/extensions/api/passwords_private.idl:286](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/passwords_private.idl#286): Trường mới.

## 25. settingsPrivate: danh sách pref cho chrome://settings đổi theo các trang Settings mới; pref Glic không còn phụ thuộc cờ và bỏ hai pref auto browse

Status: confirmed

Before: 148: allowlist gồm pref xoá dữ liệu kiểu Basic, pref tab organization, tab_search right aligned; nhóm pref Glic chỉ được thêm khi GlicEnabling::IsEnabledByFlags() và gồm kGlicUserEnabledActuationOnWeb, kGlicExperimentalTriggeringEnabled.

After: 151: thêm pref email verification (enabled/state), shopping entities, personal context autofill toggle, Gmail OTP (khi kGlicActorAutofillOneTimePassword bật), bookmark_bar.visibility_state, side panel alignment overrides, ctrl+tab MRU, drive consent, HTTPS-first toast, cpu tier override, skills, contextual cueing, smart tab sharing; bỏ các pref Basic của xoá dữ liệu, tab organization, tab search right aligned. Nhóm pref Glic luôn được thêm, có thêm media understanding, và không còn user_enabled_actuation_on_web / experimental_triggering_enabled.

Mechanism: settingsPrivate là cầu nối pref của trang Settings; danh sách đổi theo đúng các thay đổi của review Settings (docs/reviews/chromium-148-to-151-settings). Việc bỏ hai pref Glic khớp với việc chúng chuyển sang header internal, chỉ GlicEnabling được đọc/ghi.

Impact: WebUI downstream đọc/ghi các pref đã bỏ qua chrome.settingsPrivate sẽ nhận lỗi pref không có trong allowlist. Pref mới có sẵn cho WebUI Settings tuỳ biến.

Conditions: Windows; một số mục phụ thuộc cờ (Gmail OTP theo kGlicActorAutofillOneTimePassword, disabled).

Action: Grep WebUI downstream cho các pref đã bỏ khỏi allowlist.

- `file:chrome/browser/extensions/api/settings_private/prefs_util.cc` · [from: chrome/browser/extensions/api/settings_private/prefs_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/api/settings_private/prefs_util.cc), [to: chrome/browser/extensions/api/settings_private/prefs_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/api/settings_private/prefs_util.cc): Đã đọc mọi hunk, gồm các hunk ChromeOS (timezone, ash::prefs) chỉ đổi namespace.
- `base_feature:GlicActorAutofillOneTimePassword` · [to: chrome/common/chrome_features.cc:1016](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/chrome_features.cc#1016): Cờ mới (disabled) gate pref Gmail OTP trong allowlist.
- [from: chrome/browser/extensions/api/settings_private/prefs_util.cc:1341](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/api/settings_private/prefs_util.cc#1341): 148: pref Glic theo cờ, gồm hai pref auto browse.

## 26. Mojo EventRouter: thông tin service worker tách khỏi EventListener thành tham số bắt buộc của Add/RemoveListenerForServiceWorker

Status: confirmed

Before: 148: struct EventListener có trường tuỳ chọn ServiceWorkerContext? service_worker_context, chỉ có khi listener do service worker thêm; AddListenerForServiceWorker và RemoveListenerForServiceWorker nhận một EventListener.

After: 151: trường đó bị xoá khỏi EventListener; hai method nhận thêm tham số ServiceWorkerContext service_worker_context (không nullable).

Mechanism: Kiểu dữ liệu nói thẳng "listener của service worker luôn có context" thay vì dựa vào trường nullable. Đây là IPC renderer → browser trong cùng một bản build.

Impact: Không đổi hành vi. Code downstream gọi hoặc cài đặt extensions::mojom::EventRouter (ví dụ patch trong EventRouter hoặc renderer bindings) phải đổi chữ ký; hai tiến trình luôn cùng bản build nên không có vấn đề lệch phiên bản.

Conditions: Windows; áp dụng mọi extension service worker.

Action: Grep downstream cho AddListenerForServiceWorker/RemoveListenerForServiceWorker và service_worker_context; biên dịch lại.

- `mojo_method:extensions.mojom.EventRouter.AddListenerForServiceWorker` · [from: extensions/common/mojom/event_router.mojom:51](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/event_router.mojom#51), [to: extensions/common/mojom/event_router.mojom:48](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/event_router.mojom#48): Chữ ký thêm ServiceWorkerContext.
- `mojo_method:extensions.mojom.EventRouter.RemoveListenerForServiceWorker` · [from: extensions/common/mojom/event_router.mojom:89](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/event_router.mojom#89), [to: extensions/common/mojom/event_router.mojom:87](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/event_router.mojom#87): Chữ ký thêm ServiceWorkerContext.
- `mojo_field:extensions.mojom.EventListener.service_worker_context` · [from: extensions/common/mojom/event_router.mojom:37](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/event_router.mojom#37): Trường nullable bị xoá khỏi EventListener.
- `file:extensions/common/mojom/event_router.mojom` · [from: extensions/common/mojom/event_router.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/mojom/event_router.mojom), [to: extensions/common/mojom/event_router.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/event_router.mojom): Đã đọc mọi hunk của file.
- [to: extensions/common/mojom/event_router.mojom:48](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/mojom/event_router.mojom#48): 151: tham số context bắt buộc.

## 27. Loader của extension theo API mạng mới: FollowRedirect nhận HttpRequestHeadersUpdateParams, OnBeforeSendHeaders nhận URL, child id thành ChildProcessId

Status: confirmed

Before: 148: URLLoader.FollowRedirect(removed_headers, modified_headers, modified_cors_exempt_headers, new_url); TrustedHeaderClient.OnBeforeSendHeaders(headers); chrome_url_request_util và url_request_util dùng int child_id.

After: 151: FollowRedirect(HttpRequestHeadersUpdateParams, new_url); OnBeforeSendHeaders(request_url, headers) trả thêm extended_net_log_events; loader tài nguyên extension đổi chữ ký theo, trả bytes rỗng khi resource null; url_request_util dùng content::ChildProcessId (còn GetUnsafeValue tạm, crbug.com/379869738).

Mechanism: Extension là consumer của hai method Mojo mạng này (loader tài nguyên chrome-extension://, proxy webRequest).

Impact: Không đổi hành vi. Downstream có URLLoader hoặc TrustedHeaderClient tuỳ biến trong code extension phải đổi chữ ký.

Conditions: Windows.

Action: Grep downstream cho FollowRedirect và OnBeforeSendHeaders.

- `mojo_method:network.mojom.URLLoader.FollowRedirect` · [from: services/network/public/mojom/url_loader.mojom:46](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/network/public/mojom/url_loader.mojom#46), [to: services/network/public/mojom/url_loader.mojom:46](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/services/network/public/mojom/url_loader.mojom#46): Chữ ký đổi.
- `mojo_method:network.mojom.TrustedHeaderClient.OnBeforeSendHeaders` · [from: services/network/public/mojom/network_context.mojom:175](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/network/public/mojom/network_context.mojom#175), [to: services/network/public/mojom/network_context.mojom:187](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/services/network/public/mojom/network_context.mojom#187): Chữ ký đổi.
- `file:chrome/browser/extensions/chrome_url_request_util.cc` · [from: chrome/browser/extensions/chrome_url_request_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/chrome_url_request_util.cc), [to: chrome/browser/extensions/chrome_url_request_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/chrome_url_request_util.cc): Đã đọc mọi hunk.
- `file:extensions/browser/url_request_util.cc` · [from: extensions/browser/url_request_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/url_request_util.cc), [to: extensions/browser/url_request_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/url_request_util.cc): Đã đọc mọi hunk.
- `file:services/network/public/mojom/url_loader.mojom` · [from: services/network/public/mojom/url_loader.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/network/public/mojom/url_loader.mojom), [to: services/network/public/mojom/url_loader.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/services/network/public/mojom/url_loader.mojom): File mojom dùng chung; chỉ đọc hunk FollowRedirect.
- [to: chrome/browser/extensions/chrome_url_request_util.cc:134](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/chrome_url_request_util.cc#134): Loader theo chữ ký mới.

## 28. Schema API chuyển định dạng: ba file .idl thành .webidl và scripting.idl dời sang //extensions

Status: confirmed

Before: 148: api_sources.gni liệt kê enterprise_reporting_private.idl, experimental_actor.idl, experimental_ai_data.idl, scripting.idl dưới chrome/common/extensions/api; _api_features.json của chrome có mục scripting và scripting.globalParams.

After: 151: ba file đó được liệt kê dạng .webidl; scripting.idl không còn ở chrome/ mà có ở extensions/common/api/scripting.idl với nội dung giống hệt (khác duy nhất một số crbug trong comment), mục scripting chuyển sang _api_features.json của //extensions. Các namespace enterprise.reportingPrivate, experimentalActor, experimentalAiData vẫn có trong _api_features.json 151.

Mechanism: Đổi định dạng và vị trí nguồn schema, không đổi API.

Impact: Không đổi hành vi. Downstream patch vào các file .idl này hoặc tham chiếu đường dẫn cũ trong GN sẽ không áp được.

Conditions: Windows.

Action: Chuyển patch schema downstream sang file .webidl mới và extensions/common/api/scripting.idl.

- `file:chrome/common/extensions/api/enterprise_reporting_private.idl` · [from: chrome/common/extensions/api/enterprise_reporting_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/enterprise_reporting_private.idl): File .idl không còn ở 151 (upstream_404); api_sources.gni liệt kê .webidl.
- `file:chrome/common/extensions/api/experimental_actor.idl` · [from: chrome/common/extensions/api/experimental_actor.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/experimental_actor.idl): Như trên.
- `file:chrome/common/extensions/api/experimental_ai_data.idl` · [from: chrome/common/extensions/api/experimental_ai_data.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/experimental_ai_data.idl): Như trên.
- `file:chrome/common/extensions/api/scripting.idl` · [from: chrome/common/extensions/api/scripting.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/scripting.idl): Không còn ở chrome/ ở 151.
- `file:extensions/common/api/scripting.idl` · [to: extensions/common/api/scripting.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/scripting.idl): Có mới ở //extensions; nội dung so với bản chrome/ 148 chỉ khác một số crbug.
- [to: chrome/common/extensions/api/api_sources.gni:86](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/api_sources.gni#86): 151 liệt kê .webidl.
- [to: extensions/common/api/_api_features.json:739](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/_api_features.json#739): Mục scripting ở //extensions.

## 29. API webrtcAudioPrivate (Hangouts) bị xoá hoàn toàn

Status: confirmed

Before: 148: schema webrtc_audio_private.idl, quyền webrtcAudioPrivate (allowlist Hangouts và extension test) và mục API.

After: 151: schema, quyền trong chrome_api_permissions.cc, mục _permission_features.json và _api_features.json đều bị xoá.

Mechanism: API riêng chỉ phục vụ Hangout Services component extension bị gỡ.

Impact: Không ảnh hưởng extension bên thứ ba. Downstream có extension allowlist dùng webrtcAudioPrivate sẽ mất API.

Conditions: Windows.

Action: Grep extension nội bộ cho chrome.webrtcAudioPrivate.

- `file:chrome/common/extensions/api/webrtc_audio_private.idl` · [from: chrome/common/extensions/api/webrtc_audio_private.idl](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/webrtc_audio_private.idl): File bị xoá ở 151 (upstream_404).
- [from: chrome/common/extensions/permissions/chrome_api_permissions.cc:196](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/permissions/chrome_api_permissions.cc#196): 148: quyền được đăng ký — không còn ở 151.
- [from: chrome/common/extensions/api/api_sources.gni:48](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/api_sources.gni#48): 148: schema được biên dịch.

## 30. API manifest nội bộ: Manifest::Type thành enum class, dữ liệu manifest trả const, manifest_url_handlers.h và managed_installation_mode.h dời chỗ, AppURLsHandler tách file

Status: confirmed

Before: 148: Manifest::TYPE_* hằng số; GetManifestData trả con trỏ không const được static_cast thành kiểu thường; include extensions/common/manifest_url_handlers.h và chrome/browser/extensions/managed_installation_mode.h.

After: 151: Manifest::Type::k*; mọi manifest handler cast sang con trỏ const; include extensions/common/manifest_handlers/manifest_url_handlers.h và extensions/browser/managed_installation_mode.h; AppURLsHandler (parse web URLs của hosted app) nằm ở file mới extensions/common/manifest_handlers/app_urls_handler.cc.

Mechanism: Tái cấu trúc cơ học trên toàn bộ //extensions.

Impact: Không đổi hành vi. Mọi patch downstream đụng manifest handler hoặc dùng Manifest::TYPE_* không biên dịch.

Conditions: Windows.

Action: Chạy lại patch downstream và sửa tên enum/include.

Uncertainties: Không tìm thấy AppURLsHandler ở cache 148 nên chưa xác định file gốc của nó.

- `file:extensions/common/manifest_handlers/app_urls_handler.cc` · [to: extensions/common/manifest_handlers/app_urls_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/app_urls_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/chrome_url_overrides_handler.cc` · [from: extensions/common/manifest_handlers/chrome_url_overrides_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/chrome_url_overrides_handler.cc), [to: extensions/common/manifest_handlers/chrome_url_overrides_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/chrome_url_overrides_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/content_capabilities_handler.cc` · [from: extensions/common/manifest_handlers/content_capabilities_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/content_capabilities_handler.cc), [to: extensions/common/manifest_handlers/content_capabilities_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/content_capabilities_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/content_scripts_handler.cc` · [from: extensions/common/manifest_handlers/content_scripts_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/content_scripts_handler.cc), [to: extensions/common/manifest_handlers/content_scripts_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/content_scripts_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/default_locale_handler.cc` · [from: extensions/common/manifest_handlers/default_locale_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/default_locale_handler.cc), [to: extensions/common/manifest_handlers/default_locale_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/default_locale_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/devtools_page_handler.cc` · [from: extensions/common/manifest_handlers/devtools_page_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/devtools_page_handler.cc), [to: extensions/common/manifest_handlers/devtools_page_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/devtools_page_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/icon_variants_handler.cc` · [from: extensions/common/manifest_handlers/icon_variants_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/icon_variants_handler.cc), [to: extensions/common/manifest_handlers/icon_variants_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/icon_variants_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/icons_handler.cc` · [from: extensions/common/manifest_handlers/icons_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/icons_handler.cc), [to: extensions/common/manifest_handlers/icons_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/icons_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/manifest_handlers/input_components_handler.cc` · [from: extensions/common/manifest_handlers/input_components_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/input_components_handler.cc), [to: extensions/common/manifest_handlers/input_components_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/input_components_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/api/bluetooth/bluetooth_manifest_handler.cc` · [from: extensions/common/api/bluetooth/bluetooth_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/bluetooth/bluetooth_manifest_handler.cc), [to: extensions/common/api/bluetooth/bluetooth_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/bluetooth/bluetooth_manifest_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/api/commands/commands_handler.cc` · [from: extensions/common/api/commands/commands_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/commands/commands_handler.cc), [to: extensions/common/api/commands/commands_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/commands/commands_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/api/declarative_net_request/dnr_manifest_handler.cc` · [from: extensions/common/api/declarative_net_request/dnr_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/declarative_net_request/dnr_manifest_handler.cc), [to: extensions/common/api/declarative_net_request/dnr_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/declarative_net_request/dnr_manifest_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/api/sockets/sockets_manifest_handler.cc` · [from: extensions/common/api/sockets/sockets_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/sockets/sockets_manifest_handler.cc), [to: extensions/common/api/sockets/sockets_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/sockets/sockets_manifest_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/common/api/speech/tts_engine_manifest_handler.cc` · [from: extensions/common/api/speech/tts_engine_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/api/speech/tts_engine_manifest_handler.cc), [to: extensions/common/api/speech/tts_engine_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/api/speech/tts_engine_manifest_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:chrome/common/extensions/api/omnibox/omnibox_handler.cc` · [from: chrome/common/extensions/api/omnibox/omnibox_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/api/omnibox/omnibox_handler.cc), [to: chrome/common/extensions/api/omnibox/omnibox_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/api/omnibox/omnibox_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:chrome/common/extensions/manifest_handlers/settings_overrides_handler.cc` · [from: chrome/common/extensions/manifest_handlers/settings_overrides_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/manifest_handlers/settings_overrides_handler.cc), [to: chrome/common/extensions/manifest_handlers/settings_overrides_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/manifest_handlers/settings_overrides_handler.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:chrome/browser/ui/webui/extensions/extension_basic_info.cc` · [from: chrome/browser/ui/webui/extensions/extension_basic_info.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extension_basic_info.cc), [to: chrome/browser/ui/webui/extensions/extension_basic_info.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extension_basic_info.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:chrome/browser/ui/webui/extensions/extensions_internals_source.cc` · [from: chrome/browser/ui/webui/extensions/extensions_internals_source.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions/extensions_internals_source.cc), [to: chrome/browser/ui/webui/extensions/extensions_internals_source.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions/extensions_internals_source.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:extensions/browser/ui_util.cc` · [from: extensions/browser/ui_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/browser/ui_util.cc), [to: extensions/browser/ui_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/browser/ui_util.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.
- `file:chrome/browser/extensions/external_install_manager.cc` · [from: chrome/browser/extensions/external_install_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/external_install_manager.cc), [to: chrome/browser/extensions/external_install_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/external_install_manager.cc): Đã đọc mọi hunk: const cast, đổi tên enum hoặc include như mechanism.

## 31. Code extension theo tái cấu trúc Browser: bỏ browser_finder.h, browser_navigator dời sang ui/navigator/, BrowserWindow::FromBrowser

Status: confirmed

Before: 148: include chrome/browser/ui/browser_finder.h và chrome/browser/ui/browser_navigator*.h; browser_window_util dùng GetBrowserForMigrationOnly()->window().

After: 151: include dời sang chrome/browser/ui/navigator/; browser_window_util dùng BrowserWindow::FromBrowser(&browser); extensions_menu_test_util dùng CreateBubbleDeprecated với NATIVE_WIDGET_OWNS_WIDGET; web_file_handlers dùng base::MakeFlatSet.

Mechanism: Cùng đợt tái cấu trúc Browser/BrowserWindowInterface đã thấy ở review Settings.

Impact: Không đổi hành vi. Patch downstream dùng đường include cũ không biên dịch.

Conditions: Windows.

Action: Sửa include trong patch downstream.

- `file:chrome/browser/extensions/browser_window_util.cc` · [from: chrome/browser/extensions/browser_window_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/browser_window_util.cc), [to: chrome/browser/extensions/browser_window_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/browser_window_util.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/extensions/browsertest_util.cc` · [from: chrome/browser/extensions/browsertest_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/browsertest_util.cc), [to: chrome/browser/extensions/browsertest_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/browsertest_util.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/extensions/api/tabs/windows_util.cc` · [from: chrome/browser/extensions/api/tabs/windows_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/api/tabs/windows_util.cc), [to: chrome/browser/extensions/api/tabs/windows_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/api/tabs/windows_util.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/extensions/file_handlers/web_file_handlers_permission_handler.cc` · [from: chrome/browser/extensions/file_handlers/web_file_handlers_permission_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/file_handlers/web_file_handlers_permission_handler.cc), [to: chrome/browser/extensions/file_handlers/web_file_handlers_permission_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/file_handlers/web_file_handlers_permission_handler.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/ui/webui/extensions_zero_state_promo/zero_state_promo_page_handler.cc` · [from: chrome/browser/ui/webui/extensions_zero_state_promo/zero_state_promo_page_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/extensions_zero_state_promo/zero_state_promo_page_handler.cc), [to: chrome/browser/ui/webui/extensions_zero_state_promo/zero_state_promo_page_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/extensions_zero_state_promo/zero_state_promo_page_handler.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/ui/views/side_panel/extensions/extension_side_panel_manager.cc` · [from: chrome/browser/ui/views/side_panel/extensions/extension_side_panel_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/views/side_panel/extensions/extension_side_panel_manager.cc), [to: chrome/browser/ui/views/side_panel/extensions/extension_side_panel_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/views/side_panel/extensions/extension_side_panel_manager.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.
- `file:chrome/browser/ui/views/extensions/extensions_menu_test_util.cc` · [from: chrome/browser/ui/views/extensions/extensions_menu_test_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/views/extensions/extensions_menu_test_util.cc), [to: chrome/browser/ui/views/extensions/extensions_menu_test_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/views/extensions/extensions_menu_test_util.cc): Đã đọc mọi hunk: chỉ đổi include/API như mechanism.

## 32. Theme extension không còn đặt bảng màu nhóm tab (tab_group_color_palette); cờ thử nghiệm bị xoá

Status: confirmed

Before: 148: theme handler đọc theme.tab_group_color_palette khi kCustomizeTabGroupColorPalette bật (disabled theo source) và có ThemeInfo::GetTabGroupColorPalette.

After: 151: hàm LoadTabGroupColorPalette, getter và cờ đều bị xoá.

Mechanism: Cờ bị xoá khi đang disabled: khả năng thử nghiệm bị bỏ, không graduate.

Impact: Không đổi mặc định. Theme dùng tab_group_color_palette (chỉ có tác dụng khi bật cờ) sẽ bị bỏ qua.

Conditions: Windows.

Action: Không cần hành động trừ khi sản phẩm bật cờ này.

- `file:chrome/common/extensions/manifest_handlers/theme_handler.cc` · [from: chrome/common/extensions/manifest_handlers/theme_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/manifest_handlers/theme_handler.cc), [to: chrome/common/extensions/manifest_handlers/theme_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/extensions/manifest_handlers/theme_handler.cc): Đã đọc mọi hunk.
- `base_feature:CustomizeTabGroupColorPalette` · [from: chrome/common/chrome_features.cc:143](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/chrome_features.cc#143): Cờ disabled bị xoá.
- [from: chrome/common/extensions/manifest_handlers/theme_handler.cc:204](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/extensions/manifest_handlers/theme_handler.cc#204): 148: parse theo cờ.

## 33. API tabs/windows bỏ qua cửa sổ đang chờ xoá

Status: confirmed

Before: 148: vòng lặp tìm cửa sổ chỉ lọc theo profile.

After: 151: bỏ qua cửa sổ không còn BrowserWindowInterface hoặc IsDeleteScheduled(); đổi include sang chrome/browser/ui/navigator/.

Mechanism: Tránh trả về cửa sổ đang bị huỷ cho chrome.tabs/chrome.windows.

Impact: Extension gọi chrome.windows/tabs lúc một cửa sổ đang đóng không còn nhận cửa sổ đó.

Conditions: Windows.

Action: Không cần hành động.

- `file:chrome/browser/extensions/extension_tab_util.cc` · [from: chrome/browser/extensions/extension_tab_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/extensions/extension_tab_util.cc), [to: chrome/browser/extensions/extension_tab_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/extension_tab_util.cc): Đã đọc mọi hunk.
- [to: chrome/browser/extensions/extension_tab_util.cc:643](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/extensions/extension_tab_util.cc#643): Lọc cửa sổ đang bị xoá.

## 34. oauth2.auto_approve dùng client ID của Chrome được mở cho extension allowlist bằng dòng lệnh

Status: confirmed

Before: 148: chỉ extension location component dùng auto_approve với client ID của Chrome (bỏ trống client_id).

After: 151: can_use_auto_approve = location component HOẶC IsExtensionAllowlistedByCommandLine(extension).

Mechanism: Mở rộng cho extension được liệt kê qua --allowlisted-extension-id (ví dụ extension kiểm thử tự động).

Impact: Chỉ ảnh hưởng khi chạy với --allowlisted-extension-id; sản phẩm không dùng switch này thì không đổi.

Conditions: Windows.

Action: Đảm bảo bản phát hành không chạy với --allowlisted-extension-id.

- `file:extensions/common/manifest_handlers/oauth2_manifest_handler.cc` · [from: extensions/common/manifest_handlers/oauth2_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/manifest_handlers/oauth2_manifest_handler.cc), [to: extensions/common/manifest_handlers/oauth2_manifest_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/oauth2_manifest_handler.cc): Đã đọc mọi hunk, gồm các hunk const.
- [to: extensions/common/manifest_handlers/oauth2_manifest_handler.cc:54](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/manifest_handlers/oauth2_manifest_handler.cc#54): Điều kiện mới.

## 35. Switch mới --refresh-component-extension-service-workers

Status: confirmed

Before: 148: không có switch.

After: 151: switch buộc service worker của component extension đăng ký lại mỗi lần nạp thay vì dùng bản đăng ký đã lưu trong profile.

Mechanism: Công cụ cho phát triển component extension.

Impact: Không ảnh hưởng mặc định.

Conditions: Windows.

Action: Không cần hành động.

- `switch:refresh-component-extension-service-workers` · [to: extensions/common/switches.cc:42](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/switches.cc#42): Switch mới.
- `file:extensions/common/switches.cc` · [from: extensions/common/switches.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/switches.cc), [to: extensions/common/switches.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/switches.cc): Đã đọc mọi hunk: hai switch mới, switch kia thuộc event:ext-test-api-standardized-behavior.
- [to: extensions/common/switches.h:83](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/switches.h#83): Mô tả switch.

## 36. Switch mới cho chrome.test theo đề xuất browser.test

Status: confirmed

Before: 148: không có switch và native handler.

After: 151: --extension-test-api-standardized-behavior làm chrome.test dùng hành vi chuẩn hoá theo đề xuất browser.test; native handler mới trả cờ này cho JS.

Mechanism: Chỉ cho kiểm thử extension.

Impact: Không ảnh hưởng người dùng.

Conditions: Windows.

Action: Không cần hành động.

- `switch:extension-test-api-standardized-behavior` · [to: extensions/common/switches.cc:52](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/switches.cc#52): Switch mới.
- `file:extensions/common/switches.h` · [from: extensions/common/switches.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/extensions/common/switches.h), [to: extensions/common/switches.h](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/common/switches.h): Đã đọc mọi hunk: khai báo hai switch.
- `file:extensions/renderer/test_api_standardized_behavior_native_handler.cc` · [to: extensions/renderer/test_api_standardized_behavior_native_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/extensions/renderer/test_api_standardized_behavior_native_handler.cc): File mới; đã đọc toàn bộ.

