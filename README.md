# chromedrift

Công cụ so sánh hai phiên bản Chromium và trả lời câu hỏi: **đội làm trình duyệt downstream cần sửa những gì khi nâng nền.**

---

## Phần 1. Dự án này giải quyết vấn đề gì

Samsung Browser (chạy trên Windows) được xây trên nền Chromium. Cứ vài phiên bản, đội lại nâng nền lên một mốc mới — ví dụ đang ở M148, sắp nâng lên M151.

Mỗi lần nâng như vậy, có ba câu hỏi phải trả lời:

- Chromium **thêm** tính năng gì mới?
- Chromium **bỏ** cái gì đi?
- Cái gì **vẫn còn nhưng đổi cách hoạt động**?

Nghe thì đơn giản. Nhưng nếu bạn tải hai bản Chromium về rồi chạy `git diff`, bạn nhận được **vài triệu dòng khác nhau**. Phần lớn trong đó không liên quan gì đến ba câu hỏi trên: đổi tên biến, dọn code, sửa chính tả trong comment, cập nhật thư viện bên thứ ba. Đọc hết là không khả thi, mà đọc lướt thì bỏ sót đúng cái quan trọng.

Nên vấn đề thật không phải *"làm sao so được"*, mà là **"làm sao lọc ra đúng phần có nghĩa"**.

Đó là việc mà `chromedrift` làm.

---

## Phần 2. Ba ý tưởng cốt lõi

### Ý tưởng 1 — Không cần tải Chromium về

Một bản Chromium đầy đủ nặng khoảng **100 GB** và mất vài giờ để đồng bộ. Nhân hai phiên bản là 200 GB và cả buổi chờ đợi.

Nhưng thực ra công cụ chỉ cần đọc vài nghìn **file khai báo** — những file liệt kê "có tính năng gì, tên gì, mặc định bật hay tắt". Chromium cho phép tải riêng từng thư mục qua giao thức Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<phiên-bản>/<thư-mục>.tar.gz
```

Tổng cộng khoảng **40 MB mỗi phiên bản**. Đo thật: so hai phiên bản mất **1 phút 36 giây** lần đầu, và gần như tức thì các lần sau nhờ cache.

Nếu đội đã có sẵn bản Chromium trên máy hoặc mirror nội bộ thì dùng tuỳ chọn `--local-src`, phần còn lại không đổi gì.

### Ý tưởng 2 — Chuẩn hoá trước, so sánh sau

Đây là chỗ quyết định công cụ dùng được hay không.

Giữa M139 và M143, Chromium đổi cách viết macro khai báo tính năng — bỏ bớt một tham số:

```cpp
// M139 trở về trước
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);

// M142 trở đi — tên chuỗi được tự suy ra từ tên biến
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
```

Chỉ riêng trong một file, M139 có **170/170** khai báo kiểu cũ, M143 có **12/187**. Công cụ nào so theo *văn bản mã nguồn* sẽ báo: *"170 tính năng bị xoá, 187 tính năng mới"* — hoàn toàn vô nghĩa.

`chromedrift` chuẩn hoá `kBackForwardCache` thành `"BackForwardCache"` trước khi so. Kết quả thật: **152 giữ nguyên, 18 bị bỏ, 35 thêm mới**. Đó mới là con số đọc được.

### Ý tưởng 3 — AI đứng cuối, không đứng đầu

Các bước tất định (trích xuất, chuẩn hoá, so sánh, chấm điểm) làm phần nặng và lọc từ vài nghìn thay đổi xuống còn vài chục mục đáng chú ý. Model AI chỉ nhận danh sách đã lọc và xếp hạng đó.

Nhờ vậy, với cửa sổ ngữ cảnh 200k, **toàn bộ 2.226 thay đổi chỉ tốn ~189k token = 2 request** — thay vì hàng trăm request nếu đưa mã nguồn thô vào. Chi tiết ở [Phần 6](#phần-6-chia-việc-theo-vùng--và-cái-bẫy-thứ-hai).

---

## Phần 3. Cái bẫy lớn nhất — và tại sao công cụ này tồn tại

Nếu bạn chỉ đọc một phần trong README này, hãy đọc phần này.

### Chromium không bao giờ bật thẳng một tính năng mới

Quy trình của họ luôn là bốn bước:

1. **Viết code mới, đặt sau một cái công tắc**, mặc định TẮT. Code đã có trong bản phát hành nhưng không ai thấy gì.
2. **Bật dần từ xa** — 1% người dùng, rồi 10%, rồi 50%. Có sự cố thì tắt lại ngay, không cần phát hành bản mới. Cái công tắc này gọi là *feature flag*.
3. **Đặt mặc định BẬT trong code**, khi đã chắc chắn ổn.
4. **Vài phiên bản sau, xoá luôn công tắc** và xoá code cũ, vì không còn ai cần tắt nữa.

### Hệ quả: một tính năng có ba mốc thời gian khác nhau

| Mốc | Trong code xảy ra gì | Người dùng thấy gì |
|---|---|---|
| **A** | Code mới xuất hiện, công tắc TẮT | Không thấy gì |
| **B** | Công tắc chuyển thành BẬT | **Đây mới là lúc thấy đổi** |
| **C** | Code cũ và công tắc bị xoá | Không thấy gì |

Ba mốc này thường **cách nhau nhiều phiên bản**. Một tính năng có thể xuất hiện ở M145, bật ở M147, và dọn dẹp ở M151.

Bây giờ hãy tưởng tượng bạn so M148 với M151 và chỉ nhìn code. Bạn sẽ thấy **Mốc C** — code cũ biến mất — và kết luận *"Chromium vừa bỏ tính năng này"*. Trong khi sự thật là tính năng đã đổi từ M147, và giữa M148 với M151 người dùng chẳng thấy gì khác cả.

**Nói một câu:** *File khai báo cho biết cái gì tồn tại. Chỉ có công tắc mới cho biết người dùng thật sự thấy gì.*

### Ví dụ có thật: Local Network Access

Đây không phải chuyện lý thuyết. Kiểm trên dữ liệu thật M148 → M151:

**Bước 1.** So danh sách trang settings, mục `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` **biến mất**. Đọc thô: *"Chromium bỏ trang Local Network Access"* — một trang quyền riêng tư quan trọng. Đủ để cả đội hoảng.

**Bước 2.** Nhưng đọc kỹ ở M148 thì thấy có **hai** trang cùng tồn tại:

```js
Nếu công tắc 'enableLocalNetworkAccessSetting' bật:
    → tạo trang  /localNetworkAccess     (bản cũ)

