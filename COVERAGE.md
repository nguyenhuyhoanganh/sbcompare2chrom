# "Tính năng" là gì, và công cụ phủ được bao nhiêu

Tài liệu này trả lời hai câu hỏi hay bị gộp làm một:

1. **Công cụ coi cái gì là "một tính năng"?**
2. **Nó lấy được bao nhiêu phần trăm khác biệt giữa hai bản Chromium?**

Mọi con số dưới đây **đo thật tại M151 (151.0.7922.138)**, kèm cách đo để anh
tự kiểm lại — không có ước lượng cảm tính. Số sẽ trôi theo từng milestone; phần
"Tự kiểm lại" ở cuối cho biết chạy lệnh nào để lấy số mới.

---

## Phần 1. Định nghĩa "tính năng"

Không có một định nghĩa duy nhất, và đó là chủ ý. Công cụ trích **13 loại sự
kiện khai báo**, chia ba tầng. Đây là toàn bộ danh sách.

### Tầng A — Công tắc hành vi

Cái quyết định người dùng thấy gì.

| Loại | Là gì | Số lượng M151 |
|---|---|---:|
| `base_feature` | `BASE_FEATURE(kFoo, ENABLED_BY_DEFAULT)` — cờ bật/tắt | 2.062 |
| `feature_param` | Tham số tinh chỉnh của một cờ (ngưỡng, timeout) | 862 |
| `blink_runtime_feature` | API web: `stable` / `experimental` / `test` | 1.212 |
| `flag_entry` | Mục `chrome://flags` kèm **milestone sẽ bị xoá** | 1.753 |

Đây là tầng quan trọng nhất. Một cờ đổi từ `disabled` sang `enabled` là Chromium
nói **"cái này vừa ship"** — bit dự báo gần như toàn bộ thay đổi hành vi mà một
fork thừa hưởng, và nó không xuất hiện trong release note.

### Tầng B — Hợp đồng với bên ngoài

Đổi là gãy, nhưng gãy im lặng.

| Loại | Là gì | M151 |
|---|---|---:|
| `pref` | Khoá preference — đổi tên = **orphan dữ liệu đã lưu của người dùng** | 683 |
| `switch` | Cờ dòng lệnh — đổi tên = script khởi chạy hết tác dụng | 288 |
| `mojo_interface` / `mojo_method` | ABI giữa các tiến trình — đổi signature **gãy lúc chạy, không gãy lúc build** | 338 / 1.362 |
| `idl_interface` / `idl_member` | Hình dạng API web — xoá member = vỡ tương thích với site | 2.608 / 11.941 |

### Tầng C — Bề mặt giao diện khai báo

| Loại | Là gì | M151 |
|---|---|---:|
| `webui_route` | Một trang `chrome://settings/...` **kèm cờ gác nó** | 108 |
| `webui_control` | Một control: loại element + `pref` nó ghi vào | 761 |
| `webui_gate` | `AddBoolean("enableX", IsEnabled(kX) && !kY.Get())` | 668 |

Ba loại này nối thành chuỗi ba chặng:

```
route.ts  --guard-->  khoá loadTimeData  --settings_ui.cc-->  base::Feature
```

Đọc thiếu một chặng là ra kết luận sai. Xem trap 6 trong
[skills/analyzing-chromium-uprevs/reference/traps.md](skills/analyzing-chromium-uprevs/reference/traps.md).

### Ba kích thước của "một tính năng"

Công cụ **không chọn hộ** kích thước, mà xuất cả ba rồi nhóm lại:

| Kích thước | Ví dụ thật | Nhận ra nhờ |
|---|---|---|
| **Control** | Dropdown thành toggle | `webui_control` đổi thuộc tính `control` |
| **Trang / mục** | Local Network Access là một page | `webui_route` |
| **Năng lực** | Cả cụm LNA: 1 route xoá, 1 route thêm, 5 cờ, 3 Blink feature | `cluster.py` gộp |

Việc gộp dùng **liên kết mà dữ liệu tự khai báo** (route gọi tên guard, guard gọi
tên feature), không phải suy đoán theo độ giống tên. Cụm LNA gom 7 mảnh rời trên
4 bề mặt thành 1 dòng.

---

## Phần 2. Cái KHÔNG nằm trong định nghĩa

Phần quan trọng nhất của tài liệu này. Nó quyết định "100%" có đạt được hay không.

