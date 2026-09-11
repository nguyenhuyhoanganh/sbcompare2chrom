# 5. Cơ chế so sánh, chấm điểm và phân loại bucket

Tài liệu này giải thích vì sao một thay đổi được 80 điểm còn thay đổi khác được 20 điểm, và vì sao một finding lại được giao cho team này chứ không phải team kia.

## Bốn khái niệm không được trộn với nhau

Đây là chỗ hay bị nhầm nhất khi đọc báo cáo. Bốn từ dưới đây nghe gần giống nhau nhưng trả lời bốn câu hỏi hoàn toàn khác:

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| `signal` | Chính xác thì chuyện gì đã xảy ra? |
| `severity` | Nếu bằng chứng đầy đủ, loại thay đổi này đáng được xem sớm đến đâu? |
| `score` | Sau khi xét bản build Windows và độ đầy đủ của lần đọc, thứ tự ưu tiên cuối cùng là bao nhiêu? |
| `bucket` | Đây là contract bị phá, hành vi thay đổi, khai báo mới, lịch xoá, hay chỉ là dọn dẹp? |

Ba điều `score` **không** phải: không phải xác suất, không phải công sức, không phải mức chắc chắn Samsung có bug.

Một finding 80 điểm nghĩa là *"theo rule của công cụ, đây là loại thay đổi upstream cần được review trước"*. Nó không có nghĩa *"80% khả năng Samsung Browser bị lỗi"*.

## Toàn bộ luồng so sánh

```text
Fact bên cũ + Fact bên mới
        │
        ▼
ghép theo uid = kind:key
        │
        ├── chỉ có ở bên mới → added
        ├── chỉ có ở bên cũ  → removed
        └── có ở cả hai      → so các thuộc tính có ý nghĩa
                                  │
                                  └── khác nhau → modified + deltas
        │
        ▼
lượt ghép bổ sung: đổi tên / WebUI control chuyển pref
        │
        ▼
sinh ra một hoặc nhiều signal
        │
        ▼
chọn leading signal
        │
        ├── quyết định severity
        ├── quyết định bucket ban đầu
        │
        ▼
bước chấm điểm
  xét bản build Windows + lỗ hổng về coverage/acquisition
        │
        ▼
Finding(score, bucket, reasons)
```

Sáu bước dưới đây đi qua từng chặng.

## Bước 1 — Chỉ so những thuộc tính có ý nghĩa

Mỗi `kind` có danh sách thuộc tính được phép so riêng. Bốn ví dụ:

- `base_feature`: giá trị mặc định, trạng thái trên Windows và theo platform, điều kiện, biến C++;
- `mojo_method`: signature, params, response, attrs, ordinal, position trong interface stable, platform state;
- `webui_control`: loại control, pref, nhãn, điều kiện build/platform;
- `flag_entry`: chỉ đúng một thứ — milestone hết hạn.

Những trường không ảnh hưởng tới ngữ nghĩa bị loại khỏi việc so sánh. Nhờ vậy, ba tình huống sau không tạo thêm dòng mơ hồ nào trong báo cáo: `BASE_FEATURE` đổi dạng macro, số dòng thay đổi, hoặc `method_count` đổi chỉ vì một method đã được thêm/bớt và bản thân method đó đã có finding riêng.

Còn một chuẩn hoá nhỏ nhưng hiệu quả: trạng thái platform `compiled` được coi là tương đương với "không có guard nào". Nhờ vậy, việc Chromium bỏ một `#if !IS_ANDROID` khỏi một khai báo vốn vẫn có mặt trên Windows sẽ không sinh ra nhiễu.

## Bước 2 — Ba hướng cơ bản và hai lượt ghép bổ sung

### Added, removed, modified

- `added`: UID chỉ có ở snapshot mới.
- `removed`: UID chỉ có ở snapshot cũ.
- `modified`: UID có ở cả hai, nhưng các thuộc tính có ý nghĩa khác nhau.

### Phát hiện đổi tên

Pref, switch và feature string dùng chính chuỗi bên ngoài làm identity. Khi chuỗi đó đổi, lượt so cơ bản chỉ thấy một `removed` cộng một `added` — hai dòng rời rạc, che mất bản chất.

Công cụ ghép chúng lại nếu biến C++ giữ nguyên:

```text
trước: pref key old.path, var kFoo
sau:   pref key new.path, var kFoo
                     ↓
modified + pref_renamed
```

Hai trường hợp cần phân biệt rõ, vì hậu quả ngược nhau:

| Trường hợp | Hậu quả |
|---|---|
| Chuỗi đổi, symbol giữ nguyên | Cấu hình và dữ liệu bên ngoài có thể mất tác dụng — build vẫn qua |
| Chuỗi giữ nguyên, symbol đổi | Dữ liệu bên ngoài an toàn, nhưng code C++ của Samsung có thể fail build |

### Phát hiện WebUI control chuyển pref

Pref là một phần trong identity của control. Vì vậy, khi một control vẫn ở nguyên trang và giữ nguyên element id nhưng chuyển sang ghi vào một pref khác, lượt so cơ bản cũng chỉ thấy một `removed` cộng một `added`.

Công cụ ghép lại theo bộ ba `(screen, page, element_id hoặc label)`, và sinh ra signal `ui_control_repointed`.

## Bước 3 — Signal được sinh ra từ hướng thay đổi và delta

`signal` là kết quả của một rule cố định, không phải một nhận xét tự do. Một `Change` có thể mang nhiều signal cùng lúc:

```text
base_feature modified
deltas:
  platform_state: disabled → enabled
  var: kOld → kNew
signals:
  enabled_by_default
  feature_symbol_renamed
```

`leading signal` là signal có severity cao nhất trong số đó. Nếu hai signal bằng điểm, công cụ chọn theo thứ tự tên, để đầu ra không phụ thuộc thứ tự xử lý.

### Một chi tiết quan trọng về cách tính severity

Severity được lấy **đúng bằng** severity của leading signal. Bảng điểm nền theo `kind` + hướng thay đổi chỉ được dùng khi một `Change` không có signal nào.

Công cụ **không** lấy `max(điểm nền, điểm của signal)`. Lý do đến từ một lỗi thật đã gặp: điểm nền thô của `mojo_method modified` từng đẩy một thay đổi thuộc tính Mojo hoàn toàn bình thường lên ngang hàng với một thay đổi signature phá vỡ ABI.

## Bảng điểm nền, dùng khi không có signal nào

| Kind | Added | Removed | Modified |
|---|---:|---:|---:|
| `base_feature` | 20 | 30 | 45 |
| `feature_param` | 15 | 35 | 35 |
| `blink_runtime_feature` | 25 | 20 | 40 |
| `idl_interface` | 30 | 70 | 40 |
| `idl_member` | 25 | 60 | 45 |
| `mojo_interface` | 20 | 70 | 40 |
| `mojo_method` | 20 | 70 | 75 |
| `mojo_struct` | 20 | 70 | 60 |
| `mojo_field` | 20 | 70 | 60 |
| `mojo_enum` | 20 | 65 | 45 |
| `switch` | 10 | 30 | 40 |
| `pref` | 10 | 35 | 45 |
| `flag_entry` | 5 | 30 | 15 |
| `webui_route` | 40 | 55 | 45 |
| `webui_control` | 25 | 35 | 30 |
| `webui_gate` | 25 | 40 | 45 |

Bảng này là phương án dự phòng, để không đánh rơi một `Change` lạ chưa có rule. Mọi tình huống thật sự quan trọng với sản phẩm đều nên có một signal cụ thể của riêng nó.

## Bảng đầy đủ 60 signal

Năm bảng dưới đây liệt kê toàn bộ signal, kèm severity, bucket và cách đọc. Đây là phần tra cứu — khi mở một finding và thấy một tên signal lạ, tìm nó ở đây.

### Vòng đời feature và trạng thái mặc định

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `enabled_by_default` | 75 | Behaviour change | Trạng thái trên Windows chuyển sang BẬT |
| `disabled_by_default` | 60 | Behaviour change | Trạng thái trên Windows chuyển sang TẮT |
| `default_flip_on` | 60 | Behaviour change | Khai báo mặc định chuyển sang BẬT |
| `default_flip_off` | 50 | Behaviour change | Khai báo mặc định chuyển sang TẮT |
| `feature_deleted` | 65 | Behaviour change | Feature bị xoá, nhưng không đọc được trạng thái trước đó của nó |
| `flag_retired_on` | 35 | Upstream cleanup | Feature đã ship; flag bị dọn nên hành vi BẬT trở thành cố định |
| `flag_retired_off` | 30 | Upstream cleanup | Feature chưa ship; cả flag lẫn code bị bỏ, không bật lại được nữa |
| `new_feature_on_by_default` | 55 | Behaviour change | Feature mới xuất hiện và BẬT ngay |
| `feature_string_renamed` | 75 | Compatibility break | Tên dùng cho Finch và `--enable-features` đã đổi; cấu hình cũ **im lặng** mất tác dụng |
| `feature_symbol_renamed` | 60 | Compatibility break | C++ symbol đổi; code downstream tham chiếu tới nó có thể không compile được |