Nếu công tắc 'enableLocalNetworkAccessSplitPermissions' bật:
    → tạo trang  /localNetwork           (bản mới, tách quyền chi tiết hơn)
```

**Bước 3.** Ở M151 chỉ còn bản mới. Trang cũ đã bị xoá khỏi code.

**Bước 4.** Kiểm công tắc:

```
M148:  kLocalNetworkAccessChecksSplitPermissions = MẶC ĐỊNH BẬT
M151:  công tắc đã bị xoá hoàn toàn
```

**Kết luận thật:** Trang không bị bỏ — nó được **thay** bằng bản tách quyền. Và vì công tắc đã BẬT sẵn từ M148, **người dùng M148 đã nhìn thấy bản mới rồi**. Giữa hai mốc, trải nghiệm không đổi gì; M151 chỉ dọn code.

Việc cần làm khi nâng lên M151 không phải "khôi phục tính năng bị mất", mà chỉ là: *nếu code Samsung có chỗ nào trỏ tới `/localNetworkAccess` cũ thì sửa thành `/localNetwork`*. Một việc nhỏ, hoàn toàn khác với cái mà diff thô làm bạn tưởng.

### Quy mô của cái bẫy này

Đây không phải ca cá biệt. Đo trên dữ liệu thật:

- **M148 → M151, Windows:** 90 công tắc bị gỡ, chia đúng **45 cái đã ship** / **45 cái bỏ dở**. Không cái nào đổi hành vi. Nếu gắn nhãn "mất tính năng" cho cả 90, thì **một nửa danh sách cảnh báo là báo động giả**.
- **M139 → M143, tầng web:** trong 202 tính năng "biến mất", có **170 cái vốn đã ở trạng thái ổn định** — tức là công tắc bị dọn sau khi tính năng đã ship thành công.

Một công cụ báo 170 báo động giả ngay đầu danh sách sẽ mất hết uy tín ngay lần chạy đầu. `chromedrift` phân biệt được các trường hợp này, và đó là lý do chính nó tồn tại.

---

## Phần 4. Dự án gồm những gì

Toàn bộ là **Python thuần, 6.965 dòng, 31 file**, không dùng thư viện ngoài nào. Không cần `pip install`, không cần môi trường ảo, không cần quyền quản trị. Lý do: môi trường triển khai thường là mạng nội bộ công ty, nơi thêm một package là cả một quy trình phê duyệt.

Cộng thêm **1.541 dòng tài liệu** và **100 bài kiểm thử** chạy offline.

Dự án chia làm bốn nhóm:

### Nhóm 1 — Lấy dữ liệu về (`acquire.py`, `targets.py`, `snapshot.py`)

`targets.py` là bản khai báo *cần tải file nào và vì sao*. Ví dụ: tải `content/public/common` để lấy công tắc tầng nội dung, tải `third_party/blink/renderer/modules` để lấy các file mô tả API web. Mỗi mục có ghi chú giải thích, nên thêm một nguồn mới chỉ là thêm một dòng.

`acquire.py` tải các mục đó về, có cơ chế thử lại và lưu cache. Nó xử lý vài chuyện thực tế: máy chủ Gitiles thỉnh thoảng cắt kết nối giữa chừng và trả về file rỗng mà không báo lỗi, nên mọi lần tải đều kiểm tra nội dung có thật sự về hay không. Nó cũng chặn lỗ hổng path traversal khi giải nén (một file trong tarball tên `../../../etc/passwd` sẽ bị bỏ qua thay vì ghi ra ngoài thư mục đích).

`snapshot.py` gộp hai bước trên thành một "ảnh chụp" của một phiên bản: tải về, trích xuất, lưu thành JSON. Ảnh chụp của một phiên bản đã phát hành thì không bao giờ đổi, nên cache giữ vĩnh viễn — đây là lý do lần chạy thứ hai gần như tức thì.

### Nhóm 2 — Đọc và hiểu mã nguồn (`extract/`, 6 bộ đọc)

Mỗi bộ đọc là hai hàm thuần: *"file này có thuộc phần tôi đọc không"* và *"đọc ra được những gì"*. Nhờ vậy mỗi bộ đọc kiểm thử được độc lập, không cần mạng, không cần Chromium.

| Bộ đọc | Đọc gì | Cho biết |
|---|---|---|
| `base_features.py` | Khai báo `base::Feature` trong C++ | Công tắc tính năng và **mặc định bật/tắt theo từng nền tảng** |
| `blink_runtime.py` | `runtime_enabled_features.json5` | Tính năng tầng web engine, trạng thái ổn định/thử nghiệm theo nền tảng |
| `web_idl.py` | File `.idl` | Hình dạng chính xác của API web: interface, phương thức, thuộc tính |
| `mojom.py` | File `.mojom` | Giao diện giữa các tiến trình, kèm chữ ký phương thức |
| `constants.py` | `*_switches.cc`, `pref_names.h` | Tham số dòng lệnh và khoá thiết lập người dùng |
| `flags_metadata.py` | `flag-metadata.json` | Công tắc nào **sắp bị xoá** ở phiên bản tới |
| `webui_routes.py` | `route.ts` | Danh sách trang của màn hình `chrome://`, **kèm điều kiện hiển thị** |
| `webui_controls.py` | template `.html` | Từng điều khiển, **loại của nó**, và thiết lập nó gắn vào |
| `webui_gates.py` | `*_ui.cc` | Mắt xích nối điều kiện giao diện với công tắc |

#### Ba bộ đọc WebUI dùng chung cho mọi màn hình, không riêng Settings

`chrome://settings`, `chrome://history`, `chrome://downloads`, `chrome://bookmarks`, `chrome://extensions` và khoảng 130 màn hình `chrome://` khác **đều xây theo cùng một cách**: một trang web nằm dưới `chrome/browser/resources/`. Nên ba bộ đọc trên đọc được tất cả, không đóng khung riêng cho Settings. Hiện theo dõi 8 bề mặt, thêm một cái chỉ là thêm một dòng trong `targets.py`:

```
settings, history, downloads, bookmarks,
extensions, password_manager, new_tab_page, print_preview
```

Chi phí thêm: **~1,7 MB** cho cả 8 bề mặt, cộng 3,2 MB cho handler C++.

