# Khi một lần tra cứu không trả về kết quả

`why.py` tìm trong các finding của `report.json`, rồi tìm các CL liên quan.
**Không có finding nào khớp** và **không có CL nào khớp** là hai kết quả khác
nhau. Riêng từng cái đều không xác lập rằng source hay hành vi không đổi.

## Phần A — không có finding nào khớp

Helper in ra `nothing ... matches`. Kiểm các khả năng dưới đây.

### A1. Chuỗi tìm không khớp định danh mà báo cáo dùng

Dùng `kind:key` của finding, hoặc tìm theo một mẩu đường dẫn. Chuỗi tên feature
dùng cho bên ngoài và định danh C++ của nó có thể khác nhau. Key của Mojo bao
gồm cả namespace và khai báo chứa nó. Giữ nguyên đường dẫn cache thật:

```bash
python3 scripts/why.py out/DIR features.cc --cache "$cache_dir"
```

Lệnh này vẫn tìm trong các finding của báo cáo, **không** tìm lịch sử file bất
kỳ. Một ID dạng `file:` hoặc `brief:` của review index không phải UID của finding.

### A2. File nằm ngoài phạm vi quét khai báo

Xem target set, partition và coverage của lần chạy. Nếu file đó không được đọc,
báo cáo **không thể** xác lập các khai báo trong nó có đổi hay không.
Một lần chạy đầy đủ phủ các file mà target của nó nêu tên, không phải mọi code.

Với một câu hỏi cụ thể, hãy xem source cần thiết ở **cả hai ref chính xác**. Chỉ
dựng lại một lần so sánh rộng hơn khi phạm vi của user cần tới, và giữ kết quả
đó tách khỏi phân tích đang có trừ khi chủ ý thay thế.

### A3. Parser không trích xuất cú pháp này

Coverage theo **file** và coverage theo **cú pháp** là hai chuyện khác nhau. Một
file có thể đã nằm trong cache trong khi một số khai báo của nó không được biểu
diễn thành fact. Hãy đọc diff thô của file đó, đừng kết luận rằng không có
finding khớp nghĩa là không có thay đổi.

### A4. Thay đổi nằm trong code hiện thực

Một thay đổi trong thân hàm có thể không sinh ra finding nào về khai báo. Danh
mục source của review vẫn có thể chỉ ra file đã đổi, nếu file đó nằm trong cache
hoặc nằm trong phần so sánh Git đã chọn. Hãy xem `review source` và các consumer
liên quan ngay cả khi `why.py` không giải được.

Với A3 và A4, dùng
[thủ tục đọc source/lịch sử trực tiếp](history.md).
Nó không cần có finding và không cần biết trước tên tính năng.

### A5. Không tìm thấy khác biệt source liên quan

Nêu rõ đã so **những đường dẫn nào, ở ref nào, trong phạm vi nào**. Đừng khái
quát kết quả đó ra các file chưa cache, ra cấu hình bên ngoài, hay ra hành vi
sản phẩm. Ngay cả khai báo không đổi cũng có thể có consumer hoặc điều kiện
runtime đã đổi.

## Phần B — có finding, nhưng không có CL giải thích được

Đọc các warning của lần tra cứu **trước khi** diễn giải một danh sách `changes`
rỗng. Nhiều giới hạn có thể cùng áp dụng cho một lần tra cứu.

### B1. Chưa từng tra cứu

Không có khối enrichment nghĩa là chưa có kết quả tra cứu nào được lưu. Chạy tra
cứu nếu câu hỏi cần tới lịch sử.

### B2. Không kết nối được Gerrit

Lỗi kết nối hay lỗi request xác lập **một vấn đề khi lấy dữ liệu**, không xác lập
rằng không có thay đổi nào. Kiểm quyền truy cập và thử lại khi có ích. Vẫn không
truy cập được thì giữ kết quả ở mức source và nêu rõ giới hạn về lịch sử.

### B3. Chạm giới hạn budget đọc diff

`diffs_read: false` nghĩa là các diff liên quan chưa được đọc. Tăng budget cho
đúng finding đang xét khi có lý do. `--budget 0` bỏ trần đọc diff; **đừng** dùng
nó mặc định cho một lần so sánh lớn.

### B4. Một số request thất bại

`failed_fetches > 0` nghĩa là bằng chứng trả về **không đầy đủ**. Các kết quả
thành công vẫn có thể chống đỡ một kết luận có giới hạn. Thử lại phần lấy dữ liệu
thất bại khi có thể; phần đã thành công vẫn dùng lại được từ cache.

### B5. Danh sách ứng viên không đầy đủ

`search_incomplete` cho biết danh sách ứng viên có thể thiếu các CL liên quan.
Đọc các ứng viên đang có và dùng lịch sử trực tiếp nếu cần. **Đừng** coi danh
sách chưa đầy đủ đó là toàn bộ commit ảnh hưởng tới file.

### B6. Các lần tìm đã hoàn tất nhưng không có kết quả nào giải thích được

Nếu các lần tìm và các diff liên quan đã chạy xong mà không vướng giới hạn
B2–B5, kết quả vẫn chỉ giới hạn trong những đường dẫn, identifier, branch và
luật tìm kiếm đó. **Nó không xác định được nguyên nhân của thay đổi chưa khớp.**

Hãy điều tra các đường dẫn bị đổi tên, source được sinh ra, cập nhật dependency,
và lịch sử branch nếu phù hợp. Dùng thủ tục đọc source/lịch sử trực tiếp đã dẫn ở
trên. Nêu rõ **những lần tìm nào đã không giải thích được** khác biệt quan sát
được, thay vì khẳng định commit chịu trách nhiệm phải có hình dạng nào đó.

## Thử lại và trạng thái lệnh

Dùng `--retry` để tra lại kết quả đã lưu và giữ cache thành công, kể cả khi tăng
`--budget`. `--refresh` lấy lại dữ liệu Gerrit. JSON có `lookup.status` và
`lookup.warnings`: `complete`, `partial`, `unavailable`, `not_run`. Đây là trạng
thái tra cứu, không phải kết luận nhân quả. Mã 3 là lịch sử thiếu/không truy cập
được; 1 là không finding khớp; 2 là lỗi input/lưu file. `lookup_warnings` trong
khối Gerrit giữ giới hạn lấy dữ liệu bổ sung của lần tra cứu đã lưu trước đó.

## Đọc các trường đã lưu

| Trường trong `enrichment.gerrit` | Diễn giải |
|---|---|
| Không có khối này | Chưa có kết quả tra cứu nào được lưu |
| `diffs_read: false` | Các diff liên quan chưa được đọc |
| `failed_fetches > 0` | Một số request thất bại |
| `search_incomplete` | Danh sách ứng viên có thể không đầy đủ |
| `changes: []` | Không có CL nào khớp được lưu; kiểm mọi giới hạn ở trên |
| `found_by: "message"` | Ứng viên đến từ việc tìm trong commit message; phải kiểm diff của chúng |

**Đừng** coi một issue không truy cập được là bằng chứng chống đỡ. Khi lưu kết
quả tra cứu mới, phải giữ nguyên cache và cấu hình Git của review trong lúc
refresh, theo
[thủ tục giữ input đã lưu](investigation.md)
của skill này.
