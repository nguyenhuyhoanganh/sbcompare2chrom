# Diễn giải signal, bucket và score

MUST đọc tài liệu này trước khi diễn giải nhãn phân loại. Những nhãn đó
MUST NOT thay thế bằng chứng trước/sau hoặc ưu tiên user đã xác nhận.

**signal** là nhãn do code so sánh gán. Nó mô tả một thay đổi khai báo được ghi
nhận, hoặc cách classifier diễn giải thay đổi đó. Nó **không** phải phép đo về
hành vi sản phẩm, về triển khai, hay về tác động tới người dùng. Đọc `before`,
`after` và `deltas` trước, rồi mới kiểm chứng source và consumer liên quan.

Tài liệu này liệt kê **định danh signal**, không phải tên tính năng để đi tìm.
Một finding không mang signal nào vẫn cần phân tích. Các thay đổi source không
được parse thành finding phải xem riêng.

Cột "Cần thêm bằng chứng gì" là việc phải làm **trước khi** kết luận từ signal
đó, không phải việc tuỳ chọn.

## Khai báo feature và điều kiện

| Signal | Ghi nhận thay đổi / phân loại gì | Cần thêm bằng chứng gì |
|---|---|---|
| `enabled_by_default` / `disabled_by_default` | Giá trị mặc định của feature đã đổi trên Windows | Override lúc chạy và đường code bị ảnh hưởng |
| `default_flip_on` / `default_flip_off` | Giá trị mặc định chung của khai báo đã đổi | Nhánh Windows có đổi không; muốn nói đây là một lần revert thì cần lịch sử |
| `new_feature_on_by_default` | Feature mới có mặc định bật trong source trên Windows | Consumer và mức sẵn dùng thật trong sản phẩm |
| `flag_retired_on` / `flag_retired_off` | Khai báo feature biến mất, sau khi mặc định là bật/tắt | Phần hiện thực được giữ lại, bị xoá, hay bị thay thế |
| `feature_deleted` | Khai báo feature biến mất và không xác định được trạng thái trước đó | Khai báo cũ, khai báo thay thế, và các consumer |
| `feature_string_renamed` | Chuỗi tên feature dùng cho bên ngoài đã đổi | Các config đang dùng chuỗi cũ, và có xử lý tương thích nào không |
| `feature_symbol_renamed` | Định danh C++ đã đổi trong khi chuỗi tên feature giữ nguyên | Code đang tham chiếu định danh cũ |
| `build_gate_changed` | Điều kiện build được ghi nhận đã đổi | Cấu hình build liên quan và **mọi** vị trí khai báo |
| `declaration_moved` | Khai báo được khớp ở một đường dẫn khác | Consumer và các điều kiện xung quanh; riêng việc di chuyển không xác lập hành vi giữ nguyên |

`platform_state.windows` là **cách công cụ diễn giải** các điều kiện trong
source. Giá trị `conditional` nghĩa là các điều kiện đó không giải hết được cho
lần so sánh này. Một mặc định bật, hay một flag bị xoá, đều không chứng minh
cấu hình Finch thật hay hành vi sản phẩm vĩnh viễn.

## Khai báo Blink runtime và Web IDL