Chúng nối thành chuỗi ba chặng, và **phải đi đủ cả ba** mới ra kết luận đúng:

```
route.ts                          trang nào tồn tại
   ↓ bị canh bởi
loadTimeData key                  điều kiện hiển thị
   ↓ được gán giá trị ở
settings_ui.cc  →  base::Feature  công tắc thật
```

Dừng ở chặng đầu chính là rơi vào bẫy Local Network Access ở Phần 3.

Loại điều khiển nằm thẳng trong tên thẻ (`settings-toggle-button` là nút gạt, `settings-dropdown-menu` là danh sách xổ xuống, `cr-radio-group` là nhóm nút chọn), nên **"đổi dropdown thành select button" bắt được ngay** bằng phép so tên thẻ.

Hỗ trợ cho các bộ đọc C++ là `_cpp.py` — bộ quét văn bản C++. Nó làm ba việc mà nếu làm ẩu sẽ sai kết quả:

- **Che comment mà giữ nguyên độ dài file**, để số dòng báo cáo vẫn chính xác.
- **Cắt đối số cân bằng ngoặc**, bỏ qua ngoặc nằm trong chuỗi ký tự.
- **Đánh giá điều kiện tiền xử lý theo nền tảng.** Đây là phần quan trọng nhất — giải thích ngay dưới.

Và `jsonc.py` — bộ đọc JSON5 tự viết, vì Chromium dùng định dạng này (cho phép comment, khoá không cần nháy, dấu phẩy thừa) mà Python không có sẵn, và ta không được phép cài thêm thư viện.

#### Vì sao phải đọc điều kiện tiền xử lý

Chromium hay viết mặc định của một tính năng khác nhau theo hệ điều hành:

```cpp
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
```

Đọc thô ra "đang bật". Nhưng trên Android thực tế là "đang tắt". Chỉ trong một file, **14/187 tính năng có mặc định khác nhau theo nền tảng**.

Với một sản phẩm chỉ chạy trên Windows, đọc nhầm chỗ này không phải sai số nhỏ — nó **đảo ngược kết luận**. Nên `_cpp.py` có một bộ đánh giá điều kiện ba trạng thái: đúng / sai / **không xác định được**. Cái thứ ba quan trọng: khi điều kiện phụ thuộc vào thứ không phải nền tảng, công cụ trả lời "không xác định" thay vì đoán bừa.

### Nhóm 3 — So sánh và chấm điểm (`diff.py`, `sbprofile.py`, `impact.py`)

`diff.py` so hai ảnh chụp. Nó không so văn bản mà so **ý nghĩa**, dựa trên hai nguyên tắc:

**Nguyên tắc 1 — chỉ so những thuộc tính có ý nghĩa.** Giữa M139 và M143 mọi khai báo đều đổi cú pháp; nếu so cả thuộc tính "kiểu cú pháp" thì sinh ra hàng nghìn thay đổi vô nghĩa. Nên mỗi loại dữ liệu có danh sách trắng những thuộc tính đáng so.

**Nguyên tắc 2 — chấm theo nền tảng thật.** Một mặc định lật trên desktop mà không lật trên nền tảng bạn ship thì không phải thay đổi của bạn.

`diff.py` cũng gắn **nhãn ý nghĩa** cho từng thay đổi — đây là thứ biến "dòng code khác nhau" thành thông tin đọc được:

| Nhãn | Người dùng có thấy đổi? | Nghĩa |
|---|---|---|
| `default_flip_on` | **Có** | Công tắc lật sang bật |
| `web_api_shipped` | **Có** | API web đạt trạng thái ổn định |
| `ipc_signature_change` | **Có** | Chữ ký giao tiếp giữa tiến trình đổi — vỡ âm thầm lúc chạy |
| `flag_retired_on` | Không | Đã ship, công tắc gỡ đi, hành vi thành **vĩnh viễn không tắt được** |
| `flag_retired_off` | Không | Chưa từng ship, code gỡ đi, **không bật được nữa** |
| `feature_string_renamed` | Không, nhưng… | Tên Finch đổi — cấu hình phía server ngừng khớp trong im lặng |
| `pref_renamed` | Không, nhưng… | Khoá thiết lập đổi — giá trị đã lưu của mọi người dùng thành mồ côi |

Ba nhãn cuối là loại nguy hiểm nhất: **biên dịch sạch, test xanh, và hỏng ngoài thực địa**.

`diff.py` còn có cơ chế **nhận diện đổi tên**. Với thiết lập và tham số dòng lệnh, danh tính là chuỗi ký tự, còn tên biến C++ thì giữ nguyên. Nên một lần đổi tên hiện ra thành "một cái bị xoá, một cái mới thêm" chẳng liên quan gì nhau. Ghép cặp theo tên biến sẽ lộ ra bản chất — và hậu quả thật.

Đây là một ca có thật:

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);   // chữ r thường
// M143 — macro tự suy tên từ biến
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   tên chuỗi giờ là "FedCmIdPRegistration"                         // chữ R HOA
```

**Không ai sửa tên cả** — chính việc đổi macro đã đổi tên. Mọi cấu hình field-trial phía server và mọi cờ `--enable-features` dùng cách viết cũ giờ **âm thầm mất tác dụng**. Không lỗi biên dịch, không cảnh báo.

`sbprofile.py` là nửa còn lại: **fork của chúng ta phụ thuộc vào cái gì**. Chromium đổi cái gì đó chỉ quan trọng nếu ta có động tới. File này dựng "tập chạm" từ bất cứ bằng chứng nào đội đã có:

- Thư mục file `.patch` — dạng thường gặp của một fork
- `git diff --name-only` với bản gốc — nếu fork toàn bộ source
- Danh sách đường dẫn tự duy trì
- **Quét mã nguồn riêng của bạn** để tìm tham chiếu tới tên tính năng Chromium

Cách quét ở gạch đầu dòng cuối đáng nói riêng. Thay vì tìm tên Samsung trong cây Chromium khổng lồ, công cụ lấy **từ vựng của Chromium** (mọi tên tính năng, công tắc, thiết lập) rồi quét một lượt qua cây mã nhỏ của bạn. Đảo ngược bài toán từ "nhiều lượt qua cây khổng lồ" thành "một lượt qua cây nhỏ", và bắt được cả những chỗ code bạn *đọc* một tính năng mà không hề vá file khai báo nó.

Có một chi tiết tinh tế ở đây từng là lỗi: từ vựng phải dựng từ **cả hai** phiên bản. Nếu chỉ dựng từ bản mới, thì thứ vừa bị xoá sẽ không nằm trong từ vựng và bị lọc mất — mà đó chính là ca quan trọng nhất, ca làm vỡ build.

`impact.py` chấm điểm và phân loại. Điểm bắt đầu từ mức nghiêm trọng nội tại rồi cộng trừ theo bằng chứng, và **mỗi lần cộng trừ đều ghi lại lý do đọc được**:

```
base severity 75 (modified base_feature)
  | +12 we patch 1 of the declaring file(s): content/public/common/content_features.cc
  | +30 our source references ServiceWorkerAutoPreload, kServiceWorkerAutoPreload
  | +16 owned area 'Browser UI' (weight 80)