Vì sao `flag_retired_on/off` **không** được xếp vào Behaviour change: việc bật hoặc tắt đã xảy ra từ một release trước rồi. Release này chỉ dọn đi cái công tắc. Nhưng vẫn phải đi tìm và xoá mọi override còn sót ở bên ngoài repository, vì chúng đã không còn tác dụng.

### Web Platform và Web IDL

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `web_api_shipped` | 65 | Behaviour change | Blink runtime feature đạt stable trên Windows |
| `web_api_unshipped` | 70 | Compatibility break | API bị rút khỏi stable |
| `web_api_removed` | 70 | Compatibility break | Interface hoặc member đang dùng được bị xoá |
| `web_api_added` | 30 | New declarations | API mới, công cụ chưa xác định được gate đang mở hay đóng |
| `web_api_added_live` | 35 | New declarations | API mới, và trang web có thể gọi ngay |
| `web_api_added_gated` | 20 | New declarations | API mới, nhưng runtime gate còn đóng |
| `web_api_removed_gated` | 30 | Upstream cleanup | API bị xoá khi chưa trang nào tiếp cận được |
| `killswitch_retired` | 35 | Upstream cleanup | Blink flag ở trạng thái stable bị xoá; API trở thành vĩnh viễn |
| `experimental_dropped` | 20 | Upstream cleanup | Runtime flag experimental hoặc test bị bỏ |
| `web_api_signature_change` | 50 | Compatibility break | Signature hoặc loại member đã đổi |
| `web_api_overload_removed` | 60 | Compatibility break | Một danh sách tham số của member bị mất |
| `web_api_overload_added` | 25 | New declarations | Có overload mới, không đụng tới số tham số đã có |
| `web_api_overload_shadowed` | 45 | Behaviour change | Overload mới trùng số tham số với overload cũ; lời gọi có thể được phân giải sang hàm khác |
| `web_api_exposure_changed` | 45 | Behaviour change | `Exposed`, extended attribute hoặc runtime gate đã đổi |
| `web_api_shape_changed` | 45 | Behaviour change | Quan hệ kế thừa hoặc giá trị enum đã đổi |
| `web_api_status_moved` | 25 | Upstream cleanup | Chuyển qua lại giữa test và experimental, nhưng chưa lên stable |
| `origin_trial_change` | 35 | Behaviour change | Tên trial, OS, quyền cho bên thứ ba hoặc quyền truy cập đã đổi |
| `runtime_flag_rewired` | 30 | Upstream cleanup | Base feature, dependency hoặc quyền public/internal đổi, nhưng mức expose trên Windows chưa đổi |

Với Web IDL, `added` và `removed` còn phải hỏi thêm runtime gate. Nếu member có `[RuntimeEnabled=Foo]` và `Foo` đang stable, API được coi là tiếp cận được. Còn nếu chính flag đó chưa được snapshot đọc tới, công cụ dùng signal "chưa kết luận được" thay vì đoán bừa.

### Mojo và IPC

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `ipc_signature_change` | 80 | Compatibility break | Params hoặc response của một Mojo method đã đổi |
| `ipc_removed` | 75 | Compatibility break | Interface, method hoặc khai báo dữ liệu bị xoá |
| `ipc_shape_changed` | 80 | Compatibility break | Kiểu hoặc ordinal của field, position trong container stable, hoặc struct đổi thành union |
| `ipc_ordinal_changed` | 80 | Compatibility break | Ordinal trên wire của method, hoặc position trong container stable, đã đổi |
| `ipc_enum_changed` | 55 | Compatibility break | Giá trị enum đổi; một peer cũ có thể từ chối giá trị lạ |
| `ipc_field_annotated` | 35 | Behaviour change | Giá trị mặc định hoặc `[MinVersion]` của field đã đổi |
| `ipc_stability_changed` | 40 | Behaviour change | `[Stable]` mới xuất hiện, hoặc vừa biến mất |

Một quy tắc phòng nhiễu đáng chú ý: `position` chỉ được coi là bằng chứng ABI khi nó có giá trị ở **cả hai** bên. Nếu `[Stable]` bị bỏ khỏi một interface, `position` của mọi member trong đó cũng biến mất — nhưng công cụ không nhân việc này lên thành hàng chục ABI break riêng lẻ. Thay vào đó, chính container nhận signal `ipc_stability_changed`.

