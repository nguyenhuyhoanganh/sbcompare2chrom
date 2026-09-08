# Giới hạn của kết luận rút ra từ source

MUST đọc tài liệu này trước khi kết luận từ source. Với mỗi giới hạn áp
dụng dưới đây, thực hiện bước kiểm tra hoặc giữ lại phần chưa chắc.

Dùng tài liệu này khi diễn giải sự vắng mặt, điều kiện platform, tính sẵn dùng
của API, hoặc tính tương thích. Các phép kiểm dưới đây áp dụng cho **mọi**
identifier. So sánh source xác lập khác biệt giữa hai version; trạng thái triển
khai và lỗi thật cần bằng chứng khác.

## 1. Flag bị xoá so với capability bị xoá

Một feature flag bị xoá có thể nghĩa là nhánh bật của nó được giữ lại, phần hiện
thực bị xoá, hoặc một điều kiện khác đã thay thế nó. **Giá trị mặc định cuối
cùng được ghi nhận không phân biệt được ba khả năng đó.**

Đọc khai báo flag cũ, cả hai version của các consumer của nó, và khai báo thay
thế nếu có. Kiểm tra các cấu hình hoặc code vẫn còn tham chiếu flag đã xoá. Chỉ
kết luận hành vi được giữ hay bị xoá khi phần hiện thực chống đỡ được kết luận
đó. **Đừng** suy ra rollout vĩnh viễn từ việc flag bị xoá.

## 2. Khai báo bị xoá so với khai báo được chuyển chỗ

Một khai báo vắng mặt khỏi một file có thể đang tồn tại ở chỗ khác trong version
đích. Tìm key, định danh trong source, giá trị đã lưu, và các consumer liên quan
**ở đúng ref đích**. File bị đổi tên thì phải lần theo cả tên cũ.

Hai khai báo tên gần giống nhau không nhất thiết là thay thế cho nhau. Xác nhận
quan hệ đó qua cách dùng trong source, qua binding, hoặc qua lịch sử commit.
Flag chung, đường dẫn chung và cluster của công cụ chỉ ra **quan hệ cần điều
tra**; chúng không xác lập một cuộc migration hay thời điểm của nó.

Tìm trong một cache không đầy đủ **không** xác lập được sự vắng mặt trên toàn
cây. Không có file cần thiết thì ghi lại phạm vi chưa giải quyết được, đừng gọi
capability là đã bị xoá. Xem [history.md](history.md) để tìm source theo đúng ref.

## 3. Thay đổi cú pháp so với thay đổi khai báo

Một thay đổi ở macro hoặc ở cú pháp khai báo có thể giữ nguyên **ý nghĩa** được
trích xuất. Ví dụ: một dạng macro cung cấp chuỗi tên feature tường minh, còn
dạng kia suy nó ra từ định danh C++.

So tên, giá trị mặc định và điều kiện thu được, chứ không so nguyên văn source.
Parser chuẩn hoá các dạng nó hỗ trợ; hãy xem các dạng không được hỗ trợ và xem
phạm vi parser trước khi chấp nhận một tập lớn các mục trông như thêm mới hoặc
xoá.

## 4. Chuỗi dùng cho bên ngoài so với định danh trong source

Định danh C++ và chuỗi mà cấu hình bên ngoài dùng là **hai danh tính khác nhau**.
Một lần chuyển đổi cú pháp có thể làm đổi chuỗi được suy ra ngay cả khi định
danh C++ giữ nguyên.

Kiểm cả `name`/key lẫn `var` ở hai version. Chuỗi đổi thì xem các cấu hình bên
ngoài đang dùng nó. Chỉ định danh C++ đổi thì xem các tham chiếu trong source.
Xác nhận có alias hay xử lý migration không, trước khi khẳng định một consumer
cụ thể bị hỏng.

## 5. Giá trị mặc định theo từng platform

Đọc `platform_state.windows` cho khai báo C++ và Mojo, và trạng thái Windows
được ghi nhận cho Blink. Giá trị mặc định chung có thể khác giá trị theo
platform. Giá trị `conditional` nghĩa là còn điều kiện không thuộc platform chưa
giải được.

Khi cần, xem toàn bộ điều kiện và cấu hình build/runtime của sản phẩm. Giá trị
mặc định trong source **không đo** cấu hình Finch đang chạy. **Đừng** thay thế
bằng giá trị mặc định của platform khác.

## 6. UI được khai báo so với UI hiển thị

Route và control có thể nằm sau các điều kiện riêng. Cả UI cũ lẫn UI mới có thể
cùng tồn tại trong source trong lúc migration mà không phải cả hai đều hiển thị.

Đọc điều kiện của route/template, các giá trị do handler cung cấp, và các phép
kiểm feature liên quan ở **cả hai** version. Có code hiển thị bổ sung thì lần
theo nó. Một route bị xoá là một quan sát trên source, **không** phải bằng chứng
rằng một trang người dùng đang dùng đã biến mất trong lần so sánh này.

Xem [settings-screen.md](settings-screen.md) để biết vị trí source và quan hệ
giữa route, handler, pref và consumer.

## 7. Version chính xác so với số milestone

Một số milestone trần có thể giải ra một bản patch khác ở lần chạy sau. Các bản
patch khác nhau có thể mang hành vi khác nhau.

Ghi lại ref chính xác từ báo cáo. Dùng đúng ref đó cho mọi truy vấn source và
lịch sử. **Đừng** dùng checkout hiện tại hay bản release mới nhất để thay cho
một trong hai phía mà không nói ra.

## 8. Phạm vi so sánh và cấu hình source

