# Lấy bằng chứng cho khu vực đã chọn

Dùng sau khi xác nhận phạm vi. Quy trình này giảm việc truy vấn lặp, không
tự xác định event hoặc chứng minh đã phát hiện đầy đủ. MUST đọc
[scoping.md](scoping.md) và [investigation.md](investigation.md) trước.

## Tạo gói bằng chứng

Chọn đường dẫn chính xác từ `review overview` và source liên quan. Dùng review
rộng đã có nếu phù hợp. Những đường dẫn Settings dưới đây chỉ là ví dụ về
lựa chọn của user, không phải quy tắc tên tính năng được cài sẵn:

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix chrome/browser/resources/settings \
  --path-prefix chrome/browser/ui/webui/settings \
  --fact-kind base_feature --fact-kind mojo_method --fact-kind webui_control \
  --output out/upgrade/review/settings-focus.json
```

Lặp `--fact-kind` cho các loại khai báo user ưu tiên. Tuỳ chọn chỉ đánh dấu
`requested_kind`, không bỏ loại bằng chứng hỗ trợ. Pref có thể giải thích một
thay đổi WebUI dù user không chọn pref. Bỏ tuỳ chọn thì mọi kind được lấy đều
được đánh dấu là được yêu cầu. Đường dẫn output phải mới; lệnh từ chối ghi đè.

Lệnh này:

- bắt đầu từ khai báo và source dưới các đường dẫn đã chọn, kể cả phần không đổi;
- đọc source ở cả hai ref chính xác, tìm identifier của feature C++, tên Mojo
  có namespace và include/import Mojo;
- lần theo quan hệ khai báo và các thành viên của interface/struct được tham
  chiếu, giữ bằng chứng của cả hai phiên bản;
- giữ source delta trong phạm vi và các file được tham chiếu, kể cả file không
  có finding;
- ghi trường hợp khớp mơ hồ, thiếu khai báo/source và giới hạn số bước lần theo
  quan hệ. `--hops` đặt độ sâu lần theo quan hệ khai báo (mặc định 3, tối đa 8),
  không phải mức bảo đảm đầy đủ về ý nghĩa.

Không lọc theo score hay danh sách tên tính năng. Cùng import, file, flag hoặc
interface không có nghĩa là cùng event. Import có thể dẫn đến nhiều thay đổi
không liên quan. Test và code không hoạt động vẫn có thể khớp identifier.
MUST kiểm tra consumer thực tế và các điều kiện trước khi nói ứng viên ảnh
hưởng tới khu vực sản phẩm đã chọn.

## Đọc từng phần của gói bằng chứng

```bash
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/settings-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/settings-focus.json --section findings --limit 20
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/settings-focus.json --section files --limit 20
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/settings-focus.json --section unresolved --limit 20
```

Đọc tiếp mỗi phần bằng `--cursor` đến khi `next_cursor` là null. `findings`
chứa bản rút gọn trước/sau, deltas và ID tham chiếu. `files` liệt kê toàn bộ
source delta của từng file, không chỉ hunk có finding. `references` có hai dạng dòng:
dòng khớp source mang `targets`, dòng quan hệ khai báo mang `source` và
`target`. Cả hai đều mang `certainty`, nhận giá trị
`declared_reference` khi parser đã ghi nhận quan hệ, `lexical_lead` khi source
khớp đúng một khai báo, `ambiguous_lead` khi nhiều khai báo trùng tên, và
`unmatched` khi không có gì trong index khớp. Mọi dòng `unmatched` cũng xuất
hiện trong `unresolved` kèm bước kiểm tra tiếp theo. `sources` ghi phía
trước/sau, nguồn gốc và hash của các file đã quét.

Với file trong phạm vi đã xác nhận, đọc mọi hunk thay đổi. Với file dùng chung
nằm ngoài phạm vi, bắt đầu từ khai báo/consumer được tham chiếu rồi lần theo
hunk liên quan. Không đọc tất cả thay đổi không liên quan trong một file khai
báo trung tâm chỉ vì một flag cần xem nằm ở đó. Không đánh dấu cả file đã giải
thích nếu còn hunk chưa đọc; kiểm toàn bộ index có thể vẫn là partial khi giao
kết quả cho phạm vi hẹp.

Để xem tham chiếu trực tiếp của một ứng viên:

```bash
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/settings-focus.json --section references --item 'KIND:KEY'
```

Dùng ID thật. `--item` cũng nhận ID tham chiếu hoặc `file:PATH` để tìm bản ghi
theo file. Lần theo source/target ID nếu có chuỗi tham chiếu. Preview có
`truncated` thì MUST mở đầy đủ bằng `review inspect UID` trước khi dựa vào
trường bị lược. Dùng `review source` để đọc code trước/sau thực tế, không chỉ
dựa vào giá trị khai báo đã rút gọn.

Gói này không phải sổ quyết định review. Lưu kết luận bằng `review record`
với ID gốc, rồi check/render như thường lệ. Đọc gói không tự đánh dấu ứng viên
đã được xem hay phần còn lại bị loại khỏi phạm vi.

## Giới hạn ảnh hưởng tới độ đầy đủ và context

MUST xem phần `unresolved` và các giới hạn. Tìm tham chiếu ở đây dựa trên cú
pháp văn bản, không phải compiler hoặc đồ thị lời gọi đầy đủ. Chỉ source ở
các đường dẫn ban đầu được quét identifier. Tự lần theo consumer, import hoặc
hàm hỗ trợ tiếp theo khi cần; có thể thêm đường dẫn đã quan sát rồi tạo gói
mới. Binding sinh lúc chạy và biểu thức chưa được hỗ trợ có thể che quan hệ.

`summary.serialized_characters` đo số ký tự của mỗi phần JSON, không phải số
token. `token_count` để null khi chưa đo bằng tokenizer của model thực tế.
Skill, hội thoại, source mở thêm, CL, phần dành cho suy luận/đầu ra và các kết
quả công cụ lặp đều cần ngân sách. Không khẳng định đạt giới hạn 200k chỉ dựa
vào các kích thước này.

Lệnh kiểm tra dữ liệu đầu vào và nội dung gói có bị đổi hay không. Source hoặc
report đổi thì refresh review giữ nguyên cấu hình, rồi tạo gói mới. Không sửa
danh sách ứng viên sinh tự động để khớp câu trả lời mong muốn. Kiểm dữ liệu
còn đúng và đủ quyết định không chứng minh đã tìm được mọi thay đổi quan trọng.
