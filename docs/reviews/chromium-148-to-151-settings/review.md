# Chromium upgrade review

refs/tags/148.0.7778.217 → refs/tags/151.0.7922.138 · windows

Status: PARTIAL

Indexed items: 9437; events: 45; provisional events: 0.

Disposition counts: {"event": 287, "explained": 21, "out_of_scope": 73, "pending": 9056}

Accounting does not establish semantic completeness or product safety.

## Recorded item selection

Settings ở 148.0.7778.217 → 151.0.7922.138 trên Windows, mức full: flags, mojom, WebUI (thay đổi người dùng thấy, khả năng mới, việc downstream phải thích nghi), cộng pref/route/handler/source delta cần để giải thích chúng. Biên: toàn bộ 272 item indexed có path dưới chrome/browser/resources/settings hoặc chrome/browser/ui/webui/settings (141 finding + 131 file diff), cộng 57 finding dependency và 51 file khai báo dùng chung mà focus packet của hai tiền tố đó trả về, cộng một milestone lead M151 nói về cùng cặp quyền local-network/loopback-network. History, Downloads và Bookmarks không review lại ở đây.

Selection accounting: COMPLETE
Selected items: 381; outside the selection: 9056.
Disposition counts: {"event": 287, "explained": 21, "out_of_scope": 73}

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

## 1. Cờ YourSavedInfoSettingsPage bật mặc định trên Windows: cả nhánh trang Your saved info thành mặc định

Status: confirmed

Before: 148: kYourSavedInfoSettingsPage disabled theo source (Windows disabled).

After: 151: enabled theo source (Windows enabled).

Mechanism: Boolean enableYourSavedInfoSettingsPage đọc cờ này và là guard của cả cây route YOUR_SAVED_INFO trong route.ts (identity docs, travel, passkeys, shopping, suggestions from Gemini), cũng như của tiêu đề trang autofill_section.

Impact: Theo source, người dùng Windows 151 mặc định thấy trang "Your saved info" và cấu trúc điều hướng mới của Autofill thay vì trang cũ. Đây là thay đổi người dùng thấy rõ nhất trong nhóm Autofill của bản nâng cấp này. Lưu ý: default trong source không chứng minh rollout thật — Finch có thể vẫn tắt.

Conditions: Windows; default_state enabled, không có điều kiện build khác.

Action: Mở chrome://settings/autofill trên bản 151 sạch và xác nhận trang Your saved info xuất hiện; kiểm tra mọi deep-link cũ của sản phẩm tới trang autofill/addresses còn đúng.

Uncertainties: Chưa xác nhận cấu hình Finch/rollout thực tế.

