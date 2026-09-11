# Yêu cầu review Extensions

- Người dùng: "tiếp tục sử dụng skill làm report cho phần extension … làm đi" — giao việc tiếp nối ba review trước. Phiên bản, loại khai báo và mức độ được giữ nguyên như ba review đó theo chỉ thị này; vùng mới là **Extensions**.
- Phân tích **Extensions** khi nâng Chromium **148.0.7778.217 → 151.0.7922.138**, tập trung **flags, mojom, WebUI**, mức **full**: thay đổi người dùng thấy, khả năng mới, và việc sản phẩm downstream cần thích nghi.
- Refs: `refs/tags/148.0.7778.217` → `refs/tags/151.0.7922.138`.
- Fingerprint: `30277b7bb0496db1f0a0229226bc6c1c43daee9a29e8adf6ed8f90d58efd52ba`.
- Nền tảng: Windows theo evaluator của chromiumdiff. Chưa có cấu hình build, patch downstream, policy hoặc Finch của sản phẩm để xác nhận tác động riêng.
- Vùng Extensions gồm: hệ thống extension (`extensions/`, `chrome/browser/extensions/`, `chrome/common/extensions/`, `chrome/renderer/extensions/`), trang chrome://extensions (`chrome/browser/ui/webui/extensions/`, `chrome/browser/resources/extensions/`), UI extension trên thanh công cụ và side panel (`chrome/browser/ui/views/extensions/`, `chrome/browser/ui/extensions/`, extensions bar của WebUI toolbar/browser), cộng pref, handler, source delta và dependency cần thiết để giải thích flags/Mojo/WebUI.
- Ngoài phạm vi: Settings, History, Downloads và Bookmarks đã review riêng; API extension chỉ build trên ChromeOS được ghi out_of_scope cho review Windows; `authentication_extensions*` của WebAuthn trùng tên nhưng không phải browser extension.
- Dùng comparison rộng có sẵn: `out/M148_to_M151_wide/report.json`, `target_set=wide`, không partition; cache `.chromiumdiff-cache`. Không có Chromium Git checkout. Review riêng: `out/review-extensions`.
- Nguồn so sánh là inventory cache, không phải toàn bộ cây Chromium. Các file khai báo feature của extension API (`_api_features.json`, `_permission_features.json`, `_manifest_features.json`) không nằm trong cache ở cả hai phía; được fetch đúng ref khi cần, và phần không fetch được ghi là thiếu evidence. Không xem file thiếu cache là file bị xóa.
- Bàn giao vào `docs/reviews/chromium-148-to-151-extensions`, gồm delivery dễ đọc, review có evidence và request này.
- Không có giới hạn thời gian/token do người dùng đặt; có thể tiếp tục qua compaction. Kiểm tra ở mức source; chưa chạy build/browser test, không xác nhận rollout.