| Không đọc | Hệ quả |
|---|---|
| **Thân hàm C++** | Logic đổi hoàn toàn bên trong một hàm → vô hình |
| **Logic TypeScript** | Chỉ đọc template khai báo, không đọc hành vi trang |
| **Chuỗi / i18n (`.grd`, `.grdp`)** | **Đổi nhãn một setting là thay đổi người dùng thấy — không phát hiện được** |
| **CSS, layout, icon** | Không ảnh chụp, không bố cục, không hồi quy thị giác |
| **`page_visibility.ts`** | Khoá ẩn/hiện theo trang — phải đọc tay |
| **Đồ thị GN** | Khai báo có trong cây ≠ được biên dịch vào binary |
| **Ngoài repository** | Finch server-side, script khởi chạy, automation, metadata store |

---

## Phần 3. Độ phủ đo được

### Cờ tính năng: khoảng 60%

| | Số lượng | Cách có được |
|---|---:|---|
| Đang bắt được | **2.062** | đếm trực tiếp trong snapshot M151 |
| Trong file ứng viên chưa tải | ~1.223 | mẫu 60/401 file → 183 khai báo, 3,0/file |
| Ngoài quy ước đặt tên | ~132 | mẫu 300/39.641 file `.cc` → 1 khai báo |
| **Ước tính toàn cây** | **~3.417** | |
| **Độ phủ** | **~60%** | |

Một kết quả đáng chú ý: nỗi lo "quy ước đặt tên không phải luật" **nhỏ hơn nhiều
so với dự đoán**. Trong 39.641 file `.cc` không khớp quy ước nào, mẫu 300 file
chỉ tìm được **1** khai báo. Chromium tuân thủ quy ước khá chặt ở mức toàn cây.

Cũng đừng đọc 60% quá bi quan: 2.062 cái đang bắt được **không phải mẫu ngẫu
nhiên** — đó là các file trung tâm và lớn nhất (`chrome_features.cc` 247 cái,
`content/public/common` 201). File chưa phủ trung bình chỉ 3,0 khai báo.

### Theo từng loại nguồn

| Nguồn | Phủ | Toàn cây | % |
|---|---:|---:|---:|
| Blink runtime features | 1 file | 1 file | **100%** |
| Web IDL | 2.167 | 2.575 | 84% |
| **Mojo (IPC)** | 490 | 1.588 | **30%** |
| **`pref_names`** | 3 | 164 | **1%** |
| **Bề mặt WebUI** | 8 | 132 | **6%** |

**Hai dòng cần nêu rõ trong mọi báo cáo:**

- **Mojo 30%** — đây là loại mang finding nghiêm trọng nhất hệ thống (severity
  80). Chỉ đọc `third_party/blink/public/mojom`; toàn bộ `services/`,
  `content/`, `chrome/` không đọc.
- **`pref_names` 1%** — chỉ đọc `chrome/common/pref_names.h`. Mọi
  `components/*/pref_names.h` (downloads, bookmarks, history, autofill) không
  đọc. Mà đổi tên pref là lỗi im lặng điển hình: build qua, test xanh, cài đặt
  người dùng âm thầm reset.

`must fix: 0` **không bao giờ** nghĩa là "uprev sạch". Nó nghĩa là "không thấy
gì trong phần đã quét".

---

## Phần 4. Đóng kín được không? Trường hợp settings M148 → M151

### Hai nghĩa của "100%"

| Nghĩa | Đạt được? |
|---|---|
| 100% khai báo **bên trong** thư mục của một vùng | **Có** — bằng `--complete` |
| 100% **tính năng thuộc về** vùng đó | **Không** — vùng tham chiếu ra ngoài |

### `--complete`: đóng kín theo thư mục

Mặc định, partition là **bộ lọc trên danh sách người viết tay**, nên nó thừa
hưởng đúng khoảng trống của danh sách đó. Đo tại M151, các vùng nhỏ có lỗ thật:

| Vùng | Thiếu | Cụ thể |
|---|---:|---|
| bookmarks | 2 | `bookmark_pref_names.h`, `bookmark_features.h` |
| history | 3 | cả hai file pref + `features.h` |
| downloads | 4 | `download_stream.mojom`, `background_service/features.*` |

`--complete` **đảo chiều suy ra**: kéo cả gốc thư mục với hợp của mọi đuôi file
mà extractor đọc được, nên độ phủ trong gốc đó **đúng do cấu trúc**, không phụ
thuộc ai nhớ ra.

Khả thi vì gốc thư mục nhỏ. Kích thước tarball đo thật:

