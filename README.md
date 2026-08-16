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

Nhờ vậy, với cửa sổ ngữ cảnh 200k, **150 mục gói gọn trong 1 request khoảng 26k token** — thay vì hàng trăm request nếu đưa mã nguồn thô vào.

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

Toàn bộ là **Python thuần, 6.346 dòng, 31 file**, không dùng thư viện ngoài nào. Không cần `pip install`, không cần môi trường ảo, không cần quyền quản trị. Lý do: môi trường triển khai thường là mạng nội bộ công ty, nơi thêm một package là cả một quy trình phê duyệt.

Cộng thêm **1.228 dòng tài liệu** và **60 bài kiểm thử** chạy offline.

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

Hỗ trợ cho cả sáu là `_cpp.py` — bộ quét văn bản C++. Nó làm ba việc mà nếu làm ẩu sẽ sai kết quả:

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
python3 -m chromedrift report     # dựng lại báo cáo từ report.json đã có
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
22.109 facts trích được
2.226 thay đổi có ý nghĩa

must fix:        0     (vì chưa cấu hình hồ sơ downstream thật)
needs review:  191
opportunity: 1.035
fyi:         1.000
```

Lưu ý dòng `must fix: 0`: nó có nghĩa là **chưa cung cấp bằng chứng**, không phải "bản nâng cấp này sạch". Không có hồ sơ trỏ vào patch hoặc source thật thì không mục nào lên được Must fix, và báo cáo có ghi rõ điều đó.

---

## Phần 6. Cái chưa có

Nói rõ để không ai đọc báo cáo sạch rồi tưởng bản nâng cấp sạch.

- **Thay đổi nằm hoàn toàn trong thân hàm.** Công cụ đọc *khai báo*, không đọc logic. Một thay đổi hành vi không đụng khai báo nào sẽ không hiện ra. Đây là đánh đổi có chủ ý để bỏ được việc tải 100 GB.
- **Giao diện Settings.** Thư mục `chrome/browser/resources/settings/` **không** nằm trong danh sách tải, nên một lần chạy sinh ra **0 dữ liệu về trang settings**. Nếu câu hỏi là "trang settings nào đổi", công cụ **chưa** trả lời được — phải nói thẳng điều đó thay vì suy từ danh sách công tắc.
- **So sánh fork với Chromium.** Công cụ so upstream với upstream. Tuỳ chọn `--profile` là *đối chiếu bằng chứng* (mã của ta có nhắc tới ký hiệu này không), không phải diff giữa fork và bản gốc.
- **Mọi thứ ngoài repo:** cấu hình Finch phía server, script khởi chạy, hệ thống test tự động.
- **Giao diện đã render.** Không ảnh chụp, không bố cục, không phát hiện lỗi hiển thị.

---

## Phần 7. Skill cho agent

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

## Phần 8. Kiểm thử

```bash
python3 -m unittest discover -s tests
```

**60 bài kiểm thử, chạy trong khoảng 60 mili giây, không cần mạng.** Đã chạy trên macOS (Python 3.14), Ubuntu 24.04 (3.12) và Debian (3.9) — kết quả trùng khớp từng con số.

Dữ liệu thử là trích đoạn rút gọn nhưng đúng cấu trúc của file Chromium thật, gồm cả những dạng khó từng làm hỏng các phiên bản parser trước: macro hai tham số, mặc định bọc trong điều kiện tiền xử lý, trạng thái theo từng nền tảng.

Nên chạy lại sau mỗi lần sửa `diff.py` hoặc `impact.py` — đó là hai chỗ chứa các quyết định phân loại.

---

## Phần 9. Cấu trúc mã nguồn

```
chromedrift/
  acquire.py      364 dòng   tải nguồn qua Gitiles hoặc từ checkout local
  targets.py      109        khai báo tải file nào, kèm lý do
  snapshot.py     104        gộp tải + trích xuất thành một ảnh chụp có cache
  extract/        1.361      6 bộ đọc + tiện ích quét C++ + bộ đọc JSON5
  diff.py         482        so sánh ngữ nghĩa, gắn nhãn, nhận diện đổi tên
  sbprofile.py    392        dựng tập chạm của fork từ patch/git/quét mã
  impact.py       189        chấm điểm và phân loại, kèm lý do đọc được
  model.py        367        cấu trúc dữ liệu dùng chung, đọc/ghi JSON
  jsonc.py        259        bộ đọc JSON5 tự viết
  ai/             845        ngân sách ngữ cảnh, client, prompt, map-reduce
  report/         554        markdown + bảng điều khiển HTML tự chứa
  enrich/         175        ngữ cảnh từ chromestatus
  cli.py          454        6 lệnh dòng lệnh
```

Mỗi tầng đọc và ghi JSON, nên tầng nào cũng chạy, kiểm tra và chạy lại độc lập được.

---

## Phần 10. Đọc thêm

- **[SETUP.md](SETUP.md)** — hướng dẫn A–Z cài đặt trên máy mới: yêu cầu, cấu hình hồ sơ theo bốn cách, cấu hình AI nội bộ, proxy, mạng cách ly, và bảng xử lý sự cố lấy từ lỗi thật.
- **[skills/analyzing-chromium-uprevs/SKILL.md](skills/analyzing-chromium-uprevs/SKILL.md)** — gói kiến thức cho agent.