```

Lý do phải ghi lại: một bảng xếp hạng không ai cãi lại được là bảng xếp hạng bị bỏ qua ngay lần đầu nó sai. Ở đây điểm số còn quyết định AI tiêu ngân sách ngữ cảnh vào đâu, nên điểm không giải thích được sẽ lan thành khuyến nghị không giải thích được.

Kết quả chia bốn nhóm:

- **Must fix** — ta có tham chiếu tới nó VÀ nó đã đổi. Coi như có việc.
- **Needs review** — ta có động tới vùng đó, hoặc mức nghiêm trọng đủ cao để cần xác nhận.
- **New opportunity** — năng lực mới có thể lấy về. Quyết định sản phẩm, không phải rào cản kỹ thuật.
- **FYI** — ghi nhận cho đủ.

Chỉ **bằng chứng cấp tên ký hiệu** mới đẩy được lên Must fix. Bằng chứng cấp đường dẫn thì quá thô: `content_features.cc` khai báo gần 200 tính năng, nên biết bạn vá *file* đó gần như không nói lên điều gì.

### Nhóm 4 — Ngữ cảnh và báo cáo (`enrich/`, `ai/`, `report/`)

`enrich/chromestatus.py` lấy mô tả tính năng do người viết từ chromestatus.com. Ghép từng mục thì tỉ lệ trúng rất thấp (~2%) vì tên bên đó là văn xuôi còn tên trong mã là định danh. Nên thay vì cố ghép, công cụ đưa **cả danh sách "Chromium đã ship gì trong khoảng này" làm ngữ cảnh dùng chung** cho mọi request — khoảng 100 mục, tốn ~8k token, không đáng kể trong cửa sổ 200k, và bỏ hẳn được phép ghép mong manh.

`ai/` gồm bốn phần:

- `client.py` — nói chuyện HTTP thuần với endpoint nội bộ. Ba chế độ: `openai` (mọi endpoint tương thích: vLLM, TGI, Ollama, gateway nội bộ), `anthropic`, và `echo` — chế độ **không chạm mạng**, trả kết quả giả định để phát triển và demo offline. Báo cáo ghi rõ khi chế độ giả được dùng, để một lần chạy thử không bị nhầm là đã phân tích thật.
- `budget.py` — tính ngân sách token và đóng gói các bản ghi vào từng request.
- `prompts.py` — dựng câu lệnh cho model.
- `analyze.py` — chia việc thành các batch rồi tổng hợp.

Về `prompts.py` có một chủ ý đáng nói: prompt được thiết kế để **làm cho việc bịa đặt trở nên kém hấp dẫn**. Tên tính năng Chromium gợi hình đủ để model tự tin kể `PwaNavigationCapturing` làm gì chỉ từ cái tên. Nên mỗi bản ghi mang theo bằng chứng thật (trạng thái mặc định, chữ ký, tóm tắt chromestatus), hướng dẫn buộc trích dẫn bằng chứng đó, và **`unknown` là một câu trả lời hợp lệ hạng nhất**. Ở đây một câu trả lời sai đầy tự tin tốn của người review nhiều thời gian hơn là không trả lời.

Cách gộp batch cũng có một bài học: ban đầu tôi nhóm theo vùng chức năng để mỗi request là một chủ đề mạch lạc — nhưng quên gộp các nhóm nhỏ lại. Kết quả là 20 mục tốn 5 request, mỗi request 1.400 token trong khi ngân sách là 167.000. Sau khi sửa, **150 mục gói trong 1 request**.

`report/` sinh ba dạng đầu ra:

- `report.md` — dán thẳng vào ticket hoặc wiki
- `report.html` — bảng điều khiển lọc và sắp xếp được, **tự chứa hoàn toàn**, không tải tài nguyên ngoài nào, nên mở được trong mạng cách ly và gửi kèm mail được
- `report.json` — cho script và so sánh giữa các kỳ

---

## Phần 5. Sáu lệnh và mỗi lệnh làm gì

```bash
python3 -m chromedrift check      # kiểm tra máy có chạy được không
python3 -m chromedrift snapshot   # trích bề mặt tính năng của MỘT phiên bản
python3 -m chromedrift diff       # so ngữ nghĩa giữa HAI phiên bản
python3 -m chromedrift profile    # xem hồ sơ downstream giải ra cái gì
python3 -m chromedrift run        # chạy toàn bộ: snapshot → diff → chấm điểm → AI → báo cáo
python3 -m chromedrift report     # dựng lại báo cáo, lọc được theo vùng
```

Riêng `report` có hai tuỳ chọn đáng nhớ, giải thích kỹ ở Phần 6:

```bash
python3 -m chromedrift report out/report.json --list-areas       # có những vùng nào
python3 -m chromedrift report out/report.json --area downloads   # cắt lát cho 1 đội
```

Tách thành sáu lệnh không phải để trang trí. Bước đắt (tải về) và bước bạn chỉnh đi chỉnh lại (chấm điểm, prompt, báo cáo) có chi phí hoàn toàn khác nhau. Chạy lại được nửa rẻ trên cache ấm là khác biệt giữa một công cụ người ta tinh chỉnh và một công cụ người ta chạy đúng một lần.

`check` đáng nói riêng: nó kiểm mọi thứ thường hỏng trên máy mới **một lượt**, thay vì để bạn phát hiện từng cái sau hai phút chạy — phiên bản Python, quyền ghi thư mục cache, ba host mạng, biến proxy, hồ sơ có đọc được không, và **gọi thử một request thật** tới endpoint AI.

### Chạy đầy đủ

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --platform Windows \
  --profile config/sb-profile.json5 \
  --llm config/llm.json5 \
  --out out/M148_to_M151
```

