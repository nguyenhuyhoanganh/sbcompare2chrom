# Xác nhận phạm vi và chọn bằng chứng

Agent MUST xác định nhu cầu của user trước khi phân tích. Khu vực sản phẩm
khác với loại khai báo: một thay đổi trong Settings có thể liên quan đến route,
pref, feature C++, interface IPC và code chưa được parser hiểu. Chọn một kind
là điểm bắt đầu, không chứng minh các kind khác không liên quan.

## Hỏi và lưu câu trả lời

Hỏi user quan tâm khu vực nào và báo cáo cần hỗ trợ quyết định gì. Cho phép
chọn nhiều khu vực, tự mô tả khu vực khác hoặc chọn so sánh rộng. Những ví dụ
trong SKILL.md không phải danh sách giới hạn tính năng cần phát hiện. User
không biết kind kỹ thuật thì dùng câu trả lời theo chức năng sản phẩm của họ.

Nếu cần xác định tác động riêng với sản phẩm dựa trên Chromium, hỏi về patch,
component hoặc cấu hình liên quan. Phần chưa biết phải được ghi rõ, không đoán
sản phẩm đang dùng consumer nào. Script hiện xét điều kiện Windows, không
hỗ trợ chọn platform tuỳ ý.

Câu trả lời rõ ràng đã có trong yêu cầu thì dùng luôn. Nếu còn thiếu, MUST
chờ user trả lời. Lựa chọn được chọn sẵn trên giao diện, sự im lặng hoặc một
review trước không phải xác nhận. User có thể giao quyền chọn phạm vi; khi đó
nêu phạm vi đã chọn trước khi làm tiếp.

Sau khi tạo hoặc mở review, lưu `request.md` trong thư mục đó bằng cơ chế sửa
file của môi trường. Ghi:

- câu trả lời thực tế của user và version yêu cầu; bổ sung ref chính xác và
  fingerprint khi script trả về;
- khu vực, quyết định cần hỗ trợ và kind được ưu tiên nếu có;
- phần user loại trừ rõ ràng; phân biệt loại trừ với ít ưu tiên hơn;
- ngữ cảnh sản phẩm/build đã biết và thông tin còn thiếu;
- đường dẫn report, cache, Git và giới hạn tải source đã thống nhất;
- giới hạn tài nguyên thực sự biết và khả năng tiếp tục bằng context mới.
  Không tự đặt số token hoặc ngân sách tổng công việc rồi coi là user yêu cầu.

Ghi chú này lưu yêu cầu; CLI không tự dùng nó làm bộ lọc và không xác minh
user có thật sự đồng ý hay không. MUST giữ nội dung khớp hội thoại. Khi phạm
vi đổi, xem lại những loại trừ và kết luận phụ thuộc phạm vi cũ. Không gộp số
đếm của các review khác phạm vi rồi coi mức hoàn thành của chúng tương đương.

## Chọn phạm vi tải source riêng với phạm vi phân tích

Trước lần so sánh mới, giải thích đánh đổi:

- Lần quét đầy đủ giữ được nhiều bằng chứng giữa các khu vực nhất, và vẫn
  không phủ toàn bộ code hay ngữ pháp Chromium. `--target-set smoke` đọc ba
  file để kiểm công cụ có chạy không; nó không trả lời được câu hỏi so sánh.
- `--partition` giới hạn việc tải vào các đường dẫn được công cụ hỗ trợ cho
  khu vực đã chọn. Nó không bao hết hành vi của khu vực đó. Chỉ dùng sau khi
  user chấp nhận phạm vi tải hẹp hơn. Kiểm tra tên tuỳ chọn bằng
  `python3 -m chromiumdiff run --help`; không tự tạo tên partition mới.
- Báo cáo rộng đã có có thể được truy vấn mà không tải lại hoặc nạp toàn bộ
  vào context. Không tạo lại chỉ để tập trung vào một khu vực.

Code ngoài `settings/` vẫn có thể ảnh hưởng Settings. Lần theo điều kiện,
consumer, dữ liệu dùng chung và lịch sử liên quan qua các thư mục. Tải file
thiếu ở đúng ref khi được phép; nếu không thì nêu bằng chứng còn thiếu. Kind
user chọn MUST NOT loại bỏ source hoặc kind liên quan cần để giải thích hành vi.

## Đọc tổng hợp toàn bộ chỉ mục trước khi mở từng item

