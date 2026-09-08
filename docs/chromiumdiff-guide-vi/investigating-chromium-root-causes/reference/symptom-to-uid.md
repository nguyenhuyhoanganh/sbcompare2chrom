# Từ một triệu chứng tới một identifier

## Mục lục

- Vì sao grep báo cáo bằng lời phàn nàn không ra gì
- Bảng định tuyến
- Xử lý một triệu chứng không nêu identifier nào
- Chuỗi ba chặng đứng sau một màn hình settings
- Khi triệu chứng là một lỗi build

## Vì sao grep báo cáo bằng lời phàn nàn không ra gì

Báo cáo được index theo **tên khai báo**. Không ai đặt tên một khai báo là
"trang downloads mất cái toggle". Tìm theo chữ trong lời phàn nàn sẽ không ra gì,
và điều đó chỉ cho biết lời phàn nàn được viết bằng ngôn ngữ tự nhiên.

Nên bước đầu tiên **không bao giờ** là tìm kiếm. Bước đầu tiên là xác định
**triệu chứng thuộc loại khai báo nào**, vì `kind` thu hẹp phạm vi tìm từ ba
nghìn dòng xuống vài chục dòng.

## Bảng định tuyến

Số dòng lấy từ một lần chạy M148 → M151 thật với bộ `default`, để thấy mỗi `kind`
có bao nhiêu dòng.

| Triệu chứng nghe như | `kind` cần tìm | Số dòng |
|---|---|---|
| Một tính năng bật hoặc tắt; hành vi khác đi mà UI không đổi | `base_feature` | 507 |
| Một tham số bên trong một tính năng đã đổi (timeout, ngưỡng, biến thể) | `feature_param` | 184 |
| Một trang web ngừng hoạt động; một JS API mất hoặc mới có | `idl_member`, `idl_interface` | 477 |
| Một web feature có mặt nhưng không hoạt động, hoặc đã ship cho mọi người | `blink_runtime_feature` | 285 |
| Hai process không khớp nhau; renderer crash khi nhận message; code ngoài cây build hỏng | `mojo_method`, `mojo_field`, `mojo_struct`, `mojo_enum`, `mojo_interface` | 339 |
| Một setting không được nhớ; một giá trị trong profile bị bỏ qua | `pref` | 163 |
| Một script khởi chạy hoặc một flag automation ngừng có tác dụng | `switch` | 7 |
| Một mục `chrome://flags` biến mất hoặc đã bị lên lịch xoá | `flag_entry` | 783 |
| Một control biến mất khỏi màn hình settings | `webui_control` | 100 |
| Một trang hoặc trang con của settings biến mất hoặc chuyển chỗ | `webui_route` | 8 |
| Một màn hình vẫn hiển thị nhưng một phần bị ẩn | `webui_gate` | 169 |

Tìm trong một `kind` bằng cách truyền tiền tố:

```bash
python3 skills/investigating-chromium-root-causes/scripts/why.py out/DIR webui_control:
```

Lệnh đó liệt kê mọi dòng của `kind` ấy, đã xếp hạng. Chọn dòng có tên khớp màn
hình đang xét, rồi chạy lại với UID đầy đủ của nó.

## Xử lý một triệu chứng không nêu identifier nào

Ba bước, theo thứ tự. Dừng ở bước đầu tiên cho ra một cái tên.

1. **Đọc triệu chứng để tìm một danh từ riêng.** Tên một tính năng của sản phẩm
   thường gần với tên flag của nó — "back/forward cache", "local network access",
   "autofill AI". Tìm theo tên đó.

2. **Tìm code hiển thị nó, rồi đọc xem cái gì chắn nó.** Với một triệu chứng về
   UI, cách này nhanh hơn tìm trong báo cáo. Định vị template hoặc trang trong
   Chromium, tìm câu `if` bọc quanh thứ đang thiếu, và guard đó gọi tên flag hoặc
   pref. Cái tên đó chính là identifier.

3. **Tìm trong báo cáo theo đường dẫn.** Nếu biết đại khái code nằm ở đâu, script
   khớp được theo mẩu đường dẫn:

   ```bash
   python3 skills/investigating-chromium-root-causes/scripts/why.py out/DIR downloads
   ```

Cả ba bước đều không ra tên thì triệu chứng có thể không phải một thay đổi khai
báo — xem `no-row.md`, Phần A.

## Chuỗi ba chặng đứng sau một màn hình settings

Một triệu chứng WebUI gần như không bao giờ có nguyên nhân nằm trong một khai báo
WebUI. Chuỗi chạy như sau:

```
control trên màn hình   →   pref hoặc gate mà nó gắn vào   →   base::Feature đứng sau
   webui_control                 pref / webui_gate                   base_feature
```

**Thời điểm người dùng thấy nằm ở đầu bên kia.** Một control biến mất thường là
đã chuyển ra sau một guard khác, và thứ người dùng nhận ra là lúc flag lật — đó
là một dòng `base_feature` nằm ở một chỗ hoàn toàn khác.

Vì vậy hãy điều tra cả ba chặng trước khi trả lời, và dự liệu rằng CL sẽ gắn vào
chặng cuối. [reading-a-finding.md](reading-a-finding.md) đi qua chuỗi này chi tiết.

## Khi triệu chứng là một lỗi build

Một thay đổi Mojo làm hỏng build của code **ngoài** cây, không phải trong cây —
hai đầu bên trong Chromium đều được sinh ra từ cùng một file `.mojom`, nên một
signature đã đổi vẫn biên dịch sạch ở cả hai phía và chỉ hỏng ở nơi người khác
hiện thực interface đó.

Điều đó làm identifier dễ tìm: trình biên dịch đã gọi tên nó rồi. Lấy symbol từ
thông báo lỗi, chuyển sang dạng đường dẫn Mojo (`blink.mojom.Interface.method`),
rồi tìm theo đó.

Chiều ngược lại cũng đúng với một lần hỏng **âm thầm**: `ipc_shape_changed` và
`ipc_signature_change` làm đổi phần deserialization mà không có lỗi build nào.
Nếu triệu chứng là "message ngừng tới nơi" trong khi build vẫn sạch, hãy tìm
trong các `kind` của Mojo trước.