Hai tuỳ chọn quan trọng:

**`--platform` không phải để trang trí.** Nếu bỏ qua, bạn đọc mặc định toàn cục thay vì mặc định trên nền tảng mình ship, và có thể ra kết luận ngược.

**Luôn ghi phiên bản đầy đủ, đừng dùng số milestone trần.** `151` sẽ giải ra bản stable mới nhất *tại thời điểm chạy*, và nó trôi. Ví dụ thật: `ServiceWorkerAutoPreload` BẬT ở `143.0.7499.40` nhưng TẮT ở `143.0.7499.194` — cùng milestone, khác bản vá, vì bị revert. Hai lần chạy cách nhau vài tuần có thể cho kết luận khác nhau và cả hai đều đúng.

### Kết quả thật

Chạy M148 → M151 cho Windows:

```
1 phút 36 giây
24.638 facts trích được
2.783 thay đổi có ý nghĩa

must fix:        0     (vì chưa cấu hình hồ sơ downstream thật)
needs review:  365
opportunity: 1.141
fyi:           994
```

Lưu ý dòng `must fix: 0`: nó có nghĩa là **chưa cung cấp bằng chứng**, không phải "bản nâng cấp này sạch". Không có hồ sơ trỏ vào patch hoặc source thật thì không mục nào lên được Must fix, và báo cáo có ghi rõ điều đó.

---

## Phần 6. Chia việc theo vùng — và cái bẫy thứ hai

Khi mở rộng ra nhiều mảng (Download, Bookmark, History, Add-ons, Settings…), câu hỏi tự nhiên là: *"làm sao giới hạn để AI khỏi phải xử lý quá nhiều?"*

Tôi đã đo trước khi làm, và **giả định đó sai**.

### AI không phải nút thắt

```
Gửi TOÀN BỘ 2.226 findings   ≈ 189.000 token
Cửa sổ ngữ cảnh              = 200.000 token
=> chỉ cần 2 request
```

Trước đó công cụ mặc định cắt còn 150 mục (26k token) — tức chỉ dùng **14%** khả năng. Cắt bớt để "tiết kiệm AI" là giải quyết một vấn đề không tồn tại. Mặc định đó đã bỏ.

Nút thắt thật là **thời gian đọc của con người**. 2.226 dòng thì không ai đọc hết.

### Cái bẫy: lọc trước khi phân tích sẽ mất phần quan trọng nhất

Cách làm tự nhiên là lọc ngay từ đầu: *"lần này chỉ phân tích Download thôi"*. Tôi thử và đo:

```
Định nghĩa vùng chỉ theo tính năng sản phẩm:
  1.802 / 2.226 findings  (81%)  KHÔNG khớp vùng nào
  trong đó 281 mục điểm >= 60
  và cả 10 mục điểm cao nhất toàn báo cáo đều nằm trong nhóm này
```

10 mục cao nhất là `CreateLanguageModel`, `CreateSummarizer`, `AttachDevToolsSession`… — Mojo đổi chữ ký, 80 điểm, vỡ âm thầm lúc chạy. Chúng **không thuộc tính năng sản phẩm nào** vì chúng là hạ tầng dùng chung.

Lọc theo vùng sản phẩm sẽ vứt sạch phần đầu danh sách.

### Giải pháp: phân tích hết, lọc lúc đọc

| | Lọc đầu vào (sai) | Lọc đầu ra (đã làm) |
|---|---|---|
| Phân tích | chỉ vùng đã chọn | **luôn phân tích hết** |
| Chi phí | tiết kiệm không đáng kể | 2 request |
| Rủi ro | mất 281 mục điểm cao | không mất gì |
| Đổi vùng | phải chạy lại toàn bộ | dựng lại tức thì, không gọi AI |

```bash
# Phân tích một lần — report.json luôn chứa TẤT CẢ
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --platform Windows \
  --profile config/sb-profile.json5

# Xem có những vùng nào
python3 -m chromedrift report out/report.json --list-areas

# Cắt lát cho từng đội — không chạy lại, không gọi AI lần nữa
python3 -m chromedrift report out/report.json --area downloads --out downloads
python3 -m chromedrift report out/report.json --area ipc       --out ipc
```

### Ba loại vùng, không phải một

Đây là chỗ quyết định chất lượng. Định nghĩa vùng có ba loại, khai bằng trường `kind`:

- **`product`** — có đội sở hữu rõ ràng: Downloads, Bookmarks, History, Extensions, Media
- **`infra`** — hạ tầng cắt ngang, không thuộc tính năng nào nhưng **chứa các mục nghiêm trọng nhất**: Mojo, Web IDL
- **`platform`** — nền chung: cờ tính năng, pref, tham số dòng lệnh

Chỉ định nghĩa loại `product` là sai lầm kinh điển — chính là kết quả 81% ở trên.

Và mỗi vùng khớp được bằng **năm cách**, chỉ cần trúng một là nhận:

```json5
{
  id: "downloads",
  kind: "product",
  owner: "downloads-team",
  paths:   ["components/download/", "chrome/browser/download/"],  // tiền tố đường dẫn
  symbols: ["Download"],                                          // khớp chuỗi con trong tên
  prefs:   ["download."],                                         // tiền tố khoá thiết lập
  flags:   ["kDownload", "kParallelDownload"],                    // tiền tố tên cờ
  kinds:   [],                                                    // sở hữu trọn một loại dữ liệu
}
```

Cần năm cách vì Chromium không tổ chức code theo tính năng sản phẩm: "Download" nằm rải ở `components/`, `chrome/browser/`, `content/`, cộng thêm pref, cờ và Mojo.

### Kết quả sau khi làm

Với định nghĩa đủ ba loại vùng, phần không thuộc vùng nào **giảm từ 1.802 xuống 190** (81% → 8,5%):

```
flags         882 findings,   9 actionable  [release-team]
webapi        768 findings,  83 actionable  [webplatform-team]
settings      169 findings, 125 actionable  [settings-team]
media         135 findings,  23 actionable  [media-team]
ipc           112 findings,  51 actionable  [platform-team]
network        95 findings,  15 actionable  [network-team]
extensions     35 findings,  13 actionable  [extensions-team]
downloads      16 findings,   3 actionable  [downloads-team]
bookmarks       8 findings,   0 actionable  [bookmarks-team]
history         4 findings,   0 actionable  [history-team]
(no area)     190 findings,  53 actionable, 50 scoring 60+   ← chưa có chủ
```