### Pref, switch, param và cấu hình bên ngoài

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `pref_renamed` | 70 | Compatibility break | Giá trị đang lưu ở khoá cũ có thể bị bỏ rơi |
| `switch_renamed` | 60 | Compatibility break | Tham số khởi động hoặc automation cũ mất tác dụng |
| `pref_left_scan` | 35 | Ban đầu là Compatibility break | Không còn thấy pref này; có thể đã bị xoá, cũng có thể chỉ chuyển ra khỏi các file đã đọc |
| `switch_left_scan` | 30 | Ban đầu là Compatibility break | Không còn thấy switch này; có thể đã bị xoá, cũng có thể chỉ chuyển chỗ |
| `pref_symbol_renamed` | 55 | Compatibility break | Pref key giữ nguyên, nhưng hằng C++ đã đổi |
| `switch_symbol_renamed` | 45 | Compatibility break | Chuỗi switch giữ nguyên, nhưng hằng C++ đã đổi |
| `param_default_changed` | 40 | Behaviour change | Giá trị mặc định của một FeatureParam đã đổi |
| `param_removed` | 35 | Compatibility break | Cấu hình nào vẫn tiếp tục đặt param này sẽ im lặng mất tác dụng |
| `param_rewired` | 35 | Compatibility break | Kiểu hoặc feature sở hữu param đã đổi |

Hai signal `pref_left_scan` và `switch_left_scan` được bước chấm điểm chuyển sang Upstream cleanup **và gắn cờ `unconfirmed`** nếu coverage không đủ để xác nhận rằng khai báo thật sự đã bị xoá. Score của chúng vẫn bằng severity.

Ngược lại, một trường hợp đổi tên đã ghép được bằng symbol là bằng chứng mạnh hơn hẳn, nên nó không bị hạ theo rule này.

### WebUI

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `ui_page_removed` | 55 | Behaviour change | Route hoặc trang bị xoá |
| `ui_page_added` | 40 | New declarations | Route hoặc trang mới |
| `ui_page_regated` | 45 | Behaviour change | Guard quyết định trang có hiển thị hay không đã đổi |
| `ui_page_moved` | 30 | Behaviour change | URL hoặc route cha đã đổi |
| `ui_control_type_changed` | 45 | Behaviour change | Loại control đổi, ví dụ dropdown thành toggle |
| `ui_control_repointed` | 50 | Compatibility break | Control vẫn còn đó, nhưng bắt đầu ghi sang một pref khác |
| `ui_control_removed` | 35 | Behaviour change | Control bị xoá khỏi template |
| `ui_control_added` | 25 | New declarations | Control mới |
| `ui_gate_changed` | 45 | Behaviour change | Biểu thức C++ hoặc feature đứng sau một khoá `loadTimeData` đã đổi |
| `ui_gate_removed` | 40 | Behaviour change | Điều kiện hiển thị bị bỏ; phần được guard có thể trở thành luôn hiện, cũng có thể biến mất theo |
| `ui_gate_added` | 25 | New declarations | Có điều kiện hiển thị mới |
| `ui_control_relabelled` | 20 | Upstream cleanup | Khoá i18n của nhãn đã đổi; công cụ chưa đọc chuỗi hiển thị nên chưa biết người dùng có thấy khác không |

### Build, chuyển chỗ và lịch trình

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `build_gate_changed` | 35 | Behaviour change | Khai báo có thể vào hoặc ra khỏi binary Windows |
| `declaration_moved` | 25 | Upstream cleanup | Vẫn là khai báo đó, nhưng đã chuyển sang file khác |
| `flag_expiring` | 45 | Scheduled | Flag dự kiến bị xoá trước hoặc trong vòng hai milestone sau milestone đích |
| `flag_expiry_moved` | 10 | Scheduled | Lịch xoá đổi, nhưng hành vi lúc chạy chưa đổi |

`flag_expiring` có bucket riêng — **Scheduled** — chính vì lý do này: nó nói về một mốc ngày chứ chưa phải một việc đã xảy ra, phần phải xử lý nằm ngoài repository, và người đang phụ thuộc vào flag đó cần kịp lên kế hoạch. Gộp nó vào Upstream cleanup thì sai: Upstream cleanup nói về việc đã xảy ra và hoá ra không quan trọng, còn `flag_expiring` nói về việc **chưa** xảy ra.