Target set, partition, chế độ completeness và các file có sẵn đều ảnh hưởng tới
việc snapshot chứa fact nào. So các input tương thích với nhau và đọc các warning
về coverage. `wide` mở rộng phạm vi **file được hỗ trợ**, không phải toàn bộ code
hay toàn bộ cú pháp.

Thêm `--refresh` **không** sửa được một lựa chọn phạm vi sai. Giữ nguyên target
set và partition đã định khi dựng lại một lần so sánh. Khi refresh review sau
một lần tra CL, giữ nguyên cache đã lưu và repo Git tuỳ chọn như mô tả trong
[investigation.md](investigation.md).

Cache có thể chứa file lấy về cho các phân tích khác. Vì vậy danh mục source có
thể gồm nhiều file hơn lần quét khai báo ban đầu. Nêu rõ **cả hai phạm vi**.
File tải thêm bằng `review source --fetch` là bằng chứng bổ sung, không phải sự
mở rộng tự động của danh mục ban đầu.

## 9. Loại trừ khỏi build không qua điều kiện tiền xử lý thông thường

Các thuộc tính Mojo như `[EnableIf=is_android]` có thể giới hạn một khai báo.
Một member cũng có thể kế thừa điều kiện từ khai báo chứa nó. Công cụ ghi các
điều kiện nó hỗ trợ vào `platform_state`.

Luật build có thể loại trừ file mà **không** có điều kiện nào viết trong file.
Đường dẫn đặc thù platform là bằng chứng có ích, nhưng phải xem **mọi** vị trí
khai báo và các luật build liên quan trước khi loại một key. Một khai báo trùng
nằm ngoài thư mục đó vẫn có thể liên quan tới Windows.

Score bằng 0 phản ánh **cách classifier diễn giải** platform, không phải lý do
để bỏ qua item mà không kiểm lại cách diễn giải đó. Một thay đổi chỉ dành cho
Android có thể được đánh dấu `out_of_scope` cho một đợt rà soát Windows kèm lý
do. Nó không tự động là lỗi của parser chỉ vì nó xuất hiện trong input.

## 10. Contract IPC đổi so với lỗi thật

Việc hai bên dùng binding sinh ra từ **cùng một** revision Chromium không phải
bằng chứng về lỗi khi chạy lệch version. Xác định consumer thật trước khi mô tả
tác động của một thay đổi signature hay layout của Mojo.

Kiểm: có phần hiện thực hay caller nào được duy trì ngoài cây upstream không; có
thành phần nào ship độc lập không; và các process giao tiếp với nhau có thể dùng
hai version interface khác nhau không.

Báo cáo thay đổi contract quan sát được ngay cả khi chưa biết tác động tới sản
phẩm. Chỉ nói build hỏng hay không tương thích lúc chạy khi có bằng chứng về các
consumer và các version đó. Với enum, xem tính mở rộng, giá trị mặc định và code
xử lý được sinh ra trước khi mô tả hành vi với giá trị không biết.

## 11. Khai báo API so với tính sẵn dùng của API

Một member IDL có thể mang điều kiện runtime riêng, hoặc kế thừa điều kiện từ
interface chứa nó. Exposure, yêu cầu secure context, điều kiện build và cấu hình
runtime đều có thể đặt thêm hạn chế.

`web_api_added_live` nghĩa là bộ phân loại đánh giá các điều kiện đã ghi nhận
là cho phép gọi API. Nó **không** chứng minh API sẵn dùng ở mọi nơi.
`web_api_added_gated` mô tả một hạn chế mặc định được ghi nhận; nó **không**
chứng minh mọi ngữ cảnh override hay origin trial đều không dùng được API.

Xem khai báo của cả interface lẫn member, các runtime feature liên quan, và các
consumer. Phân biệt ba mức: capability mới được khai báo, mặc định bật trong
source, và tính sẵn dùng đã xác minh trong bản build của user.

## 12. Switch bị xoá và preference đã lưu

Khai báo switch biến mất thì xem phần parse tham số, các alias, và các cấu hình
khởi chạy vẫn còn truyền nó. Một khai báo bị xoá **không** tự nó chứng minh lệnh
khởi chạy nào đã triển khai bị mất tác dụng.

Preference biến mất thì tìm key đã lưu, chỗ đăng ký, bên đọc, bên ghi, và code
migration. Dữ liệu có thể vẫn nằm trên đĩa dù code mới không đọc key đó nữa.
**Đừng** suy ra mất dữ liệu, reset, hay có migration chỉ từ nhãn bucket hoặc từ
một lần đổi tên key.

Quét khai báo rộng hơn có thể tìm ra một key đã chuyển chỗ. Nhưng muốn kết luận
về hành vi với dữ liệu đã lưu thì vẫn phải đọc phần hiện thực liên quan.

## 13. Ordinal ngầm của Mojo và giới hạn so sánh

Parser ghi vị trí theo thứ tự xuất hiện **chỉ để so sánh bên trong** các khai báo
được đánh dấu `[Stable]`. Ordinal tường minh được so riêng. Việc gỡ `[Stable]`
rồi mất vị trí được ghi nhận **không giống** việc một member đổi vị trí giữa hai
vị trí đã ghi nhận.

Với một interface không `[Stable]` mà có consumer được duy trì riêng, hãy đọc
diff thô của nó và các định danh message/field được sinh ra. Một member được chèn
thêm có thể cần điều tra ngay cả khi báo cáo dựa trên khai báo không sinh ra
finding nào về ordinal.

**Đừng** coi việc không có signal đó là bằng chứng về tính tương thích. Xác định
sản phẩm phải hỗ trợ những tổ hợp version nào.
