# Đọc một finding

Một cuộc điều tra bắt đầu từ một dòng và phải xác định dòng đó **nghĩa là gì**
trước khi đi tìm CL đứng sau nó. Ba thứ quyết định điều đó: signal của dòng nói
gì, những cách một finding đúng vẫn bị đọc sai, và chuỗi mắt xích đứng sau một
control trong settings.

Chúng được để ở đây để một cuộc điều tra không cần gì ngoài thư mục này.

## Mục lục

- Các signal mà skill này hành động theo
- Những cái bẫy làm đổi kết luận
- Chuỗi ba chặng của settings

## Các signal mà skill này hành động theo

| Signal | Nghĩa |
|---|---|
| `enabled_by_default` | Giờ mặc định BẬT **trên Windows** |
| `default_flip_on` | Mặc định chung lật sang bật |
| `ipc_signature_change` | Signature của method Mojo đã đổi. Hỏng ở ranh giới giữa hai process lúc chạy, không hỏng lúc biên dịch |
| `ipc_shape_changed` | Nửa dữ liệu của cùng kiểu hỏng đó: một field của struct đổi kiểu hoặc đổi ordinal, hoặc một struct thành union. Process bên kia đọc số byte đó thành thứ khác |

Một báo cáo mang nhiều signal hơn bốn cái này; đây là những cái mà các bước của
chính skill này gọi tên. Với mọi signal khác, đọc trường `signals` của dòng cùng
với phần chữ của finding — signal quyết định là signal có severity cao nhất, và
nó vừa đặt ra severity vừa xếp dòng đó vào bucket của nó.

## Những cái bẫy làm đổi kết luận

Đọc các mục dưới đây trước khi diễn giải bất kỳ mục bị xoá nào. Mỗi mục là một
cách đi tới câu trả lời sai từ một finding bản thân nó vẫn đúng.

### Một flag bị gỡ không phải một tính năng bị xoá

Một `base::Feature` hoặc một Blink runtime feature biến mất, và bản diff đọc lên
thành mất capability. Chromium xoá flag khi kết cục đã ngã ngũ, nên trạng thái mà
flag giữ **ngay trước khi** bị xoá cho biết kết cục đó là gì.

Trên một cặp milestone, đây là một nhóm lớn, và phần lớn là `flag_retired_on` —
các tính năng đã ship — chứ không phải `flag_retired_off`. Đọc cả nhóm này thành
mất capability là đảo ngược ý nghĩa thông thường của nó.

`flag_retired_on` nghĩa là hành vi đó giờ là vĩnh viễn và không tắt được;
`flag_retired_off` nghĩa là code đã bị xoá. Cả hai đều không đổi hành vi ở đợt
nâng version này, nhưng cả hai đều làm hỏng build của bất cứ thứ gì gọi tên
symbol đó, và cả hai đều **âm thầm** làm mọi override đặt flag từ bên ngoài
binary mất tác dụng.

### Một khai báo thường là chuyển chỗ chứ không phải biến mất

Một mục biến mất khỏi một file và thường xuất hiện lại ở chỗ khác, hay gặp là sau
một flag khác. M148 → M151 "mất" route `SITE_SETTINGS_LOCAL_NETWORK_ACCESS`;
thực tế Chromium đang giữa một cuộc migration và khai báo **cả hai** version của
trang ở M148, mỗi cái sau guard riêng, rồi xoá cái cũ khi guard mới đã ship.

Tìm key đó trên toàn cây trước khi báo cáo một mục bị xoá, và đọc thuộc tính
`guards` ở cả hai phía. Nếu nó tồn tại ở chỗ khác thì đây là một lần chuyển chỗ,
và thay đổi mà người dùng thấy đã xảy ra vào lúc flag điều khiển lật — thường là
sớm hơn cả hai version đang so, và đó là lý do CL cần tìm có thể nằm ngoài cửa sổ
so sánh.

### Một lần phá vỡ ABI của Mojo phải phá vỡ đối với một ai đó