### Luật bắt buộc: phần thừa phải hiện ra

Dòng cuối là phần quan trọng nhất của thiết kế này. Chia vùng mà **im lặng nuốt phần không khớp** là cách chắc chắn nhất để bỏ lọt lỗi.

Nên công cụ **luôn in con số đó**, và cảnh báo khi trong đó có mục điểm cao:

```
⚠️ 50 unassigned findings score 60 or more (highest: 87). These belong to no
   area, so no per-area report shows them. Either extend the area definitions
   or review this set explicitly.
```

Xem được luôn bằng `--area _unassigned`. Con số này cũng là **thước đo chất lượng định nghĩa vùng**: 190 mục còn lại đều là cờ tầng content (accessibility, một số tính năng Android) — danh sách đó chính là chỉ dẫn để bổ sung vùng tiếp theo.

---

## Phần 7. Gom mảnh vụn thành một câu chuyện

Một thay đổi của Chromium không bao giờ đến gọn một chỗ. Nó vỡ thành nhiều mảnh rải trên mọi bề mặt mà công cụ đọc.

Ca Local Network Access sinh ra **đúng 7 mảnh**:

```
webui_route    SITE_SETTINGS_LOCAL_NETWORK_ACCESS         bị xoá
webui_route    SITE_SETTINGS_LOCAL_NETWORK                đổi điều kiện canh
webui_gate     enableLocalNetworkAccessSplitPermissions   bị xoá
webui_gate     enableLocalNetworkAccessSetting            đổi biểu thức
webui_control  label:siteSettingsLocalNetworkAccess       bị xoá
base_feature   LocalNetworkAccessChecksSplitPermissions   cờ đã ship rồi gỡ
blink_runtime  LocalNetworkAccessSplitPermissions         cờ thử nghiệm bỏ
```

Đọc rời từng dòng thì chúng **mâu thuẫn nhau**: dòng trên nói một trang bị xoá, dòng dưới nói một trang xuất hiện. Đọc thành một cụm thì nó nói một điều đơn giản và đúng: *trang chuyển sang mô hình tách quyền, người dùng đã có từ M148, việc duy nhất là cập nhật tham chiếu đường dẫn cũ*.

### Gom bằng quan hệ thật, không bằng tên giống nhau

Đây là điểm tôi cho là quan trọng. Cách dễ nhất là gom theo tiền tố tên (`kLocalNetworkAccess*`), nhưng đó là phỏng đoán. Công cụ gom bằng **liên kết mà chính dữ liệu đã khai**:

```
route  --khai tên guard-->  gate  --khai tên feature-->  base_feature
control  --khai label-->  route
feature_param  --khai feature cha-->  base_feature
blink  --khai base_feature-->  base_feature
```

Mỗi mũi tên là một trường dữ liệu có thật, không phải suy đoán. Kết quả là cụm chính xác chứ không phải gần đúng.

### Chỗ cố tình không gom

Mảnh thứ 7 — `blink_runtime LocalNetworkAccessSplitPermissions` — **đứng riêng**, và đó là đúng. Fact của nó khai rõ:

```json5
{ name: "LocalNetworkAccessSplitPermissions", base_feature: "none" }
```

Chromium nói thẳng: cờ này **không có** feature C++ tương ứng. Tên nó gần giống `LocalNetworkAccessChecksSplitPermissions` nhưng "gần giống" không phải là quan hệ. Nối vào sẽ là bịa ra một liên kết mà nguồn phủ nhận. Công cụ để nó riêng lẻ.

Trên lần chạy thật M148 → M151: **25 cụm**, lớn nhất 7 mảnh. Báo cáo có hẳn mục *"Related changes, grouped"* xếp theo điểm cao nhất trong cụm.

---

## Phần 8. Target set đã đủ chưa — bằng chứng, không phải khẳng định

Câu hỏi đúng nhất có thể hỏi về công cụ này. Tôi đã đo hai lần và **cả hai lần đều phát hiện thiếu nghiêm trọng**.

### Lần 1 — thiếu 45% feature flag

Danh sách file ban đầu tôi chọn theo *tầng* mà trình duyệt nhúng (`content/`, `net/`, `media/`, `blink/`), và **quên mất tầng của chính trình duyệt**. Đo tại M151 những file khai báo `base::Feature` **không** nằm trong danh sách:

```
247  chrome/common/chrome_features.cc          ← file feature cấp Chrome quan trọng nhất
126  content/common/features.cc
101  components/omnibox/common/omnibox_features.cc
 57  extensions/common/extension_features.cc
 47  components/sync/base/features.cc
 41  components/segmentation_platform/public/features.cc
 28  components/optimization_guide/...
 ... và các file nhỏ hơn
────
964  base::Feature không được theo dõi
```

So với 1.190 đang có thì **thiếu khoảng 45%**. Một khoảng trống cỡ đó **không hiện ra như một khoảng trống trong báo cáo — nó hiện ra như một bản nâng cấp yên ả.**

Sau khi bổ sung 13 file: **base_feature 1.190 → 2.054**, tổng thay đổi 2.504 → 2.783.

### Lần 2 — thiếu 23% template, và gần hết ở đúng bề mặt cần

Chromium đang chuyển WebUI từ Polymer (`.html`) sang Lit (`.html.ts`), và **chuyển không đều**. Đo tại M151:

| bề mặt | `.html` | `.html.ts` (Lit) |
|---|---:|---:|
| settings | 243 | 6 |
| password_manager | 47 | 0 |
| new_tab_page | 32 | 7 |
| **extensions** | 2 | **33** |
| **print_preview** | 2 | **32** |
| **history** | 2 | **12** |
| **bookmarks** | 2 | **8** |
| **downloads** | 2 | **4** |

Nhìn riêng settings thì chỉ sót 2% — nên nếu chỉ kiểm settings sẽ kết luận "ổn". Nhìn cả 8 bề mặt thì sót **23%**, và **bốn bề mặt quan trọng nhất — extensions, history, bookmarks, downloads — gần như sót hoàn toàn**.

Lit đặt template trong một chuỗi TypeScript, ràng buộc khác hẳn:

```ts
export function getHtml(this: DownloadsItemElement) {
  return html`
    <cr-toggle id="deepScan" ?checked="${this.isChecked_}" @change="${this.onToggle_}">
    <settings-toggle-button .pref="${this.prefs.download.bubble_enabled}">
  `;
}
```

So với Polymer: `?attr=` thay cho attribute boolean, `.prop=` thay cho property, `@event=` cho sự kiện, và `${this.prefs.x}` thay cho `{{prefs.x}}`. Bộ đọc giờ hiểu cả hai. Kết quả: **webui_control 633 → 761**, trong đó **128 điều khiển đến từ file Lit** mà trước đây không thấy gì.

### Một lỗi cache lộ ra khi sửa

Thêm `.html.ts` vào bộ lọc xong chạy lại thì **số fact không nhúc nhích**. Nguyên nhân: marker cache của cây chỉ khoá theo đường dẫn, không tính bộ lọc — nên nó tưởng đã tải rồi và bỏ qua. Snapshot dựng lại, con số không đổi, **không có gì báo lỗi**. Nay marker gồm cả hash của bộ lọc.

### Cách tự kiểm khoảng trống

Danh sách file là **được chọn thủ công, không phải vét cạn**. Kiểm bằng cách lấy một file feature bất kỳ nghi là thiếu rồi đếm:

```bash
python3 - <<'EOF'
import urllib.request, base64, re
p = 'chrome/common/chrome_features.cc'      # đổi đường dẫn cần kiểm
u = f'https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.138/{p}?format=TEXT'
r = urllib.request.Request(u, headers={'User-Agent':'check'})
s = base64.b64decode(urllib.request.urlopen(r).read()).decode('utf8','replace')
print(p, len(re.findall(r'\bBASE_FEATURE\s*\(', s)), 'features')
EOF
```

Rồi đối chiếu với `chromedrift/targets.py`. Thiếu thì thêm một dòng.

---

## Phần 9. Cái chưa có — và cái cố ý không làm

Nói rõ để không ai đọc báo cáo sạch rồi tưởng bản nâng cấp sạch. Hai loại khác nhau: *chưa làm* (có thể làm, chỉ là chưa) và *cố ý không làm* (đánh đổi có chủ ý).

### 8.1 CHƯA LÀM — các màn hình `chrome://` khác

Công cụ đang theo dõi 8 bề mặt. Chromium có 132 thư mục dưới `chrome/browser/resources/`, nhưng con số đó gây hiểu nhầm. Đếm kỹ:

```
132  tổng
  8  đang theo dõi     settings, history, downloads, bookmarks,
                       extensions, password_manager, new_tab_page, print_preview
 39  trang debug       chrome://net-internals, chrome://discards, chrome://device-log...
                       → người dùng KHÔNG BAO GIỜ thấy
  9  chỉ ChromeOS      ash, help_app, input_ime...
                       → sản phẩm Windows không compile
 76  còn lại, trong đó ~29 đáng cân nhắc
```

**Con số thật là ~29, không phải 130.**

Đáng cân nhắc thêm: `autofill, browser_switch, certificate_manager, compose, default_browser, enterprise, feedback, lens, management, media, media_router, pdf, search_engine_choice, shopping, side_panel, signin, tab_search, toolbar, wallet, webauthn, whats_new`...

**Thêm cụ thể là dòng nào.** Trong `chromedrift/targets.py`:

```python
WEBUI_SURFACES = (
    "settings",
    "history",
    ...
    "pdf",        # ← thêm dòng này là xong
)
```

Không cần viết parser mới, không sửa gì khác — ba bộ đọc đã tổng quát cho mọi bề mặt và tự nhận file mới.

**Vì sao không thêm hết luôn.** Vì nút thắt là *thời gian đọc của người*, không phải chi phí máy (8 bề mặt chỉ tốn 1,7 MB). Thêm `chrome://net-internals` chỉ làm dài danh sách chứ không ai quan tâm. Chọn theo nhu cầu thật tốt hơn là bật hết.

### 8.2 CỐ Ý KHÔNG LÀM — logic TypeScript

Mỗi trang WebUI có hai file song song:

```
downloads_page.html   ← ĐỌC   khai báo: có điều khiển nào, loại gì, gắn pref nào
downloads_page.ts     ← BỎ    hành vi:  khi nào hiện, bấm vào thì làm gì
```

**Ví dụ thật ở M151.** Trong `.html` công cụ đọc được:

```html
<template is="dom-if" if="[[autoOpenDownloads_]]" restamp>
    ... nút "Xoá tất cả" ...
</template>
```

Công cụ biết: *có một khối bị canh bởi điều kiện tên `autoOpenDownloads_`*.

Trong `.ts` công cụ không đọc:

```ts
autoOpenDownloads_: boolean;
autoOpenDownloads_ = autoOpen;    // autoOpen là trạng thái lúc chạy
```

Công cụ **không biết** khi nào điều kiện đó đúng — nó phụ thuộc người dùng có đặt loại file tự mở hay không, tức trạng thái runtime chứ không phải khai báo.

**Quy mô điểm mù.** Đo trên 332 file template của 8 bề mặt:

```
602  khối điều kiện <template is="dom-if"> / dom-repeat
460  ràng buộc hidden="[[...]]"
37%  điều khiển nằm trong một khối điều kiện
```

Khoảng **một phần ba điều khiển** có điều kiện hiển thị mà công cụ không giải được.

**Bắt được gì, sót gì:**

| | |
|---|---|
| Thêm/bớt một điều khiển | ✅ |
| Đổi loại điều khiển (dropdown → toggle) | ✅ |
| Đổi pref mà điều khiển ghi vào | ✅ |
| Thêm/bớt trang, đổi điều kiện canh **trang** | ✅ |
| Đổi logic quyết định khi nào **điều khiển** hiện | ❌ |
| Đổi việc bấm nút thì làm gì | ❌ |
| Đổi cách sắp xếp, lọc danh sách | ❌ |

**Ba lý do cố ý bỏ:**

1. **Đọc logic là phân tích luồng dữ liệu, không phải quét cú pháp.** Để biết `autoOpenDownloads_` khi nào đúng phải lần theo callback, và cả trạng thái từ C++ gửi sang. Nó sẽ sai ngay khi Chromium viết lại một hàm.
2. **Phá vỡ nguyên tắc "không cần tải Chromium về".** Phần khai báo vài MB; đọc logic thì phải kéo cả cây TypeScript, và vẫn không đủ vì logic nối sang C++.
3. **Nhất quán với tầng C++.** Công cụ cũng không đọc thân hàm C++ — chỉ đọc macro khai báo. Đọc được logic một bên thì phải đọc cả hai, và lúc đó nó thành một compiler chứ không còn là công cụ 40 MB chạy trong 90 giây.