## Bước 4 — Score được tính thế nào

Đoạn giả mã sau mô tả cách tính score và bucket:

```text
severity = severity(leading signal)
        hoặc base_severity(kind, direction) nếu không có signal nào

nếu khai báo không được compile vào Windows ở MỌI bên mà nó tồn tại:
    score = 0
    bucket = Upstream cleanup
    dừng lại

score = severity
bucket = bucket(leading signal)

direction_for_absence = added / removed
nếu delta nằm ở tập overload signature:
    mất đi một signature → coi như removed
    chỉ thêm vào         → coi như added

nếu là removed, VÀ (coverage của surface đó ở bản mới < 95%
                    hoặc bản mới thiếu file mục tiêu / có file không parse được):
    unconfirmed = true
    ghi lý do vào reasons
    nếu leading signal là pref_left_scan hoặc switch_left_scan:
        bucket = Upstream cleanup

nếu là added, VÀ bản cũ thiếu file mục tiêu / có file không parse được:
    unconfirmed = true
    ghi lý do vào reasons
    nếu bucket là New declarations:
        bucket = Upstream cleanup

(score không đổi ở cả hai nhánh trên)
```

### Score chỉ có hai giá trị: severity hoặc 0

Score bằng severity, trừ khi khai báo nằm ngoài bản build Windows ở mọi phía; khi đó score bằng 0.

Không có rule cộng điểm kiểu "Samsung có patch trong file này nên +20", vì ChromiumDiff không có dữ liệu về source Samsung trong pipeline lõi. Cộng điểm cho một yếu tố không quan sát được sẽ tạo ra độ chính xác giả.

Độ tin cậy của bằng chứng cũng không làm đổi score. Score và bucket trả lời câu hỏi "nếu thay đổi này là thật thì nó tốn gì". Độ tin cậy của bằng chứng là một câu hỏi khác, và cờ `unconfirmed` trả lời câu đó. Việc tách hai câu hỏi cũng giữ cho giá trị 0 chỉ có một nghĩa: khai báo nằm ngoài bản build Windows.

Hệ quả kiểm chứng được: nếu score khác severity thì `reasons` phải có dòng ghi rằng khai báo nằm ngoài bản build Windows. Nếu không có dòng đó, đây là lỗi của công cụ.

### Rule về bản build Windows

Score chỉ bị đưa về 0 khi khai báo ở trạng thái `not_compiled` tại **mọi bên mà nó tồn tại**. Ba trường hợp:

| Tình huống | Kết quả |
|---|---|
| Chỉ có trên Android, ở cả bản cũ lẫn bản mới | score 0 |
| Có trên Windows ở bản cũ, bị loại khỏi Windows ở bản mới | Giữ nguyên score — chính việc rời khỏi binary là thay đổi cần xem |
| Chưa có ở bản cũ, vào Windows ở bản mới | Giữ nguyên score |

### Rule về coverage

Ngưỡng để xác nhận một khai báo thật sự vắng mặt là **95%**, tính theo surface của từng `kind`:

- feature flags;
- web platform flags;
- web API definitions;
- process-boundary interfaces;
- preference keys and switches;
- flags entries;
- routes, controls, gates.

Điểm cần chú ý: **chỉ removal bị xét theo coverage.**

- Một kết luận `removed` dựa vào coverage của snapshot **mới**: câu "không còn ở bản mới" chỉ đáng tin nếu bản mới đã thật sự được đọc.
- Một kết luận `added` là khai báo mà công cụ quan sát trực tiếp ở bản mới, nên coverage không được áp dụng cho nó. Nó chỉ bị gắn cờ khi bản cũ thiếu file mục tiêu hoặc có file không parse được, vì khi đó công cụ không chứng minh được rằng khai báo này chưa tồn tại ở bản cũ.

Kết quả của rule này là cờ `unconfirmed` và một dòng trong `reasons`. Score không đổi.

Lần chạy có `--partition` cũng đo coverage theo cả cây, không theo thư mục gốc của partition. Ví dụ, `--partition downloads` ở M151 đọc 10 trên 8.366 file ứng viên của cả cây, trong đó có 2 trên 529 file pref và switch, nên pref hoặc switch bị gỡ nằm trong bản build Windows đều mang cờ `unconfirmed`. Log in thêm con số bên trong thư mục gốc của partition: 10 trên 22 file. Trong số các dòng mang cờ, 6 key vẫn còn được khai báo trong cây M151, ở file nằm ngoài partition.

## Bước 5 — Bucket được chọn thế nào

