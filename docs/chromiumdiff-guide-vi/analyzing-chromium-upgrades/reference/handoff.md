# Chuyển việc sang skill khác

Gọi skill đích bằng tên và nêu nhiệm vụ. Không đọc reference hay chạy bất cứ
thứ gì bên trong thư mục của skill đó. Mọi command `chromiumdiff` thuộc về tool,
nên cả hai skill vốn đã gọi cùng một bộ command.

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
hoặc triệu chứng khi một event cần bằng chứng nhân quả. Yêu cầu nó trả chuyển
biến source, CL/issue nó đã đọc, độ chắc chắn, liên hệ tới triệu chứng và bước
kiểm tiếp, rồi ghi kết quả nhận về vào ledger event của chính skill này.

Skill nhận kiểm ref và độ mới bằng chứng, giữ phạm vi và quyền user đã cho,
đọc reference của chính nó. Chuyển việc không tự đánh dấu đã review hay xác
lập nguyên nhân. Report đã được enrich thì refresh review bằng input đã lưu
trước khi ghi quyết định. Skill đích không có thì trả giới hạn năng lực và
bằng chứng về tác vụ gọi, không truy cập trực tiếp file của skill đó.
