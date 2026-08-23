# Bộ tài liệu giải thích ChromeDrift

Sáu tài liệu dưới đây trả lời sáu nhóm câu hỏi độc lập. Có thể gửi riêng từng phần mà người đọc không cần đọc toàn bộ tài liệu lớn trước đó.

1. [Thuật ngữ dùng trong ChromeDrift](<01 - Thuật ngữ ChromeDrift.md>)
2. [ChromeDrift lấy source tree, thư mục và file như thế nào](<02 - Cách lấy source Chromium.md>)
3. [Vì sao có 9 nhóm file và bộ lọc hoạt động ra sao](<03 - Chín nhóm file và bộ lọc.md>)
4. [Fact là gì và từng extractor tạo Fact như thế nào](<04 - Fact và cách trích xuất.md>)
5. [Cơ chế so sánh, chấm điểm, bucket và owner](<05 - Cách so sánh, chấm điểm và phân loại.md>)
6. [Skill và agent hỗ trợ từng team như thế nào](<06 - Skill và cách hỗ trợ từng nhóm.md>)

Nếu chỉ có thời gian cho một vòng đọc ngắn:

- Tech lead: đọc phần 2, 3, 5 và 6.
- Người phát triển extractor: đọc phần 3, 4 và 5.
- WebUI: đọc phần 3 ở các mục WebUI, rồi phần 6.
- Browser C++/native: đọc phần 4 ở `base_feature`, `feature_param`, `pref`, `switch`, rồi phần 5 và 6.
- IPC/Mojo hoặc Web Platform: đọc đúng nhóm Fact tương ứng trong phần 4, sau đó xem signal và owner trong phần 5.

Tài liệu tổng quan: [ChromeDrift và kế hoạch nâng phiên bản Chromium](<Tổng quan ChromeDrift cho việc nâng phiên bản Chromium.md>).