Leading signal quyết định bucket. Nếu không có signal nào, quy tắc dự phòng là:

- `added` → New declarations;
- `removed` → Upstream cleanup;
- `modified` → Behaviour change.

Không có quy tắc dự phòng nào dẫn tới Scheduled hoặc Compatibility break: cả hai đều đòi một signal cụ thể nói ra điều đó.

Ý nghĩa của năm bucket:

### Compatibility break

Một contract nằm bên ngoài binary có thể ngừng hoạt động mà không được compiler hay runtime báo sớm: dữ liệu trong profile, script khởi động, cấu hình Finch, một website đang chạy, hoặc một process ở đầu kia.

Cần đọc cho đúng: đây **không** phải khẳng định Samsung chắc chắn hỏng. Nó nói rằng loại contract này phải được đối chiếu với cách Samsung đang dùng.

### Behaviour change

Bản build Windows sẽ làm hoặc sẽ expose một thứ khác sau khi upgrade. Sẽ có người dùng, website hoặc luồng test quan sát thấy khác đi.

### New declarations

Có một khai báo, API, trang hoặc control tồn tại ở version mới mà version cũ không có.

Việc nó tồn tại **không** tự chứng minh rằng Samsung cần adopt nó, và cũng không chứng minh feature đã được BẬT.

### Scheduled

Upstream đã lên lịch xoá một `chrome://flags` entry, hoặc dời cái lịch đó. Đây là phần **duy nhất** của báo cáo nói về việc chưa xảy ra: đọc nó như danh sách của milestone sau, không phải của milestone này.

### Upstream cleanup

Upstream dọn thứ đã ngã ngũ, chuyển khai báo sang file khác, hoặc khai báo không nằm trong build Windows ở cả hai phía. Không có gì quan sát được thay đổi.

Đây là bucket lớn nhất trong mọi báo cáo và là bucket không cần đọc từng dòng — trừ những dòng mang cờ `unconfirmed`.

### `unconfirmed` không phải bucket thứ sáu

Việc lần chạy này có xác nhận được sự vắng mặt hay không là thuộc tính của **lần chạy**, không phải của thay đổi: cùng một removal có cờ `unconfirmed` trên lần chạy `--partition downloads` và không có cờ trên lần chạy `analysis`. Vì vậy nó là một field trên finding, không phải một bucket.

Pref và switch mang cờ nằm trong Upstream cleanup vì **thiếu bằng chứng**, không phải vì thay đổi ít quan trọng. Ví dụ, `DebuggingFeaturesRequested` nằm ở Upstream cleanup trên lần chạy partition downloads nhưng là Compatibility break trên lần chạy `analysis`, và score ở cả hai lần đều là 35. Các dòng mang cờ khác, ví dụ removal của Mojo hoặc Web API, giữ nguyên bucket. `report.md` dành cho chúng một mục riêng có cột bucket, `report.html` gắn badge cạnh pill bucket kèm bộ lọc *All coverage*, và `summary.unconfirmed` đếm chúng: tại M148 → M151, **0 trên lần chạy `analysis`** và 16 trên lần chạy `--partition downloads`.

## Bước 6 — Những signal phải sửa ở ngoài repository

Phần lớn finding được sửa ngay tại file khai báo mà nó trỏ tới. Chín signal dưới đây thì không: chúng biên dịch bình thường rồi ngừng có tác dụng ngoài thực địa, và chỗ phải sửa là Finch config, script khởi động hoặc automation.

```text
feature_string_renamed
switch_renamed
param_removed
param_rewired
flag_retired_on
flag_retired_off
killswitch_retired
flag_expiring
flag_expiry_moved
```

Công cụ không nhìn thấy bất kỳ nơi nào trong số đó, nên đây là danh sách cần đi kiểm tra chứ không phải danh sách đã hỏng.

### Các cặp ví dụ quan trọng

Bảng này cho thấy vì sao hai signal nghe rất giống nhau lại đòi hai chỗ sửa hoàn toàn khác:

| Signal | Nơi cần sửa |
|---|---|
| `switch_renamed` | Script khởi động bên ngoài phải đổi — build không báo gì |
| `switch_symbol_renamed` | Chuỗi CLI vẫn giữ; chỉ tham chiếu C++ phải đổi — build sẽ báo |
| `feature_string_renamed` | Cấu hình Finch / feature config phải đổi — build không báo gì |
| `feature_symbol_renamed` | Tham chiếu C++ phải đổi — build sẽ báo |
| `pref_renamed` | Cần migration, đăng ký lại, hoặc đọc fallback trong code browser |