```
components/bookmarks  0,2 MB      net/base                0,7 MB
components/download   0,4 MB      services/network/public 0,7 MB
components/history    0,5 MB      chrome/browser/ui/webui 3,4 MB
extensions/           3,8 MB      extensions/common/api   0,2 MB
```

Gitiles phục vụ **cả thư mục hoặc không gì cả**, nên `third_party/blink/` sẽ là
hàng trăm MB. Vì vậy vùng `webplatform` **không đóng kín được** và công cụ báo
lỗi nói rõ điều đó, thay vì giả vờ.

### Đóng kín theo tham chiếu: biến "đủ chưa" thành một danh sách

Độ phủ mức file chỉ trả lời "ta có tải những file ai đó liệt kê không". Nó không
trả lời được "ta có tải những file mà bề mặt này *phụ thuộc* không" — vì điều đó
chỉ biết được **sau khi trích xuất**.

Tầng khai báo là một đồ thị với các cạnh do chính dữ liệu khai:

```
webui_route  --guards-->      webui_gate  --features-->  base_feature
webui_control --pref-->       pref
blink_runtime --base_feature--> base_feature
feature_param --feature-->    base_feature
```

Đi hết các cạnh đó và báo cáo cạnh nào trỏ ra ngoài snapshot. **Danh sách rỗng
là bằng chứng bề mặt tự đóng kín. Danh sách không rỗng là worklist chính xác.**

### Kết quả thật

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --partition settings --complete --no-enrich
```

Tìm được **1.565 khác biệt**:

| Loại | Tổng | thêm / bớt / đổi |
|---|---:|---|
| `flag_entry` | 783 | +282 −220 ~281 |
| `mojo_method` | 170 | +110 −56 ~4 |
| `pref` | 163 | +22 −139 ~2 |
| `webui_gate` | 143 | +70 −33 ~40 |
| `webui_control` | 108 | +48 −26 ~34 |
| `base_feature` | 70 | +39 −23 ~8 |
| `feature_param` | 66 | +41 −13 ~12 |
| `mojo_interface` | 51 | +41 −10 ~0 |
| `webui_route` | 8 | +5 −1 ~2 |
| `switch` | 3 | +2 −1 ~0 |

Và phần quan trọng — công cụ **tự khai** chỗ nó chưa đóng kín:

```
reference closure: 170 unresolved reference(s)
    89  cờ mà gate của settings gọi tên, nhưng không file nào ta tải khai báo
    77  preference mà control ghi vào, khai báo nằm ở components/*/pref_names.h
     4  guard của route mà không handler nào ta tải khai báo
```

### Kết luận cho settings

- **Có 100%** cho tầng khai báo, trong phạm vi thư mục settings, nhờ
  `--complete`. Phủ do cấu trúc chứ không do trí nhớ.
- **Chưa đóng kín** với 170 thứ settings tham chiếu ra ngoài. Khác biệt căn bản
  so với trước: công cụ **tự nói ra con số đó và gọi tên từng cái**, thay vì để
  người dùng đoán.
- **Không bao giờ 100%** với đổi nhãn, đổi layout, hay logic TypeScript — những
  thứ nằm ngoài định nghĩa "khai báo" ở Phần 1.

### Muốn đóng nốt 170 mục kia

Chúng nằm ở nơi đã biết: `components/*/pref_names.h` (77 pref) và các file cờ ở
`content/`, `components/` (89 cờ). Thêm chúng vào roots của partition `settings`
là đóng được — nhưng khi đó "settings" không còn là một vùng nhỏ nữa.

Đó là đánh đổi cần người quyết, không nên mặc định.

---

## Phần 5. Tự kiểm lại

Mọi con số ở trên đều dựng lại được:

```bash
# Độ phủ mức file, kèm tên từng file còn thiếu
python3 -m chromedrift catalog 151.0.7922.138 --limit 0

# Độ phủ của riêng một vùng
python3 -m chromedrift catalog 151.0.7922.138 --partition downloads

# Đóng kín tham chiếu: in ra ở mỗi lần chạy, và lưu trong
# report.json tại meta.unresolved_references
python3 -m chromedrift run <A> <B> --partition settings --complete

# Số fact theo từng loại
python3 -m chromedrift snapshot 151.0.7922.138
```

Khi thêm target mới vào `chromedrift/targets.py`, chạy lại `catalog` và closure
để xem khoảng trống dịch chuyển bao nhiêu — đó là cách duy nhất biết một lần bổ
sung có đáng hay không.
