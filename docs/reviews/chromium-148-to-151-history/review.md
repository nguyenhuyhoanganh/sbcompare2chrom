# Chromium upgrade review

refs/tags/148.0.7778.217 → refs/tags/151.0.7922.138 · windows

Status: PARTIAL

Indexed items: 9437; events: 21; provisional events: 0.

Disposition counts: {"event": 82, "explained": 15, "out_of_scope": 14, "pending": 9326}

Accounting does not establish semantic completeness or product safety.

## Recorded item selection

History đầy đủ ba ưu tiên: thay đổi người dùng thấy, khả năng mới, thích nghi downstream; flags/Mojo/WebUI, tất cả source deltas trực tiếp và dependency cần thiết. Windows 148.0.7778.217 → 151.0.7922.138. Downloads/Bookmarks ngoài phạm vi. Shared files chỉ quyết định hunks liên quan, không claim toàn Chromium.

Selection accounting: COMPLETE
Selected items: 111; outside the selection: 9326.
Disposition counts: {"event": 82, "explained": 15, "out_of_scope": 14}

Only the explicitly selected items are counted. Selection and semantic completeness require review.

## Coverage and limits

This comparison reads declarations the extractor parses. It does not compare behaviour, and a file with no declaration parser is absent from the findings whether or not it changed.

Parsed file suffixes: features.cc, features.h, switches.cc, switches.h, feature_list.cc, feature_list.h, field_trial.cc, field_trial.h, fieldtrial.cc, fieldtrial.h, flags.cc, flags.h, _handler.cc, _util.cc, _manager.cc, pref_names.cc, pref_names.h, prefs.cc, prefs.h, .mojom, .idl, .json5, route.ts, routes.ts, .html, .html.ts, flag-metadata.json.

- from: 8024 of 8094 candidate declarations read; 70 missed.
- to: 8295 of 8366 candidate declarations read; 71 missed.
- Candidates missed by directory (to side): chrome/services 24; chrome/credential_provider 15; chrome/installer 12; third_party/blink 6; chrome/renderer 3; chrome/notification_helper 2; chrome/browser 1; chrome/common 1; and 4 more directories
- Acquisition: target set wide; partitions none; unconfirmed findings: 0.
- Unresolved declaration references: 295.
- Source scope: Only cached files, possibly beyond the original scan. A missing side is unknown, not an upstream addition/removal. Uncached code and symlinks are unexamined; .git and acquisition markers are excluded.
- Finch, external configuration, product patches and rendered UI require separate evidence.

These limits bound what the comparison could observe. They are the places a reviewer must check by hand.

## 1. VisitedLinksOn404 bật mặc định trên Windows

Status: confirmed

Before: 148: feature disabled mặc định; backend CHECK không nhận k404 khi gate tắt.

After: 151: feature enabled mặc định; History cho phép lưu visit 404 theo đường navigation đủ điều kiện và cập nhật visited links.

Mechanism: HistoryTabHelper vẫn kiểm tra ShouldUpdateHistory trước khi thêm visit; đánh dấu HTTP 4xx/5xx hidden, loại 404 khỏi Most Visited, và không phát callback on_updated_history_for_navigation cho k404. HistoryBackend gọi NotifyVisitedLinksAdded sau thêm visit và vẫn loại 404 khỏi VisitTracker.

Impact: Link dẫn đến trang trả 404 có thể mang trạng thái :visited; không suy ra mọi URL lỗi được lưu hoặc được đề xuất trong omnibox/Most Visited.

Conditions: Source default Windows; các điều kiện navigation, history eligibility và partitioning visited links vẫn áp dụng. Không kiểm chứng renderer/CSS và toàn bộ network error cases end-to-end.

Action: Test HTTP 404, redirect kết thúc 404, 200 sau 404, 500/network error và history eligibility; kiểm tra :visited cùng omnibox/Most Visited.