Điểm chung của ba dòng "build không báo gì": chúng là loại hỏng duy nhất có thể không lộ ra suốt một milestone.

## Sáu ví dụ chấm điểm đầy đủ

### Ví dụ A — Feature được bật mặc định trên Windows

```text
kind: base_feature
direction: modified
delta: windows disabled → enabled
signal: enabled_by_default
severity: 75
có trong build Windows: có
vấn đề coverage: không
score: 75
bucket: Behaviour change
```

**Việc tiếp theo:** tìm bản vá và các tham chiếu tới feature này trong code Samsung, kiểm tra xem có override từ Finch không, rồi chạy test cho các luồng chịu ảnh hưởng.

### Ví dụ B — Mojo method đổi signature

```text
kind: mojo_method
direction: modified
signal: ipc_signature_change
severity/score: 80
bucket: Compatibility break
```

**Việc tiếp theo:** tìm cả phía gọi lẫn phía hiện thực trong code Samsung, kiểm tra generated binding và khả năng tương thích version, rồi chạy test runtime đi qua đúng ranh giới process đó.

### Ví dụ C — Mojo method chỉ đổi thuộc tính build

```text
điểm nền cho mojo_method modified: 75
signal cụ thể: build_gate_changed
severity của signal: 35
score: 35, không phải 75
```

Đây là minh hoạ trực tiếp cho rule ở Bước 3: **signal cụ thể được ưu tiên hơn điểm nền thô.** Chính vì vậy bảng điểm mới kiểm toán được — mỗi con số truy ngược về đúng một rule.

### Ví dụ D — Pref không còn thấy trong lần chạy có partition

```text
signal: pref_left_scan
severity: 35
coverage của surface pref và switch ở bản mới: 0,4% (--partition downloads)
score: 35
bucket: Upstream cleanup thay vì Compatibility break, unconfirmed = true
lý do: có thể khoá này chỉ chuyển sang một file mà lần chạy chưa đọc
```

**Việc tiếp theo:** đọc file pref mà khoá đó có thể đã chuyển sang. Có ba kết quả:

- thấy cùng biến C++ đó ở một đường dẫn mới → đây là **move**;
- ghép được với một chuỗi mới → đây là **rename**;
- không thấy ở đâu trong khi coverage đã đủ cao → kết luận **đã bị xoá** là đáng tin.

### Ví dụ E — Feature bị dọn sau khi đã BẬT từ trước

```text
signal: flag_retired_on
severity/score: 35
bucket: Upstream cleanup
sửa ở: ngoài repository
```

**Không nên** mở bug với tiêu đề "hành vi vừa được bật" — vì nó đã bật từ lâu rồi. Việc đúng là đi tìm xem cấu hình rollout của Samsung còn đang set flag đó không, vì override đó từ nay sẽ không còn tác dụng.

### Ví dụ F — Khai báo chỉ dành cho Android, ở cả hai version

```text
platform_state.windows: not_compiled → not_compiled
score: 0
bucket: Upstream cleanup
```

Finding vẫn được giữ lại để kiểm toán, nhưng nó không cạnh tranh thứ tự ưu tiên với công việc thuộc Windows.

## Có thể tin tới đâu, và không nên tin điều gì

### Những điểm khiến kết quả kiểm toán được

- `Fact` và `Change` là JSON cố định, không phụ thuộc LLM.
- Mỗi finding đều có `reasons`: severity đến từ signal nào, vì sao score bằng 0 nếu có, và vì sao dòng đó mang cờ `unconfirmed` nếu có.
- Bảng signal, bảng bucket và danh sách thuộc tính được so đều nằm tập trung trong code, không rải rác.
- Có test bảo đảm bảng severity của signal và bảng bucket dùng chung một tập khoá; một signal không thể lặng lẽ rơi vào bucket mặc định mà không bị phát hiện.
- Cùng một cây source phải tạo ra cùng một thứ tự `Fact`; bước loại trùng không phụ thuộc thứ tự file mà hệ điều hành trả về.
- Bước so sánh từ chối chạy khi hai bên dùng target set khác nhau, hoặc khi số `Fact` lệch nhau bất thường.
- Độ tin cậy của kết luận "đã bị xoá" dùng coverage của đúng surface và đúng phía.
- `path:line`, giá trị trước/sau và delta đều được giữ lại, để người review mở source kiểm tra.

### Những điều điểm số không chứng minh

