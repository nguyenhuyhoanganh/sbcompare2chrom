# chromedrift

Phát hiện **cái gì đã đổi giữa hai bản Chromium** và **điều đó có ảnh hưởng gì tới browser downstream của bạn** — dành cho đội rebase kiểu M139 → M143 → M148, mỗi lần nhảy vài milestone.

Bài toán không phải là "xem diff". Diff giữa M139 và M143 là hàng triệu dòng. Bài toán là: *trong đống đó, thứ gì chạm vào phần chúng ta đã vá, thứ gì âm thầm đổi hành vi, thứ gì mới đáng lấy về.*

---

## Ý tưởng cốt lõi

**1. Không cần checkout Chromium.**
Kéo thẳng tarball từng thư mục con qua Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<tag>/<dir>.tar.gz
```

Toàn bộ tập file cần thiết ≈ **40 MB/phiên bản**, thay vì ~100 GB và vài giờ `gclient sync`. So sánh hai phiên bản mất vài phút khi cache nguội, và tức thì khi cache ấm. Nếu đội đã có sẵn checkout hoặc mirror nội bộ thì `--local-src` dùng luôn, phần còn lại không đổi.

**2. Chuẩn hoá ngữ nghĩa trước, rồi mới diff.**
Đây là phần quyết định công cụ có dùng được hay không. Giữa M139 và M143, macro `BASE_FEATURE` bỏ tham số tên chuỗi:

```cpp
// M139 — 170/170 khai báo trong content_features.cc
BASE_FEATURE(kBackForwardCache, "BackForwardCache", base::FEATURE_ENABLED_BY_DEFAULT);
// M143 — 175/187 khai báo
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
```

Công cụ diff theo cú pháp sẽ báo *"170 feature bị xoá, 187 feature mới"*. Sau chuẩn hoá (`kFoo` → `"Foo"`), con số thật là **152 giữ nguyên / 18 xoá / 35 thêm**.

**3. AI đứng cuối, không đứng đầu.**
Các tầng tất định làm phần nặng: trích xuất, chuẩn hoá, diff, chấm điểm, gắn bằng chứng. Model chỉ nhận các **bản ghi thay đổi** đã xếp hạng — vài trăm token mỗi bản ghi thay vì vài nghìn dòng. Với cửa sổ 200k, **150 findings gói gọn trong 1 request ~16k token**.

---

## Chạy thử

> Cài đặt trên máy mới, cấu hình, và xử lý sự cố: xem **[SETUP.md](SETUP.md)**.

```bash
# Không cần cài gì — chỉ Python 3.9+ stdlib
python3 -m chromedrift check                    # kiểm tra máy trước

python3 -m chromedrift run 139.0.7258.155 143.0.7499.194 \
  --profile config/sb-profile.example.json5 \
  --no-ai
```

Kết quả trong `out/`: `report.md`, `report.html` (dashboard lọc/sắp xếp được, một file tự chứa), `report.json`.

Các lệnh con chạy độc lập được — tầng đắt (snapshot, tốn mạng) tách khỏi tầng bạn tinh chỉnh liên tục (chấm điểm, prompt, báo cáo):

```bash
python3 -m chromedrift snapshot 143              # trích xuất bề mặt tính năng 1 bản
python3 -m chromedrift diff 139 143              # diff ngữ nghĩa
python3 -m chromedrift profile config/sb.json5   # xem hồ sơ downstream ra cái gì
python3 -m chromedrift report out/report.json --format html
```

`139` tự phân giải thành bản stable Android mới nhất của milestone đó; hoặc ghi thẳng `139.0.7258.155`.

---

## Nó đọc những gì

| Nguồn | Trả lời câu hỏi |
|---|---|
| `base::Feature` trong `*_features.cc` | Cái gì vừa **ship** (default lật từ disabled sang enabled) |
| `runtime_enabled_features.json5` | Web API nào lên `stable`, theo **từng platform** |
| Web IDL (`*.idl`) | Hình dạng API chính xác: method mới / bị xoá / đổi chữ ký |
| Mojo (`*.mojom`) | ABI giữa các process — chỗ vỡ âm thầm lúc runtime |
| `*_switches.cc`, `pref_names.h` | Hợp đồng với script khởi chạy, automation, profile người dùng |
| `flag-metadata.json` | Flag nào **sắp bị xoá** ở milestone tới |
| chromestatus.com | Tóm tắt do người viết + link spec, làm ngữ cảnh cho AI |

### Nhận biết theo platform

Chromium bọc default trong `#if BUILDFLAG(...)`:

```cpp
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
```