- `base_feature:YourSavedInfoSettingsPage` · [from: components/autofill/core/common/autofill_features.cc:1146](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#1146), [to: components/autofill/core/common/autofill_features.cc:1102](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_features.cc#1102): Default Windows disabled → enabled.
- [to: chrome/browser/resources/settings/route.ts:227](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#227): enableYourSavedInfoSettingsPage là guard của cả cây route Your saved info.

## 2. Hộp thoại Xoá dữ liệu duyệt web: bản v2 thành bản duy nhất, bỏ tab Basic/Advanced và bỏ xoá mật khẩu

Status: confirmed

Before: 148: file clear_browsing_data_dialog_v2.html là phần tử settings-clear-browsing-data-dialog-v2 được privacy_page dựng; handler giữ hai nhóm counter (counters_basic_, counters_advanced_) và chọn danh sách pref theo cờ browsing_data::features::kDbdRevampDesktop (enabled), BrowsingDataType::PASSWORDS xoá cả DATA_TYPE_PASSWORDS và ACCOUNT_PASSWORDS, restartCounters nhận 2 tham số (basic, time period), initializeClearBrowsingData đọc cả kDeleteTimePeriodBasic.

After: 151: file đổi tên thành clear_browsing_data_dialog.html, phần tử thành settings-clear-browsing-data-dialog; nội dung giống hệt bản v2 cũ trừ một khối :host-context([webui-refresh-2026]). Handler chỉ còn một mảng kCounterPrefs và một danh sách counters_, AddCounter/RestartCounters mất tham số tab, HandleRestartCounters CHECK_EQ(1U, args.size()), BrowsingDataType::PASSWORDS thành NOTREACHED kèm ghi chú "Passwords are no longer deletable via DBD modal (crbug.com/397187800)", và cờ kDbdRevampDesktop bị xoá.

Mechanism: Cả hai phía graduate cùng lúc: cờ revamp đã enabled nên nhánh cũ (tab Basic/Advanced, counter mật khẩu, pref kDeleteTimePeriodBasic) bị xoá và tên "v2" bị bỏ. Mười finding control là cùng năm control được dời từ file v2 sang file mới — không phải control bị xoá rồi thêm control khác.

Impact: Người dùng không còn xoá mật khẩu từ hộp thoại này (phải vào Password Manager) và không còn hai tab. Downstream có WebUI/JS riêng gọi restartCounters với 2 tham số sẽ làm CHECK_EQ thất bại (crash renderer-initiated message), và tham chiếu tới settings-clear-browsing-data-dialog-v2 sẽ không còn phần tử. Pref kDeleteTimePeriodBasic vẫn có thể còn trên đĩa nhưng không còn được đọc ở đây.

Conditions: Windows; không còn cờ nào điều khiển — đây là hành vi mặc định của 151.

Action: Grep downstream cho "clear-browsing-data-dialog-v2" và cho restartCounters; mở hộp thoại Xoá dữ liệu duyệt web, xác nhận không có mục Passwords và counter cập nhật theo khoảng thời gian.

- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog/id:cancelButton` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html:157](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html#157): Control xuất hiện dưới tên file mới (dời theo file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog/id:deleteButton` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html:161](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html#161): Control xuất hiện dưới tên file mới (dời theo file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog/id:manageOtherGoogleDataRow` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html:144](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html#144): Control xuất hiện dưới tên file mới (dời theo file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog/id:showMoreButton` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html:137](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html#137): Control xuất hiện dưới tên file mới (dời theo file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog/id:timePicker` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html:108](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html#108): Control xuất hiện dưới tên file mới (dời theo file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2/id:cancelButton` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html:153](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html#153): Control biến mất khỏi file v2 cũ (cùng control, khác file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2/id:deleteButton` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html:157](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html#157): Control biến mất khỏi file v2 cũ (cùng control, khác file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2/id:manageOtherGoogleDataRow` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html:140](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html#140): Control biến mất khỏi file v2 cũ (cùng control, khác file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2/id:showMoreButton` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html:133](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html#133): Control biến mất khỏi file v2 cũ (cùng control, khác file).
- `webui_control:settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2/id:timePicker` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html:104](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html#104): Control biến mất khỏi file v2 cũ (cùng control, khác file).
- `file:chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html` · [to: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog.html): File mới ở 151; diff với file v2 của 148 chỉ khác khối :host-context([webui-refresh-2026]).
- `file:chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html` · [from: chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/clear_browsing_data_dialog/clear_browsing_data_dialog_v2.html): File v2 không còn ở 151 (fetch đúng ref trả upstream_404).
- `file:chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc` · [from: chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc), [to: chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc): Đã đọc mọi hunk: gộp counter, bỏ nhánh cờ, NOTREACHED cho PASSWORDS, đổi chữ ký message.
- `file:chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler_unittest.cc): Đã đọc mọi hunk: test theo một counter và một tham số.
- `file:chrome/browser/resources/settings/privacy_page/privacy_page.html` · [from: chrome/browser/resources/settings/privacy_page/privacy_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/privacy_page.html), [to: chrome/browser/resources/settings/privacy_page/privacy_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/privacy_page.html): Đã đọc hunk duy nhất: đổi tên phần tử dialog.
- `base_feature:DbdRevampDesktop` · [from: components/browsing_data/core/features.cc:16](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/browsing_data/core/features.cc#16): Cờ enabled bị xoá — graduate.
- [to: chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc:64](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_clear_browsing_data_handler.cc#64): Mảng kCounterPrefs duy nhất thay hai hàm chọn theo cờ.

## 3. Quyền Local network access tách hẳn thành Local network và Loopback network; trang gộp bị xoá

Status: confirmed

Before: 148: hai cấu hình song song. enableLocalNetworkAccessSetting = kLocalNetworkAccessChecks && !Warn && !kLocalNetworkAccessChecksSplitPermissions mở route localNetworkAccess và trang local_network_access_page; enableLocalNetworkAccessSplitPermissions (cùng điều kiện nhưng cờ split bật) mở hai route localNetwork và loopbackNetwork. site_settings_helper chọn ContentSettingsType::LOCAL_NETWORK_ACCESS hoặc cặp LOCAL_NETWORK + LOOPBACK_NETWORK theo cờ split.

After: 151: cờ kLocalNetworkAccessChecksSplitPermissions (đang enabled) bị xoá; enableLocalNetworkAccessSetting còn = kLocalNetworkAccessChecks && !Warn và giờ gate hai route localNetwork/loopbackNetwork; route localNetworkAccess, trang local_network_access_page.html (upstream_404 ở 151), bảy chuỗi siteSettingsLocalNetworkAccess* và nhánh site_details tương ứng bị xoá. LOCAL_NETWORK_ACCESS chuyển sang danh sách không có tên UI trong site_settings_helper.

Mechanism: Đây là bước dọn sau khi split permissions launch: một nhánh cấu hình biến mất, nhánh còn lại đổi gate. Content setting LOCAL_NETWORK_ACCESS vẫn tồn tại trong enum (chuyển vào nhóm nullptr) nên dữ liệu cũ không bị coi là loại lạ, chỉ không còn UI. Một milestone lead của M151 mô tả cùng cặp quyền local-network/loopback-network ở bề mặt permission policy của Isolated Web App, tức cùng một đợt tách quyền.

Impact: Người dùng dùng quyền này thấy hai mục riêng thay vì một. Downstream deep-link tới chrome://settings/content/localNetworkAccess mất route; patch đọc enableLocalNetworkAccessSplitPermissions nhận undefined. Ngoại lệ đã lưu dưới LOCAL_NETWORK_ACCESS không còn xuất hiện trong Settings — cần kiểm tra có migration nào sang hai loại mới không (chưa thấy trong phạm vi đã đọc).

Conditions: Windows; cần network::features::kLocalNetworkAccessChecks và !kLocalNetworkAccessChecksWarn. Cùng file site_settings_helper.cc còn hai hunk dọn enum khác (TPCD_METADATA_GRANTS/TPCD_HEURISTICS_GRANTS bị bỏ khỏi danh sách không-UI; DEPRECATED_SUB_APP_INSTALLATION_PROMPTS → SUB_APP_INSTALLATION_PROMPTS và SUB_APPS_WITHOUT_PROMPTS) — thay đổi riêng, chỉ ảnh hưởng static_assert nếu downstream patch bảng này.

Action: Kiểm tra deep-link localNetworkAccess; xem ngoại lệ cũ của loại gộp còn hiển thị ở đâu không; kiểm tra hai trang mới trên chrome://settings/content.

Uncertainties: Chưa tìm được code migration cho ngoại lệ đã lưu dưới LOCAL_NETWORK_ACCESS; cần đọc components/content_settings để kết luận.

- `webui_route:settings/SITE_SETTINGS_LOCAL_NETWORK_ACCESS` · [from: chrome/browser/resources/settings/route.ts:146](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/route.ts#146): Route gộp bị xoá.
- `webui_route:settings/SITE_SETTINGS_LOCAL_NETWORK` · [from: chrome/browser/resources/settings/route.ts:150](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/route.ts#150), [to: chrome/browser/resources/settings/route.ts:146](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#146): Route localNetwork đổi guard sang enableLocalNetworkAccessSetting.
- `webui_route:settings/SITE_SETTINGS_LOOPBACK_NETWORK` · [from: chrome/browser/resources/settings/route.ts:151](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/route.ts#151), [to: chrome/browser/resources/settings/route.ts:147](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#147): Route loopbackNetwork đổi guard tương tự.
- `webui_gate:settings_ui/enableLocalNetworkAccessSetting` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:552](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#552), [to: chrome/browser/ui/webui/settings/settings_ui.cc:567](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#567): Biểu thức gate mất số hạng cờ split.
- `webui_gate:settings_ui/enableLocalNetworkAccessSplitPermissions` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:560](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#560): Boolean split bị xoá.
- `webui_control:settings/site_settings/local_network_access_page/label:siteSettingsLocalNetworkAccess` · [from: chrome/browser/resources/settings/site_settings/local_network_access_page.html:2](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/site_settings/local_network_access_page.html#2): settings-subpage của trang gộp bị xoá.
- `base_feature:LocalNetworkAccessChecksSplitPermissions` · [from: services/network/public/cpp/features.cc:286](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/services/network/public/cpp/features.cc#286): Cờ split (đang enabled) bị xoá — graduate.
- `file:chrome/browser/resources/settings/site_settings/local_network_access_page.html` · [from: chrome/browser/resources/settings/site_settings/local_network_access_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/site_settings/local_network_access_page.html): File trang gộp không còn ở 151 (upstream_404).
- `file:chrome/browser/resources/settings/site_settings/site_details.html` · [from: chrome/browser/resources/settings/site_settings/site_details.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/site_settings/site_details.html), [to: chrome/browser/resources/settings/site_settings/site_details.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/site_settings/site_details.html): Đã đọc hunk duy nhất: bỏ nhánh site-details-permission của loại gộp.
- `file:chrome/browser/ui/webui/settings/site_settings_helper.cc` · [from: chrome/browser/ui/webui/settings/site_settings_helper.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/site_settings_helper.cc), [to: chrome/browser/ui/webui/settings/site_settings_helper.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/site_settings_helper.cc): Đã đọc mọi hunk: bỏ nhánh cờ split, chuyển LOCAL_NETWORK_ACCESS sang nhóm không-UI; hunk INLINE_CUE_MENU thuộc event:settings-inline-cue-menu.
- `file:chrome/browser/resources/settings/route.ts` · [from: chrome/browser/resources/settings/route.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/route.ts), [to: chrome/browser/resources/settings/route.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts): Đã đọc mọi hunk của route.ts: hunk LNA ở đây; hunk inline cue menu thuộc event:settings-inline-cue-menu, hunk ACCOUNT/GOOGLE_SERVICES thuộc event:settings-account-page-unification, hunk AI thuộc event:settings-ai-suggestions-page và event:settings-skills-page, hunk Your saved info thuộc event:settings-your-saved-info-shopping và event:settings-personal-context-links.
- `file:chrome/browser/resources/settings/privacy_page/privacy_page_index.html` · [from: chrome/browser/resources/settings/privacy_page/privacy_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/privacy_page_index.html), [to: chrome/browser/resources/settings/privacy_page/privacy_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/privacy_page_index.html): Đã đọc mọi hunk: bỏ view trang gộp, gom hai view split vào một nhánh; hunk inline cue menu thuộc event:settings-inline-cue-menu.
- [to: chrome/browser/ui/webui/settings/site_settings_helper.cc:669](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/site_settings_helper.cc#669): Hai loại split được thêm không điều kiện khi kLocalNetworkAccessChecks bật.
- `brief:5fce8f7b9bacee07834b`: Milestone lead M151 "Permission Policy Merger: direct-sockets-private with local-network and loopback-network" gọi đúng hai tên quyền mới — nguồn độc lập cho thấy việc tách local-network/loopback-network là thay đổi toàn nền tảng ở 151, không chỉ UI Settings. Lead nói về manifest Isolated Web App và Direct Sockets, không nói về trang Settings, và số milestone không chứng minh điều gì về đúng hai bản 148.0.7778.217 → 151.0.7922.138 này.

## 4. Lựa chọn "Block V8 optimizer trên site lạ" thành mặc định: cờ và boolean gate bị xoá

Status: confirmed

Before: 148: boolean enableBlockV8OptimizerOnUnfamiliarSites = IsEnabled(kBlockV8OptimizerOnUnfamiliarSitesSetting) (cờ enabled), và v8_page bọc radio blockForUnfamiliarSites trong dom-if theo boolean đó.

After: 151: cả cờ và boolean bị xoá; radio blockForUnfamiliarSites luôn được dựng.

Mechanism: Cờ đã enabled trước khi xoá và nhánh UI duy nhất của nó trở thành không điều kiện — khả năng được giữ lại, không phải bị bỏ. security_settings_provider cũng bỏ include components/content_settings/core/common/features.h.

Impact: Người dùng luôn thấy ba lựa chọn cho JavaScript optimizer, kể cả sản phẩm trước đây tắt cờ để ẩn lựa chọn giữa — nay không còn cờ để tắt. Downstream muốn ẩn phải patch template.

Conditions: Windows; không còn điều kiện runtime.

Action: Mở chrome://settings/content/v8 và xác nhận có lựa chọn "Block for unfamiliar sites"; nếu sản phẩm cần ẩn, lên kế hoạch patch.

- `webui_gate:security_settings_provider/enableBlockV8OptimizerOnUnfamiliarSites` · [from: chrome/browser/ui/webui/settings/security_settings_provider.cc:64](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/security_settings_provider.cc#64): Boolean gate bị xoá.
- `base_feature:BlockV8OptimizerOnUnfamiliarSitesSetting` · [from: components/content_settings/core/common/features.cc:68](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/content_settings/core/common/features.cc#68): Cờ enabled bị xoá — graduate.
- `file:chrome/browser/ui/webui/settings/security_settings_provider.cc` · [from: chrome/browser/ui/webui/settings/security_settings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/security_settings_provider.cc), [to: chrome/browser/ui/webui/settings/security_settings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/security_settings_provider.cc): Đã đọc mọi hunk của provider.
- `file:chrome/browser/resources/settings/site_settings/v8_page.html` · [from: chrome/browser/resources/settings/site_settings/v8_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/site_settings/v8_page.html), [to: chrome/browser/resources/settings/site_settings/v8_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/site_settings/v8_page.html): Đã đọc hunk duy nhất: dom-if quanh radio bị bỏ.

## 5. Công tắc Card benefits không còn gate: luôn hiển thị trong Payments

Status: confirmed

Before: 148: boolean autofillCardBenefitsAvailable = payments_data.IsCardBenefitsFeatureEnabled(), và payments_section bọc cardBenefitsToggle trong dom-if cardBenefitsFlagEnabled_.

After: 151: boolean bị xoá và dom-if biến mất — cardBenefitsToggle luôn được dựng, chỉ còn disable khi pref autofill.credit_card_enabled tắt.

Mechanism: Khả năng card benefits đã launch nên điều kiện hiển thị bị bỏ; pref autofill.payment_card_benefits không đổi.

Impact: Người dùng luôn thấy công tắc Card benefits trong Payments, kể cả khi tài khoản/khu vực không có benefit nào. Downstream dựa vào boolean autofillCardBenefitsAvailable trong WebUI riêng sẽ nhận undefined.

Conditions: Windows; không còn điều kiện runtime nào cho việc hiển thị.

Action: Mở chrome://settings/payments và xác nhận công tắc xuất hiện; kiểm tra WebUI riêng không còn đọc autofillCardBenefitsAvailable.

- `webui_gate:settings_localized_strings_provider/autofillCardBenefitsAvailable` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1740](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1740): Boolean gate bị xoá.
- `file:chrome/browser/resources/settings/autofill_page/payments_section.html` · [from: chrome/browser/resources/settings/autofill_page/payments_section.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/payments_section.html), [to: chrome/browser/resources/settings/autofill_page/payments_section.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/payments_section.html): Đã đọc hunk duy nhất: dom-if quanh cardBenefitsToggle bị bỏ.

## 6. Công tắc nút Tab search luôn hiển thị sau khi cờ HorizontalTabStripComboButton bị xoá

Status: confirmed

Before: 148: boolean showTabSearchEnabled = IsVerticalTabsFeatureEnabled() || IsEnabled(tabs::kHorizontalTabStripComboButton) (cờ này disabled theo source); appearance_page bọc showTabSearchButton và hai công tắc projects/everything trong dom-if showTabSearchEnabled_. Browsertest có nhánh đếm pinned action theo cờ và theo vị trí tab search.

After: 151: cờ kHorizontalTabStripComboButton và boolean showTabSearchEnabled bị xoá; showTabSearchButton luôn dựng, hai công tắc projects/everything chỉ còn gate riêng của chúng. Browsertest cố định 2 rồi 1 pinned action, bỏ nhánh theo cờ và bỏ phần ghim Tab search cho ChromeOS.

Mechanism: Cờ bị xoá khi đang disabled, nên đây không phải graduate: điều kiện hiển thị bị bỏ hẳn và công tắc trở thành mặc định. Số pinned action mặc định cũng đổi (test trước đó chấp nhận 3/2 tuỳ cờ, giờ chỉ 2).

Impact: Người dùng Windows thấy công tắc "Show tab search button" không điều kiện. Sản phẩm từng dựa vào cờ/boolean để ẩn công tắc này mất cách ẩn; đọc showTabSearchEnabled trong WebUI riêng nhận undefined.

Conditions: Windows; không còn điều kiện runtime.

Action: Mở chrome://settings/appearance và xác nhận công tắc Tab search; nếu sản phẩm đổi bộ nút ghim mặc định, chạy lại AppearanceHandlerTest.

- `webui_gate:settings_localized_strings_provider/showTabSearchEnabled` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:588](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#588): Boolean gate bị xoá.
- `base_feature:HorizontalTabStripComboButton` · [from: chrome/browser/ui/tabs/features.cc:87](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/tabs/features.cc#87): Cờ disabled bị xoá — khả năng không graduate, điều kiện chỉ bị bỏ.
- `file:chrome/browser/ui/webui/settings/appearance_handler_browsertest.cc` · [from: chrome/browser/ui/webui/settings/appearance_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/appearance_handler_browsertest.cc), [to: chrome/browser/ui/webui/settings/appearance_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/appearance_handler_browsertest.cc): Đã đọc mọi hunk: test bỏ nhánh theo cờ, số pinned action cố định.

## 7. Trang Security v2: HTTPS-First Mode chuyển từ công tắc ở mục "Account and network" thành feature row mở rộng có badge New

Status: confirmed

Before: 148: security_page_v2 có settings-toggle-button httpsFirstModeToggle cùng một settings-radio-group riêng, đặt trong section securityAccountAndNetworkSectionTitle.

After: 151: thay bằng security-page-feature-row httpsFirstModeRow (cùng pref generated.https_first_mode_enabled) nằm trong section chính, có slot collapse chứa radio group, state-text-map, show-new-badge, và hiệu ứng highlight khi mở bằng link. security_page_feature_row thêm new-badge và #labelContainer.

Mechanism: Cùng một pref và cùng hai lựa chọn Balanced/Strict, chỉ đổi dạng control và vị trí; feature row cho phép thu gọn phần radio. Hiệu ứng pulse-highlight có nhánh prefers-reduced-motion.

Impact: Người dùng thấy HTTPS-First Mode ở mục Safe Browsing/chính thay vì mục Account and network, kèm badge New. Downstream test UI chọn #httpsFirstModeToggle sẽ không tìm thấy phần tử; selector mới là #httpsFirstModeRow.

Conditions: Windows; chỉ áp dụng cho trang Security v2 (trang v2 có gate riêng ngoài phạm vi hai file này).

Action: Mở trang Security v2, kiểm tra hàng HTTPS-First Mode mở ra radio group, badge New, và pref vẫn là generated.https_first_mode_enabled; cập nhật selector trong test downstream.

Uncertainties: Chưa xác định điều kiện hiển thị trang Security v2 (nằm ngoài hai file này).

- `webui_control:settings/privacy_page/security_page_v2/pref:generated.https_first_mode_enabled#httpsFirstModeRow` · [to: chrome/browser/resources/settings/privacy_page/security/security_page_v2.html:461](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/security/security_page_v2.html#461): Control mới kiểu security-page-feature-row, cùng pref.
- `webui_control:settings/privacy_page/security_page_v2/pref:generated.https_first_mode_enabled#httpsFirstModeToggle` · [from: chrome/browser/resources/settings/privacy_page/security/security_page_v2.html:451](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/security/security_page_v2.html#451): Control cũ kiểu settings-toggle-button bị xoá.
- `file:chrome/browser/resources/settings/privacy_page/security/security_page_v2.html` · [from: chrome/browser/resources/settings/privacy_page/security/security_page_v2.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/security/security_page_v2.html), [to: chrome/browser/resources/settings/privacy_page/security/security_page_v2.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/security/security_page_v2.html): Đã đọc mọi hunk: chuyển khối HTTPS-First Mode, thêm highlight.
- `file:chrome/browser/resources/settings/privacy_page/security/security_page_feature_row.html` · [from: chrome/browser/resources/settings/privacy_page/security/security_page_feature_row.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/security/security_page_feature_row.html), [to: chrome/browser/resources/settings/privacy_page/security/security_page_feature_row.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/security/security_page_feature_row.html): Đã đọc mọi hunk: new-badge và layout nhãn.

## 8. Hộp thoại reset tự động bản V2 thành bản duy nhất và Windows mất cờ showExplanationWithBulletPoints

Status: confirmed

Before: 148: cờ kShowResetProfileBannerV2 (enabled) quyết định hai biến thể trong reset_profile_banner — V2 có tiêu đề/thân V2, danh sách pref bị can thiệp, nút learnMoreV2 + confirm; bản cũ có description, nút ok + reset. HandleGetTamperedPreferencePaths trả mảng rỗng nếu cờ tắt. Provider đẩy showExplanationWithBulletPoints = true trên Windows (hardcode trong #if IS_WIN) kèm TODO(crbug.com/40192052).

After: 151: cờ, hai nhánh và boolean showExplanationWithBulletPoints đều bị xoá. Banner chỉ còn một dạng: resetAutomatedDialogTitle nay trỏ IDS_..._V2_TITLE, thân dùng resetAutomatedDialogBody (V2), nút learnMore (đổi id từ learnMoreV2) + confirm; nút ok và reset biến mất. Handler luôn trả danh sách pref bị can thiệp; unittest bỏ fixture V2 và bỏ test "EmptyWhenFeatureDisabled".

Mechanism: Hai việc dọn cùng lúc: cờ banner V2 graduate (nên nhánh cũ bị xoá và các khoá chuỗi bỏ hậu tố V2), và cờ JS showExplanationWithBulletPoints được gỡ vì trên Windows nó luôn true. Cùng các file này còn việc chuyển reset_page sang Lit — thuộc event:settings-templates-lit-migration.

Impact: Người dùng thấy một hộp thoại duy nhất kèm danh sách pref đã bị thay đổi; không còn nút Reset ngay trên banner. Downstream đọc showExplanationWithBulletPoints hoặc khoá resetAutomatedDialogV2Title/resetAutomatedDialogV2Body/resetProfileBannerDescription/resetProfileBannerButton sẽ không còn dữ liệu.

Conditions: Windows; không còn cờ điều khiển.

Action: Kích hoạt điều kiện ShouldShowResetProfileBanner để xem hộp thoại; grep downstream cho bốn khoá chuỗi đã xoá và cho showExplanationWithBulletPoints.

- `webui_gate:settings_ui/showResetProfileBannerV2` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:351](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#351): Boolean cờ banner V2 bị xoá khỏi settings_ui.cc.
- `webui_gate:settings_localized_strings_provider/showExplanationWithBulletPoints` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1036](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1036): Boolean bullet-points bị xoá khỏi provider.
- `base_feature:ShowResetProfileBannerV2` · [from: chrome/common/chrome_features.cc:179](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/chrome_features.cc#179): Cờ enabled bị xoá — graduate.
- `webui_control:settings/reset_page/reset_profile_banner/id:learnMoreV2` · [from: chrome/browser/resources/settings/reset_page/reset_profile_banner.html:50](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_banner.html#50): Nút learnMoreV2 bị xoá.
- `webui_control:settings/reset_page/reset_profile_banner/id:learnMore` · [to: chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts:24](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts#24): Nút learnMore mới (cùng chức năng, bỏ hậu tố V2).
- `webui_control:settings/reset_page/reset_profile_banner/id:ok` · [from: chrome/browser/resources/settings/reset_page/reset_profile_banner.html:61](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_banner.html#61): Nút ok của nhánh cũ bị xoá.
- `webui_control:settings/reset_page/reset_profile_banner/id:reset` · [from: chrome/browser/resources/settings/reset_page/reset_profile_banner.html:64](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_banner.html#64): Nút reset của nhánh cũ bị xoá.
- `file:chrome/browser/ui/webui/settings/reset_settings_handler.cc` · [from: chrome/browser/ui/webui/settings/reset_settings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/reset_settings_handler.cc), [to: chrome/browser/ui/webui/settings/reset_settings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/reset_settings_handler.cc): Đã đọc mọi hunk: bỏ kiểm tra cờ trong HandleGetTamperedPreferencePaths.
- `file:chrome/browser/ui/webui/settings/reset_settings_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/reset_settings_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/reset_settings_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/reset_settings_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/reset_settings_handler_unittest.cc): Đã đọc mọi hunk: bỏ fixture và test theo cờ.

## 9. Privacy Sandbox: hai cờ UX quảng cáo graduate nên chỉ còn bản V2 của chuỗi và bỏ message content-parity

Status: confirmed

Before: 148: kPrivacySandboxAdsApiUxEnhancements và kPrivacySandboxAdTopicsContentParity đều enabled; provider đẩy boolean isPrivacySandboxAdsApiUxEnhancementsEnabled và chuỗi adTopicsPageDisclaimer; handler có message shouldShowPrivacySandboxAdTopicsContentParity; trang Topics chọn giữa hai mô tả/hai footer theo content parity; privacy guide chọn sub-label theo shouldShowV2AdPrivacySubLabel_. kPrivacySandboxAdPrivacyUxDeprecation disabled.

After: 151: hai cờ bị xoá cùng boolean, chuỗi disclaimer bản cũ, message và cả hai nhánh dom-if — chỉ còn bản V2 (adTopicsPageActiveTopicsDescription, adTopicsPageDisclaimerV2Desktop, privacyGuideCompletionCardPrivacySandboxSubLabelAdTopics). kPrivacySandboxAdPrivacyUxDeprecation đổi sang enabled.

Mechanism: Hai cờ đã enabled nên nhánh V2 trở thành mặc định và nhánh cũ bị xoá; cờ deprecation bật mặc định là bước tiếp theo của cùng hướng (gỡ UX quảng cáo cũ). Chuỗi topicsPageActiveTopicsDescription và privacyGuideCompletionCardPrivacySandboxSubLabel bị xoá khỏi bảng chuỗi.

Impact: Người dùng luôn thấy nội dung Ad topics bản V2. Downstream gọi message shouldShowPrivacySandboxAdTopicsContentParity sẽ không còn handler (message không được đăng ký → lỗi JS). Cờ AdPrivacyUxDeprecation bật mặc định có thể thay đổi thêm UI quảng cáo ngoài phạm vi các file đã đọc — cần kiểm riêng.

Conditions: Windows; các giá trị lấy từ source, chưa biết Finch.

Action: Grep downstream cho shouldShowPrivacySandboxAdTopicsContentParity; mở chrome://settings/adPrivacy/topics và privacy guide để xác nhận chuỗi V2; điều tra riêng ảnh hưởng của kPrivacySandboxAdPrivacyUxDeprecation.

Uncertainties: Chưa điều tra hết ảnh hưởng của kPrivacySandboxAdPrivacyUxDeprecation ngoài phạm vi Settings đã đọc.

- `webui_gate:settings_localized_strings_privacy_sandbox_provider/isPrivacySandboxAdsApiUxEnhancementsEnabled` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc:305](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc#305): Boolean content-parity/UX enhancements bị xoá.
- `webui_gate:settings_localized_strings_privacy_sandbox_provider/adTopicsPageDisclaimer` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc:344](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc#344): Chuỗi disclaimer bản cũ bị xoá.
- `base_feature:PrivacySandboxAdsApiUxEnhancements` · [from: components/privacy_sandbox/privacy_sandbox_features.cc:93](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/privacy_sandbox/privacy_sandbox_features.cc#93): Cờ enabled bị xoá — graduate.
- `base_feature:PrivacySandboxAdTopicsContentParity` · [from: components/privacy_sandbox/privacy_sandbox_features.cc:90](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/privacy_sandbox/privacy_sandbox_features.cc#90): Cờ enabled bị xoá — graduate.
- `base_feature:PrivacySandboxAdPrivacyUxDeprecation` · [from: components/privacy_sandbox/privacy_sandbox_features.cc:98](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/privacy_sandbox/privacy_sandbox_features.cc#98), [to: components/privacy_sandbox/privacy_sandbox_features.cc:86](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/privacy_sandbox/privacy_sandbox_features.cc#86): Cờ disabled → enabled.
- `webui_control:settings/privacy_page/privacy_guide_completion_fragment/id:privacySandboxRow` · [from: chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html:51](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html#51), [to: chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html:51](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html#51): Hàng privacy sandbox trong privacy guide đổi sang sub-label AdTopics cố định.
- `file:chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc), [to: chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_privacy_sandbox_provider.cc): Đã đọc mọi hunk của provider privacy sandbox.
- `file:chrome/browser/ui/webui/settings/privacy_sandbox_handler.cc` · [from: chrome/browser/ui/webui/settings/privacy_sandbox_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/privacy_sandbox_handler.cc), [to: chrome/browser/ui/webui/settings/privacy_sandbox_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/privacy_sandbox_handler.cc): Đã đọc mọi hunk: bỏ message và handler content-parity.
- `file:chrome/browser/ui/webui/settings/privacy_sandbox_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/privacy_sandbox_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/privacy_sandbox_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/privacy_sandbox_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/privacy_sandbox_handler_unittest.cc): Đã đọc mọi hunk: test chuyển sang không điều kiện.
- `file:chrome/browser/resources/settings/privacy_sandbox/privacy_sandbox_topics_subpage.html` · [from: chrome/browser/resources/settings/privacy_sandbox/privacy_sandbox_topics_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_sandbox/privacy_sandbox_topics_subpage.html), [to: chrome/browser/resources/settings/privacy_sandbox/privacy_sandbox_topics_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_sandbox/privacy_sandbox_topics_subpage.html): Đã đọc mọi hunk: bỏ hai nhánh dom-if.
- `file:chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html` · [from: chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html), [to: chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/privacy_guide/privacy_guide_completion_fragment.html): Đã đọc mọi hunk: sub-label cố định và đổi aiInnovationsPageTitle → aiPageTitle (hunk sau thuộc event:settings-ai-page-entry-points).

## 10. On-device AI: bật mặc định cờ hiển thị và chặn ghi khi policy cấm

Status: confirmed

Before: 148: ShowOnDeviceAiSettings disabled theo source; setter setOnDeviceAiEnabled ghi trực tiếp local-state pref sau khi kiểm tra số đối số. Getter đã trả cả enabled và allowedByPolicy.

After: 151: cờ hiển thị enabled theo source. Setter đọc GenAILocalFoundationalModelEnterprisePolicySettings và return không ghi pref nếu kDisallowed.

Mechanism: Gate showOnDeviceAiSettings vẫn đọc cùng cờ; template System vẫn có branding guard. Thay đổi default và kiểm tra policy ở setter cùng điều khiển khả năng dùng công tắc On-device AI. Test bổ sung gửi true khi policy cấm và yêu cầu pref vẫn false.

Impact: Bản Google Chrome có thể hiện công tắc theo default mới; WebUI tùy biến gọi setter phải xử lý trường hợp yêu cầu bị từ chối. Không suy ra mọi Chromium build có công tắc hoặc model đã được cài.

Conditions: Windows; UI chỉ trong GOOGLE_CHROME_BRANDING và không ChromeOS, thêm runtime feature. Pref nằm ở local state. Getter trả allowedByPolicy, setter chặn kDisallowed. Chưa biết Finch/build downstream.

Action: Kiểm tra build branding, bật/tắt cờ; policy Allowed/Disallowed, trạng thái sau reload và thay đổi local-state giữa các profile. Đối chiếu test HandleSetOnDeviceAiEnabled_PolicyDisabled; chưa chạy test.

Uncertainties: Chưa chạy Chromium build/UI test, chưa xác nhận rollout hoặc cấu hình sản phẩm.

- `base_feature:ShowOnDeviceAiSettings` · [from: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc:23](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc#23), [to: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc:23](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc#23): Default Windows disabled → enabled.
- `file:chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc` · [from: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc), [to: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc): Đã đọc mọi hunk: đổi default và thêm policy guard ở setter.
- `file:chrome/browser/ui/webui/settings/on_device_ai_settings_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/on_device_ai_settings_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/on_device_ai_settings_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/on_device_ai_settings_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/on_device_ai_settings_handler_unittest.cc): Đã đọc toàn bộ diff test: thêm trường hợp policy cấm ghi.
- [from: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc:89](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc#89): Setter 148 ghi trực tiếp.
- [to: chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc:89](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/on_device_ai_settings_handler.cc#89): Setter 151 return khi policy disallowed.
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:677](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#677): Khối BUILDFLAG(GOOGLE_CHROME_BRANDING) && !BUILDFLAG(IS_CHROMEOS) chứa AddBoolean showOnDeviceAiSettings đọc cờ kShowOnDeviceAiSettings.
- [to: chrome/browser/resources/settings/system_page/system_page.html:141](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/system_page/system_page.html#141): Template System dùng showOnDeviceAiSettings và onDeviceAiToggle.

## 11. Autofill có card "Email verification" mới và cờ EmailVerificationProtocol bật mặc định

Status: confirmed

Before: 148: không có pref autofill.email_verification_enabled, không có boolean emailVerificationProtocolEnabled, trang autofill_section không có card email; cờ kEmailVerificationProtocol disabled theo source.

After: 151: cờ enabled theo source trên Windows; loadTimeData thêm emailVerificationProtocolEnabled; autofill_section thêm một card có settings-toggle-button bind pref autofill.email_verification_enabled, danh sách địa chỉ email đã xác minh (site-favicon theo pref autofill.email_verification_state), menu emailSharedMenu với mục Remove, và dialog xác nhận xoá.

Mechanism: Toggle và danh sách nằm trong dom-if isEmailVerificationProtocolEnabled_; cờ là content feature (content/public/common/content_features.cc) nên bật mặc định nghĩa là giao thức email verification sẵn sàng, còn việc có địa chỉ nào hiển thị phụ thuộc pref autofill.email_verification_state.

Impact: Người dùng Windows mặc định thấy một mục cài đặt mới trong Autofill và có thể xoá quyền email đã xác minh. Downstream cần biết có pref mới được ghi và một giao thức mới bật mặc định.

Conditions: Windows; cờ kEmailVerificationProtocol enabled theo source. Hiển thị danh sách phụ thuộc dữ liệu trong pref autofill.email_verification_state.

Action: Mở chrome://settings/autofill (hoặc trang Your saved info), kiểm tra card Email verification, bật/tắt toggle và kiểm tra pref; thử xoá một email đã xác minh.

Uncertainties: Chưa xác nhận rollout Finch của kEmailVerificationProtocol.

- `webui_gate:settings_localized_strings_provider/emailVerificationProtocolEnabled` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1922](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1922): Boolean gate mới.
- `webui_control:settings/autofill_page/autofill_section/pref:autofill.email_verification_enabled#autofillEmailVerificationToggle` · [to: chrome/browser/resources/settings/autofill_page/autofill_section.html:198](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/autofill_section.html#198): Toggle mới bind pref email verification.
- `webui_control:settings/autofill_page/autofill_section/id:emailSharedMenu` · [to: chrome/browser/resources/settings/autofill_page/autofill_section.html:221](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/autofill_section.html#221): cr-action-menu mới cho mục Remove.
- `pref:autofill.email_verification_enabled` · [to: components/autofill/core/common/autofill_prefs.h:104](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_prefs.h#104): Pref mới (kAutofillEmailVerificationEnabled).
- `base_feature:EmailVerificationProtocol` · [from: content/public/common/content_features.cc:405](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/content/public/common/content_features.cc#405), [to: content/public/common/content_features.cc:426](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/content/public/common/content_features.cc#426): Cờ disabled → enabled trên Windows.
- `file:chrome/browser/resources/settings/autofill_page/autofill_section.html` · [from: chrome/browser/resources/settings/autofill_page/autofill_section.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/autofill_section.html), [to: chrome/browser/resources/settings/autofill_page/autofill_section.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/autofill_section.html): Đã đọc mọi hunk: card email verification, dialog xác nhận, và các style phụ.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1921](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1921): emailVerificationProtocolEnabled đọc features::kEmailVerificationProtocol.

## 12. Autofill wallet branding: cờ save-to-wallet graduate, wallet branding bật mặc định, thêm hai cờ logo mới

Status: confirmed

Before: 148: boolean enableSaveToWalletFromSettings gate cả vị trí thông báo lỗi và logo Wallet trong dialog thêm/sửa entity; kAutofillEnableWalletBranding disabled; không có kAutofillAiWalletPassBranding2026 và kAutofillEnableGradientGoogleLogos; ba list entry dùng srcset IDR_AUTOFILL_GOOGLE_PAY_* cố định.

After: 151: cờ kAutofillEnableSaveToWalletFromSettings và boolean tương ứng bị xoá — lỗi validation luôn ở trên và logo Wallet chỉ còn phụ thuộc entityInstance; kAutofillEnableWalletBranding enabled theo source; hai cờ mới (cả hai disabled theo source) thêm biến thể logo: isAutofillAiWalletPassBranding2026Enabled chọn icon standalone, autofillEnableGradientGoogleLogos chọn srcset gradient qua getGooglePay*LogoSrcSet_.

Mechanism: Đây là ba thay đổi cùng một vùng branding: một cờ đã launch nên xoá (trước khi xoá nó enabled), một cờ đổi default sang enabled, và hai cờ mới cho bộ logo 2026. Chỉ cờ wallet branding đổi kết quả mặc định trên Windows.

Impact: Người dùng Windows mặc định thấy branding Wallet trong phần Payments; hai biến thể logo mới chưa bật. Downstream patch các template này phải biết getScaledSrcSet_ đã bị thay bằng hai hàm chọn logo mới.

Conditions: Windows. kAutofillEnableWalletBranding enabled theo source; hai cờ logo disabled theo source; branding Google Chrome vẫn là điều kiện build của các khối <if expr="_google_chrome">.

Action: Kiểm tra trang Payments với build branding: logo và chuỗi Wallet; bật hai cờ logo mới để xem biến thể. Nếu sản phẩm thay IDR_AUTOFILL_GOOGLE_PAY_*, cập nhật theo hai hàm mới.

Uncertainties: Chưa xác nhận Finch cho kAutofillEnableWalletBranding.

- `webui_gate:settings_ui/enableSaveToWalletFromSettings` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:578](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#578): Boolean save-to-wallet bị xoá khỏi settings_ui.cc.
- `webui_gate:settings_ui/autofillEnableGradientGoogleLogos` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:578](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#578): Boolean gradient logo mới.
- `webui_gate:settings_localized_strings_provider/isAutofillAiWalletPassBranding2026Enabled` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1947](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1947): Boolean wallet pass branding 2026 mới.
- `base_feature:AutofillEnableSaveToWalletFromSettings` · [from: components/autofill/core/common/autofill_features.cc:587](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#587): Cờ save-to-wallet (đang enabled) bị xoá — graduate.
- `base_feature:AutofillEnableWalletBranding` · [from: components/autofill/core/common/autofill_payments_features.cc:267](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_payments_features.cc#267), [to: components/autofill/core/common/autofill_payments_features.cc:291](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_payments_features.cc#291): kAutofillEnableWalletBranding disabled → enabled.
- `base_feature:AutofillAiWalletPassBranding2026` · [to: components/autofill/core/common/autofill_features.cc:343](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_features.cc#343): Cờ mới, disabled theo source.
- `base_feature:AutofillEnableGradientGoogleLogos` · [to: components/autofill/core/common/autofill_payments_features.cc:204](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_payments_features.cc#204): Cờ mới, disabled theo source.
- `file:chrome/browser/resources/settings/autofill_page/autofill_ai_add_or_edit_dialog.html` · [from: chrome/browser/resources/settings/autofill_page/autofill_ai_add_or_edit_dialog.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/autofill_ai_add_or_edit_dialog.html), [to: chrome/browser/resources/settings/autofill_page/autofill_ai_add_or_edit_dialog.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/autofill_ai_add_or_edit_dialog.html): Đã đọc mọi hunk: bỏ gate save-to-wallet, thêm nhánh branding 2026.
- `file:chrome/browser/resources/settings/autofill_page/credit_card_list_entry.html` · [from: chrome/browser/resources/settings/autofill_page/credit_card_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/credit_card_list_entry.html), [to: chrome/browser/resources/settings/autofill_page/credit_card_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/credit_card_list_entry.html): Đã đọc mọi hunk: srcset logo qua hàm mới; các hunk aria-hidden thuộc event:settings-minor-a11y-and-cleanups.
- `file:chrome/browser/resources/settings/autofill_page/iban_list_entry.html` · [from: chrome/browser/resources/settings/autofill_page/iban_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/iban_list_entry.html), [to: chrome/browser/resources/settings/autofill_page/iban_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/iban_list_entry.html): Đã đọc hunk duy nhất: srcset logo qua hàm mới.
- `file:chrome/browser/resources/settings/autofill_page/pay_over_time_issuer_list_entry.html` · [from: chrome/browser/resources/settings/autofill_page/pay_over_time_issuer_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/autofill_page/pay_over_time_issuer_list_entry.html), [to: chrome/browser/resources/settings/autofill_page/pay_over_time_issuer_list_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/pay_over_time_issuer_list_entry.html): Đã đọc hunk duy nhất: srcset logo qua hàm mới.

## 13. Bốn cờ Autofill đổi trạng thái: hai bật mặc định, hai graduate và mất boolean trong Settings

Status: confirmed

Before: 148: kAutofillAiAvailableByDefault và kAutofillAiReauthRequired disabled; kAutofillEnableSupportForHomeAndWork và kYourSavedInfoPolicyAndExtentionToggleIndicators enabled và được đẩy xuống WebUI qua hai AddBoolean.

After: 151: hai cờ đầu enabled theo source trên Windows; hai cờ sau bị xoá cùng hai AddBoolean (enableSupportForHomeAndWork, enableYourSavedInfoPolicyAndExtentionToggleIndicators).

Mechanism: Bốn cờ cùng vòng đời: hai cờ đổi default nên Settings đọc giá trị mới qua autofillAiAvailableByDefault và autofillAiReauthRequired (vẫn còn trong strings provider), hai cờ đã launch nên boolean phía WebUI không cần nữa. identity_docs_page và travel_page thêm page-name/metric-entity-types cho settings-autofill-ai-entries-list cùng lúc.

Impact: Theo source, Autofill AI sẵn dùng mặc định và yêu cầu xác thực lại khi xem dữ liệu; hai khả năng kia trở thành mặc định không tắt được bằng cờ. Downstream đọc hai boolean đã xoá trong WebUI riêng sẽ nhận undefined.

Conditions: Windows; bốn giá trị lấy từ source, chưa biết Finch.

Action: Kiểm tra trang Your saved info: mục Autofill AI có sẵn và có yêu cầu xác thực lại; grep WebUI riêng cho hai boolean đã xoá.

Uncertainties: Chưa xác nhận Finch cho hai cờ đổi default.

- `base_feature:AutofillAiAvailableByDefault` · [from: components/autofill/core/common/autofill_features.cc:164](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#164), [to: components/autofill/core/common/autofill_features.cc:161](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_features.cc#161): disabled → enabled trên Windows.
- `base_feature:AutofillAiReauthRequired` · [from: components/autofill/core/common/autofill_features.cc:224](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#224), [to: components/autofill/core/common/autofill_features.cc:237](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/autofill/core/common/autofill_features.cc#237): disabled → enabled trên Windows.
- `base_feature:AutofillEnableSupportForHomeAndWork` · [from: components/autofill/core/common/autofill_features.cc:611](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#611): Cờ enabled bị xoá — graduate.
- `base_feature:YourSavedInfoPolicyAndExtentionToggleIndicators` · [from: components/autofill/core/common/autofill_features.cc:1141](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/autofill/core/common/autofill_features.cc#1141): Cờ enabled bị xoá — graduate.
- `webui_gate:settings_ui/enableSupportForHomeAndWork` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:650](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#650): AddBoolean tương ứng bị xoá.
- `webui_gate:settings_ui/enableYourSavedInfoPolicyAndExtentionToggleIndicators` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:424](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#424): AddBoolean bị xoá, chỗ của nó thành enableYourSavedInfoShoppingPage.

## 14. Glic: web actuation và experimental triggering vào section "Auto browse" mới và chuyển sang ghi qua handler thay vì bind pref

Status: confirmed

Before: 148: hai công tắc nằm trong section Data/Permissions của glic_subpage và bind trực tiếp pref glic.user_enabled_actuation_on_web và glic.experimental_triggering_enabled; hai pref này khai báo ở chrome/browser/glic/glic_pref_names.h. GlicHandler::ShouldShowWebActuationToggle tự quyết định hiện/ẩn bằng switch dòng lệnh, kGlicWebActuationSetting, kGlicWebActuationSettingsToggle, tier đăng ký và trạng thái pref. showGlicExperimentalTriggering = kGlicExperimentalTriggering && ShouldShowWebActuationToggle(profile).

After: 151: cả hai công tắc nằm trong section mới glicAutoBrowseSection, dùng no-set-pref với thuộc tính nội bộ (webActuationEnabledPref_, experimentalTriggeringEnabledPref_) và đọc/ghi qua bốn message mới getWebActuationEnabled, setWebActuationEnabled, getExperimentalTriggeringEnabled, setExperimentalTriggeringEnabled. Experimental triggering thêm cr-expand-button, hai cột When on/Consider và ba chuỗi consider (consider 3 có link safety URL). Toggle experimental triggering bị disable khi web actuation tắt, và setWebActuationEnabled(false) tự tắt experimental triggering. Hai pref chuyển sang chrome/browser/glic/glic_pref_names_internal.h với chú thích chỉ GlicEnabling được truy cập trực tiếp; khoá lưu không đổi. Quyết định hiện/ẩn chuyển vào glic::GlicEnabling (ShouldShowWebActuationToggle) và có thêm GlicHandler::ShouldShowExperimentalTriggeringToggle.

Mechanism: Vì WebUI không còn bind pref, GlicHandler đăng ký hai subscription mới trên GlicEnabling và phát glic-web-actuation-enabled-changed / glic-experimental-triggering-enabled-changed. ShouldShowExperimentalTriggeringToggle yêu cầu kGlicExperimentalTriggering, ShouldShowWebActuationToggle, IsExperimentalTriggeringUserControlled và pref không còn ở giá trị mặc định — browsertest mới xác nhận đúng thứ tự điều kiện đó. Hai finding "pref removed" là do khai báo rời khỏi header mà bộ quét đọc (glic_pref_names_internal.h không khớp hậu tố pref_names.h/.cc), không phải pref bị xoá: glic_pref_names.cc 151 vẫn RegisterBooleanPref cả hai.

Impact: Người dùng thấy hai công tắc này trong một section riêng, và experimental triggering chỉ bật được khi đã bật web actuation. Sản phẩm downstream có WebUI riêng bind thẳng hai pref sẽ thấy công tắc không còn tác dụng hai chiều: phải gọi bốn message mới; đọc/ghi pref trực tiếp vẫn chạy nhưng đi ngược chú thích upstream và bỏ qua logic GlicEnabling (ví dụ việc tắt kéo theo). Cùng file glic_handler.cc còn ba hunk đổi tên API hotkey (GetGlobalHotkey→GetToggleHotkey, GetSelectionGlobalHotkey→GetSelectionHotkey, LocalHotkeyManager::Hotkey→Command) — thay đổi riêng, chỉ ảnh hưởng mức biên dịch cho code patch vào GlicHandler.

Conditions: Windows; cần Glic bật và kGlicExperimentalTriggering cho công tắc thứ hai; thêm điều kiện enterprise (isWebActuationDisabledForEnterprise_) và policy (disallowedByAdmin_). Chưa biết Finch và cấu hình subscription tier.

Action: Mở chrome://settings/ai/glic: xác nhận section Auto browse, bật/tắt web actuation và kiểm tra experimental triggering tự tắt; kiểm tra pref trong Preferences file vẫn là hai khoá cũ. Nếu downstream có WebUI riêng, chuyển sang bốn message mới. Đối chiếu browsertest GetWebActuationEnabled/SetWebActuationEnabled/ShouldShowExperimentalTriggeringToggle_*; chưa chạy test.

Uncertainties: Chưa đọc glic::GlicEnabling nên chưa biết đủ điều kiện ShouldShowWebActuationToggle ở 151.

- `webui_control:settings/glic_page/glic_subpage/pref:glic.user_enabled_actuation_on_web#webActuationToggle` · [from: chrome/browser/resources/settings/glic_page/glic_subpage.html:387](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/glic_page/glic_subpage.html#387): Binding pref của webActuationToggle biến mất (chuyển sang thuộc tính nội bộ + no-set-pref).
- `webui_control:settings/glic_page/glic_subpage/pref:glic.experimental_triggering_enabled#glicExperimentalTriggeringToggle` · [from: chrome/browser/resources/settings/glic_page/glic_subpage.html:485](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/glic_page/glic_subpage.html#485): glicExperimentalTriggeringToggle không còn pref — cùng cơ chế.
- `webui_control:settings/glic_page/glic_subpage/id:experimentalTriggeringExpandButton` · [to: chrome/browser/resources/settings/glic_page/glic_subpage.html:552](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/glic_page/glic_subpage.html#552): Nút mở rộng mới cho phần giải thích experimental triggering.
- `webui_gate:settings_localized_strings_provider/showGlicExperimentalTriggering` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:993](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#993), [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1083](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1083): Gate rút gọn còn một lời gọi ShouldShowExperimentalTriggeringToggle(profile).
- `webui_gate:settings_localized_strings_provider/glicExperimentalTriggeringConsider3` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1042](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1042): Chuỗi consider 3 mới, ghép link safety URL qua glic::GetHelpCenterUrl.
- `pref:glic.user_enabled_actuation_on_web` · [from: chrome/browser/glic/glic_pref_names.h:151](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/glic/glic_pref_names.h#151): Khai báo pref rời khỏi glic_pref_names.h; xem mechanism — pref vẫn tồn tại.
- `pref:glic.experimental_triggering_enabled` · [from: chrome/browser/glic/glic_pref_names.h:103](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/glic/glic_pref_names.h#103): Cùng cơ chế với pref trên.
- `file:chrome/browser/resources/settings/glic_page/glic_subpage.html` · [from: chrome/browser/resources/settings/glic_page/glic_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/glic_page/glic_subpage.html), [to: chrome/browser/resources/settings/glic_page/glic_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/glic_page/glic_subpage.html): Đã đọc mọi hunk: section Auto browse, no-set-pref, disable theo web actuation; hunk mediaUnderstandingToggle thuộc event:settings-glic-media-understanding; các class="hr" thuộc event:settings-webui-refresh-2026.
- `file:chrome/browser/ui/webui/settings/glic_handler.cc` · [from: chrome/browser/ui/webui/settings/glic_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/glic_handler.cc), [to: chrome/browser/ui/webui/settings/glic_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/glic_handler.cc): Đã đọc mọi hunk: bốn message mới, hai subscription, logic hiện/ẩn chuyển sang GlicEnabling; ba hunk đổi tên hotkey là thay đổi riêng.
- `file:chrome/browser/ui/webui/settings/glic_handler_browsertest.cc` · [from: chrome/browser/ui/webui/settings/glic_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/glic_handler_browsertest.cc), [to: chrome/browser/ui/webui/settings/glic_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/glic_handler_browsertest.cc): Đã đọc mọi hunk: test mới cho bốn message và cho ShouldShowExperimentalTriggeringToggle.
- `file:chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc), [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc): Đã đọc mọi hunk của file chuỗi; hunk glic (experimental triggering, media understanding, activity URL) ở đây, các hunk khác thuộc event:settings-ai-page-entry-points, event:settings-ai-mode-search-section, event:settings-reset-v2-graduation, event:settings-appearance-bookmarks-bar, event:settings-appearance-side-panel-alignment, event:settings-appearance-ctrl-tab-mru, event:settings-tab-search-toggle-unconditional, event:settings-cpu-performance-tier, event:settings-autofill-email-verification, event:settings-autofill-wallet-branding, event:settings-autofill-card-benefits, event:settings-personal-context-links, event:settings-account-page-unification, event:settings-privacy-sandbox-ads-ux, event:settings-inline-cue-menu, event:settings-local-network-access-split.
- [to: chrome/browser/ui/webui/settings/glic_handler.cc:423](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/glic_handler.cc#423): ShouldShowWebActuationToggle chỉ còn gọi GlicEnabling; ShouldShowExperimentalTriggeringToggle mới.
- [to: chrome/browser/glic/glic_pref_names_internal.h:10](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/glic/glic_pref_names_internal.h#10): Hai khoá pref vẫn giữ nguyên tên, chỉ chuyển sang header internal với chú thích chỉ GlicEnabling được truy cập trực tiếp.
- [to: chrome/browser/glic/glic_pref_names.cc:90](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/glic/glic_pref_names.cc#90): 151 vẫn RegisterBooleanPref cho cả hai pref — không phải bị xoá.

## 15. Mục Process isolation (Windows) vẫn hiện khi pref local-state đã bật, dù cờ tắt

Status: confirmed

Before: 148: showProcessIsolationSetting = IsEnabled(features::kProcessIsolationSettings) && install_static::IsSystemInstall().

After: 151: showProcessIsolationSetting = install_static::IsSystemInstall() && (IsEnabled(features::kProcessIsolationSettings) || local_state->GetBoolean(prefs::kProcessIsolationEnabled)).

Mechanism: Thêm một đường bật thứ hai: nếu pref local state kProcessIsolationEnabled đã true thì mục cài đặt vẫn hiển thị để người dùng tắt được, kể cả sau khi cờ bị tắt lại (ví dụ Finch rút thí nghiệm).

Impact: Đây là thay đổi chỉ có trên Windows và liên quan trực tiếp tới sản phẩm chạy Windows: nếu từng bật process isolation cho người dùng, mục này sẽ tiếp tục hiện sau khi cờ tắt — không còn tình trạng bật rồi không tắt được. Điều kiện system install vẫn giữ.

Conditions: Windows, bản cài system-wide (IsSystemInstall). Pref nằm ở local state nên dùng chung mọi profile.

Action: Trên bản system install: bật cờ, bật mục process isolation, tắt cờ, mở lại chrome://settings và xác nhận mục vẫn hiện; kiểm tra pref kProcessIsolationEnabled trong Local State.

Uncertainties: Chưa đọc nơi ghi pref kProcessIsolationEnabled nên chưa biết ai đặt nó ngoài chính mục này.

- `webui_gate:settings_ui/showProcessIsolationSetting` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:542](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#542), [to: chrome/browser/ui/webui/settings/settings_ui.cc:555](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#555): Biểu thức gate thêm nhánh đọc pref local state.
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:552](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#552): Biểu thức mới trong khối BUILDFLAG(IS_WIN).

## 16. Windows: lời mời ghim vào taskbar trong Settings không còn cờ điều khiển

Status: confirmed

Before: 148: cờ kOfferPinToTaskbarInSettings (BUILDFLAG(IS_WIN), enabled theo source) bọc lời gọi browser_util::ShouldOfferToPin trong DefaultBrowserHandler; nếu tắt thì rơi xuống OnDefaultCheckFinished(can_pin=false).

After: 151: cờ bị xoá; ShouldOfferToPin luôn được gọi trên Windows và hàm return ngay sau đó.

Mechanism: Cờ đã enabled nên hành vi mặc định không đổi; chỉ mất cách tắt. include chrome/browser/ui/ui_features.h cũng bị bỏ.

Impact: Sản phẩm Windows muốn không mời ghim taskbar từ trang Settings không còn cờ để tắt — phải patch. Lưu ý đây là hành vi đụng tới shell người dùng (taskbar), nên đáng kiểm tra với cấu hình doanh nghiệp.

Conditions: Windows; phụ thuộc ShouldOfferToPin (kiểm tra trạng thái shell, ngoài phạm vi đã đọc).

Action: Mở chrome://settings/defaultBrowser và xác nhận hành vi ghim; nếu cần tắt, lên kế hoạch patch vì không còn cờ.

Uncertainties: Chưa đọc browser_util::ShouldOfferToPin nên chưa biết nó tự bỏ qua trong trường hợp nào.

- `base_feature:OfferPinToTaskbarInSettings` · [from: chrome/browser/ui/ui_features.cc:61](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/ui_features.cc#61): Cờ Windows enabled bị xoá.
- `file:chrome/browser/ui/webui/settings/settings_default_browser_handler.cc` · [from: chrome/browser/ui/webui/settings/settings_default_browser_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_default_browser_handler.cc), [to: chrome/browser/ui/webui/settings/settings_default_browser_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_default_browser_handler.cc): Đã đọc mọi hunk: bỏ nhánh theo cờ.

## 17. Trang Account và Google services dùng chung cho mọi nền tảng: điều kiện build dịch chuyển, hàng Sync có sub-label trên Windows

Status: confirmed

Before: 148: trong people_page.html, ba hàng account-subpage-row, google-services, sync-setup nằm trong <if expr="not is_chromeos">; ChromeOS có khối riêng với profile-row và một sync-setup có sub-label. Route ACCOUNT/GOOGLE_SERVICES tạo trong khối not is_chromeos. sync_controls bọc phần account-settings trong not is_chromeos; chuỗi accountPageTitle/accountDataTypesBody/googleServicesPageTitle nằm trong nhánh #else (không ChromeOS); historyTabsCheckboxLabel có #if !IS_CHROMEOS. people_handler chỉ đăng ký SyncShowSyncPassphraseDialog, ShowAccountSettingsUI, SetDatatype khi không phải ChromeOS. updateAccountSettingsStrings = false trên ChromeOS.

After: 151: ba hàng trở thành "Shared Elements" ngoài mọi điều kiện build và sync-setup có thêm sub-label getSyncAndNonPersonalizedServicesSubtext_; khối ChromeOS chỉ còn profile-row (kèm điều kiện shouldLinkToAccountSettingsPage_). Route ACCOUNT/GOOGLE_SERVICES chuyển ra ngoài khối not is_chromeos, chỉ còn guard replaceSyncPromosWithSignInPromos. sync_account_control bọc các control đăng nhập/đổi tài khoản vào not is_chromeos. sync_controls bỏ các #if !IS_CHROMEOS quanh phần account settings và thêm nhánh ChromeOS cho accountDataTypesBody. Chuỗi account* ra khỏi nhánh #else và manageDeviceAccounts thêm cho ChromeOS; account_page có cr-link-row manage-device-accounts (is_chromeos). people_handler đăng ký ba message đó cho mọi nền tảng. updateAccountSettingsStrings dùng cùng biểu thức trên mọi nền tảng.

Mechanism: Mười hai finding build_gate_changed là hai chiều của một việc, cộng một control chỉ có trên ChromeOS (manage-device-accounts): phần dùng chung ra khỏi điều kiện, phần riêng ChromeOS vào điều kiện. Trên Windows, tập control được biên dịch không đổi — trừ một điểm thật sự thấy được: hàng "Sync and Google services" nay có sub-label mà trước chỉ bản ChromeOS có.

Impact: Với sản phẩm Windows: hàng Sync có thêm dòng phụ; phần còn lại là dọn điều kiện build nên không đổi UI. Nếu sản phẩm có patch dựa trên vị trí các khối <if expr> trong năm file này thì patch sẽ xung đột. people_handler nay đăng ký ba message trên mọi nền tảng, nên WebUI dùng chung không cần nhánh theo OS nữa.

Conditions: Windows: not is_chromeos = true nên các control dùng chung vẫn được dựng. Sub-label phụ thuộc syncStatus.

Action: Mở chrome://settings/people và xác nhận hàng Sync có dòng phụ; chạy lại mọi patch downstream trên năm template này; kiểm tra trang /account và /googleServices với replaceSyncPromosWithSignInPromos bật.

Uncertainties: Chưa đọc getSyncAndNonPersonalizedServicesSubtext_ (file .ts) nên chưa biết nội dung dòng phụ trong từng trạng thái.

- `webui_control:settings/people_page/people_page/id:account-subpage-row` · [from: chrome/browser/resources/settings/people_page/people_page.html:110](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/people_page.html#110), [to: chrome/browser/resources/settings/people_page/people_page.html:139](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page.html#139): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/people_page/id:google-services` · [from: chrome/browser/resources/settings/people_page/people_page.html:133](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/people_page.html#133), [to: chrome/browser/resources/settings/people_page/people_page.html:164](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page.html#164): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/people_page/id:sync-setup` · [from: chrome/browser/resources/settings/people_page/people_page.html:127](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/people_page.html#127), [to: chrome/browser/resources/settings/people_page/people_page.html:156](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page.html#156): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_controls/id:mergedHistoryTabsToggle` · [from: chrome/browser/resources/settings/people_page/sync_controls.html:99](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_controls.html#99), [to: chrome/browser/resources/settings/people_page/sync_controls.html:105](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_controls.html#105): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/account_page/id:manage-device-accounts` · [to: chrome/browser/resources/settings/people_page/account_page.html:66](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/account_page.html#66): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:account-aware` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:258](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#258), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:265](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#265): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:dropdown-arrow` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:217](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#217), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:222](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#222): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:menu` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:295](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#295), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:304](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#304): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:remove-account-button` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:279](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#279), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:286](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#286): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:signIn` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:161](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#161), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:162](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#162): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:signout-button` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:228](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#228), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:233](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#233): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:sync-button` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:233](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#233), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:238](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#238): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `webui_control:settings/people_page/sync_account_control/id:turn-off` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html:241](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html#241), [to: chrome/browser/resources/settings/people_page/sync_account_control.html:246](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html#246): Điều kiện build của control đổi (vào hoặc ra khỏi khối is_chromeos) theo việc gộp trang Account.
- `file:chrome/browser/resources/settings/people_page/people_page.html` · [from: chrome/browser/resources/settings/people_page/people_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/people_page.html), [to: chrome/browser/resources/settings/people_page/people_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page.html): Đã đọc mọi hunk: ba hàng thành shared elements, thêm sub-label, khối ChromeOS gọn lại.
- `file:chrome/browser/resources/settings/people_page/people_page_index.html` · [from: chrome/browser/resources/settings/people_page/people_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/people_page_index.html), [to: chrome/browser/resources/settings/people_page/people_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page_index.html): Đã đọc mọi hunk: hai view account/googleServices ra khỏi khối not is_chromeos.
- `file:chrome/browser/resources/settings/people_page/account_page.html` · [from: chrome/browser/resources/settings/people_page/account_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/account_page.html), [to: chrome/browser/resources/settings/people_page/account_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/account_page.html): Đã đọc hunk duy nhất: thêm hàng manage-device-accounts cho ChromeOS.
- `file:chrome/browser/resources/settings/people_page/sync_controls.html` · [from: chrome/browser/resources/settings/people_page/sync_controls.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_controls.html), [to: chrome/browser/resources/settings/people_page/sync_controls.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_controls.html): Đã đọc mọi hunk: bỏ các #if quanh phần account settings, thêm nhánh chuỗi ChromeOS.
- `file:chrome/browser/resources/settings/people_page/sync_account_control.html` · [from: chrome/browser/resources/settings/people_page/sync_account_control.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/people_page/sync_account_control.html), [to: chrome/browser/resources/settings/people_page/sync_account_control.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/sync_account_control.html): Đã đọc mọi hunk: các control đăng nhập vào khối not is_chromeos.
- `file:chrome/browser/ui/webui/settings/people_handler.cc` · [from: chrome/browser/ui/webui/settings/people_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/people_handler.cc), [to: chrome/browser/ui/webui/settings/people_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/people_handler.cc): Đã đọc mọi hunk: ba message ra khỏi #if, thêm RecordSigninOffered (thuộc event:settings-signin-offered-metrics), chuyển GlobalBrowserCollection (thuộc event:settings-browser-window-interface), và điều kiện ClearSyncFeatureDisabledViaDashboard cho ChromeOS.
- `file:chrome/browser/ui/webui/settings/shared_settings_localized_strings_provider.cc` · [from: chrome/browser/ui/webui/settings/shared_settings_localized_strings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/shared_settings_localized_strings_provider.cc), [to: chrome/browser/ui/webui/settings/shared_settings_localized_strings_provider.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/shared_settings_localized_strings_provider.cc): Đã đọc mọi hunk: updateAccountSettingsStrings bỏ nhánh ChromeOS; hunk japaneseBrailleEnabled là thay đổi riêng chỉ cho ChromeOS.
- [to: chrome/browser/resources/settings/people_page/people_page.html:155](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/people_page/people_page.html#155): Hàng sync-setup dùng chung có sub-label.

## 18. Trang AI đổi tiêu đề và thêm bốn entry point mới (Suggestions, Skills, Indigo, AI Mode Workspace)

Status: confirmed

Before: 148: section AI lấy tiêu đề từ loadTimeData aiInnovationsPageTitle; trang AI có các hàng passwordChange, aiModeSearchRow, historySearch, compose. showAiPage = show_glic_section || show_ai_features_section, và enable_ai_mode_search được OR vào show_ai_features_section.

After: 151: section AI lấy tiêu đề từ khoá mới aiPageTitle; aiPageTitle được AddLocalizedString theo features::IsWebuiRefresh2026Enabled() — bật thì IDS_SETTINGS_AI_PAGE_TITLE, tắt thì vẫn IDS_SETTINGS_AI_INNOVATIONS_PAGE_TITLE (chuỗi cũ). Trang AI thêm aiSuggestionsRow, skillsRow, indigoRow, googleSearchAiModeWorkspaceRow; aiModeSearchRow bị bỏ. showAiPage = show_glic_section || show_ai_features_section || enable_ai_mode_search, và enable_ai_mode_search không còn cộng vào show_ai_features_section.

Mechanism: Bốn hàng mới đọc bốn loadTimeData boolean thêm vào vector kBooleans của settings_ui.cc: showAiSuggestionsControl (contextual_cueing::kContextualCueingV2), showSkillsSettingPage (features::kSkillsEnabled), showIndigoControl (features::kIndigo), showGoogleSearchAiModeWorkspaceControl (features::kGoogleSearchAiModeWorkspace). indigoRow và googleSearchAiModeWorkspaceRow là link ngoài, dùng ba URL mới (indigoSavedUrl từ feature param, kMyActivitySearchServicesAppsUrl, và một URL myactivity hardcode). Việc tách enable_ai_mode_search khỏi show_ai_features_section làm AI mode search mở trang AI nhưng không bật section "AI features".

Impact: Người dùng Windows thấy tên trang AI đổi chỉ khi webui refresh 2026 bật; các hàng mới chỉ xuất hiện khi cờ tương ứng bật (cả bốn tắt mặc định trên Windows trừ GoogleSearchAiModeWorkspace đã enabled theo source). Sản phẩm downstream dựng lại settings_menu hoặc trang AI phải đổi khoá chuỗi aiInnovationsPageTitle → aiPageTitle, nếu không nhãn trong menu và route AI trống.

Conditions: Windows. Tiêu đề phụ thuộc IsWebuiRefresh2026Enabled(). GoogleSearchAiModeWorkspace enabled theo source; kSkillsEnabled, kIndigo, kContextualCueingV2 chưa đọc được ở đây (khai báo ngoài phạm vi file đã đọc). Chưa biết Finch.

Action: Kiểm tra chrome://settings/ai với webui refresh bật/tắt: tên section và item menu. Bật từng cờ để xem bốn hàng mới; xác nhận ba URL mở đúng (test settings_ui_browsertest GoogleSearchAiModeWorkspaceUrl và GoogleSearchAiModeRestrictedUrl đã cố định giá trị). Grep mọi chỗ downstream còn dùng aiInnovationsPageTitle.

Uncertainties: Chưa chạy build/UI test, chưa biết cấu hình Finch của kSkillsEnabled, kIndigo, kContextualCueingV2 và IsWebuiRefresh2026Enabled trong sản phẩm.

- `webui_control:settings/ai_page/ai_page/label:aiInnovationsPageTitle` · [from: chrome/browser/resources/settings/ai_page/ai_page.html:4](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_page.html#4): Control settings-section nhãn aiInnovationsPageTitle biến mất khỏi ai_page.html.
- `webui_control:settings/ai_page/ai_page/label:aiPageTitle` · [to: chrome/browser/resources/settings/ai_page/ai_page.html:9](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html#9): Control settings-section nhãn aiPageTitle xuất hiện thay thế.
- `webui_control:settings/ai_page/ai_page/id:aiSuggestionsRow` · [to: chrome/browser/resources/settings/ai_page/ai_page.html:35](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html#35): cr-link-row aiSuggestionsRow mới, ẩn theo showAiSuggestionsControl_.
- `webui_control:settings/ai_page/ai_page/id:skillsRow` · [to: chrome/browser/resources/settings/ai_page/ai_page.html:43](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html#43): cr-link-row skillsRow mới, ẩn theo showSkillsSettingPage_.
- `webui_control:settings/ai_page/ai_page/id:indigoRow` · [to: chrome/browser/resources/settings/ai_page/ai_page.html:51](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html#51): cr-link-row indigoRow mới, link ngoài, ẩn theo showIndigoControl_.
- `webui_control:settings/ai_page/ai_page/id:googleSearchAiModeWorkspaceRow` · [to: chrome/browser/resources/settings/ai_page/ai_page.html:63](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html#63): cr-link-row googleSearchAiModeWorkspaceRow mới, link ngoài.
- `webui_gate:settings_ui/showAiPage` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:645](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#645), [to: chrome/browser/ui/webui/settings/settings_ui.cc:668](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#668): Biểu thức showAiPage thêm enable_ai_mode_search.
- `webui_gate:settings_localized_strings_provider/indigoSavedUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:545](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#545): Chuỗi indigoSavedUrl mới, lấy từ features::kIndigoSavedUrl.Get().
- `webui_gate:settings_localized_strings_provider/googleSearchAiModeWorkspaceUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:547](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#547): Chuỗi googleSearchAiModeWorkspaceUrl mới.
- `webui_gate:settings_localized_strings_provider/googleSearchAiModeRestrictedUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:549](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#549): Chuỗi googleSearchAiModeRestrictedUrl mới, hardcode myactivity.google.com.
- `base_feature:GoogleSearchAiModeWorkspace` · [to: chrome/common/chrome_features.cc:1046](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/chrome_features.cc#1046): Cờ kGoogleSearchAiModeWorkspace mới, enabled theo source trên Windows, gate hàng AIM Workspace.
- `file:chrome/browser/resources/settings/ai_page/ai_page.html` · [from: chrome/browser/resources/settings/ai_page/ai_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_page.html), [to: chrome/browser/resources/settings/ai_page/ai_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page.html): Đã đọc mọi hunk: đổi page-title và thêm bốn hàng, bỏ aiModeSearchRow.
- `file:chrome/browser/resources/settings/ai_page/ai_page_index.html` · [from: chrome/browser/resources/settings/ai_page/ai_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_page_index.html), [to: chrome/browser/resources/settings/ai_page/ai_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_page_index.html): Đã đọc mọi hunk: thêm view aiSuggestions và skills, chuyển aiModeSearch lên view không route.
- `file:chrome/browser/resources/settings/settings_menu/settings_menu.html` · [from: chrome/browser/resources/settings/settings_menu/settings_menu.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/settings_menu/settings_menu.html), [to: chrome/browser/resources/settings/settings_menu/settings_menu.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/settings_menu/settings_menu.html): Đã đọc hunk duy nhất: item menu đổi sang aiPageTitle.
- `file:chrome/browser/ui/webui/settings/settings_ui_browsertest.cc` · [from: chrome/browser/ui/webui/settings/settings_ui_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui_browsertest.cc), [to: chrome/browser/ui/webui/settings/settings_ui_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui_browsertest.cc): Đã đọc mọi hunk: hai test mới cố định hai URL AI mode, một test hồi quy Glic, và bỏ ENABLE_DICE_SUPPORT (hunk DICE thuộc event:settings-webui-plumbing).
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:631](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#631): Bốn boolean mới trong kBooleans và chuỗi aiSuggestionsHelpCenterArticleLink.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:511](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#511): aiPageTitle chọn chuỗi theo IsWebuiRefresh2026Enabled.

## 19. AI mode search chuyển từ trang con thành section của trang AI, chuỗi đổi sang V3 và thêm policy indicator

Status: confirmed

Before: 148: ai_mode_search_page là settings-subpage có route /ai/aiModeSearch, vào từ cr-link-row aiModeSearchRow trên trang AI; có hai cột When on / Things to consider và một cr-link-row "My Google Search history". enable_ai_mode_search = contextual_tasks::GetIsSmartTabSharingEnabled().

After: 151: cùng file trở thành settings-section (không còn route-path, được render trực tiếp trong ai_page_index), bỏ hai cột và bỏ hàng My Google Search history, nhãn đổi sang bộ V3, thêm nhánh policy với cr-policy-pref-indicator và toggle bị disable. enable_ai_mode_search = ContextualTasksContextService::GetIsSmartTabSharingEnabled(profile) && kContextualTasksContextSmartTabSharingDefaultOnAvailability.

Mechanism: Bốn chuỗi STS cũ bị xoá khỏi AddAiStrings và bốn chuỗi V3 thêm vào; chuỗi stsSettingsOption1SitesAddedHereWontBeReferenced chọn V2 hay V3 theo lens::features::kLensDeleteContextOnPageNavigation. Pref contextual_tasks.share_open_tabs_every_thread không đổi, chỉ đổi nhãn và thêm điều kiện disable. Gate giờ phụ thuộc profile (service) và một cờ mới, nên hai profile trong cùng build có thể khác nhau.

Impact: Người dùng không còn vào AI mode search qua một hàng riêng; nội dung nằm ngay trên trang AI và ít chữ hơn. Downstream deep-link tới /ai/aiModeSearch sẽ không còn route đó. Gate đổi từ cờ toàn cục sang điều kiện theo profile cộng một cờ mới (tắt mặc định trên Windows), nên mặc định 151 là không hiện section này.

Conditions: Windows; cần cả GetIsSmartTabSharingEnabled(profile) và kContextualTasksContextSmartTabSharingDefaultOnAvailability (disabled theo source). Chuỗi site-exclusion phụ thuộc kLensDeleteContextOnPageNavigation (enabled theo source).

Action: Kiểm tra mọi deep-link/đường dẫn tới /ai/aiModeSearch. Bật cờ mới + service để xem section trên chrome://settings/ai. So sánh chuỗi hiện ra với kLensDeleteContextOnPageNavigation bật/tắt. Thử policy cấm để xem indicator.

Uncertainties: Chưa đọc ContextualTasksContextService nên chưa biết điều kiện profile gồm những gì.

- `webui_control:settings/ai_page/ai_mode_search_page/label:stsSettingsEntrypointAiModeSearch` · [from: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#15): settings-subpage nhãn stsSettingsEntrypointAiModeSearch biến mất.
- `webui_control:settings/ai_page/ai_mode_search_page/label:stsSettingsEntrypointGoogleSearchAiMode` · [to: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:23](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#23): settings-section nhãn stsSettingsEntrypointGoogleSearchAiMode xuất hiện — chứng cứ trang con thành section.
- `webui_control:settings/ai_page/ai_mode_search_page/label:stsSettingsOption1ShareOpenTabsForEveryThread` · [from: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#17): Nhãn cũ ShareOpenTabsForEveryThread bị bỏ.
- `webui_control:settings/ai_page/ai_mode_search_page/label:stsSettingsOption1ShareOpenTabsForEveryThreadV3` · [to: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:27](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#27): Nhãn V3 thay thế.
- `webui_control:settings/ai_page/ai_mode_search_page/label:stsSettingsOption1MyGoogleSearchHistory` · [from: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:125](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#125): Hàng My Google Search history bị bỏ.
- `webui_control:settings/ai_page/ai_mode_search_page/pref:contextual_tasks.share_open_tabs_every_thread#shareTabsEveryThreadToggle` · [from: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:30](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#30), [to: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html:65](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html#65): Toggle giữ nguyên pref, chỉ đổi nhãn sang V3.
- `webui_control:settings/ai_page/ai_page/id:aiModeSearchRow` · [from: chrome/browser/resources/settings/ai_page/ai_page.html:13](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_page.html#13): Hàng vào trang con trên ai_page.html bị bỏ vì không còn trang con.
- `base_feature:ContextualTasksContextSmartTabSharingDefaultOnAvailability` · [to: components/contextual_tasks/public/features.cc:62](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/contextual_tasks/public/features.cc#62): Cờ mới là điều kiện thứ hai của enable_ai_mode_search.
- `base_feature:LensDeleteContextOnPageNavigation` · [to: components/lens/lens_features.cc:157](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/lens/lens_features.cc#157): Cờ mới chọn chuỗi site-exclusion V2/V3.
- `file:chrome/browser/resources/settings/ai_page/ai_mode_search_page.html` · [from: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html), [to: chrome/browser/resources/settings/ai_page/ai_mode_search_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_mode_search_page.html): Đã đọc mọi hunk của file.
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:646](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#646): enable_ai_mode_search đổi sang service theo profile cộng cờ mới; không còn OR vào show_ai_features_section.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:521](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#521): Chuỗi site-exclusion chọn theo kLensDeleteContextOnPageNavigation.

## 20. Trang con AI Suggestions mới, bật/tắt contextual cueing bằng pref ba trạng thái

Status: confirmed

Before: 148: không có route /ai/suggestions và không có file ai_suggestions_page.html (fetch đúng ref 148 trả upstream_404).

After: 151: route AI_SUGGESTIONS = /ai/suggestions, con của AI, guard showAiPage và showAiSuggestionsControl. Trang con có một settings-toggle-button ghi pref optimization_guide.contextual_cueing_setting_state bằng numeric-checked-value/numeric-unchecked-values, một cr-link-row dẫn Help Center, hai cột When on / Consider.

Mechanism: showAiSuggestionsControl = base::FeatureList::IsEnabled(contextual_cueing::kContextualCueingV2) (thêm vào vector kBooleans). Link Help Center đọc chuỗi mới aiSuggestionsHelpCenterArticleLink = contextual_cueing::kHelpCenterArticleLink.Get(). Chuỗi consider 1 chọn theo feature param contextual_cueing::kUsePrivateAi.Get(). Toggle dùng pref enum (FeatureOptInState) nên giá trị lưu là số, không phải boolean; khi policy cấm thì toggle disabled và hiện settings-ai-policy-indicator.

Impact: Khi kContextualCueingV2 bật, người dùng có thêm một trang con AI và một công tắc ghi pref optimization_guide.contextual_cueing_setting_state. Sản phẩm downstream muốn tắt hẳn phải tắt cờ hoặc policy; đọc pref phải xử lý giá trị số ba trạng thái chứ không phải bool.

Conditions: Windows; cần kContextualCueingV2. Nội dung chuỗi phụ thuộc param kUsePrivateAi. Policy enterprise có thể disable toggle. Chưa biết Finch.

Action: Bật kContextualCueingV2, mở chrome://settings/ai/suggestions, đổi công tắc và đọc lại pref (3 trạng thái), thử policy cấm để xem indicator. Kiểm tra param kHelpCenterArticleLink trỏ đúng.

Uncertainties: Chưa xác nhận giá trị mặc định của kContextualCueingV2 và kUsePrivateAi (khai báo ngoài file đã đọc).

- `webui_route:settings/AI_SUGGESTIONS` · [to: chrome/browser/resources/settings/route.ts:213](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#213): Route mới với guard showAiPage + showAiSuggestionsControl.
- `webui_control:settings/ai_page/ai_suggestions_page/label:aiSuggestionsLabel` · [to: chrome/browser/resources/settings/ai_page/ai_suggestions_page.html:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_suggestions_page.html#19): settings-subpage nhãn aiSuggestionsLabel mới.
- `webui_control:settings/ai_page/ai_suggestions_page/label:aiSuggestionsToggleLabel` · [to: chrome/browser/resources/settings/ai_page/ai_suggestions_page.html:24](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_suggestions_page.html#24): cr-link-row nhãn aiSuggestionsToggleLabel mới (link Help Center).
- `webui_control:settings/ai_page/ai_suggestions_page/pref:optimization_guide.contextual_cueing_setting_state#showSuggestionsToggle` · [to: chrome/browser/resources/settings/ai_page/ai_suggestions_page.html:57](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_suggestions_page.html#57): Toggle mới gắn pref contextual_cueing_setting_state.
- `webui_gate:settings_ui/aiSuggestionsHelpCenterArticleLink` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:643](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#643): Chuỗi link Help Center mới lấy từ feature param.
- `file:chrome/browser/resources/settings/ai_page/ai_suggestions_page.html` · [to: chrome/browser/resources/settings/ai_page/ai_suggestions_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_suggestions_page.html): File mới; đã đọc toàn bộ, kể cả nhánh policy.
- [to: chrome/browser/resources/settings/route.ts:211](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#211): Route AI_SUGGESTIONS tạo trong nhánh showAiSuggestionsControl.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:515](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#515): Chuỗi aiSuggestionsConsider1 chọn theo param kUsePrivateAi.

## 21. Trang con Skills mới với pref skills.enabled và link Skills gallery

Status: confirmed

Before: 148: không có route /ai/skills, không có file skills_page.html (upstream_404 ở ref 148) và không có pref skills.enabled trong phạm vi quét.

After: 151: route SKILLS = /ai/skills, con của AI, guard showAiPage và showSkillsSettingPage. Trang có settings-toggle-button gắn pref skills.enabled (var kChromeSkillsEnabled, khai báo ở components/skills/public/skills_prefs.cc), hai cột When on / Consider, và cr-link-row skillsGalleryLink mở ngoài.

Mechanism: showSkillsSettingPage = base::FeatureList::IsEnabled(features::kSkillsEnabled) trong vector kBooleans của settings_ui.cc; settings_ui.cc thêm include components/skills/features.h. Chuỗi skills* thêm vào AddAiStrings.

Impact: Một pref mới đồng bộ được ghi từ Settings khi cờ bật. Sản phẩm downstream cần quyết định có cho phép Skills hay không; hiện chỉ có cờ build/runtime, chưa thấy policy trong phạm vi đã đọc.

Conditions: Windows; cần features::kSkillsEnabled. Chưa đọc được default của cờ (khai báo ở components/skills/features.cc, ngoài phạm vi packet).

Action: Bật kSkillsEnabled, mở chrome://settings/ai/skills, đổi công tắc và kiểm tra pref skills.enabled được ghi/đồng bộ; kiểm tra link gallery.

Uncertainties: Chưa đọc khai báo features::kSkillsEnabled nên chưa biết default trên Windows.

- `webui_route:settings/SKILLS` · [to: chrome/browser/resources/settings/route.ts:216](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#216): Route SKILLS mới với guard showSkillsSettingPage.
- `webui_control:settings/ai_page/skills_page/label:skillsSettingLabel` · [to: chrome/browser/resources/settings/ai_page/skills_page.html:7](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/skills_page.html#7): settings-subpage nhãn skillsSettingLabel mới.
- `webui_control:settings/ai_page/skills_page/pref:skills.enabled#skillsToggle` · [to: chrome/browser/resources/settings/ai_page/skills_page.html:9](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/skills_page.html#9): Toggle mới gắn pref skills.enabled.
- `webui_control:settings/ai_page/skills_page/id:skillsGalleryLink` · [to: chrome/browser/resources/settings/ai_page/skills_page.html:44](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/skills_page.html#44): cr-link-row skillsGalleryLink mới.
- `pref:skills.enabled` · [to: components/skills/public/skills_prefs.cc:11](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/skills/public/skills_prefs.cc#11): Pref skills.enabled (kChromeSkillsEnabled) mới xuất hiện ở 151.
- `file:chrome/browser/resources/settings/ai_page/skills_page.html` · [to: chrome/browser/resources/settings/ai_page/skills_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/skills_page.html): File mới; đã đọc toàn bộ.
- [to: chrome/browser/resources/settings/route.ts:214](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#214): Route SKILLS tạo trong nhánh showSkillsSettingPage.

## 22. Your saved info có trang Shopping mới (đơn hàng, vận chuyển) với opt-in riêng

Status: confirmed

Before: 148: Your saved info chỉ có identity docs và travel; không có route /shopping, không có shopping_page.html (upstream_404 ở ref 148) và không có boolean enableYourSavedInfoShoppingPage.

After: 151: route YOUR_SAVED_INFO_SHOPPING = /shopping với guard enableYourSavedInfoSettingsPage + enableYourSavedInfoShoppingPage; trang có settings-toggle-button optInToggle (opt-in kiểu shoppingOptedIn_, không bind pref trực tiếp) và một settings-autofill-ai-entries-list theo pref autofill.autofill_ai.shopping_entities_enabled; trang Your saved info thêm category-reference-card shoppingManagerButton với chips orders/shipments.

Mechanism: enableYourSavedInfoShoppingPage = base::FeatureList::IsEnabled(autofill::features::kYourSavedInfoSettingsPageShoppingIntegration) — AddBoolean này thay đúng chỗ AddBoolean của enableYourSavedInfoPolicyAndExtentionToggleIndicators đã bị xoá. Toggle opt-in bị disable theo eligibility/opt-in/pref autofill.profile_enabled, và có extension-controlled-indicator.

Impact: Khi cờ bật, người dùng có một trang con mới lưu đơn hàng/vận chuyển — dữ liệu mới được Autofill AI giữ. Downstream cần cân nhắc policy cho loại dữ liệu này; cờ chưa đọc được default nên chưa kết luận mặc định.

Conditions: Windows; cần enableYourSavedInfoSettingsPage (cờ kYourSavedInfoSettingsPage, đã bật mặc định ở 151 — xem event:settings-your-saved-info-default-on) và kYourSavedInfoSettingsPageShoppingIntegration.

Action: Bật cờ shopping, mở chrome://settings/shopping, bật opt-in và kiểm tra pref autofill.autofill_ai.shopping_entities_enabled cùng dữ liệu đồng bộ.

Uncertainties: Chưa đọc khai báo kYourSavedInfoSettingsPageShoppingIntegration nên chưa biết default.

- `webui_route:settings/YOUR_SAVED_INFO_SHOPPING` · [to: chrome/browser/resources/settings/route.ts:240](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#240): Route shopping mới.
- `webui_gate:settings_ui/enableYourSavedInfoShoppingPage` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:438](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#438): Boolean gate mới thay chỗ boolean indicators bị xoá.
- `webui_control:settings/your_saved_info_page/shopping_page/id:optInToggle` · [to: chrome/browser/resources/settings/your_saved_info_page/shopping_page.html:9](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/shopping_page.html#9): Toggle opt-in mới.
- `webui_control:settings/your_saved_info_page/shopping_page/label:shoppingCardTitle` · [to: chrome/browser/resources/settings/your_saved_info_page/shopping_page.html:7](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/shopping_page.html#7): settings-subpage nhãn shoppingCardTitle mới.
- `file:chrome/browser/resources/settings/your_saved_info_page/shopping_page.html` · [to: chrome/browser/resources/settings/your_saved_info_page/shopping_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/shopping_page.html): File mới; đã đọc toàn bộ (hunk link row Lorem Ipsum thuộc event:settings-personal-context-links).
- `file:chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html` · [from: chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html), [to: chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html): Đã đọc mọi hunk: card shopping và card suggestions-from-Gemini (hunk sau thuộc event:settings-personal-context-links).
- `file:chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page_index.html` · [from: chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page_index.html), [to: chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page_index.html): Đã đọc mọi hunk: thêm view shopping và view suggestionsFromGemini.
- [to: chrome/browser/resources/settings/route.ts:227](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#227): Hai route mới trong nhánh enableYourSavedInfoSettingsPage.

## 23. Personal Context vào Settings: trang con "Suggestions from Gemini" mới (chuỗi còn là Lorem Ipsum) thay chỗ link accessibility annotator

Status: confirmed

Before: 148: settings_ui.cc đặt showAccessibilityAnnotatorSettingsLink = false kèm TODO(b/493907185), và collapsible_autofill_settings_card có cr-link-row accessibilityAnnotatorSettingsLink dùng tạm chuỗi privacyPageTitle (TODO b/494479460). Không có route suggestionsFromGemini, không có pref autofill.personal_context.settings_toggle_status, không có URL personal context.

After: 151: boolean false cứng và link annotator bị xoá; thay bằng showPersonalContextSettingsLink = enablement_service->GetEnablementState() == kEnabled và cr-link-row personalContextSettingsLink có chuỗi thật (IDS_PERSONAL_CONTEXT_SETTINGS_TITLE/_DESCRIPTION_DESKTOP). Thêm route SUGGESTIONS_FROM_GEMINI = /autofill/suggestionsFromGemini, trang con suggestions_from_gemini_subpage.html mới, gate showSuggestionsFromGeminiSettings = autofill::ShouldShowPersonalContextAutofillSetting(autofill_client, enablement_service), gate isAtMemoryEnabled = autofill::MayPerformAtMemoryAction(kShowAtMemoryInSettings, ...), hai URL personal context, và bốn cr-link-row suggestionsFromGeminiLinkRow trên your_saved_info_page, identity_docs_page, travel_page, shopping_page.

Mechanism: Cả hai gate dựa trên PersonalContextEnablementService theo profile (và với at-memory còn thêm subscription eligibility, prefs và GoogleGroupsManager), không phải một cờ đơn. Trang con có ba phần: toggle ghi pref autofill.personal_context.settings_toggle_status, hàng Manage connected apps (URL mới), và một card at-memory với cr-shortcut-input cho phím tắt. Điểm cần lưu: nhãn của trang con, của toggle và của cả bốn link row vẫn là chuỗi cứng "Lorem Ipsum" với TODO(crbug.com/512202637) "Add strings and make them translatable" ở 151.0.7922.138.

Impact: Nếu gate bật trong sản phẩm, người dùng sẽ thấy văn bản placeholder "Lorem Ipsum" ở 5 chỗ trong Settings — đây là tính năng chưa hoàn thiện dù đã có mặt trong source của bản 151 này. Link accessibility annotator (trước luôn ẩn vì boolean false) biến mất hoàn toàn; downstream từng bật nó bằng patch phải chuyển sang personal context.

Conditions: Windows; phụ thuộc PersonalContextEnablementService theo profile, autofill client, subscription eligibility và Google groups. Các điều kiện này chưa đọc được trong phạm vi đã đọc, nên chưa kết luận mặc định bật/tắt.

Action: Trước khi bật bất kỳ điều kiện personal context, kiểm tra chrome://settings/autofill/suggestionsFromGemini và trang Your saved info: nếu thấy "Lorem Ipsum" thì chặn tính năng cho tới khi upstream thay chuỗi. Đọc ShouldShowPersonalContextAutofillSetting và MayPerformAtMemoryAction để biết điều kiện thật.

Uncertainties: Chưa đọc PersonalContextEnablementService, ShouldShowPersonalContextAutofillSetting, MayPerformAtMemoryAction nên không biết mặc định của các gate này.

- `webui_route:settings/SUGGESTIONS_FROM_GEMINI` · [to: chrome/browser/resources/settings/route.ts:243](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#243): Route mới trong nhánh showSuggestionsFromGeminiSettings.
- `webui_gate:settings_ui/showSuggestionsFromGeminiSettings` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:697](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#697): Gate mới theo enablement service và autofill client.
- `webui_gate:settings_ui/isAtMemoryEnabled` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:700](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#700): Gate at-memory mới, dùng cho card phím tắt trong trang con.
- `webui_gate:settings_ui/showPersonalContextSettingsLink` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:708](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#708): Gate link personal context mới.
- `webui_gate:settings_ui/showAccessibilityAnnotatorSettingsLink` · [from: chrome/browser/ui/webui/settings/settings_ui.cc:677](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc#677): Boolean false cứng cho annotator bị xoá.
- `webui_gate:settings_localized_strings_provider/personalContextSettingsUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1983](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1983): URL trang cài đặt personal context.
- `webui_gate:settings_localized_strings_provider/personalContextConnectedAppsUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1985](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1985): URL quản lý connected apps, dùng ở hàng manageConnectedAppsLinkRow.
- `webui_gate:settings_localized_strings_provider/accessibilityAnnotatorSettingsUrl` · [from: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1845](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1845): URL annotator bị xoá cùng link.
- `webui_control:settings/your_saved_info_page/collapsible_autofill_settings_card/id:accessibilityAnnotatorSettingsLink` · [from: chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html:27](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html#27): Link annotator trong card autofill bị xoá.
- `webui_control:settings/your_saved_info_page/collapsible_autofill_settings_card/id:personalContextSettingsLink` · [to: chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html:26](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html#26): Link personal context thay chỗ, dùng chuỗi thật.
- `webui_control:settings/your_saved_info_page/identity_docs_page/id:suggestionsFromGeminiLinkRow` · [to: chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html:25](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html#25): Link row Lorem Ipsum trên identity docs.
- `webui_control:settings/your_saved_info_page/travel_page/id:suggestionsFromGeminiLinkRow` · [to: chrome/browser/resources/settings/your_saved_info_page/travel_page.html:25](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/travel_page.html#25): Link row Lorem Ipsum trên travel.
- `webui_control:settings/your_saved_info_page/your_saved_info_page/id:suggestionsFromGeminiLinkRow` · [to: chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html:104](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/your_saved_info_page.html#104): Link row Lorem Ipsum trên trang Your saved info.
- `webui_control:settings/your_saved_info_page/shopping_page/id:suggestionsFromGeminiLinkRow` · [to: chrome/browser/resources/settings/your_saved_info_page/shopping_page.html:22](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/shopping_page.html#22): Link row Lorem Ipsum trên shopping.
- `webui_control:settings/autofill_page/suggestions_from_gemini_subpage/id:manageConnectedAppsLinkRow` · [to: chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html:13](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html#13): Hàng Manage connected apps trong trang con.
- `webui_control:settings/autofill_page/suggestions_from_gemini_subpage/pref:autofill.personal_context.settings_toggle_status#suggestionsFromGeminiToggle` · [to: chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html:9](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html#9): Toggle ghi pref personal context.
- `webui_control:settings/autofill_page/suggestions_from_gemini_subpage/settings-subpage#0` · [to: chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html:5](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html#5): settings-subpage của trang con mới.
- `pref:autofill.personal_context.settings_toggle_status` · [to: components/personal_context/core/personal_context_prefs.h:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/personal_context/core/personal_context_prefs.h#19): Pref mới (kPersonalContextInAutofillSettingsToggleStatus).
- `file:chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html` · [to: chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html): File mới; đã đọc toàn bộ, kể cả card at-memory và quality logging.
- `file:chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html` · [from: chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html), [to: chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/collapsible_autofill_settings_card.html): Đã đọc hunk duy nhất: đổi link annotator sang personal context.
- `file:chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html` · [from: chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html), [to: chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/identity_docs_page.html): Đã đọc mọi hunk: thêm link row, thêm page-name/metric-entity-types cho entries list (hunk sau thuộc event:settings-autofill-ai-defaults).
- `file:chrome/browser/resources/settings/your_saved_info_page/travel_page.html` · [from: chrome/browser/resources/settings/your_saved_info_page/travel_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/your_saved_info_page/travel_page.html), [to: chrome/browser/resources/settings/your_saved_info_page/travel_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/your_saved_info_page/travel_page.html): Như identity_docs_page.
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:695](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#695): Ba gate personal context và hai chuỗi mới, thay cho boolean annotator false.
- [to: chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/autofill_page/suggestions_from_gemini_subpage.html#1): Chuỗi Lorem Ipsum và TODO crbug.com/512202637 ngay trong bản 151.

## 24. Site setting mới "Inline cue menu" cho Glic selection, route tạo không điều kiện

Status: confirmed

Before: 148: không có ContentSettingsType::INLINE_CUE_MENU trong bảng tên UI, không có route inlineCueMenu và không có trang inline_cue_menu_page.html.

After: 151: site_settings_helper thêm {INLINE_CUE_MENU, "inline-cue-menu"} và đẩy loại này vào base_types khi kGlicSelectionPrompt bật và param kGlicSelectionEnableSiteSettings true; settings_ui.cc thêm boolean enableInlineCueMenuContentSetting với cùng điều kiện; route SITE_SETTINGS_INLINE_CUE_MENU được tạo không guard; privacy_page_index thêm view và trang mới có radio-group mặc định cùng danh sách ngoại lệ.

Mechanism: Khác các route site-settings khác, route này nằm ngoài mọi if trong route.ts nên luôn tồn tại; việc hiện/ẩn do mục trên trang Site settings và loại content setting quyết định (enableInlineCueMenuContentSetting). Đây là lý do finding route không có guard nào.

Impact: Khi Glic selection bật kèm param site settings, người dùng có thêm một quyền theo site. Vì route luôn tồn tại, deep-link chrome://settings/content/inlineCueMenu mở được trang cả khi tính năng chưa bật — cần kiểm tra trang dựng ra trông thế nào trong trường hợp đó.

Conditions: Windows; cần features::kGlicSelectionPrompt và param kGlicSelectionEnableSiteSettings. Chưa đọc default của cờ/param đó (khai báo ngoài phạm vi đã đọc).

Action: Bật kGlicSelectionPrompt + param, mở chrome://settings/content và trang inlineCueMenu; thử deep-link khi tính năng tắt để xem route không guard dựng gì.

Uncertainties: Chưa đọc khai báo kGlicSelectionPrompt/kGlicSelectionEnableSiteSettings nên chưa biết default.

- `webui_route:settings/SITE_SETTINGS_INLINE_CUE_MENU` · [to: chrome/browser/resources/settings/route.ts:150](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#150): Route mới, danh sách guard rỗng.
- `webui_gate:settings_ui/enableInlineCueMenuContentSetting` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:588](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#588): Boolean gate mới trong settings_ui.cc.
- `webui_control:settings/site_settings/inline_cue_menu_page/label:siteSettingsInlineCueMenu` · [to: chrome/browser/resources/settings/site_settings/inline_cue_menu_page.html:2](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/site_settings/inline_cue_menu_page.html#2): settings-subpage của trang mới.
- `webui_control:settings/privacy_page/privacy_page_index/id:siteSettingsInlineCueMenu` · [to: chrome/browser/resources/settings/privacy_page/privacy_page_index.html:366](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/privacy_page_index.html#366): View mới trong privacy_page_index.
- `file:chrome/browser/resources/settings/site_settings/inline_cue_menu_page.html` · [to: chrome/browser/resources/settings/site_settings/inline_cue_menu_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/site_settings/inline_cue_menu_page.html): File mới; đã đọc toàn bộ.
- [to: chrome/browser/resources/settings/route.ts:149](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/route.ts#149): Route inlineCueMenu tạo ngoài mọi điều kiện.
- [to: chrome/browser/ui/webui/settings/site_settings_helper.cc:617](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/site_settings_helper.cc#617): INLINE_CUE_MENU chỉ vào base_types khi cờ và param bật.

## 25. Trang Speed thêm mục ghi đè CPU performance tier, đọc thông tin CPU qua message mới

Status: confirmed

Before: 148: speed_page chỉ có preload/tab hover; handler không có message nào về CPU; không có pref cpu_performance_tier_override và boolean cpuPerformanceEnabled.

After: 151: boolean cpuPerformanceEnabled = IsEnabled(blink::features::kCpuPerformance); speed_page thêm (trong dom-if) phần tiêu đề, dòng thông tin CPU (model + nominal tier) và settings-dropdown-menu cpuPerformanceOverrideDropdown dùng pref-key cpu_performance_tier_override; handler thêm message getCpuPerformanceInfo trả hardwareTier/model/cores từ content::cpu_performance; thêm 11 chuỗi cpuPerformance* và plural string cpuPerformanceCores.

Mechanism: Ghi đè là pref số (kCpuPerformanceTierOverride) được ContentBrowserClient đọc qua GetCpuPerformanceTierOverride; handler vẫn luôn báo tier phần cứng thật, không phải giá trị ghi đè — browsertest mới cố định đúng điểm này.

Impact: Khi cờ bật, người dùng (và QA) có thể buộc Chromium coi máy thuộc tier khác, ảnh hưởng các tính năng đọc tier. Với sản phẩm downstream đây là một pref mới có thể đổi hành vi hiệu năng toàn trình duyệt, nên cần policy/kiểm soát nếu không muốn người dùng đổi.

Conditions: Windows; cần blink::features::kCpuPerformance (chưa đọc default).

Action: Bật kCpuPerformance, mở chrome://settings/performance (Speed), đổi dropdown và kiểm tra pref cùng hành vi của tính năng đọc tier; đối chiếu browsertest GetCpuPerformanceInfo.

Uncertainties: Chưa đọc blink::features::kCpuPerformance nên chưa biết default.

- `webui_gate:settings_localized_strings_provider/cpuPerformanceEnabled` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1327](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1327): Boolean gate mới.
- `webui_control:settings/performance_page/speed_page/pref:cpu_performance_tier_override#cpuPerformanceOverrideDropdown` · [to: chrome/browser/resources/settings/performance_page/speed_page.html:142](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/performance_page/speed_page.html#142): Dropdown mới theo pref override.
- `pref:cpu_performance_tier_override` · [to: chrome/common/pref_names.h:3259](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/pref_names.h#3259): Pref mới (kCpuPerformanceTierOverride).
- `file:chrome/browser/resources/settings/performance_page/speed_page.html` · [from: chrome/browser/resources/settings/performance_page/speed_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/performance_page/speed_page.html), [to: chrome/browser/resources/settings/performance_page/speed_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/performance_page/speed_page.html): Đã đọc mọi hunk của speed_page.
- `file:chrome/browser/ui/webui/settings/performance_handler.cc` · [from: chrome/browser/ui/webui/settings/performance_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/performance_handler.cc), [to: chrome/browser/ui/webui/settings/performance_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/performance_handler.cc): Đã đọc mọi hunk: message getCpuPerformanceInfo và chuyển sang GlobalBrowserCollection (hunk sau thuộc event:settings-browser-window-interface).
- `file:chrome/browser/ui/webui/settings/performance_handler_browsertest.cc` · [from: chrome/browser/ui/webui/settings/performance_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/performance_handler_browsertest.cc), [to: chrome/browser/ui/webui/settings/performance_handler_browsertest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/performance_handler_browsertest.cc): Đã đọc mọi hunk: test xác nhận handler trả tier phần cứng dù có override.

## 26. Thanh dấu trang: thêm lựa chọn ba trạng thái (dropdown) bên cạnh công tắc cũ, theo cờ NtpSimplificationBookmarkBar

Status: confirmed

Before: 148: appearance_page có một settings-toggle-button không id, bind pref bookmark_bar.show_on_all_tabs, nhãn showBookmarksBar. Không có pref bookmark_bar.visibility_state, không có boolean ntpSimplificationBookmarksBarEnabled.

After: 151: hai nhánh dom-if. Khi ntpSimplificationBookmarksBarEnabled_ tắt: công tắc cũ, nay có id showBookmarksBar. Khi bật: một settings-dropdown-menu bookmarksBarVisibilityDropdown dùng pref-key bookmark_bar.visibility_state với ba lựa chọn (always show / only on NTP / always hide) và ba chuỗi mới.

Mechanism: ntpSimplificationBookmarksBarEnabled = IsEnabled(ntp_features::kNtpSimplificationBookmarkBar). Pref mới bookmark_bar.visibility_state (kBookmarkBarVisibilityState, components/bookmarks/common/bookmark_pref_names.h) là enum ba giá trị, khác pref boolean cũ. Hai finding control của pref cũ (removed + added) là cùng một công tắc được thêm id, không phải hai control khác nhau.

Impact: Khi cờ bật, người dùng đổi từ công tắc sang lựa chọn ba trạng thái và giá trị được ghi vào pref mới — pref boolean cũ có thể không còn được UI ghi, nên sản phẩm đọc bookmark_bar.show_on_all_tabs phải kiểm tra lại nguồn sự thật. Chưa thấy code migration giữa hai pref trong phạm vi đã đọc.

Conditions: Windows; cần ntp_features::kNtpSimplificationBookmarkBar (chưa đọc default). pageVisibility.bookmarksBar vẫn ẩn cả hai biến thể.

Action: Bật cờ, mở chrome://settings/appearance, đổi dropdown và kiểm tra cả hai pref; tìm code đọc bookmark_bar.show_on_all_tabs trong sản phẩm.

Uncertainties: Chưa đọc kNtpSimplificationBookmarkBar nên chưa biết default; chưa tìm thấy migration từ pref boolean sang pref enum.

- `webui_control:settings/appearance_page/appearance_page/pref:bookmark_bar.show_on_all_tabs` · [from: chrome/browser/resources/settings/appearance_page/appearance_page.html:164](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/appearance_page/appearance_page.html#164): Công tắc không id biến mất.
- `webui_control:settings/appearance_page/appearance_page/pref:bookmark_bar.show_on_all_tabs#showBookmarksBar` · [to: chrome/browser/resources/settings/appearance_page/appearance_page.html:168](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html#168): Công tắc có id showBookmarksBar xuất hiện (cùng pref, cùng nhãn).
- `webui_control:settings/appearance_page/appearance_page/pref:bookmark_bar.visibility_state#bookmarksBarVisibilityDropdown` · [to: chrome/browser/resources/settings/appearance_page/appearance_page.html:180](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html#180): Dropdown mới theo pref enum.
- `webui_gate:settings_localized_strings_provider/ntpSimplificationBookmarksBarEnabled` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:637](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#637): Boolean gate mới.
- `pref:bookmark_bar.visibility_state` · [to: components/bookmarks/common/bookmark_pref_names.h:49](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/bookmarks/common/bookmark_pref_names.h#49): Pref enum mới xuất hiện ở 151.
- `file:chrome/browser/resources/settings/appearance_page/appearance_page.html` · [from: chrome/browser/resources/settings/appearance_page/appearance_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/appearance_page/appearance_page.html), [to: chrome/browser/resources/settings/appearance_page/appearance_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html): Đã đọc mọi hunk của appearance_page.html; hunk side panel thuộc event:settings-appearance-side-panel-alignment, hunk ctrl+tab thuộc event:settings-appearance-ctrl-tab-mru, hunk tab search thuộc event:settings-tab-search-toggle-unconditional, hunk pref-key thuộc event:settings-dropdown-menu-pref-key, hunk on-disable-extension-click thuộc event:settings-extension-indicator-event.

## 27. Vị trí side panel: một dropdown chung thành danh sách dropdown theo từng panel, với pref override riêng

Status: confirmed

Before: 148: một settings-dropdown-menu id=sidePanelPosition, nhãn sidePanelPosition, bind pref side_panel.is_right_aligned.

After: 151: hàng tiêu đề sidePanelPosition, rồi một dom-repeat trên configurableSidePanels_ tạo một dropdown cho mỗi panel (no-set-pref, value lấy từ prefs.side_panel.alignment_overrides, ghi qua onOverrideAlignmentChange_), cộng một dropdown cuối cho "Chrome panels" dùng pref-key side_panel.is_right_aligned với nhãn mới sidePanelAlignmentChromePanels. Danh sách panel lấy từ chuỗi JSON mới configurableSidePanelAlignments = JSONWriter(side_panel_prefs::GetConfigurableSidePanelAlignments(profile)).

Mechanism: Người dùng giờ đặt được vị trí riêng cho từng panel; giá trị riêng nằm trong pref side_panel.alignment_overrides còn pref boolean cũ chỉ còn áp cho các panel của Chrome. Finding control "added" không id là dropdown trong dom-repeat; finding relabelled là dropdown cuối đổi nhãn.

Impact: Người dùng thấy nhiều dropdown thay vì một. Sản phẩm đọc side_panel.is_right_aligned để suy ra vị trí của mọi panel sẽ sai khi có override; phải đọc thêm side_panel.alignment_overrides.

Conditions: Windows; danh sách panel do GetConfigurableSidePanelAlignments(profile) quyết định nên khác nhau theo profile/build.

Action: Mở chrome://settings/appearance, đặt vị trí cho từng panel và đọc cả hai pref; đọc side_panel_prefs::GetConfigurableSidePanelAlignments nếu sản phẩm có panel riêng.

Uncertainties: Chưa đọc GetConfigurableSidePanelAlignments nên chưa biết panel nào vào danh sách.

- `webui_gate:settings_localized_strings_provider/configurableSidePanelAlignments` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:663](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#663): Chuỗi JSON mới liệt kê panel cấu hình được.
- `webui_control:settings/appearance_page/appearance_page/pref:side_panel.is_right_aligned` · [to: chrome/browser/resources/settings/appearance_page/appearance_page.html:267](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html#267): Dropdown trong dom-repeat (không id) là control mới.
- `webui_control:settings/appearance_page/appearance_page/pref:side_panel.is_right_aligned#sidePanelPosition` · [from: chrome/browser/resources/settings/appearance_page/appearance_page.html:241](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/appearance_page/appearance_page.html#241), [to: chrome/browser/resources/settings/appearance_page/appearance_page.html:285](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html#285): Dropdown cuối đổi nhãn sang sidePanelAlignmentChromePanels.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:659](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#659): configurableSidePanelAlignments ghi JSON từ GetConfigurableSidePanelAlignments(profile).

## 28. Công tắc mới "Ctrl+Tab theo thứ tự dùng gần nhất" trong Appearance

Status: confirmed

Before: 148: không có cờ kCtrlTabMru, pref browser.ctrl_tab_mru, boolean showCtrlTabMru hay công tắc nào.

After: 151: cờ kCtrlTabMru (disabled theo source trên Windows) trong chrome/browser/ui/ui_features.cc; boolean showCtrlTabMru; appearance_page có settings-toggle-button ctrlTabMru bind pref browser.ctrl_tab_mru trong dom-if showCtrlTabMru_; chuỗi ctrlTabMru mới.

Mechanism: Một tính năng điều hướng tab mới được phơi ra Settings, gate bằng một cờ mới.

Impact: Mặc định không thấy gì (cờ tắt). Nếu sản phẩm bật cờ, người dùng có thêm một công tắc và một pref mới.

Conditions: Windows; cần features::kCtrlTabMru.

Action: Bật kCtrlTabMru và kiểm tra công tắc cùng hành vi Ctrl+Tab.

Uncertainties: Chưa xác nhận rollout.

- `webui_gate:settings_localized_strings_provider/showCtrlTabMru` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:656](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#656): Boolean gate mới.
- `webui_control:settings/appearance_page/appearance_page/pref:browser.ctrl_tab_mru#ctrlTabMru` · [to: chrome/browser/resources/settings/appearance_page/appearance_page.html:254](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_page.html#254): Công tắc mới.
- `pref:browser.ctrl_tab_mru` · [to: chrome/common/pref_names.h:655](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/pref_names.h#655): Pref mới (kCtrlTabMru).
- `base_feature:CtrlTabMru` · [to: chrome/browser/ui/ui_features.cc:49](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/ui_features.cc#49): Cờ mới, disabled theo source.

## 29. Glic có công tắc Media understanding mới, gate bằng khả năng headless caption

Status: confirmed

Before: 148: không có công tắc media understanding, không có pref glic.media_understanding_enabled và không có boolean headlessCaptionsEnabled.

After: 151: glic_subpage thêm settings-toggle-button mediaUnderstandingToggle bind pref glic.media_understanding_enabled, nằm trong dom-if headlessCaptionsEnabled_; loadTimeData thêm headlessCaptionsEnabled = captions::IsHeadlessCaptionFeatureSupported().

Mechanism: Công tắc dùng sub-label-with-link và có learn-more riêng. Điều kiện hiện là khả năng headless caption của build chứ không phải một cờ Glic — tên boolean nói về caption nhưng chỗ dùng duy nhất trong scope là công tắc Glic này.

Impact: Người dùng có thêm một công tắc quyền cho Glic khi build hỗ trợ headless caption. Downstream cần biết công tắc này phụ thuộc thành phần caption, nên tắt/không build caption sẽ làm công tắc biến mất dù Glic vẫn bật.

Conditions: Windows; cần Glic bật và captions::IsHeadlessCaptionFeatureSupported() true. Chưa đọc hàm đó nên chưa biết nó phụ thuộc cờ hay thành phần cài thêm.

Action: Mở trang Glic trên build có/không hỗ trợ headless caption và so sánh; đổi công tắc rồi đọc pref glic.media_understanding_enabled.

Uncertainties: Chưa đọc captions::IsHeadlessCaptionFeatureSupported() nên chưa biết điều kiện đầy đủ.

- `webui_control:settings/glic_page/glic_subpage/pref:glic.media_understanding_enabled#mediaUnderstandingToggle` · [to: chrome/browser/resources/settings/glic_page/glic_subpage.html:380](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/glic_page/glic_subpage.html#380): Công tắc mới bind pref media understanding.
- `pref:glic.media_understanding_enabled` · [to: chrome/browser/glic/glic_pref_names.h:149](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/glic/glic_pref_names.h#149): Pref mới xuất hiện ở 151 trong glic_pref_names.h.
- `webui_gate:settings_localized_strings_provider/headlessCaptionsEnabled` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1075](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1075): Boolean gate mới; chỗ dùng duy nhất trong scope là công tắc này.
- [to: chrome/browser/resources/settings/glic_page/glic_subpage.html:379](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/glic_page/glic_subpage.html#379): dom-if headlessCaptionsEnabled_ bọc mediaUnderstandingToggle.

## 30. Bộ giao diện "webui refresh 2026" vào Settings qua thuộc tính trên <html> và selector :host-context

Status: confirmed

Before: 148: không có chuỗi webuiRefresh2026; settings.html mở thẻ <html> chỉ với dir/lang/class="loading".

After: 151: settings_ui.cc thêm AddString("webuiRefresh2026", IsWebuiRefresh2026Enabled() ? "webui-refresh-2026" : ""); settings.html chèn $i18n{webuiRefresh2026} và $i18n{roundedIconsAttribute} làm thuộc tính của <html> cùng một quy tắc html[webui-refresh-2026] cho màu nền; ai_info_card và clear_browsing_data_dialog thêm khối :host-context([webui-refresh-2026]); nhiều template thêm class="hr".

Mechanism: Một thuộc tính trên phần tử gốc được dùng làm công tắc CSS cho toàn trang, nên không cần nhân đôi template. Cùng cơ chế này quyết định tiêu đề trang AI (xem event:settings-ai-page-entry-points).

Impact: Khi bật, giao diện Settings đổi nền/ngăn cách và một số màu. Sản phẩm có CSS riêng cho Settings phải kiểm tra lại với thuộc tính này bật, vì selector :host-context([webui-refresh-2026]) sẽ ghi đè biến màu.

Conditions: Windows; phụ thuộc features::IsWebuiRefresh2026Enabled() (chưa đọc được hàm trong phạm vi đã đọc).

Action: Bật webui refresh 2026 và xem chrome://settings (nền, ngăn cách, card thông tin AI, hộp thoại xoá dữ liệu); so CSS riêng của sản phẩm.

Uncertainties: Chưa đọc features::IsWebuiRefresh2026Enabled() nên chưa biết điều kiện/default.

- `webui_gate:settings_ui/webuiRefresh2026` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:719](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#719): Chuỗi mới trả tên thuộc tính hoặc chuỗi rỗng.
- `file:chrome/browser/resources/settings/settings.html` · [from: chrome/browser/resources/settings/settings.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/settings.html), [to: chrome/browser/resources/settings/settings.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/settings.html): Đã đọc mọi hunk: hai thuộc tính i18n trên <html> và quy tắc nền.
- `file:chrome/browser/resources/settings/ai_page/ai_info_card.html` · [from: chrome/browser/resources/settings/ai_page/ai_info_card.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/ai_page/ai_info_card.html), [to: chrome/browser/resources/settings/ai_page/ai_info_card.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/ai_page/ai_info_card.html): Đã đọc mọi hunk: khối :host-context([webui-refresh-2026]).

## 31. Metrics consent restructure: Settings có thể ẩn công tắc báo cáo thống kê và API chuyển sang namespace metrics

Status: confirmed

Before: 148: personalization_options luôn dựng settings-toggle-button metricsReportingControl (hoặc cr-link-row trên ChromeOS); handler gọi IsMetricsReportingPolicyManaged() và ChangeMetricsReportingState() ở phạm vi toàn cục.

After: 151: settings_ui.cc thêm boolean shouldUseMetricsConsentRestructure = metrics::MetricsReportingChoiceService::ShouldUseMetricsConsentRestructure(local_state); personalization_options bọc cả hai biến thể control trong dom-if !shouldUseMetricsConsentRestructure_; handler gọi metrics::IsMetricsReportingPolicyManaged() và metrics::ChangeMetricsReportingState(); unittest dùng MetricsReportingChoiceService::IsBasicMetricsReportingEnabled và ClearCachedFeatureStateForTesting.

Mechanism: Quyết định dựa trên local state qua một service mới có cache (nên test phải xoá cache). Khi restructure bật, công tắc cũ biến mất khỏi trang Privacy — nơi đồng ý mới nằm ngoài phạm vi các file đã đọc.

Impact: Sản phẩm downstream phải biết công tắc "Help improve Chrome" có thể không còn trên trang Privacy tuỳ local state, và code gọi hai hàm metrics đã chuyển namespace sẽ không biên dịch. Chưa xác định được UI thay thế ở đâu.

Conditions: Windows; phụ thuộc ShouldUseMetricsConsentRestructure(local_state) — chưa đọc hàm nên chưa biết điều kiện (có thể là cờ + trạng thái local state).

Action: Đọc components/metrics/metrics_reporting_choice_service.* để biết điều kiện; mở trang Privacy ở cả hai trạng thái và tìm nơi đồng ý mới; cập nhật code downstream gọi ChangeMetricsReportingState.

Uncertainties: Chưa đọc MetricsReportingChoiceService nên chưa biết điều kiện bật và UI thay thế.

- `webui_gate:settings_ui/shouldUseMetricsConsentRestructure` · [to: chrome/browser/ui/webui/settings/settings_ui.cc:314](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#314): Boolean gate mới.
- `file:chrome/browser/ui/webui/settings/metrics_reporting_handler.cc` · [from: chrome/browser/ui/webui/settings/metrics_reporting_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/metrics_reporting_handler.cc), [to: chrome/browser/ui/webui/settings/metrics_reporting_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/metrics_reporting_handler.cc): Đã đọc mọi hunk: hai hàm chuyển sang namespace metrics.
- `file:chrome/browser/ui/webui/settings/metrics_reporting_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/metrics_reporting_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/metrics_reporting_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/metrics_reporting_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/metrics_reporting_handler_unittest.cc): Đã đọc mọi hunk: test dùng service mới và xoá cache.
- `file:chrome/browser/resources/settings/privacy_page/personalization_options.html` · [from: chrome/browser/resources/settings/privacy_page/personalization_options.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/privacy_page/personalization_options.html), [to: chrome/browser/resources/settings/privacy_page/personalization_options.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/privacy_page/personalization_options.html): Đã đọc mọi hunk: cả hai biến thể control bị bọc dom-if.

## 32. Trang Search bản mới: thông báo "controlled by extension" riêng, truyền prefs xuống danh sách shortcut, và getSearchEnginesList thành đường cấm

Status: confirmed

Before: 148: khi DSE do extension kiểm soát, search_page luôn dùng extension-controlled-indicator; không có file extension_controlled_message.html; các trang shortcut và settings-search-engines-list không nhận prefs; menu "Manage extension" ẩn theo engine.extension; GetSearchEnginesList không có CHECK; list_controller dùng UpdateIdToTemplateURLMapping và table_model()->RowCount().

After: 151: với searchSettingsUpdateEnabled_ bật, search_page dùng phần tử mới extension-controlled-message (file mới, có icon info và disclaimer theo tên extension); prefs được truyền xuống site_shortcuts_page, feature_shortcuts_page, search_engines_list và search_engine_entry; menu ẩn theo engine.isOmniboxExtension; hàng Active shortcuts thêm aria-label ghép hai chuỗi và báo sự kiện mở/đóng; GetSearchEnginesList mở đầu bằng CHECK(!IsEnabled(switches::kSearchSettingsUpdate)); list_controller gọi Refresh() và table_model()->engine_count().

Mechanism: Hai cấu hình trang Search tồn tại song song: bản cũ dùng getSearchEnginesList, bản mới dùng getCategorizedTemplateUrls. CHECK mới là cách upstream chặn việc gọi API cũ khi bản mới bật. Danh sách starter pack bị vô hiệu hoá nay tính theo AIM eligibility và pref kGeminiSettings thay vì chỉ profile.

Impact: Nếu sản phẩm bật kSearchSettingsUpdate nhưng WebUI riêng còn gọi getSearchEnginesList, handler sẽ CHECK-fail (crash). Finding relabel của activeShortcutsRow chỉ là thêm aria-label, không đổi chữ hiển thị. extension-controlled-message là phần tử mới cần dịch (ba chuỗi controlledByExtension* mới).

Conditions: Windows; phụ thuộc switches::kSearchSettingsUpdate (boolean searchSettingsUpdate trong settings_ui.cc, không đổi ở bản này).

Action: Nếu bật kSearchSettingsUpdate: grep WebUI riêng cho getSearchEnginesList; mở chrome://settings/search với một extension kiểm soát tìm kiếm để xem thông báo mới; kiểm tra ba chuỗi controlledByExtension* đã dịch.

Uncertainties: Chưa đọc AimEligibilityService nên chưa biết điều kiện ai_mode_enabled.

- `webui_control:settings/search_page/site_shortcuts_page/id:activeShortcutsRow` · [from: chrome/browser/resources/settings/search_page/site_shortcuts_page.html:30](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/site_shortcuts_page.html#30), [to: chrome/browser/resources/settings/search_page/site_shortcuts_page.html:30](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/site_shortcuts_page.html#30): Hàng Active shortcuts thêm aria-label (nhãn đọc được đổi, chữ hiển thị không).
- `file:chrome/browser/ui/webui/settings/search_engines_handler.cc` · [from: chrome/browser/ui/webui/settings/search_engines_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/search_engines_handler.cc), [to: chrome/browser/ui/webui/settings/search_engines_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/search_engines_handler.cc): Đã đọc mọi hunk: CHECK mới, Refresh/engine_count, starter pack theo AIM + pref, và metric hijacking (thuộc event:settings-search-hijacking-metrics).
- `file:chrome/browser/resources/settings/search_page/search_page.html` · [from: chrome/browser/resources/settings/search_page/search_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/search_page.html), [to: chrome/browser/resources/settings/search_page/search_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/search_page.html): Đã đọc mọi hunk: hai nhánh indicator/message, đổi tên listener extension.
- `file:chrome/browser/resources/settings/search_page/search_page_index.html` · [from: chrome/browser/resources/settings/search_page/search_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/search_page_index.html), [to: chrome/browser/resources/settings/search_page/search_page_index.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/search_page_index.html): Đã đọc mọi hunk: truyền prefs xuống hai trang shortcut.
- `file:chrome/browser/resources/settings/search_page/extension_controlled_message.html` · [to: chrome/browser/resources/settings/search_page/extension_controlled_message.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/extension_controlled_message.html): File mới; đã đọc toàn bộ.
- `file:chrome/browser/resources/settings/search_page/search_engines_list.html` · [from: chrome/browser/resources/settings/search_page/search_engines_list.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/search_engines_list.html), [to: chrome/browser/resources/settings/search_page/search_engines_list.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/search_engines_list.html): Đã đọc mọi hunk: truyền prefs xuống từng entry.
- `file:chrome/browser/resources/settings/search_page/search_engine_entry.html` · [from: chrome/browser/resources/settings/search_page/search_engine_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/search_engine_entry.html), [to: chrome/browser/resources/settings/search_page/search_engine_entry.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/search_engine_entry.html): Đã đọc mọi hunk: onViewOrEditClick_ và điều kiện isOmniboxExtension.
- `file:chrome/browser/resources/settings/search_page/feature_shortcuts_page.html` · [from: chrome/browser/resources/settings/search_page/feature_shortcuts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/feature_shortcuts_page.html), [to: chrome/browser/resources/settings/search_page/feature_shortcuts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/feature_shortcuts_page.html): Đã đọc mọi hunk: prefs và sự kiện expand.
- `file:chrome/browser/resources/settings/search_page/site_shortcuts_page.html` · [from: chrome/browser/resources/settings/search_page/site_shortcuts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/site_shortcuts_page.html), [to: chrome/browser/resources/settings/search_page/site_shortcuts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/site_shortcuts_page.html): Đã đọc mọi hunk: prefs, sự kiện expand, aria-label.
- `file:chrome/browser/resources/settings/search_page/search_engine_icon.html` · [from: chrome/browser/resources/settings/search_page/search_engine_icon.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/search_engine_icon.html), [to: chrome/browser/resources/settings/search_page/search_engine_icon.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/search_engine_icon.html): Đã đọc mọi hunk: thêm alt="" và aria-hidden cho favicon.
- [to: chrome/browser/ui/webui/settings/search_engines_handler.cc:216](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/search_engines_handler.cc#216): CHECK(!IsEnabled(switches::kSearchSettingsUpdate)) ở đầu GetSearchEnginesList.

## 33. settings-dropdown-menu chuyển sang Lit và đổi API từ pref="{{...}}" sang pref-key="..."

Status: confirmed

Before: 148: settings_dropdown_menu.html là template Polymer (dom-if/dom-repeat, on-change, aria-label$); mọi chỗ dùng truyền hai chiều pref="{{prefs.some.path}}".

After: 151: template thành settings_dropdown_menu.html.ts trả lit html (@change, ?disabled, this.menuOptions.map); chỗ dùng truyền pref-key="some.path" (dạng chuỗi đường dẫn) và có thêm no-set-pref + value cho trường hợp ghi qua handler. Các file đã đổi trong scope: captions_page (7 dropdown), live_translate, appearance_fonts_page (5), keyboard_shortcut_page, appearance_page, speed_page.

Mechanism: Lit không hỗ trợ two-way binding như Polymer nên phần tử tự lấy pref từ PrefsMixin bằng đường dẫn chuỗi. Đây là lý do nhiều finding webui_control đổi/đi kèm pref trong các trang dùng dropdown.

Impact: Bất kỳ template downstream nào còn dùng settings-dropdown-menu với pref="{{...}}" sẽ hỏng âm thầm: phần tử không nhận pref, dropdown rỗng/không ghi được, và Polymer không báo lỗi. Phải đổi sang pref-key. Đây là thay đổi API có rủi ro cao nhất trong nhóm WebUI của bản nâng cấp này.

Conditions: Windows; áp dụng mọi nơi dùng settings-dropdown-menu.

Action: Grep downstream cho "settings-dropdown-menu" kèm pref= và đổi sang pref-key; kiểm tra từng dropdown (captions, fonts, font size, side panel, tab strip, keyboard shortcut, cpu tier) mở ra và ghi pref đúng.

- `file:chrome/browser/resources/settings/controls/settings_dropdown_menu.html` · [from: chrome/browser/resources/settings/controls/settings_dropdown_menu.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/controls/settings_dropdown_menu.html): Template Polymer không còn ở 151 (upstream_404).
- `file:chrome/browser/resources/settings/controls/settings_dropdown_menu.html.ts` · [to: chrome/browser/resources/settings/controls/settings_dropdown_menu.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/controls/settings_dropdown_menu.html.ts): Template Lit mới với cùng cấu trúc select/option.
- `file:chrome/browser/resources/settings/a11y_page/captions_page.html` · [from: chrome/browser/resources/settings/a11y_page/captions_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/a11y_page/captions_page.html), [to: chrome/browser/resources/settings/a11y_page/captions_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/a11y_page/captions_page.html): Đã đọc mọi hunk: 7 dropdown đổi sang pref-key.
- `file:chrome/browser/resources/settings/a11y_page/live_translate.html` · [from: chrome/browser/resources/settings/a11y_page/live_translate.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/a11y_page/live_translate.html), [to: chrome/browser/resources/settings/a11y_page/live_translate.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/a11y_page/live_translate.html): Đã đọc hunk duy nhất: dropdown đổi sang pref-key.
- `file:chrome/browser/resources/settings/appearance_page/appearance_fonts_page.html` · [from: chrome/browser/resources/settings/appearance_page/appearance_fonts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/appearance_page/appearance_fonts_page.html), [to: chrome/browser/resources/settings/appearance_page/appearance_fonts_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/appearance_page/appearance_fonts_page.html): Đã đọc mọi hunk: 5 dropdown font đổi sang pref-key.
- `file:chrome/browser/resources/settings/search_page/keyboard_shortcut_page.html` · [from: chrome/browser/resources/settings/search_page/keyboard_shortcut_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/search_page/keyboard_shortcut_page.html), [to: chrome/browser/resources/settings/search_page/keyboard_shortcut_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/search_page/keyboard_shortcut_page.html): Đã đọc hunk duy nhất: dropdown đổi sang pref-key.

## 34. Safety Hub: danh sách quyền đã thu hồi đổi từ mảng chuỗi sang mảng {type, settingValue}

Status: confirmed

Before: 148: GetUnusedSitePermissionsFromDict yêu cầu mỗi phần tử permissions là chuỗi (CHECK(permission.is_string())) và handler trả về mảng chuỗi tên nhóm quyền; PermissionsData giữ permission_types.

After: 151: mỗi phần tử phải là dict (CHECK(permission.is_dict())) có kType và kSettingValue; PermissionsData giữ map permissions (type → value); handler trả mảng dict.

Mechanism: Thay đổi hai chiều giữa WebUI và handler để mang theo giá trị setting chứ không chỉ loại quyền (cần cho quyền không phải ALLOW/BLOCK đơn giản).

Impact: Đây là đổi hợp đồng WebUI↔C++: JS downstream gửi mảng chuỗi như 148 sẽ làm CHECK(permission.is_dict()) thất bại; JS đọc kết quả như chuỗi sẽ nhận object. Cần cập nhật cả hai phía cùng lúc.

Conditions: Windows; áp dụng cho Safety Hub unused/abusive site permissions.

Action: Grep WebUI downstream cho site_settings kPermissions / allowPermissionsAgainForUnusedSite và cập nhật sang dạng dict; đối chiếu unittest đã đổi sang FindString(kType).

- `file:chrome/browser/ui/webui/settings/safety_hub_handler.cc` · [from: chrome/browser/ui/webui/settings/safety_hub_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/safety_hub_handler.cc), [to: chrome/browser/ui/webui/settings/safety_hub_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/safety_hub_handler.cc): Đã đọc mọi hunk: CHECK đổi sang dict, map permissions thay set.
- `file:chrome/browser/ui/webui/settings/safety_hub_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/safety_hub_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/safety_hub_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/safety_hub_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/safety_hub_handler_unittest.cc): Đã đọc mọi hunk: test đọc kType trong dict; thêm hai ContentSettingsType vào danh sách kỳ vọng.
- [to: chrome/browser/ui/webui/settings/safety_hub_handler.cc:86](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/safety_hub_handler.cc#86): CHECK(permission.is_dict()) và đọc kType/kSettingValue.

## 35. HaTS trang Security tách thành hai message: securityPageHatsRequest (3 tham số) và securityPageV2HatsRequest (4 tham số)

Status: confirmed

Before: 148: chỉ có message securityPageHatsRequest, nhận 4 tham số (interaction, safe browsing state, thời gian, SecuritySettingsBundleSetting), gửi survey kHatsSurveyTriggerSettingsSecurity.

After: 151: securityPageHatsRequest trở lại dạng 3 tham số và vẫn dùng trigger kHatsSurveyTriggerSettingsSecurity; bản 4 tham số đổi tên thành securityPageV2HatsRequest với trigger mới kHatsSurveyTriggerSettingsSecurityV2 và hàm dữ liệu riêng GetSecurityPageV2ProductSpecificStringData.

Mechanism: Hai trang Security (bản cũ và v2) giờ có hai survey riêng; hàm GetSecurityPageProductSpecificStringData được dựng lại cho bản 3 tham số, kèm kiểm tra thời gian trên trang và param security-page-require-interaction.

Impact: WebUI nào gửi securityPageHatsRequest với 4 tham số như ở 148 sẽ chạm CHECK_EQ(3U, args.size()) trong handler, tức crash tiến trình renderer-initiated message. Downstream có trang Security riêng phải chọn đúng message theo phiên bản trang.

Conditions: Windows; survey phụ thuộc pref kSafeBrowsingSurveysEnabled, param thời gian và cấu hình HaTS/Finch.

Action: Grep WebUI downstream cho securityPageHatsRequest và đếm tham số; nếu là trang v2 thì đổi sang securityPageV2HatsRequest. Đối chiếu unittest HandleSecurityPageHatsRequest_* ; chưa chạy test.

Uncertainties: Chưa biết cấu hình HaTS thực tế của sản phẩm.

- `file:chrome/browser/ui/webui/settings/hats_handler.cc` · [from: chrome/browser/ui/webui/settings/hats_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/hats_handler.cc), [to: chrome/browser/ui/webui/settings/hats_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/hats_handler.cc): Đã đọc mọi hunk: thêm message V2, dựng lại hàm 3 tham số, hai trigger khác nhau.
- `file:chrome/browser/ui/webui/settings/hats_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/hats_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/hats_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/hats_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/hats_handler_unittest.cc): Đã đọc mọi hunk: test tách theo hai trigger, thêm test require-interaction.
- [to: chrome/browser/ui/webui/settings/hats_handler.cc:79](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/hats_handler.cc#79): securityPageHatsRequest mới CHECK_EQ(3U, args.size()).

## 36. Hạ tầng WebUI của Settings: tracked element thành singleton theo document, đổi thứ tự tham số Mojo của theme color picker, bỏ ENABLE_DICE_SUPPORT quanh batch upload promo

Status: confirmed

Before: 148: SettingsUI::CreateHelpBubbleHandler tự truyền danh sách ElementIdentifier cho HelpBubbleHandler; help_bubble.mojom có method BindTrackedElementHandler(pending_receiver<TrackedElementHandler>); ThemeColorPickerHandlerFactory.CreateThemeColorPickerHandler(pending_receiver<...Handler> handler, pending_remote<...Client> client); batch upload promo (BindInterface, CreateBatchUploadPromoHandler, chuỗi plural) nằm trong #if BUILDFLAG(ENABLE_DICE_SUPPORT).

After: 151: SettingsUI constructor gọi ui::TrackedElementHandlerDocumentSingleton::Register(this, {...5 identifier}) và CreateHelpBubbleHandler lấy singleton theo RenderFrameHost; method BindTrackedElementHandler bị xoá khỏi help_bubble.mojom; thứ tự tham số CreateThemeColorPickerHandler đảo thành (client, handler); các khối ENABLE_DICE_SUPPORT quanh batch upload promo bị bỏ.

Mechanism: Ba thay đổi hạ tầng trong cùng file: vòng đời tracked element chuyển từ per-handler sang per-document, một method Mojo bị bỏ vì không còn cần bind riêng, và một factory đổi thứ tự tham số. Việc bỏ ENABLE_DICE_SUPPORT làm batch upload promo được biên dịch trên mọi cấu hình (Windows vốn đã có DICE nên không đổi hành vi ở đây).

Impact: Đổi thứ tự tham số của CreateThemeColorPickerHandler là thay đổi hợp đồng Mojo: mọi nơi override hoặc gọi factory này (WebUI khác, code downstream) phải đổi theo, nếu không sẽ lỗi biên dịch — và nếu chỉ đổi một phía thì nhầm receiver/remote. Xoá BindTrackedElementHandler làm code gọi method đó không còn biên dịch được. Build không có DICE nay phải biên dịch được batch upload promo.

Conditions: Windows. Mojo ở đây là giao tiếp trong cùng bản build (WebUI ↔ browser) nên không có vấn đề lệch phiên bản giữa hai tiến trình khác bản.

Action: Grep downstream cho CreateThemeColorPickerHandler và BindTrackedElementHandler; biên dịch lại các WebUI dùng theme color picker. Kiểm tra help bubble trong Settings vẫn hiện đúng chỗ.

- `mojo_method:help_bubble.mojom.HelpBubbleHandler.BindTrackedElementHandler` · [from: ui/webui/resources/cr_components/help_bubble/help_bubble.mojom:132](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/help_bubble/help_bubble.mojom#132): Method Mojo bị xoá khỏi help_bubble.mojom.
- `mojo_method:theme_color_picker.mojom.ThemeColorPickerHandlerFactory.CreateThemeColorPickerHandler` · [from: ui/webui/resources/cr_components/theme_color_picker/theme_color_picker.mojom:58](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/theme_color_picker/theme_color_picker.mojom#58), [to: ui/webui/resources/cr_components/theme_color_picker/theme_color_picker.mojom:58](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/theme_color_picker/theme_color_picker.mojom#58): Thứ tự tham số đảo; settings_ui.cc đổi chữ ký override tương ứng.
- `file:chrome/browser/ui/webui/settings/settings_ui.cc` · [from: chrome/browser/ui/webui/settings/settings_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_ui.cc), [to: chrome/browser/ui/webui/settings/settings_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc): Đã đọc mọi hunk của settings_ui.cc; các hunk gate riêng thuộc các event khác đã nêu ở chúng.
- [to: chrome/browser/ui/webui/settings/settings_ui.cc:830](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui.cc#830): Chữ ký CreateThemeColorPickerHandler đảo thứ tự tham số.

## 37. Các handler Settings bỏ chrome::FindBrowserWithTab/FindLastActive, chuyển sang GlobalBrowserCollection và BrowserWindowInterface

Status: confirmed

Before: 148: các handler include chrome/browser/ui/browser_finder.h và dùng chrome::FindBrowserWithTab(), chrome::FindLastActive(), chrome::GetIncognitoBrowserCount(); phần lớn giữ con trỏ Browser*.

After: 151: include đổi sang browser_window/public/global_browser_collection.h (và browser_window_interface.h), gọi GlobalBrowserCollection::GetInstance()->FindBrowserWithTab(), ->GetLastActiveBrowser(), ->GetIncognitoBrowserCount(); biến đổi sang BrowserWindowInterface*. Nơi còn cần Browser* dùng browser->GetBrowserForMigrationOnly() (people_handler) hoặc browser->GetWindow() (import_data_handler).

Mechanism: Đây là một bước trong quá trình tách Browser thành BrowserWindowInterface của upstream. Mười file trong phạm vi Settings đổi lời gọi: tám file ở event này cộng people_handler.cc và performance_handler.cc (hai file đó thuộc event khác); ngoài ra settings_clear_browsing_data_handler.cc và site_settings_handler.cc chỉ bỏ include browser_finder.h.

Impact: Không đổi hành vi. Với downstream: mọi patch trong các handler này dùng Browser*/browser_finder.h sẽ không biên dịch; cần chuyển sang BrowserWindowInterface và GlobalBrowserCollection. Đây là loại thay đổi gây xung đột merge lặng lẽ nhất khi nâng cấp.

Conditions: Windows; thuần mức biên dịch.

Action: Grep downstream trong chrome/browser/ui/webui/settings cho browser_finder.h, FindBrowserWithTab, FindLastActive, GetIncognitoBrowserCount và chuyển sang API mới.

- `file:chrome/browser/ui/webui/settings/about_handler.cc` · [from: chrome/browser/ui/webui/settings/about_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/about_handler.cc), [to: chrome/browser/ui/webui/settings/about_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/about_handler.cc): Ba chỗ FindBrowserWithTab → GlobalBrowserCollection; đã đọc mọi hunk.
- `file:chrome/browser/ui/webui/settings/appearance_handler.cc` · [from: chrome/browser/ui/webui/settings/appearance_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/appearance_handler.cc), [to: chrome/browser/ui/webui/settings/appearance_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/appearance_handler.cc): Hai chỗ FindLastActive → GetLastActiveBrowser.
- `file:chrome/browser/ui/webui/settings/browser_lifetime_handler.cc` · [from: chrome/browser/ui/webui/settings/browser_lifetime_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/browser_lifetime_handler.cc), [to: chrome/browser/ui/webui/settings/browser_lifetime_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/browser_lifetime_handler.cc): GetIncognitoBrowserCount → phương thức của collection.
- `file:chrome/browser/ui/webui/settings/import_data_handler.cc` · [from: chrome/browser/ui/webui/settings/import_data_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/import_data_handler.cc), [to: chrome/browser/ui/webui/settings/import_data_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/import_data_handler.cc): FindBrowserWithTab + browser->GetWindow() thay browser->window().
- `file:chrome/browser/ui/webui/settings/password_manager_handler.cc` · [from: chrome/browser/ui/webui/settings/password_manager_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/password_manager_handler.cc), [to: chrome/browser/ui/webui/settings/password_manager_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/password_manager_handler.cc): FindBrowserWithTab → collection, biến thành BrowserWindowInterface.
- `file:chrome/browser/ui/webui/settings/settings_security_key_handler.cc` · [from: chrome/browser/ui/webui/settings/settings_security_key_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_security_key_handler.cc), [to: chrome/browser/ui/webui/settings/settings_security_key_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_security_key_handler.cc): FindBrowserWithTab trong ShowSettingsSubPage.
- `file:chrome/browser/ui/webui/settings/font_handler.cc` · [from: chrome/browser/ui/webui/settings/font_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/font_handler.cc), [to: chrome/browser/ui/webui/settings/font_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/font_handler.cc): Chỉ bỏ include browser_finder.h.
- `file:chrome/browser/ui/webui/settings/performance_settings_interactive_uitest.cc` · [from: chrome/browser/ui/webui/settings/performance_settings_interactive_uitest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/performance_settings_interactive_uitest.cc), [to: chrome/browser/ui/webui/settings/performance_settings_interactive_uitest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/performance_settings_interactive_uitest.cc): Bốn chỗ FindLastActive trong uitest → GetLastActiveBrowser.

## 38. Bốn thành phần Settings chuyển template từ Polymer .html sang Lit .html.ts (about page, reset page, settings-subpage)

Status: confirmed

Before: 148: about_page.html, reset_page.html, reset_profile_banner.html, reset_profile_dialog.html, settings_subpage.html là template Polymer có cả <style> bên trong; dùng on-click, dom-if, [[...]]/{{...}}, cr-lazy-render.

After: 151: năm file .html đó không còn (fetch đúng ref 151 trả upstream_404) và có năm file .html.ts xuất getHtml() trả lit html: @click, ${...}, ?hidden, .innerHTML, cr-lazy-render-lit, about_page import RestartType từ relaunch_mixin_lit. Style chuyển ra ngoài template.

Mechanism: Mười bốn finding webui_control ở đây mang signal declaration_moved với delta duy nhất là path (.html → .html.ts): cùng control, cùng id, cùng nhãn, chỉ khác file khai báo. Một khác biệt nhỏ ngoài khuôn khổ migration: id product-logo của about page đổi thành productLogo.

Impact: Không có thay đổi người dùng thấy. Với downstream: patch vào năm file .html này sẽ không áp được (file không còn), và mọi override CSS dựa trên <style> trong template phải chuyển sang file CSS tương ứng. Test UI chọn #product-logo phải đổi sang #productLogo.

Conditions: Windows; thuần mức build/khung WebUI.

Action: Chuyển mọi patch downstream trên năm file .html sang .html.ts và file CSS đi kèm; chạy lại test UI có selector cũ.

- `webui_control:settings/about_page/about_page/id:help` · [from: chrome/browser/resources/settings/about_page/about_page.html:130](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#130), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:91](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#91): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/id:privacyPolicy` · [from: chrome/browser/resources/settings/about_page/about_page.html:137](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#137), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:97](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#97): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/id:relaunch` · [from: chrome/browser/resources/settings/about_page/about_page.html:101](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#101), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:62](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#62): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/id:reportIssue` · [from: chrome/browser/resources/settings/about_page/about_page.html:134](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#134), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:94](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#94): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/label:aboutPageTitle` · [from: chrome/browser/resources/settings/about_page/about_page.html:48](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#48), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:14](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#14): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/label:managementPage` · [from: chrome/browser/resources/settings/about_page/about_page.html:141](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#141), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:101](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#101): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/about_page/about_page/settings-section#0` · [from: chrome/browser/resources/settings/about_page/about_page.html:147](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html#147), [to: chrome/browser/resources/settings/about_page/about_page.html.ts:107](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts#107): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_page/id:resetProfile` · [from: chrome/browser/resources/settings/reset_page/reset_page.html:4](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_page.html#4), [to: chrome/browser/resources/settings/reset_page/reset_page.html.ts:14](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_page.html.ts#14): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_page/label:resetPageTitle` · [from: chrome/browser/resources/settings/reset_page/reset_page.html:2](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_page.html#2), [to: chrome/browser/resources/settings/reset_page/reset_page.html.ts:12](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_page.html.ts#12): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_profile_banner/id:confirm` · [from: chrome/browser/resources/settings/reset_page/reset_profile_banner.html:55](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_banner.html#55), [to: chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts:29](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts#29): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_profile_dialog/id:cancel` · [from: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html:26](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html#26), [to: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts:26](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts#26): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_profile_dialog/id:reset` · [from: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html:30](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html#30), [to: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts:30](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts#30): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/reset_page/reset_profile_dialog/id:sendSettings` · [from: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html:36](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html#36), [to: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts:36](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts#36): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `webui_control:settings/settings_page/settings_subpage/id:closeButton` · [from: chrome/browser/resources/settings/settings_page/settings_subpage.html:82](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/settings_page/settings_subpage.html#82), [to: chrome/browser/resources/settings/settings_page/settings_subpage.html.ts:13](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/settings_page/settings_subpage.html.ts#13): Control được khai báo lại trong file .html.ts tương ứng (delta duy nhất là path).
- `file:chrome/browser/resources/settings/about_page/about_page.html` · [from: chrome/browser/resources/settings/about_page/about_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/about_page/about_page.html): Template Polymer không còn ở 151 (upstream_404).
- `file:chrome/browser/resources/settings/about_page/about_page.html.ts` · [to: chrome/browser/resources/settings/about_page/about_page.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/about_page/about_page.html.ts): Template Lit mới; đã đọc toàn bộ.
- `file:chrome/browser/resources/settings/reset_page/reset_page.html` · [from: chrome/browser/resources/settings/reset_page/reset_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_page.html): Không còn ở 151.
- `file:chrome/browser/resources/settings/reset_page/reset_page.html.ts` · [to: chrome/browser/resources/settings/reset_page/reset_page.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_page.html.ts): Template Lit mới; dùng cr-lazy-render-lit.
- `file:chrome/browser/resources/settings/reset_page/reset_profile_banner.html` · [from: chrome/browser/resources/settings/reset_page/reset_profile_banner.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_banner.html): Không còn ở 151.
- `file:chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts` · [to: chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_banner.html.ts): Template Lit mới; nội dung chỉ còn nhánh V2 (xem event:settings-reset-v2-graduation).
- `file:chrome/browser/resources/settings/reset_page/reset_profile_dialog.html` · [from: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html): Không còn ở 151.
- `file:chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts` · [to: chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/reset_page/reset_profile_dialog.html.ts): Template Lit mới.
- `file:chrome/browser/resources/settings/settings_page/settings_subpage.html` · [from: chrome/browser/resources/settings/settings_page/settings_subpage.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/settings_page/settings_subpage.html): Không còn ở 151.
- `file:chrome/browser/resources/settings/settings_page/settings_subpage.html.ts` · [to: chrome/browser/resources/settings/settings_page/settings_subpage.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/settings_page/settings_subpage.html.ts): Template Lit mới; style rời khỏi template.

## 39. extension-controlled-indicator đổi tên sự kiện thành disable-extension-click; system_page trước đó nghe sai tên

Status: confirmed

Before: 148: ba chỗ dùng ba tên listener khác nhau — appearance_page dùng on-disable-extension, search_page dùng on-disable-extension, còn system_page dùng on-extension-disable.

After: 151: cả ba chỗ dùng on-disable-extension-click và handler đổi tên thành onDisableExtensionClick_.

Mechanism: Sự kiện của thành phần dùng chung được đặt lại tên nhất quán. Việc system_page trước đó nghe on-extension-disable trong khi hai trang khác nghe on-disable-extension cho thấy ít nhất một trong hai tên không khớp sự kiện thành phần phát ra, nên nút "Disable extension" ở một trong các trang đó không có tác dụng trước 151.

Impact: Mọi template downstream nghe hai tên cũ sẽ im lặng không nhận sự kiện — Polymer không báo lỗi khi tên listener không tồn tại. Cần grep và đổi.

Conditions: Windows; áp dụng mọi nơi dùng extension-controlled-indicator.

Action: Grep downstream cho on-disable-extension và on-extension-disable; thử bấm "Disable extension" trên trang System, Appearance và Search để xác nhận có tác dụng.

Uncertainties: Chưa đọc extension_controlled_indicator.ts (ngoài phạm vi settings) nên chưa xác định tên sự kiện ở 148 là gì, tức chưa biết chắc trang nào bị hỏng trước đây.

- `file:chrome/browser/resources/settings/system_page/system_page.html` · [from: chrome/browser/resources/settings/system_page/system_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/system_page/system_page.html), [to: chrome/browser/resources/settings/system_page/system_page.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/system_page/system_page.html): Đã đọc mọi hunk: đổi on-extension-disable → on-disable-extension-click và thêm một đường kẻ ngang.

## 40. Bộ icon của Settings thêm 14 icon mới và bỏ hai icon (computer, center-focus-strong)

Status: confirmed

Before: 148: iconset settings20 có center-focus-strong và computer.

After: 151: hai id đó không còn (grep trong file ở đúng ref: 148 có 1, 151 có 0 mỗi id); thêm agent-mode2, apps, button-auto, e911-emergency, finance, insight-spark, lightbulb-tips, local-shipping, location-disabled, orders, person-text, personal-recommendations, screensaver-auto, stream-science.

Mechanism: Icon mới phục vụ các hàng/trang mới (AI suggestions, skills, shopping, glic experimental triggering, personal context). Hai icon bỏ đi không còn chỗ dùng nào trong chrome/browser/resources ở 151 (đã grep).

Impact: Template downstream còn dùng settings20:computer hoặc settings20:center-focus-strong sẽ không hiện icon nào — cr-icon không báo lỗi khi thiếu id, nên lỗi này im lặng.

Conditions: Windows; thuần tài nguyên.

Action: Grep downstream cho settings20:computer và settings20:center-focus-strong; nếu có, mang icon theo hoặc đổi icon.

- `file:chrome/browser/resources/settings/icons.html` · [from: chrome/browser/resources/settings/icons.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/settings/icons.html), [to: chrome/browser/resources/settings/icons.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/settings/icons.html): Đã đọc mọi hunk: 14 id thêm, 2 id bỏ.

## 41. URL trong trang Glic đổi nguồn: activity URL thành hằng C++, mọi learn-more đi qua glic::GetHelpCenterUrl

Status: confirmed

Before: 148: glicActivityButtonUrl là AddLocalizedString từ IDS_SETTINGS_GLIC_PERMISSIONS_ACTIVITY_BUTTON_URL (dịch theo locale); add_localized_url chỉ bọc GURL(url_string) bằng AppendGoogleLocaleParam. glicOsWidgetToggle chọn chuỗi theo kGlicShowStatusTrayIcon trên ChromeOS.

After: 151: glicActivityButtonUrl là AddString lấy chrome::kGlicActivityUrl; add_localized_url gọi glic::GetHelpCenterUrl(url_string) trước khi thêm locale; glicOsWidgetToggle dùng một chuỗi duy nhất, không còn nhánh ChromeOS, và cờ kGlicShowStatusTrayIcon bị xoá.

Mechanism: Chuyển từ chuỗi bản dịch sang hằng số trong code làm URL không còn phụ thuộc file dịch; GetHelpCenterUrl là một lớp gián tiếp mới cho toàn bộ learn-more của Glic (bao gồm URL mới glicExperimentalTriggeringLearnMoreUrl).

Impact: Downstream dịch hoặc thay URL activity qua file .grd sẽ không còn tác dụng — giá trị nay nằm trong chrome::kGlicActivityUrl. Các learn-more khác có thể bị GetHelpCenterUrl đổi host/đường dẫn; cần đọc hàm đó nếu sản phẩm trỏ sang help center riêng.

Conditions: Windows. Việc xoá kGlicShowStatusTrayIcon chỉ ảnh hưởng ChromeOS (cờ có BUILDFLAG(IS_CHROMEOS), not_compiled trên Windows) nhưng nó là lý do nhánh chuỗi biến mất.

Action: Nếu sản phẩm đổi URL help center của Glic, kiểm tra chrome::kGlicActivityUrl và glic::GetHelpCenterUrl thay vì chuỗi IDS_. Mở trang Glic và bấm từng learn-more để xem URL cuối.

Uncertainties: Chưa đọc glic::GetHelpCenterUrl (chrome/browser/glic/glic_settings_util.cc) nên chưa biết nó biến đổi URL thế nào.

- `webui_gate:settings_localized_strings_provider/glicActivityButtonUrl` · [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:980](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#980): glicActivityButtonUrl chuyển từ localized string sang AddString hằng C++.
- `base_feature:GlicShowStatusTrayIcon` · [from: chrome/common/chrome_features.cc:530](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/common/chrome_features.cc#530): Cờ ChromeOS bị xoá, kéo theo nhánh chuỗi glicOsWidgetToggle.
- [to: chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc:1000](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc#1000): add_localized_url gọi glic::GetHelpCenterUrl.

## 42. Đổi avatar profile đi qua GetSanitizedAvatarIndex thay vì dùng trực tiếp số từ WebUI

Status: confirmed

Before: 148: HandleSetProfileIconToAvatar lấy args[0].GetInt() rồi gọi profiles::SetDefaultProfileAvatarIndex(profile_, avatar_icon_index) — chỉ CHECK kiểu int, không kiểm tra miền giá trị.

After: 151: gọi profiles::SetDefaultProfileAvatarIndex(profile_, profiles::GetSanitizedAvatarIndex(args[0].GetInt())).

Mechanism: Giá trị đến từ tiến trình renderer nên upstream lọc nó trước khi ghi pref; include chrome/grit/generated_resources.h không còn cần.

Impact: Một chỉ số avatar ngoài miền không còn được ghi thẳng vào pref profile. Sản phẩm có bộ avatar riêng nên kiểm tra GetSanitizedAvatarIndex chấp nhận dải nào.

Conditions: Windows; không có cờ.

Action: Đọc profiles::GetSanitizedAvatarIndex nếu sản phẩm thêm avatar; thử đặt avatar và xem pref.

Uncertainties: Chưa đọc GetSanitizedAvatarIndex nên chưa biết nó kẹp giá trị hay trả mặc định.

- `file:chrome/browser/ui/webui/settings/settings_manage_profile_handler.cc` · [from: chrome/browser/ui/webui/settings/settings_manage_profile_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/settings_manage_profile_handler.cc), [to: chrome/browser/ui/webui/settings/settings_manage_profile_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_manage_profile_handler.cc): Đã đọc mọi hunk: thêm lớp lọc chỉ số avatar.

## 43. Mở danh sách công cụ tìm kiếm ghi hai histogram về heuristic search hijacking

Status: confirmed

Before: 148: handler không đọc SearchHijackingDetector và không ghi histogram nào khi trả danh sách.

After: 151: RecordSearchHijackingHeuristicMetric() (chạy một lần mỗi handler) đọc SearchHijackingDetector::GetRecentHeuristicResult(prefs, 7 ngày) và ghi Settings.SearchEngines.SearchHijackingDetector.HeuristicAvailable, rồi HeuristicMatch nếu có dữ liệu; được gọi từ cả getCategorizedTemplateUrls và getSearchEnginesList. Unittest thêm ba test cho ba trạng thái.

Mechanism: Heuristic đọc hai pref của extension telemetry (kExtensionTelemetrySearchHijackingLastCheckTime, kExtensionTelemetrySearchHijackingSignalData); chỉ ghi một lần để không đếm trùng khi UI gọi lại.

Impact: Thêm telemetry khi người dùng mở phần công cụ tìm kiếm. Không đổi UI. Sản phẩm quan tâm tới extension telemetry nên biết hai histogram mới này tồn tại.

Conditions: Windows; phụ thuộc dữ liệu do extension telemetry ghi.

Action: Nếu sản phẩm tắt extension telemetry, xác nhận histogram chỉ ghi HeuristicAvailable=false; chạy ba test mới nếu có patch vùng này.

- `file:chrome/browser/ui/webui/settings/search_engines_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/search_engines_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/search_engines_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/search_engines_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/search_engines_handler_unittest.cc): Đã đọc mọi hunk: ba test cho Unknown/NoMatch/Match.

## 44. Settings ghi nhận việc mời đăng nhập: message RecordSigninOffered mới và histogram Signin.SignIn.Offered

Status: confirmed

Before: 148: people_handler chỉ có RecordSigninPendingOffered; không có histogram cho lần mời đăng nhập thường.

After: 151: thêm message RecordSigninOffered nhận ChromeSigninAccessPoint, tự chọn PromoAction theo việc có tài khoản sẵn hay không, rồi gọi signin_metrics::LogSignInOffered. Unittest PeopleHandlerDiceTest.RecordSigninOffered cố định hai nhánh histogram; interactive uitest SignInOfferedLoggedOnMigration xác nhận việc mở /account tự bắn Signin.SignIn.Offered với AccessPoint kSettings.

Mechanism: WebUI gọi message khi dựng nút đăng nhập, nên histogram phản ánh số lần hiển thị lời mời chứ không phải số lần bấm.

Impact: Thêm dữ liệu telemetry từ Settings. Sản phẩm downstream tắt metrics không bị ảnh hưởng hành vi; nếu có WebUI riêng thì không tự có histogram này. Hai test Mac bị DISABLED trong cùng file (crbug.com/512594622, crbug.com/510237034) và uitest thêm mock Bluetooth adapter — là sửa hạ tầng test, không phải thay đổi sản phẩm.

Conditions: Windows; chỉ biên dịch với ENABLE_DICE_SUPPORT cho nhánh unittest.

Action: Nếu sản phẩm theo dõi histogram đăng nhập, đối chiếu định nghĩa mới; chạy hai test nếu có patch vùng people_handler.

- `file:chrome/browser/ui/webui/settings/people_handler_unittest.cc` · [from: chrome/browser/ui/webui/settings/people_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/people_handler_unittest.cc), [to: chrome/browser/ui/webui/settings/people_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/people_handler_unittest.cc): Đã đọc mọi hunk: test RecordSigninOffered và mock ShowCrossDeviceSigninQrBubble.
- `file:chrome/browser/ui/webui/settings/sync_settings_interactive_uitest.cc` · [from: chrome/browser/ui/webui/settings/sync_settings_interactive_uitest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/settings/sync_settings_interactive_uitest.cc), [to: chrome/browser/ui/webui/settings/sync_settings_interactive_uitest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/sync_settings_interactive_uitest.cc): Đã đọc mọi hunk: test mới cho histogram, hai test DISABLED trên Mac, mock Bluetooth adapter.

## 45. Cờ GlicAnchorEntryPointForOnboardedUsers mới, kèm test hồi quy Settings không crash khi Glic bị tắt

Status: confirmed

Before: 148: không có cờ kGlicAnchorEntryPointForOnboardedUsers.

After: 151: cờ mới trong chrome/browser/glic/public/features.cc, disabled theo source trên Windows. settings_ui_browsertest thêm SettingsUITestGlicDisabledButAnchored: bật cờ này, tắt kGlic, đặt kGlicCompletedFre = kCompleted, mở chrome://settings và yêu cầu không crash, đồng thời showGlicSettings phải false.

Mechanism: Cờ cho phép một entry point Glic với người đã onboard; test cố định rằng killswitch kGlic vẫn thắng và trang Settings không dựng section Glic.

Impact: Không đổi UI mặc định trên Windows (cờ tắt). Ý nghĩa với downstream: nếu sản phẩm tắt kGlic nhưng để cờ anchor bật, Settings phải vẫn mở được — đây là hồi quy đã từng xảy ra nên upstream thêm test.

Conditions: Windows; cờ disabled theo source. Chưa biết Finch.

Action: Nếu sản phẩm tắt Glic bằng kGlic, thử mở chrome://settings với profile đã completed FRE để xác nhận không crash và section Glic ẩn.

Uncertainties: Chưa chạy browsertest.

- `base_feature:GlicAnchorEntryPointForOnboardedUsers` · [to: chrome/browser/glic/public/features.cc:179](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/glic/public/features.cc#179): Cờ mới, disabled theo source trên Windows.
- [to: chrome/browser/ui/webui/settings/settings_ui_browsertest.cc:156](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/settings/settings_ui_browsertest.cc#156): Test hồi quy dùng cờ anchor cùng kGlic tắt.