- Rằng code Samsung có tham chiếu tới symbol đó.
- Rằng build hoặc runtime của Samsung chắc chắn hỏng.
- Rằng severity 80 luôn tốn công hơn severity 60.
- Rằng parser đã hiểu mọi cú pháp Chromium có thể thêm trong tương lai.
- Rằng target set phủ được phần implementation.
- Rằng cấu hình bên ngoài repository đã được ai đó kiểm tra.

Tóm lại: báo cáo là **bằng chứng đã xếp hạng và đầu vào cho việc triage**, không phải một cái gật đầu tự động cho đợt upgrade.

## Đọc và lọc báo cáo như thế nào

### Các trường quan trọng trong JSON

```json
{
  "change": {
    "change_type": "modified",
    "kind": "mojo_method",
    "key": "network.mojom.Probe.Start",
    "before": {},
    "after": {},
    "deltas": {},
    "locations": ["path/to/file.mojom:42"],
    "signals": ["ipc_signature_change"],
    "severity": 80
  },
  "reasons": ["severity 80 — ..."],
  "score": 80,
  "bucket": "contract",
  "unconfirmed": false,
  "enrichment": {}
}
```

Một điểm cần biết khi viết script: `change.kind` và `bucket` nằm sẵn trong từng finding của JSON, nên lọc theo chúng là đọc thẳng. Nhóm hậu quả thì được tính từ `kind` lúc render, và `summary.by_group` giữ số đếm tương ứng.

### Bộ lọc trong bản HTML

Bản HTML có bốn bộ lọc độc lập, cộng một ô tìm kiếm và một ô loại trừ:

- **Bucket**: Compatibility break / Behaviour change / New declarations / Scheduled / Upstream cleanup.
- **Surface hoặc kind**: 16 loại `Fact`, được gom thành ba nhóm — Feature switches, External contracts, UI and scheduling.
- **Nhóm hậu quả**: chính ba nhóm vừa nêu.
- **Bằng chứng CL**: dòng này đã tra được CL chưa, và ở mức nào. Bộ lọc này chỉ hiện khi báo cáo có dữ liệu tra cứu; [phần 7](<07 - Truy nguyên CL và issue.md>) giải thích năm trạng thái của nó.
- **Ô loại trừ**: gõ một hoặc nhiều từ khoá để bỏ hẳn những dòng khớp chúng.
- **Ô tìm kiếm**: khớp với tên, `kind` thô, phần mô tả, tên màn hình hoặc thư mục, signal, đường dẫn, và phần tóm tắt từ ChromeStatus.

Các bộ lọc kết hợp với nhau bằng **AND**. Ô tìm kiếm không thay thế được bộ lọc kind — nó thu hẹp thêm, chứ không thay thế.

Mặc định bảng được sắp theo score giảm dần; bấm vào tiêu đề cột để đổi cách sắp. Chỉ 200 dòng đầu được render, để báo cáo lớn vẫn phản hồi nhanh; nút `Show more` mở thêm chứ không làm mất dữ liệu. Bấm vào một dòng sẽ mở ra: signal, vị trí source, các delta chính, lý do chấm điểm, phần enrichment, và — nếu đã tra cứu — CL cùng issue đứng sau thay đổi.

### Luồng triage đề xuất

1. Kiểm tra ref của hai bên, target set, coverage, missing target và lỗi trích xuất.
2. Lọc theo phần cần xem — kind, bucket hoặc nhóm hậu quả.
3. Xử lý các finding Compatibility break điểm cao trước — nhưng đọc signal chứ đừng chỉ nhìn con số.
4. Xem Behaviour change, tập trung vào các luồng mà Samsung có tuỳ biến riêng.
5. Xem New declarations để lập backlog cho việc test và cân nhắc adopt.
6. Xem Scheduled như danh sách của milestone sau.
7. Trước khi đóng Upstream cleanup, đọc mục *Unconfirmed* — hoặc bật bộ lọc *All coverage* trong HTML. Bỏ qua phần còn lại.

Với những dòng cần quyết định chứ không chỉ cần ghi nhận, còn một bước nữa: chạy `chromiumdiff serve` và mở dòng đó ra để xem CL nào đã tạo ra thay đổi và issue nào đứng sau nó. Điểm số nói dòng này đáng xem sớm đến đâu; CL nói người upstream đang sửa cái gì, và đó thường mới là thứ quyết định Samsung có phải làm gì hay không. Xem [phần 7](<07 - Truy nguyên CL và issue.md>).