Đọc thô ra `enabled`. Trên Android thực tế là `disabled`. Chỉ riêng một file `content_features.cc` đã có **14/187 feature** có default khác nhau theo platform. Với browser chỉ ship Android, đọc sai chỗ này không phải sai số — nó đảo ngược kết luận.

---

## Ba lớp lỗi âm thầm mà nó bắt được

Đây là những thứ không xuất hiện trong release notes và không có compiler nào cảnh báo.

**1. Kill-switch bị dọn ≠ API bị xoá.**
Trên diff M139→M143 thật, **170 trong 202** blink runtime feature "biến mất" vốn đã là `stable`. Blink xoá cờ vài milestone *sau khi* tính năng ship — API vẫn còn, chỉ là không tắt được nữa. Gắn nhãn "web API removed, severity 70" cho 170 mục này sẽ đẩy 170 báo động giả lên đầu báo cáo và giết chết độ tin cậy ngay lần chạy đầu. Chúng được phân loại `killswitch_retired` (severity 35), chỉ thành việc phải làm nếu fork của bạn *đang override* cờ đó.

**2. Tên Finch bị đổi mà không ai sửa tên.**

```cpp
// M139
BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...);  // r thường
// M143 — macro 2 tham số suy tên từ biến
BASE_FEATURE(kFedCmIdPRegistration, base::FEATURE_DISABLED_BY_DEFAULT);
//   → chuỗi feature thành "FedCmIdPRegistration"  (R HOA)
```

Mọi cấu hình field-trial phía server, mọi `--enable-features=FedCmIdPregistration`, mọi override downstream khoá theo tên cũ **lặng lẽ hết tác dụng**. Không lỗi biên dịch, không cảnh báo. Công cụ ghép cặp removed/added theo *biến C++* nên bắt được lớp này (`feature_string_renamed`, severity 75). Cùng cơ chế đó bắt pref bị đổi khoá — làm mồ côi giá trị đã lưu của mọi người dùng hiện có.

**3. Thứ ta phụ thuộc vừa bị xoá.**
Feature bị xoá upstream mà fork còn tham chiếu = build break. Điểm tinh tế: từ điển symbol phải dựng từ **cả hai** snapshot. Dựng chỉ từ bản mới thì symbol vừa bị xoá không nằm trong từ điển và bị lọc mất — đúng ca quan trọng nhất lại là ca bị giấu đi.

---

## Nửa còn lại: hồ sơ downstream

Chromium không biết bạn phụ thuộc vào gì. Chất lượng cột "Must fix" tỉ lệ thuận với độ trung thực của file này (`config/sb-profile.example.json5`). Kết hợp được nhiều nguồn bằng chứng:

- `patch_dirs` — thư mục `.patch`/`.diff`, dạng thường gặp của vendor fork
- `git` — `git diff --name-only <upstream_tag>` với fork toàn bộ source
- `modified_paths` — danh sách tự duy trì
- `source_roots` — quét **mã của bạn** tìm tham chiếu tới symbol Chromium
- `areas` — vùng chức năng kèm `weight`, `owner` để finding tự định tuyến

### Bằng chứng cấp symbol quan trọng hơn cấp đường dẫn

`content_features.cc` khai báo gần 200 feature. Nếu bạn vá một default trong đó, khớp theo *đường dẫn* sẽ khiến cả 200 thay đổi trông như phụ thuộc của bạn. Nên bộ đọc patch trích **cả identifier trong thân hunk**: dòng patch thêm/xoá/kề cận là bằng chứng cụ thể. Điểm cộng phản ánh đúng: đường dẫn `+12`, symbol `+30`, và chỉ symbol mới đủ để đẩy lên `must_fix`.

Chạy thật M139 → M143, bộ target đầy đủ, với demo patch kèm sẵn (`examples/demo-patches/`, dữ liệu tổng hợp có ghi rõ):

```
21.592 facts trích từ 2.513 file (0 lỗi parse, 73 giây tải)
3.118 thay đổi ngữ nghĩa trên 10 loại bề mặt

must fix:        5    ← 2 build break thật + 1 đổi tên Finch + 2 default lật trên Android
needs review:  432
opportunity: 1.396    ← "người dùng vừa có thêm gì"
fyi:         1.285
```

Chỉ 78/3.118 thay đổi giao với fork — đó chính là giá trị của tầng chấm điểm.

Mọi điểm số đều kèm lý do đọc được:

```
base severity 75 (modified base_feature)
  | +12 we patch 1 of the declaring file(s): content/public/common/content_features.cc
  | +30 our source references ServiceWorkerAutoPreload, kServiceWorkerAutoPreload
```

