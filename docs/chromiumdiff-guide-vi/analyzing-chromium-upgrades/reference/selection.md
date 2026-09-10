# Theo dõi mức hoàn thành của danh sách item đã chọn

Dùng sau khi xác nhận phạm vi với user và xem inventory bằng chứng. Ở đây có ba
thứ khác nhau nên mỗi thứ giữ một từ riêng: **scope** là yêu cầu bằng ngôn ngữ
sản phẩm, lưu trong `request.md`; **selection** là danh sách item trong index mà
quyết định phải đủ cho yêu cầu đó, lưu ở khoá `selection` trong `review.json`;
`source_scope` là số file mà lượt quét khai báo đã đọc. Bộ lọc truy vấn không tự
xác lập thứ nào trong ba.

Đưa vào các finding, item `file:` mà yêu cầu bao trùm, cộng bằng chứng hỗ trợ
ngoài đường dẫn đã chọn khi cần. Kiểm thay đổi chỉ có trong implementation và
các dependency chưa giải được; không chỉ chọn điểm cao hoặc finding parser hiểu.
Node không đổi trong graph là bằng chứng hỗ trợ, không phải item cần quyết định.

## Lưu selection

Lấy `fingerprint` hiện tại từ `review check`, dùng ID thật trong index:

```json
{
  "selection": {
    "description": "Phạm vi user đã xác nhận và ranh giới danh sách này",
    "fingerprint": "COPY_CURRENT_REVIEW_FINGERPRINT",
    "items": ["kind:actual-key", "file:path/from/index.cc"]
  }
}
```

Chạy từ root repository:

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/selection.json
python3 -m chromiumdiff review check out/upgrade/review --selection
```

Có thể lưu selection cùng patch event/disposition. Danh sách rỗng, trùng, chứa
ID không tồn tại hoặc fingerprint cũ sẽ bị từ chối. Khi thay, danh sách cũ được
lưu trong `selection_history`. `"selection": null` xoá nó và không thể qua gate.

## Đọc kết quả

`check` vẫn trả số liệu toàn index, đồng thời trả khối `selection` riêng. Khi đã
lưu selection, khối này gồm `configured`, `description`, `total`,
`outside_selection`, `counts`, `by_kind`, `events`, `provisional_events`,
`accounting_complete` và `limit`. Chưa lưu thì khối này chỉ có
`configured: false` và `accounting_complete: false`. Selection mà index không
còn validate được sẽ thêm `invalid: true`.

`check` thường dùng toàn index để quyết định mã thoát. `check --selection` chỉ
trả 0 khi selection đã lưu hợp lệ, không còn item pending/unresolved, không còn
event provisional chạm tới nó, và input vẫn hợp lệ. Phần việc ngoài nó chưa xong
vẫn được hiển thị. Gate không kiểm chứng danh sách có bao trùm ý định user hay
không, và không xác minh ý nghĩa kết luận.

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-selection-complete
```

Báo cáo giữ `PARTIAL` của toàn index nếu cần, thêm riêng `Selection accounting:
COMPLETE`. Selection thiếu hoặc chưa xong thì không ghi đè output. `render`
thường vẫn xuất bản nháp có trạng thái rõ ràng. `--require-complete` kiểm toàn
index; không dùng đồng thời với `--require-selection-complete`.

Input giống nhau giữ selection. Refresh chỉ đổi ngữ cảnh thì cập nhật fingerprint
và mở lại quyết định liên quan, nhưng chỉ khi index mới vẫn còn đủ mọi item đã
chọn: enrichment có thể làm một item biến mất — ID `brief:` là digest của chính
nội dung brief — và khi đó selection bị xoá, `review init` sẽ cảnh báo. Đổi
source/snapshot/baseline thì lưu trữ và xoá luôn. Cả hai trường hợp đều phải xác
nhận lại danh sách từ index mới trước khi tuyên bố hoàn thành.
