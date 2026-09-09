# Chuyển việc sang skill khác

Gọi skill đích bằng tên và nêu nhiệm vụ. Không đọc reference hay chạy script
bên trong thư mục của skill đó. Script dùng chung vẫn ở `scripts/` tại root.

Chuyển một bản ghi ngắn với các trường sau; có thể dùng JSON:

- `from_skill`, `to_skill`: tên skill gửi và nhận.
- `purpose`: câu hỏi cụ thể hoặc kết quả cần trả về.
- `refs`: `from` và `to` chính xác từ report, không dùng alias milestone.
- `artifacts`: đường dẫn report/review, cache, repo Git đã lưu nếu có; nói rõ
  đường dẫn tuyệt đối hay tính từ root repository.
- `identifiers`: UID finding hoặc đường dẫn source chính xác. Chưa có UID
  thì giữ triệu chứng, không đoán identifier.
- `evidence`: quan sát before/after, vị trí/hash source, CL/issue đã đọc và
  điều chúng chứng minh. Phân biệt ứng viên với bằng chứng, link chưa đọc.
- `limits`: bằng chứng thiếu, lượt tìm chưa đầy đủ, câu hỏi còn mở.
- `return_to`: tác vụ gọi và phần kết quả nó cần nhận lại.

Dùng `investigating-chromium-root-causes` để lần nguyên nhân của một thay đổi
hoặc triệu chứng khi event nâng cấp cần bằng chứng nhân quả. Trả chuyển biến
source, CL/issue đã đọc, độ chắc chắn, liên hệ tới triệu chứng và bước kiểm
tiếp. Skill phân tích tự ghi kết quả vào ledger của nó.

Dùng `analyzing-chromium-upgrades` khi user cần review cả đợt nâng cấp hoặc
một khu vực sản phẩm vượt ra ngoài một nguyên nhân. Chuyển phạm vi đã xác nhận
và bằng chứng đang có; không tự suy ra version, khu vực hoặc loại khai báo mới.

Skill nhận kiểm ref và độ mới bằng chứng, giữ phạm vi và quyền user đã cho,
đọc reference của chính nó. Chuyển việc không tự đánh dấu đã review hay xác
lập nguyên nhân. Report đã được enrich thì refresh review bằng input đã lưu
trước khi ghi quyết định. Skill đích không có thì trả giới hạn năng lực và
bằng chứng về tác vụ gọi, không truy cập trực tiếp file của skill đó.