**Cái gì bù lại.** Chuỗi `route → guard → flag` bù được phần quan trọng nhất: điều kiện hiển thị ở cấp **trang**, vì Chromium khai nó dưới dạng `loadTimeData` chứ không phải logic. Đó là lý do ca Local Network Access truy được đến tận cùng. Phần không bù được là điều kiện ở cấp **điều khiển bên trong trang** — chỗ đó chỉ **so sánh ảnh chụp giao diện** mới trả lời được, đúng vai trò kiểm chứng cuối như mô tả ở Phần 6.

### 8.3 Các giới hạn còn lại

- **Thay đổi nằm hoàn toàn trong thân hàm C++.** Cùng lý do như 8.2, ở tầng khác.
- **So sánh fork với Chromium.** Công cụ so upstream với upstream. `--profile` là *đối chiếu bằng chứng* (mã của ta có nhắc tới ký hiệu này không), không phải diff giữa fork và bản gốc.
- **Mọi thứ ngoài repo:** cấu hình Finch phía server, script khởi chạy, hệ thống test tự động.
- **Giao diện đã render.** Không ảnh chụp, không bố cục, không phát hiện lỗi hiển thị.

---

## Phần 10. Skill cho agent

Thư mục `skills/analyzing-chromium-uprevs/` là gói kiến thức để đưa lên agent nội bộ, viết theo chuẩn Agent Skills chính thức:

```
SKILL.md                          quy trình + checklist + con trỏ
reference/signals.md              bảng tra nhãn và ý nghĩa
reference/traps.md                8 cái bẫy đã kiểm chứng bằng dữ liệu thật
reference/settings-surface.md     nguồn settings và cách xác định độ lớn tính năng
```

Agent chỉ nạp `SKILL.md` khi cần, và chỉ đọc file tham chiếu khi thật sự dùng tới.

Phần giá trị nhất của skill không phải hướng dẫn chạy lệnh, mà là **kiến thức ngăn agent kết luận sai** — vòng đời công tắc, ba mốc thời gian, và tám cái bẫy kèm số liệu thật.

---

## Phần 11. Kiểm thử

```bash
python3 -m unittest discover -s tests
```

**100 bài kiểm thử, chạy trong khoảng 60 mili giây, không cần mạng.** Đã chạy trên macOS (Python 3.14), Ubuntu 24.04 (3.12) và Debian (3.9) — kết quả trùng khớp từng con số.

Dữ liệu thử là trích đoạn rút gọn nhưng đúng cấu trúc của file Chromium thật, gồm cả những dạng khó từng làm hỏng các phiên bản parser trước: macro hai tham số, mặc định bọc trong điều kiện tiền xử lý, trạng thái theo từng nền tảng.

Nên chạy lại sau mỗi lần sửa `diff.py` hoặc `impact.py` — đó là hai chỗ chứa các quyết định phân loại.

### Đối chứng với dữ liệu thật

Test đơn vị chỉ chứng minh code làm đúng cái tôi nghĩ. Để kiểm xem nó có đúng *thực tế* không, tôi viết lại bộ trích bằng **phương pháp khác hẳn** (bỏ hết chỉ thị tiền xử lý, tách theo dấu `;`, regex khác) rồi so trên `content_features.cc` giữa M148 và M151:

```
Phương pháp độc lập :  19 thêm,  9 bỏ
Công cụ báo         :  19 thêm,  8 bỏ

Mục thêm  : khớp 19/19, không sót, không thừa
Mục bỏ    : lệch 1  —  AndroidEnableBackgroundMediaCapturing
```

Truy mục lệch đó thì hoá ra **công cụ đúng, phép đối chứng của tôi sai**: feature không bị xoá mà **chuyển từ `content_features.cc` sang `media_switches.cc`**, và công cụ báo đúng là `declaration_moved` (mức 25, thấp). Phép đối chứng chỉ nhìn một file nên không thấy.

Nói cách khác: **0 sai lệch thật**, và ở mục duy nhất khác nhau thì công cụ chính xác hơn cách kiểm.

---

## Phần 12. Cấu trúc mã nguồn

```
chromedrift/
  acquire.py      364 dòng   tải nguồn qua Gitiles hoặc từ checkout local
  targets.py      109        khai báo tải file nào, kèm lý do
  snapshot.py     104        gộp tải + trích xuất thành một ảnh chụp có cache
  extract/        1.822      9 bộ đọc + tiện ích quét C++
  diff.py         556        so sánh ngữ nghĩa, 35 nhãn, nhận diện đổi tên
  cluster.py      196        gom mảnh vụn thành một câu chuyện
  sbprofile.py    455        tập chạm của fork + định nghĩa vùng (5 cách khớp)
  impact.py       235        chấm điểm, phân loại, và báo cáo độ phủ vùng
  model.py        396        cấu trúc dữ liệu dùng chung, đọc/ghi JSON, lọc theo vùng
  jsonc.py        259        bộ đọc JSON5 tự viết
  ai/             845        ngân sách ngữ cảnh, client, prompt, map-reduce
  report/         616        markdown + bảng điều khiển HTML tự chứa
  enrich/         175        ngữ cảnh từ chromestatus
  cli.py          512        6 lệnh dòng lệnh
```

Mỗi tầng đọc và ghi JSON, nên tầng nào cũng chạy, kiểm tra và chạy lại độc lập được.

---

## Phần 13. Đọc thêm

- **[HANDOFF.md](HANDOFF.md)** — danh sách việc cần chạy tại công ty, trên máy có source SB và mạng nội bộ. Có checkbox theo dõi tiến độ, lệnh copy-paste, và mẫu báo cáo lại. Đây là những việc không làm được từ bên ngoài.
- **[SETUP.md](SETUP.md)** — hướng dẫn A–Z cài đặt trên máy mới: yêu cầu, cấu hình hồ sơ theo bốn cách, cấu hình AI nội bộ, proxy, mạng cách ly, và bảng xử lý sự cố lấy từ lỗi thật.
- **[skills/analyzing-chromium-uprevs/SKILL.md](skills/analyzing-chromium-uprevs/SKILL.md)** — gói kiến thức cho agent.