Xếp hạng mà không ai cãi lại được là xếp hạng bị bỏ qua ngay lần đầu nó sai — và ở đây điểm số còn quyết định AI tiêu context vào đâu, nên điểm không giải thích được sẽ lan thành khuyến nghị không giải thích được.

---

## AI nội bộ (200k context)

`config/llm.example.json5`. Client viết bằng `urllib` thuần, **không SDK, không `pip install`** — vì môi trường triển khai thường là mạng nội bộ nơi thêm một package là cả một quy trình.

- `openai` — mọi endpoint `/chat/completions` tương thích (vLLM, TGI, Ollama, gateway nội bộ)
- `anthropic` — Messages API
- `echo` — **không chạm mạng**, trả stub tất định để phát triển và demo offline. Báo cáo ghi rõ khi stub được dùng, để một lần chạy stub không bị nhầm là đã phân tích thật.

Cách ghép batch: nhóm theo *area* để mỗi request là một subsystem mạch lạc, rồi **gộp các nhóm lại chừng nào còn vừa ngân sách**. Nhóm mà không gộp là cái bẫy: mỗi area chỉ vài nghìn token, thành ra tốn 5 request để gửi 4k token trong khi cửa sổ là 200k.

Prompt được thiết kế để **bịa đặt trở nên kém hấp dẫn**: tên feature Chromium gợi hình đủ để model tự tin kể `PwaNavigationCapturing` làm gì chỉ từ cái tên. Nên mỗi bản ghi mang theo bằng chứng thật (default state, status, chữ ký, tóm tắt chromestatus), hướng dẫn buộc trích dẫn bằng chứng đó, và `unknown` là một verdict hạng nhất. Ở đây một câu trả lời sai đầy tự tin tốn của reviewer nhiều thời gian hơn là không trả lời.

Response được cache theo hash(model + prompt) — chỉnh template rồi chạy lại không tốn gì. `max_requests` chặn cứng để cấu hình sai không lặng lẽ biến thành hàng trăm request.

---

## Giới hạn cần biết

- **Không đọc mã triển khai.** Công cụ đọc *khai báo* (macro, IDL, mojom, hằng chuỗi). Một thay đổi hành vi nằm hoàn toàn trong thân hàm, không đụng khai báo nào, sẽ không xuất hiện. Đây là đánh đổi có chủ ý để không cần checkout.
- **chromestatus khớp thấp.** Tên chromestatus là văn xuôi ("Allow more characters in javascript DOM APIs"), tên trong mã là định danh — ghép mờ chỉ trúng ~2%. Trúng thì thêm summary và link spec; không trúng cũng không sao.
- **Bộ target là bề mặt lớn, không phải toàn bộ.** `targets.py` khai báo tường minh những gì được kéo về, để chi phí luôn nhìn thấy được. Thêm nguồn mới là một dòng.
- **Demo patch là dữ liệu tổng hợp.** `examples/demo-patches/` tồn tại để pipeline chạy ra kết quả có nghĩa ngay. Các symbol nó tham chiếu *thật sự* đã đổi giữa M139 và M143; chỉ có chuyện "vendor này phụ thuộc vào chúng" là bịa. Thay bằng patch queue thật trước khi tin kết quả.

---

## Kiểm thử

```bash
python3 -m unittest discover -s tests
```

58 test, không cần mạng. Đã chạy trên macOS (Python 3.14), Ubuntu 24.04 (3.12) và Debian (3.9) — kết quả trùng khớp từng con số. Fixture là trích đoạn rút gọn nhưng đúng cấu trúc của file Chromium thật — gồm cả những dạng khó đã làm hỏng các phiên bản parser trước: macro 2 tham số, default bọc trong tiền xử lý, status theo từng platform.

---

## Cấu trúc

```
chromedrift/
  acquire.py      lấy nguồn qua Gitiles / checkout local, có cache + retry
  targets.py      khai báo kéo file nào, kèm lý do
  extract/        mỗi nguồn sự thật một parser thuần hàm
  diff.py         diff ngữ nghĩa: whitelist thuộc tính, tín hiệu, nhận diện đổi tên
  sbprofile.py    dựng TouchSet downstream từ patch / git / danh sách / quét mã
  impact.py       chấm điểm + phân loại, kèm lý do đọc được
  ai/             ngân sách context, client, prompt, map-reduce
  report/         markdown + dashboard HTML tự chứa
```

Mỗi tầng đọc và ghi JSON, nên tầng nào cũng chạy, kiểm tra và chạy lại độc lập được.