Sau `review init`, MUST chạy các lệnh sau và đọc kết quả:

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` trả mã 1 khi chưa xong; ban đầu điều này là bình thường. `overview`
tổng hợp toàn bộ index trong tiến trình script, không in finding thô, nội dung
diff hoặc ID từng item. `index_total` là số item trước khi lọc; `total` là số
nhóm tổng hợp của truy vấn. Đọc tiếp bằng `--cursor` đến khi `next_cursor` là
null. Nhóm đường dẫn có thể trùng item khi finding có nhiều đường dẫn. Các số
đếm không phải số event, độ quan trọng, ước lượng token hay bằng chứng đã đọc.

Dùng `--path-prefix` để chọn thư mục đã thấy trong kết quả, tăng `--path-depth`
để xem chi tiết hơn. Bộ lọc khớp từng thành phần đường dẫn, không dùng danh
sách tên tính năng. Ví dụ, thay giá trị bằng dữ liệu thực tế:

```bash
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 5 --path-prefix chrome/browser/resources
python3 -m chromiumdiff review index out/upgrade/review --status pending --path-prefix chrome/browser/resources/settings --limit 20
python3 -m chromiumdiff review index out/upgrade/review --status pending --fact-kind pref --limit 20
python3 -m chromiumdiff review index out/upgrade/review --status pending --item-kind source_delta --limit 20
```

`--fact-kind` nhận loại khai báo ở nhóm có `item_kinds.finding` trong overview.
Với `source_delta` hay `milestone_lead`, dùng `--item-kind`. Lặp `--fact-kind` hoặc
`--path-prefix` để chọn bất kỳ giá trị nào trong danh sách tương ứng. Các loại
bộ lọc khác nhau được kết hợp. Lọc fact-kind chỉ trả finding, nên MUST đọc
thêm source delta liên quan. Bộ lọc chỉ chọn dữ liệu để đọc, không quyết định
thành viên event, không đánh dấu ngoài phạm vi và không xoá item pending.

## Dùng context cho câu hỏi của user

Với một khu vực sản phẩm đã chọn, MUST dùng [focus.md](focus.md) để tạo và đọc
gói ứng viên từ source. Truy vấn đường dẫn/kind đơn thuần bỏ sót phụ thuộc khai
báo ở nơi khác, kể cả Mojo được gọi từ file consumer không đổi.

Từ bản tổng hợp, tìm bằng chứng cho khu vực đã xác nhận rồi đọc khai báo liên
quan, source trước/sau và consumer. Không cần in mọi dòng không liên quan
trước. Giải thích chuyển biến và việc cần làm, không tìm đủ một số lượng
entry điểm cao. Mức quan trọng phải có lý do dựa trên quyết định user cần và
tác động có bằng chứng, không dựa vào số dòng đổi, tên quen thuộc hay bucket.

Phân biệt phần không liên quan, phần bị loại và phần chưa rõ phạm vi. Ngoài
đường dẫn ban đầu không tự động nghĩa là không liên quan. Chưa rõ thì giữ câu
hỏi hoặc giới hạn phạm vi, không âm thầm bỏ qua. Xét cả thay đổi chỉ có trong
source và bản tóm tắt milestone, không chỉ finding.

Phân trang giới hạn một kết quả, không giới hạn context tích luỹ. MUST NOT nói
rằng đọc hết mọi trang sẽ vừa 200k token. Lưu kết quả và vị trí source rồi tiếp
tục bằng context mới nếu môi trường hỗ trợ. Nếu chỉ có một context cố định,
thống nhất phạm vi nhỏ hơn với user hoặc báo phần chưa làm. Số đếm tổng hợp
không chứng minh đã tìm được mọi thay đổi quan trọng.

## Trước khi giao báo cáo

MUST kiểm tra yêu cầu đã lưu khớp lựa chọn của user, reference bắt buộc đã đọc,
và lệnh đã thực sự chạy. Nêu đường dẫn request/review, ref chính xác, kết quả
check cuối và giới hạn còn lại. Không ghi đã đọc hay đã chạy khi chưa làm.
Nếu môi trường có lịch sử thực thi công cụ, giữ lại để kiểm tra.

`review check` kiểm tra quyết định cho các item, không kiểm việc đọc reference
hay sự đồng ý của user. Chữ `MUST` không cưỡng chế được môi trường bỏ qua skill.
Muốn cưỡng chế từ bên ngoài agent, chương trình gọi agent phải kiểm tra việc
thực thi công cụ và từ chối lời nhận hoàn thành thiếu bằng chứng. Một ô do
agent tự đánh dấu không tương đương với bằng chứng đó.
