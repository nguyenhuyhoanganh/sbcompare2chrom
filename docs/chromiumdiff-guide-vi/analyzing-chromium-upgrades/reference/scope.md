# Theo dõi mức hoàn thành của phạm vi đã chọn

Dùng sau khi xác nhận phạm vi với user và xem inventory bằng chứng. `request.md`
lưu yêu cầu bằng ngôn ngữ sản phẩm; `scope` lưu danh sách item cụ thể cần xử lý.
Bộ lọc truy vấn không tự xác lập danh sách này.

Đưa vào các finding, item `file:` và bằng chứng hỗ trợ ngoài đường dẫn đã chọn
khi cần. Kiểm thay đổi chỉ có trong implementation và các dependency chưa giải
được; không chỉ chọn điểm cao hoặc finding parser hiểu. Node không đổi trong
graph là bằng chứng hỗ trợ, không phải item cần quyết định.

## Lưu phạm vi

Lấy `fingerprint` hiện tại từ `review check`, dùng ID thật trong index:

```json
{
  "scope": {
    "description": "Phạm vi user đã xác nhận và ranh giới danh sách này",
    "fingerprint": "COPY_CURRENT_REVIEW_FINGERPRINT",
    "items": ["kind:actual-key", "file:path/from/index.cc"]
  }
}
```

Chạy từ root repository:

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/scope.json
python3 -m chromiumdiff review check out/upgrade/review --scope
```

Có thể lưu scope cùng patch event/disposition. Danh sách rỗng, trùng, chứa ID
không tồn tại hoặc fingerprint cũ sẽ bị từ chối. Khi thay phạm vi, danh sách cũ
được lưu trong `scope_history`. `"scope": null` xoá phạm vi và không thể qua gate.

## Đọc kết quả

`check` vẫn trả số liệu toàn index, đồng thời trả khối `scope` riêng:
`configured`, `description`, `total`, `outside_scope`, `counts`, `by_kind`,
`provisional_events`, `accounting_complete`. Chưa lưu scope thì khối này chỉ
có `configured: false` và `accounting_complete: false`.

`check` thường dùng toàn index để quyết định mã thoát. `check --scope` chỉ trả
0 khi scope đã lưu hợp lệ, không còn item pending/unresolved, không còn event
provisional chạm tới scope, và input vẫn hợp lệ. Phần ngoài scope chưa xong
vẫn được hiển thị. Gate không kiểm chứng danh sách có bao trùm ý định user hay
không, và không xác minh ý nghĩa kết luận.

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-scope-complete
```

Báo cáo giữ `PARTIAL` của toàn index nếu cần, thêm riêng `Scope accounting:
COMPLETE`. Scope thiếu hoặc chưa xong thì không ghi đè output. `render` thường
vẫn xuất bản nháp có trạng thái rõ ràng. `--require-complete` kiểm toàn index;
không dùng đồng thời với `--require-scope-complete`.

Input giống nhau giữ scope. Refresh chỉ đổi ngữ cảnh giữ danh sách item, cập
nhật fingerprint và mở lại quyết định liên quan. Đổi source/snapshot/baseline
thì lưu trữ và xoá scope; phải xác nhận lại danh sách từ index mới.
