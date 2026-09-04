# Bộ tài liệu giải thích ChromiumDiff

## ChromiumDiff là gì, trong ba câu

Samsung Browser được xây trên mã nguồn Chromium. Vài milestone một lần, team phải chuyển nền Chromium sang một version mới hơn — đây là việc mà tài liệu này gọi là `upgrade`. ChromiumDiff là một công cụ đọc mã nguồn Chromium ở hai version, tìm ra những **khai báo** đã thay đổi (feature flag, Web API, IPC contract, preference key, trang `chrome://`...), rồi xếp chúng thành một danh sách có thứ tự ưu tiên, có lý do và có vị trí `file:dòng` để người đọc mở source kiểm tra lại.

Điều quan trọng cần nhớ ngay từ đầu: ChromiumDiff **chỉ đọc Chromium gốc**. Nó không đọc mã nguồn Samsung, nên nó không thể nói "Samsung sẽ bị lỗi ở đâu". Nó chỉ nói "Chromium đã đổi những gì, và team nào nên kiểm tra trước".

## Bộ tài liệu này gồm những gì

Bảy tài liệu dưới đây trả lời bảy nhóm câu hỏi độc lập với nhau. Có thể gửi riêng từng phần cho một người mà không bắt họ đọc toàn bộ tài liệu lớn trước đó.

| # | Tài liệu | Trả lời câu hỏi |
|---|---|---|
| 1 | [Thuật ngữ dùng trong ChromiumDiff](<01 - Thuật ngữ ChromiumDiff.md>) | Những từ trong báo cáo có nghĩa là gì? |
| 2 | [ChromiumDiff lấy source Chromium như thế nào](<02 - Cách lấy source Chromium.md>) | Công cụ tải code từ đâu, tải bao nhiêu, và làm sao biết đã tải đúng? |
| 3 | [Chín nhóm file và bộ lọc](<03 - Chín nhóm file và bộ lọc.md>) | Vì sao chỉ đọc 9 nhóm file, và một file phải qua bao nhiêu lớp lọc? |
| 4 | [Fact và cách trích xuất](<04 - Fact và cách trích xuất.md>) | Một khai báo trong source biến thành dữ liệu so sánh được bằng cách nào? |
| 5 | [So sánh, chấm điểm và phân loại](<05 - Cách so sánh, chấm điểm và phân loại.md>) | Vì sao một thay đổi được 80 điểm còn thay đổi khác được 20 điểm? |
| 6 | [Skill và cách hỗ trợ từng nhóm](<06 - Skill và cách hỗ trợ từng nhóm.md>) | Một AI agent có thể tạo báo cáo riêng cho từng team không, và tới mức nào? |
| 7 | [Truy nguyên CL và issue](<07 - Truy nguyên CL và issue.md>) | Ai đã tạo ra thay đổi này, họ đang sửa cái gì, và những dòng nào thật ra là cùng một thay đổi? |

Sáu tài liệu đầu nói về việc **cái gì đã đổi** — đó là phần công cụ trả lời được chỉ bằng hai cây source. Tài liệu thứ bảy là phần còn lại: nó hỏi Gerrit, review server của chính Chromium, để tìm ra CL đã tạo ra thay đổi và issue đứng sau CL đó. Nó cần mạng và được tách thành một lệnh riêng, vì một báo cáo vẫn đáng đọc khi không có nó.

Ngoài ra còn một tài liệu tổng quan dài hơn, dùng khi cần trình bày toàn bộ project trong một buổi họp: [ChromiumDiff và kế hoạch nâng phiên bản Chromium](<Tổng quan ChromiumDiff cho việc nâng phiên bản Chromium.md>). Nội dung của nó bao trùm sáu phần trên, nhưng đi kèm số liệu chạy thật, kịch bản demo và phần hỏi đáp.

Kèm theo bộ tài liệu là một sơ đồ luồng: [Luồng xử lý của ChromiumDiff](flow.html) — mở thẳng trong trình duyệt, không cần mạng. Nó gom cả năm chặng của công cụ vào một hình, dùng khi cần định vị nhanh chặng đang nói tới nằm ở đâu.

## Nên đọc phần nào

Nếu chỉ có thời gian cho một vòng đọc ngắn, đây là lộ trình theo vai trò:

| Vai trò | Đọc theo thứ tự | Vì sao |
|---|---|---|
| Người mới, chưa biết gì về project | 1 → 2 → 5 | Có từ vựng, biết dữ liệu từ đâu ra, biết đọc điểm số |
| Tech lead | 2 → 3 → 5 → 6 | Đủ để đánh giá công cụ đáng tin tới đâu và đưa vào quy trình thế nào |
| Người trực tiếp triage một đợt upgrade | 5 → 7 | Biết đọc điểm số, rồi biết hỏi tiếp *vì sao* một dòng lại đổi |
| Người viết thêm extractor cho công cụ | 3 → 4 → 5 | Biết bộ lọc, biết cấu trúc dữ liệu, biết thay đổi nào tạo ra tín hiệu gì |
| Team WebUI | Mục WebUI trong phần 3 → phần 6 | Biết công cụ đọc được gì trong `chrome://settings` và cần kiểm tra gì |
| Team Browser C++ / native | Các mục `base_feature`, `feature_param`, `pref`, `switch` trong phần 4 → phần 5 → phần 6 | Biết feature flag và pref key được theo dõi ra sao |
| Team IPC/Mojo hoặc Web Platform | Nhóm Fact tương ứng trong phần 4 → phần signal và owner trong phần 5 | Biết contract nào được theo dõi và thay đổi nào bị coi là nguy hiểm |

## Quy ước dùng trong cả bộ tài liệu

Nhiều thuật ngữ trong project không có từ tiếng Việt tương đương chính xác. Ép dịch chúng sẽ làm người đọc mất liên hệ với những gì hiện trên màn hình báo cáo và trong mã nguồn. Vì vậy quy ước là:

- **Giữ nguyên từ tiếng Anh** khi đó là tên một khái niệm kỹ thuật hoặc một chuỗi xuất hiện thật trong công cụ — ví dụ `Fact`, `signal`, `bucket`, `coverage`, `target set`.
- **Kèm giải thích ngắn trong ngoặc ở lần dùng đầu tiên** của mỗi tài liệu.
- **Dịch sang tiếng Việt** khi từ tiếng Anh không phải tên riêng của khái niệm — ví dụ "khai báo" thay cho "declaration", "phiên bản" thay cho "version" trong văn xuôi thông thường.

Toàn bộ định nghĩa được gom trong [phần 1](<01 - Thuật ngữ ChromiumDiff.md>); khi gặp một từ lạ, tra ở đó trước.