- `base_feature:VisitedLinksOn404` · [from: components/history/core/browser/features.cc:78](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/features.cc#78), [to: components/history/core/browser/features.cc:78](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/features.cc#78): features.cc:78 đổi disabled → enabled, comment xác định :visited cho HTTP 404; consumer History giữ xử lý đặc biệt 404.
- [from: components/history/core/browser/features.cc:73](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/features.cc#73): Default cũ.
- [to: components/history/core/browser/features.cc:73](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/features.cc#73): Default mới.
- [to: chrome/browser/history/history_tab_helper.cc:235](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/history/history_tab_helper.cc#235): HTTP error hidden.
- [to: chrome/browser/history/history_tab_helper.cc:321](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/history/history_tab_helper.cc#321): 404 không tăng Most Visited.
- [to: components/history/core/browser/history_backend.cc:1254](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/history_backend.cc#1254): VisitTracker filter và NotifyVisitedLinksAdded.
- [to: components/history/core/browser/history_backend.cc:1425](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/history_backend.cc#1425): CHECK 404 theo gate.

## 2. Bỏ công tắc Actor Integration M2, giữ tách actor visits và loại khỏi Most Visited

Status: confirmed

Before: 148: M2 bật mặc định trên Windows; helper trả M2 || M3, consumer dùng helper khi phân nhóm và chọn visit cho NTP.

After: 151: không còn công tắc M2; dedup dùng actor/non-actor map theo is_actor_visit và NTP loại visit có actor_task_id trực tiếp.

Mechanism: browsing_history_service.cc giữ hai map; history_tab_helper.cc giữ !actor_task_id.has_value() sau khi bỏ kiểm tra M2. Không kết luận mất actor history.

Impact: Patch gọi helper hoặc feature cũ cần cập nhật; disable-features tên M2 không khôi phục hành vi legacy.

Conditions: Đối chiếu Windows/non-iOS. M3 là gate riêng, vẫn disabled mặc định trên Windows.

Action: Cập nhật call sites và test M2; kiểm tra actor/user cùng URL cùng ngày vẫn tách, actor visits không tăng Most Visited.

- `base_feature:BrowsingHistoryActorIntegrationM2` · [from: components/history/core/browser/features.cc:142](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/features.cc#142): features.cc/h bỏ feature và IsBrowsingHistoryActorIntegrationM2Enabled().
- `flag_entry:browsing-history-actor-integration-M2` · [from: chrome/browser/flag-metadata.json:1306](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/flag-metadata.json#1306): Metadata entry cũ expiry=148 bị bỏ; about_flags.cc bỏ entry tương ứng.
- [to: components/history/core/browser/browsing_history_service.cc:612](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/browsing_history_service.cc#612): Dedup actor/user tách map không qua M2.
- [to: chrome/browser/history/history_tab_helper.cc:325](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/history/history_tab_helper.cc#325): NTP trực tiếp loại actor_task_id.

## 3. History handlers chuyển sang BrowserWindowInterface và GlobalBrowserCollection

Status: confirmed

Before: 148: browsing-history và embeddings handler dùng browser_finder/Browser* ở các call site.

After: 151: lấy BrowserWindowInterface qua GlobalBrowserCollection; Embeddings feedback dùng GetLastActiveBrowser. Search truyền thêm url_id_filter rỗng.

Mechanism: API C++ controller/browser và service signature thay đổi; factory/page remote là cùng migration đã ghi riêng. Empty URL-ID filter là argument ở call site, không chứng minh chất lượng search thay đổi.

Impact: Downstream C++ patch và mocks cần dùng abstraction/signature mới; chưa có build failure của sản phẩm để xác nhận.

Conditions: Đối chiếu Windows. Chưa đánh giá độc lập toàn bộ browser-window architecture hoặc thuật toán Embeddings backend.

Action: Compile call sites và tests; thử clear browsing data, bật history sync, embeddings search và gửi feedback với nhiều cửa sổ.

- `file:chrome/browser/ui/webui/history/browsing_history_handler.cc` · [from: chrome/browser/ui/webui/history/browsing_history_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/history/browsing_history_handler.cc), [to: chrome/browser/ui/webui/history/browsing_history_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/browsing_history_handler.cc): Toàn bộ diff chuyển Browser*/browser_finder sang BrowserWindowInterface/GlobalBrowserCollection ở ClearBrowsingData và TurnOnHistorySync; include paths tương ứng.
- `file:chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc` · [from: chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc), [to: chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc): Đã đọc toàn bộ diff: factory/page remote (event factories), BrowserWindowInterface cho feedback, include navigator mới, Search thêm url_id_filter={}.
- [to: chrome/browser/ui/webui/history/browsing_history_handler.cc:540](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/browsing_history_handler.cc#540): Call sites dùng browser window interface.
- [to: chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc:91](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc#91): Search và handler target.
- [to: chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc:257](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/cr_components/history_embeddings/history_embeddings_handler.cc#257): Feedback uses GlobalBrowserCollection/GetLastActiveBrowser.

## 4. Thêm promo đăng nhập Chrome trên điện thoại vào History

Status: confirmed

Before: 148: chưa có card và HistoryCrossDeviceSigninPromoHandler này.

After: 151: card hỏi ShouldShowPromoCard; khi hiện/bỏ qua gửi metric-state; nút action mở QR bubble và ẩn sau callback. CrossDeviceSigninFromDesktop mới, disabled Windows; flag expiry M154.

Mechanism: C++ delegate về promo manager entry HistoryPage. Gate: feature bật, signed-in hoặc syncing không error, history selectable type bật, không có thiết bị OTHER dạng phone; chặn sau 5 lần hiện, cooldown 7 ngày sau dismiss và chỉ một lần hiện lại sau dismiss. Prefs lưu dưới Gaia account/CrossDevicePromoPrefs/history.

Impact: Thêm nội dung vào History khi đủ điều kiện, cần port resources/bindings và branding. Thiết bị tablet hoặc phone không có trong DeviceInfo không tương đương điều kiện có phone.

Conditions: Handler compile dưới ENABLE_DICE_SUPPORT; template không ChromeOS. Tình trạng đăng nhập, sync và device tracker vẫn quyết định visibility; default disabled không chứng minh rollout.

Action: Test gate matrix, shown count/cooldown theo account, dismiss, action đang pending và callback. OnPromoCardActionClicked thực tế có response => (); mock phải resolve promise.

- `base_feature:CrossDeviceSigninFromDesktop` · [to: components/signin/public/base/signin_switches.cc:281](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/signin/public/base/signin_switches.cc#281): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `flag_entry:cross-device-signin-from-desktop` · [to: chrome/browser/flag-metadata.json:2197](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/flag-metadata.json#2197): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `mojo_interface:history_cross_device_signin_promo.mojom.HistoryCrossDeviceSigninPromoHandler` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:8](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#8): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `mojo_method:history_cross_device_signin_promo.mojom.HistoryCrossDeviceSigninPromoHandler.ShouldShowPromoCard` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:10](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#10): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `mojo_method:history_cross_device_signin_promo.mojom.HistoryCrossDeviceSigninPromoHandler.OnPromoCardShown` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:13](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#13): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `mojo_method:history_cross_device_signin_promo.mojom.HistoryCrossDeviceSigninPromoHandler.OnPromoCardDismissed` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:16](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#16): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `mojo_method:history_cross_device_signin_promo.mojom.HistoryCrossDeviceSigninPromoHandler.OnPromoCardActionClicked` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:20](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#20): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `webui_control:history/history_cross_device_signin_promo/history_cross_device_signin_promo/id:actionButton` · [to: chrome/browser/resources/history/history_cross_device_signin_promo.html.ts:29](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_cross_device_signin_promo.html.ts#29): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `webui_control:history/history_cross_device_signin_promo/history_cross_device_signin_promo/id:close` · [to: chrome/browser/resources/history/history_cross_device_signin_promo.html.ts:12](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_cross_device_signin_promo.html.ts#12): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `file:chrome/browser/resources/history/history_cross_device_signin_promo.html.ts` · [to: chrome/browser/resources/history/history_cross_device_signin_promo.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_cross_device_signin_promo.html.ts): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `file:chrome/browser/ui/webui/history/history_cross_device_signin_promo_handler.cc` · [to: chrome/browser/ui/webui/history/history_cross_device_signin_promo_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/history_cross_device_signin_promo_handler.cc): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `file:ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom` · [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- `file:chrome/browser/signin/cross_device_signin_promo_manager.cc` · [to: chrome/browser/signin/cross_device_signin_promo_manager.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/signin/cross_device_signin_promo_manager.cc): Thành phần cùng luồng promo History: điều kiện hiển thị, shown/dismiss/action, hoặc UI card. File mới đã xác nhận exact-ref 148 không tồn tại.
- [to: chrome/browser/signin/cross_device_signin_promo_manager.cc:40](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/signin/cross_device_signin_promo_manager.cc#40): Điều kiện và prefs promo.
- [to: chrome/browser/resources/history/history_cross_device_signin_promo.ts:40](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_cross_device_signin_promo.ts#40): Frontend lifecycle và action callback.
- [to: ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/history_cross_device_signin_promo.mojom#1): Chữ ký thực có response cho action.
- `pref:CrossDevicePromoPrefs` · [to: components/signin/public/base/signin_prefs.cc:59](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/signin/public/base/signin_prefs.cc#59): Pref dictionary mới được History promo manager đọc/ghi dưới Gaia account và history entry point.
- [to: components/signin/public/base/signin_prefs.cc:610](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/signin/public/base/signin_prefs.cc#610): GetOrCreateCrossDevicePromoPrefs đặt dưới account dictionary.

## 5. Luồng promo có WebUI QR và Mojo lấy dữ liệu tài khoản

Status: confirmed

Before: 148: chưa có contract và WebUI QR bubble ở các path này (exact-ref 404).

After: 151: factory tạo PageHandler; GetRegistrationData trả nullable struct gồm full_name, email, qr_code_data_uri. Frontend gán dữ liệu vào template khi response không null.

Mechanism: UIConfig bị gate CrossDeviceSigninFromDesktop. Backend lấy primary account kSignin, escape email vào URL FeatureParam, tạo QR PNG data URI với avatar hoặc product logo. Default URL: https://www.google.com/chrome/go-mobile?entry_point_id=1&email=$1.

Impact: Downstream phải kiểm tra endpoint và branding của luồng mới, regenerate Mojo và xử lý response null. QR chứa URL có email theo default; code đọc không chứng minh chỉ mở bubble đã gửi request đến URL đó.

Conditions: Mojo interface EnableIf desktop Windows/macOS/Linux. Không có account/IdentityManager => null; QR generation thất bại có thể trả struct với URI rỗng. URL param có thể bị cấu hình thay đổi.

Action: Test không account, account thiếu tên/avatar, ký tự đặc biệt trong email, tạo QR thất bại và URL override; kiểm tra luồng quét QR trên thiết bị thật.

- `mojo_field:cross_device_signin.mojom.CrossDeviceSigninQrBubbleData.email` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:9](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#9): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_field:cross_device_signin.mojom.CrossDeviceSigninQrBubbleData.full_name` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:8](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#8): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_field:cross_device_signin.mojom.CrossDeviceSigninQrBubbleData.qr_code_data_uri` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:13](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#13): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_interface:cross_device_signin.mojom.PageHandler` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:28](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#28): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_interface:cross_device_signin.mojom.PageHandlerFactory` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:19](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#19): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_method:cross_device_signin.mojom.PageHandler.GetRegistrationData` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:33](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#33): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_method:cross_device_signin.mojom.PageHandlerFactory.CreateCrossDeviceSigninQrBubbleHandler` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:22](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#22): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `mojo_struct:cross_device_signin.mojom.CrossDeviceSigninQrBubbleData` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom:7](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom#7): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `feature_param:CrossDeviceSigninFromDesktop/url` · [to: components/signin/public/base/signin_switches.cc:282](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/signin/public/base/signin_switches.cc#282): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `file:chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.mojom): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `file:chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble_ui.cc` · [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble_ui.cc): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `file:chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.html` · [to: chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble.html): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- `file:chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble_app.html.ts` · [to: chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble_app.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble_app.html.ts): Nằm trên đường action từ History promo sang QR bubble; field, factory, handler hoặc URL param được consumer đọc trực tiếp.
- [to: chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble_ui.cc:42](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/signin/cross_device_signin_qr_bubble_ui.cc#42): Gate và reader của URL param, dữ liệu QR.
- [to: chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble_app.ts:44](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/signin/cross_device_signin_qr_bubble/cross_device_signin_qr_bubble_app.ts#44): Factory và nullable response handling.

## 6. Giải nén passage của History Embeddings kiểm tra thêm RAM còn trống

Status: confirmed

Before: 148: chỉ từ chối gzip có kích thước giải nén vượt 16 MiB.

After: 151: trên Windows còn từ chối nếu kích thước vượt RAM vật lý khả dụng, trả nullopt trước GzipUncompress.

Mechanism: PassagesBlobToProto đọc kích thước footer sau giải mã và so với min giới hạn cứng/RAM; Fuchsia giữ giới hạn cứng.

Impact: Đọc passage có thể không trả dữ liệu khi máy thiếu RAM. Đây là cơ chế phòng cấp phát lớn; không phải bảo đảm loại hết OOM.

Conditions: Chỉ khi đọc blob passages History Embeddings; không có thay đổi default HistoryEmbeddings từ file này.

Action: Kiểm tra đường đọc passage lỗi/nullopt và search dưới áp lực bộ nhớ; không coi nullopt là bằng chứng toàn bộ History bị mất.

- `file:components/history_embeddings/core/passages_util.cc` · [from: components/history_embeddings/core/passages_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history_embeddings/core/passages_util.cc), [to: components/history_embeddings/core/passages_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history_embeddings/core/passages_util.cc): Đã đọc cả hai hunk: include SysInfo/safe_conversions và giới hạn min(16MB, available_size).
- [to: components/history_embeddings/core/passages_util.cc:47](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history_embeddings/core/passages_util.cc#47): Điều kiện và kết quả trả về trong hàm giải mã/giải nén.

## 7. Bộ lọc lịch sử người dùng/AI chuyển trực tiếp giữa hai nguồn và thêm trợ năng

Status: confirmed

Before: 148: khi đang chỉ chọn actor rồi bấm user (hoặc ngược lại), handler đưa về cả hai nguồn; chip chỉ có check khi được chọn.

After: 151: click user luôn giữ user=true và đảo actor; click actor đối xứng. Có thể chuyển trực tiếp actor-only ↔ user-only; thêm icon người dùng/actor và tên nhóm cho trợ năng.

Mechanism: history_filter_chips.ts đổi hai handler; template dùng getUserVisitsIcon_/getActorVisitsIcon_. App chỉ hiện chip khi M3 bật, có web actuation và không ở grouped view.

Impact: Tương tác khác khi switch nguồn; cần cập nhật test và snapshot downstream. Không mặc định hiện trên mọi Windows profile.

Conditions: M3 Windows vẫn tắt mặc định. Icon actor nội bộ chỉ có ở _google_chrome; Chromium thường trả icon rỗng khi chưa chọn. Glic consent và actuation còn phải hợp lệ.

Action: Test cả ba trạng thái both/user-only/actor-only, click chéo nguồn, query gửi include_user_visits/include_actor_visits và accessibility group.

- `file:chrome/browser/resources/history/history_filter_chips.html.ts` · [from: chrome/browser/resources/history/history_filter_chips.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/history/history_filter_chips.html.ts), [to: chrome/browser/resources/history/history_filter_chips.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_filter_chips.html.ts): Thêm role=group/aria-label, icon động ở cả hai chip; đã đọc toàn bộ diff.
- `file:chrome/browser/ui/webui/cr_components/history/history_util.cc` · [from: chrome/browser/ui/webui/cr_components/history/history_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/cr_components/history/history_util.cc), [to: chrome/browser/ui/webui/cr_components/history/history_util.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/cr_components/history/history_util.cc): Thêm sourceFilterChipsAriaLabel nối template với localized string; không có hunk khác.
- [to: chrome/browser/resources/history/history_filter_chips.ts:36](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_filter_chips.ts#36): Logic toggle, metric và icon target.
- [to: chrome/browser/resources/history/app.ts:950](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/app.ts#950): Gate hiển thị filter gồm M3 và actuation.

## 8. Click tab từ side panel mở tab mới và ghi metrics trước thao tác điều hướng

Status: confirmed

Before: 148: click không modifier dùng CURRENT_TAB; chưa có các recorder riêng của panel này.

After: 151: riêng side panel đổi CURRENT_TAB thành NEW_FOREGROUND_TAB; middle-click vẫn background. Metrics liên quan tab/device/recency được ghi trước restore vì restore có thể huỷ handler đồng bộ.

Mechanism: ForeignSessionHandler kiểm tra side_panel_ui_; OpenForeignSessionAllTabs có CHECK không ở side panel. Tên session trùng nhau trong panel thêm suffix kênh Canary/Dev/Beta/developer build từ DeviceInfo; Stable không có suffix.

Impact: Click tab ở panel giữ trang đang xem và mở tab mới. Main History giữ semantics CURRENT_TAB. Tests/fake cần cập nhật API và lifetime.

Conditions: Chỉ các nhánh side_panel_ui_; metric không chứng minh giảm crash hay cải thiện hiệu năng.

Action: Test left/middle/Ctrl/Shift click, incognito behavior ở main History, handler bị huỷ trong restore, và thiết bị trùng tên/thiếu DeviceInfo.

- `file:chrome/browser/ui/webui/history/foreign_session_handler.cc` · [from: chrome/browser/ui/webui/history/foreign_session_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/history/foreign_session_handler.cc), [to: chrome/browser/ui/webui/history/foreign_session_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc): Đã đọc tất cả hunks: factory constructor, timestamp, ShowUi, stable filter/name suffix, click disposition và metrics. Các phần khác đối chiếu các event sidepanel/factory.
- `file:chrome/browser/ui/webui/history/foreign_session_handler_unittest.cc` · [from: chrome/browser/ui/webui/history/foreign_session_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/history/foreign_session_handler_unittest.cc), [to: chrome/browser/ui/webui/history/foreign_session_handler_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler_unittest.cc): Đã đọc tất cả 615 dòng diff: FakeOpenTabsUIDelegate thay Mock, constructor page remote, bỏ SetPageShowsUi, left/middle click, destroy synchronously, metrics count/device/recency, duplicate names, exclude Stable.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:250](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#250): Disposition, CHECK và metric trước restore.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:125](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#125): Suffix/filter helpers.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:403](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#403): Tên trùng trong panel.

## 9. History đọc trạng thái web actuation qua Glic service

Status: confirmed

Before: 148: isGlicWebActuationAvailable = IsEnabledAndConsentForProfile(profile) AND pref kGlicUserEnabledActuationOnWeb.

After: 151: còn cần GlicKeyedService tồn tại; dùng service.enabling().GetUserEnabledActuationOnWeb(). Helper trả true nếu GlicExperimentalTriggeringOptInBypass bật, ngược lại đọc cùng pref.

Mechanism: Gate bên ngoài IsEnabledAndConsentForProfile vẫn giữ ở cả hai ref. Experimental opt-in bypass chỉ thay điều kiện user-actuation của helper; không bỏ gate enable/consent bên ngoài hoặc M3.

Impact: Patch/fake service và test filter AI cần service hợp lệ. Bypass có thể làm helper trả true dù pref=false, nhưng gate IsEnabledAndConsentForProfile vẫn phải pass.

Conditions: Bypass mới disabled Windows; M3 riêng vẫn disabled Windows. Chưa kiểm chứng config sản phẩm hoặc rollout Glic.

Action: Test service null, consent off/on, pref off/on và bypass off/on; kiểm tra sự xuất hiện source chips đúng các gate.

- `base_feature:GlicExperimentalTriggeringOptInBypass` · [to: chrome/common/chrome_features.cc:218](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/common/chrome_features.cc#218): Feature mới disabled mặc định được GetUserEnabledActuationOnWeb đọc; HistoryUI hiện gọi helper thay đọc pref trực tiếp.
- [to: chrome/browser/glic/public/glic_enabling.cc:1223](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/glic/public/glic_enabling.cc#1223): Helper và bypass chính xác.
- [from: chrome/browser/ui/webui/history/history_ui.cc:145](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/history/history_ui.cc#145): Gate cũ đọc pref.
- [to: chrome/browser/ui/webui/history/history_ui.cc:145](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/history_ui.cc#145): Gate mới qua service.

## 10. Help bubble của History chuyển tracking element sang document singleton

Status: confirmed

Before: 148: HelpBubbleHandler nhận thêm binding tracked-element qua BindTrackedElementHandler; frontend dùng HelpBubbleProxyImpl.

After: 151: HistoryUI đăng ký kHistorySearchInputElementId với document singleton; HelpBubbleHandler dùng GetOrCreate cho render frame. Frontend mixin dùng TrackedElementManager và browserProxyFactory.

Mechanism: Tracking được dùng chung theo document; mixin unregister khi disconnect, options đổi anchorPadding… sang padding… và không tự giữ bộ observer cũ.

Impact: Patch IPH/tutorial hoặc mock HelpBubbleProxy cần cập nhật; neo bubble trên ô search cần được kiểm tra khi scroll, resize và thay route.

Conditions: History desktop; không kết luận mọi consumer HelpBubble ngoài History đã tương thích. Hunk tạo handler PDF nằm ngoài phạm vi.

Action: Port binding singleton và test mocks; kiểm tra bubble position/visibility, focus, anchor biến mất và cleanup.

- `mojo_method:help_bubble.mojom.HelpBubbleHandler.BindTrackedElementHandler` · [from: ui/webui/resources/cr_components/help_bubble/help_bubble.mojom:132](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/help_bubble/help_bubble.mojom#132): Method bị bỏ khỏi mojom; HistoryUI chuyển sang TrackedElementHandlerDocumentSingleton.
- [to: ui/webui/resources/cr_components/help_bubble/help_bubble_mixin_lit.ts:154](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/help_bubble/help_bubble_mixin_lit.ts#154): Đăng ký/huỷ tracking qua manager.
- [to: chrome/browser/ui/webui/history/history_ui.cc:240](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/history_ui.cc#240): Đăng ký document singleton ở HistoryUI.

## 11. Bỏ flag HistoryQueryOnlyLocalFirst, giữ truy vấn local trước remote

Status: confirmed

Before: 148: local-first bật mặc định nhưng còn nhánh cấu hình tắt flag.

After: 151: chỉ truy vấn remote sau khi hết khả năng lấy thêm local và tổng kết quả chưa đủ; giới hạn remote bằng số kết quả còn thiếu.

Mechanism: ShouldQueryRemote, QueryHistory và QueryComplete giữ nhánh trước đây nằm sau flag. Loại bỏ flag không loại bỏ khả năng truy vấn remote.

Impact: Default thông thường được giữ; downstream từng tắt flag không còn chọn được thuật toán cũ bằng cấu hình đó.

Conditions: Vẫn phụ thuộc WebHistoryService, điều kiện query và dữ liệu local/remote; app-specific query vẫn có điều kiện riêng.

Action: Bỏ cấu hình/patch nhắc kHistoryQueryOnlyLocalFirst; kiểm tra phân trang local hết, remote bổ sung, số lượng kết quả và lỗi remote.

- `base_feature:HistoryQueryOnlyLocalFirst` · [from: components/history/core/browser/features.cc:160](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/features.cc#160): Khai báo và header bị bỏ; browsing_history_service.cc bỏ nhánh legacy và giữ logic local-first.
- [from: components/history/core/browser/browsing_history_service.cc:510](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/browsing_history_service.cc#510): ShouldQueryRemote cũ có hai nhánh.
- [to: components/history/core/browser/browsing_history_service.cc:510](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/browsing_history_service.cc#510): Local-first được giữ sau bỏ gate.

## 12. Menu thao tác History tự đóng khi focus rời menu

Status: confirmed

Before: 148: các menu không bật xử lý focusout này.

After: 151: History list, cluster và visit menu opt-in auto-close-on-focusout.

Mechanism: cr_action_menu.ts bổ sung property mặc định false và focusout listener: khi relatedTarget ngoài menu thì close(). Ba template History bật property.

Impact: Điều hướng bàn phím hoặc chuyển focus ra ngoài sẽ đóng menu; patch menu cần giữ hành vi này.

Conditions: Áp dụng khi menu tương ứng được render; không có feature flag mới riêng cho thay đổi này.

Action: Kiểm tra Tab/Shift+Tab, chọn hành động và focus trả về anchor; focus di chuyển bên trong menu không được đóng sớm.

- `file:chrome/browser/resources/history/history_list.html.ts` · [from: chrome/browser/resources/history/history_list.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/history/history_list.html.ts), [to: chrome/browser/resources/history/history_list.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history_list.html.ts): Thêm auto-close-on-focusout cho sharedMenu; toàn bộ hunk đã đọc.
- `file:ui/webui/resources/cr_components/history_clusters/cluster_menu.html.ts` · [from: ui/webui/resources/cr_components/history_clusters/cluster_menu.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_clusters/cluster_menu.html.ts), [to: ui/webui/resources/cr_components/history_clusters/cluster_menu.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_clusters/cluster_menu.html.ts): Thêm cùng thuộc tính ở menu cluster; phần còn lại chỉ format template.
- `file:ui/webui/resources/cr_components/history_clusters/url_visit.html.ts` · [from: ui/webui/resources/cr_components/history_clusters/url_visit.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_clusters/url_visit.html.ts), [to: ui/webui/resources/cr_components/history_clusters/url_visit.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_clusters/url_visit.html.ts): Thêm cùng thuộc tính ở menu của visit.
- [to: ui/webui/resources/cr_elements/cr_action_menu/cr_action_menu.ts:198](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_elements/cr_action_menu/cr_action_menu.ts#198): Listener và điều kiện tự đóng.

## 13. Foreign Sessions, Clusters và Embeddings chuyển sang tạo handler qua factory

Status: confirmed

Before: 148: frontend lấy PageHandler rồi gọi SetPage để gắn callback remote.

After: 151: factory nhận cả page remote và handler receiver trong Create…; ba SetPage tương ứng bị bỏ.

Mechanism: Controller BindInterface bind/reset factory receiver; Create… khởi tạo handler với page remote ngay từ constructor. Frontend dùng browserProxyFactory sinh từ mojom; các proxy viết tay Clusters/Embeddings bị bỏ. Clusters còn chuyển WebContents* thành raw_ptr và sửa comment, không tạo capability riêng.

Impact: Downstream cần port đồng bộ mojom, C++ constructor/binder, TS imports và fake/test. Ghép UI 148 với binding 151 không còn đáp ứng API cũ; chưa chạy build để kết luận lỗi cụ thể của sản phẩm.

Conditions: Áp dụng cho ba interface này trên History và side panel có dùng chúng. PageHandler của History chính vẫn dùng setPage; chrome.send cho history query vẫn còn.

Action: Regenerate bindings; test initial load, callbacks, reload/rebind, disconnect và side panel close/reopen. Không thay toàn bộ History.setPage bằng factory một cách máy móc.

- `mojo_interface:history.mojom.ForeignSessionPageHandlerFactory` · [to: ui/webui/resources/cr_components/history/foreign_sessions.mojom:37](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/foreign_sessions.mojom#37): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history.mojom.ForeignSessionPageHandlerFactory.CreateForeignSessionPageHandler` · [to: ui/webui/resources/cr_components/history/foreign_sessions.mojom:39](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/foreign_sessions.mojom#39): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history.mojom.ForeignSessionPageHandler.SetPage` · [from: ui/webui/resources/cr_components/history/foreign_sessions.mojom:38](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history/foreign_sessions.mojom#38): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_interface:history_clusters.mojom.PageHandlerFactory` · [to: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom:160](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom#160): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history_clusters.mojom.PageHandlerFactory.CreatePageHandler` · [to: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom:162](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom#162): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history_clusters.mojom.PageHandler.SetPage` · [from: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom:70](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom#70): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_interface:history_embeddings.mojom.PageHandlerFactory` · [to: ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom:97](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom#97): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history_embeddings.mojom.PageHandlerFactory.CreatePageHandler` · [to: ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom:99](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom#99): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `mojo_method:history_embeddings.mojom.PageHandler.SetPage` · [from: ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom:100](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom#100): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `file:ui/webui/resources/cr_components/history_clusters/history_clusters.mojom` · [from: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom), [to: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `file:ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom` · [from: ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom), [to: ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history_embeddings/history_embeddings.mojom): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `file:chrome/browser/ui/webui/history_clusters/history_clusters_handler.cc` · [from: chrome/browser/ui/webui/history_clusters/history_clusters_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/history_clusters/history_clusters_handler.cc), [to: chrome/browser/ui/webui/history_clusters/history_clusters_handler.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history_clusters/history_clusters_handler.cc): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `file:chrome/browser/ui/webui/side_panel/history/history_side_panel_ui.cc` · [from: chrome/browser/ui/webui/side_panel/history/history_side_panel_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/side_panel/history/history_side_panel_ui.cc), [to: chrome/browser/ui/webui/side_panel/history/history_side_panel_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/history/history_side_panel_ui.cc): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- `file:chrome/browser/ui/webui/side_panel/history_clusters/history_clusters_side_panel_ui.cc` · [from: chrome/browser/ui/webui/side_panel/history_clusters/history_clusters_side_panel_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/ui/webui/side_panel/history_clusters/history_clusters_side_panel_ui.cc), [to: chrome/browser/ui/webui/side_panel/history_clusters/history_clusters_side_panel_ui.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/history_clusters/history_clusters_side_panel_ui.cc): Hợp đồng factory mới nhận page remote và handler receiver; thay SetPage và cập nhật constructor/controller tương ứng. Các file trực tiếp đã đọc toàn bộ diff.
- [to: chrome/browser/ui/webui/history/history_ui.cc:270](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/history_ui.cc#270): BindInterface và các Create handler target.
- [to: chrome/browser/resources/history/browser_proxy.ts:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/browser_proxy.ts#1): Proxy mới vẫn giữ API History chính.
- [from: ui/webui/resources/cr_components/history_clusters/history_clusters.mojom:60](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/ui/webui/resources/cr_components/history_clusters/history_clusters.mojom#60): Hợp đồng trước nâng cấp.

## 14. Bật mặc định việc tạo lại History database quá cũ để migrate

Status: confirmed

Before: 148: RazeOldHistoryDatabase tắt mặc định; database dưới schema tối thiểu không đi vào db_.Raze() qua gate này.

After: 151: bật mặc định; nếu database có meta table và version < 15 (gồm 0 khi đọc version thất bại), RazeDbIfTooOld gọi db_.Raze() trước khi tạo bảng.

Mechanism: Đổi default kích hoạt một nhánh xử lý đã có; đây là schema version, không phải tuổi của từng visit. Thiếu meta table vẫn return true, không raze ở nhánh này.

Impact: Profile có database schema quá cũ sẽ mất nội dung database History khi được khởi tạo lại. Database schema hỗ trợ migration không bị điều kiện này chọn.

Conditions: Windows; database đã tồn tại, có meta table, version < kMinimalVersionNumber=15, feature thực tế bật; không suy ra Finch hoặc profile downstream.

Action: Kiểm tra profile nâng cấp rất cũ và đường migration thông thường; xác nhận override RazeOldHistoryDatabase và dữ liệu phải bảo toàn trong sản phẩm.

- `base_feature:RazeOldHistoryDatabase` · [from: components/history/core/browser/features.cc:114](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/features.cc#114), [to: components/history/core/browser/features.cc:114](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/features.cc#114): features.cc:114–115: Windows disabled → enabled; consumer RazeDbIfTooOld vẫn tồn tại ở cả hai ref.
- [from: components/history/core/browser/history_database.cc:100](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/history/core/browser/history_database.cc#100): Nhánh raze cũ bị gate và quy trình Init.
- [to: components/history/core/browser/history_database.cc:100](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/history_database.cc#100): Điều kiện version, Raze và tái tạo bảng ở target.
- [to: components/history/core/browser/history_database.cc:39](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/history/core/browser/history_database.cc#39): Schema constants: current 70, minimum 15.

## 15. History bổ sung giao diện WebUI Refresh 2026 và icon bo tròn

Status: confirmed

Before: 148: không có các gate/attribute Refresh 2026 và RoundedIcons này.

After: 151: html History nhận webuiRefresh2026 và roundedIconsAttribute; History Clusters side panel nhận roundedIconsAttribute. Ba feature mới đều disabled mặc định Windows.

Mechanism: IsWebuiRefresh2026Enabled = DesktopGlowUp OR WebuiRefresh2026; IsRoundedIconsEnabled = DesktopGlowUp OR RoundedIcons. App tải colors.css?sets=ui,chrome và ColorChangeUpdater khi refresh; CSS đổi separator/text/bookmark-star/card-title, nền dùng color-webui-page-background.

Impact: Downstream theme, icon override và snapshot cần xét cả gate cha; tắt riêng WebuiRefresh2026 không đủ nếu DesktopGlowUp bật. Metadata expiry cả ba flag là M160, không chứng minh ngày phát hành hoặc chắc chắn bị xoá ở M160.

Conditions: Source defaults disabled; Finch/command-line/build sản phẩm chưa cung cấp. Không suy ra UI mới bật cho toàn bộ Windows.

Action: Kiểm tra light/dark/custom theme, contrast, selected sidebar, separators và tổ hợp DesktopGlowUp/Refresh/RoundedIcons; cập nhật resource map, CSS và color tokens.

- `base_feature:DesktopGlowUp` · [to: ui/base/ui_base_features.cc:505](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/base/ui_base_features.cc#505): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `base_feature:WebuiRefresh2026` · [to: chrome/browser/ui/ui_features.cc:69](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/ui_features.cc#69): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `base_feature:RoundedIcons` · [to: ui/base/ui_base_features.cc:507](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/base/ui_base_features.cc#507): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `flag_entry:desktop-glow-up` · [to: chrome/browser/flag-metadata.json:2479](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/flag-metadata.json#2479): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `flag_entry:webui-refresh-2026` · [to: chrome/browser/flag-metadata.json:10117](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/flag-metadata.json#10117): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `flag_entry:rounded-icons` · [to: chrome/browser/flag-metadata.json:8506](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/flag-metadata.json#8506): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `webui_gate:history_ui/webuiRefresh2026` · [to: chrome/browser/ui/webui/history/history_ui.cc:230](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/history_ui.cc#230): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `file:chrome/browser/resources/history/history.html` · [from: chrome/browser/resources/history/history.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/history/history.html), [to: chrome/browser/resources/history/history.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/history.html): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- `file:chrome/browser/resources/side_panel/history_clusters/history_clusters.html` · [from: chrome/browser/resources/side_panel/history_clusters/history_clusters.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/side_panel/history_clusters/history_clusters.html), [to: chrome/browser/resources/side_panel/history_clusters/history_clusters.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/history_clusters/history_clusters.html): Declaration/gate hoặc template nối trực tiếp History với Refresh/RoundedIcons; DesktopGlowUp là gate cha OR cho cả hai.
- [to: ui/base/ui_base_features.cc:500](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/base/ui_base_features.cc#500): Feature cha và helper RoundedIcons.
- [to: chrome/browser/ui/ui_features.cc:65](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/ui_features.cc#65): Refresh feature và helper OR.
- [to: chrome/browser/resources/history/shared_vars.css:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/history/shared_vars.css#1): CSS variables được đổi theo attribute.

## 16. Tên thiết bị trong History có thể dùng tên hiển thị từ DeviceInfo

Status: confirmed

Before: 148: tracker dùng tên session từ header specifics, chưa có override này.

After: 151: khi SyncSessionsUsePreferredDisplayName bật, tracker gọi GetSessionDisplayNameFromDeviceInfo(session_tag); nếu có optional string thì SetSessionName, nếu nullopt giữ tên đã populate.

Mechanism: ForeignSessionHandler đọc GetSessionName cho cả main History và side panel. Vì vậy đổi tên ở tracker được đưa tới UI; suffix kênh cho tên trùng trong side panel là bước riêng.

Impact: Tên thiết bị có thể khác khi bật feature, cần tránh dùng display name làm identifier và cập nhật snapshot. Session tag vẫn là key ở consumer đã đọc.

Conditions: Disabled mặc định Windows; phụ thuộc tên mà SyncSessionsClient trả về và thời điểm update header. Chưa xác minh mọi nguồn/rollout của preferred name phía server.

Action: Test feature on/off, tên có/không có, thay đổi DeviceInfo và thiết bị trùng tên; giữ lựa chọn theo session tag.

- `base_feature:SyncSessionsUsePreferredDisplayName` · [to: components/sync_sessions/features.cc:17](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/sync_sessions/features.cc#17): Feature mới disabled; SyncedSessionTracker áp dụng ngay sau PopulateSyncedSessionFromSpecifics.
- [from: components/sync_sessions/synced_session_tracker.cc:738](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/components/sync_sessions/synced_session_tracker.cc#738): Tracker cũ populate header không override.
- [to: components/sync_sessions/synced_session_tracker.cc:758](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/sync_sessions/synced_session_tracker.cc#758): Optional name override và gate.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:426](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#426): History đọc tên từ SyncedSession.

## 17. Flag side panel chọn theo tổ hợp và thêm tuỳ chọn pin mặc định

Status: confirmed

Before: 148: có base feature side panel disabled, chưa có flag entry/feature pinned-by-default này.

After: 151: List View bật panel + exclude Stable + pin mặc định; Screenshot View thêm SyncTabScreenshots; Disabled tắt cả bốn. PinnedByDefault bổ sung action vào default kPinnedActions khi registry tạo prefs. Ngoài default pref, MigrateExistingPrefs cũng gọi UpdatePinnedState(true) một lần nếu feature bật và prefs::kTabsFromOtherDevicesAutoPinnedMigration còn false, rồi đánh dấu migration=true.

Mechanism: Choice dùng chuỗi enable-features/disable-features. Toolbar có cả default pref và migration một lần; UpdatePinnedState chỉ thay pin cho regular profile. Migration có thể thêm pin vào profile cũ, không chỉ profile mới.

Impact: List/Screenshot View còn bật lọc Stable và có thể pin nút lên toolbar khi migration chưa chạy. Sau marker=true, nhánh migration này không tự pin lại mỗi lần khởi động. Metadata expiry M153 cần rà lại khi nâng tiếp; không phải lịch xoá chắc chắn.

Conditions: Feature pin disabled mặc định; regular profile và migration marker quyết định tác động. Chưa chạy lifecycle profile thực. Feature panel vẫn có regular-profile gate.

Action: Test profile mới/cũ và pin/unpin đã lưu; thử từng choice trong chrome://flags và kiểm tra tập feature thực tế.

- `flag_entry:tabs-from-other-devices-side-panel` · [to: chrome/browser/flag-metadata.json:9251](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/flag-metadata.json#9251): Entry mới expiry M153; about_flags dùng MULTI_VALUE và các tập enable-features.
- `base_feature:TabsFromOtherDevicesSidePanelPinnedByDefault` · [to: chrome/browser/ui/ui_features.cc:425](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/ui_features.cc#425): Feature mới disabled; toolbar pref registration thêm action side panel nếu bật.
- [to: chrome/browser/about_flags.cc:2829](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/about_flags.cc#2829): Tổ hợp choices.
- [to: chrome/browser/ui/toolbar/toolbar_pref_names.cc:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/toolbar/toolbar_pref_names.cc#15): Reader feature và default pref.
- `pref:toolbar.tabs_from_other_devices_auto_pinned_migration` · [to: chrome/browser/ui/toolbar/toolbar_pref_names.h:33](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/toolbar/toolbar_pref_names.h#33): Marker mới reader/writer trong MigrateExistingPrefs; registry default false.
- [to: chrome/browser/ui/toolbar/pinned_toolbar/pinned_toolbar_actions_model.cc:238](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/toolbar/pinned_toolbar/pinned_toolbar_actions_model.cc#238): Migration pin một lần.
- [to: chrome/browser/ui/toolbar/pinned_toolbar/pinned_toolbar_actions_model.cc:59](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/toolbar/pinned_toolbar/pinned_toolbar_actions_model.cc#59): Regular profile guard và pin khi chưa pin.

## 18. Side panel chỉ ShowUi sau khi frontend lấy xong foreign sessions ban đầu

Status: confirmed

Before: 148: SetPage trên handler đồng thời gọi ShowUI khi có side panel embedder.

After: 151: app side panel gọi handler.showUi() sau getForeignSessions() và cập nhật state; constructor/factory tự nó không mở UI.

Mechanism: ShowUi là thông báo readiness riêng qua Mojo; backend vẫn cần embedder để gọi ShowUI.

Impact: Frontend downstream quên gọi ShowUi có thể không hiện panel dù binding đã tạo xong. Không có bằng chứng độ trễ thực tế đã cải thiện.

Conditions: Áp dụng side panel; History tab chính không dựa vào embedder để hiện trang.

Action: Test initial empty/error/result response và mở lại panel; mock factory phải cho phép frontend hoàn tất readiness.

- `mojo_method:history.mojom.ForeignSessionPageHandler.ShowUi` · [to: ui/webui/resources/cr_components/history/foreign_sessions.mojom:63](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/foreign_sessions.mojom#63): Method mới tách hiển thị side panel khỏi SetPage bị xoá.
- [to: chrome/browser/resources/side_panel/tabs_from_other_devices/app.ts:75](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/app.ts#75): Initial fetch rồi ShowUi.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:350](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#350): Handler target và embedder readiness.

## 19. Side panel thêm screenshot tab đồng bộ với fallback

Status: confirmed

Before: 148: không có datasource screenshot hoặc screenshot grid này.

After: 151: showScreenshots đọc SyncTabScreenshots (mới, disabled); UI dùng chrome://synced-screenshot/<session>/<tab>?timestamp, lỗi ảnh quay về favicon và cho retry khi sessions đổi.

Mechanism: WebUI cài datasource và cho phép img-src chrome://synced-screenshot. Datasource parse session/tab id, gọi SessionSyncService.ReadTabScreenshot và trả image/jpg hoặc rỗng. Service/bridge đọc nullopt khi chưa sync/store; đường ghi screenshot CHECK feature và chỉ ghi khi đang sync/tab hợp lệ.

Impact: Có thêm preview khi thật sự có dữ liệu sync. Bật gate hoặc tạo URL không tự tạo screenshot. Consumer cần xử lý thiếu ảnh và cập nhật CSP/resources.

Conditions: Flag là gate UI/ghi dữ liệu, datasource không tự kiểm tra flag ở đường đọc. Chưa kiểm chứng capture/upload, thiết bị nguồn hoặc chính sách sync end-to-end.

Action: Test flag on/off, missing/invalid session-tab, không sync, cache timestamp, image error fallback và dữ liệu screenshot thực giữa hai thiết bị.

- `base_feature:SyncTabScreenshots` · [to: components/sync_sessions/features.cc:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/sync_sessions/features.cc#15): Gate screenshot, datasource và tests phục vụ cùng cơ chế thumbnail của side panel.
- `webui_gate:tabs_from_other_devices_side_panel_ui/showScreenshots` · [to: chrome/browser/ui/webui/side_panel/tabs_from_other_devices/tabs_from_other_devices_side_panel_ui.cc:58](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/tabs_from_other_devices/tabs_from_other_devices_side_panel_ui.cc#58): Gate screenshot, datasource và tests phục vụ cùng cơ chế thumbnail của side panel.
- `file:chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source.cc` · [to: chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source.cc): Gate screenshot, datasource và tests phục vụ cùng cơ chế thumbnail của side panel.
- `file:chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source_unittest.cc` · [to: chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source_unittest.cc](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source_unittest.cc): Gate screenshot, datasource và tests phục vụ cùng cơ chế thumbnail của side panel.
- [to: chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source.cc:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/side_panel/tabs_from_other_devices/synced_screenshot_data_source.cc#1): Toàn bộ datasource.
- [to: components/sync_sessions/session_sync_bridge.cc:139](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/components/sync_sessions/session_sync_bridge.cc#139): Ghi và đọc screenshot.

## 20. Side panel có gate loại session từ thiết bị chạy kênh Stable

Status: confirmed

Before: 148: không có filter này.

After: 151: nếu đang ở side panel và feature bật, thiết bị có user agent channel stable bị loại khỏi kết quả; History chính không áp dụng filter này.

Mechanism: Consumer tra DeviceInfo bằng session tag, phân tích user-agent; thiếu DeviceInfo không bị suy đoán là Stable và vẫn giữ session.

Impact: Người thử flag List/Screenshot View có thể không thấy thiết bị Stable dù tab sync vẫn có. Không được kết luận sync mất dữ liệu.

Conditions: Default feature disabled; chrome://flags tabs-from-other-devices-side-panel List View và Screenshot View đều bật feature này.

Action: Test Stable/Beta/Dev/Canary/unknown DeviceInfo; so sánh main History và side panel cùng account.

- `base_feature:TabsFromOtherDevicesSidePanelExcludeStableChannel` · [to: chrome/browser/ui/ui_features.cc:422](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/ui_features.cc#422): Feature mới disabled, consumer lọc session trong ForeignSessionHandler.
- [to: chrome/browser/ui/webui/history/foreign_session_handler.cc:386](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/webui/history/foreign_session_handler.cc#386): Lọc foreign sessions và tên thiết bị.

## 21. Tabs from other devices side panel có danh sách, chọn thiết bị và tìm kiếm

Status: confirmed

Before: 148: side panel chỉ render Hello World! dưới feature TabsFromOtherDevicesSidePanel đã tồn tại và disabled.

After: 151: có search field, device picker/menu, danh sách hoặc grid tab, tiêu đề/favicon/relative time. Search không rỗng tìm theo title/URL trên tất cả thiết bị; query rỗng dùng thiết bị đang chọn; tab sắp xếp mới nhất trước.

Mechanism: app.ts lấy foreign sessions qua factory; C++ bổ sung timestamp_display_str. Coordinator IsSupported(Profile*) yêu cầu regular profile ngoài feature, loại incognito/guest.

Impact: Đây là khả năng mới khi bật gate, không phải side panel mặc định mới cho mọi người dùng. Field struct chèn mới cần bindings/fake data cùng phiên bản.

Conditions: Feature chính vẫn disabled ở cả hai ref; cần session sync/open-tabs delegate và dữ liệu phù hợp; không bảo đảm có tab chỉ vì panel mở.

Action: Test search title/URL, clear query, switch device, empty state, timestamps/order, incognito/guest và keyboard accessibility.

- `webui_control:side_panel/tabs_from_other_devices/app/id:deviceMenu` · [to: chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts:36](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts#36): UI side panel và dữ liệu timestamp hiển thị được nối với ForeignSessionHandler.
- `webui_control:side_panel/tabs_from_other_devices/app/id:picker-button` · [to: chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts:32](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts#32): UI side panel và dữ liệu timestamp hiển thị được nối với ForeignSessionHandler.
- `mojo_field:history.mojom.ForeignSessionTab.timestamp_display_str` · [to: ui/webui/resources/cr_components/history/foreign_sessions.mojom:15](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/ui/webui/resources/cr_components/history/foreign_sessions.mojom#15): UI side panel và dữ liệu timestamp hiển thị được nối với ForeignSessionHandler.
- `file:chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts` · [from: chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts), [to: chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/app.html.ts): UI side panel và dữ liệu timestamp hiển thị được nối với ForeignSessionHandler.
- `file:chrome/browser/resources/side_panel/tabs_from_other_devices/tabs_from_other_devices.html` · [from: chrome/browser/resources/side_panel/tabs_from_other_devices/tabs_from_other_devices.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/148.0.7778.217/chrome/browser/resources/side_panel/tabs_from_other_devices/tabs_from_other_devices.html), [to: chrome/browser/resources/side_panel/tabs_from_other_devices/tabs_from_other_devices.html](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/tabs_from_other_devices.html): UI side panel và dữ liệu timestamp hiển thị được nối với ForeignSessionHandler.
- [to: chrome/browser/resources/side_panel/tabs_from_other_devices/app.ts:1](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/resources/side_panel/tabs_from_other_devices/app.ts#1): State, query, sorting và data loading.
- [to: chrome/browser/ui/views/side_panel/tabs_from_other_devices/tabs_from_other_devices_side_panel_coordinator.cc:59](https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/chrome/browser/ui/views/side_panel/tabs_from_other_devices/tabs_from_other_devices_side_panel_coordinator.cc#59): Regular-profile gate.

