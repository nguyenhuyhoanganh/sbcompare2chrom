# chromedrift

Công cụ so sánh hai phiên bản Chromium và trả lời một câu hỏi: **đội làm trình duyệt downstream cần sửa những gì khi nâng nền.**

Sản phẩm đích là Samsung Browser bản desktop trên Windows. Toàn bộ là Python thuần (10.180 dòng, 33 file), không dùng thư viện ngoài nào, không cần `pip install`.

Ngoài file này chỉ còn một tài liệu nữa: **[docs/pipeline.html](docs/pipeline.html)** — mở bằng trình duyệt, không cần mạng — đi theo một thay đổi có thật qua từng bước của đường ống, kèm định nghĩa thuật ngữ và cách so sánh từng loại tệp. README này nói dự án là gì và dùng thế nào; `pipeline.html` nói bên trong nó chạy ra sao.

---

## Mục lục

1. [Vấn đề](#1-vấn-đề)
2. [Bắt đầu nhanh](#2-bắt-đầu-nhanh)
3. [Cái bẫy quan trọng nhất](#3-cái-bẫy-quan-trọng-nhất)
4. [Công cụ đọc những gì](#4-công-cụ-đọc-những-gì)
5. [Độ phủ: đọc được bao nhiêu cây nguồn](#5-độ-phủ-đọc-được-bao-nhiêu-cây-nguồn)
6. [Chín lệnh](#6-chín-lệnh)
7. [Hồ sơ downstream](#7-hồ-sơ-downstream)
8. [Đọc báo cáo](#8-đọc-báo-cáo)
9. [Giới hạn](#9-giới-hạn)
10. [Môi trường và xử lý sự cố](#10-môi-trường-và-xử-lý-sự-cố)
11. [Kiểm thử](#11-kiểm-thử)
12. [Cấu trúc mã nguồn](#12-cấu-trúc-mã-nguồn)

---

## 1. Vấn đề

Cứ vài phiên bản, đội lại nâng nền Chromium lên một mốc mới — ví dụ từ M148 lên M151. Mỗi lần như vậy có ba câu hỏi phải trả lời:

- Chromium **thêm** gì mới?
- Chromium **bỏ** gì đi?
- Cái gì **vẫn còn nhưng đổi cách hoạt động**?

Nếu tải hai bản Chromium về rồi chạy `git diff`, kết quả là vài triệu dòng khác nhau. Phần lớn không liên quan: đổi tên biến, dọn code, sửa chính tả trong comment, cập nhật thư viện bên thứ ba. Đọc hết thì không khả thi, đọc lướt thì bỏ sót đúng cái quan trọng.

Nên vấn đề thật không phải "làm sao so được", mà là **"làm sao lọc ra đúng phần có nghĩa"**. Đó là việc chromedrift làm.

### Ba nguyên tắc thiết kế

**Không cần tải Chromium về.** Một bản đầy đủ nặng khoảng 100 GB và mất vài giờ đồng bộ. Công cụ chỉ cần vài nghìn file khai báo — những file liệt kê "có gì, tên gì, mặc định bật hay tắt". Chromium cho tải riêng từng thư mục qua Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<phiên-bản>/<thư-mục>.tar.gz
```

Khoảng 40 MB mỗi phiên bản với target set mặc định. Đội nào đã có checkout hoặc mirror nội bộ thì dùng `--local-src`, phần còn lại không đổi.

**Chuẩn hoá trước, so sánh sau.** Giữa M139 và M143, Chromium đổi cách viết macro khai báo tính năng:

```cpp
// M139 trở về trước
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);

// M142 trở đi — tên chuỗi tự suy ra từ tên biến
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
```

Chỉ trong một file, M139 có 170/170 khai báo kiểu cũ, M143 có 12/187. Công cụ so theo văn bản mã nguồn sẽ báo "170 tính năng bị xoá, 187 tính năng mới" — vô nghĩa. chromedrift chuẩn hoá `kBackForwardCache` thành `"BackForwardCache"` trước khi so, và cho kết quả đọc được: 152 giữ nguyên, 18 bị bỏ, 35 thêm mới.

**Dừng ở bằng chứng.** Các bước tất định — trích xuất, chuẩn hoá, so sánh, chấm điểm — lọc từ vài nghìn thay đổi xuống còn vài trăm mục đáng chú ý, rồi dừng. Công cụ không kết luận "cái này có nghĩa gì với sản phẩm". Đó là phần cần suy xét, thuộc về người đọc báo cáo hoặc về agent chạy skill [`analyzing-chromium-uprevs`](skills/analyzing-chromium-uprevs/SKILL.md). Việc của chromedrift là làm cho đầu vào ấy đầy đủ, có xếp hạng và trích dẫn được.

---

## 2. Bắt đầu nhanh

### Yêu cầu

| Hạng mục | Yêu cầu |
|---|---|
| Python | 3.9 trở lên. Không dùng cú pháp 3.10+. Đã chạy trên 3.14.6 |
| Thư viện ngoài | Không có. Chỉ stdlib |
| Đĩa trống | ~150 MB cho hai phiên bản với target set mặc định |
| Mạng | Ba host HTTPS, xem bảng dưới. Bỏ được hết nếu dùng checkout nội bộ |
| Chromium checkout | Không cần |

| Host | Dùng để | Bắt buộc |
|---|---|---|
| `chromium.googlesource.com` | Tải mã nguồn theo tag | Có |
| `chromiumdash.appspot.com` | Phân giải `151` → `151.0.7922.138` | Không, nếu luôn ghi phiên bản đầy đủ |
| `chromestatus.com` | Tóm tắt tính năng và link spec | Không, bỏ bằng `--no-enrich` |

### Cài đặt

Không có bước build. Chép thư mục sang máy đích là chạy được:

```bash
tar czf chromedrift.tgz chromedrift/ config/ examples/ tests/ skills/ docs/ README.md
# trên máy đích
tar xzf chromedrift.tgz && cd chromedrift
python3 -m chromedrift --version
```

Trên Windows dùng `py -3` thay cho `python3`.

### Kiểm tra máy

Nên làm đầu tiên trên mọi máy mới. Lệnh này kiểm mọi thứ thường hỏng trong một lượt, thay vì để bạn phát hiện từng cái sau hai phút chạy:

```bash
python3 -m chromedrift check
```

```
python
  [OK  ] version 3.14.6
cache directory
  [OK  ] /path/.chromedrift-cache writable — 68 GB free
network
  [OK  ] gitiles (source) — HTTP 200
  [OK  ] chromiumdash (version resolution) — HTTP 200
  [OK  ] chromestatus (enrichment, optional) — HTTP 200

ready
```

Thoát code `0` là sẵn sàng, `1` là có dòng FAIL cần xử lý — dùng được trong CI làm bước tiền kiểm. Thêm `--profile config/sb-profile.json5` để kiểm luôn hồ sơ downstream.

### Chạy thử đường ống (~10 giây)

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --target-set minimal --no-enrich
```

`minimal` chỉ tải ba file — đủ để xác nhận đường ống thông suốt.

### Chạy đầy đủ

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --profile config/sb-profile.json5 \
  --out out/M148_to_M151
```

Khoảng hai phút với cache nguội. Lần chạy sau với cùng cặp tag là cache hit, đo được **0,24 giây**. Tag đã phát hành thì nội dung không bao giờ đổi, nên cache giữ vĩnh viễn.

Kết quả trong `out/M148_to_M151/`:

| File | Kích thước | Dùng khi nào |
|---|---|---|
| `report.md` | ~66 KB | Dán vào Jira, Confluence, MR |
| `report.html` | ~1,9 MB | Mở bằng browser, lọc và sắp xếp được, tự chứa hoàn toàn |
| `report.json` | ~2,4 MB | Script, dashboard, so sánh giữa các kỳ |

`report.html` không tải tài nguyên ngoài nào, nên mở được trong mạng cách ly và gửi kèm mail được.

### Luôn ghi phiên bản đầy đủ

`151` phân giải sang bản stable mới nhất *tại thời điểm chạy*, và nó trôi. Đây là khác biệt thật:

```
143.0.7499.40   → ServiceWorkerAutoPreload = ENABLED
143.0.7499.194  → ServiceWorkerAutoPreload = DISABLED   (bị revert trong bản vá)
```

Cùng lệnh `run 139 143` chạy cách nhau vài tuần có thể cho hai kết luận khác nhau, và cả hai đều đúng. Với báo cáo chính thức, luôn ghi phiên bản đầy đủ và lưu lại trong ticket. Số milestone trần chỉ dùng khi thăm dò.

---

## 3. Cái bẫy quan trọng nhất

Nếu chỉ đọc một phần trong README này, hãy đọc phần này. Nó là lý do công cụ tồn tại.

### Chromium không bao giờ bật thẳng một tính năng mới

Quy trình của họ luôn là bốn bước:

1. Viết code mới, **đặt sau một công tắc**, mặc định tắt. Code có trong bản phát hành nhưng không ai thấy gì.
2. **Bật dần từ xa** — 1% người dùng, rồi 10%, rồi 50%. Có sự cố thì tắt lại ngay, không cần phát hành bản mới. Công tắc này gọi là *feature flag*.
3. **Đặt mặc định bật trong code**, khi đã chắc chắn ổn.
4. Vài phiên bản sau, **xoá luôn công tắc** và code cũ, vì không còn ai cần tắt nữa.

### Hệ quả: một tính năng có ba mốc thời gian

| Mốc | Trong code xảy ra gì | Người dùng thấy gì |
|---|---|---|
| A | Code mới xuất hiện, công tắc tắt | Không thấy gì |
| B | Công tắc chuyển sang bật | **Đây mới là lúc thấy đổi** |
| C | Code cũ và công tắc bị xoá | Không thấy gì |

Ba mốc này thường cách nhau nhiều phiên bản: xuất hiện ở M145, bật ở M147, dọn dẹp ở M151.

Bây giờ giả sử bạn so M148 với M151 và chỉ nhìn code. Bạn thấy **mốc C** — code cũ biến mất — và kết luận "Chromium vừa bỏ tính năng này". Trong khi sự thật là tính năng đã đổi từ M147, và giữa M148 với M151 người dùng chẳng thấy gì khác.

Nói gọn: **file khai báo cho biết cái gì tồn tại; chỉ công tắc mới cho biết người dùng thật sự thấy gì.**

### Ví dụ có thật: Local Network Access

Kiểm trên dữ liệu M148 → M151:

**Bước 1.** So danh sách trang settings, mục `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` biến mất. Đọc thô: "Chromium bỏ trang Local Network Access" — một trang quyền riêng tư quan trọng. Đủ để cả đội hoảng.

**Bước 2.** Đọc kỹ ở M148 thì thấy có **hai** trang cùng tồn tại:

```js
Nếu công tắc 'enableLocalNetworkAccessSetting' bật:
    → tạo trang  /localNetworkAccess     (bản cũ)

Nếu công tắc 'enableLocalNetworkAccessSplitPermissions' bật:
    → tạo trang  /localNetwork           (bản mới, tách quyền chi tiết hơn)
```

**Bước 3.** Ở M151 chỉ còn bản mới.

**Bước 4.** Kiểm công tắc: `kLocalNetworkAccessChecksSplitPermissions` **mặc định bật ở M148**, và bị xoá hoàn toàn ở M151.

**Kết luận thật:** trang không bị bỏ, nó được **thay** bằng bản tách quyền. Vì công tắc đã bật sẵn từ M148, người dùng M148 đã nhìn thấy bản mới rồi. Giữa hai mốc, trải nghiệm không đổi; M151 chỉ dọn code.

Việc cần làm khi nâng lên M151 không phải "khôi phục tính năng bị mất", mà chỉ là: nếu code Samsung có chỗ nào trỏ tới `/localNetworkAccess` cũ thì sửa thành `/localNetwork`. Một việc nhỏ, hoàn toàn khác với cái mà diff thô làm bạn tưởng.

### Quy mô

Đây không phải ca cá biệt:

- **M148 → M151, Windows:** 90 công tắc bị gỡ, chia đúng 45 cái đã ship / 45 cái bỏ dở. Không cái nào đổi hành vi. Gắn nhãn "mất tính năng" cho cả 90 thì một nửa danh sách cảnh báo là báo động giả.
- **M139 → M143, tầng web:** trong 202 tính năng "biến mất", 170 cái vốn đã ở trạng thái ổn định — công tắc bị dọn sau khi tính năng đã ship thành công.

Một công cụ báo 170 báo động giả ngay đầu danh sách sẽ mất hết uy tín ngay lần chạy đầu.

### Gom mảnh vụn thành một câu chuyện

Một thay đổi của Chromium không đến gọn một chỗ. Ca Local Network Access ở trên sinh ra đúng bảy mảnh:

```
webui_route    SITE_SETTINGS_LOCAL_NETWORK_ACCESS         bị xoá
webui_route    SITE_SETTINGS_LOCAL_NETWORK                đổi điều kiện canh
webui_gate     enableLocalNetworkAccessSplitPermissions   bị xoá
webui_gate     enableLocalNetworkAccessSetting            đổi biểu thức
webui_control  label:siteSettingsLocalNetworkAccess       bị xoá
base_feature   LocalNetworkAccessChecksSplitPermissions   cờ đã ship rồi gỡ
blink_runtime  LocalNetworkAccessSplitPermissions         cờ thử nghiệm bỏ
```

Đọc rời từng dòng thì chúng mâu thuẫn nhau: dòng trên nói một trang bị xoá, dòng dưới nói một trang xuất hiện. Đọc thành một cụm thì nó nói một điều đơn giản và đúng.

`cluster.py` gom bằng **liên kết mà chính dữ liệu đã khai**, không phải bằng tên giống nhau:

```
route  --khai tên guard-->  gate  --khai tên feature-->  base_feature
control  --khai label-->  route
feature_param  --khai feature cha-->  base_feature
blink  --khai base_feature-->  base_feature
```

Mỗi mũi tên là một trường dữ liệu có thật. Mảnh thứ bảy — `blink_runtime LocalNetworkAccessSplitPermissions` — cố ý đứng riêng, vì fact của nó khai `base_feature: "none"`: Chromium nói thẳng là cờ này không có feature C++ tương ứng. Tên gần giống không phải là quan hệ.

Trên lần chạy M148 → M151: **72 cụm, lớn nhất 7 mảnh**. Báo cáo có mục *Related changes, grouped* xếp theo điểm cao nhất trong cụm.

---

## 4. Công cụ đọc những gì

### Chín bộ đọc

Mỗi bộ đọc là hai hàm thuần: "file này có thuộc phần tôi đọc không" và "đọc ra được những gì". Nhờ vậy mỗi bộ kiểm thử được độc lập, không cần mạng, không cần Chromium.

| Bộ đọc | Đọc gì | Cho biết |
|---|---|---|
| `base_features.py` | Khai báo `base::Feature` trong C++ | Công tắc tính năng và mặc định bật/tắt theo nền tảng |
| `blink_runtime.py` | `runtime_enabled_features.json5` | Tính năng tầng web engine, trạng thái ổn định/thử nghiệm |
| `web_idl.py` | File `.idl` | Hình dạng chính xác của API web: interface, phương thức, thuộc tính |
| `mojom.py` | File `.mojom` | Giao diện giữa các tiến trình, kèm chữ ký phương thức |
| `constants.py` | `*switches.{cc,h}`, `*pref_names.{h,cc}`, `*_prefs.{h,cc}` | Tham số dòng lệnh và khoá thiết lập người dùng |
| `flags_metadata.py` | `flag-metadata.json` | Công tắc nào sắp bị xoá ở phiên bản tới |
| `webui_routes.py` | `route.ts` | Danh sách trang của màn hình `chrome://`, kèm điều kiện hiển thị |
| `webui_controls.py` | Template `.html` và `.html.ts` | Từng điều khiển, loại của nó, và thiết lập nó gắn vào |
| `webui_gates.py` | `*_ui.cc` | Mắt xích nối điều kiện giao diện với công tắc |

Hỗ trợ cho các bộ đọc C++ là `_cpp.py`. Nó che comment mà giữ nguyên độ dài file (để số dòng báo cáo vẫn đúng), cắt đối số cân bằng ngoặc (bỏ qua ngoặc trong chuỗi ký tự), và đánh giá điều kiện tiền xử lý theo nền tảng. `jsonc.py` là bộ đọc JSON5 tự viết, vì Chromium dùng định dạng này còn Python không có sẵn và ta không được cài thêm thư viện.

### Ba bộ đọc WebUI dùng chung cho mọi màn hình

`chrome://settings`, `chrome://history`, `chrome://downloads`, `chrome://bookmarks`, `chrome://extensions` và khoảng 130 màn hình `chrome://` khác đều xây theo cùng một cách: một trang web nằm dưới `chrome/browser/resources/`. Nên ba bộ đọc trên đọc được tất cả.

Chúng nối thành chuỗi ba chặng, và phải đi đủ cả ba mới ra kết luận đúng:

```
route.ts                          trang nào tồn tại
   ↓ bị canh bởi
loadTimeData key                  điều kiện hiển thị
   ↓ được gán giá trị ở
settings_ui.cc  →  base::Feature  công tắc thật
```

Dừng ở chặng đầu chính là rơi vào bẫy Local Network Access.

Loại điều khiển nằm thẳng trong tên thẻ — `settings-toggle-button` là nút gạt, `settings-dropdown-menu` là danh sách xổ xuống, `cr-radio-group` là nhóm nút chọn — nên "đổi dropdown thành toggle" bắt được ngay bằng phép so tên thẻ.

Chromium đang chuyển WebUI từ Polymer (`.html`) sang Lit (`.html.ts`), và chuyển không đều: ở M151, settings còn 243 file Polymer và 6 file Lit, còn extensions thì 2 và 33, print_preview 2 và 32. Bộ đọc hiểu cả hai dialect.

**Danh tính phải đủ để phân biệt.** Một loadTimeData key không phải là duy nhất: ở M151, 62 trong 668 key được đặt bởi nhiều hơn một handler — `undoDescription` do cả `bookmarks_ui.cc` lẫn `downloads_ui.cc` — và 27 trong số đó đặt giá trị khác nhau. Điều khiển cũng vậy: 98 trong 1.256 key trùng nhau giữa các file cùng thư mục, như `id:nicknameInput` có ở cả `credit_card_edit_dialog` lẫn `iban_edit_dialog`. Trùng key thì một bản bị bỏ, và bản nào sống sót lại tuỳ thứ tự duyệt thư mục. Nên gate mang thêm tên handler, control mang thêm tên file: lấy lại 318 khai báo từng bị vứt. Route vẫn nối tới gate bằng key trần, nên chuỗi ba chặng không đổi.

### Vì sao phải đọc điều kiện tiền xử lý

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

Cách đọc thô — lấy giá trị đầu tiên gặp được — trả về "đang bật". Ở ví dụ này tình cờ đúng, vì `IS_WIN` nằm ngay nhánh đầu. Nguy hiểm nằm ở trường hợp ngược lại, khi Windows rơi vào nhánh `#else`. Chỉ trong một file, 14/187 tính năng có mặc định khác nhau theo nền tảng.

| Guard bọc quanh khai báo | Đọc thô | Giá trị thực trên Windows |
|---|---|---|
| `IS_WIN \|\| IS_MAC \|\| IS_LINUX` | `enabled` | `enabled` — trùng nhau |
| `IS_ANDROID` … `#else` | `enabled` | **`disabled`** — đọc thô cho kết luận ngược |
| `ENABLE_PLUGINS` … `#else` | `enabled` | `conditional` — không đoán |

Dòng thứ hai là lý do công cụ tồn tại: đọc nhầm không phải sai số nhỏ mà đảo ngược kết luận. Dòng thứ ba cũng quan trọng: khi điều kiện phụ thuộc vào một buildflag không phải nền tảng, bộ đánh giá ba trạng thái trả lời "không xác định" thay vì đoán bừa.

### Nền tảng là cố định, không phải tuỳ chọn

Sản phẩm là trình duyệt desktop trên Windows, nên **không có tuỳ chọn `--platform`**. Đây là chủ ý: một tuỳ chọn mà không ai kiểm là một cách để sai trong im lặng, và như trên, sai ở đây đảo ngược kết luận.

Macro của các nền tảng khác vẫn được nhận diện, nhưng để đánh giá thành *sai*, không phải "không xác định":

```python
eval_condition("BUILDFLAG(IS_WIN)")          # True
eval_condition("BUILDFLAG(IS_ANDROID)")      # False  — chắc chắn không phải ta
eval_condition("BUILDFLAG(ENABLE_PLUGINS)")  # None   — không đoán
```

Điều kiện build được giải cho Windows ở mọi nơi nó xuất hiện, không chỉ trong macro khai báo feature: `#if` bọc quanh một hằng pref hay switch (115 khoá ở M151 không nằm trong bản build Windows), và `<if expr="...">` của GRIT bọc quanh một điều khiển WebUI (14 điều khiển). Cùng một bộ đánh giá ba trạng thái, hai cú pháp — `not is_win` và `!BUILDFLAG(IS_WIN)` hỏi cùng một câu.

Cây mã của các nền tảng khác (`ash/`, `chromeos/`, `ios/`, `fuchsia/`) bị bỏ qua, **trừ một ngoại lệ**: hằng chuỗi vẫn được đọc ở mọi nơi. Lý do là một khoá pref được định danh bằng chuỗi của nó, và Chromium đang tách nhỏ `chrome/common/pref_names.h`. Khi một khoá chuyển sang file ChromeOS mà ta không nhìn thấy đích đến, công cụ sẽ báo là bị xoá — mà pref bị xoá nghĩa là giá trị đã lưu của mọi người dùng thành mồ côi. Đo M148 → M151: trong 141 khoá biến mất, 100 khoá chỉ đơn giản là đã chuyển sang đó.

### So sánh theo ý nghĩa, không theo văn bản

`diff.py` dựa trên hai nguyên tắc:

**Chỉ so những thuộc tính có ý nghĩa.** Giữa M139 và M143 mọi khai báo đều đổi cú pháp; nếu so cả thuộc tính "kiểu cú pháp" thì sinh ra hàng nghìn thay đổi vô nghĩa. Mỗi loại dữ liệu có danh sách trắng thuộc tính đáng so.

**Chấm theo nền tảng thật.** Một mặc định lật trên desktop mà không lật trên Windows thì không phải thay đổi của bạn.

Rồi nó gắn **nhãn ý nghĩa** cho từng thay đổi — đây là thứ biến "dòng code khác nhau" thành thông tin đọc được:

| Nhãn | Người dùng thấy đổi? | Nghĩa |
|---|---|---|
| `default_flip_on` | Có | Công tắc lật sang bật |
| `web_api_shipped` | Có | API web đạt trạng thái ổn định |
| `ipc_signature_change` | Có | Chữ ký giao tiếp giữa tiến trình đổi — vỡ âm thầm lúc chạy |
| `flag_retired_on` | Không | Đã ship, công tắc gỡ đi, hành vi thành vĩnh viễn không tắt được |
| `flag_retired_off` | Không | Chưa từng ship, code gỡ đi, không bật được nữa |
| `feature_string_renamed` | Không, nhưng… | Tên Finch đổi — cấu hình phía server ngừng khớp trong im lặng |
| `feature_symbol_renamed` | Không, nhưng… | Định danh C++ đổi — build của ta vỡ sau khi merge |
| `pref_renamed` | Không, nhưng… | Khoá thiết lập đổi — giá trị đã lưu của mọi người dùng thành mồ côi |

Mọi thuộc tính được đem ra so đều sinh được một nhãn như vậy. Đó là quy tắc chứ không phải mong muốn: một thuộc tính nằm trong danh sách trắng vì ai đó đã quyết định nó có nghĩa, nên nếu nó đổi mà báo cáo không nói gì thì dòng ấy không đọc được. Đo M148 → M151, **380 trong 709 thay đổi loại "modified" từng đến theo cách đó**; giờ có test chặn.

Bốn nhãn cuối là loại nguy hiểm nhất: **biên dịch sạch, test xanh, và hỏng ngoài thực địa** — hoặc vỡ build ngay sau khi merge, đúng lúc muộn nhất.

`diff.py` còn nhận diện đổi tên. Với pref và switch, danh tính là chuỗi ký tự, còn tên biến C++ giữ nguyên; nên một lần đổi tên sẽ hiện ra thành "một cái bị xoá, một cái mới thêm" chẳng liên quan gì nhau. Ghép cặp theo tên biến sẽ lộ ra bản chất. Một ca có thật:

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);   // chữ r thường
// M143 — macro tự suy tên từ biến
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   tên chuỗi giờ là "FedCmIdPRegistration"                        // chữ R hoa
```

Không ai sửa tên cả — chính việc đổi macro đã đổi tên. Mọi cấu hình field-trial phía server và mọi cờ `--enable-features` dùng cách viết cũ **âm thầm mất tác dụng**. Không lỗi biên dịch, không cảnh báo.

Khi một pref hay switch biến mất mà không ghép được cặp, công cụ **không** khẳng định là đã bị xoá. Nó gắn nhãn `pref_left_scan` / `switch_left_scan`, nghĩa là "đã rời khỏi phạm vi quét" — có thể bị xoá thật, có thể chỉ chuyển sang file ta không đọc. Trên lần chạy M148 → M151 với target set mặc định, cả 139 pref biến mất đều mang nhãn này.

---

## 5. Độ phủ: đọc được bao nhiêu cây nguồn

### Mỗi lần chạy đều tự đo

Một danh sách file viết tay chỉ đúng cho phiên bản nó được viết ra. Dựng danh sách theo hiện trạng M130 rồi đem chạy ở M151, hai mươi mốt mốc sau, thì nó bỏ sót 27% số file pref và 34% số file feature đang tồn tại ở đó. Một phần ba độ phủ bốc hơi sau hai năm, và bốc hơi trong im lặng — file không ai liệt kê là file không ai để ý.

Nên mỗi lần chạy, công cụ hỏi chính cây nguồn của phiên bản đó xem có những file nào, rồi đối chiếu target set với nó. Gitiles trả về danh sách đệ quy của một thư mục trong một request, nên mười bốn thư mục gốc tốn khoảng 24 MB và 21 giây, cache vĩnh viễn vì cây của một tag không bao giờ đổi.

Kết quả in ra ở mỗi lần chạy, lưu trong snapshot, và đi vào báo cáo — `report.json` ở `meta.coverage` (`{from, to}`, mỗi bên một số đo) cùng danh sách đường dẫn chưa đọc ở `meta.uncovered_files`, `report.md` ở mục cuối *How this was produced*:

```
coverage: reads 42 of 1039 files in this tree that could declare (4% of files)
  largest gaps: chrome/browser/ (251 files), components/enterprise/ (50 files)
  to read these too, run `--target-set wide`: about 315 MB per version instead of 40
```

**Con số trong tài liệu này là số đo tại M151. Con số đáng tin là con số lần chạy của bạn in ra.**

### Ba target set

| | Tải về | Giữ trên đĩa | File khai báo đọc được | Dùng khi nào |
|---|---:|---:|---:|---|
| `minimal` | ~300 KB | ~1 MB | 3 file | Kiểm khói, kiểm đường ống CI |
| `default` | ~40 MB | ~38 MB | 42 / 1.039 (4%) | Làm việc hằng ngày |
| `wide` | ~315 MB | ~94 MB | **1.039 / 1.039 (100%)** | Cổng chặn trước release |

4% nghe rất tệ, nhưng **số file không phải số khai báo**. Các file được chọn thủ công là những file lớn nhất. Đo tại M151:

| | `default` | `wide` |
|---|---:|---:|
| `base::Feature` | 2.062 | 3.951 |
| Tham số feature | 862 | 1.623 |
| Pref | 689 | 2.404 |
| Switch | 288 | 1.111 |
| Mojo interface | 338 | 1.455 |
| Mojo method | 1.362 | 5.738 |
| Điều khiển WebUI | 884 | 1.421 |
| **Tổng số fact** | **24.871** | **36.089** |

Tức là `default` đọc 4% số file nhưng hơn một nửa số khai báo `base::Feature`. Đó là một đánh đổi có chủ ý, không phải một khiếm khuyết — nhưng khi câu trả lời thực sự quan trọng thì chạy `wide`.

`wide` đọc 100% theo nghĩa chặt: mọi file mà quy ước tên cho biết là có thể khai báo đều được tải về, **và** mọi file tải về đều có ít nhất một bộ đọc nhận. Có test giữ cả hai chiều, vì cả hai đều đã từng lệch: có lúc phép đo không đếm `*flags.{cc,h}` dù bộ đọc vẫn đọc chúng, có lúc bộ đọc bỏ qua `switches.cc` dạng trần dù phép đo vẫn đếm, và có lúc `--complete` lọc bằng một bản danh sách hậu tố riêng chưa biết quy ước `*_prefs.{h,cc}`.

Danh sách hậu tố ấy giờ chỉ có một bản (`targets.READABLE_SUFFIXES`), dùng chung cho `wide` và `--complete`, vì cả hai hỏi cùng một câu: bộ đọc đọc được những dạng tên file nào.

### Phân vùng: giới hạn phần phải tải và quét

Khi chỉ quan tâm một mảng, `--partition` giới hạn cả việc tải lẫn việc đọc:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --partition downloads
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --partition settings --partition bookmarks
```

Vùng có sẵn: `settings, downloads, bookmarks, history, extensions, passwords, printing, newtab, webplatform, network, media`.

Phân vùng là **bộ lọc trên danh sách target**, không phải danh sách thứ hai phải bảo trì — thêm một target mới thì nó tự chảy vào đúng vùng khớp đường dẫn. Vài mục luôn được giữ trong mọi phân vùng vì rẻ và liên quan tới tất cả: `pref_names.h`, `flag-metadata.json`, `content_switches.cc`.

Chạy phân vùng cũng in độ phủ của riêng nó, đo trên đúng thư mục gốc mà phân vùng ấy tải:

```
$ python3 -m chromedrift snapshot 151.0.7922.138 --partition downloads
coverage: reads 3 of 6 files in this tree that could declare (50% of files)
snapshot: 2692 facts
```

**Đánh đổi phải nói rõ:** phân vùng nhanh hơn và kém đầy đủ hơn, một chiều. Chromium không tổ chức code theo tính năng sản phẩm — một thay đổi ảnh hưởng Downloads có thể nằm ở `content/`, ở một Mojo interface, hoặc ở một file cờ không khớp vùng nào. Đúng khi đang lặp trên một mảng; **sai khi chạy làm cổng chặn trước release**.

Thêm `--complete` thì phân vùng tải trọn thư mục gốc thay vì lọc theo danh sách file, nên độ phủ bên trong các thư mục đó là trọn vẹn theo cấu trúc. Đo tại M151: `--partition extensions --complete` đọc 19/19 file. Tuỳ chọn này bị từ chối với những phân vùng có thư mục gốc là cả một hệ thống con (`webplatform`), vì Gitiles trả về cả thư mục hoặc không gì cả.

### Đo bằng blobless clone — lệnh `catalog`

`catalog` trả lời cùng câu hỏi bằng nguồn khác: một clone không tải nội dung file lấy được toàn bộ cấu trúc cây Chromium trong vài giây.

```bash
python3 -m chromedrift catalog 151.0.7922.138
```

Nó dùng **chung một luật** với phép đo chạy mỗi lần, nên hai con số mô tả cùng một tập hợp, và nó nêu đích danh từng file còn thiếu để bổ sung theo thứ tự ưu tiên.

### Hai nghĩa của "đầy đủ"

| Câu hỏi | Trả lời được không |
|---|---|
| Đọc hết mọi khai báo **bên trong** thư mục của một vùng? | **Có** — bằng `--complete`, hoặc `--target-set wide` cho toàn cây |
| Đọc hết mọi tính năng **thuộc về** vùng đó? | **Không** — vùng nào cũng tham chiếu ra ngoài |

Ví dụ: mọi khai báo trong `chrome/browser/resources/settings` đều đọc được, nhưng một tính năng hiện trên trang Settings có thể được điều khiển bởi một cờ khai ở `content/`. Đó là lý do báo cáo có mục *bao đóng tham chiếu* — nó đi theo mọi liên kết mà dữ liệu tự khai và liệt kê những liên kết trỏ tới thứ không có trong snapshot.

---

## 6. Chín lệnh

```bash
python3 -m chromedrift check      # kiểm tra máy có chạy được không
python3 -m chromedrift snapshot   # trích bề mặt tính năng của MỘT phiên bản
python3 -m chromedrift diff       # so ngữ nghĩa giữa HAI phiên bản
python3 -m chromedrift profile    # xem hồ sơ downstream giải ra cái gì
python3 -m chromedrift run        # chạy toàn bộ: snapshot → diff → chấm điểm → báo cáo
python3 -m chromedrift report     # dựng lại báo cáo, lọc được theo vùng
python3 -m chromedrift catalog    # đo target set đang thiếu file nào
python3 -m chromedrift discover   # tìm file của vendor trong cây fork
python3 -m chromedrift provenance # tách quyết định cố ý khỏi nợ merge
```

Tách thành từng lệnh không phải để trang trí. Bước đắt (tải về) và bước bạn chỉnh đi chỉnh lại (chấm điểm, báo cáo) có chi phí hoàn toàn khác nhau. Chạy lại được nửa rẻ trên cache ấm là khác biệt giữa một công cụ người ta tinh chỉnh và một công cụ người ta chạy đúng một lần.

Mỗi lệnh chỉ nhận những tuỳ chọn nó thật sự dùng. `catalog` không có `--local-src`, `discover` không có `--partition` — nếu một lệnh nhận một cờ rồi bỏ qua thì đó là lỗi, và có test chặn.

### Ba lệnh dành cho fork

`discover` đi bộ qua một checkout fork và tìm file của vendor bằng tên: thư mục mang tên vendor (`samsung/`, `sbrowser/`) và hậu tố tên file đánh dấu biến thể của một file upstream (`privacy_page-si.html`). Cái thứ hai quan trọng hơn vẻ ngoài của nó, vì nó nằm *bên trong* thư mục của Chromium nên không tiền tố đường dẫn nào tìm ra.

Kết quả chia làm hai, và tách hai loại này ra là điểm mấu chốt:

- **Sửa được** — có bộ đọc nhận file này, nên thứ duy nhất còn thiếu là một dòng trong `targets.py`.
- **Ngoài mô hình** — không bộ đọc nào đọc file này dù có tải về: UI C++ native, chuỗi hiển thị `.grd`, file `.gn`. Thêm target không thay đổi gì; chúng thuộc phần giới hạn ở §9.

`coverage.py` trả lời một câu hỏi khác mà một fork dạng merge luôn gặp. Fork loại này không ghi đè code Chromium — nó merge nguyên bản mới vào, giữ bản của mình bên cạnh, và chọn giữa hai bằng cờ build:

```cpp
#if defined(SBROWSER_CUSTOM_DOWNLOADS)
  ... bản của vendor, đây mới là bản chạy thật ...
#else
  ... bản của Chromium, nguyên vẹn từ lần merge ...
#endif
```

Vì cả hai đều có mặt nên phép so giá trị không tìm ra gì: code upstream đúng là y hệt upstream. Câu hỏi đáng trả lời không phải "code upstream còn nguyên không" mà là **phần nào đang bị che**. `provenance.py` trả lời nửa sau: so bản của vendor với một dãy phiên bản upstream để biết lớp che ấy được viết cho mốc nào.

Tên cờ không đoán được, nên hồ sơ phải khai — xem `vendor_markers` ở §7.

---

## 7. Hồ sơ downstream

Đây là việc duy nhất bắt buộc phải làm nghiêm túc. Chất lượng cột **Must fix** tỉ lệ thuận trực tiếp với file này. Không có nó, công cụ chỉ biết "Chromium đổi gì", không biết "đổi đó có đụng tới ta không".

```bash
cp config/sb-profile.example.json5 config/sb-profile.json5
```

### Bốn nguồn bằng chứng, kết hợp được

**A — thư mục patch** (phổ biến nhất với vendor fork):

```json5
{ patch_dirs: ["/work/sbrowser/patches"] }
```

Đọc mọi `.patch`/`.diff`, lấy cả đường dẫn lẫn identifier trong thân hunk.

**B — fork toàn bộ source trong git**:

```json5
{ git: { repo: "/work/sbrowser/src", upstream_ref: "148.0.7778.217" } }
```

Chạy `git diff --name-only <upstream_ref>`. Cần `git` trong PATH.

**C — quét mã riêng của bạn** (bắt được thứ patch bỏ sót):

```json5
{ source_roots: ["/work/sbrowser/sbrowser_chrome", "/work/sbrowser/sbrowser_java"] }
```

Cách này đáng nói riêng. Thay vì tìm tên Samsung trong cây Chromium khổng lồ, công cụ lấy **từ vựng của Chromium** — mọi tên feature, switch, pref — rồi quét một lượt qua cây mã nhỏ của bạn. Đảo bài toán từ "nhiều lượt qua cây khổng lồ" thành "một lượt qua cây nhỏ", và bắt được cả những chỗ code bạn *đọc* một tính năng mà không hề vá file khai báo nó.

Một chi tiết ở đây từng là lỗi: từ vựng phải dựng từ **cả hai** phiên bản. Nếu chỉ dựng từ bản mới thì thứ vừa bị xoá sẽ không nằm trong từ vựng và bị lọc mất — mà đó chính là ca làm vỡ build.

**D — danh sách tự duy trì**:

```json5
{
  modified_paths: [
    "content/browser/renderer_host/render_widget_host_view_aura.cc",
    "media/base/win/",              // dấu / cuối = khớp theo tiền tố
  ],
  symbols: ["BackForwardCache", "kBackForwardCache"],
}
```

### Chỉ bằng chứng cấp ký hiệu mới đẩy lên Must fix

Bằng chứng cấp đường dẫn thì quá thô: `content_features.cc` khai báo gần 200 tính năng, nên biết bạn vá *file* đó gần như không nói lên điều gì. Biết bạn động vào `kServiceWorkerAutoPreload` thì rất có nghĩa. Điểm cộng phản ánh đúng chênh lệch đó.

### Khai báo `areas`

Đây là thứ khiến finding tự định tuyến về đúng đội. `weight` (0–100) vào thẳng điểm số, `owner` hiện trong báo cáo:

```json5
areas: [
  { id: "media", title: "Video & media", kind: "product", weight: 90, owner: "media-team",
    paths:   ["media/", "content/browser/media/"],
    symbols: ["Media", "Video", "Codec"],
    prefs:   ["media."],
    flags:   ["kMedia"],
    kinds:   [] },
]
```

Năm cách khớp — đường dẫn, ký hiệu, pref, cờ, và trọn một loại dữ liệu — chỉ cần trúng một là nhận. Cần đến năm cách vì Chromium không tổ chức code theo tính năng sản phẩm: "Download" nằm rải ở `components/`, `chrome/browser/`, `content/`, cộng thêm pref, cờ và Mojo.

`symbols` là **khớp chuỗi con**, không phải khớp chính xác — `"Audio"` sẽ bắt cả `RestrictOwnAudio`. Cố ý như vậy để phân loại theo chủ đề, nhưng đừng đặt từ quá ngắn hoặc quá chung.

### Ba loại vùng, không phải một

Trường `kind` có ba giá trị, và chỉ khai loại `product` là sai lầm kinh điển:

- **`product`** — có đội sở hữu rõ ràng: Downloads, Bookmarks, History, Extensions, Media
- **`infra`** — hạ tầng cắt ngang, không thuộc tính năng nào nhưng **chứa các mục nghiêm trọng nhất**: Mojo, Web IDL
- **`platform`** — nền chung: cờ tính năng, pref, tham số dòng lệnh

Đo trên một lần chạy thật: nếu chỉ khai vùng theo tính năng sản phẩm thì **81% số finding không khớp vùng nào**, trong đó có cả mười mục điểm cao nhất toàn báo cáo — `CreateLanguageModel`, `CreateSummarizer`, `AttachDevToolsSession`, đều là Mojo đổi chữ ký, 80 điểm, vỡ âm thầm lúc chạy. Chúng không thuộc tính năng sản phẩm nào vì chúng là hạ tầng dùng chung. Khai đủ ba loại thì phần không thuộc vùng nào giảm còn khoảng 8%.

### `vendor_markers` — cho phân tích fork

```json5
vendor_markers: {
  macros:           ["SBROWSER", "SAMSUNG"],   // cờ build trong #if
  symbol_prefixes:  ["kSbrowser", "kSamsung"], // tiền tố định danh C++
  path_markers:     ["samsung/", "sbrowser/"], // thư mục
  filename_markers: ["-si"],                   // hậu tố biến thể của file upstream
}
```

Không khai thì phần phân tích fork bị bỏ qua, chứ không đoán bừa. Chạy `chromedrift discover --fork-src <đường-dẫn>` để lấy khối này điền sẵn từ chính cây fork.

### Kiểm hồ sơ trước khi chạy thật

```bash
python3 -m chromedrift profile config/sb-profile.json5 --ref 151.0.7922.138
```

```
profile: Samsung Browser (platform windows)
  areas:            7
  patched files:    3
  symbols:          11
    symbols_from_patches: 7
```

Nếu `symbols: 0` thì không mục nào lên được Must fix, và công cụ sẽ cảnh báo.

---

## 8. Đọc báo cáo

### Bốn nhóm

```
must fix:      4     ← ta có bằng chứng phụ thuộc VÀ nó đã đổi. Coi như có việc.
needs review: 210    ← hoặc ta có đụng, hoặc mức độ đủ nghiêm trọng để xác nhận
opportunity: 1313    ← năng lực mới có thể lấy về
fyi:         1229    ← ghi nhận cho đủ
```

Đọc theo thứ tự Must fix → Needs review → Opportunity. `fyi` chỉ tra khi cần.

`must fix: 0` nghĩa là **chưa cung cấp bằng chứng**, không phải "bản nâng cấp này sạch". Không có hồ sơ trỏ vào patch hoặc source thật thì không mục nào lên được Must fix, và báo cáo có ghi rõ điều đó.

Ở chế độ `--mode fork` bốn nhóm này mang nghĩa khác, vì phép so cũng khác: không phải Chromium theo thời gian, mà upstream đối chiếu bản fork ở cùng milestone. "Removed" nghĩa là *ta* đã bỏ, "added" nghĩa là *ta* đang mang thêm.

| Nhóm | Ở `uprev` | Ở `fork` |
|---|---|---|
| Must fix | Ta tham chiếu tới nó và nó đã đổi | Khác biệt ta phụ thuộc — lần rebase sau sẽ âm thầm xoá nó |
| Needs review | Ta động tới vùng đó, hoặc đủ nghiêm trọng | Khác biệt chưa rõ ai chịu trách nhiệm |
| New opportunity | Năng lực mới | **Không dùng** — trong phép so fork không có gì là "cơ hội" |
| FYI | Ghi nhận cho đủ | Như trên |

Mỗi finding trỏ tới **`đường-dẫn:dòng`** của cả hai phía, không chỉ tên file. `content_features.cc` khai gần hai trăm tính năng — đúng lý do mà bằng chứng cấp ký hiệu được xếp trên bằng chứng cấp đường dẫn khi chấm điểm.

### Báo cáo xếp theo câu hỏi người đọc mang tới, không phải một bảng

Một bảng 2.792 dòng chỉ trả lời được đúng một câu: *cái gì điểm cao nhất*. Nó không trả lời được "màn hình của tôi đổi gì", "cờ nào giờ bật trong build của mình", hay "cái gì vỡ ra ngoài binary" — mà đó mới là những câu người ta mở báo cáo để tìm. Nên `report.html` chia thành các mục theo đúng thứ tự câu hỏi:

```
Triage                     4 nhóm, mỗi nhóm kèm câu "phải làm gì với nó"
What this uprev is made of 3 nhóm nghĩa, kèm tỉ lệ thêm / đổi / mất
Behaviour switches         chuyện gì đã xảy ra   (974)
External contracts         chuyện gì đã xảy ra   (764)
UI and scheduling          màn hình nào đổi gì   (1.054)
Every finding              toàn bộ, lọc và sắp xếp được
```

Ba mục giữa là ba nhóm nghĩa ở §8.7, mỗi nhóm trình bày theo trục mang nghĩa của chính nó: hai nhóm hướng mã nguồn xếp theo *chuyện đã xảy ra*, nhóm hướng người dùng xếp theo *màn hình*. Con số trên mỗi mục cộng lại đúng bằng tổng số finding, và mọi dòng trong các mục đều có trong bảng cuối và trong JSON — đây là phần trình bày thuần, không bịa fact nào, không bỏ fact nào.

### "Chuyện gì đã xảy ra" — khoảng bốn mươi chuyện, không phải 2.792 dòng

Câu mô tả cho mỗi chuyện vốn đã được viết sẵn: nó chính là nhãn của signal đã ấn định mức nghiêm trọng cho finding đó. Trước đây câu đó chỉ đọc được khi bấm mở từng dòng một trong bảng.

```
● 77   Now ON by default on Windows                                    77 changed
       ~ feature flag PrefetchPrerenderIntegration — off → on for Windows   100
       ~ feature flag CastStreamingWinHardwareH264 — off → on for Windows    93
● 40   Mojo method signature changed (ABI)                             40 changed
       ~ process call blink.mojom.PictureInPictureService.StartSession()     98
● 139  Preference no longer in the file we read — it may have been deleted…  139 gone
```

Gộp theo signal đã ấn định severity, chứ không phải signal đầu tiên trong danh sách: nếu không, một finding sẽ bị xếp dưới một câu và bị chấm điểm theo một câu khác. Finding nào không mang signal nào — thứ chỉ vừa xuất hiện, chưa có mặc định nào dịch chuyển — lấy chiều và loại làm câu mô tả (`New feature flag`, `Removed chrome://flags entry`). Nhờ vậy mỗi finding rơi vào đúng một chuyện, không sót và không đếm hai lần; có test kiểm đúng điều đó.

Thứ tự là lời khuyên đọc: nặng trước. Một chuyện mang severity 80 đứng trên một chuyện mang severity 25, dù chuyện sau có nhiều dòng hơn.

### Màn hình nào đổi gì

Người sở hữu một màn hình đến với câu hỏi khác — *trang của tôi khác gì so với bản trước* — và một danh sách phẳng toàn định danh không trả lời được: `id:cancelButton` không nói trang nào, không nói thêm hay bớt, không nói đó là nút hay nút gạt. Cùng một loadTimeData key còn xuất hiện một lần cho mỗi handler đặt nó, nên `webuiRefresh2026` hiện chín dòng giống hệt nhau.

```
settings › ai_page — 13 new · 1 changed · 5 gone
  + section    aiPageTitle
  + link row   skillsSettingLabel
  ~ toggle — glicExperimentalTriggering  (writes glic.experimental_triggering_enabled)
  − page /localNetworkAccess
```

Dữ liệu để viết ra như vậy vốn đã nằm sẵn trên fact và chỉ là chưa từng được hiển thị: mỗi control mang bề mặt, trang, file, tên thẻ và pref nó ghi; mỗi route mang đường dẫn và điều kiện canh; mỗi gate mang handler đặt nó.

### Bảng cuối: định danh không phải mô tả

Bảng "Every finding" có bảy cột, và bốn trong số đó trước đây chỉ đọc được khi bấm mở từng dòng hoặc không có ở đâu cả:

| Cột | Trả lời |
|---|---|
| Score | Xếp hạng, giải thích được từng điểm |
| Change | `new` / `changed` / `gone` |
| Bucket | Rơi vào nhóm triage nào |
| What | Vật đó **bằng lời**, không phải định danh trần: `feature flag AAPMBlocksWebGPU — off → on for Windows` |
| What happened | Câu mô tả chuyện đã xảy ra, cùng câu dùng ở mục trên |
| Where | Màn hình, hoặc thư mục khai báo |
| Surface | Loại fact, kèm nhóm nghĩa của nó |

Nhãn `ours` gắn ngay trong cột What cho những dòng chạm vào mã ta vá hoặc tham chiếu — trên một lần chạy thật đó là 53 trong 2.792 dòng, và 53 dòng đó là lý do báo cáo tồn tại. Mỗi con số ở các mục trên đều bấm được: bấm vào là bảng tự lọc đúng phần đó.

### Mọi điểm số đều giải thích được

```
base severity 75 (modified base_feature)
  | +12 we patch 1 of the declaring file(s): content/public/common/content_features.cc
  | +30 our source references ServiceWorkerAutoPreload, kServiceWorkerAutoPreload
  | +16 owned area 'Video & media' (weight 80)
```

Một bảng xếp hạng không ai cãi lại được là bảng xếp hạng bị bỏ qua ngay lần đầu nó sai. Muốn chỉnh ưu tiên thì sửa `weight` trong `areas`, hoặc sửa bảng `BASE_SEVERITY` / `SIGNAL_SEVERITY` trong `chromedrift/diff.py`. Cả hai đều là dữ liệu thuần, không phải logic.

### Phân tích hết, lọc lúc đọc

Cách làm tự nhiên khi mở rộng ra nhiều mảng là lọc ngay từ đầu: "lần này chỉ phân tích Download thôi". Đó là cách chắc chắn nhất để vứt mất phần đầu danh sách, vì lý do đã nêu ở §7: các mục nghiêm trọng nhất là hạ tầng dùng chung, không thuộc vùng sản phẩm nào.

Nên `report.json` **luôn chứa tất cả**, và việc cắt lát diễn ra lúc đọc:

```bash
# Phân tích một lần
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 --profile config/sb-profile.json5

# Xem có những vùng nào
python3 -m chromedrift report out/report.json --list-areas

# Cắt lát cho từng đội — không chạy lại, không quét lại
python3 -m chromedrift report out/report.json --area downloads --out downloads
python3 -m chromedrift report out/report.json --area ipc       --out ipc
```

Kích thước không phải nút thắt: toàn bộ phần không-FYI của một kỳ uprev là khoảng 1 MB JSON, còn `report.md` chỉ 66 KB. Nút thắt là thời gian đọc của con người.

### Phần thừa phải hiện ra

Chia vùng mà im lặng nuốt phần không khớp là cách chắc chắn nhất để bỏ lọt lỗi. Nên công cụ luôn in số finding không thuộc vùng nào, và cảnh báo khi trong đó có mục điểm cao:

```
⚠️ 50 unassigned findings score 60 or more (highest: 87). These belong to no
   area, so no per-area report shows them. Either extend the area definitions
   or review this set explicitly.
```

Xem được luôn bằng `--area _unassigned`. Con số này cũng là thước đo chất lượng của chính định nghĩa vùng.

### Mười ba loại fact, ba nhóm nghĩa

Báo cáo nhóm bộ lọc theo *ý nghĩa của thay đổi*, không xếp mười ba loại thành một danh sách phẳng:

| Nhóm | Gồm | Một thay đổi ở đây nghĩa là |
|---|---|---|
| Behaviour switches | feature flag, feature param, Blink runtime | Hành vi tự nó đổi |
| External contracts | pref, switch, Web IDL, Mojo | Vỡ một thứ bên ngoài binary, âm thầm: dữ liệu người dùng đã lưu, script khởi chạy, website đang chạy, tiến trình bên kia |
| UI and scheduling | route/control/gate WebUI, `chrome://flags` | Đổi cái người dùng thấy, hoặc đổi ngày một cờ bị xoá |

Trên một báo cáo M139 → M143 thật, 3.120 finding chia 34% / 35% / 30%. Tức là **hai phần ba báo cáo không phải chuyện tính năng được bật hay tắt** — đọc phẳng thành mười ba loại "tính năng" là cách hiểu sai phổ biến nhất.

Ba nhóm này là ba mục của báo cáo, không chỉ là cách gom bộ lọc: mỗi mục in kèm câu "một thay đổi ở đây nghĩa là gì", tỉ lệ thêm / đổi / mất, và số finding của từng loại trong nhóm. Trước đây chỗ duy nhất nói ra chuyện này là nhãn `<optgroup>` bên trong một dropdown lọc.

### Ngữ cảnh từ chromestatus

`enrich/chromestatus.py` lấy mô tả tính năng do người viết. Ghép từng mục thì tỉ lệ trúng rất thấp (~2%) vì tên bên đó là văn xuôi còn tên trong mã là định danh. Nên thay vì cố ghép, công cụ ghi cả danh sách "Chromium đã ship gì trong khoảng này" vào báo cáo như phần nền — khoảng 100 mục. Đó là nguồn duy nhất nói *upstream định ship cái gì*, nên nó nằm trong báo cáo dưới dạng bối cảnh, không phải dưới dạng ý kiến thứ hai về bất kỳ dòng nào.

---

## 9. Giới hạn

Nói rõ để không ai đọc báo cáo sạch rồi tưởng bản nâng cấp sạch.

### Công cụ đọc khai báo, không đọc logic

Mỗi trang WebUI có hai file song song:

```
downloads_page.html   ← ĐỌC   khai báo: có điều khiển nào, loại gì, gắn pref nào
downloads_page.ts     ← BỎ    hành vi:  khi nào hiện, bấm vào thì làm gì
```

Trong `.html` công cụ đọc được:

```html
<template is="dom-if" if="[[autoOpenDownloads_]]" restamp>
    ... nút "Xoá tất cả" ...
</template>
```

Nó biết có một khối bị canh bởi điều kiện tên `autoOpenDownloads_`. Nhưng trong `.ts`:

```ts
autoOpenDownloads_ = autoOpen;    // autoOpen là trạng thái lúc chạy
```

Nó **không biết** khi nào điều kiện đó đúng — điều đó phụ thuộc người dùng có đặt loại file tự mở hay không, tức trạng thái runtime chứ không phải khai báo.

Đo trên 332 file template của tám bề mặt: 602 khối điều kiện, 460 ràng buộc `hidden="[[...]]"`, và **37% điều khiển nằm trong một khối điều kiện**. Khoảng một phần ba điều khiển có điều kiện hiển thị mà công cụ không giải được.

| | |
|---|---|
| Thêm/bớt một điều khiển | Bắt được |
| Đổi loại điều khiển (dropdown → toggle) | Bắt được |
| Đổi pref mà điều khiển ghi vào | Bắt được |
| Thêm/bớt trang, đổi điều kiện canh **trang** | Bắt được |
| Đổi logic quyết định khi nào **điều khiển** hiện | Không |
| Đổi việc bấm nút thì làm gì | Không |
| Đổi cách sắp xếp, lọc danh sách | Không |

Ba lý do cố ý bỏ:

1. **Đọc logic là phân tích luồng dữ liệu, không phải quét cú pháp.** Để biết `autoOpenDownloads_` khi nào đúng phải lần theo callback và cả trạng thái từ C++ gửi sang. Nó sẽ sai ngay khi Chromium viết lại một hàm.
2. **Phá vỡ nguyên tắc "không cần tải Chromium về".** Phần khai báo vài chục MB; đọc logic thì phải kéo cả cây TypeScript, và vẫn không đủ vì logic nối sang C++.
3. **Nhất quán với tầng C++.** Công cụ cũng không đọc thân hàm C++, chỉ đọc macro khai báo. Đọc được logic một bên thì phải đọc cả hai, và lúc đó nó thành một compiler chứ không còn là công cụ chạy trong hai phút.

Chuỗi `route → guard → flag` bù được phần quan trọng nhất — điều kiện hiển thị ở cấp **trang**, vì Chromium khai nó dưới dạng `loadTimeData` chứ không phải logic. Đó là lý do ca Local Network Access truy được đến tận cùng. Phần không bù được là điều kiện ở cấp **điều khiển bên trong trang**; chỗ đó chỉ so sánh ảnh chụp giao diện mới trả lời được.

### Các giới hạn còn lại

- **Một khai báo có trong cây nguồn vẫn có thể không được biên dịch vào binary.** Công cụ không đọc đồ thị GN, nên nó biết cái gì được *khai báo*, không biết cái gì được *build*.
- **Thay đổi nằm hoàn toàn trong thân hàm C++** — cùng lý do như trên, ở tầng khác.
- **Chuỗi hiển thị trong `.grd`** — đổi nhãn hiển thị không bắt được.
- **API của extension.** Đuôi `.idl` trong cây Chromium dùng cho ba ngôn ngữ khác nhau: Web IDL của Blink, Chrome Extensions IDL (`chrome/common/extensions/api/`, `extensions/common/api/`), và MIDL (`ichromeaccessible.idl`). Bộ đọc chỉ hiểu ngôn ngữ đầu, nên nó chỉ đọc dưới `third_party/blink/renderer/`. Trước đây nó đọc cả ba và cho ra 1.081 fact sai ở M151 — 96 fact có nguyên một khai báo lồng nằm trong chữ ký của chính nó, số còn lại bị gắn nhãn "Web API" trong khi không website nào gọi được `chrome.fileManagerPrivate`. Đọc sai một phương ngữ tệ hơn là không đọc; muốn phủ bề mặt extension thì cần một bộ đọc riêng với loại fact riêng.
- **Mọi thứ ngoài repo:** cấu hình Finch phía server, script khởi chạy, hệ thống test tự động.
- **Giao diện đã render** — không ảnh chụp, không bố cục, không phát hiện lỗi hiển thị.

### Còn có thể mở rộng

Công cụ đang theo dõi tám bề mặt `chrome://` trong target set mặc định (`wide` đọc cả 132). Chromium có 132 thư mục dưới `chrome/browser/resources/`, nhưng con số đó gây hiểu nhầm: 39 là trang debug người dùng không bao giờ thấy, 9 chỉ dành cho ChromeOS. **Số đáng cân nhắc là khoảng 29**, chẳng hạn `autofill`, `certificate_manager`, `enterprise`, `lens`, `pdf`, `side_panel`, `signin`, `tab_search`, `webauthn`.

Thêm một bề mặt là thêm một dòng trong `chromedrift/targets.py`:

```python
WEBUI_SURFACES = (
    "settings",
    "history",
    ...
    "pdf",        # ← thêm dòng này là xong
)
```

Không cần viết parser mới — ba bộ đọc WebUI đã tổng quát cho mọi bề mặt.

### Thêm một nguồn sự thật mới

Viết một extractor với hai hàm thuần `applies_to(path)` và `extract(text, path)`, đăng ký một dòng trong `chromedrift/extract/__init__.py`, khai file cần tải trong `chromedrift/targets.py`. Không đụng tới phần còn lại.

---

## 10. Môi trường và xử lý sự cố

### Hệ điều hành

| Nền tảng | Trạng thái | Đã kiểm chứng thế nào |
|---|---|---|
| macOS | Chạy đầy đủ | Toàn bộ pipeline, Python 3.14.6 |
| Linux / Ubuntu | Chạy đầy đủ | Ubuntu 24.04 + Python 3.12 và Debian + Python 3.9 trong Docker, kết quả trùng khớp macOS từng con số |
| Windows | Chạy được | Chưa chạy trực tiếp; từng cơ chế Windows gây vỡ đã kiểm riêng — xem dưới |

Về Windows, mã nguồn không có phần nào phụ thuộc POSIX. Các điểm thường làm vỡ công cụ Python đã kiểm riêng:

- **Encoding console** — đây là lỗi thật đã tìm ra và sửa. Windows chỉ dùng UTF-8 cho console thật; hễ output bị chuyển hướng ra file hoặc pipe là rơi về cp1252, mà báo cáo chứa `→` và `·`. Nay CLI ép stdout/stderr về UTF-8 khi khởi động, và có test hồi quy chạy CLI dưới `PYTHONIOENCODING=cp1252`.
- **Đọc file UTF-8** — mọi `open()` đều khai `encoding=` tường minh.
- **Ngữ nghĩa đường dẫn** — kiểm trực tiếp qua module `ntpath`, gồm cả chốt chặn path-traversal khi giải nén tarball.
- **Giới hạn 260 ký tự** — đường dẫn tương đối dài nhất trong cache đo được là 142 ký tự. Đủ thoải mái, nhưng đừng đặt dự án ở chỗ quá sâu.
- **Tên file cấm, đụng độ hoa-thường** — quét toàn bộ cache: không có tên `CON`/`PRN`/`AUX`/`NUL`/`COM*`/`LPT*`, không có cặp file chỉ khác nhau hoa-thường, không có ký tự `: * ? " < > |`.

### Sau proxy công ty

`urllib` tự đọc biến môi trường:

```bash
export HTTPS_PROXY=http://proxy.noi-bo:8080
export NO_PROXY=localhost,127.0.0.1,.noi-bo
python3 -m chromedrift check          # in ra proxy đang dùng
```

Nếu proxy giải mã TLS và gặp `CERTIFICATE_VERIFY_FAILED`, trỏ Python tới CA nội bộ:

```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-noi-bo.pem
```

### Mạng cách ly hoàn toàn

Hai lựa chọn.

**Dùng checkout hoặc mirror nội bộ.** `--local-src` áp cho cả hai ref, nên khi hai phiên bản nằm ở hai thư mục khác nhau thì dùng `--from-src` và `--to-src`:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /mirror/chromium-148/src \
  --to-src   /mirror/chromium-151/src \
  --no-enrich
```

**Chuyển cache từ máy có mạng sang.** Snapshot là JSON thuần:

```bash
# máy có mạng
python3 -m chromedrift snapshot 151.0.7922.138
# chép .chromedrift-cache/snapshots/*.json sang máy cách ly
```

### Bảng sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `could not resolve milestone 151` | Không vào được chromiumdash | Ghi phiên bản đầy đủ. Tra ở chromiumdash.appspot.com/branches |
| `404 …` khi snapshot | Tag không tồn tại | Chỉ tag đã phát hành mới có |
| `GET failed after 4 attempts` | Mạng chập chờn hoặc rate limit | Chạy lại — cache giữ phần đã tải xong. Lặp lại thì xem phần proxy |
| `every target missing for <ref>` | Ref sai hoàn toàn | So lại chuỗi ref; `refs/tags/` được thêm tự động |
| `snapshot: N facts` với N rất nhỏ | `--local-src` trỏ sai chỗ | Phải trỏ vào thư mục `src/` của Chromium, nơi có `content/` và `third_party/` |
| `missing targets: 1` | File không tồn tại ở milestone đó | Bình thường. Chromium di chuyển file giữa các bản |
| `cannot diff snapshots built from different target sets` | Hai snapshot tạo bằng `--target-set` khác nhau | Chạy lại với cùng target set. Công cụ từ chối thay vì so nhầm — một bên thiếu hẳn nhiều loại fact thì mọi fact bên kia sẽ bị đọc thành "mới thêm" |
| `snapshot cache stale (schema N != M)` | Cache tạo bởi bản cũ hơn | Bình thường, tự dựng lại |
| `scope: N FILE(S) OUT OF SCOPE` | Cache cây cũ còn sót file của một lần chạy rộng hơn | Chạy lại phía đó với `--refresh` |
| `must fix: 0` | Hồ sơ chưa có bằng chứng | Chạy `chromedrift profile …`. Nếu `symbols: 0` xem dòng dưới |
| `symbols: 0` trong profile | `patch_dirs` sai, hoặc patch không chứa identifier Chromium | Token trong patch được lọc theo từ vựng Chromium, nên chỉ tên feature/switch/pref thật mới được giữ |
| Quá nhiều mục "review" | `areas.symbols` đặt từ quá chung | Từ như `"Api"`, `"Data"` khớp mọi thứ |
| Kết quả khác lần chạy trước | Dùng số milestone trần | Luôn ghim phiên bản đầy đủ cho báo cáo chính thức |
| (Windows) `FileNotFoundError` khi giải nén | Chạm giới hạn 260 ký tự | Đặt dự án ở đường dẫn ngắn, hoặc `set CHROMEDRIFT_CACHE=C:\cdcache` |
| (Windows) `python3` không phải là lệnh | Windows dùng tên khác | Dùng `py -3` hoặc `python` |

### Cache và log

```bash
CHROMEDRIFT_DEBUG=1 python3 -m chromedrift run …   # in nguyên traceback
python3 -m chromedrift run … --refresh             # bỏ qua cache, tải lại
export CHROMEDRIFT_CACHE=/shared/chromedrift-cache # đặt cache ở nơi khác
```

Cache dùng chung khiến các job CI sau gần như tức thì. Snapshot của tag đã phát hành không bao giờ đổi nên chia sẻ được thoải mái giữa các job và các đội.

### Chạy trong CI

```bash
#!/bin/bash
set -euo pipefail
export CHROMEDRIFT_CACHE=/shared/chromedrift-cache

FROM="148.0.7778.217"        # ghim, đừng dùng số milestone trần
TO="151.0.7922.138"

python3 -m chromedrift check --profile config/sb-profile.json5
python3 -m chromedrift run "$FROM" "$TO" \
  --profile config/sb-profile.json5 \
  --out "reports/${FROM}_to_${TO}"

# Chặn merge nếu còn mục Must fix chưa xử lý
MUST=$(python3 -c "import json,sys; \
  print(json.load(open(sys.argv[1]))['summary']['by_bucket'].get('must_fix', 0))" \
  "reports/${FROM}_to_${TO}/report.json")
[ "$MUST" -eq 0 ] || { echo "Còn $MUST mục phải xử lý trước khi uprev"; exit 1; }
```

---

## 11. Kiểm thử

```bash
python3 -m unittest discover -s tests
```

**273 bài kiểm thử, chạy trong ~0,6 giây, không cần mạng.**

Dữ liệu thử là trích đoạn rút gọn nhưng đúng cấu trúc của file Chromium thật, gồm cả những dạng khó từng làm hỏng các phiên bản parser trước: macro hai tham số, mặc định bọc trong điều kiện tiền xử lý, trạng thái theo từng nền tảng.

Nên chạy lại sau mỗi lần sửa `diff.py` hoặc `impact.py` — đó là hai chỗ chứa các quyết định phân loại.

Một số test không kiểm hành vi mà kiểm **tính nhất quán nội bộ**, vì lớp lỗi hay lặp lại nhất ở dự án này là cùng một sự thật được suy ra ở hai nơi rồi lệch nhau:

- Mọi chỗ hỏi "đường dẫn này có trong phạm vi không" phải cho cùng một câu trả lời.
- Mọi chỗ hỏi "file này có thể khai báo gì không" phải cho cùng một câu trả lời.
- Mọi quy ước tên mà phép đo độ phủ đếm thì phải có bộ đọc nhận, và ngược lại.
- Mọi quy ước tên mà bộ đọc nhận thì phải nằm trong bộ lọc tải về — nếu không, file nằm trên đĩa mà không ai mở, nhìn y hệt như file không tồn tại.
- Mỗi số đo phải có tên riêng: "độ phủ cây nguồn" và "độ phủ theo vùng" là hai thứ khác nhau.
- Cùng một cây nguồn phải cho cùng một tập fact, bất kể hệ thống tệp trả về thư mục theo thứ tự nào.
- Mọi thuộc tính được đem ra so thì phải sinh được một nhãn giải thích; một dòng có điểm số mà cột "vì sao" trống thì không đọc được.
- Mọi con số đo được mà tài liệu ghi ra phải khớp với snapshot trên đĩa.
- Mọi fact phải trỏ đúng dòng khai báo của nó, và số dòng ấy phải đi được tới báo cáo.
- Không lệnh nào được nhận một cờ rồi bỏ qua nó.
- Không chuỗi hiển thị nào được ghi cứng một con số độ phủ — mỗi lần chạy tự đo và tự in.

### Đối chứng với dữ liệu thật

Test đơn vị chỉ chứng minh code làm đúng cái người viết nghĩ. Để kiểm xem nó có đúng thực tế không, bộ trích được viết lại bằng phương pháp khác hẳn — bỏ hết chỉ thị tiền xử lý, tách theo dấu `;`, regex khác — rồi so trên `content_features.cc` giữa M148 và M151:

```
Phương pháp độc lập :  19 thêm,  9 bỏ
Công cụ báo         :  19 thêm,  8 bỏ
```

Truy mục lệch thì hoá ra **công cụ đúng, phép đối chứng sai**: feature không bị xoá mà chuyển từ `content_features.cc` sang `media_switches.cc`, và công cụ báo đúng là `declaration_moved`. Phép đối chứng chỉ nhìn một file nên không thấy.

---

## 12. Cấu trúc mã nguồn

```
chromedrift/
  acquire.py      536 dòng   tải nguồn qua Gitiles hoặc từ checkout local
  targets.py      611        khai báo tải file nào và vì sao; phân vùng; luật độ phủ
  snapshot.py     186        gộp tải + trích xuất thành một ảnh chụp có cache
  extract/      2.306        9 bộ đọc + tiện ích quét C++
  diff.py         927        so sánh ngữ nghĩa, gắn nhãn, nhận diện đổi tên
  cluster.py      214        gom mảnh vụn thành một câu chuyện
  sbprofile.py    474        tập chạm của fork + định nghĩa vùng
  impact.py       258        chấm điểm, phân loại, báo cáo độ phủ vùng
  catalog.py      362        đo target set thiếu gì; kiểm bao đóng tham chiếu
  discover.py     311        tìm file của vendor trong cây fork
  provenance.py   207        tách quyết định cố ý khỏi nợ merge
  coverage.py     249        tìm chỗ fork che upstream bằng cờ build
  model.py        628        cấu trúc dữ liệu dùng chung, đọc/ghi JSON, lọc theo vùng
  jsonc.py        259        bộ đọc JSON5 tự viết
  report/       1.691        markdown + bảng điều khiển HTML tự chứa;
                             gộp finding theo chuyện đã xảy ra và theo màn hình
  enrich/         174        ngữ cảnh từ chromestatus
  cli.py          780        9 lệnh dòng lệnh
```

Toàn bộ đường ống là một chuỗi thẳng các phép biến đổi dữ liệu thuần:

```
Snapshot(ref)            ->  [Fact]      extract/
(Snapshot, Snapshot)     ->  [Change]    diff.py
([Change], TouchSet)     ->  [Finding]   impact.py
[Finding]                ->  [Finding+]  cluster.py, enrich/
[Finding]                ->  báo cáo     report/
```

Mỗi chặng đọc và ghi JSON, nên chặng nào cũng chạy, kiểm tra và chạy lại độc lập được. Điều đó quan trọng ở đây vì chặng đắt (mạng) và chặng phải chỉnh đi chỉnh lại (chấm điểm, báo cáo) có chi phí hoàn toàn khác nhau.

`model.py` giữ một hằng `SCHEMA_VERSION`. Nó được tăng mỗi khi một artifact đã cache thôi mang nghĩa mà bản cũ tưởng nó mang, kèm ghi chú nói rõ cái gì đã hỏng trong im lặng — nhờ vậy cache cũ được dựng lại thay vì bị đọc nhầm.

---

## Đọc thêm

- **[docs/pipeline.html](docs/pipeline.html)** — đường ống từ đầu đến cuối, bám theo một thay đổi có thật. Mở thẳng bằng trình duyệt, không cần mạng, không cần server.
- **[skills/analyzing-chromium-uprevs/SKILL.md](skills/analyzing-chromium-uprevs/SKILL.md)** — gói kiến thức cho agent: quy trình phân loại, bảng tra nhãn, và các bẫy đã kiểm chứng bằng dữ liệu thật. Phần giá trị nhất không phải hướng dẫn chạy lệnh, mà là kiến thức ngăn agent kết luận sai.