| Signal | Ghi nhận thay đổi / phân loại gì | Cần thêm bằng chứng gì |
|---|---|---|
| `web_api_shipped` | Khai báo runtime được thêm ở trạng thái stable, hoặc chuyển sang stable, trên platform được ghi nhận | Khai báo API, mức exposure, các điều kiện còn lại, và bằng chứng triển khai |
| `web_api_unshipped` | Trạng thái runtime chuyển từ stable xuống mức thấp hơn | Consumer, các đường bật khác, và lịch sử |
| `killswitch_retired` | Khai báo runtime biến mất sau khi đã ở trạng thái stable | Khai báo API và phần hiện thực còn lại hay không |
| `experimental_dropped` | Khai báo runtime biến mất và trạng thái được ghi nhận ở phiên bản trước không phải stable | Mức exposure thật trước đó; phần hiện thực bị xoá hay bị thay thế |
| `web_api_added_live` | Bộ phân loại đánh giá khai báo IDL mới là có thể gọi được theo các điều kiện đã ghi nhận | Điều kiện của interface, exposure, yêu cầu secure context, và cấu hình runtime thật |
| `web_api_added_gated` | Classifier coi điều kiện runtime ghi nhận của khai báo IDL mới là không bật mặc định | Các đường bật khác; nó **không** chứng minh không ngữ cảnh nào dùng được |
| `web_api_added` | Khai báo API/runtime được thêm nhưng chưa kết luận được về tính sẵn dùng ở stable | Xem `kind` của finding, khai báo runtime, và các điều kiện còn thiếu |
| `web_api_removed` | Khai báo IDL biến mất; bộ phân loại không xác định rằng các điều kiện trước đó đã ngăn việc gọi API | Coverage về sự vắng mặt, khai báo thay thế, consumer bị ảnh hưởng; khả năng sử dụng API có thể vẫn chưa xác định |
| `web_api_removed_gated` | Khai báo IDL biến mất; bộ phân loại đánh giá điều kiện runtime đã ghi nhận trước đó là ngăn việc gọi API | Có ngữ cảnh liên quan nào từng bật nó không |
| `web_api_overload_removed` | Một hoặc nhiều signature của method đã trích xuất biến mất | Các lời gọi dùng những signature đó, và khai báo thay thế |
| `web_api_overload_added` | Có signature được thêm mà classifier không phát hiện xung đột số lượng đối số | Chuyển kiểu, cách chọn overload, và các caller hiện có |
| `web_api_overload_shadowed` | Signature mới có thể làm đổi cách chọn overload theo số đối số, kể cả các đối số dư trước đây | Toàn bộ luật overload và các lời gọi tiêu biểu |
| `web_api_signature_change` | Signature của một member hoặc kiểu của member đã đổi | Caller, luật chuyển kiểu, và điều kiện runtime |
| `web_api_shape_changed` | Quan hệ kế thừa của interface, loại khai báo, hoặc danh sách giá trị enum đã đổi | Các member kế thừa và các consumer |
| `web_api_exposure_changed` | Extended attribute hoặc điều kiện runtime ghi nhận của member đã đổi | Toàn bộ điều kiện trên **cả** member lẫn interface |
| `web_api_status_moved` | Trạng thái runtime đổi mà không vào hoặc ra khỏi stable | Các ngữ cảnh mà những trạng thái đó hoặc override áp dụng |
| `origin_trial_change` | Cấu hình origin trial đã đổi | Origin áp dụng, platform, token, và các yêu cầu runtime khác |
| `runtime_flag_rewired` | Dependency, liên kết base-feature, hoặc metadata runtime khác đã đổi | So các trường đã đổi và code đang dùng chúng |

Trạng thái stable **không đủ** để kết luận mọi trang web đều gọi được API. Trạng
thái không stable **không** là bằng chứng rằng mọi ngữ cảnh đều không gọi được.
Một member mới có thể mang điều kiện kế thừa từ interface chứa nó.
`base_feature: none` nghĩa là không có liên kết base-feature nào được sinh ra;
nó **không** xác lập rằng một feature C++ khai báo độc lập đã bị xoá.

## Khai báo Mojo IPC

IPC là giao tiếp giữa các process. Các signal dưới đây mô tả **khai báo
interface**, không mô tả lỗi giao tiếp đã quan sát được.

| Signal | Ghi nhận thay đổi / phân loại gì | Cần thêm bằng chứng gì |
|---|---|---|
| `ipc_signature_change` | Tham số hoặc phần trả về của method đã đổi | Caller, phần hiện thực, và hai bên có dùng binding sinh ra khớp nhau không |
| `ipc_ordinal_changed` | Ordinal tường minh của method, hoặc vị trí so sánh trong khai báo `[Stable]`, đã đổi | Định danh message được sinh ra, và các tổ hợp version liên quan |
| `ipc_shape_changed` | Kiểu/ordinal của field, vị trí so sánh trong khai báo `[Stable]`, hoặc loại container đã đổi | Phần serialization được sinh ra, và các consumer |
| `ipc_enum_changed` | Giá trị enum hoặc annotation ghi nhận của chúng đã đổi | Tính mở rộng, giá trị mặc định, và cách xử lý giá trị không biết |
| `ipc_removed` | Một khai báo Mojo biến mất khỏi các fact đang so | Coverage về sự vắng mặt, khai báo thay thế, và consumer |
| `ipc_stability_changed` | Annotation `[Stable]` ghi nhận đã đổi | Yêu cầu tương thích; riêng nó **không** mô tả byte trên đường truyền đã đổi |
| `ipc_field_annotated` | Giá trị mặc định của field hoặc annotation version đã đổi | Giá trị mặc định được sinh ra, và hành vi tương thích với các peer liên quan |

Với enum, xem các thuộc tính như `[Extensible]` và `[Default]` trước khi mô tả
cách xử lý giá trị không biết. **Đừng** giả định mọi peer đều từ chối giá trị lạ,
hay mọi thay đổi signature đều gây lỗi lúc chạy. Xem mục 10 và 13 của
[traps.md](traps.md).

## Pref, switch, param và WebUI