Hai đầu của một Mojo interface đều biên dịch từ cùng một cây source, nên process
browser và process renderer của cùng một bản build luôn khớp nhau. Vì vậy một
`ipc_signature_change` giữa hai version gốc là **lỗi build cho code nằm ngoài
cây này**, không phải lỗi lúc chạy — trừ khi có thứ gì đó ship tách khỏi browser
mà vẫn nói cùng interface, hoặc một bản cài có thể rơi vào trạng thái cập nhật
dở dang khiến hai version chạy song song, hoặc có code ngoài cây hiện thực
interface đó, và đây là trường hợp thường gặp.

Hãy nói rõ trường hợp nào đang áp dụng trước khi gọi nó là lỗi lúc chạy. Một dòng
**Compatibility break** nói rằng một contract đã đổi, không nói rằng có ai đang
dựa vào contract đó.

### Một switch bị xoá hỏng âm thầm; một pref bị xoá có thể bỏ rơi dữ liệu

Chromium **bỏ qua các command-line switch nó không nhận ra** — không cảnh báo,
không báo lỗi, không dòng log nào. Một script khởi chạy hay một test runner vẫn
khởi động browser y như cũ trong khi flag nó truyền vào ngừng có tác dụng.

Một preference bị xoá thì khác: key vẫn nằm trong file `Preferences` của người
dùng trên đĩa, và điều đó có quan trọng hay không phụ thuộc vào việc Chromium có
viết migration trong `chrome/browser/prefs/browser_prefs.cc` hay không.

Với switch, tìm chuỗi đó trong các script khởi chạy và test automation. Với pref,
áp dụng cái bẫy phía trên trước: một key bị xoá đến dưới dạng `pref_left_scan`,
mà chính phần `reason` của nó nói rằng key có thể chỉ đơn giản đã chuyển vào một
file pref mà lần quét không mở. Signal đó là một **câu hỏi chưa ngã ngũ**, không
phải một lần xoá. Đọc file pref mà nó có thể đã chuyển vào để giải quyết.

## Chuỗi ba chặng của settings

Khi triệu chứng là một control trên trang settings, flag đứng sau nó cách ba chặng:

```
route.ts  --guard-->  key loadTimeData  --settings_ui.cc-->  base::Feature
```

| Source | Cho biết |
|---|---|
| `chrome/browser/resources/settings/route.ts` | Danh mục trang, cùng guard `loadTimeData` bọc quanh mỗi route |
| Template trong `chrome/browser/resources/settings/<page>/` | Từng control, loại của nó (`settings-toggle-button`, `settings-dropdown-menu`, `cr-radio-group`), và binding `pref="{{prefs.x.y}}"` của nó |
| `chrome/browser/ui/webui/settings/settings_ui.cc` | Ánh xạ mỗi key `loadTimeData` sang `base::Feature` đứng sau nó |
| `chrome/browser/resources/settings/page_visibility.ts` | Các key hiển thị theo từng trang. **Công cụ không tải file này** — đọc thủ công khi câu hỏi là một trang có tồn tại hay không |
| `chrome/common/pref_names.h` | Các pref nền phía sau |

**Đi hết cả ba chặng.** Dừng ở chặng đầu sẽ báo cáo một trang là có mặt trong khi
một flag có thể đang ẩn nó: một file khai báo bao giờ cũng khai báo nhiều hơn
phần thật sự ship.

Binding `pref="{{prefs.x.y}}"` là mối nối mạnh nhất giữa một control và phần lõi
của browser, vì nó mang tính khai báo và sống sót qua một lần thiết kế lại — trang
có thể được viết lại trong khi preference đứng sau vẫn giữ nguyên, nên binding cho
biết **cùng một control đã chuyển chỗ**, chứ không phải một control mới xuất hiện
bên cạnh một control cũ biến mất. Loại của control được viết ngay trong tên
element, và đó là thứ khiến "một dropdown đã thành một toggle" phát hiện được một
cách máy móc.
