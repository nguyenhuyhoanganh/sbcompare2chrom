# Phân tích thay đổi WebUI

MUST đọc tài liệu này khi phân tích route, control, pref hoặc điều kiện
hiển thị WebUI. Chọn một màn hình không loại trừ các thành phần mà nó phụ
thuộc trong thư mục hay kind khác.

Dùng tài liệu này cho khai báo route, control, preference và điều kiện hiển thị.
Mục tiêu là **giải thích một thay đổi trong UI hoặc trong hành vi của nó**,
không phải liệt kê riêng từng element HTML hay từng feature flag đã đổi.

## Vị trí source

Với settings trên desktop, bắt đầu từ các file dưới đây nếu chúng tồn tại ở hai
ref đang so. Các screen WebUI khác có thể dùng handler và cấu trúc route khác.

| Source | Cần xem gì |
|---|---|
| `chrome/browser/resources/settings/route.ts` | Tên route, đường dẫn, route cha, và các điều kiện xung quanh |
| Template và TypeScript trong `chrome/browser/resources/settings/` | Control, binding tới preference, handler sự kiện, và logic hiển thị |
| C++ trong `chrome/browser/ui/webui/settings/` | Các giá trị cung cấp cho `loadTimeData` và biểu thức đầy đủ của chúng |
| `chrome/browser/resources/settings/page_visibility.ts`, nếu có | Các điều kiện hiển thị trang bổ sung |
| Khai báo, đăng ký và consumer của preference | Danh tính key, giá trị mặc định, giá trị đã lưu, và hành vi migration |
| String resource mà template tham chiếu | Chữ hiển thị thật và bản dịch, không chỉ key của resource |

Một đường dẫn trong bảng này là **điểm bắt đầu**, không phải đảm bảo rằng file
đó đã được tải về hoặc đã được parse. Dùng đúng source root theo version trong
index, hoặc dùng `review source`. Cache thiếu file cần thiết thì tải đúng đường
dẫn đó ở đúng ref, hoặc ghi lại bằng chứng còn thiếu.

## Xác định điều kiện hiển thị và hành vi

Lần theo từng tham chiếu liên quan:

```text
route hoặc control
  -> điều kiện hoặc key loadTimeData
  -> biểu thức trong handler
  -> giá trị feature/cấu hình và phần hiện thực bị ảnh hưởng
```

Đọc **mọi** thành phần của một biểu thức. Giá trị mặc định của một feature không
quyết định được một điều kiện còn phụ thuộc vào trạng thái profile, platform,
hay một giá trị khác. So cả hai version: một số khai báo này có thể không đổi
trong khi consumer của chúng đổi.

Với một control có binding tới preference, xem bên đọc và bên ghi của key đó.
Cùng một binding có thể giúp nhận ra một control đã chuyển chỗ, nhưng nhiều
control có thể dùng chung một preference. Hãy xác nhận quan hệ, đừng gộp mọi
control chỉ vì chúng dùng chung một key.

Khi câu hỏi là **UI làm gì**, phải xem handler sự kiện và code hiện thực khác.
Riêng việc template có mặt không xác lập hành vi hay việc trang thật sự hiển thị.
Với các file đặc thù platform, hãy kiểm phạm vi build thay vì mặc định mọi finding
đều liên quan tới Windows.

## Chọn phạm vi cho một event

| Thay đổi quan sát được | Điều gì làm nên một mục báo cáo có ích |
|---|---|
| Một control đổi loại, đổi giá trị, hoặc đổi nhãn | Giải thích tương tác before/after và setting bị ảnh hưởng |
| Một route xuất hiện, biến mất, hoặc chuyển chỗ | Giải thích điều hướng, các điều kiện, và route thay thế nếu có |
| Nhiều trang, control và consumer cùng đổi | Giải thích thay đổi capability chung và bằng chứng nối các phần lại |

Gom theo **thay đổi được bằng chứng chống đỡ**, không gom theo tên màn hình,
tiền tố, flag chung hay score. Một màn hình có thể chứa nhiều thay đổi không
liên quan. Một thay đổi liên quan có thể trải nhiều màn hình và nhiều file. Thay
đổi không có feature flag cũng cần phân tích.

Với một cuộc migration được đề xuất, phải xác định hành vi cũ, hành vi mới, và
source hoặc lịch sử nối hai cái đó. **Hai version ở hai đầu không xác lập thời
điểm người dùng lần đầu thấy UI mới.** Chỉ nêu mốc thời gian đó khi có lịch sử
hoặc bằng chứng triển khai tương ứng.

## Coverage và kiểm chứng

Các extractor WebUI đọc những khai báo route, control và handler **được hỗ trợ**
trong các file mà lần chạy đã chọn. Đây không phải phân tích TypeScript đầy đủ,
cũng không phải kiểm thử UI đã render. Dùng coverage thật của báo cáo; **đừng**
giả định số màn hình hay danh sách file của một lần chạy trước còn đúng.

`cluster.py` tạo ra các nhóm ứng viên. Review index cũng ghi lại các quan hệ khai
báo đi qua cả những fact không đổi. Cả hai giúp **truy xuất bằng chứng**; agent
vẫn phải tự xác minh item nào thuộc về một event.

Trước khi kết luận một trang hoặc một control đã bị xoá, hãy kiểm các vị trí thay
thế, toàn bộ điều kiện hiển thị, và các consumer. Nếu chưa kiểm hết, báo cáo thay
đổi quan sát được trên source cùng câu hỏi còn chưa giải quyết.