| Signal | Ghi nhận thay đổi / phân loại gì | Cần thêm bằng chứng gì |
|---|---|---|
| `pref_renamed` / `switch_renamed` | Hai mục được ghép cặp như một lần đổi tên key đã lưu hoặc đổi tên switch | Xác nhận quan hệ đó, các consumer, và phần xử lý tương thích |
| `pref_symbol_renamed` / `switch_symbol_renamed` | Định danh trong source đã đổi trong khi chuỗi giữ nguyên | Các chỗ trong source đang dùng định danh cũ |
| `pref_left_scan` / `switch_left_scan` | Key không còn trong những file lần chạy này đọc | Tìm phần di chuyển, thay thế và migration trong source đủ đầy đủ |
| `param_removed` | Khai báo feature param biến mất | Bên đọc, khai báo thay thế, và cấu hình bên ngoài |
| `param_rewired` | Kiểu ghi nhận hoặc feature sở hữu param đã đổi | Bên đọc, và các điều kiện của feature sở hữu mới |
| `param_default_changed` | Giá trị mặc định của param đã đổi | Consumer và các override |
| `ui_page_added` / `ui_page_removed` | Khai báo route xuất hiện hoặc biến mất | Điều kiện của route, route thay thế, và hành vi của trang |
| `ui_page_regated` | Điều kiện ghi nhận của route đã đổi | Toàn bộ biểu thức, và giá trị do handler C++ cung cấp |
| `ui_page_moved` | Đường dẫn hoặc route cha đã đổi | Các consumer điều hướng, và có redirect nào không |
| `ui_control_added` / `ui_control_removed` | Một control đã trích xuất xuất hiện hoặc biến mất | Control thay thế, điều kiện trong template, và phần xử lý sự kiện |
| `ui_control_type_changed` | Loại element đã đổi | Hành vi của control và cách biểu diễn giá trị |
| `ui_control_repointed` | Control gắn sang một pref khác | Cả hai key, bên đọc, và migration |
| `ui_control_relabelled` | Key của label resource đã đổi | Chuỗi đã dịch thật; đổi key **không** chứng minh chữ hiển thị đã đổi |
| `ui_gate_added` / `ui_gate_removed` / `ui_gate_changed` | Biểu thức hiển thị ghi nhận của handler đã đổi | Mọi thành phần trong biểu thức, và code dùng giá trị của nó |
| `flag_expiring` / `flag_expiry_moved` | Metadata hạn xoá của mục flag được đặt hoặc đổi | Milestone chính xác, và việc xoá đã xảy ra chưa; **lên lịch không phải đã xoá** |

## Bucket và score

Bucket dùng để sắp xếp báo cáo thô. Chúng **không** phải tiêu đề cho báo cáo
event cuối cùng và không chứng minh hậu quả tới sản phẩm.

| Bucket | Dùng nó thế nào trong lúc phân tích |
|---|---|
| Compatibility break | Xem xét các contract có thể đã đổi và xác định consumer thật sự bị ảnh hưởng |
| Behaviour change | Xác định khai báo đã đổi có làm đổi hành vi trong các điều kiện liên quan hay không |
| New declarations | Điều tra khả năng có capability mới và điều kiện của nó; riêng một khai báo không chứng minh nó đã sẵn dùng |
| Scheduled | Kiểm tra công việc tương lai ghi trong metadata; phân biệt kế hoạch với việc đã hoàn thành |
| Upstream cleanup | Xác minh thay đổi là không đổi hành vi, bị loại khỏi platform, hay dựa trên bằng chứng vắng mặt không đủ |

Signal quyết định (leading signal) đặt ra severity và bucket của finding. Không
có signal thì classifier dùng `kind` và hướng thay đổi. Score bằng severity,
hoặc bằng 0 khi Chromium loại khai báo khỏi bản build Windows ở cả hai phía.

**Các con số này là mức ưu tiên**, không phải xác suất, không phải mức độ tin
cậy, và không phải tác động đo được tới người dùng. Đọc `reasons` để biết vì sao
score bằng 0, hoặc vì sao dòng đó bị gắn cờ.

`unconfirmed` tách biệt với bucket và score, và không bao giờ làm thay đổi
score. Cờ này nghĩa là kết luận của finding dựa vào việc không thấy một khai báo
ở một phía, nhưng lần chạy chưa đủ căn cứ để khẳng định: ở phiên bản mới, lần
chạy đọc chưa tới 95% số file chứa loại khai báo đó trong toàn bộ cây, hoặc
phía cung cấp bằng chứng bị thiếu target hay có file không parse được. Cờ này
không phải xác suất finding sai. Pref hoặc switch bị gỡ mà có cờ này được xếp
vào Upstream cleanup; các finding có cờ còn lại giữ nguyên bucket. Coverage của
lần chạy `--partition` vẫn tính trên toàn bộ cây, nên removal của những loại
file mà partition chỉ đọc trong thư mục gốc của nó sẽ bị gắn cờ; finding có
score 0 theo quy tắc build Windows thì không được xét. Quét rộng hơn cải thiện
coverage theo file, nhưng không xác lập rằng parser đã đọc hết ngữ pháp hay đã
phủ hết hành vi.

**Đừng sửa các hằng số xếp hạng** trong lúc phân tích một đợt nâng version của
user. Không đồng ý với nhãn của classifier thì giải thích bằng bằng chứng thật.
