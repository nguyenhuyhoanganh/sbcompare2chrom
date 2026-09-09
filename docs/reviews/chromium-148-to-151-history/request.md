# Yêu cầu review Chromium History

- Yêu cầu gốc: “chạy skill analyzing-chromium-upgrades cho 2 ver 148.0.7778.217 và 151.0.7922.138 cho History về flag mojom webui”.
- Ưu tiên: người dùng trả lời “full” khi được hỏi về thay đổi người dùng thấy, khả năng mới và thay đổi sản phẩm cần thích nghi; bao gồm cả ba mục trong phạm vi History.
- Phiên bản: 148.0.7778.217 → 151.0.7922.138.
- Exact refs từ report: refs/tags/148.0.7778.217 → refs/tags/151.0.7922.138.
- Khu vực: History, gồm trang History, các component History/Clusters/Embeddings và side panel cùng dependency cần thiết.
- Declaration kinds yêu cầu: feature flags (base_feature, feature_param, flag_entry), Mojo interfaces và thành viên (mojo_*), WebUI controls/gates/routes. Các loại khác và source-only changes vẫn được đọc nếu giải thích phạm vi này.
- Loại trừ: không review độc lập các khu vực sản phẩm khác; dependency liên quan History không bị loại chỉ vì ở đường dẫn khác. “Full” là đầy đủ các mục ưu tiên của History, không phải toàn bộ Chromium.
- Platform: Windows theo comparison. Chưa có downstream Chromium checkout, patch, cấu hình build, Finch, hay kết quả UI runtime của sản phẩm; không suy đoán những consumer sản phẩm đang ship.
- Comparison đã dùng: `wide`, 6.064 findings, cùng exact refs và fingerprint ghi ở trên. Tài liệu: `docs/reviews/chromium-148-to-151-history/` — [delivery.md](delivery.md), [review.md](review.md).
- Cache: .chromiumdiff-cache. Không có source-repo được cung cấp. Dùng broad target_set=wide sẵn có, partitions=[]; không thu hẹp acquisition.
- Evidence fingerprint: `30277b7bb0496db1f0a0229226bc6c1c43daee9a29e8adf6ed8f90d58efd52ba`.
- Nguồn lực: không có hạn mức thời gian/token do người dùng chỉ định; có thể tiếp tục qua context compaction. Lưu quyết định từng batch.
- Delivery: tài liệu Markdown đã hoàn tất trong `docs/reviews/chromium-148-to-151-history/`; không có đích xuất bản Confluence.

- Chỉ dẫn bổ sung: “làm nốt đi, đừng quan đếm phần phân tích của download bookmark” — hoàn tất History độc lập, không mở rộng sang review Downloads/Bookmarks.

- Bàn giao bổ sung: lưu ba file Markdown theo cấu trúc `docs/reviews`; bỏ thư mục output tạm khỏi project sau khi kiểm tra bản tài liệu và liên kết.
